import os
import sys
import logging

# Add plugins folder to path so we can import etl_utils
sys.path.append(os.path.join(os.path.dirname(__file__), '../plugins'))

from etl_utils import get_voyage_embeddings, load_to_mongo

# Mock Variable for testing if running outside Airflow
try:
    from airflow.models.variable import Variable
except ImportError:
    class Variable:
        @staticmethod
        def get(key):
            return os.getenv(key)

def test_embedding():
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        print("SKIPPING: VOYAGE_API_KEY not found in environment.")
        return

    print("Testing Voyage AI Embedding...")
    texts = ["This is a test sentence for embedding.", "금융 상품에 대한 설명입니다."]
    
    try:
        embeddings = get_voyage_embeddings(texts, api_key)
        if len(embeddings) == 2 and len(embeddings[0]) > 0:
            print(f"SUCCESS: Generated {len(embeddings)} embeddings. Dimension: {len(embeddings[0])}")
        else:
            print("FAILURE: Embeddings generated but count or dimension is wrong.")
    except Exception as e:
        print(f"FAILURE: Embedding generation failed: {e}")

if __name__ == "__main__":
    test_embedding()
