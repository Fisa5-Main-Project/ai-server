from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from app.core.config import settings
import asyncio

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    user_id: int = None # 추후 사용자 컨텍스트 활용 가능

# Streaming을 위한 LLM 설정
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0.7,
    streaming=True
)

async def generate_chat_response(message: str):
    """
    사용자 메시지를 받아 LLM의 응답을 스트리밍으로 생성합니다.
    """
    async for chunk in llm.astream([HumanMessage(content=message)]):
        yield chunk.content

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    챗봇 API (Streaming)
    사용자의 질문에 대해 실시간으로 응답을 스트리밍합니다.
    """
    return StreamingResponse(
        generate_chat_response(request.message),
        media_type="text/event-stream"
    )
