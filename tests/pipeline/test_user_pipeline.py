from copy import deepcopy
from datetime import date
from unittest.mock import Mock

import mongomock
import pytest

from app.pipelines.cdc import RefreshQueue, affected_users, process_event
from app.pipelines.persona import build_persona
from app.pipelines.user_projection import UserProjection
from app.pipelines.user_source import UserNotFound


@pytest.fixture
def data():
    return {"user": {"birth": "1990-01-01", "gender": "M", "asset_total": 0,
                     "investment_tendancy": "안정추구형", "user_mydata_registration": False},
            "user_info": {"annual_income": 0, "retirement_status": False,
                          "mydata_status": "CONNECTED", "goal_amount": 0},
            "assets": [{"type": "CURRENT", "balance": "100000.01"}, {"type": "LOAN", "balance": "20000.00"}],
            "keywords": [{"name": "여행"}, {"name": "안정"}]}


@pytest.fixture
def pipeline(data):
    source = Mock()
    source.read.side_effect = lambda _: deepcopy(data)
    collection = mongomock.MongoClient().db.users
    embed = Mock(return_value=[0.1, 0.2])
    return UserProjection(source, collection, embed, "test-model")


def event(table, op="u", before=None, after=None):
    return {"op": op, "source": {"db": "knowhow", "table": table}, "before": before, "after": after}


def test_exact_asset_and_zero_state_values_are_preserved(data):
    text = build_persona(data, date(2026, 10, 7))
    assert "만 36세" in text
    assert "100000.01원" in text and "20000.00원" in text
    assert "연 소득: 0원" in text and "목표 자산: 0원" in text
    assert "은퇴 상태: 은퇴 전" in text and "마이데이터 등록: 미등록" in text


def test_reordered_assets_keywords_do_not_change_persona(data):
    before = build_persona(data)
    data["assets"].reverse()
    data["keywords"].reverse()
    assert build_persona(data) == before


def test_persona_refresh_does_not_wait_for_embedding(pipeline):
    result = pipeline.refresh(1)
    assert "100000.01원" in result["persona_text"]
    pipeline.embedder.assert_not_called()
    assert pipeline.collection.find_one()["embedding_status"] == "pending"


def test_duplicate_refresh_skips_embedding_and_preserves_created_at(pipeline):
    pipeline.refresh(1)
    pipeline.embed_pending(1)
    created = pipeline.collection.find_one()["created_at"]
    pipeline.refresh(1)
    assert not pipeline.embed_pending(1)
    assert pipeline.collection.count_documents({}) == 1
    assert pipeline.collection.find_one()["created_at"] == created
    pipeline.embedder.assert_called_once()


def test_small_balance_change_invalidates_embedding(pipeline, data):
    pipeline.refresh(1)
    pipeline.embed_pending(1)
    assert pipeline.current_embedding(1) == [0.1, 0.2]
    data["assets"][0]["balance"] = "100000.02"
    result = pipeline.refresh(1)
    assert "100000.02원" in result["persona_text"]
    assert pipeline.current_embedding(1) is None
    assert pipeline.embed_pending(1)


def test_state_change_used_without_embedding(pipeline, data):
    pipeline.refresh(1)
    data["user_info"]["retirement_status"] = True
    data["user"]["investment_tendancy"] = "적극투자형"
    text = pipeline.refresh(1)["persona_text"]
    assert "은퇴 상태: 은퇴." in text and "적극투자형" in text
    pipeline.embedder.assert_not_called()


def test_embedding_failure_keeps_latest_persona_and_retries(pipeline):
    pipeline.refresh(1)
    pipeline.embedder.side_effect = RuntimeError("provider unavailable")
    with pytest.raises(RuntimeError):
        pipeline.embed_pending(1)
    assert pipeline.collection.find_one()["embedding_status"] == "pending"
    assert pipeline.collection.find_one()["persona_text"]
    pipeline.embedder.side_effect = None
    assert not pipeline.embed_pending(1)  # Backoff must elapse before retry.
    pipeline.collection.update_one({"_id": "user_1"}, {"$unset": {"embedding_retry_at": ""}})
    assert pipeline.embed_pending(1)


def test_late_embedding_cannot_overwrite_new_persona(pipeline, data):
    pipeline.refresh(1)

    def slow_embed(_):
        data["assets"][0]["balance"] = "999999.99"
        pipeline.refresh(1)
        return [9, 9]

    pipeline.embedder.side_effect = slow_embed
    assert not pipeline.embed_pending(1)
    assert pipeline.current_embedding(1) is None
    assert "999999.99원" in pipeline.collection.find_one()["persona_text"]


def test_source_deletion_removes_persona_and_embedding(pipeline):
    pipeline.refresh(1)
    pipeline.embed_pending(1)
    pipeline.source.read.side_effect = UserNotFound("deleted")
    with pytest.raises(UserNotFound):
        pipeline.refresh(1)
    doc = pipeline.collection.find_one()
    assert doc["deleted"] and "persona_text" not in doc and "embedding" not in doc
    assert pipeline.current_embedding(1) is None


