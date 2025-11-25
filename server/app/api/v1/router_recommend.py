"""
금융상품 추천 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from app.models.recommendation import RecommendationResponse
from app.services.rag_service import rag_service

router = APIRouter(tags=["Recommendations"])


@router.get("/recommendations/{user_id}", response_model=RecommendationResponse)
async def get_recommendations(user_id: int):
    """
    사용자 ID 기반 맞춤형 금융상품 추천
    
    - 사용자 임베딩을 MongoDB에서 가져옴
    - Vector Search로 유사한 금융상품 검색
    - 예적금, 연금저축, 펀드 각 1개씩 추천
    
    Returns:
        - deposit_or_saving: 예금 또는 적금 추천
        - annuity: 연금저축 추천
        - fund: 펀드 추천
    """
    try:
        recommendations = await rag_service.get_recommendations(user_id)
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 실패: {str(e)}")