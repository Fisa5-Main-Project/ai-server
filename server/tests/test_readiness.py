import importlib
import json
from unittest.mock import Mock

import pytest


@pytest.fixture
def readiness(monkeypatch):
    module = importlib.import_module("app.main")
    service = Mock()
    connection = Mock()
    service.source.engine.connect.return_value.__enter__ = Mock(return_value=connection)
    service.source.engine.connect.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(module, "user_vectorization_service", service)
    monkeypatch.setattr(module.settings, "CDC_MONITORING_ENABLED", False)
    return module, service


def test_readiness_fails_on_source_outage(readiness):
    module, service = readiness
    service.source.engine.connect.side_effect = ConnectionError("secret URL must not be returned")
    response = module.readiness()
    body = json.loads(response.body)
    assert response.status_code == 503 and body["checks"]["mysql"] == "unavailable"
    assert "secret" not in response.body.decode()


def test_readiness_fails_on_mongo_outage(readiness):
    module, service = readiness
    service.db.command.side_effect = ConnectionError("mongo down")
    assert module.readiness().status_code == 503


def test_embedding_outage_does_not_disable_readthrough_serving(readiness, monkeypatch):
    module, _ = readiness
    monkeypatch.setattr(module.settings, "CDC_MONITORING_ENABLED", True)
    monkeypatch.setattr(module, "pipeline_status", Mock(return_value={"ready": False, "embedding_failed": 2}))
    response = module.readiness()
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["ready"] and not body["pipeline_ready"]
