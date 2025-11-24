import requests
import math
import re
import time
from pymongo import MongoClient
from airflow.models.variable import Variable
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# --- [E] Extract Functions ---

def fetch_fss_data(api_key: str, api_endpoint: str, top_fin_grp_no: str):
    """(수정) 금감원 API를 호출하여 '모든 페이지'를 수집합니다."""
    print(f"[{api_endpoint}] 데이터 추출 시작...")
    base_url = "http://finlife.fss.or.kr/finlifeapi/"
    url = f"{base_url}{api_endpoint}"
    
    all_base_list = []
    all_option_list = []
    page_no = 1
    max_page_no = 1
    
    while page_no <= max_page_no:
        params = {"auth": api_key, "topFinGrpNo": top_fin_grp_no, "pageNo": str(page_no)}
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            result = data["result"]
            
            if result.get("err_cd") != "000":
                print(f"API 오류 (Page {page_no}): {result.get('err_msg')}")
                break

            all_base_list.extend(result.get("baseList", []))
            all_option_list.extend(result.get("optionList", []))
            
            max_page_no = int(result.get("max_page_no", 1))
            print(f"페이지 {page_no}/{max_page_no} 수집 완료...")
            page_no += 1
            
        except requests.exceptions.RequestException as e:
            print(f"API 호출 실패 (Page {page_no}): {e}")
            raise
            
    print(f"[{api_endpoint}] 추출 완료: 총 {len(all_base_list)}개 상품")
    return {"base_list": all_base_list, "option_list": all_option_list}

def fetch_kvic_funds(api_key: str):
    """KVIC API로 2020-2023년 펀드 현황을 수집합니다."""
    print("KVIC 펀드 현황 데이터 추출 시작...")
    url = "https://www.kvic.or.kr/api/fundType"
    years_to_fetch = [2020, 2021, 2022, 2023]
    all_fund_list = []
    
    for year in years_to_fetch:
        print(f"--- {year}년도 데이터 수집 시작 ---")
        params = {"key": api_key, "fundType": "00", "year": str(year), "of": "1"}
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, dict) and data.get("code") not in [None, ""]:
                print(f"KVIC API 오류 ({year}년): Code={data.get('code')}, Message={data.get('Message', 'N/A')}")
                continue

            year_fund_list = []
            if isinstance(data, dict) and "result_11" in data and isinstance(data["result_11"], list):
                year_fund_list = data["result_11"]
            elif isinstance(data, dict) and "result" in data and isinstance(data["result"], list):
                year_fund_list = data["result"]
            elif isinstance(data, list):
                year_fund_list = data
            
            print(f"{year}년도 {len(year_fund_list)}개 펀드 수집 완료.")
            all_fund_list.extend(year_fund_list)
                
        except requests.exceptions.RequestException as e:
            print(f"KVIC API 호출 실패 ({year}년): {e}")
            continue
            
    print(f"KVIC 추출 완료: 총 {len(all_fund_list)}개 펀드 수집")
    return all_fund_list

def fetch_fsc_funds(api_key: str, target_date: str):
    """금융위원회 펀드상품기본정보 API로 '지정된 날짜(basDt)'의 펀드를 수집합니다."""
    print(f"FSC 펀드 표준코드 데이터 추출 시작... (기준일자: {target_date})")
    url = "https://apis.data.go.kr/1160100/service/GetFundProductInfoService/getStandardCodeInfo"
    
    all_fund_items = []
    page_no = 1
    max_page_no = 1
    num_of_rows = 1000
    
    while page_no <= max_page_no:
        params = {
            "serviceKey": api_key,
            "resultType": "json",
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
            "basDt": target_date 
        }
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "response" not in data or "body" not in data["response"]:
                raise Exception(f"API 응답 형식이 다릅니다 (response/body 없음): {str(data)[:200]}")
            
            body = data["response"]["body"]
            
            if page_no == 1:
                total_count = int(body.get("totalCount", 0))
                if total_count == 0:
                    print(f"{target_date} 기준 수집할 데이터가 0건입니다.")
                    break
                max_page_no = math.ceil(total_count / num_of_rows)
                print(f"총 {total_count}개 데이터 확인. (총 {max_page_no} 페이지)")

            items = body.get("items", {}).get("item", [])
            if isinstance(items, dict): items = [items]
            
            all_fund_items.extend(items)
            print(f"페이지 {page_no}/{max_page_no} 수집 완료... (항목 {len(items)}개)")
            page_no += 1
            
        except requests.exceptions.RequestException as e:
            print(f"API 호출 실패 (Page {page_no}): {e}")
            raise
            
    print(f"FSC 펀드 추출 완료: 총 {len(all_fund_items)}개 펀드 수집")
    return all_fund_items

# --- [Embed] Embedding Functions ---

