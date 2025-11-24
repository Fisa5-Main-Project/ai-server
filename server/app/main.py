from fastapi import FastAPI
from app.api.v1 import router_recommend, router_chat

app = FastAPI(
    title="노후하우 AI 추천 서버",
    description="RAG와 Gemini를 이용한 개인 맞춤형 금융상품 추천 API",
    version="1.0.0"
)

# API v1 라우터 포함
app.include_router(router_recommend.router, prefix="/api/v1")
app.include_router(router_chat.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AI Server is running"}