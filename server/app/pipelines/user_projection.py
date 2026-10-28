"""Publish persona first; retry embeddings independently with conditional writes."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from pymongo import ReturnDocument
from pymongo.write_concern import WriteConcern
from app.pipelines.persona import build_persona, persona_hash
from app.pipelines.user_source import UserNotFound
from app.pipelines.resilience import backoff


class ProjectionBusy(RuntimeError):
    pass


class UserProjection:
    def __init__(self, source, collection, embedder, model, max_attempts=5, lease_seconds=120):
        self.source = source
        self.collection = collection.with_options(write_concern=WriteConcern(w="majority", j=True))
        self.embedder, self.model = embedder, model
        self.max_attempts, self.lease_seconds = max_attempts, lease_seconds

    def refresh(self, user_id):
        key = f"user_{user_id}"
        for _ in range(5):
            # Reserve before reading. Older source reads cannot overwrite newer refreshes.
            reservation = self.collection.find_one_and_update(
                {"_id": key}, {"$inc": {"refresh_revision": 1},
                               "$setOnInsert": {"user_id": user_id, "created_at": datetime.now(timezone.utc)}},
                upsert=True, return_document=ReturnDocument.AFTER)
            revision = reservation["refresh_revision"]
            match = {"_id": key, "refresh_revision": revision}
            now = datetime.now(timezone.utc)
            try:
                data = self.source.read(user_id)
                text = build_persona(data)
            except UserNotFound:
                result = self.collection.update_one(match, {
                    "$set": {"deleted": True, "updated_at": now, "embedding_status": "deleted"},
                    "$unset": {"persona_text": "", "persona_hash": "", "embedding": "", "embedding_hash": "", "keyword_ids": ""}})
                if result.matched_count:
                    raise
                continue
            digest = persona_hash(text)
            now = datetime.now(timezone.utc)
            fields = {"persona_text": text, "persona_hash": digest, "deleted": False,
                      "keyword_ids": sorted({int(kw["keyword_id"]) for kw in data.get("keywords", []) if "keyword_id" in kw}),
                      "source_checked_at": now, "updated_at": now}
            target = reservation.get("embedding_target_model", reservation.get("embedding_model"))
            if reservation.get("persona_hash") != digest or target != self.model:
                fields["embedding_status"] = "pending"
                fields["embedding_target_model"] = self.model
                fields["embedding_attempts"] = 0
                update = {"$set": fields, "$unset": {
                    "embedding": "", "embedding_hash": "", "embedding_retry_at": "",
                    "embedding_error_type": "", "embedding_lease_token": "", "embedding_lease_until": ""}}
            else:
                update = {"$set": fields}
            result = self.collection.update_one(match, update)
            if result.matched_count:
                return {"user_id": user_id, "persona_text": text, "persona_hash": digest, "status": "success"}
        raise ProjectionBusy("Concurrent user refreshes; retry the request")

    def embed_pending(self, user_id):
        now = datetime.now(timezone.utc)
        token = uuid4().hex
        doc = self.collection.find_one_and_update({
            "_id": f"user_{user_id}", "deleted": False, "embedding_status": "pending",
            "embedding_target_model": self.model,
            "$and": [
                {"$or": [{"embedding_retry_at": {"$exists": False}}, {"embedding_retry_at": {"$lte": now}}]},
                {"$or": [{"embedding_lease_until": {"$exists": False}}, {"embedding_lease_until": {"$lte": now}}]},
            ]}, {"$set": {"embedding_lease_token": token,
                          "embedding_lease_until": now + timedelta(seconds=self.lease_seconds)}},
            return_document=ReturnDocument.AFTER)
        if doc is None:
            return False
        match = {"_id": doc["_id"], "persona_hash": doc["persona_hash"], "deleted": False,
                 "embedding_target_model": self.model, "embedding_lease_token": token}
        try:
            vector = self.embedder(doc["persona_text"])
            if not vector:
                raise ValueError("Empty embedding")
        except Exception as exc:
            attempts = doc.get("embedding_attempts", 0) + 1
            self.collection.update_one(match, {
                "$set": {"embedding_attempts": attempts, "embedding_error_type": type(exc).__name__,
                         "embedding_status": "failed" if attempts >= self.max_attempts else "pending",
                         "embedding_retry_at": datetime.now(timezone.utc) + timedelta(seconds=backoff(attempts))},
                "$unset": {"embedding_lease_token": "", "embedding_lease_until": ""}})
            raise
        result = self.collection.update_one(
            match,
            {"$set": {"embedding": vector, "embedding_hash": doc["persona_hash"], "embedding_model": self.model,
                      "embedding_status": "ready", "embedding_attempts": 0, "embedding_updated_at": datetime.now(timezone.utc)},
             "$unset": {"embedding_lease_token": "", "embedding_lease_until": "",
                        "embedding_error_type": "", "embedding_retry_at": ""}})
        return bool(result.matched_count)

    def retry_embedding(self, user_id):
        result = self.collection.update_one({"_id": f"user_{user_id}", "deleted": False, "embedding_status": "failed"}, {
            "$set": {"embedding_status": "pending", "embedding_attempts": 0},
            "$unset": {"embedding_retry_at": "", "embedding_error_type": "", "embedding_lease_token": "", "embedding_lease_until": ""}})
        return bool(result.matched_count)

    def current_embedding(self, user_id):
        doc = self.collection.find_one({"_id": f"user_{user_id}", "deleted": False})
        if (doc and doc.get("embedding_status") == "ready"
                and doc.get("embedding_hash") == doc.get("persona_hash")
                and doc.get("embedding_model") == self.model):
            return doc.get("embedding")
        return None
