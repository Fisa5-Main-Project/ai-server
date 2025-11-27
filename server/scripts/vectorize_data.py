import os
import sys
import time
from pymongo import MongoClient
from dotenv import load_dotenv

# Add server directory to sys.path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.config import settings
from app.core.llm_factory import LLMFactory

# Load environment variables
load_dotenv()

# Initialize Embedding Model (Local via LLMFactory)
embeddings = LLMFactory.create_embeddings()

def create_vector_index(db, collection_name):
    """Creates a vector search index for the collection."""
    index_definition = {
        "name": "vector_index",
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 1024,  # Local BGE-m3-ko Dimension
                    "similarity": "cosine"
                },
                {
                    "type": "filter",
                    "path": "product_type"
                }
            ]
        }
    }
    
    try:
        indexes = list(db[collection_name].list_search_indexes())
        if any(idx['name'] == 'vector_index' for idx in indexes):
            print(f"[{collection_name}] Vector index 'vector_index' already exists.")
            # Note: If dimension changed, user might need to drop and recreate index manually or we can add logic here.
            # For now, just printing existence.
            return

        print(f"[{collection_name}] Creating vector index...")
        db.command({
            "createSearchIndexes": collection_name,
            "indexes": [index_definition]
        })
        print(f"[{collection_name}] Vector index created.")
    except Exception as e:
        print(f"[{collection_name}] Failed to create vector index: {e}")

def vectorize_collection(db, collection_name):
    """Fetches docs, generates embeddings, and updates docs."""
    collection = db[collection_name]
    cursor = collection.find({"rag_text": {"$exists": True}})
    
    total_docs = collection.count_documents({"rag_text": {"$exists": True}})
    print(f"[{collection_name}] Found {total_docs} documents with 'rag_text'. Processing...")
    
    count = 0
    batch_size = 10
    batch_docs = []
    
    for doc in cursor:
        batch_docs.append(doc)
        
        if len(batch_docs) >= batch_size:
            process_batch(collection, batch_docs)
            count += len(batch_docs)
            print(f"[{collection_name}] Processed {count}/{total_docs}...")
            batch_docs = []
            time.sleep(0.5) # Rate limit precaution
            
    if batch_docs:
        process_batch(collection, batch_docs)
        count += len(batch_docs)
        print(f"[{collection_name}] Processed {count}/{total_docs}...")

def process_batch(collection, docs):
    texts = [doc["rag_text"] for doc in docs]
    try:
        vectors = embeddings.embed_documents(texts)
        
        for doc, vector in zip(docs, vectors):
            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"embedding": vector}}
            )
    except Exception as e:
        print(f"Error embedding batch: {e}")

def main():
    # Settings from config.py are used, but we can fallback or check envs if needed.
    # LLMFactory uses settings.SOLAR_API_KEY
    
    if not settings.MONGO_DB_URL:
        print("Error: MONGO_DB_URL is missing.")
        sys.exit(1)

    print(f"Connecting to MongoDB...")
    client = MongoClient(settings.MONGO_DB_URL)
    db = client[settings.DB_NAME]
    
    collections = [
        "products_deposit",
        "products_saving",
        "products_annuity",
        "products_fsc_fund",
        "products_fund_kvic"
    ]
    
    for col_name in collections:
        create_vector_index(db, col_name)
        vectorize_collection(db, col_name)
        
    print("Vectorization complete!")

if __name__ == "__main__":
    main()
