"""
Recommendation API Tests (REC-01)
Tests for /api/v1/recommendations/* endpoints
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestRecommendations:
    """REC-01: Get Personalized Recommendations Tests"""
    
    def test_get_recommendations_success(self, client, mock_products_service):
        """Valid user with embedding → 200 OK with 3 products"""
        mock_recommendations = {
            "deposit_or_saving": {
                "product_id": "prod_001",
                "product_type": "적금",
                "product_name": "우리SUPER주거래적금",
                "company_name": "우리은행",
                "benefit": "최고 연 3.55%",
                "reason": "안정적인 저축을 원하시는 고객님께 적합한 상품입니다.",
                "interest_rate": 3.55
            },
            "annuity": {
                "product_id": "prod_002",
                "product_type": "연금저축",
                "product_name": "KB Star 연금저축",
                "company_name": "KB국민은행",
                "benefit": "세액공제 혜택",
                "reason": "노후 준비를 위한 안정적인 연금 상품입니다.",
                "interest_rate": 4.0
            },
            "fund": {
                "product_id": "prod_003",
                "product_type": "펀드",
                "product_name": "삼성 글로벌 성장 펀드",
                "company_name": "삼성자산운용",
                "benefit": "글로벌 분산투자",
                "reason": "장기 투자로 높은 수익을 기대할 수 있습니다.",
                "return_rate": 8.5
            }
        }
        
        mock_products_service.get_recommendations = AsyncMock(
            return_value=mock_recommendations
        )
        
        response = client.get("/api/v1/recommendations/1")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all 3 product types are returned
        assert "deposit_or_saving" in data
        assert "annuity" in data
        assert "fund" in data
        
        # Verify product structure
        assert data["deposit_or_saving"]["product_type"] == "적금"
        assert data["deposit_or_saving"]["product_name"] == "우리SUPER주거래적금"
        assert "reason" in data["deposit_or_saving"]
        
        assert data["annuity"]["product_type"] == "연금저축"
        assert data["fund"]["product_type"] == "펀드"
        
        # Verify service was called with correct user_id
        mock_products_service.get_recommendations.assert_called_once_with(1)
    
    def test_get_recommendations_with_ai_reasons(self, client, mock_products_service):
        """Vector search returns results → Products with AI-generated reasons"""
        mock_recommendations = {
            "deposit_or_saving": {
                "product_id": "prod_001",
                "product_type": "적금",
                "product_name": "테스트 적금",
                "company_name": "테스트은행",
                "benefit": "높은 금리",
                "reason": "고객님의 저축 성향과 목표에 맞는 상품입니다. 안정적인 이자 수익을 기대할 수 있습니다."
            },
            "annuity": None,  # No matching annuity product
            "fund": None      # No matching fund product
        }
        
        mock_products_service.get_recommendations = AsyncMock(
            return_value=mock_recommendations
        )
        
        response = client.get("/api/v1/recommendations/1")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify AI-generated reason exists
        assert "reason" in data["deposit_or_saving"]
        assert len(data["deposit_or_saving"]["reason"]) > 0
        
        # Verify empty recommendations for other types
        assert data["annuity"] is None
        assert data["fund"] is None
    
    def test_get_recommendations_empty_results(self, client, mock_products_service):
        """No matching products → Empty recommendations"""
        mock_recommendations = {
            "deposit_or_saving": None,
            "annuity": None,
            "fund": None
        }
        
        mock_products_service.get_recommendations = AsyncMock(
            return_value=mock_recommendations
        )
        
        response = client.get("/api/v1/recommendations/999")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["deposit_or_saving"] is None
        assert data["annuity"] is None
        assert data["fund"] is None
    
    def test_get_recommendations_user_without_embedding(self, client, mock_products_service):
        """User without embedding → 500 Error"""
        mock_products_service.get_recommendations = AsyncMock(
            side_effect=Exception("User embedding not found")
        )
        
        response = client.get("/api/v1/recommendations/999")
        
        assert response.status_code == 500
        assert "추천 실패" in response.json()["detail"]
    
    def test_get_recommendations_mongodb_error(self, client, mock_products_service):
        """MongoDB connection error → 500 Error"""
        mock_products_service.get_recommendations = AsyncMock(
            side_effect=Exception("MongoDB connection failed")
        )
        
        response = client.get("/api/v1/recommendations/1")
        
        assert response.status_code == 500
        data = response.json()
        assert "추천 실패" in data["detail"]
        assert "문제가 발생하였습니다" in data["detail"]
    
    def test_get_recommendations_vector_search_timeout(self, client, mock_products_service):
        """Vector search timeout → 500 Error"""
        mock_products_service.get_recommendations = AsyncMock(
            side_effect=TimeoutError("Vector search timeout")
        )
        
        response = client.get("/api/v1/recommendations/1")
        
        assert response.status_code == 500
    
    def test_get_recommendations_different_user_ids(self, client, mock_products_service):
        """Test with various user IDs"""
        mock_recommendations = {
            "deposit_or_saving": {"product_id": "prod_001", "product_type": "적금"},
            "annuity": None,
            "fund": None
        }
        
        mock_products_service.get_recommendations = AsyncMock(
            return_value=mock_recommendations
        )
        
        # Test with different user IDs
        for user_id in [1, 10, 100, 1000]:
            response = client.get(f"/api/v1/recommendations/{user_id}")
            assert response.status_code == 200
            
            # Verify service was called with correct user_id
            call_args = mock_products_service.get_recommendations.call_args
            assert call_args[0][0] == user_id
