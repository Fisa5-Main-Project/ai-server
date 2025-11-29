from pydantic import BaseModel
from typing import List, Optional

# --- Request Models ---

class RecommendationRequest(BaseModel):
    # Spring Boot는 user_id만 넘겨주면 됩니다.
    user_id: int

# --- Response Models ---
# (이미지의 포트폴리오 카드 형식)

class RecommendedProduct(BaseModel):
    product_id: Optional[str] = None  # MongoDB document ID (피드백 추적용)
    product_type: Optional[str] = None        # "예금", "적금", "연금저축", "펀드"
    product_name: Optional[str] = None         # 상품명 (e.g., "우리SUPER주거래적금")
    company_name: Optional[str] = None         # 제공회사 (e.g., "우리은행")
    benefit: Optional[str] = None              # 핵심 혜택 요약 (e.g., "최고 연 3.55%")
    reason: Optional[str] = None               # (AI 생성) 이 상품을 추천하는 이유
    
from pydantic import BaseModel
from typing import List, Optional

# --- Request Models ---

class RecommendationRequest(BaseModel):
    # Spring Boot는 user_id만 넘겨주면 됩니다.
    user_id: int

# --- Response Models ---
# (이미지의 포트폴리오 카드 형식)

class RecommendedProduct(BaseModel):
    product_id: Optional[str] = None  # MongoDB document ID (피드백 추적용)
    product_type: Optional[str] = None        # "예금", "적금", "연금저축", "펀드"
    product_name: Optional[str] = None         # 상품명 (e.g., "우리SUPER주거래적금")
    company_name: Optional[str] = None         # 제공회사 (e.g., "우리은행")
    benefit: Optional[str] = None              # 핵심 혜택 요약 (e.g., "최고 연 3.55%")
    reason: Optional[str] = None               # (AI 생성) 이 상품을 추천하는 이유
    
    # 추가 선택 필드
    interest_rate: Optional[float] = None  # 금리 (예적금, 연금)
    return_rate: Optional[float] = None    # 수익률 (펀드)
    min_amount: Optional[int] = None       # 최소 가입 금액
    max_amount: Optional[int] = None       # 최대 가입 금액

class RecommendationResponse(BaseModel):
    # 3가지 금융상품을 각각 하나씩 추천 (Legacy support)
    deposit_or_saving: Optional[RecommendedProduct] = None
    annuity: Optional[RecommendedProduct] = None
    fund: Optional[RecommendedProduct] = None
    
    # 유연한 상품 추천을 위한 리스트 (New)
    products: Optional[List[RecommendedProduct]] = None