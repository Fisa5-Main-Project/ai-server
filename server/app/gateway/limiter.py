"""Single atomic admission round trip, shared across processes and replicas."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from redis.exceptions import RedisError

from .errors import GatewayError


@dataclass(frozen=True)
class Limits:
    global_rpm: int = 54
    user_rpm: int = 30
    concurrency: int = 4
    lease_seconds: int = 75

    def __post_init__(self):
        if min(self.global_rpm, self.user_rpm, self.concurrency, self.lease_seconds) < 1:
            raise ValueError('All limits must be positive')


class RedisLimiter:
    def __init__(self, redis, pool: str, limits: Limits):
        self.redis, self.limits = redis, limits
        # Same hash slot for atomic multi-key admission on Redis Cluster.
        self.prefix = 'llm:{' + hashlib.sha256(pool.encode()).hexdigest()[:24] + '}'
        self.admit_script = redis.register_script(Path(__file__).with_name('admit.lua').read_text())
        self.cooldown_script = redis.register_script('''
            local old = redis.call('PTTL', KEYS[1])
            local duration = tonumber(ARGV[1])
            if duration > old then redis.call('SET', KEYS[1], '1', 'PX', duration) end
            return 1
        ''')

    def _key(self, kind, identity=''):
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24] if identity else ''
        return f'{self.prefix}:{kind}:{digest}'

    async def acquire(self, user: str, model: str, attempt_id: str):
        try:
            result = await self.admit_script(keys=[self._key('global'), self._key('user', user),
                self._key('leases', model), self._key('cooldown')], args=[
                    self.limits.global_rpm, self.limits.user_rpm, self.limits.concurrency,
                    self.limits.lease_seconds * 1000, attempt_id])
        except RedisError as exc:
            raise GatewayError('limiter_unavailable') from exc
        code, wait_ms = int(result[0]), int(result[1])
        if code:
            reason = {1:'global_rate_limit', 2:'user_rate_limit', 3:'concurrency_limit',
                      4:'provider_cooldown'}[code]
            raise GatewayError(reason, 429, max(1, wait_ms / 1000))
        return attempt_id

    async def release(self, model, lease):
        try:
            await self.redis.zrem(self._key('leases', model), lease)
        except RedisError as exc:
            raise GatewayError('limiter_unavailable') from exc

    async def cooldown(self, seconds):
        try:
            await self.cooldown_script(keys=[self._key('cooldown')], args=[max(1, int(seconds * 1000))])
        except RedisError as exc:
            raise GatewayError('limiter_unavailable') from exc
