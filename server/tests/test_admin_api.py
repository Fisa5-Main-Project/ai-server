"""
Admin API Tests (ADMIN-01 to ADMIN-06)
Tests for /api/admin/* endpoints
"""
import pytest
from unittest.mock import MagicMock


class TestDashboardStats:
    """ADMIN-01: Dashboard Overview Stats Tests"""
    
    def test_get_dashboard_stats_success(self, client, mock_admin_service):
        """Valid request → 200 OK with statistics"""
        mock_stats = {
            "total_chats": 1500,
            "total_api_calls": 1500,
            "satisfaction_rate": 85.5,
            "active_users": 120
        }
        
        mock_admin_service.get_dashboard_stats = MagicMock(return_value=mock_stats)
        
        response = client.get("/api/admin/stats/overview")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_chats"] == 1500
        assert data["total_api_calls"] == 1500
        assert data["satisfaction_rate"] == 85.5
        assert data["active_users"] == 120
        
        mock_admin_service.get_dashboard_stats.assert_called_once()
    
    def test_get_dashboard_stats_empty_database(self, client, mock_admin_service):
        """Empty database → 200 OK with zero values"""
        mock_stats = {
            "total_chats": 0,
            "total_api_calls": 0,
            "satisfaction_rate": 0,
            "active_users": 0
        }
        
        mock_admin_service.get_dashboard_stats = MagicMock(return_value=mock_stats)
        
        response = client.get("/api/admin/stats/overview")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_chats"] == 0
        assert data["total_api_calls"] == 0
        assert data["satisfaction_rate"] == 0
        assert data["active_users"] == 0


class TestDashboardTrends:
    """ADMIN-02: Dashboard Trends Tests"""
    
    def test_get_dashboard_trends_success(self, client, mock_admin_service):
        """Valid request → 200 OK with monthly trends"""
        mock_trends = {
            "trends": [
                {"date": "2024-10", "api_calls": 500, "user_chats": 500},
                {"date": "2024-11", "api_calls": 750, "user_chats": 750},
                {"date": "2024-12", "api_calls": 1000, "user_chats": 1000}
            ]
        }
        
        mock_admin_service.get_dashboard_trends = MagicMock(return_value=mock_trends)
        
        response = client.get("/api/admin/stats/trends")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "trends" in data
        assert len(data["trends"]) == 3
        assert data["trends"][0]["date"] == "2024-10"
        assert data["trends"][0]["api_calls"] == 500
        assert data["trends"][0]["user_chats"] == 500
    
    def test_get_dashboard_trends_empty(self, client, mock_admin_service):
        """Empty database → 200 OK with empty trends array"""
        mock_trends = {"trends": []}
        
        mock_admin_service.get_dashboard_trends = MagicMock(return_value=mock_trends)
        
        response = client.get("/api/admin/stats/trends")
        
        assert response.status_code == 200
        data = response.json()
        assert data["trends"] == []


class TestFeedbackStats:
    """ADMIN-03: Feedback Distribution Tests"""
    
    def test_get_feedback_stats_success(self, client, mock_admin_service):
        """Valid request → 200 OK with like/dislike counts"""
        mock_feedback = {
            "like": 850,
            "dislike": 150
        }
        
        mock_admin_service.get_feedback_stats = MagicMock(return_value=mock_feedback)
        
        response = client.get("/api/admin/stats/feedback")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["like"] == 850
        assert data["dislike"] == 150
    
    def test_get_feedback_stats_no_data(self, client, mock_admin_service):
        """No feedback data → 200 OK with zero counts"""
        mock_feedback = {
            "like": 0,
            "dislike": 0
        }
        
        mock_admin_service.get_feedback_stats = MagicMock(return_value=mock_feedback)
        
        response = client.get("/api/admin/stats/feedback")
        
        assert response.status_code == 200
        data = response.json()
        assert data["like"] == 0
        assert data["dislike"] == 0


class TestUserStats:
    """ADMIN-04: User Statistics Tests"""
    
    def test_get_user_stats_success(self, client, mock_admin_service):
        """Valid request → 200 OK with paginated user stats"""
        mock_stats = {
            "users": [
                {
                    "user_id": 1,
                    "name": "홍길동",
                    "login_id": "hong123",
                    "chat_count": 50,
                    "api_count": 50,
                    "likes": 40,
                    "dislikes": 10,
                    "satisfaction": 80.0
                },
                {
                    "user_id": 2,
                    "name": "김철수",
                    "login_id": "kim456",
                    "chat_count": 30,
                    "api_count": 30,
                    "likes": 25,
                    "dislikes": 5,
                    "satisfaction": 83.3
                }
            ],
            "total": 100,
            "page": 1,
            "limit": 10
        }
        
        mock_admin_service.get_user_stats = MagicMock(return_value=mock_stats)
        
        response = client.get("/api/admin/users", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["users"]) == 2
        assert data["total"] == 100
        assert data["page"] == 1
        assert data["limit"] == 10
        
        # Verify user data structure
        assert data["users"][0]["user_id"] == 1
        assert data["users"][0]["name"] == "홍길동"
        assert data["users"][0]["satisfaction"] == 80.0
    
    def test_get_user_stats_with_search(self, client, mock_admin_service):
        """Search by name/login_id → Filtered results"""
        mock_stats = {
            "users": [
                {
                    "user_id": 1,
                    "name": "홍길동",
                    "login_id": "hong123",
                    "chat_count": 50,
                    "api_count": 50,
                    "likes": 40,
                    "dislikes": 10,
                    "satisfaction": 80.0
                }
            ],
            "total": 1,
            "page": 1,
            "limit": 10
        }
        
        mock_admin_service.get_user_stats = MagicMock(return_value=mock_stats)
        
        response = client.get("/api/admin/users", params={"search": "홍길동"})
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["users"]) == 1
        assert data["users"][0]["name"] == "홍길동"
        
        # Verify service was called with search parameter
        call_kwargs = mock_admin_service.get_user_stats.call_args.kwargs
        assert call_kwargs["search"] == "홍길동"
    
    def test_get_user_stats_pagination(self, client, mock_admin_service):
        """Pagination (page, limit) → Correct subset returned"""
        mock_stats = {
            "users": [],
            "total": 100,
            "page": 3,
            "limit": 20
        }
        
        mock_admin_service.get_user_stats = MagicMock(return_value=mock_stats)
        
        response = client.get("/api/admin/users", params={"page": 3, "limit": 20})
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 3
        assert data["limit"] == 20
        
        call_kwargs = mock_admin_service.get_user_stats.call_args.kwargs
        assert call_kwargs["page"] == 3
        assert call_kwargs["limit"] == 20


