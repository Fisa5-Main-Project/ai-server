import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.gateway.auth import authenticated_user, Principal
from app.gateway.errors import GatewayError
from app.gateway.service import current_call


def load_endpoint(name, service_name, service):
    path = Path(__file__).resolve().parents[2] / 'server/app/api/v1/endpoints' / (name+'.py')
    spec = importlib.util.spec_from_file_location('gateway_test_'+name,path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {f'app.services.{service_name}':SimpleNamespace(**{service_name:service})}):
        spec.loader.exec_module(module)
    return module


def client_for(module, user=7, roles=frozenset({'ROLE_USER'})):
    app = FastAPI()
    app.include_router(module.router)
    async def principal():
        return Principal(user,roles)
    app.dependency_overrides[authenticated_user] = principal
    @app.exception_handler(GatewayError)
    async def handle(request,exc):
        return JSONResponse({'error':exc.payload()},status_code=exc.status,
                            headers={'Retry-After':str(exc.retry_after)})
    return TestClient(app)


def test_chat_rate_denial_is_http_429_before_sse_and_has_verified_context():
    async def stream_chat(**kwargs):
        context = current_call.get()
        assert context.user_id == '7' and context.feature == 'chat'
        raise GatewayError('global_rate_limit',429,12)
        yield  # async generator, no completed content.
    client = client_for(load_endpoint('chat','chat_service',SimpleNamespace(stream_chat=stream_chat)))
    response = client.post('/chat/stream',json={'user_id':7,'session_id':'s','message':'예금 추천'})
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '12'
    assert response.json()['error']['code'] == 'global_rate_limit'


def test_impersonation_stops_before_service():
    service = Mock()
    client = client_for(load_endpoint('chat','chat_service',service))
    response = client.post('/chat/stream',json={'user_id':8,'session_id':'s','message':'예금'})
    assert response.status_code == 403
    service.stream_chat.assert_not_called()


def test_successful_sse_wire_format_preserved():
    async def stream_chat(**kwargs):
        yield {'type':'token','content':'응답'}
        yield {'type':'done','content':'응답'}
    client = client_for(load_endpoint('chat','chat_service',SimpleNamespace(stream_chat=stream_chat)))
    response = client.post('/chat/stream',json={'user_id':7,'session_id':'s','message':'예금'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.text.count('data: ') == 2


def test_recommendation_gateway_error_is_not_wrapped_in_500():
    service = SimpleNamespace(get_recommendations=AsyncMock(side_effect=GatewayError('user_rate_limit',429,10)))
    client = client_for(load_endpoint('recommend','products_service',service))
    response = client.get('/recommendations/7')
    assert response.status_code == 429


def test_admin_usage_denies_normal_user_and_bounds_date_range():
    module = load_endpoint('admin','admin_service',Mock())
    client = client_for(module)
    assert client.get('/stats/llm-usage').status_code == 403
    admin = client_for(module,roles=frozenset({'ROLE_ADMIN'}))
    admin.app.state.llm_usage = SimpleNamespace(summary=AsyncMock(return_value={'rows':[]}))
    assert admin.get('/stats/llm-usage?days=91').status_code == 422
    assert admin.get('/stats/llm-usage?days=7').json() == {'rows':[]}
