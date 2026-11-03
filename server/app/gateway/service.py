import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
import random as rng
import time
from uuid import uuid4

from .errors import GatewayError
from .provider import ProviderLimited

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallContext:
    user_id: str
    feature: str
    request_id: str


current_call = ContextVar('llm_call', default=None)


@contextmanager
def usage_context(user_id, feature):
    token = current_call.set(CallContext(str(user_id), feature, str(uuid4())))
    try:
        yield
    finally:
        current_call.reset(token)


class Gateway:
    def __init__(self, limiter, provider, usage, max_attempts=2, deadline=60,
                 random=rng.random, base_backoff=1.0, max_input_chars=24000):
        if not 1 <= max_attempts <= 3 or not 0 < deadline < limiter.limits.lease_seconds:
            raise ValueError('Attempts must be 1..3; deadline must be shorter than lease')
        self.limiter, self.provider, self.usage = limiter, provider, usage
        self.max_attempts, self.deadline = max_attempts, deadline
        self.random, self.base_backoff, self.max_input_chars = random, base_backoff, max_input_chars

    async def _record(self, event):
        try:
            async with asyncio.timeout(3):
                await self.usage.record(event)
        except Exception as exc:
            logger.error('LLM metering unavailable attempt_id=%s', event['attempt_id'])
            raise GatewayError('metering_unavailable') from exc

    async def invoke(self, messages, context=None, temperature=0.3):
        try:
            async with asyncio.timeout(self.deadline) as budget:
                return await self._invoke(messages, context, temperature, budget)
        except TimeoutError as exc:
            raise GatewayError('gateway_deadline_exceeded', 504) from exc

    async def _finish(self, event, lease):
        if lease is not None:
            try:
                async with asyncio.timeout(2):
                    await self.limiter.release(self.provider.model, lease)
            except Exception:
                logger.error('LLM lease release failed attempt_id=%s', event['attempt_id'])
        try:
            await self._record(event)
        except Exception:
            logger.error('LLM final usage write failed attempt_id=%s', event['attempt_id'])
            if event['status'] in ('success', 'provider_429'):
                raise GatewayError('metering_unavailable')

    async def _invoke(self, messages, context, temperature, budget):
        context = context or current_call.get()
        if context is None:
            raise GatewayError('authenticated_context_required', 401)
        if sum(len(m['content']) for m in messages) > self.max_input_chars:
            raise GatewayError('llm_input_too_large', 413)
        end = time.monotonic() + self.deadline
        for attempt in range(1, self.max_attempts + 1):
            event = {**asdict(context), 'attempt_id':str(uuid4()), 'attempt':attempt,
                     'provider':self.provider.provider, 'model':self.provider.model,
                     'timestamp':datetime.now(timezone.utc), 'status':'started',
                     'outbound_started':False, 'input_tokens':None, 'output_tokens':None,
                     'total_tokens':None, 'cached_input_tokens':None}
            lease = None
            limited = None
            started = time.monotonic()
            try:
                lease = await self.limiter.acquire(context.user_id, self.provider.model, event['attempt_id'])
                # Intent persisted BEFORE outbound; a crash is visible as unfinished/unknown usage.
                await self._record(event)
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise GatewayError('provider_timeout', 504)
                event['outbound_started'] = True
                async with asyncio.timeout(remaining):
                    result = await self.provider.invoke(messages, temperature)
                event.update({k:v for k,v in asdict(result).items() if k != 'content'})
                event['status'] = 'success'
                return result
            except ProviderLimited as exc:
                limited = exc
                delay = max(0.01, exc.delay or 0, self.base_backoff * 2 ** (attempt - 1)) + self.random() * 0.25
                # Coordinate all replicas, not just this coroutine.
                event.update(status='provider_429', error_code=exc.code)
                await self.limiter.cooldown(delay)
            except asyncio.CancelledError:
                event.update(status='timeout' if budget.expired() else 'cancelled',
                             error_code='gateway_deadline_exceeded' if budget.expired() else 'cancelled')
                raise
            except TimeoutError as exc:
                event.update(status='timeout', error_code='provider_timeout')
                raise GatewayError('provider_timeout', 504) from exc
            except GatewayError as exc:
                event.update(getattr(exc, 'usage', {}))
                event.update(status=('timeout' if exc.status == 504 else
                    'rejected' if not event['outbound_started'] else 'failed'), error_code=exc.code)
                raise
            finally:
                event['latency_ms'] = round((time.monotonic() - started) * 1000)
                # Shield the WHOLE finalization, including when cancellation arrives during cleanup.
                # Cleanup has a separate bounded 2s release + 3s ledger budget.
                finish = asyncio.create_task(self._finish(dict(event), lease))
                try:
                    await asyncio.shield(finish)
                except asyncio.CancelledError:
                    try:
                        await asyncio.shield(finish)
                    finally:
                        raise
            if limited:
                if attempt == self.max_attempts or delay >= end - time.monotonic():
                    raise GatewayError('provider_rate_limit', 429, delay)
                await asyncio.sleep(delay)
        raise GatewayError('provider_unavailable')
