import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
import os

from etl_utils import fetch_fss_data, transform_annuity, load_to_mongo

# --- 0. 설정: Airflow UI의 Variables에서 값 불러오기 ---
import urllib.parse

# .env 파일이나 환경변수에서 가져옴
username = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
password = os.getenv("MONGO_INITDB_ROOT_PASSWORD") 

# 비밀번호에 '@', ':', '/' 같은 문자가 있으면 에러가 나므로 인코딩 필수
encoded_user = urllib.parse.quote_plus(username)
encoded_pwd = urllib.parse.quote_plus(password)

# Docker Compose의 service name이 'mongo'라고 가정
host = "mongo"
port = "27017"

# ?authSource=admin 은 루트 계정이 admin DB에 생성되기 때문에 붙여주는 게 좋습니다.
MONGO_DB_URL = f"mongodb://{encoded_user}:{encoded_pwd}@{host}:{port}/?authSource=admin"
try:
    FSS_API_KEY = Variable.get("FSS_API_KEY")
    # MONGO_DB_URL = Variable.get("MONGO_DB_URL")
    MONGO_DB_NAME = Variable.get("DB_NAME")
except KeyError:
    raise Exception("Airflow Variables에 FSS_API_KEY, MONGO_DB_URL, DB_NAME을 등록해야 합니다.")

# [DAG] Airflow DAG 정의
@dag(
    dag_id="fss_pipeline_annuity",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 3 * * *", # 매일 새벽 3시 
    catchup=False,
    tags=["fss", "annuity", "etl", "team_4", "preprocessing"],
)
def fss_annuity_pipeline():
    """[4팀] 금융감독원 '연금저축' 상품을 수집/전처리하여 MongoDB에 적재합니다."""

    @task(task_id="extract_annuity")
    def extract():
        return fetch_fss_data(FSS_API_KEY, "annuitySavingProductsSearch.json", "060000")

    @task(task_id="transform_annuity")
    def transform(data: dict):
        return transform_annuity(data)

    @task(task_id="load_annuity")
    def load(mongo_docs: list):
        return load_to_mongo(MONGO_DB_URL, MONGO_DB_NAME, "products_annuity", mongo_docs, "annuity")

    # Task 순서 정의: E -> T -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    load(transformed_data)

# DAG 실행
fss_annuity_pipeline()