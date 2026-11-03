import asyncio
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest
from fakeredis.aioredis import FakeRedis

from app.gateway.errors import GatewayError
from app.gateway.limiter import RedisLimiter, Limits
from app.gateway.provider import HTTPProvider, retry_after_seconds
from app.gateway.service import Gateway, CallContext


class MemoryUsage:
    def __init__(self):
        self.events = {}

    async def record(self, event):
        self.events.setdefault(event['attempt_id'], {}).update(event)


def run(coro):
    return asyncio.run(coro)


def test_atomic_global_limit_across_two_instances():
    async def case():
        redis = FakeRedis(decode_responses=True)
        limits = Limits(global_rpm=5, user_rpm=5, concurrency=20)
        clients = [RedisLimiter(redis, 'test', limits) for _ in range(2)]
        async def admit(i):
            try:
                return await clients[i % 2].acquire(str(i), 'model', str(i))
            except GatewayError as exc:
                assert exc.code == 'global_rate_limit'
                return None
        results = await asyncio.gather(*(admit(i) for i in range(30)))
        assert sum(x is not None for x in results) == 5
        await redis.aclose()
    run(case())


def test_user_denial_does_not_consume_shared_capacity():
    async def case():
        redis = FakeRedis(decode_responses=True)
        limiter = RedisLimiter(redis, 'test', Limits(global_rpm=2, user_rpm=1, concurrency=5))
        lease = await limiter.acquire('u1', 'model', 'a')
        await limiter.release('model', lease)
        with pytest.raises(GatewayError, match='user_rate_limit'):
            await limiter.acquire('u1', 'model', 'b')
        assert await limiter.acquire('u2', 'model', 'c')
        await redis.aclose()
    run(case())


def test_model_concurrency_release_and_independent_models():
    async def case():
        redis = FakeRedis(decode_responses=True)
        limiter = RedisLimiter(redis, 'test', Limits(global_rpm=20, user_rpm=20, concurrency=1))
        lease = await limiter.acquire('u', 'a', 'one')
        with pytest.raises(GatewayError, match='concurrency_limit'):
            await limiter.acquire('u', 'a', 'two')
        assert await limiter.acquire('u', 'b', 'three')
        await limiter.release('a', lease)
        assert await limiter.acquire('u', 'a', 'four')
        await redis.aclose()
    run(case())


def test_shared_cooldown_cannot_be_shortened():
    async def case():
        redis = FakeRedis(decode_responses=True)
        limiter = RedisLimiter(redis, 'test', Limits())
        await limiter.cooldown(10)
        await limiter.cooldown(1)
        with pytest.raises(GatewayError) as caught:
            await limiter.acquire('u', 'm', 'one')
        assert caught.value.code == 'provider_cooldown'
        assert caught.value.retry_after >= 9
        await redis.aclose()
    run(case())


def test_retry_after_seconds_and_http_date():
    now = datetime.now(timezone.utc)
    assert retry_after_seconds('12', now) == 12
    assert 6 <= retry_after_seconds(format_datetime(now + timedelta(seconds=7)), now) <= 7
    assert retry_after_seconds('invalid', now) is None
    assert retry_after_seconds('-1', now) is None


def test_gateway_counts_physical_attempts_and_tokens():
    async def case():
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={'Retry-After': '0'})
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20}})
        redis = FakeRedis(decode_responses=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            usage = MemoryUsage()
            provider = HTTPProvider(http, 'groq', 'model', 'secret', 512)
            gateway = Gateway(RedisLimiter(redis, 'test', Limits()), provider, usage, max_attempts=2,
                              random=lambda: 0, base_backoff=0)
            result = await gateway.invoke([{'role':'user','content':'hi'}], CallContext('1','chat','r1'))
        assert result.content == '{}'
        assert len(calls) == 2
        assert sorted(e['status'] for e in usage.events.values()) == ['provider_429', 'success']
        success = next(e for e in usage.events.values() if e['status'] == 'success')
        assert success['input_tokens'] == 12 and success['output_tokens'] == 8
        assert success['user_id'] == '1' and success['feature'] == 'chat'
        assert all('prompt' not in e and 'api_key' not in e for e in usage.events.values())
        await redis.aclose()
    run(case())


def test_long_retry_after_returns_without_retry():
    async def case():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={'Retry-After':'120'})
        redis = FakeRedis(decode_responses=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gateway = Gateway(RedisLimiter(redis, 'test', Limits()),
                HTTPProvider(http,'groq','model','secret',512), MemoryUsage(), deadline=1)
            with pytest.raises(GatewayError) as caught:
                await gateway.invoke([], CallContext('1','chat','r1'))
            assert caught.value.status == 429 and caught.value.retry_after >= 120
        assert len(calls) == 1
        await redis.aclose()
    run(case())


def test_timeout_is_not_retried_and_lease_is_released():
    async def case():
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout('private request contents')
        redis = FakeRedis(decode_responses=True)
        limiter = RedisLimiter(redis, 'test', Limits(concurrency=1))
        usage = MemoryUsage()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gateway = Gateway(limiter, HTTPProvider(http,'groq','model','secret',512), usage)
            with pytest.raises(GatewayError) as caught:
                await gateway.invoke([], CallContext('1','chat','r1'))
            assert caught.value.status == 504
        assert len(calls) == 1
        assert await limiter.acquire('1','model','next')
        assert next(iter(usage.events.values()))['status'] == 'timeout'
        await redis.aclose()
    run(case())


def test_gemini_metering_includes_thinking_tokens():
    async def case():
        def handler(request):
            assert request.headers['x-goog-api-key'] == 'secret'
            assert 'secret' not in str(request.url)
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'{}'}]}}],
                'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':4,'thoughtsTokenCount':6,'totalTokenCount':20}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            response = await HTTPProvider(http,'gemini','gemini-2.5-flash','secret',512).invoke([],0)
        assert response.input_tokens == 10 and response.output_tokens == 10
        assert response.total_tokens == 20
    run(case())


def test_usage_failure_prevents_outbound_call():
    async def case():
        class BrokenUsage:
            async def record(self, event):
                raise OSError('db down')
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200)
        redis = FakeRedis(decode_responses=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gateway = Gateway(RedisLimiter(redis,'test',Limits()),
                HTTPProvider(http,'groq','m','secret',512),BrokenUsage())
            with pytest.raises(GatewayError) as caught:
                await gateway.invoke([],CallContext('1','chat','r'))
            assert caught.value.status == 503
        assert not calls
        await redis.aclose()
    run(case())
