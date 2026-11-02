import asyncio
import importlib
import sys
from types import ModuleType
from unittest.mock import Mock, AsyncMock
from test_service import module as products_module
from app.schemas.chat import ChatProduct


def test_recommendation_stream_never_calls_unvalidated_second_model(monkeypatch):
    # Only external model/vector clients are replaced; run the real ChatService generator.
    vector = ModuleType('app.db.vector_store')
    for name in ('deposit_vector_store', 'saving_vector_store', 'annuity_vector_store', 'fund_vector_store'):
        setattr(vector, name, None)
    monkeypatch.setitem(sys.modules, 'app.db.vector_store', vector)
    factory = ModuleType('app.core.llm_factory')
    factory.get_llm = lambda **kwargs: Mock()
    monkeypatch.setitem(sys.modules, 'app.core.llm_factory', factory)
    module = importlib.import_module('app.services.chat_service')
    service = module.ChatService.__new__(module.ChatService)
    service.validate_input = lambda _: None
    service.is_financial_question = lambda _: True
    service.get_user_context = lambda *args: 'persona'
    service.get_chat_history = lambda *args, **kwargs: []
    service.save_message = Mock()
    service.check_feature_navigation = lambda _: None
    service.llm = Mock()
    service.llm.astream.side_effect = AssertionError('Unvalidated generation must not run')
    validated = ChatProduct(id='safe', icon='💰', type='예금', name='검증예금', bank='우리은행',
                            features=['적합성 검증 통과'], stat='위험 6등급', link='https://example.com')
    monkeypatch.setattr(module.products_service, 'get_chat_products', AsyncMock(return_value=[validated]))

    async def collect(message):
        return [event async for event in service.stream_chat(1, 'session', message)]

    for query in ('예금 추천', '어디에 가입할까', '어떤 펀드가 좋을까?', '내 자산 포트폴리오를 짜줘'):
        events = asyncio.run(collect(query))
        assert events[-1]['type'] == 'done'
        assert '검증예금' in events[-1]['content']
        assert any(e['type'] == 'products' for e in events)
    monkeypatch.setattr(module.products_service, 'get_chat_products', AsyncMock(return_value=[]))
    events = asyncio.run(collect('예금 추천'))
    assert events[-1]['type'] == 'done'
    assert '없' in events[-1]['content']
    assert not any(e['type'] == 'products' for e in events)
    events = asyncio.run(collect('금리란 무엇인가요?'))
    assert events[-1]['type'] == 'done'
    assert not any(e['type'] == 'products' for e in events)
