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

# 2. RAG를 위한 Vector Store 컬렉션 정의
# (Airflow가 이 컬렉션들에 데이터를 미리 적재해야 함)
try:
    deposit_saving_collection = db["products_deposit_saving"]
    annuity_collection = db["products_annuity"]
    fund_collection = db["products_funds"] # 또는 products_fund_kvic

    # LangChain VectorStore 객체 생성
    deposit_saving_vector_store = MongoDBAtlasVectorSearch(
        collection=deposit_saving_collection,
        embedding=embeddings,
        index_name="vector_index" # Airflow(rag_vectorize_pipeline.py)에서 생성한 인덱스
    )
    annuity_vector_store = MongoDBAtlasVectorSearch(
        collection=annuity_collection,
        embedding=embeddings,
        index_name="vector_index"
    )
    fund_vector_store = MongoDBAtlasVectorSearch(
        collection=fund_collection,
        embedding=embeddings,
        index_name="vector_index"
    )
    
    # [신규] 사용자 벡터 저장소
    user_collection = db["users_vector"]
    user_vector_store = MongoDBAtlasVectorSearch(
        collection=user_collection,
        embedding=embeddings,
        index_name="vector_index"
    )
    print("LangChain Vector Stores 초기화 완료.")

except Exception as e:
    print(f"Vector Store 초기화 실패: {e}")
    deposit_vector_store = None
    saving_vector_store = None
    annuity_vector_store = None
    fund_vector_store = None
    user_vector_store = None