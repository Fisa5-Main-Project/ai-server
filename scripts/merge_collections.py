"""
MongoDB 컬렉션 통합 스크립트
- products_deposit + products_saving → products_deposit_saving
- products_fsc_fund + products_fund_kvic → products_funds
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

def get_mongo_url():
    username = os.getenv("MONGO_USERNAME")
    password = os.getenv("MONGO_PASSWORD")
    host = os.getenv("MONGO_HOST")
    return f"mongodb+srv://{username}:{password}@{host}"

def merge_collections():
    """컬렉션 통합 실행"""
    mongo_url = get_mongo_url()
    
    with MongoClient(mongo_url) as client:
        db = client["financial_products"]
        
        print("="*60)
        print("MongoDB 컬렉션 통합 시작")
        print("="*60)
        
        # 1. Deposit + Saving 통합
        print("\n[1/2] Deposit + Saving 통합 중...")
        
        # 새 컬렉션 생성
        new_deposit_saving = db["products_deposit_saving"]
        
        # Deposit 데이터 복사
        deposit_docs = list(db["products_deposit"].find())
        if deposit_docs:
            new_deposit_saving.insert_many(deposit_docs)
            print(f"  ✅ Deposit: {len(deposit_docs)}개 문서 복사")
        
        # Saving 데이터 복사
        saving_docs = list(db["products_saving"].find())
        if saving_docs:
            new_deposit_saving.insert_many(saving_docs)
            print(f"  ✅ Saving: {len(saving_docs)}개 문서 복사")
        
        print(f"  ✅ 총 {len(deposit_docs) + len(saving_docs)}개 문서를 products_deposit_saving에 통합")
        
        # 2. FSC Fund + KVIC Fund 통합
        print("\n[2/2] FSC Fund + KVIC Fund 통합 중...")
        
        # 새 컬렉션 생성
        new_funds = db["products_funds"]
        
        # FSC Fund 데이터 복사
        fsc_docs = list(db["products_fsc_fund"].find())
        if fsc_docs:
            new_funds.insert_many(fsc_docs)
            print(f"  ✅ FSC Fund: {len(fsc_docs)}개 문서 복사")
        
        # KVIC Fund 데이터 복사
        kvic_docs = list(db["products_fund_kvic"].find())
        if kvic_docs:
            new_funds.insert_many(kvic_docs)
            print(f"  ✅ KVIC Fund: {len(kvic_docs)}개 문서 복사")
        
        print(f"  ✅ 총 {len(fsc_docs) + len(kvic_docs)}개 문서를 products_funds에 통합")
        
        print("\n" + "="*60)
        print("컬렉션 통합 완료!")
        print("="*60)
        print("\n다음 단계:")
        print("1. Atlas UI에서 기존 인덱스 모두 삭제")
        print("2. 새 컬렉션에 인덱스 생성:")
        print("   - products_annuity → annuity_vector_index")
        print("   - products_deposit_saving → deposit_saving_vector_index")
        print("   - products_funds → funds_vector_index")
        print("3. 기존 컬렉션 삭제 (선택사항):")
        print("   - products_deposit")
        print("   - products_saving")
        print("   - products_fsc_fund")
        print("   - products_fund_kvic")

if __name__ == "__main__":
    try:
        merge_collections()
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
