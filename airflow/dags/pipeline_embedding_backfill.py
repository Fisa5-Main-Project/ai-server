import pendulum
from airflow.decorators import dag, task
from pymongo import MongoClient, UpdateOne
from etl_utils import add_embeddings_to_docs, get_mongo_db_url


def backfill_collection_embeddings(collection_name: str, display_name: str) -> int:
    """
    특정 컬렉션의 임베딩이 누락된 문서를 찾아 임베딩을 추가하는 헬퍼 함수
    
    Args:
        collection_name: MongoDB 컬렉션 이름
        display_name: 로그 출력용 표시 이름
    
    Returns:
        처리된 문서 수
    """
    mongo_url = get_mongo_db_url()
    total_processed = 0
    
    with MongoClient(mongo_url) as client:
        db = client["financial_products"]
        collection = db[collection_name]
        
        # embedding 필드가 없는 문서 조회
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        print(f"[{display_name}] 임베딩 누락 문서: {len(docs_without_embedding)}개")
        
        if not docs_without_embedding:
            return 0
        
        # 배치 처리
        batch_size = 50
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
            
            # Bulk write로 성능 개선
            operations = [
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": doc["embedding"]}}
                ) for doc in embedded_docs
            ]
            
            if operations:
                result = collection.bulk_write(operations)
                total_processed += result.modified_count
        
        print(f"[{display_name}] 임베딩 추가 완료: {total_processed}개")
    
    return total_processed


@dag(
    dag_id="embedding_backfill_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 4 * * *",  
    catchup=False,
    tags=["embedding", "backfill", "team_4"],
)
def embedding_backfill_pipeline():
    """모든 컬렉션에서 임베딩이 누락된 문서를 찾아 임베딩을 추가합니다."""

    @task(task_id="backfill_fsc_fund_embeddings")
    def backfill_fsc_fund():
        """FSC 펀드 임베딩 보완"""
        return backfill_collection_embeddings("products_fsc_fund", "FSC Fund")

    @task(task_id="backfill_deposit_embeddings")
    def backfill_deposit():
        """예금 임베딩 보완"""
        return backfill_collection_embeddings("products_deposit", "Deposit")

    @task(task_id="backfill_saving_embeddings")
    def backfill_saving():
        """적금 임베딩 보완"""
        return backfill_collection_embeddings("products_saving", "Saving")

    @task(task_id="backfill_annuity_embeddings")
    def backfill_annuity():
        """연금저축 임베딩 보완"""
        return backfill_collection_embeddings("products_annuity", "Annuity")

    @task(task_id="backfill_kvic_fund_embeddings")
    def backfill_kvic_fund():
        """KVIC 펀드 임베딩 보완"""
        return backfill_collection_embeddings("products_fund_kvic", "KVIC Fund")

    # 모든 컬렉션 병렬 처리
    backfill_fsc_fund()
    backfill_deposit()
    backfill_saving()
    backfill_annuity()
    backfill_kvic_fund()


# DAG 인스턴스 생성
embedding_backfill_pipeline()
