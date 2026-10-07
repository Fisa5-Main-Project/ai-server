import importlib
from unittest.mock import Mock

import mongomock
import pytest
from confluent_kafka import TopicPartition


@pytest.fixture
def worker(monkeypatch):
    module = importlib.import_module("app.pipelines.worker")
    service = Mock()
    service.db = mongomock.MongoClient().db
    service.user_vectors_collection = service.db.user_vectors
    monkeypatch.setattr(module, "service", service)
    return module, service


def test_saved_offset_outside_retention_stops_without_reset(worker):
    module, _ = worker
    consumer = Mock()
    consumer.committed.return_value = [TopicPartition("users", 0, 10)]
    consumer.get_watermark_offsets.return_value = (20, 100)
    with pytest.raises(module.OffsetGap):
        module.assign_safely(consumer, [TopicPartition("users", 0)])
    consumer.assign.assert_not_called()


def test_new_group_explicitly_starts_at_oldest_retained_offset(worker):
    module, _ = worker
    consumer = Mock()
    consumer.committed.return_value = [TopicPartition("users", 0, -1001)]
    consumer.get_watermark_offsets.return_value = (20, 100)
    module.assign_safely(consumer, [TopicPartition("users", 0)])
    assert consumer.assign.call_args.args[0][0].offset == 20


def test_refresh_failure_is_retained_and_retried(worker):
    module, service = worker
    jobs = module.queue()
    jobs.enqueue(1)
    service.refresh_user.side_effect = ConnectionError("mysql down")
    assert module.refresh_once(jobs)
    job = jobs.collection.find_one()
    assert job["attempts"] == 1 and job["status"] == "ready"
    assert "lease_token" not in job


def test_manual_cdc_resubmission_enqueues_before_resolving(worker):
    module, service = worker
    service.db.cdc_dead_letters.insert_one({"_id": "users:0:10", "status": "failed"})
    module.retry_cdc("users:0:10", [1, 2])
    assert service.db.user_refresh_jobs.count_documents({}) == 2
    assert service.db.cdc_dead_letters.find_one()["status"] == "resubmitted"


def test_failed_resubmission_preserves_quarantine(worker, monkeypatch):
    module, service = worker
    service.db.cdc_dead_letters.insert_one({"_id": "users:0:10", "status": "failed"})
    jobs = Mock()
    jobs.enqueue.side_effect = ConnectionError("mongo down")
    monkeypatch.setattr(module, "queue", Mock(return_value=jobs))
    with pytest.raises(ConnectionError):
        module.retry_cdc("users:0:10", [1])
    assert service.db.cdc_dead_letters.find_one()["status"] == "failed"


def test_kafka_diagnostics_report_lag_without_joining_or_committing(monkeypatch):
    from types import SimpleNamespace
    from app.pipelines.monitoring import kafka_status
    consumer = Mock()
    consumer.list_topics.return_value = SimpleNamespace(topics={"users": SimpleNamespace(error=None, partitions={0: None})})
    consumer.committed.return_value = [TopicPartition("users", 0, 40)]
    consumer.get_watermark_offsets.return_value = (20, 100)
    monkeypatch.setattr("confluent_kafka.Consumer", Mock(return_value=consumer))
    assert kafka_status("kafka:9092", "group", ["users"]) == {"ready": True, "state": "healthy", "lag": 60}
    consumer.subscribe.assert_not_called()
    consumer.assign.assert_not_called()
    consumer.commit.assert_not_called()
    consumer.close.assert_called_once()


def test_kafka_diagnostics_detect_retention_gap(monkeypatch):
    from types import SimpleNamespace
    from app.pipelines.monitoring import kafka_status
    consumer = Mock()
    consumer.list_topics.return_value = SimpleNamespace(topics={"users": SimpleNamespace(error=None, partitions={0: None})})
    consumer.committed.return_value = [TopicPartition("users", 0, 10)]
    consumer.get_watermark_offsets.return_value = (20, 100)
    monkeypatch.setattr("confluent_kafka.Consumer", Mock(return_value=consumer))
    state = kafka_status("kafka:9092", "group", ["users"])
    assert not state["ready"] and state["state"] == "offset_gap"


def test_connector_restart_uses_json_and_only_failed_instances(worker, monkeypatch):
    module, _ = worker
    response = Mock(status=202)
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    open_url = Mock(return_value=context)
    monkeypatch.setattr("urllib.request.urlopen", open_url)
    module.restart_connector()
    request = open_url.call_args.args[0]
    assert request.get_header("Content-type") == "application/json"
    assert request.method == "POST" and "onlyFailed=true" in request.full_url


def test_cdc_without_recoverable_identifier_can_be_reconciled(worker, monkeypatch):
    module, service = worker
    service.db.cdc_dead_letters.insert_one({"_id": "users:0:10", "status": "failed"})
    repair = Mock()
    monkeypatch.setattr(module, "reconcile", repair)
    module.retry_cdc("users:0:10", reconcile_all=True)
    repair.assert_called_once()
    assert service.db.cdc_dead_letters.find_one()["status"] == "resubmitted"
