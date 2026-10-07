"""Debezium changes invalidate personas; events never replace joined user state."""
from datetime import datetime, timezone, timedelta
from pymongo.write_concern import WriteConcern

TABLES = ("users", "user_info", "assets", "user_keyword", "keyword")


def affected_users(event, source, database):
    if event is None:
        return set()  # Compaction tombstone; preceding delete event carries the row.
    payload = event.get("payload", event)
    if payload is None:
        return set()
    if payload.get("op") not in {"c", "u", "d", "r"}:
        raise ValueError("Unsupported CDC operation")
    metadata = payload.get("source", {})
    if metadata.get("db") != database or metadata.get("table") not in TABLES:
        raise ValueError("Unexpected CDC source")
    rows = [row for row in (payload.get("before"), payload.get("after")) if row is not None]
    if not rows:
        raise ValueError("CDC row image missing")
    ids = set()
    for row in rows:
        if metadata["table"] == "keyword":
            ids.update(int(uid) for uid in source.users_for_keyword(row["keyword_id"]))
        else:
            ids.add(int(row["user_id"]))  # Handles deletion and changes of asset owner.
    return ids


class RefreshQueue:
    def __init__(self, collection):
        self.collection = collection.with_options(write_concern=WriteConcern(w="majority", j=True))

    def enqueue(self, user_id):
        now = datetime.now(timezone.utc)
        self.collection.update_one({"_id": int(user_id)}, {
            "$inc": {"generation": 1}, "$set": {"queued_at": now, "retry_at": now},
            "$setOnInsert": {"attempts": 0}}, upsert=True)

    def next_job(self):
        return self.collection.find_one({"retry_at": {"$lte": datetime.now(timezone.utc)}},
                                        sort=[("retry_at", 1)])

    def complete(self, job):
        self.collection.delete_one({"_id": job["_id"], "generation": job["generation"]})

    def fail(self, job):
        delay = min(60, 2 ** min(job.get("attempts", 0) + 1, 6))
        self.collection.update_one({"_id": job["_id"], "generation": job["generation"]}, {
            "$inc": {"attempts": 1},
            "$set": {"retry_at": datetime.now(timezone.utc) + timedelta(seconds=delay)}})


def process_event(event, source, queue, database):
    ids = affected_users(event, source, database)
    for user_id in sorted(ids):
        queue.enqueue(user_id)
    return len(ids)
