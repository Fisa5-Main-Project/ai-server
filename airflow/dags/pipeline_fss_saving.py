import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
# etl_utils의 get_mongo_db_url이 최신 상태(mongodb://, f-string 적용)인지 확인 필수
from etl_utils import fetch_fss_data, transform_deposit_saving, load_to_mongo, get_mongo_db_url, add_embeddings_to_docs

# [DAG] Airflow DAG 정의
@dag(
    dag_id="fss_pipeline_saving",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="30 3 * * *", # 매일 새벽 3시 정각
    catchup=False,
    tags=["fss", "saving", "etl", "team_4"],
)
def fss_saving_pipeline():
    """[4팀] 금융감독원 '적금' 상품을 수집/전처리하여 MongoDB에 적재합니다."""
    
    @task(task_id="extract_saving")
    def extract():
        # [수정] 변수 로드를 Task 실행 시점으로 이동
        try:
            api_key = Variable.get("FSS_API_KEY")
        except KeyError:
            raise Exception("Airflow Variables에 'FSS_API_KEY'가 없습니다.")

        # 적금 상품 코드: "020000" (예금과 동일한 API 엔드포인트 사용 시 구분 필요)
        # etl_utils 내부 구현에 따라 다르겠지만 보통 적금도 같은 함수나 유사한 로직을 탈 것입니다.
        return fetch_fss_data(api_key, "savingProductsSearch.json", "020000")

    @task(task_id="transform_saving")
    def transform(data: dict):
        # product_type="saving"으로 전달
        return transform_deposit_saving(data, product_type="saving")

    @task(task_id="embed_saving")
    def embed(mongo_docs: list):
        # Voyage AI 임베딩 추가
        return add_embeddings_to_docs(mongo_docs)

    @task(task_id="load_saving")
    def load(mongo_docs: list):
        # [수정] DB 연결 설정을 Task 실행 시점으로 이동
        try:
            mongo_url = get_mongo_db_url()
            db_name = Variable.get("DB_NAME")
        except KeyError:
            db_name = "financial_products" # 기본값

        return load_to_mongo(mongo_url, db_name, "products_saving", mongo_docs, "saving")

    # Task 순서 정의: E -> T -> Embed -> L
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    embedded_data = embed(transformed_data)
    load(embedded_data)

# DAG 실행
fss_saving_pipeline()