from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from app.core.config import settings
from app.services.embedding import embeddings # 임베딩 모델 로드

# 1. MongoDB 클라이언트
try:
    mongo_client = MongoClient(settings.MONGO_DB_URL, serverSelectionTimeoutMS=5000)
    mongo_client.server_info() # 연결 테스트
    db = mongo_client[settings.MONGO_DB_NAME]
    print(f"MongoDB ({settings.MONGO_DB_NAME}) 연결 성공.")
except Exception as e:
    print(f"MongoDB 연결 실패: {e}")
    db = None

# 2. RAG를 위한 Vector Store 컬렉션 정의 (통합 컬렉션 사용)
try:
    # 통합 컬렉션
    deposit_saving_collection = db["products_deposit_saving"]
    annuity_collection = db["products_annuity"]
    funds_collection = db["products_funds"]

    # LangChain VectorStore 객체 생성
    # Deposit & Saving (통합)
    deposit_vector_store = MongoDBAtlasVectorSearch(
        collection=deposit_saving_collection,
        embedding=embeddings,
        index_name="deposit_saving_vector_index",
        text_key="rag_text",
        embedding_key="embedding"
    )
    
    # Saving은 deposit과 같은 컬렉션 사용 (product_type 필터로 구분)
    saving_vector_store = MongoDBAtlasVectorSearch(
        collection=deposit_saving_collection,
        embedding=embeddings,
        index_name="deposit_saving_vector_index",
        text_key="rag_text",
        embedding_key="embedding"
    )
    
    # Annuity
    annuity_vector_store = MongoDBAtlasVectorSearch(
        collection=annuity_collection,
        embedding=embeddings,
        index_name="annuity_vector_index",
        text_key="rag_text",
        embedding_key="embedding"
    )
    
    # Funds (FSC + KVIC 통합)
    fund_vector_store = MongoDBAtlasVectorSearch(
        collection=funds_collection,
        embedding=embeddings,
        index_name="fund_vector_index",
        text_key="rag_text",
        embedding_key="embedding"
    )
    
    print("LangChain Vector Stores 초기화 완료.")
    print(f"  - Deposit/Saving: {deposit_saving_collection.count_documents({})}개 문서")
    print(f"  - Annuity: {annuity_collection.count_documents({})}개 문서")
    print(f"  - Funds: {funds_collection.count_documents({})}개 문서")

except Exception as e:
    print(f"Vector Store 초기화 실패: {e}")
    deposit_vector_store = None
    saving_vector_store = None
    annuity_vector_store = None
    fund_vector_store = None