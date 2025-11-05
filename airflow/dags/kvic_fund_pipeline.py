import pendulum
import requests
from pymongo import MongoClient
from airflow.decorators import dag, task
from airflow.models.variable import Variable

# --- 0. 설정: Airflow UI의 Variables에서 값 불러오기 ---
try:
    KVIC_API_KEY = Variable.get("KVIC_API_KEY")
    MONGO_DB_URL = Variable.get("MONGO_DB_URL")
    MONGO_DB_NAME = Variable.get("DB_NAME")
    FUND_COLLECTION = "products_fund"
except KeyError:
    raise Exception("Airflow Variables에 KVIC_API_KEY, MONGO_DB_URL, DB_NAME을 등록해야 합니다.")

# -------------------------------------------------------------------
# [E] Extract: 펀드 현황 API 호출 Task (수정됨)
# -------------------------------------------------------------------
@task(task_id="extract_kvic_funds")
def extract_kvic_funds():
    """한국벤처투자(KVIC) API로 펀드 현황을 수집합니다. (2020-2023년)"""
    print("KVIC 펀드 현황 데이터 추출 시작...")
    url = "https://www.kvic.or.kr/api/fundType"
    
    # [수정] 2020, 2021, 2022, 2023년 데이터를 수집
    years_to_fetch = [2020, 2021, 2022, 2023]
    all_fund_list = [] # 모든 연도의 데이터를 담을 리스트
    
    for year in years_to_fetch:
        print(f"--- {year}년도 데이터 수집 시작 ---")
        params = {
            "key": KVIC_API_KEY,
            "fundType": "00", # 전체
            "year": str(year), # [수정] 2020, 2021, 2022, 2023 순회
            "of": "1" # JSON 포맷
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # 1. 오류 코드 확인
            if isinstance(data, dict) and data.get("code") not in [None, ""]:
                print(f"KVIC API 오류 ({year}년): Code={data.get('code')}, Message={data.get('Message', 'N/A')}")
                continue # 오류 발생 시 다음 연도로 넘어감

            # 2. "result_11" 또는 "result" 키에서 데이터 리스트 추출
            year_fund_list = []
            if isinstance(data, dict) and "result_11" in data and isinstance(data["result_11"], list):
                year_fund_list = data["result_11"]
            elif isinstance(data, dict) and "result" in data and isinstance(data["result"], list):
                year_fund_list = data["result"]
            elif isinstance(data, list):
                year_fund_list = data
            elif isinstance(data, dict) and 'list' in data and isinstance(data['list'], list):
                year_fund_list = data['list']
            else:
                print(f"KVIC API ({year}년) 응답 형식이 예상과 다릅니다. (0개 처리) 응답: {str(data)[:200]}")
            
            print(f"{year}년도 {len(year_fund_list)}개 펀드 수집 완료.")
            all_fund_list.extend(year_fund_list) # [수정] 전체 리스트에 추가
                
        except requests.exceptions.RequestException as e:
            print(f"KVIC API 호출 실패 ({year}년): {e}")
            # 한 해가 실패해도 다음 연도를 시도
            continue 
            
    print(f"KVIC 추출 완료: 총 {len(all_fund_list)}개 펀드 수집 (기준연도: {years_to_fetch})")
    return all_fund_list # [수정] 전체 리스트 반환

# -------------------------------------------------------------------
# [T+L] Transform & Load: 변환 및 적재 공통 함수
# -------------------------------------------------------------------
@task(task_id="transform_load_mongo_funds")
def transform_and_load_mongo_funds(fund_list: list):
    """
    추출된 펀드 데이터를 RAG용 텍스트로 변환하고
    MongoDB 'products_fund' 컬렉션에 적재(Upsert)합니다.
    """
    
    if not fund_list:
        print("MongoDB에 적재할 펀드 데이터가 없습니다.")
        return 0

    mongo_docs_to_upsert = []
    
    # API 명세 필드: year, fd, mng, asn, exp, amt, ca
    for fund in fund_list:
        
        # RAG AI가 검색할 통합 텍스트 필드 ('rag_text')
        rag_text = (
            f"상품유형: 펀드. "
            f"조합명: {fund.get('asn', '')}. "
            f"운용사: {fund.get('mng', '')}. "
            f"출자분야: {fund.get('fd', '')}. "
            f"약정액(억원): {fund.get('ca', '')}. "
            f"금액(억원): {fund.get('amt', '')}. "
            f"만기일: {fund.get('exp', '')}. "
            f"기준년도: {fund.get('year', '')}."
        )
        
        mongo_doc = fund.copy()
        mongo_doc["product_type"] = "fund"
        mongo_doc["rag_text"] = rag_text # AI 서버가 임베딩할 텍스트
        
        # 고유 ID (조합명 + 연도)
        mongo_doc["_id"] = f"KVIC_{fund.get('asn', 'UNKNOWN')}_{fund.get('year', '')}" 
        
        mongo_docs_to_upsert.append(mongo_doc)

    if not mongo_docs_to_upsert:
        print("MongoDB에 적재할 문서가 없습니다.")
        return 0
        
    try:
        client = MongoClient(MONGO_DB_URL, serverSelectionTimeoutMS=5000)
        client.server_info() # DB 연결 테스트
        db = client[MONGO_DB_NAME]
        collection = db[FUND_COLLECTION] # 'products_fund' 컬렉션 사용
        
        print(f"MongoDB ({MONGO_DB_NAME}.{FUND_COLLECTION})에 {len(mongo_docs_to_upsert)}개 문서 적재 (Upsert) 시작...")
        
        upsert_count = 0
        for doc in mongo_docs_to_upsert:
            collection.update_one(
                {"_id": doc["_id"]}, # 필터
                {"$set": doc},       # 덮어쓰기
                upsert=True          # 없으면 삽입
            )
            upsert_count += 1
            
        print(f"적재 완료: {upsert_count}개 문서 처리됨.")
        return upsert_count
        
    except Exception as e:
        print(f"MongoDB 적재 실패: {e}")
        raise
    finally:
        if client:
            client.close()

# -------------------------------------------------------------------
# [DAG] Airflow DAG 정의
# -------------------------------------------------------------------
@dag(
    dag_id="kvic_fund_etl_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 3 * * *", # 매일 새벽 3시
    catchup=False,
    tags=["kvic", "fund", "etl", "team_4"],
)
def kvic_fund_pipeline():
    """
    [4팀] 한국벤처투자(KVIC)의 펀드 현황을 수집하여
    MongoDB (financial_products.products_fund)에 RAG용 데이터로 적재(Upsert)합니다.
    (2020-2023년 데이터 수집)
    """
    # Task 순서: extract -> transform_and_load
    extracted_data = extract_kvic_funds()
    transform_and_load_mongo_funds(extracted_data)

# DAG 실행
kvic_fund_pipeline()