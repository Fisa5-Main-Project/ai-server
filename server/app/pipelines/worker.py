"""Workers and operator commands for recoverable user-state ingestion."""
import argparse
import json
import logging
import signal
import threading
import time

from app.core.config import settings
from app.pipelines.cdc import TABLES, RefreshQueue, process_event, InvalidCDCEvent
from app.pipelines.monitoring import Heartbeat, pipeline_status, worker_alive
from app.pipelines.resilience import CDCQuarantine, CircuitBreaker
from app.pipelines.user_source import UserNotFound
from app.services.user_vectorization_service import user_vectorization_service as service

log = logging.getLogger(__name__)
stop = threading.Event()


class OffsetGap(RuntimeError):
    pass


def queue():
    return RefreshQueue(service.db["user_refresh_jobs"], settings.CDC_MAX_ATTEMPTS, settings.CDC_LEASE_SECONDS)


def heartbeat(mode):
    return Heartbeat(mode, service.db["worker_states"])


def assign_safely(consumer, partitions):
    committed = consumer.committed(partitions, timeout=5)
    for partition in committed:
        if partition.error is not None:
            raise OffsetGap("Cannot determine committed partition offset")
        low, high = consumer.get_watermark_offsets(partition, timeout=5, cached=False)
        if partition.offset >= 0 and not low <= partition.offset <= high:
            raise OffsetGap("Retained Kafka history no longer covers the committed offset")
        if partition.offset < 0:
            partition.offset = low  # Explicit first assignment, not silent recovery of lost offsets.
    consumer.assign(committed)


def consume():
    from confluent_kafka import Consumer
    jobs = queue()
    quarantine = CDCQuarantine(service.db["cdc_dead_letters"])
    health = heartbeat("consume")
    consumer = Consumer({"bootstrap.servers": settings.CDC_KAFKA_BOOTSTRAP_SERVERS,
                         "group.id": settings.CDC_GROUP_ID, "enable.auto.commit": False,
                         "enable.auto.offset.store": False, "auto.offset.reset": "error",
                         "session.timeout.ms": 10000, "max.poll.interval.ms": 300000})
    consumer.subscribe([f"{settings.CDC_TOPIC_PREFIX}.{settings.CDC_DATABASE}.{t}" for t in TABLES],
                       on_assign=assign_safely)
    try:
        while not stop.is_set():
            health.tick()
            message = consumer.poll(1)
            if message is None:
                continue
            if message.error():
                raise RuntimeError("Kafka delivery error; inspect broker/group status")
            try:
                event = json.loads(message.value()) if message.value() is not None else None
                count = process_event(event, service.source, jobs, settings.CDC_DATABASE)
            except (InvalidCDCEvent, json.JSONDecodeError, UnicodeDecodeError) as exc:
                # Only invalid input is quarantined. DB/network failures never advance offsets.
                key = quarantine.save(message, exc)
                log.error("cdc_quarantined id=%s error=%s", key, type(exc).__name__)
                count = 0
            consumer.commit(message=message, asynchronous=False)
            log.info("cdc_processed topic=%s partition=%s offset=%s users=%s",
                     message.topic(), message.partition(), message.offset(), count)
    except Exception as exc:
        health.tick("failed", exc, force=True)
        raise
    finally:
        consumer.close()


def refresh_once(jobs):
    job = jobs.next_job()
    if job is None:
        return False
    try:
        service.refresh_user(job["_id"])
    except UserNotFound:
        jobs.complete(job)
    except Exception as exc:
        log.error("refresh_failed user=%s error=%s", job["_id"], type(exc).__name__)
        jobs.fail(job, exc)
    else:
        jobs.complete(job)
        log.info("persona_refreshed user=%s", job["_id"])
    return True


def refresh():
    jobs = queue()
    health = heartbeat("refresh")
    service.db["user_refresh_jobs"].create_index([("status", 1), ("retry_at", 1)])
    while not stop.is_set():
        health.tick()
        if not refresh_once(jobs):
            stop.wait(0.5)


def embed_once(breaker):
    from datetime import datetime, timezone
    if not breaker.available():
        return False
    now = datetime.now(timezone.utc)
    doc = service.user_vectors_collection.find_one({"embedding_status": "pending", "deleted": False,
        "embedding_target_model": settings.USER_EMBEDDING_MODEL,
        "$and": [
            {"$or": [{"embedding_retry_at": {"$exists": False}}, {"embedding_retry_at": {"$lte": now}}]},
            {"$or": [{"embedding_lease_until": {"$exists": False}}, {"embedding_lease_until": {"$lte": now}}]},
        ]})
    if doc is None:
        return False
    try:
        service.projection.embed_pending(doc["user_id"])
    except Exception as exc:
        breaker.failure()
        log.error("embedding_failed user=%s error=%s", doc["user_id"], type(exc).__name__)
    else:
        breaker.success()
    return True


def embed():
    health = heartbeat("embed")
    breaker = CircuitBreaker()
    service.user_vectors_collection.create_index([("embedding_status", 1), ("embedding_retry_at", 1)])
    while not stop.is_set():
        health.tick("healthy" if breaker.available() else "backoff")
        if not embed_once(breaker):
            stop.wait(1)


def reconcile():
    jobs = queue()
    count = 0
    for user_id in service.source.user_ids():
        jobs.enqueue(user_id)
        count += 1
    for doc in service.user_vectors_collection.find({"deleted": {"$ne": True}}, {"user_id": 1}):
        if "user_id" in doc:
            jobs.enqueue(doc["user_id"])
    log.info("reconciliation_enqueued source_users=%s", count)


