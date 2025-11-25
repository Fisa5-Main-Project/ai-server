from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router_recommend, router_chat, router_vectorize

app = FastAPI(
    title="노후하우 AI 추천 서버",
    description="RAG와 Gemini를 이용한 개인 맞춤형 금융상품 추천 API",
    version="1.0.0"
)

# CORS 설정 (Spring Boot 게이트웨이 연동)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8060",  # Spring Boot (local)
        "http://localhost:3000",  # Next.js (local)
        "https://fisa-main-project.vercel.app",  # Vercel
        "https://knowwhohow.cloud",  # Production
        "https://www.knowwhohow.cloud",
        "https://knowwhohow.site",  # Production
        "https://www.knowwhohow.site"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 라우터 포함
app.include_router(router_recommend.router, prefix="/api/v1")
app.include_router(router_chat.router, prefix="/api/v1")
app.include_router(router_vectorize.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AI Server is running"}