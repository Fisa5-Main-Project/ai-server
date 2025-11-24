import pendulum
from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from pymongo import MongoClient
from etl_utils import add_embeddings_to_docs, get_mongo_db_url

@dag(
    dag_id="embedding_backfill_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 5 * * *",  
    catchup=False,
    tags=["embedding", "backfill", "team_4"],
)
def embedding_backfill_pipeline():
    """모든 컬렉션에서 임베딩이 누락된 문서를 찾아 임베딩을 추가합니다."""

    @task(task_id="backfill_fsc_fund_embeddings")
    def backfill_fsc_fund():
        """FSC 펀드 임베딩 보완"""
        mongo_url = get_mongo_db_url()
        client = MongoClient(mongo_url)
        db = client["financial_products"]
        collection = db["products_fsc_fund"]
        
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        print(f"[FSC Fund] 임베딩 누락 문서: {len(docs_without_embedding)}개")
        
        if not docs_without_embedding:
            client.close()
            return 0
        
        # 배치 처리
        batch_size = 50
        total_processed = 0
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
            
            for doc in embedded_docs:
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": doc["embedding"]}}
                )
                total_processed += 1
        
        client.close()
        print(f"[FSC Fund] 임베딩 추가 완료: {total_processed}개")
        return total_processed

    @task(task_id="backfill_deposit_embeddings")
    def backfill_deposit():
        """예금 임베딩 보완"""
        mongo_url = get_mongo_db_url()
        client = MongoClient(mongo_url)
        db = client["financial_products"]
        collection = db["products_deposit"]
        
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        print(f"[Deposit] 임베딩 누락 문서: {len(docs_without_embedding)}개")
        
        if not docs_without_embedding:
            client.close()
            return 0
        
        batch_size = 50
        total_processed = 0
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
            
            for doc in embedded_docs:
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": doc["embedding"]}}
                )
                total_processed += 1
        
        client.close()
        print(f"[Deposit] 임베딩 추가 완료: {total_processed}개")
        return total_processed

    @task(task_id="backfill_saving_embeddings")
    def backfill_saving():
        """적금 임베딩 보완"""
        mongo_url = get_mongo_db_url()
        client = MongoClient(mongo_url)
        db = client["financial_products"]
        collection = db["products_saving"]
        
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        print(f"[Saving] 임베딩 누락 문서: {len(docs_without_embedding)}개")
        
        if not docs_without_embedding:
            client.close()
            return 0
        
        batch_size = 50
        total_processed = 0
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
            
            for doc in embedded_docs:
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": doc["embedding"]}}
                )
                total_processed += 1
        
        client.close()
        print(f"[Saving] 임베딩 추가 완료: {total_processed}개")
        return total_processed

    @task(task_id="backfill_annuity_embeddings")
    def backfill_annuity():
        """연금저축 임베딩 보완"""
        mongo_url = get_mongo_db_url()
        client = MongoClient(mongo_url)
        db = client["financial_products"]
        collection = db["products_annuity"]
        
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        print(f"[Annuity] 임베딩 누락 문서: {len(docs_without_embedding)}개")
        
        if not docs_without_embedding:
            client.close()
            return 0
        
        batch_size = 50
        total_processed = 0
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
            
            for doc in embedded_docs:
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": doc["embedding"]}}
                )
                total_processed += 1
        
        client.close()
        print(f"[Annuity] 임베딩 추가 완료: {total_processed}개")
        return total_processed

    @task(task_id="backfill_kvic_fund_embeddings")
    def backfill_kvic_fund():
        """KVIC 펀드 임베딩 보완"""
        mongo_url = get_mongo_db_url()
        client = MongoClient(mongo_url)
        db = client["financial_products"]
        collection = db["products_fund_kvic"]
        
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        print(f"[KVIC Fund] 임베딩 누락 문서: {len(docs_without_embedding)}개")
        
        if not docs_without_embedding:
            client.close()
            return 0
        
        batch_size = 50
        total_processed = 0
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
            
            for doc in embedded_docs:
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": doc["embedding"]}}
                )
                total_processed += 1
        
        client.close()
        print(f"[KVIC Fund] 임베딩 추가 완료: {total_processed}개")
        return total_processed

    # 모든 컬렉션 병렬 처리
    backfill_fsc_fund()
    backfill_deposit()
    backfill_saving()
    backfill_annuity()
    backfill_kvic_fund()

# DAG 인스턴스 생성
embedding_backfill_pipeline()
