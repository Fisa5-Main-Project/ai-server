import asyncio

import httpx
import pytest
from fakeredis.aioredis import FakeRedis

from app.gateway.errors import GatewayError
from app.gateway.limiter import RedisLimiter, Limits
from app.gateway.provider import HTTPProvider
from app.gateway.service import Gateway, CallContext
from app.gateway.streaming import prepare_first_chunk
from test_gateway import MemoryUsage


def test_disconnect_before_first_sse_chunk_cancels_work():
    async def case():
        finished=asyncio.Event()
        async def slow_stream():
            try:
                await asyncio.Event().wait()
                yield {}
            finally:
                finished.set()
        async def disconnected():
            return True
        stream=slow_stream()
        with pytest.raises(asyncio.CancelledError):
            await prepare_first_chunk(stream,disconnected,7)
        assert finished.is_set()
    asyncio.run(case())


def test_deadline_covers_slow_admission_before_provider():
    async def case():
        class SlowLimiter:
            limits=Limits()
            async def acquire(self,*args):
                await asyncio.Event().wait()
        class Never:
            provider,model='groq','m'
            async def invoke(self,*args):
                pytest.fail('Cannot call provider after admission deadline')
        usage=MemoryUsage()
        with pytest.raises(GatewayError) as error:
            await Gateway(SlowLimiter(),Never(),usage,deadline=.02).invoke([],CallContext('1','chat','r'))
        assert error.value.status==504
        assert next(iter(usage.events.values()))['status']=='timeout'
    asyncio.run(case())


def test_metering_failure_after_429_prevents_retry():
    async def case():
        class FlakyUsage(MemoryUsage):
            def __init__(self):
                super().__init__()
                self.calls=0
            async def record(self,event):
                self.calls+=1
                if self.calls==2:
                    raise OSError('temporarily unavailable')
                await super().record(event)
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(429,headers={'Retry-After':'0'})
        redis=FakeRedis(decode_responses=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gateway=Gateway(RedisLimiter(redis,'metering',Limits()),
                HTTPProvider(http,'groq','m','secret',100),FlakyUsage(),base_backoff=.01)
            with pytest.raises(GatewayError,match='metering_unavailable'):
                await gateway.invoke([],CallContext('1','chat','r'))
        assert len(calls)==1
        await redis.aclose()
    asyncio.run(case())


def test_blocked_response_preserves_reported_tokens_without_retry():
    async def case():
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(200,json={'candidates':[{'finishReason':'SAFETY'}],
                'usageMetadata':{'promptTokenCount':10,'totalTokenCount':10}})
        redis=FakeRedis(decode_responses=True)
        usage=MemoryUsage()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gateway=Gateway(RedisLimiter(redis,'blocked',Limits()),HTTPProvider(http,'gemini','m','secret',100),usage)
            with pytest.raises(GatewayError,match='provider_invalid_response'):
                await gateway.invoke([],CallContext('1','chat','r'))
        event=next(iter(usage.events.values()))
        assert event['input_tokens']==10 and event['total_tokens']==10
        assert event['output_tokens'] is None
        assert event['status']=='failed' and len(calls)==1
        await redis.aclose()
    asyncio.run(case())
