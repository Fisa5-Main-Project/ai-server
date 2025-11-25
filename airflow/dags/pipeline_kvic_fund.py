import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
# etl_utils의 get_mongo_db_url 함수가 최신 버전(f-string, mongodb://)인지 확인 필수
from etl_utils import fetch_kvic_funds, transform_kvic_funds, load_to_mongo, get_mongo_db_url, add_embeddings_to_docs

# [DAG] Airflow DAG 정의
@dag(
    dag_id="kvic_fund_etl_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="40 3 * * *", 
    catchup=False,
    tags=["kvic", "fund", "etl", "team_4", "preprocessing"],
)
def kvic_fund_pipeline():
    """[4팀] 한국벤처투자(KVIC) 펀드를 수집/전처리하여 MongoDB에 적재합니다."""

    @task(task_id="extract_kvic_funds")
    def extract():
        # [수정] API Key 호출을 Task 실행 시점으로 이동
        try:
            api_key = Variable.get("KVIC_API_KEY")
        except KeyError:
            raise Exception("Airflow Variables에 'KVIC_API_KEY'가 없습니다.")
            
        return fetch_kvic_funds(api_key)

    @task(task_id="transform_kvic_funds")
    def transform(data: list):
        return transform_kvic_funds(data)

    @task(task_id="embed_kvic_funds")
    def embed(mongo_docs: list):
        # Voyage AI 임베딩 추가
        return add_embeddings_to_docs(mongo_docs)

    @task(task_id="load_kvic_funds")
    def load(mongo_docs: list):
        # [수정] DB 연결 설정을 Task 실행 시점으로 이동
        try:
            mongo_url = get_mongo_db_url()
            db_name = Variable.get("DB_NAME")
        except KeyError:
            db_name = "financial_products" # 기본값

        return load_to_mongo(mongo_url, db_name, "products_fund_kvic", mongo_docs, "fund_kvic")

    # Task 순서 정의: E -> T -> Embed -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    embedded_data = embed(transformed_data)
    load(embedded_data)

# DAG 실행
kvic_fund_pipeline()