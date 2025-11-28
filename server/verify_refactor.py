import asyncio
import os
import sys
import json

# Add server directory to sys.path
sys.path.append(os.path.abspath("c:/fisa/final-project/main-project-ai/server"))

from app.services.search_tools import search_deposits
from app.services.rag_service import rag_service
from app.services.chatbot_service import chatbot_service

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

async def test_rag_service():
    log("\n--- Testing RAG Service (Feature 1) ---")
    user_id = 1  # Assuming user 1 exists or will be mocked/created
    try:
        response = await rag_service.get_recommendations(user_id)
        log(f"[PASS] RAG Response: {response}")
        if response.deposit_or_saving:
            log(f"   - Deposit/Saving: {response.deposit_or_saving.product_name}")
        if response.annuity:
            log(f"   - Annuity: {response.annuity.product_name}")
        if response.fund:
            log(f"   - Fund: {response.fund.product_name}")
    except Exception as e:
        log(f"[FAIL] RAG Service: {e}")

async def test_chatbot_service():
    log("\n--- Testing Chatbot Service (Feature 2) ---")
    user_id = 1
    session_id = "test_session"
    message = "연금저축 상품 추천해줘"
    
    log(f"User Message: {message}")
    log("Streaming Response:")
    
    try:
        async for chunk in chatbot_service.stream_chat(user_id, session_id, message):
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
    except Exception as e:
        log(f"\n[FAIL] Chatbot Service: {e}")

async def main():
    # Clear log file
    with open("verify_log.txt", "w", encoding="utf-8") as f:
        f.write("Verification Log\n")
        
    await test_search_tools()
    await test_rag_service()
    await test_chatbot_service()

if __name__ == "__main__":
    asyncio.run(main())