def get_gemini_embeddings(texts: list[str], model: str = "models/text-embedding-004") -> list[list[float]]:
    """Gemini(LangChain)를 사용하여 텍스트 리스트의 임베딩을 생성합니다."""
    if not texts:
        return []
    
    api_key = Variable.get("GEMINI_API_KEY")
    
    try:
        # GoogleGenerativeAIEmbeddings 초기화
        embeddings_model = GoogleGenerativeAIEmbeddings(
            model=model,
            google_api_key=api_key
        )
        
        # 임베딩 생성
        embeddings = embeddings_model.embed_documents(texts)
        return embeddings
    except Exception as e:
        print(f"Gemini 임베딩 생성 실패: {e}")
        raise

def add_embeddings_to_docs(mongo_docs: list, batch_size: int = 5):
    """MongoDB 문서 리스트의 'rag_text' 필드를 임베딩하여 'embedding' 필드에 추가합니다."""
    if not mongo_docs:
        return mongo_docs

    print(f"임베딩 생성 시작: 총 {len(mongo_docs)}개 문서 (Batch Size: {batch_size})")
    
    # 임베딩 대상 텍스트 추출
    texts_to_embed = [doc.get("rag_text", "") for doc in mongo_docs]
    
    all_embeddings = []
    total_docs = len(texts_to_embed)
    
    # Batch 처리
    for i in range(0, total_docs, batch_size):
        batch_texts = texts_to_embed[i : i + batch_size]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                embeddings = get_gemini_embeddings(batch_texts)
                all_embeddings.extend(embeddings)
                print(f"임베딩 진행 중: {min(i + batch_size, total_docs)}/{total_docs} 완료")
                time.sleep(3.0) # 기본 대기 시간
                break # 성공 시 retry 루프 탈출
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 30 # 30초, 60초 대기
                    print(f"Rate Limit (429) 발생. {wait_time}초 후 재시도합니다... (시도 {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"Batch {i} 처리 중 오류 발생 (시도 {attempt + 1}/{max_retries}): {e}")
                    raise

    # 문서에 임베딩 추가
    for doc, embedding in zip(mongo_docs, all_embeddings):
        doc["embedding"] = embedding
        
    print("임베딩 추가 완료.")
    return mongo_docs

# --- [L] Load Function (공통 로더) ---

def load_to_mongo(mongo_url: str, db_name: str, collection_name: str, mongo_docs: list, product_type: str):
    """MongoDB에 Upsert를 수행하는 공통 로더 함수"""
    if not mongo_docs:
        print(f"[{product_type}] MongoDB에 적재할 문서가 없습니다.")
        return 0
    
    client = None
    try:
        import certifi
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000, tlsCAFile=certifi.where())
        db = client[db_name]
        collection = db[collection_name]
        
        print(f"[{product_type}] MongoDB ({db_name}.{collection_name})에 {len(mongo_docs)}개 문서 적재 (Upsert) 시작...")
        
        upsert_count = 0
        for doc in mongo_docs:
            if not doc.get("_id"):
                print(f"ID가 없는 문서 발견, 건너뜁니다: {doc}")
                continue
            collection.update_one(
                {"_id": doc["_id"]}, # Filter
                {"$set": doc},       # Update/Set data
                upsert=True          # Insert if not exists
            )
            upsert_count += 1
            
        print(f"[{product_type}] 적재 완료: {upsert_count}개 문서 처리됨.")
        return upsert_count
    except Exception as e:
        print(f"[{product_type}] MongoDB 적재 실패: {e}")
        raise
    finally:
        if client: client.close()

# --- [T] Transform Functions (상품별 전처리) ---

def transform_deposit_saving(data: dict, product_type: str):
    """[신규] 예금/적금 RAG 텍스트 전처리"""
    base_list = data["base_list"]
    option_list = data["option_list"]
    if not base_list: return []

    # 키워드 매핑 정의
    keyword_map = {
        "비대면": ["인터넷", "스마트폰", "비대면"],
        "첫거래": ["최초", "첫거래", "신규고객"],
        "주거래": ["주거래"],
        "급여이체": ["급여", "연금"],
        "카드실적": ["카드"],
        "마케팅동의": ["마케팅", "SMS"],
        "오픈뱅킹": ["오픈뱅킹"],
        "청년": ["청년"],
        "고령자": ["시니어", "연금", "만50세", "만65세"]
    }

    mongo_docs = []
    for base_product in base_list:
        product_code = base_product["fin_prdt_cd"]
        company_no = base_product["fin_co_no"]
        
        options = [opt for opt in option_list if opt["fin_prdt_cd"] == product_code and opt["fin_co_no"] == company_no]
        
        # --- 전처리 로직 ---
        rag_keywords = set()
        full_text = f"{base_product.get('spcl_cnd', '')} {base_product.get('join_member', '')} {base_product.get('join_way', '')}"
        
        for key, values in keyword_map.items():
            if any(val in full_text for val in values):
                rag_keywords.add(key)
        
        # 옵션에서 최고 금리 찾기 (RAG 검색용)
        max_rate = 0.0
        if options:
            try:
                max_rate = max(float(opt.get('intr_rate2', 0.0)) for opt in options)
            except (ValueError, TypeError):
                max_rate = 0.0 # 숫자가 아닌 값이 들어올 경우 대비
        
        rag_text = (
            f"상품유형: {product_type}. "
            f"상품명: {base_product.get('fin_prdt_nm', '')}. "
            f"은행: {base_product.get('kor_co_nm', '')}. "
            f"최고금리: {max_rate}%. "
            f"키워드: {', '.join(rag_keywords) if rag_keywords else '없음'}."
        )
        
        mongo_doc = base_product.copy()
        mongo_doc["product_type"] = product_type
        mongo_doc["options"] = options
        mongo_doc["rag_text"] = rag_text
        mongo_doc["_id"] = f"{company_no}_{product_code}"
        
        mongo_docs.append(mongo_doc)
    return mongo_docs

