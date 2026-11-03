"""Serving tests: verify the financial context handed to the recommendation graph."""
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def products(monkeypatch):
    module = importlib.import_module("app.services.products_service")
    graph = Mock()
    graph.ainvoke = AsyncMock(return_value={"products": [], "intent": {}, "decisions": []})
    monkeypatch.setattr(module, "product_graph", graph)
    current = Mock()
    monkeypatch.setattr(module, "user_vectorization_service", current)
    service = module.ProductsService.__new__(module.ProductsService)
    service.chat_logs_collection = Mock()
    service.chat_logs_collection.find.return_value = []
    service.audit_collection = Mock()
    return service, current, graph


def test_each_recommendation_uses_current_financial_context(products):
    service, current, graph = products
    current.get_user_data_from_db.side_effect = [
        {"user": {"investment_tendancy": "안정추구형"}, "assets": [{"type": "CURRENT", "balance": 100}]},
        {"user": {"investment_tendancy": "원금보장형"}, "assets": [{"type": "CURRENT", "balance": 200}]},
    ]
    asyncio.run(service.get_recommendations(1))
    asyncio.run(service.get_recommendations(1))
    contexts = [call.args[0]["profile"] for call in graph.ainvoke.call_args_list]
    assert [c["available_funds"] for c in contexts] == [100, 200]
    assert [c["tendency"] for c in contexts] == ["안정추구형", "원금보장형"]
    current.vectorize_user.assert_not_called()


def test_source_failure_prevents_recommendation_with_stale_context(products):
    service, current, graph = products
    current.get_user_data_from_db.side_effect = ConnectionError("mysql unavailable")
    result = asyncio.run(service.get_recommendations(1))
    assert result.products == []
    assert result.status == "unavailable"
    graph.ainvoke.assert_not_called()


def test_chat_recommendation_does_not_trust_persona_as_financial_evidence(products):
    service, current, graph = products
    current.get_user_data_from_db.return_value = {
        "user": {"investment_tendancy": "원금보장형"}, "assets": [{"type": "CURRENT", "balance": 100}]}
    asyncio.run(service.get_chat_products(1, "추천해줘", persona_text="공격투자형 잔액 999억원"))
    current.get_current_persona.assert_not_called()
    assert graph.ainvoke.call_args.args[0]["profile"]["available_funds"] == 100
    assert graph.ainvoke.call_args.args[0]["profile"]["tendency"] == "원금보장형"


def test_chat_context_is_refreshed_on_each_request(monkeypatch):
    module = importlib.import_module("app.services.chat_service")
    current = Mock()
    current.get_current_persona.side_effect = ["은퇴 전, 잔액 1원", "은퇴, 잔액 2원"]
    monkeypatch.setattr(module, "user_vectorization_service", current)
    service = module.ChatService.__new__(module.ChatService)
    assert service.get_user_context(1) == "은퇴 전, 잔액 1원"
    assert service.get_user_context(1) == "은퇴, 잔액 2원"
