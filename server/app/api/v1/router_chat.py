"""
챗봇 API 엔드포인트 (SSE 스트리밍)
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from app.services.chatbot_service import chatbot_service
import json

router = APIRouter(tags=["Chatbot"])


class ChatRequest(BaseModel):
    user_id: int
    session_id: str
    message: str
    keywords: Optional[List[int]] = None


class FeedbackRequest(BaseModel):
    user_id: int
    session_id: str
    message_id: str
    feedback: str  # "like" or "dislike"
    product_id: Optional[str] = None


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    스트리밍 챗봇 API (SSE)
    
    - 사용자 메시지를 받아 실시간으로 응답 스트리밍
    - 대화 히스토리 자동 저장
    - 금융상품 외 질문 예외처리
    """
    async def event_generator():
        try:
            async for chunk in chatbot_service.stream_chat(
                user_id=request.user_id,
                session_id=request.session_id,
                message=request.message,
                keywords=request.keywords
            ):
                # SSE 형식으로 전송
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            error_data = {
                "type": "error",
                "content": f"오류 발생: {str(e)}"
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/chat/feedback")
async def save_feedback(request: FeedbackRequest):
    """
    사용자 피드백 저장 API
    
    - 좋아요/싫어요 피드백 수집
    - 로그 분석용 데이터 저장
    """
    try:
        chatbot_service.save_feedback(
            user_id=request.user_id,
            session_id=request.session_id,
            message_id=request.message_id,
            feedback=request.feedback,
            product_id=request.product_id
        )
        return {"status": "success", "message": "피드백이 저장되었습니다."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피드백 저장 실패: {str(e)}")
