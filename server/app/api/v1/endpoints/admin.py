from fastapi import APIRouter, Query
from typing import List, Dict, Any
from app.services.admin_service import admin_service

router = APIRouter()

@router.get("/stats/overview")
async def get_dashboard_stats():
    """대시보드 전체 통계 조회"""
    return admin_service.get_dashboard_stats()

@router.get("/stats/trends")
async def get_dashboard_trends():
    """대화 및 API 요청 추이 조회"""
    return admin_service.get_dashboard_trends()

@router.get("/stats/feedback")
async def get_feedback_stats():
    """피드백 분포 조회"""
    return admin_service.get_feedback_stats()

@router.get("/users")
async def get_user_stats(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str = Query("", description="이름 또는 ID 검색")
):
    """사용자별 AI 사용 통계 조회"""
    return admin_service.get_user_stats(page, limit, search)

@router.get("/logs")
async def get_chat_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str = Query("", description="사용자 ID 검색")
):
    """챗봇 대화 로그 목록 조회"""
    return admin_service.get_chat_logs(page, limit, search)

@router.get("/logs/{user_id}")
async def get_chat_details(
    user_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """특정 사용자의 대화 상세 내역 조회"""
    return admin_service.get_user_chat_history(user_id, page, limit)
