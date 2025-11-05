import pendulum
import requests
import math
from pymongo import MongoClient
from airflow.decorators import dag, task
from airflow.models.variable import Variable

# --- 0. 설정: Airflow UI의 Variables에서 값 불러오기 ---
try:
    FSC_API_KEY = Variable.get("FSC_API_KEY") # 금융위 API 키
    MONGO_DB_URL = Variable.get("MONGO_DB_URL")
    MONGO_DB_NAME = Variable.get("DB_NAME")
    FUND_COLLECTION = "products_fsc_fund" # 펀드 전용 컬렉션
except KeyError:
    raise Exception("Airflow Variables에 FSC_API_KEY, MONGO_DB_URL, DB_NAME을 등록해야 합니다.")

# -------------------------------------------------------------------
# [E] Extract: 펀드 표준코드 API 호출 Task (수정됨)
# -------------------------------------------------------------------
@task(task_id="extract_fsc_funds")
def extract_fsc_funds(**kwargs): # Airflow 실행 날짜를 받기 위해 **kwargs 추가
    """
    금융위원회 펀드상품기본정보(getStandardCodeInfo) API로 펀드 표준코드를 수집합니다.
    (수정) 매일 실행 시 '어제' 날짜의 데이터만 증분 수집합니다.
    """
    print("FSC 펀드 표준코드 데이터 추출 시작...")
    url = "https://apis.data.go.kr/1160100/service/GetFundProductInfoService/getStandardCodeInfo"
    
    # [수정] Airflow의 실행 날짜(logical_date)를 기준으로 '어제' 날짜를 계산
    # 'data_interval_start'는 UTC 기준이므로 한국 시간(Asia/Seoul)으로 변경
    logical_date = kwargs.get("data_interval_start", pendulum.today(tz="Asia/Seoul").subtract(days=1))
    if isinstance(logical_date, str):
         logical_date = pendulum.parse(logical_date)
         
    # 'data_interval_start'는 3시 실행 시 '어제' 날짜가 됩니다.
    # (e.g., 11월 5일 03:00 실행 -> data_interval_start는 11월 4일 03:00)
    # API가 요구하는 'YYYYMMDD' 형식으로 포맷
    target_date = logical_date.format("YYYYMMDD")
    print(f"데이터 수집 기준 일자(basDt): {target_date}")
    
    all_fund_items = []
    page_no = 1
    max_page_no = 1 
    num_of_rows = 1000
    
    while page_no <= max_page_no:
        params = {
            "serviceKey": FSC_API_KEY,
            "resultType": "json",
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
            "basDt": target_date # [수정] 어제 날짜(basDt)로 범위 한정
        }
        
        try:
            response = requests.get(url, params=params, timeout=30) 
            response.raise_for_status()
            data = response.json()
            
            if "response" not in data or "body" not in data["response"]:
                raise Exception(f"API 응답 형식이 다릅니다 (response/body 없음): {str(data)[:200]}")
            
            body = data["response"]["body"]
            
            # (최초 1회) max_page_no 계산
            if page_no == 1:
                total_count = int(body.get("totalCount", 0))
                if total_count == 0:
                    print(f"{target_date} 기준 수집할 데이터가 0건입니다.")
                    break
                max_page_no = math.ceil(total_count / num_of_rows)
                print(f"총 {total_count}개 데이터 확인. (총 {max_page_no} 페이지)")

            items = body.get("items", {}).get("item", [])
            
            if isinstance(items, dict):
                items = [items]
            
            all_fund_items.extend(items)
            
            print(f"페이지 {page_no}/{max_page_no} 수집 완료... (항목 {len(items)}개)")
            page_no += 1
            
        except requests.exceptions.RequestException as e:
            print(f"API 호출 실패 (Page {page_no}): {e}")
            raise
        except Exception as e:
            print(f"데이터 파싱 실패 (Page {page_no}): {e}")
            raise
            
    print(f"FSC 펀드 추출 완료: 총 {len(all_fund_items)}개 펀드 수집")
    return all_fund_items

# -------------------------------------------------------------------
# [T+L] Transform & Load: 변환 및 적재 공통 함수
# -------------------------------------------------------------------
@task(task_id="transform_load_mongo_fsc_funds")
def transform_and_load_mongo_fsc_funds(fund_list: list):
    """
    추출된 펀드 표준코드를 RAG용 텍스트로 변환하고
    MongoDB 'products_fsc_fund' 컬렉션에 적재(Upsert)합니다.
    """
    
    if not fund_list:
        print("MongoDB에 적재할 펀드 데이터가 없습니다.")
        return 0

    mongo_docs_to_upsert = []
    
    # API 명세 필드: srtnCd, fndNm, ctg, fndTp 등
    for fund in fund_list:
        
        # RAG AI가 검색할 통합 텍스트 필드 ('rag_text')
        rag_text = (
            f"상품유형: 펀드(금융위). "
            f"펀드명: {fund.get('fndNm', '')}. "
            f"펀드유형: {fund.get('fndTp', '')}. "
            f"구분: {fund.get('ctg', '')}. "
            f"단축코드: {fund.get('srtnCd', '')}. "
            f"기준일자: {fund.get('basDt', '')}."
        )
        
        mongo_doc = fund.copy()
        mongo_doc["product_type"] = "fund_fsc"
        mongo_doc["rag_text"] = rag_text
        
        # 고유 ID (단축코드 'srtnCd' 사용)
        mongo_doc["_id"] = f"FSC_{fund.get('srtnCd', 'UNKNOWN')}" 
        
        mongo_docs_to_upsert.append(mongo_doc)

    if not mongo_docs_to_upsert:
        print("MongoDB에 적재할 문서가 없습니다.")
        return 0
        
    try:
        client = MongoClient(MONGO_DB_URL, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client[MONGO_DB_NAME]
        collection = db[FUND_COLLECTION] # 'products_fsc_fund' 컬렉션 사용
        
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
    dag_id="fsc_fund_standard_code_pipeline",
    start_date=pendulum.datetime(2025, 11, 1, tz="Asia/Seoul"),
    schedule="0 3 * * *", # 매일 새벽 3시
    catchup=False,
    tags=["fsc", "fund", "etl", "team_4"],
)
def fsc_fund_pipeline():
    """
    [4팀] 금융위원회(data.go.kr)의 펀드상품기본정보를 수집하여
    MongoDB (financial_products.products_fsc_fund)에 RAG용 데이터로 적재(Upsert)합니다.
    (매일 새벽 3시, '어제' 날짜의 데이터만 증분 수집)
    """
    # Task 순서: extract -> transform_and_load
    extracted_data = extract_fsc_funds()
    transform_and_load_mongo_fsc_funds(extracted_data)

# DAG 실행
fsc_fund_pipeline()