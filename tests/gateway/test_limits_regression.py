import asyncio

import httpx
import pytest
from fakeredis.aioredis import FakeRedis

from app.gateway.errors import GatewayError
from app.gateway.limiter import RedisLimiter, Limits
from app.gateway.provider import HTTPProvider
from app.gateway.service import Gateway, CallContext
from test_gateway import MemoryUsage


def test_retry_cannot_bypass_rpm_budget():
    async def case():
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(429,headers={'Retry-After':'0'})
        redis=FakeRedis(decode_responses=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            usage=MemoryUsage()
            gateway=Gateway(RedisLimiter(redis,'retry',Limits(global_rpm=1)),
                HTTPProvider(http,'groq','m','secret',100),usage,base_backoff=.01,random=lambda:0)
            with pytest.raises(GatewayError,match='global_rate_limit'):
                await gateway.invoke([],CallContext('1','chat','r'))
        assert len(calls)==1
        assert {e['status'] for e in usage.events.values()}=={'provider_429','rejected'}
        await redis.aclose()
    asyncio.run(case())


def test_gateway_error_survives_graph_fallback():
    from app.rag.graphs.product_graph import build_product_graph
    class Denied:
        async def ainvoke(self,*args):
            raise GatewayError('user_rate_limit',429,20)
    async def retrieve(*args):
        pytest.fail('Denied LLM admission must not continue to retrieval')
    with pytest.raises(GatewayError,match='user_rate_limit'):
        asyncio.run(build_product_graph(model=Denied(),retrieve=retrieve).ainvoke({'query':'예금 추천'}))


def test_missing_identity_and_oversized_prompt_cannot_reach_provider():
    async def case():
        class Never:
            provider,model='groq','m'
            async def invoke(self,*args):
                pytest.fail('Provider must not be called')
        redis=FakeRedis(decode_responses=True)
        gateway=Gateway(RedisLimiter(redis,'identity',Limits()),Never(),MemoryUsage(),max_input_chars=3)
        with pytest.raises(GatewayError,match='authenticated_context_required'):
            await gateway.invoke([])
        with pytest.raises(GatewayError,match='llm_input_too_large'):
            await gateway.invoke([{'role':'user','content':'1234'}],CallContext('1','chat','r'))
        await redis.aclose()
    asyncio.run(case())
