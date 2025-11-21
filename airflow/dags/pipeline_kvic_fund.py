import pendulum
from airflow.decorators import dag, task
import os

from etl_utils import fetch_kvic_funds, transform_kvic_funds, load_to_mongo

# --- 0. 설정: .env 파일에서 환경 변수 불러오기 ---
KVIC_API_KEY = os.getenv("KVIC_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
MONGO_DB_NAME = os.getenv("DB_NAME")

if not all([KVIC_API_KEY, MONGO_DB_URL, MONGO_DB_NAME]):
    raise ValueError("필수 환경 변수(KVIC_API_KEY, MONGO_DB_URL, DB_NAME)가 설정되지 않았습니다.")

# [DAG] Airflow DAG 정의
@dag(
    dag_id="kvic_fund_etl_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="15 3 * * *", # 매일 새벽 3시 15분
    catchup=False,
    tags=["kvic", "fund", "etl", "team_4", "preprocessing"],
)
def kvic_fund_pipeline():
    """[4팀] 한국벤처투자(KVIC) 펀드를 수집/전처리하여 MongoDB에 적재합니다."""

    @task(task_id="extract_kvic_funds")
    def extract():
        return fetch_kvic_funds(KVIC_API_KEY)

    @task(task_id="transform_kvic_funds")
    def transform(data: list):
        return transform_kvic_funds(data)

    @task(task_id="load_kvic_funds")
    def load(mongo_docs: list):
        return load_to_mongo(MONGO_DB_URL, MONGO_DB_NAME, "products_fund_kvic", mongo_docs, "fund_kvic")

    # Task 순서 정의: E -> T -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    load(transformed_data)

# DAG 실행
kvic_fund_pipeline()