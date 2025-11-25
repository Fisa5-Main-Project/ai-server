import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
from etl_utils import fetch_fsc_funds, transform_fsc_funds, load_to_mongo, get_mongo_db_url, add_embeddings_to_docs

# [DAG] Airflow DAG 정의
@dag(
    dag_id="fsc_fund_standard_code_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="20 3 * * *", 
    catchup=False,
    tags=["fsc", "fund", "etl", "team_4", "preprocessing"],
)
def fsc_fund_pipeline():
    """[4팀] 금융위원회(data.go.kr) 펀드 정보를 수집/전처리하여 MongoDB에 적재합니다."""

    # --- Extract Task ---
    @task(task_id="extract_fsc_funds")
    def extract(logical_date_str):
        # [수정] Variable.get을 Task 안으로 이동 (성능 최적화)
        try:
            api_key = Variable.get("FSC_API_KEY")
        except KeyError:
            raise Exception("Airflow Admin -> Variables에 'FSC_API_KEY'를 등록해주세요.")

        # YYYY-MM-DD... -> YYYYMMDD (현재 날짜 데이터 조회)
        target_date = pendulum.parse(logical_date_str).format("YYYYMMDD")
        return fetch_fsc_funds(api_key, target_date)

    # --- Transform Task ---
    @task(task_id="transform_fsc_funds")
    def transform(data: list):
        return transform_fsc_funds(data)

    # --- Embed Task ---
    @task(task_id="embed_fsc_funds")
    def embed(mongo_docs: list):
        # Gemini 임베딩 추가
        return add_embeddings_to_docs(mongo_docs)

    # --- Load Task ---
    @task(task_id="load_fsc_funds")
    def load(mongo_docs: list):
        # [수정] DB 연결 설정도 Task 안에서 수행
        try:
            db_name = Variable.get("DB_NAME") # 예: financial_products
        except KeyError:
            # 변수가 없으면 기본값 사용
            db_name = "financial_products"
            
        mongo_url = get_mongo_db_url()
        
        # 로깅 (비번 마스킹 후 출력 권장)
        print(f"Connecting to DB Name: {db_name}")

        return load_to_mongo(mongo_url, db_name, "products_fsc_fund", mongo_docs, "fund_fsc")

    # --- Pipeline 실행 흐름 ---
    # logical_date_str를 인자로 전달
    extracted_data = extract("{{ data_interval_start }}")
    transformed_data = transform(extracted_data)
    embedded_data = embed(transformed_data)
    load(embedded_data)

# DAG 인스턴스 생성
fsc_fund_pipeline()