"""Compatibility facade over the shared, continuously refreshed user projection."""
import asyncio
from pymongo import MongoClient
from sqlalchemy import create_engine

from app.core.config import settings
from app.pipelines.persona import build_persona
from app.pipelines.user_source import MySQLUserSource
from app.pipelines.user_projection import UserProjection


def embed_persona(text):
    # CDC ingestion and persona refresh do not initialize/call the embedding client.
    from app.services.embedding import embeddings
    return embeddings.embed_query(text)


class UserVectorizationService:
    def __init__(self):
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.DB_NAME]
        self.user_vectors_collection = self.db["user_vectors"]
        self.source = MySQLUserSource(create_engine(settings.MYSQL_DB_URL, pool_pre_ping=True),
                                      self.user_vectors_collection)
        self.projection = UserProjection(self.source, self.user_vectors_collection,
                                         embed_persona, settings.USER_EMBEDDING_MODEL)

    def get_user_data_from_db(self, user_id):
        return self.source.read(user_id)

    def generate_persona_text(self, user_data):
        return build_persona(user_data)

    def refresh_user(self, user_id):
        return self.projection.refresh(user_id)

    def get_current_persona(self, user_id):
        # CDC lag/outage must not silently serve an old financial profile.
        # Source failures propagate instead of falling back to stale assets.
        return self.refresh_user(user_id)["persona_text"]

    async def vectorize_user(self, user_id):
        result = await asyncio.to_thread(self.refresh_user, user_id)
        await asyncio.to_thread(self.projection.embed_pending, user_id)
        return result

    def get_user_embedding(self, user_id):
        return self.projection.current_embedding(user_id)


user_vectorization_service = UserVectorizationService()
