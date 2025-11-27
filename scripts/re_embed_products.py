"""
금융상품 재임베딩 스크립트 (Upstage Solar, 4096차원)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from pymongo import MongoClient
from app.core.config import settings
from app.core.llm_factory import LLMFactory
from tqdm import tqdm

def re_embed_products():
    """모든 금융상품을 Upstage Solar로 재임베딩"""
    
    print("📝 Upstage Solar 임베딩 모델 로드 중...")
    embeddings = LLMFactory.create_embeddings()
    
    client = MongoClient(settings.MONGO_DB_URL)
    db = client[settings.DB_NAME]
    
    collections = [
        "products_deposit_saving",
        "products_annuity",
        "products_fund"
    ]
    
    for coll_name in collections:
        collection = db[coll_name]
        
        # embedding 필드가 있는 문서만 조회
        docs = list(collection.find({"description": {"$exists": True}}))
        
        if not docs:
            print(f"⚠️  {coll_name}: 문서 없음")
            continue
        
        print(f"\n🔄 {coll_name}: {len(docs)}개 재임베딩 중...")
        
        updates = []
        for doc in tqdm(docs, desc=coll_name):
            try:
                # description 텍스트로 임베딩 생성
                text = doc.get("description", "")
                if not text:
                    continue
                
                embedding = embeddings.embed_query(text)
                
                # 4096차원 확인 (Solar)
                assert len(embedding) == 4096, f"차원 오류: {len(embedding)}"
                
                updates.append({
                    "_id": doc["_id"],
                    "embedding": embedding
                })
                
                # 100개씩 배치 업데이트
                if len(updates) >= 100:
                    for item in updates:
                        collection.update_one(
                            {"_id": item["_id"]},
                            {"$set": {"embedding": item["embedding"]}}
                        )
                    updates = []
            
            except Exception as e:
                print(f"❌ {doc.get('_id')} 실패: {e}")
        
        # 남은 업데이트 처리
        if updates:
            for item in updates:
                collection.update_one(
                    {"_id": item["_id"]},
                    {"$set": {"embedding": item["embedding"]}}
                )
        
        print(f"✅ {coll_name} 완료")
    
    print("\n🎉 전체 재임베딩 완료!")

if __name__ == "__main__":
    re_embed_products()
