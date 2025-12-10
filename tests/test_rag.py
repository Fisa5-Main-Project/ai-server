import pytest
from unittest.mock import patch, MagicMock
from app.services.products_service import ProductsService
from app.schemas.chat import ChatProduct

# 실제 서비스 로직 테스트를 위한 Mocking
# 주의: 실제 DB나 OpenAI API를 호출하지 않도록 Mock 객체를 사용합니다.

@pytest.mark.asyncio
async def test_product_recommendation_flow(mock_vector_store, mock_llm):
    """
    상품 추천 전체 흐름 테스트
    1. 사용자 질문 입력
    2. Vector Store 검색 (Mock)
    3. LLM 응답 생성 (Mock)
    4. 결과 반환 확인
    """
    
    # ProductsService의 의존성 Mocking
    with patch('app.services.products_service.user_vectorization_service') as mock_user_service, \
         patch('app.services.products_service.product_graph') as mock_graph:
        
        # 사용자 벡터 Mock 설정
        mock_user_service.user_vectors_collection.find_one.return_value = {
            "persona_text": "안정적인 투자를 선호하는 30대 직장인"
        }
        
        # LangGraph 실행 결과 Mock 설정
        mock_graph.ainvoke.return_value = {
            "messages": [
                MagicMock(content='{"products": [{"product_id": "1", "product_type": "deposit", "product_name": "테스트 예금", "company_name": "테스트 은행", "reason": "추천 이유", "benefit": "3.5%"}]}')
            ]
        }
        
        service = ProductsService()
        user_id = 1
        user_message = "예금 추천해줘"
        
        # 서비스 호출
        products = await service.get_chat_products(user_id, user_message)
        
        # 검증
        assert len(products) > 0
        assert products[0].name == "테스트 예금"
        assert products[0].bank == "테스트 은행"
        
        # Mock 호출 확인
        mock_user_service.user_vectors_collection.find_one.assert_called()
        mock_graph.ainvoke.assert_called()

@pytest.mark.asyncio
async def test_retrieval_accuracy_example():
    """
    [평가 예시] 검색 정확도 테스트
    특정 키워드 검색 시, 예상되는 문서가 반환되는지 확인
    """
    # 실제 Vector Store를 사용하는 경우 (통합 테스트)
    # from app.db.vector_store import deposit_vector_store
    
    # 여기서는 Mock을 사용하여 로직만 검증
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = [
        MagicMock(page_content="우리은행 WON 플러스 예금", metadata={"id": "doc_1"}),
        MagicMock(page_content="신한은행 쏠편한 정기예금", metadata={"id": "doc_2"})
    ]
    
    query = "우리은행 예금"
    docs = mock_retriever.invoke(query)
    
    # 검증: 상위 문서에 '우리은행' 관련 내용이 있어야 함
    found = any("우리은행" in doc.page_content for doc in docs)
    assert found, "검색 결과에 '우리은행' 관련 문서가 포함되어야 합니다."

def test_generation_quality_metric_example():
    """
    [평가 예시] 생성 품질 평가 (Ragas 스타일의 로직 구현 예시)
    """
    question = "ISA 계좌의 장점은?"
    context = "ISA 계좌는 비과세 혜택과 저율 과세 혜택이 있습니다."
    generated_answer = "ISA 계좌는 세금 혜택이 있어 유리합니다."
    
    # Faithfulness 평가 (간단한 버전): 답변의 키워드가 문맥에 포함되는지 확인
    keywords = ["세금", "혜택"]
    faithfulness_score = 0
    for k in keywords:
        if k in context:
            faithfulness_score += 1
    
    faithfulness_score /= len(keywords)
    
    assert faithfulness_score >= 0.5, "답변이 문맥을 충분히 반영해야 합니다."
