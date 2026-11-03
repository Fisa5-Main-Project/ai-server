import base64
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pymongo import MongoClient
from redis import Redis

from app.gateway.auth import authenticated_user
from app.gateway.errors import GatewayError
from app.gateway.runtime import gateway_lifespan, get_gateway

pytestmark = pytest.mark.skipif(not (os.getenv('TEST_REDIS_URL') and os.getenv('TEST_MONGO_URL')),
                                reason='Set isolated Redis and Mongo URLs')


def test_startup_verified_jwt_blacklist_and_shutdown(monkeypatch):
    import sys
    db_name='gateway_runtime_'+uuid4().hex
    key=b'r'*64
    monkeypatch.setenv('AI_REDIS_URL',os.environ['TEST_REDIS_URL'])
    monkeypatch.setenv('AI_AUTH_REDIS_URL',os.environ['TEST_REDIS_URL'])
    monkeypatch.setenv('AI_JWT_SECRET_BASE64',base64.b64encode(key).decode())
    monkeypatch.setenv('AI_LIMIT_POOL',uuid4().hex)
    settings=SimpleNamespace(MONGO_DB_URL=os.environ['TEST_MONGO_URL'],MONGO_DB_NAME=db_name,
                             LLM_PROVIDER='groq',GROQ_API_KEY='test-not-a-real-key')
    monkeypatch.setitem(sys.modules,'app.core.config',SimpleNamespace(settings=settings))
    app=FastAPI(lifespan=gateway_lifespan)
    @app.exception_handler(GatewayError)
    async def handle(request,exc):
        return JSONResponse({'code':exc.code},status_code=exc.status)
    @app.get('/identity')
    async def identity(principal=Depends(authenticated_user)):
        return {'user_id':principal.user_id,'model':get_gateway().provider.model}
    token=jwt.encode({'sub':'77','exp':time.time()+60,'authorities':'ROLE_USER','jti':uuid4().hex},key,algorithm='HS512')
    redis=Redis.from_url(os.environ['TEST_REDIS_URL'])
    mongo=MongoClient(os.environ['TEST_MONGO_URL'])
    try:
        with TestClient(app) as client:
            assert client.get('/identity').status_code==401
            assert client.get('/identity',headers={'Authorization':'Bearer '+token}).json()['user_id']==77
            redis.set(token,'logout',ex=60)
            denied=client.get('/identity',headers={'Authorization':'Bearer '+token})
            assert denied.status_code==401 and denied.json()['code']=='access_token_revoked'
        with pytest.raises(GatewayError,match='gateway_not_ready'):
            get_gateway()
    finally:
        redis.delete(token)
        redis.close()
        mongo.drop_database(db_name)
        mongo.close()
