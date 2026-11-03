"""
스트리밍 챗봇 서비스
LangGraph 기반 대화형 금융상품 추천 챗봇
"""
from typing import List, Dict, Optional
from datetime import datetime
from pymongo import MongoClient
import asyncio
from sqlalchemy import create_engine, text

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.core.config import settings
from app.services.user_vectorization_service import user_vectorization_service
from app.services.products_service import products_service

class ChatService:
    def __init__(self):
        
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_logs_collection = self.db["chat_logs"]
        self.chat_history_collection = self.db["chat_history"]
        
        # MySQL Engine (Reuse)
        self.mysql_engine = create_engine(settings.MYSQL_DB_URL)
        
        
    def get_user_context(self, user_id: int, keywords: Optional[List[int]] = None) -> str:
        """사용자 컨텍스트 생성 (페르소나 + 추가 키워드)"""
        # 임베딩 완료를 기다리지 않고 최신 원천 상태로 페르소나 생성
        persona = user_vectorization_service.get_current_persona(user_id)
        
        if persona:
            context = persona
            
            # 추가 키워드가 있다면 포함
            if keywords:
                try:
                    with self.mysql_engine.connect() as conn:
                        keyword_names = []
                        for keyword_id in keywords:
                            result = conn.execute(
                                text("SELECT name FROM keyword WHERE keyword_id = :kid"),
                                {"kid": keyword_id}
                            ).first()
                            if result:
                                keyword_names.append(result[0])
                        
                        if keyword_names:
                            context += f" 추가 관심 키워드: {', '.join(keyword_names)}"
                except Exception as e:
                    print(f"키워드 조회 실패: {e}")
            
            return context
        else:
            # 페르소나가 없는 경우 기본 메시지
            return "사용자의 금융 상황을 알려주시면 더 정확한 추천을 해드릴 수 있습니다."
    
    def get_chat_history(self, user_id: int, session_id: str, limit: int = 10) -> List[BaseMessage]:
        """대화 히스토리 가져오기 (LLM Context용)"""
        history_docs = self.chat_history_collection.find(
            {"user_id": user_id, "session_id": session_id}
        ).sort("timestamp", -1).limit(limit)
        
        messages = []
        for doc in reversed(list(history_docs)):
            if doc["role"] == "user":
                messages.append(HumanMessage(content=doc["content"]))
            else:
                messages.append(AIMessage(content=doc["content"]))
        
        return messages

    def get_paginated_chat_history(self, user_id: int, session_id: str, limit: int, skip: int) -> list:
        """대화 히스토리 조회 (API 반환용, 페이지네이션)"""
        history_docs = self.chat_history_collection.find(
            {"user_id": user_id, "session_id": session_id}
        ).sort("timestamp", -1).skip(skip).limit(limit)
        
        history = []
        for doc in history_docs:
            history.append({
                "role": doc["role"],
                "content": doc["content"],
                "timestamp": doc["timestamp"].isoformat()
            })
            
        return history[::-1]
    
    def save_message(self, user_id: int, session_id: str, role: str, content: str):
        """메시지 저장"""
        self.chat_history_collection.insert_one({
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        })
    
    def is_financial_question(self, message: str) -> bool:
        #금융상품 관련 질문인지 판단
        financial_keywords = [
            "예금", "적금", "연금", "펀드", "투자", "저축", "금리", "수익",
            "은퇴", "노후", "자산", "재테크", "금융", "상품", "추천",
            "보험", "ETF", "채권", "주식", "ISA", "IRP", "CMA", "MMDA",
            "계좌", "뱅킹", "대출", "신용", "카드", "보험", "대출",
            "인터넷 뱅킹", "카드", 
            "세금", "세액공제", "비과세", "이자", "배당", "수수료",
            "만기", "가입", "해지", "상담", "은행", "증권", "포트폴리오",
            "목돈", "굴리기", "모으기", "불리기", "노후준비", "은퇴자금",
            "일자리", "취업", "알바", "구직", "채용"
        ]
        
        # 키워드 매칭
        has_financial_keyword = any(keyword in message for keyword in financial_keywords)
        
        # 비금융 키워드 
        non_financial_keywords = [
            "날씨", "맛집", "영화", "음악", "게임", "스포츠",
            "뉴스", "정치", "연예", "여행지", "농담", "유머",
            "오늘 뭐 먹지", "심심해", "놀아줘"
        ]
        has_non_financial = any(keyword in message for keyword in non_financial_keywords)
        
        return has_financial_keyword and not has_non_financial
    
    def check_feature_navigation(self, message: str) -> Optional[Dict]:
        """특정 키워드에 따른 기능 이동 가이드 확인"""
        message = message.lower()
        
        # 1. 퇴직연금 (Pension)
        if any(k in message for k in ["퇴직연금", "연금저축", "연금 추천", "pension", "연금 저축", "퇴직", "연금",]):
            return {
                "type": "feature_guide",
                "title": "퇴직연금 맞춤 관리",
                "description": "세액공제 혜택과 노후 준비를 동시에! 나에게 딱 맞는 퇴직연금 포트폴리오를 확인해보세요.",
                "benefit": "세액공제 혜택",
                "link": "/pension",
                "button_text": "은퇴 후 자금 진단하기"
            }
            
        # 2. 상속/증여/신탁 (Inheritance)
        if any(k in message for k in ["신탁", "irp", "db", "dc", "isa", "상속", "증여"]):
            return {
                "type": "feature_guide",
                "title": "스마트한 유산 관리 & 상속",
                "description": "ISA, IRP부터 상속/증여 시뮬레이션까지. 나에게 딱 맞는 유산 관리 플랜을 확인해보세요.",
                "benefit": "절세 효과 및 체계적인 자산 승계 플랜",
                "link": "/inheritance",
                "button_text": "안전한 상속 관리하기"
            }
            
        # 3. 일자리/위치 (Job/Location)
        if any(k in message for k in ["일자리", "소일거리", "취업", "알바", "근처", "위치"]):
            return {
                "type": "feature_guide",
                "title": "내 주변 일자리 찾기",
                "description": "시니어/중장년을 위한 주변의 맞춤형 일자리 정보를 쉽고 빠르게 찾아보세요.",
                "benefit": "위치 기반 실시간 채용 정보 제공",
                "link": "/job/location",
                "button_text": "인생 일자리 찾으러 가기"
            }
            
        return None

    # 보안 공격 차단
    MAX_MESSAGE_LENGTH = 1000
    INJECTION_KEYWORDS = [
        "ignore previous instructions", "system prompt", "시스템 프롬프트",
        "ignore all instructions", "forget everything", "무시해",
        "you are not", "당신은 이제부터", "DAN mode",
        "os.environ", "environ", "os.", "sys.", "subprocess", "print(", "exec(",
        "API KEY", "SECRET", "credential", "password", "auth token",
        "developer mode", "simul game", "roleplay as root"
    ]

    def validate_input(self, message: str) -> Optional[str]:
        """AI 입력 유효성 검사 (Prompt Injection 방지)"""
        # 1. 길이 제한
        if len(message) > self.MAX_MESSAGE_LENGTH:
            return f"질문이 너무 깁니다. {self.MAX_MESSAGE_LENGTH}자 이내로 입력해주세요."
            
        # 2. Prompt Injection 키워드 필터링
        message_lower = message.lower()
        for keyword in self.INJECTION_KEYWORDS:
            if keyword in message_lower:
                return "부적절한 요청이 감지되었습니다. 금융 상품 관련 질문만 해주세요."
                
        return None

    async def stream_chat(
        self,
        user_id: int,
        session_id: str,
        message: str,
        keywords: Optional[List[int]] = None
    ):
        """스트리밍 챗봇 응답 (실제 LLM 스트리밍 + RAG 추천)"""
        
        # 0. 보안 검증
        validation_error = self.validate_input(message)
        if validation_error:
            yield {
                "type": "error",
                "content": validation_error
            }
            return

        # 1. 금융상품 질문 검증 (그만 물어보기 예외 처리)
        if message == "그만 물어보기":
            yield {
                "type": "token",
                "content": "네, 알겠습니다. 더 궁금한 점이 있으시면 언제든지 말씀해주세요."
            }
            yield {
                "type": "keywords",
                "keywords": ['예금/적금 추천', '연금저축 추천', '펀드 추천', '포트폴리오 점검']
            }
            yield {
                "type": "done",
                "content": "네, 알겠습니다. 더 궁금한 점이 있으시면 언제든지 말씀해주세요."
            }
            return

        if message == "처음으로":
            import random
            random_terms = ["ETF", "ISA", "IRP", "CMA", "MMDA"]
            selected_term = random.choice(random_terms)
            
            welcome_msg = "저는 금융상품 추천 전문 AI입니다. 예금, 적금, 연금, 펀드 등 금융상품이나, 금융 상품 관련 정보에 대해 질문해주세요."
            
            # 팁을 키워드로 추가
            keywords_list = ['예금/적금 추천', '연금저축 추천', '펀드 추천', '포트폴리오 점검', f"{selected_term}가 뭔가요?"]
            
            yield {
                "type": "token",
                "content": welcome_msg
            }
            yield {
                "type": "keywords",
                "keywords": keywords_list
            }
            yield {
                "type": "done",
                "content": welcome_msg
            }
            return

        # No free-form model output is permitted to introduce unvalidated products.
        from app.services.financial_education import education_answer
        educational = education_answer(message)
        feature_guide = self.check_feature_navigation(message)
        products = []
        if educational:
            content = educational
        elif any(word in message for word in ("일자리", "취업", "채용", "알바")):
            content = "일자리는 앱의 내 주변 일자리 찾기에서 조건에 맞게 확인할 수 있습니다."
        elif any(word in message for word in ("상담", "상속", "증여")):
            content = "개인별 판단이 필요한 내용입니다. 앱의 상담 또는 상속 안내 기능에서 확인해 주세요."
        elif self.is_financial_question(message):
            products = await products_service.get_chat_products(user_id, message)
            if products:
                content = "조건을 확인한 상품입니다. 각 상품은 대안이며 동시 가입을 권하는 것은 아닙니다.\n" + "\n".join(
                    f"- {p.bank} {p.name}: {p.features[0]} ({p.stat})" for p in products)
            else:
                content = "현재 요청 조건과 투자 성향에 맞고 가입 조건이 확인된 상품이 없습니다. 투자 성향과 자산 정보를 확인하거나 조건을 구체적으로 알려주세요."
        else:
            content = "예금, 적금, 연금, 펀드 중 원하는 상품과 조건을 알려주세요. 조건을 확인할 수 있는 상품만 안내합니다."
        await asyncio.to_thread(self.save_message, user_id, session_id, "user", message)
        await asyncio.to_thread(self.save_message, user_id, session_id, "assistant", content)
        yield {"type": "token", "content": content}
        if products:
            yield {"type": "products", "products": [p.model_dump() for p in products]}
        if feature_guide:
            yield feature_guide
        yield {"type": "keywords", "keywords": ["예금 추천", "적금 추천", "상담 종료"]}
        yield {"type": "done", "content": content}

    def save_feedback(self, user_id: int, session_id: str, message_id: str, feedback: str, product_id: Optional[str] = None):
        """사용자 피드백 저장"""
        self.chat_logs_collection.insert_one({
            "user_id": user_id,
            "session_id": session_id,
            "message_id": message_id,
            "product_id": product_id,
            "feedback": feedback,  # "like" or "dislike"
            "timestamp": datetime.utcnow()
        })


chat_service = ChatService()
