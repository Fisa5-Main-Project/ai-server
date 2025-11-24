import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
# etl_utils.py 파일에 get_mongo_db_url 함수가 올바르게(f-string, mongodb://) 수정되어 있어야 합니다.
from etl_utils import fetch_fss_data, transform_annuity, load_to_mongo, get_mongo_db_url
import os

# [DAG] Airflow DAG 정의
@dag(
    dag_id="fss_pipeline_annuity",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 3 * * *", # 매일 새벽 3시 
    catchup=False,
    tags=["fss", "annuity", "etl", "team_4", "preprocessing", "embedding"],
)
def fss_annuity_pipeline():
    """[4팀] 금융감독원 '연금저축' 상품을 수집/전처리/임베딩하여 MongoDB에 적재합니다."""

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

    @task(task_id="embed_annuity")
    def embed(load_count: int):
        """Voyage AI를 사용하여 임베딩을 생성하고 MongoDB에 업데이트합니다."""
        import voyageai
        from pymongo import MongoClient
        
        # API 키 가져오기
        try:
            voyage_api_key = Variable.get("VOYAGE_API_KEY")
        except KeyError:
            voyage_api_key = os.getenv("VOYAGE_API_KEY")
        
        if not voyage_api_key:
            print("[annuity] VOYAGE_API_KEY가 없습니다. 임베딩을 건너뜁니다.")
            return 0
        
        # MongoDB 연결
        try:
            mongo_url = get_mongo_db_url()
            db_name = Variable.get("DB_NAME", "financial_products")
        except KeyError:
            db_name = "financial_products"
        
        client = None
        try:
            # MongoDB Atlas SSL 설정
            client = MongoClient(
                mongo_url,
                serverSelectionTimeoutMS=10000,
                tlsAllowInvalidCertificates=True
            )
            db = client[db_name]
            collection = db["products_annuity"]
            
            # rag_text가 있고 embedding이 없는 문서만 조회
            docs_to_embed = list(collection.find({
                "rag_text": {"$exists": True},
                "embedding": {"$exists": False}
            }))
            
            if not docs_to_embed:
                print("[annuity] 임베딩할 문서가 없습니다.")
                return 0
            
            print(f"[annuity] {len(docs_to_embed)}개 문서에 대해 임베딩 생성 시작...")
            
            # Voyage AI 클라이언트 초기화
            vo = voyageai.Client(api_key=voyage_api_key)
            
            # 배치 처리
            batch_size = 128
            embedded_count = 0
            
            for i in range(0, len(docs_to_embed), batch_size):
                batch = docs_to_embed[i:i + batch_size]
                texts = [doc["rag_text"] for doc in batch]
                
                print(f"[annuity] 임베딩 생성 중... ({i+1}-{min(i+batch_size, len(docs_to_embed))}/{len(docs_to_embed)})")
                
                try:
                    result = vo.embed(
                        texts,
                        model="voyage-large-2",
                        input_type="document"
                    )
                    
                    # MongoDB 업데이트
                    for j, embedding in enumerate(result.embeddings):
                        doc_id = batch[j]["_id"]
                        collection.update_one(
                            {"_id": doc_id},
                            {"$set": {"embedding": embedding}}
                        )
                        embedded_count += 1
                        
                except Exception as e:
                    print(f"[annuity] 배치 임베딩 실패: {e}")
                    continue
            
            print(f"[annuity] 임베딩 완료: {embedded_count}개 문서 처리됨.")
            return embedded_count
            
        except Exception as e:
            print(f"[annuity] 임베딩 프로세스 실패: {e}")
            return 0
        finally:
            if client:
                client.close()

    # Task 순서 정의: E -> T -> L -> Embed
    extracted_data = extract()
    transformed_data = transform(extracted_data)
    loaded_count = load(transformed_data)
    embed(loaded_count)

# DAG 실행
fss_annuity_pipeline()