"""Compatibility entry point using the shared current-state persona projection."""
from sqlalchemy.orm import Session
from app.services.user_vectorization_service import user_vectorization_service


class ProfileService:
    def get_user_persona(self, db: Session, user_id: int) -> str:
        return user_vectorization_service.get_current_persona(user_id)


profile_service = ProfileService()
