"""
사용자 벡터화 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from app.services.user_vectorization_service import user_vectorization_service
from app.schemas.vectorize import VectorizationResponse

router = APIRouter(tags=["User Vectorization"])


@router.post("/users/{user_id}/vectorize", response_model=VectorizationResponse)
async def vectorize_user(user_id: int):
    """
    사용자 벡터화 API
    
    - Spring Boot에서 사용자 정보 가져오기
    - 페르소나 텍스트 생성
    - Gemini 임베딩 생성
    - MongoDB에 저장
    """
    try:
        result = await user_vectorization_service.vectorize_user(user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"벡터화 실패: {str(e)}")
