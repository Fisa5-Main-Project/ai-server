import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
# etl_utils.py 파일에 get_mongo_db_url 함수가 올바르게(f-string, mongodb://) 수정되어 있어야 합니다.
from etl_utils import fetch_fss_data, transform_annuity, load_to_mongo, get_mongo_db_url

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
        # [수정] API KEY 조회는 실행 시점(Task 내부)에 수행
        try:
            api_key = Variable.get("FSS_API_KEY")
        except KeyError:
            raise Exception("Airflow Variables에 'FSS_API_KEY'가 없습니다.")
            
        return fetch_fss_data(api_key, "annuitySavingProductsSearch.json", "060000")

    @task(task_id="transform_annuity")
    def transform(data: dict):
        return transform_annuity(data)

    @task(task_id="load_annuity")
    def load(mongo_docs: list):
        # [수정] DB 연결 정보 조회도 실행 시점(Task 내부)에 수행
        try:
            mongo_url = get_mongo_db_url()
            db_name = Variable.get("DB_NAME")
        except KeyError:
            # 변수가 없으면 기본값 설정 (안전장치)
            db_name = "financial_products" 
            
        return load_to_mongo(mongo_url, db_name, "products_annuity", mongo_docs, "annuity")

    # Task 순서 정의: E -> T -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    load(transformed_data)

# DAG 실행
fss_annuity_pipeline()