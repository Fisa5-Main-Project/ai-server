from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router

app = FastAPI(
    title="노후하우 AI 추천 서버",
    description="RAG와 Gemini를 이용한 개인 맞춤형 금융상품 추천 API",
    version="2.0.0",
    root_path="/api"
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정 (Next.js 직접 연결)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js (local dev)
        "http://127.0.0.1:3000",  # Next.js (local dev - alternative)
        "https://fisa-main-project.vercel.app",  # Vercel (dev/preview)
        "https://knowwhohow.cloud",  # Production
        "https://www.knowwhohow.cloud",
        "https://knowwhohow.site",  # Production (alternative)
        "https://www.knowwhohow.site",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# API v1 라우터 포함
app.include_router(api_router, prefix="/api")


@app.get("/")
def root():
    return {
        "service": "노후하우 AI 추천 서버",
        "version": "2.0.0",
        "description": "RAG 기반 금융상품 추천 및 챗봇 API",
        "endpoints": {
            "docs": "/docs",
            "recommendations": "/api/v1/recommendations/{user_id}",
            "chat_stream": "/api/v1/chat/stream",
            "chat_feedback": "/api/v1/chat/feedback",
            "vectorize": "/api/v1/users/{user_id}/vectorize"
        }
    }


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AI Server is running"}