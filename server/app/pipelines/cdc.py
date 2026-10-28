"""Debezium changes invalidate personas; events never replace joined user state."""
from datetime import datetime, timezone, timedelta
from pymongo.write_concern import WriteConcern
from pymongo import ReturnDocument
from uuid import uuid4
from app.pipelines.resilience import backoff

TABLES = ("users", "user_info", "assets", "user_keyword", "keyword")


class InvalidCDCEvent(ValueError):
    pass


def identifier(row, name):
    try:
        value = row[name]
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("Invalid ID type")
        result = int(value)
        if not 0 < result <= 9223372036854775807:
            raise ValueError("Invalid ID value")
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidCDCEvent("Invalid CDC identifier") from exc


def affected_users(event, source, database):
    if event is None:
        return set()  # Compaction tombstone; preceding delete event carries the row.
    if not isinstance(event, dict):
        raise InvalidCDCEvent("Invalid event envelope")
    payload = event.get("payload", event)
    if payload is None:
        return set()
    if not isinstance(payload, dict):
        raise InvalidCDCEvent("Invalid event payload")
    if not isinstance(payload.get("op"), str) or payload.get("op") not in {"c", "u", "d", "r"}:
        raise InvalidCDCEvent("Unsupported CDC operation")
    metadata = payload.get("source", {})
    if not isinstance(metadata, dict) or metadata.get("db") != database or metadata.get("table") not in TABLES:
        raise InvalidCDCEvent("Unexpected CDC source")
    rows = [row for row in (payload.get("before"), payload.get("after")) if row is not None]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise InvalidCDCEvent("CDC row image missing")
    ids = set()
    for row in rows:
        if metadata["table"] == "keyword":
            keyword_id = identifier(row, "keyword_id")
            ids.update(int(uid) for uid in source.users_for_keyword(keyword_id))
        else:
            ids.add(identifier(row, "user_id"))
    return ids


class RefreshQueue:
    def __init__(self, collection, max_attempts=5, lease_seconds=120):
        self.collection = collection.with_options(write_concern=WriteConcern(w="majority", j=True))
        self.max_attempts, self.lease_seconds = max_attempts, lease_seconds

    def enqueue(self, user_id):
        now = datetime.now(timezone.utc)
        self.collection.update_one({"_id": int(user_id)}, {
            "$inc": {"generation": 1},
            "$set": {"queued_at": now, "retry_at": now, "attempts": 0, "status": "ready"},
            "$unset": {"lease_token": "", "lease_until": "", "error_type": ""}}, upsert=True)

    def next_job(self):
        now = datetime.now(timezone.utc)
        return self.collection.find_one_and_update(
            {"retry_at": {"$lte": now}, "status": {"$ne": "failed"},
             "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": now}}]},
            {"$set": {"lease_token": uuid4().hex, "lease_until": now + timedelta(seconds=self.lease_seconds)}},
            sort=[("retry_at", 1)], return_document=ReturnDocument.AFTER)

    def match(self, job):
        return {"_id": job["_id"], "generation": job["generation"], "lease_token": job["lease_token"]}

    def complete(self, job):
        self.collection.delete_one(self.match(job))

    def fail(self, job, error=None):
        attempts = job.get("attempts", 0) + 1
        self.collection.update_one(self.match(job), {
            "$set": {"attempts": attempts, "status": "failed" if attempts >= self.max_attempts else "ready",
                     "error_type": type(error).__name__ if error else "UnknownError",
                     "retry_at": datetime.now(timezone.utc) + timedelta(seconds=backoff(attempts))},
            "$unset": {"lease_token": "", "lease_until": ""}})

    def retry(self, user_id):
        job = self.collection.find_one({"_id": int(user_id), "status": "failed"})
        if job is None:
            return False
        result = self.collection.update_one({"_id": job["_id"], "generation": job["generation"], "status": "failed"}, {
            "$inc": {"generation": 1}, "$set": {"status": "ready", "attempts": 0, "retry_at": datetime.now(timezone.utc)},
            "$unset": {"error_type": "", "lease_token": "", "lease_until": ""}})
        return bool(result.matched_count)


def process_event(event, source, queue, database):
    ids = affected_users(event, source, database)
    for user_id in sorted(ids):
        queue.enqueue(user_id)
    return len(ids)