def reconcile_loop():
    health = heartbeat("reconcile-loop")
    due = 0
    while not stop.is_set():
        health.tick()
        if time.monotonic() >= due:
            reconcile()
            due = time.monotonic() + max(30, settings.CDC_RECONCILE_INTERVAL_SECONDS)
        stop.wait(5)


def restart_connector():
    from urllib.request import Request, urlopen
    url = settings.CDC_CONNECT_URL.rstrip("/") + "/connectors/user-state-cdc/restart?includeTasks=true&onlyFailed=true"
    with urlopen(Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"}), timeout=5) as response:
        if response.status not in (200, 202, 204):
            raise RuntimeError("Connector restart request was rejected")
    log.info("connector_restart_requested; verify connector/task state with status")


def retry_cdc(key, user_ids=None, reconcile_all=False):
    from confluent_kafka import Consumer, TopicPartition
    record = service.db.cdc_dead_letters.find_one({"_id": key, "status": "failed"})
    if record is None:
        raise ValueError("No failed CDC record with this ID")
    jobs = queue()
    if reconcile_all:
        reconcile()
    elif user_ids:
        for user_id in user_ids:
            if user_id <= 0:
                raise ValueError("User IDs must be positive")
            jobs.enqueue(user_id)
    else:
        consumer = Consumer({"bootstrap.servers": settings.CDC_KAFKA_BOOTSTRAP_SERVERS,
                             "group.id": settings.CDC_GROUP_ID + "-quarantine-replay",
                             "enable.auto.commit": False, "enable.auto.offset.store": False,
                             "auto.offset.reset": "error"})
        try:
            target = TopicPartition(record["topic"], record["partition"], record["offset"])
            low, high = consumer.get_watermark_offsets(target, timeout=5, cached=False)
            if not low <= record["offset"] < high:
                raise OffsetGap("Quarantined record expired; reconcile or supply reviewed user IDs")
            consumer.assign([target])
            message = consumer.poll(10)
            if message is None or message.error() or message.offset() != record["offset"]:
                raise RuntimeError("Cannot fetch original quarantined record")
            event = json.loads(message.value()) if message.value() is not None else None
            process_event(event, service.source, jobs, settings.CDC_DATABASE)
            # No commit: replay consumer must never change the main group's offsets.
        finally:
            consumer.close()
    service.db.cdc_dead_letters.update_one({"_id": key, "status": "failed"},
        {"$set": {"status": "resubmitted", "resubmitted_at": time.time()}})


def failures():
    return {
        "cdc": list(service.db.cdc_dead_letters.find({"status": "failed"}, {"topic": 1, "partition": 1, "offset": 1, "error_type": 1}).limit(100)),
        "refresh": list(service.db.user_refresh_jobs.find({"status": "failed"}, {"attempts": 1, "error_type": 1}).limit(100)),
        "embedding": list(service.user_vectors_collection.find({"embedding_status": "failed"}, {"user_id": 1, "embedding_attempts": 1, "embedding_error_type": 1}).limit(100)),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["consume", "refresh", "embed", "reconcile", "reconcile-loop", "restart-connector", "status", "failures",
                                         "retry-refresh", "retry-embedding", "retry-cdc", "health"])
    parser.add_argument("--id")
    parser.add_argument("--user-id", type=int, action="append")
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args()
    if args.mode == "health":
        raise SystemExit(0 if args.id and worker_alive(args.id) else 1)
    if args.mode == "status":
        topics = [f"{settings.CDC_TOPIC_PREFIX}.{settings.CDC_DATABASE}.{t}" for t in TABLES]
        state = pipeline_status(service.db, settings.CDC_CONNECT_URL,
                                kafka=(settings.CDC_KAFKA_BOOTSTRAP_SERVERS, settings.CDC_GROUP_ID, topics))
        try:
            from sqlalchemy import text
            with service.source.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            state["mysql"] = "healthy"
        except Exception:
            state["mysql"] = "unavailable"
            state["ready"] = False
        print(json.dumps(state))
        raise SystemExit(0 if state["ready"] else 1)
    if args.mode == "failures":
        print(json.dumps(failures(), default=str))
        return
    if args.mode == "restart-connector":
        restart_connector()
        return
    if args.mode.startswith("retry-"):
        if args.id is None:
            parser.error("--id is required")
        if args.mode == "retry-cdc":
            if args.user_id and args.reconcile:
                parser.error("Use --user-id or --reconcile, not both")
            retry_cdc(args.id, args.user_id, args.reconcile)
        elif args.mode == "retry-refresh":
            if not queue().retry(int(args.id)):
                parser.error("No failed refresh job with this user ID")
        elif not service.projection.retry_embedding(int(args.id)):
            parser.error("No failed embedding with this user ID")
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    failed = False
    try:
        {"consume": consume, "refresh": refresh, "embed": embed, "reconcile": reconcile,
         "reconcile-loop": reconcile_loop}[args.mode]()
    except Exception as exc:
        failed = True
        heartbeat(args.mode).tick("failed", exc, force=True)
        log.error("worker_stopped mode=%s error=%s", args.mode, type(exc).__name__)
        raise SystemExit(1)
    finally:
        if not failed:
            heartbeat(args.mode).tick("stopped", force=True)


if __name__ == "__main__":
    main()