def test_deletion_during_embedding_cannot_resurrect_user(pipeline):
    pipeline.refresh(1)

    def deleting_embed(_):
        pipeline.source.read.side_effect = UserNotFound("deleted")
        with pytest.raises(UserNotFound):
            pipeline.refresh(1)
        return [9, 9]

    pipeline.embedder.side_effect = deleting_embed
    assert not pipeline.embed_pending(1)
    assert pipeline.collection.find_one()["deleted"]


def test_older_read_is_fenced_by_concurrent_refresh(pipeline, data):
    old_data = deepcopy(data)
    entered = False

    def racing_read(_):
        nonlocal entered
        if not entered:
            entered = True
            data["assets"][0]["balance"] = "777777.77"
            pipeline.refresh(1)
            return old_data
        return deepcopy(data)

    pipeline.source.read.side_effect = racing_read
    assert "777777.77원" in pipeline.refresh(1)["persona_text"]
    assert "777777.77원" in pipeline.collection.find_one()["persona_text"]


def test_source_outage_does_not_serve_stale_persona(pipeline):
    pipeline.refresh(1)
    pipeline.source.read.side_effect = ConnectionError("source down")
    with pytest.raises(ConnectionError):
        pipeline.refresh(1)


@pytest.mark.parametrize("table", ["users", "user_info", "assets", "user_keyword"])
def test_delete_routes_using_before_user_id(table):
    assert affected_users(event(table, "d", before={"user_id": 4}), Mock(), "knowhow") == {4}


def test_asset_owner_change_refreshes_both_users():
    assert affected_users(event("assets", before={"user_id": 1}, after={"user_id": 2}), Mock(), "knowhow") == {1, 2}


def test_keyword_rename_fans_out_to_linked_users():
    source = Mock()
    source.users_for_keyword.return_value = [2, 3]
    assert affected_users(event("keyword", after={"keyword_id": 7}), source, "knowhow") == {2, 3}


def test_schemaful_snapshot_and_tombstone():
    assert affected_users({"payload": event("users", "r", after={"user_id": 1})}, Mock(), "knowhow") == {1}
    assert affected_users(None, Mock(), "knowhow") == set()


def test_malformed_event_is_not_silently_discarded():
    with pytest.raises(ValueError):
        affected_users(event("assets"), Mock(), "knowhow")


def test_new_event_during_processing_remains_durable():
    queue = RefreshQueue(mongomock.MongoClient().db.jobs)
    queue.enqueue(1)
    old_job = queue.next_job()
    queue.enqueue(1)
    queue.complete(old_job)
    assert queue.next_job()["generation"] == 2


def test_enqueue_failure_propagates_before_offset_commit():
    queue = Mock()
    queue.enqueue.side_effect = ConnectionError("mongo unavailable")
    with pytest.raises(ConnectionError):
        process_event(event("users", after={"user_id": 1}), Mock(), queue, "knowhow")


def test_replayed_events_produce_one_job_and_latest_state(pipeline, data):
    queue = RefreshQueue(mongomock.MongoClient().db.jobs)
    change = event("assets", after={"user_id": 1, "balance": "old event"})
    process_event(change, pipeline.source, queue, "knowhow")
    data["assets"][0]["balance"] = "123456.78"
    process_event(change, pipeline.source, queue, "knowhow")
    job = queue.next_job()
    assert queue.collection.count_documents({}) == 1
    assert "123456.78원" in pipeline.refresh(job["_id"])["persona_text"]
    queue.complete(job)
    assert queue.next_job() is None


def test_model_change_requires_reembedding(pipeline):
    pipeline.refresh(1)
    pipeline.embed_pending(1)
    pipeline.model = "new-model"
    assert pipeline.current_embedding(1) is None
    pipeline.refresh(1)
    assert pipeline.embed_pending(1)


def test_job_retry_does_not_hide_new_generation():
    queue = RefreshQueue(mongomock.MongoClient().db.jobs)
    queue.enqueue(1)
    old = queue.next_job()
    queue.enqueue(1)
    queue.fail(old)
    assert queue.next_job()["generation"] == 2


def test_keyword_delete_fanout_survives_mysql_cascade():
    from app.pipelines.user_source import MySQLUserSource
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=Mock())
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    conn = engine.connect.return_value.__enter__.return_value
    conn.execute.return_value = []  # source links already removed by FK cascade
    projections = mongomock.MongoClient().db.users
    projections.insert_one({"user_id": 42, "keyword_ids": [7], "deleted": False})
    source = MySQLUserSource(engine, projections)
    assert affected_users(event("keyword", "d", before={"keyword_id": 7}), source, "knowhow") == {42}
