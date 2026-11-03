"""Opt-in integration tests. Never flush a DB; each test uses a unique key group."""
import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.gateway.errors import GatewayError
from app.gateway.limiter import RedisLimiter, Limits

pytestmark = pytest.mark.skipif(not os.getenv('TEST_REDIS_URL'), reason='Set isolated TEST_REDIS_URL')


def test_real_redis_500_competing_calls_share_exact_limit():
    async def case():
        clients = [Redis.from_url(os.environ['TEST_REDIS_URL'],decode_responses=True) for _ in range(5)]
        group = 'integration:' + uuid4().hex
        limiters = [RedisLimiter(r,group,Limits(global_rpm=30,user_rpm=5,concurrency=100)) for r in clients]
        async def request(i):
            limiter = limiters[i % 5]
            try:
                lease = await limiter.acquire(str(i % 10),'m',str(uuid4()))
                await limiter.release('m',lease)
                return True
            except GatewayError as exc:
                assert exc.status == 429
                return False
        try:
            assert sum(await asyncio.gather(*(request(i) for i in range(500)))) == 30
        finally:
            for r in clients:
                await r.aclose()
    asyncio.run(case())


def test_real_redis_expired_crashed_lease_is_reclaimed():
    async def case():
        r = Redis.from_url(os.environ['TEST_REDIS_URL'],decode_responses=True)
        limiter = RedisLimiter(r,uuid4().hex,Limits(concurrency=1,lease_seconds=1))
        try:
            await limiter.acquire('u','m','crashed')
            with pytest.raises(GatewayError,match='concurrency_limit'):
                await limiter.acquire('u','m','blocked')
            await asyncio.sleep(1.1)
            assert await limiter.acquire('u','m','recovered')
        finally:
            await r.aclose()
    asyncio.run(case())


def test_real_redis_rolling_window_and_global_cross_model_limit():
    async def case():
        r = Redis.from_url(os.environ['TEST_REDIS_URL'],decode_responses=True)
        limiter = RedisLimiter(r,uuid4().hex,Limits(global_rpm=1,user_rpm=1))
        try:
            lease = await limiter.acquire('u','model_a','a')
            await limiter.release('model_a',lease)
            with pytest.raises(GatewayError,match='global_rate_limit'):
                await limiter.acquire('other','model_b','b')
            # Advance only this test's accepted timestamp beyond the rolling window.
            seconds, micros = await r.time()
            expired = seconds * 1000 + micros // 1000 - 60001
            await r.zadd(limiter._key('global'),{'a':expired})
            await r.zadd(limiter._key('user','u'),{'a':expired})
            assert await limiter.acquire('u','model_b','c')
        finally:
            await r.aclose()
    asyncio.run(case())
