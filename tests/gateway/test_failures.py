import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fakeredis.aioredis import FakeRedis

from app.gateway.errors import GatewayError
from app.gateway.limiter import RedisLimiter, Limits
from app.gateway.provider import HTTPProvider
from app.gateway.service import Gateway, CallContext
from test_gateway import MemoryUsage


def test_redis_outage_fails_closed():
    async def case():
        # Use supported server connected flag to exercise Redis connection error mapping.
        import fakeredis
        server = fakeredis.FakeServer()
        r = FakeRedis(server=server,decode_responses=True)
        server.connected = False
        with pytest.raises(GatewayError,match='limiter_unavailable'):
            await RedisLimiter(r,'outage',Limits()).acquire('1','m','a')
        await r.aclose()
    asyncio.run(case())


def test_cancelled_provider_releases_lease_and_records_unknown_tokens():
    async def case():
        entered = asyncio.Event()
        class Slow:
            provider, model = 'groq','m'
            async def invoke(self,*args):
                entered.set()
                await asyncio.Event().wait()
        r = FakeRedis(decode_responses=True)
        limiter = RedisLimiter(r,'cancel',Limits(concurrency=1))
        usage = MemoryUsage()
        task = asyncio.create_task(Gateway(limiter,Slow(),usage).invoke([],CallContext('1','chat','r')))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        event = next(iter(usage.events.values()))
        assert event['status'] == 'cancelled' and event['input_tokens'] is None
        assert await limiter.acquire('1','m','next')
        await r.aclose()
    asyncio.run(case())


def test_no_retry_for_500_and_no_usage_metadata_is_not_zero():
    async def case():
        for status in (500,200):
            calls=[]
            def handler(req):
                calls.append(req)
                return httpx.Response(status,json={'choices':[{'message':{'content':'{}'}}]})
            r = FakeRedis(decode_responses=True)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                usage = MemoryUsage()
                g = Gateway(RedisLimiter(r,str(status),Limits()),HTTPProvider(http,'groq','m','s',100),usage)
                if status == 500:
                    with pytest.raises(GatewayError,match='provider_error'):
                        await g.invoke([],CallContext('1','chat','r'))
                else:
                    result = await g.invoke([],CallContext('1','chat','r'))
                    assert result.input_tokens is None and result.output_tokens is None
                assert len(calls) == 1
            await r.aclose()
    asyncio.run(case())
