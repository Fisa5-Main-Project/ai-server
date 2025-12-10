"""
Shared pytest fixtures and configuration for AI server API tests
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from bson import ObjectId


@pytest.fixture
def client():
    """FastAPI TestClient instance"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_mongo_db():
    """Mocked MongoDB database"""
    mock_db = MagicMock()
    
    # Mock collections
    mock_db.chat_history = MagicMock()
    mock_db.chat_logs = MagicMock()
    mock_db.user_embeddings = MagicMock()
    mock_db.financial_products = MagicMock()
    
    return mock_db


@pytest.fixture
def mock_mysql_engine():
    """Mocked MySQL engine"""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    return mock_engine


@pytest.fixture
def sample_user_data():
    """Sample user data for tests"""
    return {
        "user_id": 1,
        "name": "테스트사용자",
        "login_id": "test_user",
        "age": 30,
        "occupation": "직장인",
        "annual_income": 50000000,
        "assets": 100000000,
        "liabilities": 20000000
    }


@pytest.fixture
def sample_chat_history():
    """Sample chat history data"""
    return [
        {
            "_id": ObjectId(),
            "user_id": 1,
            "session_id": "test_session_1",
            "role": "user",
            "content": "안녕하세요",
            "timestamp": datetime(2024, 12, 1, 10, 0, 0)
        },
        {
            "_id": ObjectId(),
            "user_id": 1,
            "session_id": "test_session_1",
            "role": "assistant",
            "content": "안녕하세요! 무엇을 도와드릴까요?",
            "timestamp": datetime(2024, 12, 1, 10, 0, 5)
        },
        {
            "_id": ObjectId(),
            "user_id": 1,
            "session_id": "test_session_1",
            "role": "user",
            "content": "적금 추천해주세요",
            "timestamp": datetime(2024, 12, 1, 10, 1, 0)
        }
    ]


@pytest.fixture
def sample_products():
    """Sample financial product data"""
    return [
        {
            "_id": str(ObjectId()),
            "product_type": "적금",
            "product_name": "우리SUPER주거래적금",
            "company_name": "우리은행",
            "interest_rate": 3.55,
            "benefit": "최고 연 3.55%",
            "description": "주거래 고객 우대 적금",
            "embedding": [0.1] * 768  # Mock embedding vector
        },
        {
            "_id": str(ObjectId()),
            "product_type": "연금저축",
            "product_name": "KB Star 연금저축",
            "company_name": "KB국민은행",
            "interest_rate": 4.0,
            "benefit": "세액공제 혜택",
            "description": "안정적인 노후 준비",
            "embedding": [0.2] * 768
        },
        {
            "_id": str(ObjectId()),
            "product_type": "펀드",
            "product_name": "삼성 글로벌 성장 펀드",
            "company_name": "삼성자산운용",
            "return_rate": 8.5,
            "benefit": "글로벌 분산투자",
            "description": "해외 우량주 투자",
            "embedding": [0.3] * 768
        }
    ]


@pytest.fixture
def sample_user_embedding():
    """Sample user embedding data"""
    return {
        "user_id": 1,
        "persona_text": "30대 직장인으로 연봉 5천만원, 자산 1억원을 보유하고 있습니다.",
        "embedding": [0.15] * 768,
        "created_at": datetime(2024, 12, 1, 9, 0, 0),
        "updated_at": datetime(2024, 12, 1, 9, 0, 0)
    }


@pytest.fixture
def sample_feedback_data():
    """Sample feedback data"""
    return [
        {
            "_id": ObjectId(),
            "user_id": 1,
            "session_id": "test_session_1",
            "message_id": "msg_001",
            "feedback": "like",
            "product_id": "prod_001",
            "timestamp": datetime(2024, 12, 1, 10, 5, 0)
        },
        {
            "_id": ObjectId(),
            "user_id": 1,
            "session_id": "test_session_1",
            "message_id": "msg_002",
            "feedback": "dislike",
            "product_id": None,
            "timestamp": datetime(2024, 12, 1, 10, 10, 0)
        }
    ]


@pytest.fixture
def mock_chat_service():
    """Mocked chat service"""
    with patch('app.api.v1.endpoints.chat.chat_service') as mock:
        yield mock


@pytest.fixture
def mock_products_service():
    """Mocked products service"""
    with patch('app.api.v1.endpoints.recommend.products_service') as mock:
        yield mock


@pytest.fixture
def mock_user_vectorization_service():
    """Mocked user vectorization service"""
    with patch('app.api.v1.endpoints.vectorize.user_vectorization_service') as mock:
        yield mock


@pytest.fixture
def mock_admin_service():
    """Mocked admin service"""
    with patch('app.api.v1.endpoints.admin.admin_service') as mock:
        yield mock
