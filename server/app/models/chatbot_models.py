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


class ChatStreamChunk(BaseModel):
    """SSE 스트리밍 청크"""
    type: str  # "token", "done", "error", "product"
    content: str
    metadata: Optional[dict] = None  # 상품 정보 등 추가 메타데이터


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
