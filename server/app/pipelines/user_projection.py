"""Publish persona first; retry embeddings independently with conditional writes."""
from datetime import datetime, timezone
from pymongo import ReturnDocument
from pymongo.write_concern import WriteConcern
from app.pipelines.persona import build_persona, persona_hash
from app.pipelines.user_source import UserNotFound


class ProjectionBusy(RuntimeError):
    pass


class UserProjection:
    def __init__(self, source, collection, embedder, model):
        self.source = source
        self.collection = collection.with_options(write_concern=WriteConcern(w="majority", j=True))
        self.embedder, self.model = embedder, model

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
            if reservation.get("persona_hash") != digest or reservation.get("embedding_model") != self.model:
                fields["embedding_status"] = "pending"
                update = {"$set": fields, "$unset": {"embedding": "", "embedding_hash": "", "embedding_retry_at": ""}}
            else:
                update = {"$set": fields}
            result = self.collection.update_one(match, update)
            if result.matched_count:
                return {"user_id": user_id, "persona_text": text, "persona_hash": digest, "status": "success"}
        raise ProjectionBusy("Concurrent user refreshes; retry the request")

    def embed_pending(self, user_id):
        doc = self.collection.find_one({"_id": f"user_{user_id}", "deleted": False})
        if not doc or doc.get("embedding_status") != "pending":
            return False
        vector = self.embedder(doc["persona_text"])
        result = self.collection.update_one(
            {"_id": doc["_id"], "persona_hash": doc["persona_hash"], "deleted": False},
            {"$set": {"embedding": vector, "embedding_hash": doc["persona_hash"], "embedding_model": self.model,
                      "embedding_status": "ready", "embedding_updated_at": datetime.now(timezone.utc)}})
        return bool(result.matched_count)

    def current_embedding(self, user_id):
        doc = self.collection.find_one({"_id": f"user_{user_id}", "deleted": False})
        if (doc and doc.get("embedding_status") == "ready"
                and doc.get("embedding_hash") == doc.get("persona_hash")
                and doc.get("embedding_model") == self.model):
            return doc.get("embedding")
        return None
