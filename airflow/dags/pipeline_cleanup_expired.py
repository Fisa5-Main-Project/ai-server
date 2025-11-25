import pendulum
from airflow.decorators import dag, task
from pymongo import MongoClient
from etl_utils import get_mongo_db_url
from datetime import datetime


@dag(
    dag_id="cleanup_expired_products_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="50 3 * * *",  
    catchup=False,
    tags=["cleanup", "maintenance", "team_4"],
)
def cleanup_expired_products_pipeline():
    """만료된 금융상품을 자동으로 삭제합니다 (명확한 만료 정보가 있는 경우만)."""

    @task(task_id="cleanup_kvic_funds")
    def cleanup_kvic_funds():
        """KVIC 펀드: exp(만료일)이 지난 펀드 삭제"""
        mongo_url = get_mongo_db_url()
        
        with MongoClient(mongo_url) as client:
            db = client["financial_products"]
            collection = db["products_fund_kvic"]
            
            # 현재 날짜 (YYYY-MM-DD 형식)
            today = datetime.now().strftime("%Y-%m-%d")
            
            # exp 필드가 존재하고, 현재 날짜보다 이전인 펀드 삭제
            result = collection.delete_many({
                "exp": {"$exists": True, "$lt": today}
            })
            
            print(f"[KVIC Fund] 만료된 펀드 삭제: {result.deleted_count}개")
            return result.deleted_count

    @task(task_id="cleanup_fss_products")
    def cleanup_fss_products():
        """FSS 상품: dcls_end_day(공시종료일)이 지난 상품 삭제"""
        mongo_url = get_mongo_db_url()
        total_deleted = 0
        
        with MongoClient(mongo_url) as client:
            db = client["financial_products"]
            
            # 현재 날짜 (YYYYMMDD 형식)
            today = datetime.now().strftime("%Y%m%d")
            
            for collection_name in ["products_deposit", "products_saving", "products_annuity"]:
                collection = db[collection_name]
                
                # dcls_end_day가 존재하고 (null이 아니고), 현재 날짜보다 이전인 상품 삭제
                result = collection.delete_many({
                    "dcls_end_day": {
                        "$exists": True,
                        "$ne": None,
                        "$lt": today
                    }
                })
                
                print(f"[{collection_name}] 만료된 상품 삭제: {result.deleted_count}개")
                total_deleted += result.deleted_count
        
        print(f"[FSS 전체] 총 {total_deleted}개 만료 상품 삭제")
        return total_deleted

    @task(task_id="log_cleanup_summary")
    def log_cleanup_summary(kvic_count: int, fss_count: int):
        """정리 작업 요약 로그"""
        total = kvic_count + fss_count
        print("\n" + "="*60)
        print("만료 상품 정리 완료")
        print("="*60)
        print(f"KVIC Fund (exp 기준): {kvic_count}개")
        print(f"FSS 상품 (dcls_end_day 기준): {fss_count}개")
        print(f"FSC Fund: 만료 정보 없음 - 삭제 안 함")
        print(f"총 삭제: {total}개")
        print("="*60)
        return total

    # 실행 순서
    kvic_result = cleanup_kvic_funds()
    fss_result = cleanup_fss_products()
    log_cleanup_summary(kvic_result, fss_result)


# DAG 인스턴스 생성
cleanup_expired_products_pipeline()
