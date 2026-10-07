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
    monkeypatch.setattr(module.settings, "CDC_DATABASE", "knowhow")
    consumer = Mock()
    message = Mock()
    message.error.return_value = None
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


def test_invalid_message_blocks_commit(worker):
    module, _, consumer, message = worker
    message.value.return_value = b'{"op": "invalid"}'
    with pytest.raises(ValueError):
        module.consume()
    consumer.commit.assert_not_called()


def test_commit_failure_leaves_job_for_replay(worker):
    module, service, consumer, _ = worker
    consumer.commit.side_effect = RuntimeError("broker unavailable")
    with pytest.raises(RuntimeError):
        module.consume()
    assert service.db.user_refresh_jobs.find_one({"_id": 1})
