from fastapi import APIRouter
from app.api.v1.endpoints import chat, recommend, vectorize, admin

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/v1")
api_router.include_router(recommend.router, prefix="/v1")
api_router.include_router(vectorize.router, prefix="/v1")
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