class TestChatLogs:
    """ADMIN-05: Chat Logs Tests"""
    
    def test_get_chat_logs_success(self, client, mock_admin_service):
        """Valid request → 200 OK with paginated logs"""
        mock_logs = {
            "logs": [
                {
                    "user_id": 1,
                    "name": "홍길동",
                    "last_message": "적금 추천해주세요",
                    "last_active": "2024-12-01T10:00:00",
                    "total_messages": 50
                },
                {
                    "user_id": 2,
                    "name": "김철수",
                    "last_message": "연금저축 상품이 궁금합니다",
                    "last_active": "2024-12-01T09:30:00",
                    "total_messages": 30
                }
            ],
            "page": 1,
            "limit": 10
        }
        
        mock_admin_service.get_chat_logs = MagicMock(return_value=mock_logs)
        
        response = client.get("/api/admin/logs", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["logs"]) == 2
        assert data["logs"][0]["user_id"] == 1
        assert data["logs"][0]["last_message"] == "적금 추천해주세요"
    
    def test_get_chat_logs_with_search(self, client, mock_admin_service):
        """Search by user_id → Filtered results"""
        mock_logs = {
            "logs": [
                {
                    "user_id": 1,
                    "name": "홍길동",
                    "last_message": "테스트 메시지",
                    "last_active": "2024-12-01T10:00:00",
                    "total_messages": 50
                }
            ],
            "page": 1,
            "limit": 10
        }
        
        mock_admin_service.get_chat_logs = MagicMock(return_value=mock_logs)
        
        response = client.get("/api/admin/logs", params={"search": "1"})
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["logs"]) == 1
        assert data["logs"][0]["user_id"] == 1
    
    def test_get_chat_logs_message_truncation(self, client, mock_admin_service):
        """Last message truncation → Max 50 characters"""
        long_message = "이것은 매우 긴 메시지입니다. " * 10  # Very long message
        truncated = long_message[:50] + "..."
        
        mock_logs = {
            "logs": [
                {
                    "user_id": 1,
                    "name": "홍길동",
                    "last_message": truncated,
                    "last_active": "2024-12-01T10:00:00",
                    "total_messages": 50
                }
            ],
            "page": 1,
            "limit": 10
        }
        
        mock_admin_service.get_chat_logs = MagicMock(return_value=mock_logs)
        
        response = client.get("/api/admin/logs")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify message is truncated
        assert len(data["logs"][0]["last_message"]) <= 53  # 50 + "..."


class TestUserChatHistory:
    """ADMIN-06: User Chat History Tests"""
    
    def test_get_user_chat_history_success(self, client, mock_admin_service):
        """Valid user_id → 200 OK with paginated chat history"""
        mock_history = {
            "history": [
                {
                    "role": "user",
                    "content": "안녕하세요",
                    "timestamp": "2024-12-01T10:00:00"
                },
                {
                    "role": "assistant",
                    "content": "안녕하세요! 무엇을 도와드릴까요?",
                    "timestamp": "2024-12-01T10:00:05"
                }
            ],
            "total": 50,
            "page": 1,
            "limit": 20
        }
        
        mock_admin_service.get_user_chat_history = MagicMock(return_value=mock_history)
        
        response = client.get("/api/admin/logs/1", params={"page": 1, "limit": 20})
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["history"]) == 2
        assert data["total"] == 50
        assert data["history"][0]["role"] == "user"
        assert data["history"][1]["role"] == "assistant"
    
    def test_get_user_chat_history_pagination(self, client, mock_admin_service):
        """Pagination → Correct subset"""
        mock_history = {
            "history": [],
            "total": 100,
            "page": 2,
            "limit": 20
        }
        
        mock_admin_service.get_user_chat_history = MagicMock(return_value=mock_history)
        
        response = client.get("/api/admin/logs/1", params={"page": 2, "limit": 20})
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 2
        assert data["limit"] == 20
    
    def test_get_user_chat_history_empty(self, client, mock_admin_service):
        """User with no chats → 200 OK with empty history"""
        mock_history = {
            "history": [],
            "total": 0,
            "page": 1,
            "limit": 20
        }
        
        mock_admin_service.get_user_chat_history = MagicMock(return_value=mock_history)
        
        response = client.get("/api/admin/logs/999")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["history"] == []
        assert data["total"] == 0
