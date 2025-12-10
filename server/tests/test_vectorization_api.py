"""
Vectorization API Tests (VEC-01)
Tests for /api/v1/users/{user_id}/vectorize endpoint
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestUserVectorization:
    """VEC-01: Vectorize User Profile Tests"""
    
    def test_vectorize_user_success(self, client, mock_user_vectorization_service):
        """Valid user_id → 200 OK with persona_text and status"""
        mock_result = {
            "user_id": 1,
            "persona_text": "30대 직장인으로 연봉 5천만원, 자산 1억원을 보유하고 있습니다. 안정적인 저축을 선호합니다.",
            "status": "success"
        }
        
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            return_value=mock_result
        )
        
        response = client.post("/api/v1/users/1/vectorize")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["user_id"] == 1
        assert "persona_text" in data
        assert len(data["persona_text"]) > 0
        assert data["status"] == "success"
        
        # Verify service was called with correct user_id
        mock_user_vectorization_service.vectorize_user.assert_called_once_with(1)
    
    def test_vectorize_user_persona_generation(self, client, mock_user_vectorization_service):
        """User data fetched from Spring Boot → Persona generated"""
        mock_result = {
            "user_id": 2,
            "persona_text": "20대 대학생으로 아르바이트 수입이 있습니다. 소액 저축에 관심이 많습니다.",
            "status": "success"
        }
        
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            return_value=mock_result
        )
        
        response = client.post("/api/v1/users/2/vectorize")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify persona text is meaningful
        assert "대학생" in data["persona_text"] or len(data["persona_text"]) > 20
    
    def test_vectorize_user_embedding_saved(self, client, mock_user_vectorization_service):
        """Gemini embedding created → Saved to MongoDB"""
        mock_result = {
            "user_id": 1,
            "persona_text": "테스트 페르소나",
            "status": "success"
        }
        
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            return_value=mock_result
        )
        
        response = client.post("/api/v1/users/1/vectorize")
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify vectorize_user was called (which handles embedding creation and storage)
        mock_user_vectorization_service.vectorize_user.assert_called_once()
    
    def test_vectorize_user_not_found(self, client, mock_user_vectorization_service):
        """User not found in Spring Boot → 500 Error"""
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            side_effect=Exception("User not found in Spring Boot")
        )
        
        response = client.post("/api/v1/users/999/vectorize")
        
        assert response.status_code == 500
        assert "벡터화 실패" in response.json()["detail"]
    
    def test_vectorize_user_embedding_generation_failure(self, client, mock_user_vectorization_service):
        """Embedding generation failure → 500 Error"""
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            side_effect=Exception("Gemini API error: Rate limit exceeded")
        )
        
        response = client.post("/api/v1/users/1/vectorize")
        
        assert response.status_code == 500
        data = response.json()
        assert "벡터화 실패" in data["detail"]
    
    def test_vectorize_user_mongodb_connection_error(self, client, mock_user_vectorization_service):
        """MongoDB connection error → 500 Error"""
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            side_effect=Exception("MongoDB connection failed")
        )
        
        response = client.post("/api/v1/users/1/vectorize")
        
        assert response.status_code == 500
    
    def test_vectorize_user_spring_boot_connection_error(self, client, mock_user_vectorization_service):
        """Spring Boot connection error → 500 Error"""
        mock_user_vectorization_service.vectorize_user = AsyncMock(
            side_effect=Exception("Failed to fetch user data from Spring Boot")
        )
        
        response = client.post("/api/v1/users/1/vectorize")
        
        assert response.status_code == 500
    
    def test_vectorize_multiple_users(self, client, mock_user_vectorization_service):
        """Test vectorization for multiple users"""
        for user_id in [1, 2, 3, 10, 100]:
            mock_result = {
                "user_id": user_id,
                "persona_text": f"사용자 {user_id}의 페르소나",
                "status": "success"
            }
            
            mock_user_vectorization_service.vectorize_user = AsyncMock(
                return_value=mock_result
            )
            
            response = client.post(f"/api/v1/users/{user_id}/vectorize")
            
            assert response.status_code == 200
            assert response.json()["user_id"] == user_id
