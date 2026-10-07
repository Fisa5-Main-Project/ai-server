"""Serving tests: verify the financial context handed to the recommendation graph."""
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage


@pytest.fixture
def products(monkeypatch):
    module = importlib.import_module("app.services.products_service")
    graph = Mock()
    graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content='{"products": []}')]})
    monkeypatch.setattr(module, "product_graph", graph)
    current = Mock()
    monkeypatch.setattr(module, "user_vectorization_service", current)
    service = module.ProductsService.__new__(module.ProductsService)
    service._apply_feedback_reranking = lambda _, products: products
    return service, current, graph


def test_each_recommendation_uses_current_financial_context(products):
    service, current, graph = products
    current.get_current_persona.side_effect = ["잔액 100원, 은퇴 전", "잔액 200원, 은퇴"]
    asyncio.run(service.get_recommendations(1))
    asyncio.run(service.get_recommendations(1))
    contexts = [call.args[0]["persona"] for call in graph.ainvoke.call_args_list]
    assert contexts == ["잔액 100원, 은퇴 전", "잔액 200원, 은퇴"]
    current.vectorize_user.assert_not_called()


def test_source_failure_prevents_recommendation_with_stale_context(products):
    service, current, graph = products
    current.get_current_persona.side_effect = ConnectionError("mysql unavailable")
    with pytest.raises(ConnectionError):
        asyncio.run(service.get_recommendations(1))
    graph.ainvoke.assert_not_called()


def test_chat_recommendation_reuses_same_request_snapshot(products):
    service, current, graph = products
    asyncio.run(service.get_chat_products(1, "추천해줘", persona_text="동일 요청 잔액 123원"))
    current.get_current_persona.assert_not_called()
    assert graph.ainvoke.call_args.args[0]["persona"] == "동일 요청 잔액 123원"


def test_chat_context_is_refreshed_on_each_request(monkeypatch):
    module = importlib.import_module("app.services.chat_service")
    current = Mock()
    current.get_current_persona.side_effect = ["은퇴 전, 잔액 1원", "은퇴, 잔액 2원"]
    monkeypatch.setattr(module, "user_vectorization_service", current)
    service = module.ChatService.__new__(module.ChatService)
    assert service.get_user_context(1) == "은퇴 전, 잔액 1원"
    assert service.get_user_context(1) == "은퇴, 잔액 2원"
