import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable

from etl_utils import fetch_kvic_funds, transform_kvic_funds, load_to_mongo

# --- 0. 설정: Airflow UI의 Variables에서 값 불러오기 ---
try:
    KVIC_API_KEY = Variable.get("KVIC_API_KEY")
    MONGO_DB_URL = Variable.get("MONGO_DB_URL")
    MONGO_DB_NAME = Variable.get("DB_NAME")
except KeyError:
    raise Exception("Airflow Variables에 KVIC_API_KEY, MONGO_DB_URL, DB_NAME을 등록해야 합니다.")

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