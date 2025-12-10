import asyncio
import csv
import sys
import os
import io
import json
import time 
from datetime import datetime

# Add server directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(server_dir)

from app.services.chat_service import chat_service
import app.services.products_service as products_service_module

# Mock User Context to allow dynamic personas from CSV
original_get_user_context = chat_service.get_user_context

# Mock Vectorization Service (to bypass MongoDB/MySQL lookup for User 12345)
# We need to mock user_vectorization_service.user_vectors_collection.find_one

from unittest.mock import MagicMock

def mock_get_context_factory(persona_text):
    def mock_get_user_context(user_id, keywords=None):
        return persona_text
    
    # Also mock products_service's dependency
    mock_collection = MagicMock()
    # user_id is not available here, but since the test runner uses user_id=12345,
    # and the important part is returning the persona, we can use a dummy ID.
    mock_collection.find_one.return_value = {
        "persona_text": persona_text,
        "_id": "user_mock" 
    }
    
    # Patch the module-level variable in app.services.products_service
    products_service_module.user_vectorization_service.user_vectors_collection = mock_collection
    
    return mock_get_user_context

async def run_evaluation():
    input_file = os.path.join(current_dir, "rag_test_cases.csv")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = f"rag_eval_result_{timestamp}.csv"
    output_file = os.path.join(current_dir, output_filename)

    results = []
    
    # Validation Statistics
    total_cases = 0
    passed_cases = 0
    
    # Recall Statistics (Only for Recommendation cases)
    recall_targets = [1, 3, 5]
    recall_sums = {k: 0 for k in recall_targets}
    recall_counts = 0

    print(f"Starting RAG Evaluation using {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        total_cases = len(rows)
        
        for idx, row in enumerate(rows):
            print(f"[{idx+1}/{total_cases}] Running {row['id']} ({row['category']})...")
            
            # Rate Limit Prevention
            if idx > 0:
                time.sleep(2) 
            
            # 1. Setup Context (Mock Persona)
            # This factory now mocks BOTH chat_service.get_user_context AND products_service's DB lookup
            chat_service.get_user_context = mock_get_context_factory(row['persona'])
            
            # 2. Run Chat
            user_id = 12345
            session_id = f"test_{row['id']}_{datetime.now().timestamp()}"
            query = row['query']
            
            accumulated_text = ""
            collected_products = []
            found_navigation = False
            error_occurred = False
            
            try:
                async for chunk in chat_service.stream_chat(user_id, session_id, query):
                    if chunk['type'] == 'done':
                        accumulated_text = chunk['content']
                    elif chunk['type'] == 'products':
                        collected_products = chunk['products']
                    elif chunk['type'] == 'feature_guide':
                        found_navigation = True
                    elif chunk['type'] == 'error':
                        accumulated_text = chunk['content']
                        error_occurred = True
            except Exception as e:
                accumulated_text = f"EXCEPTION: {str(e)}"
                error_occurred = True
                
            # 3. Evaluate Pass/Fail (Accuracy)
            passed = True
            fail_reasons = []
            
            # A. Intent Check
            exp_intent = row['expected_intent']
            if exp_intent == 'recommendation' and not collected_products:
                passed = False
                fail_reasons.append("No Products Found")
            elif exp_intent == 'navigation' and not found_navigation:
                passed = False
                fail_reasons.append("No Navigation Guide")
            elif exp_intent == 'blocking' and collected_products:
                 # Strict check: Blocking shouldn't return products
                 # passed = False 
                 # fail_reasons.append("Unexpected Products")
                 pass

            # B. Keyword Check (Positive)
            expected_kws = [k.strip() for k in row['expected_keywords'].split(',') if k.strip()]
            if expected_kws:
                # Check regular text response
                text_match = any(kw in accumulated_text for kw in expected_kws)
                # Check product names/banks if products exist
                prod_match = False
                if collected_products:
                    for p in collected_products:
                        # p is a dict from p.dict() or object
                        p_name = p.get('name', '') if isinstance(p, dict) else p.name
                        p_bank = p.get('bank', '') if isinstance(p, dict) else p.bank
                        if any(kw in p_name or kw in p_bank for kw in expected_kws):
                            prod_match = True
                            break
                
                if not (text_match or prod_match):
                    passed = False
                    fail_reasons.append(f"Missing Keywords: {expected_kws}")

            # C. Keyword Check (Negative)
            if row['forbidden_keywords']:
                for kw in row['forbidden_keywords'].split(','):
                    kw = kw.strip()
                    if kw and kw in accumulated_text:
                        passed = False
                        fail_reasons.append(f"Found Forbidden '{kw}'")
            
            if passed:
                passed_cases += 1

            # 4. Evaluate Recall@K (Only for Recommendation/Specific Search)
            recalls = {k: "N/A" for k in recall_targets}
            if exp_intent == 'recommendation' or row['category'] == 'Specific_Search':
                recall_counts += 1
                # Ground Truth: 'expected_keywords' must match at least one product in top K
                # We assume if the keyword (e.g., "Woori", "Deposit") is in the product, it's a Hit.
                
                for k in recall_targets:
                    # Check top K products
                    top_k_products = collected_products[:k]
                    hit = 0
                    for p in top_k_products:
                        p_name = p.get('name', '') if isinstance(p, dict) else p.name
                        p_bank = p.get('bank', '') if isinstance(p, dict) else p.bank
                        # Check strict inclusion of ANY expected keyword
                        if any(kw in p_name or kw in p_bank for kw in expected_kws):
                            hit = 1
                            break
                    
                    recalls[k] = hit
                    recall_sums[k] += hit

            # Result Row
            results.append({
                "id": row['id'],
                "category": row['category'],
                "query": query,
                "passed": "PASS" if passed else "FAIL",
                "recall_1": recalls.get(1),
                "recall_3": recalls.get(3),
                "recall_5": recalls.get(5),
                "reason": ", ".join(fail_reasons),
                "response_preview": accumulated_text[:50].replace("\n", " ") + "...",
                "num_products": len(collected_products)
            })

    # Restore
    chat_service.get_user_context = original_get_user_context

    # 5. Save Report
    keys = results[0].keys()
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
        
    print(f"\nEvaluation Complete! Results saved to {output_filename}")
    
    # 6. Print Summary Stats
    accuracy = (passed_cases / total_cases) * 100 if total_cases > 0 else 0
    print(f"\n=== Summary Report ===")
    print(f"Total Cases: {total_cases}")
    print(f"Accuracy: {accuracy:.2f}% ({passed_cases}/{total_cases})")
    
    if recall_counts > 0:
        print(f"\n=== Retrieval Performance (Recall@K) ===")
        print(f"Evaluated on {recall_counts} recommendation queries.")
        for k in recall_targets:
            avg_recall = (recall_sums[k] / recall_counts) * 100
            print(f"Recall@{k}: {avg_recall:.2f}%")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
