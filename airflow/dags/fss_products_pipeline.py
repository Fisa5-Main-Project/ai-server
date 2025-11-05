import pendulum
import requests
from pymongo import MongoClient
from airflow.decorators import dag, task
from airflow.models.variable import Variable

# --- 0. 설정: Airflow UI의 Variables에서 값 불러오기 ---
try:
    FSS_API_KEY = Variable.get("FSS_API_KEY")
    MONGO_DB_URL = Variable.get("MONGO_DB_URL")
    MONGO_DB_NAME = Variable.get("DB_NAME")
except KeyError:
    # Airflow UI에 변수가 등록되지 않았을 경우 exception
    raise Exception("Airflow Variables에 FSS_API_KEY, MONGO_DB_URL, DB_NAME을 등록해야 합니다.")

# -------------------------------------------------------------------
# [E] Extract: API 호출 공통 함수
# -------------------------------------------------------------------
def fetch_fss_data(api_endpoint: str, top_fin_grp_no: str):
    """(버그 수정) 금감원 API를 호출하여 '모든 페이지'를 수집합니다."""
    print(f"[{api_endpoint}] 데이터 추출 시작...")
    base_url = "http://finlife.fss.or.kr/finlifeapi/"
    url = f"{base_url}{api_endpoint}"
    
    all_base_list = []
    all_option_list = []
    page_no = 1
    max_page_no = 1 # 1페이지 호출 후 실제 값으로 덮어쓰임
    
    while page_no <= max_page_no:
        params = {
            "auth": FSS_API_KEY,
            "topFinGrpNo": top_fin_grp_no,
            "pageNo": str(page_no)
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status() # 200 OK가 아니면 예외 발생
            data = response.json()
            result = data["result"]
            
            if result.get("err_cd") != "000":
                print(f"API 오류 (Page {page_no}): {result.get('err_msg')}")
                break # 오류 발생 시 중단

            all_base_list.extend(result.get("baseList", []))
            all_option_list.extend(result.get("optionList", []))
            
            max_page_no = int(result.get("max_page_no", 1)) # (중요) 최대 페이지 업데이트
            print(f"페이지 {page_no}/{max_page_no} 수집 완료...")
            page_no += 1 # 다음 페이지로
            
        except requests.exceptions.RequestException as e:
            print(f"API 호출 실패 (Page {page_no}): {e}")
            raise # Airflow가 이 Task를 'failed'로 처리하도록 예외 발생
            
    print(f"[{api_endpoint}] 추출 완료: 총 {len(all_base_list)}개 상품")
    return {"base_list": all_base_list, "option_list": all_option_list}

# -------------------------------------------------------------------
# [T+L] Transform & Load: 변환 및 적재 공통 함수
# -------------------------------------------------------------------
def transform_and_load_mongo(product_type: str, collection_name: str, data: dict):
    """
    (LangChain 제거) 추출된 데이터를 RAG용 텍스트로 변환하고
    Pymongo를 사용해 MongoDB에 적재(Upsert)합니다.
    """
    base_list = data["base_list"]
    option_list = data["option_list"]
    
    if not base_list:
        print(f"[{product_type}] 변환/적재할 데이터가 없습니다.")
        return 0

    mongo_docs_to_upsert = []
    for base_product in base_list:
        product_code = base_product["fin_prdt_cd"]
        company_no = base_product["fin_co_no"]
        
        options = [
            opt for opt in option_list 
            if opt["fin_prdt_cd"] == product_code and opt["fin_co_no"] == company_no
        ]
        
        # RAG AI가 검색할 통합 텍스트 필드 ('rag_text')
        rag_text = (
            f"상품유형: {product_type}. "
            f"상품명: {base_product.get('fin_prdt_nm', '')}. "
            f"은행: {base_product.get('kor_co_nm', '')}. "
            f"가입 대상: {base_product.get('join_member', '')}. "
            f"가입 방법: {base_product.get('join_way', '')}. "
            f"우대 조건: {base_product.get('spcl_cnd', '없음')}. "
            f"기타 사항: {base_product.get('etc_note', '없음')}. "
        )
        for opt in options:
            rag_text += f"기간 {opt.get('save_trm')}개월: 최고 {opt.get('intr_rate2', 0)}% (기본 {opt.get('intr_rate', 0)}%). "
        
        mongo_doc = base_product.copy()
        mongo_doc["product_type"] = product_type
        mongo_doc["options"] = options
        mongo_doc["rag_text"] = rag_text # AI 서버가 임베딩할 텍스트
        mongo_doc["_id"] = f"{company_no}_{product_code}" # 고유 ID
        
        mongo_docs_to_upsert.append(mongo_doc)

    if not mongo_docs_to_upsert:
        print(f"[{product_type}] MongoDB에 적재할 문서가 없습니다.")
        return 0
        
    try:
        client = MongoClient(MONGO_DB_URL, serverSelectionTimeoutMS=5000)
        client.server_info() # DB 연결 테스트
        db = client[MONGO_DB_NAME]
        collection = db[collection_name] # <--- 인자로 받은 컬렉션 이름 사용
        
        print(f"[{product_type}] MongoDB ({MONGO_DB_NAME}.{collection_name})에 {len(mongo_docs_to_upsert)}개 문서 적재 (Upsert) 시작...")
        
        # (중요) Upsert 방식: 매일 실행해도 중복되지 않음
        upsert_count = 0
        for doc in mongo_docs_to_upsert:
            collection.update_one(
                {"_id": doc["_id"]}, # 필터
                {"$set": doc},       # 덮어쓰기
                upsert=True          # 없으면 삽입
            )
            upsert_count += 1
            
        print(f"[{product_type}] 적재 완료: {upsert_count}개 문서 처리됨.")
        return upsert_count
        
    except Exception as e:
        print(f"[{product_type}] MongoDB 적재 실패: {e}")
        raise
    finally:
        if client:
            client.close()

# -------------------------------------------------------------------
# [Task] Airflow Task 정의
# -------------------------------------------------------------------
@task(task_id="etl_deposit_products")
def etl_deposit():
    """Task 1: 정기예금 수집 및 'products_deposit' 컬렉션에 적재"""
    data = fetch_fss_data("depositProductsSearch.json", "020000")
    count = transform_and_load_mongo(
        product_type="deposit", 
        collection_name="products_deposit", # 개별 컬렉션
        data=data
    )
    return f"Deposit ETL Complete: {count} docs"

@task(task_id="etl_saving_products")
def etl_saving():
    """Task 2: 적금 수집 및 'products_saving' 컬렉션에 적재"""
    data = fetch_fss_data("savingProductsSearch.json", "020000")
    count = transform_and_load_mongo(
        product_type="saving", 
        collection_name="products_saving", # 개별 컬렉션
        data=data
    )
    return f"Saving ETL Complete: {count} docs"

@task(task_id="etl_annuity_products")
def etl_annuity():
    """Task 3: 연금저축 수집 및 'products_annuity' 컬렉션에 적재"""
    data = fetch_fss_data("annuitySavingProductsSearch.json", "060000")
    count = transform_and_load_mongo(
        product_type="annuity", 
        collection_name="products_annuity", # 개별 컬렉션
        data=data
    )
    return f"Annuity ETL Complete: {count} docs"

# -------------------------------------------------------------------
# [DAG] Airflow DAG 정의 (수정됨)
# -------------------------------------------------------------------
@dag(
    dag_id="fss_products_etl_pipeline", # DAG ID
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 3 * * *", # <-- [수정] 매일 새벽 3시에 실행
    catchup=False,
    tags=["fss", "products", "etl", "team_4", "separate_collections"],
)
def fss_financial_products_pipeline():
    """
    [4팀] 금융감독원 3종 상품(예금, 적금, 연금)을 수집하여
    MongoDB (financial_products)의 개별 컬렉션에 RAG용 텍스트 데이터로 적재(Upsert)합니다.
    (3개 Task는 병렬로 실행됩니다)
    """
    # 3개의 Task를 병렬로 실행
    etl_deposit()
    etl_saving()
    etl_annuity()

# DAG 실행
fss_financial_products_pipeline()