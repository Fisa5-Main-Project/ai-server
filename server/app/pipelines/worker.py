"""Separate CDC ingestion, persona refresh, embeddings and repair processes."""
import argparse
import json
import logging
import time

from app.core.config import settings
from app.pipelines.cdc import TABLES, RefreshQueue, process_event
from app.pipelines.user_source import UserNotFound
from app.services.user_vectorization_service import user_vectorization_service as service

log = logging.getLogger(__name__)


def consume():
    from confluent_kafka import Consumer
    queue = RefreshQueue(service.db["user_refresh_jobs"])
    consumer = Consumer({"bootstrap.servers": settings.CDC_KAFKA_BOOTSTRAP_SERVERS,
                         "group.id": settings.CDC_GROUP_ID, "enable.auto.commit": False,
                         "enable.auto.offset.store": False, "auto.offset.reset": "earliest"})
    consumer.subscribe([f"{settings.CDC_TOPIC_PREFIX}.{settings.CDC_DATABASE}.{t}" for t in TABLES])
    try:
        while True:
            message = consumer.poll(1)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(str(message.error()))
            event = json.loads(message.value()) if message.value() is not None else None
            # Failure stops this process without committing. Restart safely replays invalidations.
            count = process_event(event, service.source, queue, settings.CDC_DATABASE)
            consumer.commit(message=message, asynchronous=False)
            log.info("cdc_enqueued topic=%s partition=%s offset=%s users=%s",
                     message.topic(), message.partition(), message.offset(), count)
    finally:
        consumer.close()


def refresh():
    queue = RefreshQueue(service.db["user_refresh_jobs"])
    service.db["user_refresh_jobs"].create_index("retry_at")
    while True:
        job = queue.next_job()
        if job is None:
            time.sleep(0.5)
            continue
        try:
            service.refresh_user(job["_id"])
        except UserNotFound:
            queue.complete(job)  # refresh already persisted a deletion tombstone.
        except Exception as exc:
            log.error("refresh_failed user=%s error=%s", job["_id"], type(exc).__name__)
            queue.fail(job)
        else:
            queue.complete(job)
            log.info("persona_refreshed user=%s", job["_id"])


def embed():
    from datetime import datetime, timezone, timedelta
    collection = service.user_vectors_collection
    collection.create_index([("embedding_status", 1), ("embedding_retry_at", 1)])
    while True:
        doc = collection.find_one({"embedding_status": "pending", "deleted": False,
                                   "$or": [{"embedding_retry_at": {"$exists": False}},
                                           {"embedding_retry_at": {"$lte": datetime.now(timezone.utc)}}]})
        if doc is None:
            time.sleep(1)
            continue
        try:
            service.projection.embed_pending(doc["user_id"])
        except Exception as exc:
            log.error("embedding_failed user=%s error=%s", doc["user_id"], type(exc).__name__)
            collection.update_one({"_id": doc["_id"], "persona_hash": doc["persona_hash"]}, {
                "$set": {"embedding_retry_at": datetime.now(timezone.utc) + timedelta(seconds=30)}})


def reconcile():
    queue = RefreshQueue(service.db["user_refresh_jobs"])
    count = 0
    for user_id in service.source.user_ids():
        queue.enqueue(user_id)
        count += 1
    # Also repair missed source deletions.
    for doc in service.user_vectors_collection.find({"deleted": {"$ne": True}}, {"user_id": 1}):
        if "user_id" in doc:
            queue.enqueue(doc["user_id"])
    log.info("reconciliation_enqueued source_users=%s", count)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["consume", "refresh", "embed", "reconcile"])
    args = parser.parse_args()
    {"consume": consume, "refresh": refresh, "embed": embed, "reconcile": reconcile}[args.mode]()
