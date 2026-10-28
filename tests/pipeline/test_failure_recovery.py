from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import mongomock
import pytest

from app.pipelines.cdc import RefreshQueue, affected_users, InvalidCDCEvent
from app.pipelines.monitoring import Heartbeat, worker_alive, pipeline_status
from app.pipelines.resilience import CDCQuarantine, CircuitBreaker
from app.pipelines.user_projection import UserProjection


def collection():
    return mongomock.MongoClient().db.jobs


def expire(jobs):
    jobs.collection.update_many({}, {"$set": {"retry_at": datetime.now(timezone.utc) - timedelta(seconds=1),
                                              "lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})


def test_only_one_worker_can_claim_same_generation():
    jobs = RefreshQueue(collection())
    jobs.enqueue(1)
    assert jobs.next_job() is not None
    assert jobs.next_job() is None


def test_worker_killed_without_ack_releases_work_after_lease_expiry():
    jobs = RefreshQueue(collection())
    jobs.enqueue(1)
    killed_job = jobs.next_job()
    expire(jobs)
    recovered = jobs.next_job()
    assert recovered["generation"] == killed_job["generation"]
    assert recovered["lease_token"] != killed_job["lease_token"]
    jobs.complete(killed_job)
    assert jobs.collection.find_one() is not None
    jobs.complete(recovered)
    assert jobs.collection.find_one() is None


def test_retry_limit_quarantines_and_manual_retry_restores_job():
    jobs = RefreshQueue(collection(), max_attempts=2)
    jobs.enqueue(1)
    first = jobs.next_job()
    jobs.fail(first, ConnectionError("secret connection URL"))
    assert jobs.next_job() is None
    expire(jobs)
    jobs.fail(jobs.next_job(), ConnectionError("secret connection URL"))
    failed = jobs.collection.find_one()
    assert failed["status"] == "failed" and failed["attempts"] == 2
    assert failed["error_type"] == "ConnectionError" and "secret" not in str(failed)
    assert jobs.next_job() is None
    assert jobs.retry(1)
    recovered = jobs.next_job()
    assert recovered["attempts"] == 0 and recovered["generation"] == 2


def test_old_worker_cannot_fail_new_lease():
    jobs = RefreshQueue(collection())
    jobs.enqueue(1)
    old = jobs.next_job()
    expire(jobs)
    current = jobs.next_job()
    jobs.fail(old, RuntimeError())
    assert jobs.collection.find_one()["lease_token"] == current["lease_token"]
    assert jobs.collection.find_one()["attempts"] == 0


def test_other_users_continue_when_one_user_is_quarantined():
    jobs = RefreshQueue(collection(), max_attempts=1)
    jobs.enqueue(1)
    jobs.fail(jobs.next_job(), ValueError())
    jobs.enqueue(2)
    assert jobs.next_job()["_id"] == 2


def projection():
    source = Mock()
    source.read.return_value = {"user": {"birth": "1990-01-01", "gender": "M"}, "assets": []}
    return UserProjection(source, collection(), Mock(return_value=[1, 2]), "model", max_attempts=2)


def test_embedding_failure_limit_does_not_reset_on_readthrough():
    pipeline = projection()
    pipeline.refresh(1)
    pipeline.embedder.side_effect = ConnectionError("provider unavailable")
    for _ in range(2):
        pipeline.collection.update_many({}, {"$unset": {"embedding_retry_at": ""}})
        with pytest.raises(ConnectionError):
            pipeline.embed_pending(1)
    pipeline.refresh(1)
    assert pipeline.collection.find_one()["embedding_status"] == "failed"
    assert pipeline.collection.find_one()["persona_text"]
    assert pipeline.retry_embedding(1)
    pipeline.embedder.side_effect = None
    assert pipeline.embed_pending(1)


def test_changed_persona_replaces_failed_embedding_work():
    pipeline = projection()
    pipeline.refresh(1)
    pipeline.collection.update_many({}, {"$set": {"embedding_status": "failed", "embedding_attempts": 2}})
    pipeline.source.read.return_value["user"]["investment_tendancy"] = "적극투자형"
    pipeline.refresh(1)
    doc = pipeline.collection.find_one()
    assert doc["embedding_status"] == "pending" and doc["embedding_attempts"] == 0


def test_embedding_claim_blocks_duplicate_external_api_calls():
    pipeline = projection()
    pipeline.refresh(1)

    def nested(_):
        assert not pipeline.embed_pending(1)
        return [1, 2]

    pipeline.embedder.side_effect = nested
    assert pipeline.embed_pending(1)
    pipeline.embedder.assert_called_once()


def test_abandoned_embedding_lease_is_recoverable():
    pipeline = projection()
    pipeline.refresh(1)
    pipeline.collection.update_many({}, {"$set": {"embedding_lease_token": "killed",
        "embedding_lease_until": datetime.now(timezone.utc) + timedelta(minutes=1)}})
    assert not pipeline.embed_pending(1)
    pipeline.collection.update_many({}, {"$set": {"embedding_lease_until": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert pipeline.embed_pending(1)


def test_quarantine_does_not_persist_raw_payload_and_is_idempotent():
    message = Mock()
    message.topic.return_value, message.partition.return_value, message.offset.return_value = "users", 0, 10
    message.value.return_value = b'{"password":"never store this"}'
    quarantine = CDCQuarantine(collection())
    quarantine.save(message, ValueError("sensitive"))
    quarantine.save(message, ValueError("sensitive"))
    assert quarantine.collection.count_documents({}) == 1
    assert "never store" not in str(quarantine.collection.find_one())
    assert "sensitive" not in str(quarantine.collection.find_one())


@pytest.mark.parametrize("payload", [[], 4, {"payload": []}, {"op": []}, {"op": {}}, {"op": "u", "source": []},
    {"op": "u", "source": {"db": "knowhow", "table": "users"}, "after": {"user_id": 9223372036854775808}},
    {"op": "u", "source": {"db": "knowhow", "table": "users"}, "after": {"user_id": True}}])
def test_invalid_event_shapes_are_classified_as_poison_input(payload):
    with pytest.raises(InvalidCDCEvent):
        affected_users(payload, Mock(), "knowhow")


def test_circuit_breaker_pauses_calls_then_recovers():
    clock = Mock(return_value=0)
    breaker = CircuitBreaker(threshold=2, cooldown=30, clock=clock)
    breaker.failure()
    assert breaker.available()
    breaker.failure()
    assert not breaker.available()
    clock.return_value = 31
    assert breaker.available()
    breaker.success()
    assert breaker.failures == 0


def test_heartbeat_detects_stopped_worker_without_database(tmp_path):
    heartbeat = Heartbeat("refresh", directory=tmp_path)
    heartbeat.tick(force=True)
    assert worker_alive("refresh", tmp_path)
    heartbeat.tick("stopped", force=True)
    assert not worker_alive("refresh", tmp_path)


def test_stale_heartbeat_is_unhealthy(tmp_path):
    import json
    record = {"state": "healthy", "last_seen": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()}
    (tmp_path / "user-worker-refresh.json").write_text(json.dumps(record))
    assert not worker_alive("refresh", tmp_path)


def test_status_reports_failed_jobs_without_financial_content():
    db = mongomock.MongoClient().db
    for mode in ("consume", "refresh", "embed"):
        db.worker_states.insert_one({"mode": mode, "state": "healthy", "last_seen": datetime.now(timezone.utc).isoformat()})
    assert pipeline_status(db)["ready"]
    db.user_refresh_jobs.insert_one({"status": "failed", "secret": "never expose"})
    state = pipeline_status(db)
    assert not state["ready"] and state["refresh_failed"] == 1
    assert "never expose" not in str(state)