def transform_annuity(data: dict):
    """[기존] 연금저축 RAG 텍스트 전처리"""
    base_list = data["base_list"]
    option_list = data["option_list"]
    if not base_list: return []

    mongo_docs = []
    for base_product in base_list:
        product_code = base_product["fin_prdt_cd"]
        company_no = base_product["fin_co_no"]
        options = [opt for opt in option_list if opt["fin_prdt_cd"] == product_code and opt["fin_co_no"] == company_no]
        
        rag_keywords = []
        if options:
            option = options[0]
            if option.get("pnsn_kind_nm"): rag_keywords.append(option.get("pnsn_kind_nm"))
            if option.get("prdt_type_nm"): rag_keywords.append(option.get("prdt_type_nm"))
            guar_rate_str = "보장" if option.get("guar_rate") is not None else "비보장"
            rag_keywords.append(guar_rate_str)
            if option.get("pnsn_entr_age_nm"): rag_keywords.append(f"가입연령:{option.get('pnsn_entr_age_nm')}")
            if option.get("pnsn_strt_age_nm"): rag_keywords.append(f"수령연령:{option.get('pnsn_strt_age_nm')}")
            rate_1y = option.get("btrm_prft_rate_1", 0.0)
            if rate_1y > 0: rag_keywords.append(f"1년수익률:{rate_1y}%")
        
        rag_text = (
            f"상품유형: annuity. "
            f"상품명: {base_product.get('fin_prdt_nm', '')}. "
            f"운용사: {base_product.get('kor_co_nm', '')}. "
            f"특징: {base_product.get('join_way', '')}. "
            f"키워드: {', '.join(rag_keywords)}"
        )
        
        mongo_doc = base_product.copy()
        mongo_doc["product_type"] = "annuity"
        mongo_doc["options"] = options
        mongo_doc["rag_text"] = rag_text
        mongo_doc["_id"] = f"{company_no}_{product_code}"
        
        mongo_docs.append(mongo_doc)
    return mongo_docs

def transform_kvic_funds(fund_list: list):
    """[신규] KVIC 펀드 RAG 텍스트 전처리"""
    if not fund_list: return []
    mongo_docs = []
    for fund in fund_list:
        rag_text = (
            f"상품유형: 펀드(벤처투자). "
            f"조합명: {fund.get('asn', '')}. "
            f"운용사: {fund.get('mng', '')}. "
            f"출자분야: {fund.get('fd', '')}. "
            f"약정액(억원): {fund.get('ca', '0')}. "
            f"기준년도: {fund.get('year', '')}."
        )
        mongo_doc = fund.copy()
        mongo_doc["product_type"] = "fund_kvic"
        mongo_doc["rag_text"] = rag_text
        mongo_doc["_id"] = f"KVIC_{fund.get('asn', 'UNKNOWN')}_{fund.get('year', '')}" 
        mongo_docs.append(mongo_doc)
    return mongo_docs

def transform_fsc_funds(fund_list: list):
    """[신규] 금융위 펀드 RAG 텍스트 전처리"""
    if not fund_list: return []
    mongo_docs = []
    for fund in fund_list:
        rag_text = (
            f"상품유형: 펀드(금융위). "
            f"펀드명: {fund.get('fndNm', '')}. "
            f"펀드유형: {fund.get('fndTp', '')}. "
            f"구분: {fund.get('ctg', '')}. "
            f"기준일자: {fund.get('basDt', '')}."
        )
        mongo_doc = fund.copy()
        mongo_doc["product_type"] = "fund_fsc"
        mongo_doc["rag_text"] = rag_text
        mongo_doc["_id"] = f"FSC_{fund.get('srtnCd', 'UNKNOWN')}_{fund.get('basDt', '')}" # ID 중복 방지를 위해 basDt 포함
        mongo_docs.append(mongo_doc)
    return mongo_docs

def get_mongo_db_url():
    import os
    from pymongo.mongo_client import MongoClient
    from pymongo.server_api import ServerApi
    
    username = os.getenv("MONGO_USERNAME")
    password = os.getenv("MONGO_PASSWORD")
    host = os.getenv("MONGO_HOST")

    uri = f"mongodb+srv://{username}:{password}@{host}"

    return uri