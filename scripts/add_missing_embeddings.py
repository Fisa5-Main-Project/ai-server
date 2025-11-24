"""
기존 MongoDB 데이터에 임베딩이 없는 문서들을 찾아서 임베딩을 추가하는 스크립트
"""
import sys
import os

# Airflow plugins 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'airflow', 'plugins'))

from pymongo import MongoClient, UpdateOne
from etl_utils import add_embeddings_to_docs, get_mongo_db_url


def add_embeddings_to_collection(collection_name: str):
    """
    특정 컬렉션의 임베딩이 없는 문서에 임베딩 추가
    
    Args:
        collection_name: MongoDB 컬렉션 이름
    """
    print(f"\n{'='*60}")
    print(f"컬렉션: {collection_name}")
    print(f"{'='*60}")
    
    # MongoDB 연결
    mongo_url = get_mongo_db_url()
    total_processed = 0

    with MongoClient(mongo_url) as client:
        db = client["financial_products"]
        collection = db[collection_name]
        
        # embedding 필드가 없는 문서 조회
        docs_without_embedding = list(collection.find({"embedding": {"$exists": False}}))
        
        print(f"임베딩이 없는 문서 수: {len(docs_without_embedding)}")
        
        if not docs_without_embedding:
            print("모든 문서에 이미 임베딩이 있습니다.")
            return
        
        # 배치 처리 (Rate Limit 방지)
        batch_size = 50
        
        for i in range(0, len(docs_without_embedding), batch_size):
            batch = docs_without_embedding[i:i+batch_size]
            print(f"\n배치 처리 중: {i+1}~{min(i+batch_size, len(docs_without_embedding))}/{len(docs_without_embedding)}")
            
            try:
                # 임베딩 추가 (내부적으로 batch_size=5로 처리됨)
                embedded_docs = add_embeddings_to_docs(batch, batch_size=5)
                
                # Bulk write로 성능 개선
                operations = [
                    UpdateOne(
                        {"_id": doc["_id"]},
                        {"$set": {"embedding": doc["embedding"]}}
                    ) for doc in embedded_docs
                ]

                if operations:
                    result = collection.bulk_write(operations)
                    total_processed += result.modified_count
                
                print(f"배치 완료: {len(embedded_docs)}개 문서 업데이트")
                
            except Exception as e:
                print(f"배치 처리 중 오류 발생: {e}")
                print(f"   진행 상황: {total_processed}/{len(docs_without_embedding)} 완료")
                raise
    
    print(f"\n{collection_name} 임베딩 추가 완료: {total_processed}개 문서 처리됨")


def main():
    """모든 컬렉션에 대해 임베딩 추가"""
    collections = [
        "products_fsc_fund",
        "products_deposit",
        "products_saving",
        "products_annuity",
        "products_fund_kvic",
    ]
    
    print("임베딩 추가 작업 시작...")
    print(f"처리할 컬렉션 수: {len(collections)}")
    
    for collection_name in collections:
        try:
            add_embeddings_to_collection(collection_name)
        except Exception as e:
            print(f"\n{collection_name} 처리 실패: {e}")
            print("다음 컬렉션으로 계속 진행합니다...")
            continue
    
    print("\n" + "="*60)
    print("모든 작업 완료!")
    print("="*60)


if __name__ == "__main__":
    main()
