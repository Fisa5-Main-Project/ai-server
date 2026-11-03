from contextlib import asynccontextmanager

import httpx
from pymongo import MongoClient
from redis.asyncio import Redis

from .auth import signing_key
from .config import GatewaySettings
from .errors import GatewayError
from .limiter import RedisLimiter, Limits
from .provider import HTTPProvider
from .service import Gateway
from .usage import MongoUsage

_gateway = None


def get_gateway():
    if _gateway is None:
        raise GatewayError('gateway_not_ready')
    return _gateway


@asynccontextmanager
async def gateway_lifespan(app):
    global _gateway
    from app.core.config import settings
    config = GatewaySettings()
    signing_key(config.jwt_secret_base64)
    if not config.auth_redis_url:
        raise ValueError('AI_AUTH_REDIS_URL must point to Spring blacklist Redis')
    redis = Redis.from_url(config.redis_url, decode_responses=True, socket_timeout=2,
                           socket_connect_timeout=2, max_connections=100)
    auth_redis = Redis.from_url(config.auth_redis_url, socket_timeout=2,
                                socket_connect_timeout=2, max_connections=50)
    mongo = MongoClient(settings.MONGO_DB_URL, serverSelectionTimeoutMS=2000,
                        connectTimeoutMS=2000, socketTimeoutMS=5000)
    async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=5),
                                limits=httpx.Limits(max_connections=100,max_keepalive_connections=20),
                                transport=httpx.AsyncHTTPTransport(retries=0)) as http:
        try:
            await redis.ping()
            await auth_redis.ping()
            usage = MongoUsage(mongo[settings.MONGO_DB_NAME]['llm_usage'],config.usage_retention_days,
                               config.input_usd_per_million,config.output_usd_per_million)
            await usage.initialize()
            provider_name = settings.LLM_PROVIDER.lower()
            model = config.groq_model if provider_name == 'groq' else config.gemini_model
            key = settings.GROQ_API_KEY if provider_name == 'groq' else settings.GEMINI_API_KEY
            if not key:
                raise ValueError('Configured provider API key is missing')
            # Pool name must be identical on all replicas using the same provider quota.
            limiter = RedisLimiter(redis, config.limit_pool + ':' + provider_name,
                Limits(config.global_rpm,config.user_rpm,config.model_concurrency,config.lease_seconds))
            _gateway = Gateway(limiter,HTTPProvider(http,provider_name,model,key,config.max_output_tokens),
                               usage,config.max_attempts,config.deadline_seconds,max_input_chars=config.max_input_chars)
            app.state.gateway_config, app.state.gateway = config, _gateway
            app.state.auth_redis, app.state.llm_redis, app.state.llm_usage = auth_redis, redis, usage
            yield
        finally:
            _gateway = None
            await redis.aclose()
            await auth_redis.aclose()
            mongo.close()
