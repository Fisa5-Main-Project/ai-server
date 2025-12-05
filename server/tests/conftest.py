import pytest
import os
import sys
from unittest.mock import MagicMock

# server/app 모듈을 찾을 수 있도록 경로 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

# --- Heavy Dependencies Mocking (Before Import) ---
# 실제 DB 연결이나 모델 로딩을 방지하기 위해 sys.modules에 Mock 객체를 미리 주입합니다.
mock_vector_store_module = MagicMock()
sys.modules["app.db.vector_store"] = mock_vector_store_module
sys.modules["app.db.vector_store.deposit_vector_store"] = MagicMock()
sys.modules["app.db.vector_store.saving_vector_store"] = MagicMock()
sys.modules["app.db.vector_store.annuity_vector_store"] = MagicMock()
sys.modules["app.db.vector_store.fund_vector_store"] = MagicMock()

mock_graph_module = MagicMock()
sys.modules["app.rag.graphs.product_graph"] = mock_graph_module
# --------------------------------------------------

@pytest.fixture
def mock_vector_store():
    """Vector Store Mocking"""
    mock = MagicMock()
    # 검색 결과 Mocking
    mock.as_retriever.return_value.invoke.return_value = [
        MagicMock(page_content="테스트 문서 내용 1", metadata={"source": "doc1"}),
        MagicMock(page_content="테스트 문서 내용 2", metadata={"source": "doc2"})
    ]
    # 비동기 invoke Mocking
    async def async_invoke(*args, **kwargs):
        return [
            MagicMock(page_content="테스트 문서 내용 1", metadata={"source": "doc1"}),
            MagicMock(page_content="테스트 문서 내용 2", metadata={"source": "doc2"})
        ]
    mock.as_retriever.return_value.ainvoke = async_invoke
    
    return mock

@pytest.fixture
def mock_llm():
    """LLM Mocking"""
    mock = MagicMock()
    mock.invoke.return_value.content = "테스트 답변입니다."
    
    async def async_invoke(*args, **kwargs):
        return MagicMock(content="테스트 답변입니다.")
    
    mock.ainvoke = async_invoke
    return mock
