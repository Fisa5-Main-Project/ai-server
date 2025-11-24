import os
import sys
import time
from pymongo import MongoClient
from langchain_voyageai import VoyageAIEmbeddings
from dotenv import load_dotenv

# Add server directory to sys.path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables
load_dotenv()

# Initialize Embedding Model
embeddings = VoyageAIEmbeddings(
    model="voyage-large-2",
    voyage_api_key=os.getenv("VOYAGE_API_KEY") 
)

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
                    "numDimensions": 1024,
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
            time.sleep(1)
            
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
    MONGO_DB_URL = os.getenv("MONGO_DB_URL")
    DB_NAME = os.getenv("DB_NAME", "financial_products")
    VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

    if not MONGO_DB_URL:
        print("Error: MONGO_DB_URL is missing.")
        sys.exit(1)

    if not VOYAGE_API_KEY or VOYAGE_API_KEY == "YOUR_VOYAGE_API_KEY":
        print("Error: VOYAGE_API_KEY is missing or not set.")
        sys.exit(1)

    print(f"Connecting to MongoDB at {MONGO_DB_URL}...")
    client = MongoClient(MONGO_DB_URL)
    db = client[DB_NAME]
    
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
