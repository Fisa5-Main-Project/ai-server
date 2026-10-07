"""Failure policies shared by workers; never persist exception messages or payloads."""
import random
import time
from datetime import datetime, timezone
from hashlib import sha256
from pymongo.write_concern import WriteConcern


def utcnow():
    return datetime.now(timezone.utc)


def backoff(attempt, base=2, cap=60):
    return min(cap, base * 2 ** min(max(attempt - 1, 0), 8)) * random.uniform(0.8, 1.0)


class CircuitBreaker:
    def __init__(self, threshold=3, cooldown=30, clock=time.monotonic):
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.failures = 0
        self.open_until = 0

    def available(self):
        return self.clock() >= self.open_until

    def success(self):
        self.failures = 0
        self.open_until = 0

    def failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = self.clock() + self.cooldown


class CDCQuarantine:
    def __init__(self, collection):
        self.collection = collection.with_options(write_concern=WriteConcern(w="majority", j=True))

    def save(self, message, error):
        key = f"{message.topic()}:{message.partition()}:{message.offset()}"
        raw = message.value() or b""
        # Keep coordinates and digest only. A malformed payload may contain secrets.
        self.collection.update_one({"_id": key}, {"$setOnInsert": {
            "topic": message.topic(), "partition": message.partition(), "offset": message.offset(),
            "payload_sha256": sha256(raw).hexdigest(), "payload_bytes": len(raw),
            "error_type": type(error).__name__, "status": "failed", "created_at": utcnow(),
        }}, upsert=True)
        return key
