"""Legacy vectorization entry point using the shared current-state projection."""
from sqlalchemy.orm import Session
from app.services.user_vectorization_service import user_vectorization_service


class VectorService:
    def vectorize_user(self, db: Session, user_id: int):
        user_vectorization_service.refresh_user(user_id)
        user_vectorization_service.projection.embed_pending(user_id)
        return [f"user_{user_id}"]


vector_service = VectorService()
