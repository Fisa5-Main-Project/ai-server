import pendulum
from airflow.decorators import dag, task
from pymongo import MongoClient
from etl_utils import get_mongo_db_url


@dag(
    dag_id="merge_collections_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="10 4 * * *",  
    catchup=False,
    tags=["merge", "maintenance", "team_4"],
)
def merge_collections_pipeline():
    """수집된 데이터를 통합 컬렉션으로 병합합니다."""

    @task(task_id="merge_deposit_saving")
    def merge_deposit_saving():
        """Deposit + Saving → products_deposit_saving"""
        mongo_url = get_mongo_db_url()
        
        with MongoClient(mongo_url) as client:
            db = client["financial_products"]
            
            # 통합 컬렉션
            target = db["products_deposit_saving"]
            
            # Deposit 데이터 Upsert
            deposit_docs = list(db["products_deposit"].find())
            upsert_count = 0
            
            for doc in deposit_docs:
                target.update_one(
                    {"_id": doc["_id"]},
                    {"$set": doc},
                    upsert=True
                )
                upsert_count += 1
            
            print(f"[Deposit] {upsert_count}개 문서 병합")
            
            # Saving 데이터 Upsert
            saving_docs = list(db["products_saving"].find())
            saving_count = 0
            
            for doc in saving_docs:
                target.update_one(
                    {"_id": doc["_id"]},
                    {"$set": doc},
                    upsert=True
                )
                saving_count += 1
            
            print(f"[Saving] {saving_count}개 문서 병합")
            print(f"[Total] {upsert_count + saving_count}개 문서를 products_deposit_saving에 병합")
            
            return upsert_count + saving_count

    @task(task_id="merge_funds")
    def merge_funds():
        """FSC Fund + KVIC Fund → products_funds"""
        mongo_url = get_mongo_db_url()
        
        with MongoClient(mongo_url) as client:
            db = client["financial_products"]
            
            # 통합 컬렉션
            target = db["products_funds"]
            
            # FSC Fund 데이터 Upsert
            fsc_docs = list(db["products_fsc_fund"].find())
            fsc_count = 0
            
            for doc in fsc_docs:
                target.update_one(
                    {"_id": doc["_id"]},
                    {"$set": doc},
                    upsert=True
                )
                fsc_count += 1
            
            print(f"[FSC Fund] {fsc_count}개 문서 병합")
            
            # KVIC Fund 데이터 Upsert
            kvic_docs = list(db["products_fund_kvic"].find())
            kvic_count = 0
            
            for doc in kvic_docs:
                target.update_one(
                    {"_id": doc["_id"]},
                    {"$set": doc},
                    upsert=True
                )
                kvic_count += 1
            
            print(f"[KVIC Fund] {kvic_count}개 문서 병합")
            print(f"[Total] {fsc_count + kvic_count}개 문서를 products_funds에 병합")
            
            return fsc_count + kvic_count

    @task(task_id="log_merge_summary")
    def log_merge_summary(deposit_saving_count: int, funds_count: int):
        """병합 작업 요약 로그"""
        total = deposit_saving_count + funds_count
        print("\n" + "="*60)
        print("컬렉션 병합 완료")
        print("="*60)
        print(f"Deposit + Saving: {deposit_saving_count}개")
        print(f"FSC + KVIC Fund: {funds_count}개")
        print(f"총 병합: {total}개")
        print("="*60)
        return total

    # 실행 순서
    deposit_saving_result = merge_deposit_saving()
    funds_result = merge_funds()
    log_merge_summary(deposit_saving_result, funds_result)


# DAG 인스턴스 생성
merge_collections_pipeline()
