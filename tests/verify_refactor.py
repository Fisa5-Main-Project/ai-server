import asyncio
import os
import sys
import json
from datetime import datetime

# Add server directory to sys.path
# Add server directory to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.services.search_tools import search_deposits
from app.services.products_service import products_service
from app.services.chat_service import chat_service

# Custom print function to log to file
def log(message, end="\n"):
    print(message, end=end)
    with open("verify_log.txt", "a", encoding="utf-8") as f:
        f.write(message + end)

async def test_search_tools():
    log("\n--- Testing Search Tools ---")
    try:
        result = await search_deposits.ainvoke("정기예금 추천해줘")
        log(f"[PASS] search_deposits returned {len(result)} chars")
    except Exception as e:
        log(f"[FAIL] search_deposits: {e}")

async def test_products_service():
    log("\n--- Testing Products Service (Feature 1) ---")
    user_id = 1  # Assuming user 1 exists or will be mocked/created
    try:
        # 1. 추천 로직 검증
        response = await products_service.get_recommendations(user_id)
        log(f"[PASS] Products Response: {response}")
        if response.deposit_or_saving:
            log(f"   - Deposit/Saving: {response.deposit_or_saving.product_name}")
        if response.annuity:
            log(f"   - Annuity: {response.annuity.product_name}")
        if response.fund:
            log(f"   - Fund: {response.fund.product_name}")
            
        # 2. ChatProduct 변환 및 링크 검증
        chat_products = await products_service.get_chat_products(user_id)
        log(f"변환된 ChatProduct 개수: {len(chat_products)}")
        
        if chat_products:
            first_product = chat_products[0]
            log(f"첫 번째 상품: {first_product.name} ({first_product.bank})")
            log(f"핵심 속성(stat/benefit): {first_product.stat}")
            
            if first_product.link:
                log(f"링크: {first_product.link}")
                if "search.naver.com" not in first_product.link:
                     log("[PASS] Official link generated (not Naver search)")
                else:
                     log("[WARN] Still using Naver search link (might be intended if no mapping found)")
            else:
                log("[FAIL] Link missing")
                
    except Exception as e:
        log(f"[FAIL] Products Service: {e}")
        import traceback
        traceback.print_exc()

async def test_chatbot_service():
    log("\n--- Testing Chatbot Service (Feature 2) ---")
    user_id = 1
    session_id = "test_session_v2"
    message = "연금저축 상품 추천해줘"
    
    log(f"User Message: {message}")
    log("Streaming Response:")
    
    try:
        async for chunk in chat_service.stream_chat(user_id, session_id, message):
            if chunk["type"] == "token":
                # Don't log every token to file to keep it clean, or log a dot
                print(chunk["content"], end="", flush=True)
            elif chunk["type"] == "products":
                log(f"\n\n[PRODUCTS RECEIVED]: {len(chunk['products'])} items")
            elif chunk["type"] == "keywords":
                log(f"\n[KEYWORDS RECEIVED]: {chunk['keywords']}")
            elif chunk["type"] == "done":
                log("\n[DONE]")
            elif chunk["type"] == "error":
                log(f"\n[ERROR] {chunk['content']}")
                
        # Test History
        log("\n--- Testing Chat History ---")
        history_docs = chat_service.chat_history_collection.find(
            {"user_id": user_id, "session_id": session_id}
        ).sort("timestamp", 1)
        
        count = 0
        for doc in history_docs:
            count += 1
            log(f"[{doc['role']}] {doc['content'][:30]}...")
            
        if count > 0:
            log(f"[PASS] History saved {count} messages")
        else:
            log("[FAIL] No history found")
            
    except Exception as e:
        log(f"\n[FAIL] Chatbot Service: {e}")

async def main():
    # Clear log file
    with open("verify_log.txt", "w", encoding="utf-8") as f:
        f.write(f"Verification Log - {datetime.now()}\n")
        
    await test_search_tools()
    await test_products_service()
    await test_chatbot_service()

if __name__ == "__main__":
    asyncio.run(main())
