"""Local progress heartbeat and dependency/backlog diagnostics without payloads."""
import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen


class Heartbeat:
    def __init__(self, mode, collection=None, directory=None):
        self.mode, self.collection = mode, collection
        self.path = Path(directory or tempfile.gettempdir()) / f"user-worker-{mode}.json"
        self.last_write = 0

    def tick(self, state="healthy", error=None, force=False):
        if not force and time.monotonic() - self.last_write < 5:
            return
        record = {"mode": self.mode, "state": state, "last_seen": datetime.now(timezone.utc).isoformat(),
                  "error_type": type(error).__name__ if error else None}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record), encoding="utf-8")
        os.replace(temporary, self.path)
        self.last_write = time.monotonic()
        if self.collection is not None:
            try:
                self.collection.update_one({"_id": f"{self.mode}:{os.environ.get('HOSTNAME', 'local')}"},
                                           {"$set": record}, upsert=True)
            except Exception:
                # Local progress remains visible if the monitoring database is unavailable.
                pass


def worker_alive(mode, directory=None, max_age=120):
    path = Path(directory or tempfile.gettempdir()) / f"user-worker-{mode}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["last_seen"])).total_seconds()
        return 0 <= age <= max_age and record["state"] in {"healthy", "backoff"}
    except (OSError, ValueError, KeyError, TypeError):
        return False


def kafka_status(bootstrap, group, topics):
    from confluent_kafka import Consumer, TopicPartition
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": group,
                         "enable.auto.commit": False, "enable.auto.offset.store": False,
                         "auto.offset.reset": "error"})
    try:
        metadata = consumer.list_topics(timeout=5)
        partitions = []
        for topic in topics:
            entry = metadata.topics.get(topic)
            if entry is None or entry.error is not None:
                return {"ready": False, "state": "missing_topic", "lag": None}
            partitions.extend(TopicPartition(topic, partition) for partition in entry.partitions)
        offsets = consumer.committed(partitions, timeout=5)
        lag, gap = 0, False
        for partition in offsets:
            if partition.error is not None:
                return {"ready": False, "state": "offset_unavailable", "lag": None}
            low, high = consumer.get_watermark_offsets(partition, timeout=5, cached=False)
            if partition.offset < 0:
                lag += high - low
            else:
                gap |= not low <= partition.offset <= high
                lag += max(0, high - partition.offset)
        return {"ready": not gap, "state": "offset_gap" if gap else "healthy", "lag": lag}
    except Exception:
        return {"ready": False, "state": "unavailable", "lag": None}
    finally:
        consumer.close()  # No subscription/assignment/commit: never join or move the group.


def pipeline_status(db, connect_url=None, max_age=120, kafka=None):
    now = datetime.now(timezone.utc)
    result = {"ready": True, "workers": {}, "refresh_pending": 0, "refresh_failed": 0,
              "embedding_pending": 0, "embedding_failed": 0, "cdc_quarantined": 0}
    result["refresh_pending"] = db.user_refresh_jobs.count_documents({"status": {"$ne": "failed"}})
    result["refresh_failed"] = db.user_refresh_jobs.count_documents({"status": "failed"})
    result["embedding_pending"] = db.user_vectors.count_documents({"embedding_status": "pending"})
    result["embedding_failed"] = db.user_vectors.count_documents({"embedding_status": "failed"})
    result["cdc_quarantined"] = db.cdc_dead_letters.count_documents({"status": "failed"})
    oldest = db.user_refresh_jobs.find_one({"status": {"$ne": "failed"}}, sort=[("queued_at", 1)])
    queued = oldest.get("queued_at") if oldest else None
    if queued and queued.tzinfo is None:
        queued = queued.replace(tzinfo=timezone.utc)
    result["oldest_refresh_seconds"] = max(0, (now - queued).total_seconds()) if queued else 0
    for mode in ("consume", "refresh", "embed"):
        states = list(db.worker_states.find({"mode": mode}).sort("last_seen", -1).limit(1))
        record = states[0] if states else {}
        try:
            seen = datetime.fromisoformat(record["last_seen"])
            healthy = record.get("state") == "healthy" and timedelta(0) <= now - seen <= timedelta(seconds=max_age)
        except (KeyError, ValueError, TypeError):
            healthy = False
        result["workers"][mode] = "healthy" if healthy else "unavailable"
        result["ready"] &= healthy
    if result["refresh_failed"] or result["embedding_failed"] or result["cdc_quarantined"]:
        result["ready"] = False
    if result["oldest_refresh_seconds"] > max_age:
        result["ready"] = False
    if connect_url:
        try:
            with urlopen(connect_url.rstrip("/") + "/connectors/user-state-cdc/status", timeout=3) as response:
                status = json.load(response)
            running = status.get("connector", {}).get("state") == "RUNNING"
            tasks = status.get("tasks", [])
            running &= bool(tasks) and all(task.get("state") == "RUNNING" for task in tasks)
            result["connector"] = "RUNNING" if running else "unavailable"
            result["ready"] &= running
        except Exception:
            result["connector"] = "unavailable"
            result["ready"] = False
    if kafka:
        result["kafka"] = kafka_status(*kafka)
        result["ready"] &= result["kafka"]["ready"]
    return result
