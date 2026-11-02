import asyncio
import os
from unittest.mock import Mock, AsyncMock
from test_policy import product, profile, TODAY

for key, value in {'GEMINI_API_KEY': 'test', 'MONGO_DB_NAME': 'test', 'MONGO_USERNAME': 'test',
                   'MONGO_PASSWORD': 'test', 'MONGO_HOST': 'localhost', 'MONGO_URI': 'mongodb://localhost:27017',
                   'MYSQL_DB_URL': 'mysql+pymysql://test:test@localhost/test'}.items():
    os.environ[key] = value

from app.services import products_service as module


def setup(monkeypatch):
    service = module.ProductsService.__new__(module.ProductsService)
    service.chat_logs_collection = Mock()
    service.chat_logs_collection.find.return_value = []
    service.audit_collection = Mock()
    source = Mock()
    source.get_user_data_from_db.return_value = {'user': {'investment_tendancy': '안정추구형'},
        'assets': [{'type': 'CURRENT', 'balance': 1000000}]}
    monkeypatch.setattr(module, 'user_vectorization_service', source)
    async def retrieve(intent, query):
        return [product()]
    graph = module.build_product_graph(model=Mock(ainvoke=AsyncMock(side_effect=RuntimeError())),
                                       retrieve=retrieve, today=lambda: TODAY)
    monkeypatch.setattr(module, 'product_graph', graph)
    return service, source


def test_service_uses_source_profile_and_persists_decisions(monkeypatch):
    service, source = setup(monkeypatch)
    response = asyncio.run(service.get_recommendations(42, '예금 추천', persona_text='공격투자형 자산 999억원'))
    assert [p.product_id for p in response.products] == ['d1']
    record = service.audit_collection.insert_one.call_args.args[0]
    assert record['user_id'] == 42
    assert record['profile']['tendency'] == '안정추구형'
    assert record['decisions'][0]['status'] == 'selected'
    assert record['products'][0]['reason']


def test_feedback_failure_never_returns_products(monkeypatch):
    service, _ = setup(monkeypatch)
    service.chat_logs_collection.find.side_effect = RuntimeError('unavailable')
    assert asyncio.run(service.get_recommendations(42)).products == []


def test_audit_failure_never_returns_untracked_products(monkeypatch):
    service, _ = setup(monkeypatch)
    service.audit_collection.insert_one.side_effect = RuntimeError('unavailable')
    assert asyncio.run(service.get_recommendations(42)).products == []


def test_dislike_history_is_applied_before_generation(monkeypatch):
    service, _ = setup(monkeypatch)
    service.chat_logs_collection.find.return_value = [{'product_id': 'd1', 'feedback': 'dislike'}]
    assert asyncio.run(service.get_recommendations(42)).products == []
    assert 'disliked' in service.audit_collection.insert_one.call_args.args[0]['decisions'][0]['reasons']
