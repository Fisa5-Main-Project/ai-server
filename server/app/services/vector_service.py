from sqlalchemy.orm import Session
from app.services.profile_service import profile_service
from app.db.vector_store import user_vector_store
from langchain_core.documents import Document

class VectorService:
    def vectorize_user(self, db: Session, user_id: int):
        """
        RDS에서 사용자 정보를 가져와 페르소나를 생성하고,
        이를 벡터화하여 MongoDB Atlas에 저장합니다.
        """
        # 1. 사용자 페르소나 생성 (Text)
        persona_text = profile_service.get_user_persona(db, user_id)
        
        if not persona_text:
            print(f"User {user_id} not found or empty persona.")
            return None

        # 2. Document 객체 생성
        # metadata에 user_id를 저장하여 나중에 검색/필터링 가능하게 함
        doc = Document(
            page_content=persona_text,
            metadata={"user_id": user_id, "type": "user_persona"}
        )
        
        # 3. MongoDB Atlas에 벡터 저장 (기존 데이터가 있으면 중복될 수 있으므로 주의)
        # 실무에서는 user_id로 기존 벡터를 삭제하고 다시 넣는 로직이 필요할 수 있음
        # 여기서는 add_documents 사용
        ids = user_vector_store.add_documents([doc])
        
        print(f"User {user_id} vectorized. IDs: {ids}")
        return ids

vector_service = VectorService()
