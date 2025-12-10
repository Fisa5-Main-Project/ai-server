"""
Chat API Tests (CHAT-01 to CHAT-03)
Tests for /api/v1/chat/* endpoints
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock


class TestChatStream:
    """CHAT-01: Stream Chat (SSE) Tests"""
    
    def test_stream_chat_success(self, client, mock_chat_service):
        """Valid request → SSE stream with tokens, products, keywords"""
        # Mock async generator for streaming
        async def mock_stream():
            yield {"type": "token", "content": "안녕하세요"}
            yield {"type": "token", "content": "!"}
            yield {"type": "products", "products": [
                {
                    "id": "prod_001",
                    "icon": "💰",
                    "type": "적금",
                    "name": "우리SUPER주거래적금",
                    "bank": "우리은행",
                    "features": ["최고 연 3.55%"],
                    "stat": "3.55%"
                }
            ]}
            yield {"type": "keywords", "keywords": ["적금", "저축"]}
            yield {"type": "done"}
        
        mock_chat_service.stream_chat = AsyncMock(return_value=mock_stream())
        
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "user_id": 1,
                "session_id": "test_session_1",
                "message": "적금 추천해주세요",
                "keywords": [1, 2]
            }
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        
        # Verify stream_chat was called with correct parameters
        mock_chat_service.stream_chat.assert_called_once()
        call_kwargs = mock_chat_service.stream_chat.call_args.kwargs
        assert call_kwargs["user_id"] == 1
        assert call_kwargs["session_id"] == "test_session_1"
        assert call_kwargs["message"] == "적금 추천해주세요"
        assert call_kwargs["keywords"] == [1, 2]
    
    def test_stream_chat_with_error(self, client, mock_chat_service):
        """Error handling → "error" event"""
        async def mock_stream_with_error():
            yield {"type": "token", "content": "처리 중"}
            yield {"type": "error", "content": "오류 발생: 데이터베이스 연결 실패"}
        
        mock_chat_service.stream_chat = AsyncMock(return_value=mock_stream_with_error())
        
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "user_id": 1,
                "session_id": "test_session_1",
                "message": "테스트"
            }
        )
        
        assert response.status_code == 200
        # SSE stream should still return 200 even with errors in stream
    
    def test_stream_chat_without_keywords(self, client, mock_chat_service):
        """Request without optional keywords parameter"""
        async def mock_stream():
            yield {"type": "token", "content": "응답"}
            yield {"type": "done"}
        
        mock_chat_service.stream_chat = AsyncMock(return_value=mock_stream())
        
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "user_id": 1,
                "session_id": "test_session_1",
                "message": "안녕하세요"
            }
        )
        
        assert response.status_code == 200
        
        call_kwargs = mock_chat_service.stream_chat.call_args.kwargs
        assert call_kwargs["keywords"] is None


class TestChatFeedback:
    """CHAT-02: Save Feedback Tests"""
    
    def test_save_feedback_like_with_product(self, client, mock_chat_service):
        """Valid like feedback with product_id → 200 OK"""
        mock_chat_service.save_feedback = MagicMock()
        
        response = client.post(
            "/api/v1/chat/feedback",
            json={
                "user_id": 1,
                "session_id": "test_session_1",
                "message_id": "msg_001",
                "feedback": "like",
                "product_id": "prod_001"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message"] == "피드백이 저장되었습니다."
        
        mock_chat_service.save_feedback.assert_called_once_with(
            user_id=1,
            session_id="test_session_1",
            message_id="msg_001",
            feedback="like",
            product_id="prod_001"
        )
    
    def test_save_feedback_dislike_without_product(self, client, mock_chat_service):
        """Valid dislike feedback without product_id → 200 OK"""
        mock_chat_service.save_feedback = MagicMock()
        
        response = client.post(
            "/api/v1/chat/feedback",
            json={
                "user_id": 1,
                "session_id": "test_session_1",
                "message_id": "msg_002",
                "feedback": "dislike"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        call_kwargs = mock_chat_service.save_feedback.call_args.kwargs
        assert call_kwargs["product_id"] is None
    
    def test_save_feedback_validation_error(self, client, mock_chat_service):
        """Missing required fields → 422 Validation Error"""
        response = client.post(
            "/api/v1/chat/feedback",
            json={
                "user_id": 1,
                "session_id": "test_session_1"
                # Missing message_id and feedback
            }
        )
        
        assert response.status_code == 422
    
    def test_save_feedback_database_error(self, client, mock_chat_service):
        """Database error → 500 Internal Server Error"""
        mock_chat_service.save_feedback = MagicMock(
            side_effect=Exception("Database connection failed")
        )
        
        response = client.post(
            "/api/v1/chat/feedback",
            json={
                "user_id": 1,
                "session_id": "test_session_1",
                "message_id": "msg_001",
                "feedback": "like"
            }
        )
        
        assert response.status_code == 500
        assert "피드백 저장 실패" in response.json()["detail"]


class TestChatHistory:
    """CHAT-03: Get Chat History Tests"""
    
    def test_get_chat_history_success(self, client, mock_chat_service, sample_chat_history):
        """Valid request → 200 OK with paginated history"""
        mock_chat_service.get_paginated_chat_history = MagicMock(
            return_value=[
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
            ]
        )
        
        response = client.get(
            "/api/v1/chat/history",
            params={
                "user_id": 1,
                "session_id": "test_session_1",
                "limit": 5,
                "skip": 0
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert len(data["history"]) == 2
        assert data["history"][0]["role"] == "user"
        
        mock_chat_service.get_paginated_chat_history.assert_called_once_with(
            user_id=1,
            session_id="test_session_1",
            limit=5,
            skip=0
        )
    
    def test_get_chat_history_with_pagination(self, client, mock_chat_service):
        """Pagination (limit, skip) → Correct subset returned"""
        mock_chat_service.get_paginated_chat_history = MagicMock(
            return_value=[
                {"role": "user", "content": "Message 3", "timestamp": "2024-12-01T10:02:00"}
            ]
        )
        
        response = client.get(
            "/api/v1/chat/history",
            params={
                "user_id": 1,
                "session_id": "test_session_1",
                "limit": 1,
                "skip": 2
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) == 1
        
        call_kwargs = mock_chat_service.get_paginated_chat_history.call_args.kwargs
        assert call_kwargs["limit"] == 1
        assert call_kwargs["skip"] == 2
    
    def test_get_chat_history_empty(self, client, mock_chat_service):
        """Empty history → 200 OK with empty array"""
        mock_chat_service.get_paginated_chat_history = MagicMock(return_value=[])
        
        response = client.get(
            "/api/v1/chat/history",
            params={
                "user_id": 999,
                "session_id": "empty_session"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["history"] == []
    
    def test_get_chat_history_default_params(self, client, mock_chat_service):
        """Request without optional params → Default values used"""
        mock_chat_service.get_paginated_chat_history = MagicMock(return_value=[])
        
        response = client.get(
            "/api/v1/chat/history",
            params={
                "user_id": 1,
                "session_id": "test_session_1"
            }
        )
        
        assert response.status_code == 200
        
        call_kwargs = mock_chat_service.get_paginated_chat_history.call_args.kwargs
        assert call_kwargs["limit"] == 5  # Default value
        assert call_kwargs["skip"] == 0   # Default value
    
    def test_get_chat_history_database_error(self, client, mock_chat_service):
        """Database error → 500 Error"""
        mock_chat_service.get_paginated_chat_history = MagicMock(
            side_effect=Exception("MongoDB connection failed")
        )
        
        response = client.get(
            "/api/v1/chat/history",
            params={
                "user_id": 1,
                "session_id": "test_session_1"
            }
        )
        
        assert response.status_code == 500
        assert "히스토리 조회 실패" in response.json()["detail"]
