"""
AI 서버 API 테스트 스크립트
"""
import requests
import json
from sseclient import SSEClient  # pip install sseclient-py

BASE_URL = "http://localhost:8000/api/v1"

def test_health():
    """헬스 체크"""
    print("\n=== 1. Health Check ===")
    response = requests.get("http://localhost:8000/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")


def test_vectorize_user(user_id: int):
    """사용자 벡터화 테스트"""
    print(f"\n=== 2. Vectorize User {user_id} ===")
    response = requests.post(f"{BASE_URL}/users/{user_id}/vectorize")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")


def test_get_recommendations(user_id: int):
    """금융상품 추천 테스트"""
    print(f"\n=== 3. Get Recommendations for User {user_id} ===")
    response = requests.get(f"{BASE_URL}/recommendations/{user_id}")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")


def test_chat_stream(user_id: int, session_id: str, message: str):
    """챗봇 스트리밍 테스트"""
    print(f"\n=== 4. Chat Stream ===")
    print(f"User: {message}")
    print("AI: ", end="", flush=True)
    
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "message": message
    }
    
    response = requests.post(
        f"{BASE_URL}/chat/stream",
        json=payload,
        stream=True,
        headers={"Accept": "text/event-stream"}
    )
    
    client = SSEClient(response)
    for event in client.events():
        data = json.loads(event.data)
        
        if data["type"] == "token":
            print(data["content"], end="", flush=True)
        elif data["type"] == "done":
            print("\n[완료]")
            break
        elif data["type"] == "error":
            print(f"\n[에러] {data['content']}")
            break


def test_save_feedback(user_id: int, session_id: str):
    """피드백 저장 테스트"""
    print(f"\n=== 5. Save Feedback ===")
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "message_id": "test_msg_123",
        "feedback": "like",
        "product_id": "FSC_E6586_20251119"
    }
    
    response = requests.post(f"{BASE_URL}/chat/feedback", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")


if __name__ == "__main__":
    USER_ID = 1
    SESSION_ID = "test_session_001"
    
    try:
        # 1. 헬스 체크
        test_health()
        
        # 2. 사용자 벡터화
        test_vectorize_user(USER_ID)
        
        # 3. 금융상품 추천
        test_get_recommendations(USER_ID)
        
        # 4. 챗봇 스트리밍
        test_chat_stream(USER_ID, SESSION_ID, "안정적인 예금 상품 추천해줘")
        
        # 5. 피드백 저장
        test_save_feedback(USER_ID, SESSION_ID)
        
        print("\n✅ 모든 테스트 완료!")
    
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
