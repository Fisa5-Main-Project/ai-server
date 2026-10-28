import importlib
import json
from unittest.mock import Mock

import mongomock
import pytest


@pytest.fixture
def worker(monkeypatch):
    module = importlib.import_module("app.pipelines.worker")
    service = Mock()
    service.db = mongomock.MongoClient().db
    monkeypatch.setattr(module, "service", service)
    monkeypatch.setattr(module, "heartbeat", Mock(return_value=Mock()))
    monkeypatch.setattr(module.settings, "CDC_DATABASE", "knowhow")
    consumer = Mock()
    message = Mock()
    message.error.return_value = None
    message.topic.return_value = "knowhow.knowhow.assets"
    message.partition.return_value = 0
    message.offset.return_value = 10
    message.value.return_value = json.dumps({"op": "u", "source": {"db": "knowhow", "table": "assets"},
                                             "before": {"user_id": 1}, "after": {"user_id": 1}}).encode()
    consumer.poll.side_effect = [message, KeyboardInterrupt()]
    monkeypatch.setattr("confluent_kafka.Consumer", Mock(return_value=consumer))
    return module, service, consumer, message


def test_offset_committed_only_after_durable_job(worker):
    module, service, consumer, message = worker

    def commit(**kwargs):
        assert service.db.user_refresh_jobs.find_one({"_id": 1}) is not None
        assert kwargs == {"message": message, "asynchronous": False}

    consumer.commit.side_effect = commit
    with pytest.raises(KeyboardInterrupt):
        module.consume()
    consumer.commit.assert_called_once()
    consumer.close.assert_called_once()


def test_queue_failure_does_not_commit_offset(worker, monkeypatch):
    module, service, consumer, _ = worker
    monkeypatch.setattr(module, "process_event", Mock(side_effect=ConnectionError("mongo unavailable")))
    with pytest.raises(ConnectionError):
        module.consume()
    consumer.commit.assert_not_called()
    consumer.close.assert_called_once()


def test_invalid_message_is_quarantined_before_commit(worker):
    module, service, consumer, message = worker
    message.value.return_value = b'{"op": "invalid"}'
    with pytest.raises(KeyboardInterrupt):
        module.consume()
    consumer.commit.assert_called_once()
    record = service.db.cdc_dead_letters.find_one()
    assert record["status"] == "failed" and record["offset"] == 10
    assert "payload" not in record


def test_commit_failure_leaves_job_for_replay(worker):
    module, service, consumer, _ = worker
    consumer.commit.side_effect = RuntimeError("broker unavailable")
    with pytest.raises(RuntimeError):
        module.consume()
    assert service.db.user_refresh_jobs.find_one({"_id": 1})


def test_quarantine_storage_failure_does_not_advance_offset(worker, monkeypatch):
    module, _, consumer, message = worker
    message.value.return_value = b'not valid json'
    quarantine = Mock()
    quarantine.save.side_effect = ConnectionError("mongo unavailable")
    monkeypatch.setattr(module, "CDCQuarantine", Mock(return_value=quarantine))
    with pytest.raises(ConnectionError):
        module.consume()
    consumer.commit.assert_not_called()
