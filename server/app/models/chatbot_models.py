"""
챗봇 API Request/Response 모델
"""
from pydantic import BaseModel
from typing import List, Optional


class ChatRequest(BaseModel):
    """챗봇 채팅 요청"""
    user_id: int
    session_id: str
    message: str
    keywords: Optional[List[int]] = None  # 추가 키워드 ID 리스트 (선택)


class ChatProduct(BaseModel):
    """클라이언트 ChatProduct 인터페이스와 일치하는 모델"""
    id: str
    icon: str
    type: str
    name: str
    bank: str
    features: List[str]
    stat: str


class ChatStreamChunk(BaseModel):
    """SSE 스트리밍 청크"""
    type: str  # "token", "products", "keywords", "done", "error"
    content: Optional[str] = None
    products: Optional[List[ChatProduct]] = None
    keywords: Optional[List[str]] = None
    metadata: Optional[dict] = None


class FeedbackRequest(BaseModel):
    """사용자 피드백 요청"""
    user_id: int
    session_id: str
    message_id: str
    feedback: str  # "like" or "dislike"
    product_id: Optional[str] = None  # 추천된 상품 ID


class FeedbackResponse(BaseModel):
    """피드백 응답"""
    status: str
    message: str
