import pendulum
from airflow.decorators import dag, task
import os

from etl_utils import fetch_fsc_funds, transform_fsc_funds, load_to_mongo

# --- 0. 설정: .env 파일에서 환경 변수 불러오기 ---
FSC_API_KEY = os.getenv("FSC_API_KEY")
MONGO_DB_URL = os.getenv("MONGO_DB_URL")
MONGO_DB_NAME = os.getenv("DB_NAME")

if not all([FSC_API_KEY, MONGO_DB_URL, MONGO_DB_NAME]):
    raise ValueError("필수 환경 변수(FSC_API_KEY, MONGO_DB_URL, DB_NAME)가 설정되지 않았습니다.")

# [DAG] Airflow DAG 정의
@dag(
    dag_id="fsc_fund_standard_code_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="20 3 * * *", # 매일 새벽 3시 20분
    catchup=False,
    tags=["fsc", "fund", "etl", "team_4", "preprocessing"],
)
def fsc_fund_pipeline():
    """[4팀] 금융위원회(data.go.kr) 펀드 정보를 수집/전처리하여 MongoDB에 적재합니다."""

    # Airflow 템플릿 변수 {{ ds_nodash }} (YYYYMMDD)를 Task에 전달
    @task(task_id="extract_fsc_funds")
    def extract(logical_date_str):
        # YYYY-MM-DDTHH:MM:SS...Z -> YYYYMMDD
        target_date = pendulum.parse(logical_date_str).subtract(days=1).format("YYYYMMDD")
        return fetch_fsc_funds(FSC_API_KEY, target_date)

    @task(task_id="transform_fsc_funds")
    def transform(data: list):
        return transform_fsc_funds(data)

    @task(task_id="load_fsc_funds")
    def load(mongo_docs: list):
        return load_to_mongo(MONGO_DB_URL, MONGO_DB_NAME, "products_fsc_fund", mongo_docs, "fund_fsc")

    # Task 순서 정의: E -> T -> L
    # {{ data_interval_start }}는 Airflow의 '논리적 실행 시작 시간' (새벽 2시 실행 시, 어제 날짜)
    extracted_data = extract("{{ data_interval_start }}")
    transformed_data = transform(extracted_data)
    load(transformed_data)

# DAG 실행
fsc_fund_pipeline()