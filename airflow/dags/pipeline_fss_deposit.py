import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
# etl_utils의 get_mongo_db_url 함수가 최신 버전(mongodb:// 및 f-string 적용)인지 꼭 확인하세요.
from etl_utils import fetch_fss_data, load_to_mongo, get_mongo_db_url, transform_deposit_saving

# [DAG] Airflow DAG 정의
@dag(
    dag_id="fss_pipeline_deposit",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 3 * * *", # 매일 새벽 3시
    catchup=False,
    tags=["fss", "deposit", "etl", "team_4"],
)
def fss_deposit_pipeline():
    """[4팀] 금융감독원 '정기예금' 상품을 수집/전처리하여 MongoDB에 적재합니다."""
    
    @task(task_id="extract_deposit")
    def extract():
        # [수정] API 키 조회를 Task 실행 시점으로 이동
        try:
            api_key = Variable.get("FSS_API_KEY")
        except KeyError:
            raise Exception("Airflow Variables에 'FSS_API_KEY'가 없습니다.")
            
        return fetch_fss_data(api_key, "depositProductsSearch.json", "020000")

    @task(task_id="transform_deposit")
    def transform(data: dict):
        return transform_deposit_saving(data, product_type="deposit")

    @task(task_id="load_deposit")
    def load(mongo_docs: list):
        # [수정] DB 연결 정보 조회를 Task 실행 시점으로 이동
        try:
            mongo_url = get_mongo_db_url()
            db_name = Variable.get("DB_NAME")
        except KeyError:
            db_name = "financial_products" # 기본값 fallback
            
        return load_to_mongo(mongo_url, db_name, "products_deposit", mongo_docs, "deposit")

    # Task 순서 정의: E -> T -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    load(transformed_data)

# DAG 실행
fss_deposit_pipeline()