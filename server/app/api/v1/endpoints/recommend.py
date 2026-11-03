"""
금융상품 추천 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Depends
from app.gateway.auth import Principal, authenticated_user, authorize_owner
from app.gateway.errors import GatewayError
from app.gateway.service import usage_context
from app.schemas.recommendation import RecommendationResponse
from app.services.products_service import products_service

router = APIRouter(tags=["Recommendations"])


@router.get("/recommendations/{user_id}", response_model=RecommendationResponse)
async def get_recommendations(user_id: int, principal: Principal = Depends(authenticated_user)):
    """
    사용자 ID 기반 맞춤형 금융상품 추천
    
    - 최신 구조화 고객 프로필로 위험 및 자금 조건 검증
    - 검색된 후보 중 적합성이 확인된 상품만 최대 3개 반환
    - 검증 불가 시 추천 보류, request_id로 판단 이력 추적
    
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
    authorize_owner(principal, user_id)
    try:
        with usage_context(principal.user_id, 'recommendations'):
            recommendations = await products_service.get_recommendations(principal.user_id)
        return recommendations
    except GatewayError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 실패: 문제가 발생하였습니다.")
