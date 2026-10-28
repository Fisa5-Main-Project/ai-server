from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.pipelines.monitoring import pipeline_status
from app.services.user_vectorization_service import user_vectorization_service

app = FastAPI(
    title="노후하우 AI 추천 서버",
    description="RAG와 Gemini를 이용한 개인 맞춤형 금융상품 추천 API",
    version="2.0.0",
    root_path="/ai",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정 (Next.js 직접 연결)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 로컬 메인 클라이언트
        "http://localhost:3001",  # 로컬 관리자
        "http://127.0.0.1:3000",  # Next.js (local dev - alternative)
        "https://fisa-main-project.vercel.app",  # Vercel (dev/preview)
        "https://knowwhohow.cloud",  # Production
        "https://www.knowwhohow.cloud",
        "https://knowwhohow.site",  # Production (alternative)
        "https://www.knowwhohow.site",
        "https://knowwhohow.cloud/ai",
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


@app.get("/health/ready")
def readiness():
    """Readiness is separate from process liveness; never return financial payloads."""
    result = {"ready": True, "checks": {}}
    service = user_vectorization_service
    try:
        with service.source.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["checks"]["mysql"] = "healthy"
    except Exception:
        result["checks"]["mysql"] = "unavailable"
        result["ready"] = False
    try:
        service.db.command("ping")
        result["checks"]["mongo"] = "healthy"
        if settings.CDC_MONITORING_ENABLED:
            result["pipeline"] = pipeline_status(service.db, settings.CDC_CONNECT_URL)
            # Read-through serving still works during CDC/embedding outages.
            result["pipeline_ready"] = result["pipeline"]["ready"]
    except Exception:
        result["checks"]["mongo"] = "unavailable"
        result["ready"] = False
    return JSONResponse(result, status_code=200 if result["ready"] else 503)
