"""
금융상품 추천 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from app.schemas.recommendation import RecommendationResponse
from app.services.products_service import products_service

router = APIRouter(tags=["Recommendations"])


@router.get("/recommendations/{user_id}", response_model=RecommendationResponse)
async def get_recommendations(user_id: int):
    """
    사용자 ID 기반 맞춤형 금융상품 추천
    
    - 사용자 임베딩을 MongoDB에서 가져옴
    - Vector Search로 유사한 금융상품 검색
    - 예적금, 연금저축, 펀드 각 1개씩 추천
    
    **Parameters:**
    - user_id: 사용자 ID
    
    **Returns:**
    - deposit_or_saving: 예금 또는 적금 추천 (RecommendedProduct)
    - annuity: 연금저축 추천 (RecommendedProduct)
    - fund: 펀드 추천 (RecommendedProduct)
    
    **RecommendedProduct 구조:**
    - product_id: MongoDB document ID (피드백 추적용)
    - product_type: "예금", "적금", "연금저축", "펀드"
    - product_name: 상품명
    - company_name: 제공회사
    - benefit: 핵심 혜택 요약
    - reason: AI 생성 추천 이유
    """
    try:
        recommendations = await products_service.get_recommendations(user_id)
        print("recommendations", recommendations)
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 실패: 문제가 발생하였습니다.")