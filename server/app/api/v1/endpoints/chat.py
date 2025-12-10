"""
챗봇 API 엔드포인트 (SSE 스트리밍)
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, FeedbackRequest, FeedbackResponse
from app.services.chat_service import chat_service
import json

router = APIRouter(tags=["Chatbot"])


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    스트리밍 챗봇 API (SSE)
    
    - 사용자 메시지를 받아 실시간으로 응답 스트리밍
    - 사용자 컨텍스트(페르소나 + 추가 키워드) 자동 로딩
    - 대화 히스토리 자동 저장
    - 금융상품 외 질문 예외처리
    
    **Parameters:**
    - user_id: 사용자 ID
    - session_id: 세션 ID (채팅방 구분)
    - message: 사용자 메시지
    - keywords: (Optional) 추가 관심 키워드 ID 리스트
    
    **Returns:** SSE 스트리밍 응답
    - type: "token" - 토큰 단위 응답
    - type: "done" - 완료 신호
    - type: "error" - 에러 발생
    """
    print(f"\n[CHAT STREAM] Request received - User: {request.user_id}, Session: {request.session_id}")
    print(f"[CHAT STREAM] Message: {request.message}")
    
    async def event_generator():
        try:
            chunk_count = 0
            async for chunk in chat_service.stream_chat(
                user_id=request.user_id,
                session_id=request.session_id,
                message=request.message,
                keywords=request.keywords
            ):
                chunk_count += 1
                chunk_type = chunk.get("type", "unknown")
                
                # 로그 출력 (타입별 상세 정보)
                if chunk_type == "token":
                    print(f"Type: token, Content: {chunk.get('content', '')[:50]}...")
                elif chunk_type == "products":
                    product_count = len(chunk.get("products", []))
                    print(f"Type: products, Count: {product_count}")
                    print(f"Type: products, Products: {chunk.get('products', [])}")
                elif chunk_type == "keywords":
                    keywords = chunk.get("keywords", [])
                    print(f"Type: keywords, Keywords: {keywords}")
                elif chunk_type == "feature_guide":
                    print(f"Type: feature_guide, Title: {chunk.get('title', '')}")
                elif chunk_type == "done":
                    print(f"Type: done - Stream completed")
                elif chunk_type == "error":
                    print(f"Type: error, Message: {chunk.get('content', '')}")
                else:
                    print(f"Type: {chunk_type}")
                
                # SSE 형식으로 전송
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            
            print(f"[CHAT STREAM] Total chunks sent: {chunk_count}")
        
        except Exception as e:
            print(f"[CHAT STREAM ERROR] {str(e)}")
            import traceback
            traceback.print_exc()
            
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


@router.post("/chat/feedback", response_model=FeedbackResponse)
async def save_feedback(request: FeedbackRequest):
    """
    사용자 피드백 저장 API
    
    - 좋아요/싫어요 피드백 수집
    - 로그 분석용 데이터 저장
    
    **Parameters:**
    - user_id: 사용자 ID
    - session_id: 세션 ID
    - message_id: 메시지 ID
    - feedback: "like" or "dislike"
    - product_id: (Optional) 추천된 상품 ID
    """
    try:
        chat_service.save_feedback(
            user_id=request.user_id,
            session_id=request.session_id,
            message_id=request.message_id,
            feedback=request.feedback,
            product_id=request.product_id
        )
        return FeedbackResponse(
            status="success",
            message="피드백이 저장되었습니다."
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피드백 저장 실패: {str(e)}")

@router.get("/chat/history")
async def get_chat_history(user_id: int, session_id: str, limit: int = 5, skip: int = 0):
    """
    대화 히스토리 조회 API (페이지네이션 지원)
    
    - limit: 가져올 메시지 수 (기본 5)
    - skip: 건너뛸 메시지 수 (기본 0)
    """
    try:
        # 최신 메시지부터 가져오기 위해 내림차순 정렬 후 skip/limit 적용
        # 최신 메시지부터 가져오기 위해 내림차순 정렬 후 skip/limit 적용
        history = chat_service.get_paginated_chat_history(
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            skip=skip
        )
            
        return {"history": history}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"히스토리 조회 실패: {str(e)}")
