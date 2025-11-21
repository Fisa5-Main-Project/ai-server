import pendulum
from airflow.decorators import dag, task


from etl_utils import fetch_fss_data, transform_deposit_saving, load_to_mongo

import os

# --- 0. 설정: .env 파일에서 환경 변수 불러오기 ---
FSS_API_KEY = os.getenv("FSS_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
MONGO_DB_NAME = os.getenv("DB_NAME")

if not all([FSS_API_KEY, MONGO_DB_URL, MONGO_DB_NAME]):
    raise ValueError("필수 환경 변수(FSS_API_KEY, MONGO_DB_URL, DB_NAME)가 설정되지 않았습니다.")

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
        return fetch_fss_data(FSS_API_KEY, "depositProductsSearch.json", "020000")

    @task(task_id="transform_deposit")
    def transform(data: dict):
        return transform_deposit_saving(data, product_type="deposit")

    @task(task_id="load_deposit")
    def load(mongo_docs: list):
        return load_to_mongo(MONGO_DB_URL, MONGO_DB_NAME, "products_deposit", mongo_docs, "deposit")

    # Task 순서 정의: E -> T -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    load(transformed_data)

# DAG 실행
fss_deposit_pipeline()