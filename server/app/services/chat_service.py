"""
스트리밍 챗봇 서비스
LangGraph 기반 대화형 금융상품 추천 챗봇
"""
from typing import List, Dict, Optional, TypedDict, Annotated, Sequence
from datetime import datetime
from pymongo import MongoClient
import operator
import json
import re
from sqlalchemy import create_engine, text

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.db.vector_store import (
    deposit_vector_store, saving_vector_store,
    annuity_vector_store, fund_vector_store
)
from app.services.user_vectorization_service import user_vectorization_service
from app.services.products_service import products_service
from app.rag.retrievers.tools import SEARCH_TOOLS
from app.schemas.chat import ChatStreamChunk, ChatProduct
from app.core.llm_factory import get_llm

class ChatService:
    def __init__(self):
        self.llm = get_llm(temperature=0.3, streaming=True)
        
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_logs_collection = self.db["chat_logs"]
        self.chat_history_collection = self.db["chat_history"]
        
        # MySQL Engine (Reuse)
        self.mysql_engine = create_engine(settings.MYSQL_DB_URL)
        
        # Vector Search Tools (Shared)
        self.tools = SEARCH_TOOLS
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
    def get_user_context(self, user_id: int, keywords: Optional[List[int]] = None) -> str:
        """사용자 컨텍스트 생성 (페르소나 + 추가 키워드)"""
        # 사용자 벡터 가져오기
        user_vector = user_vectorization_service.user_vectors_collection.find_one(
            {"_id": f"user_{user_id}"}
        )
        
        if user_vector:
            context = user_vector["persona_text"]
            
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

        if not self.is_financial_question(message):
            yield {
                "type": "error",
                "content": "저는 금융상품 추천 전문 AI입니다. 예금, 적금, 연금, 펀드 등 금융상품이나, 금융 상품 관련 정보에 대해 질문해주세요."
            }
            return
        
        # 2. 사용자 컨텍스트 로딩
        user_context = self.get_user_context(user_id, keywords)
        
        # 3. 대화 히스토리 가져오기 (컨텍스트 윈도우 관리를 위해 최근 3개만)
        history = self.get_chat_history(user_id, session_id, limit=3)
        
        # 4. 추천 요청 감지 (단순 키워드 기반)
        is_recommendation = "추천" in message or "상품" in message or "다른" in message

        products: List[ChatProduct] = []
        
        # 5. 추천 요청인 경우 RAG 서비스 호출
        if is_recommendation:
            try:
                # RAG 서비스를 통해 추천 상품 가져오기
                products = await products_service.get_chat_products(user_id, message)
            except Exception as e:
                print(f"RAG 추천 실패: {e}")
                # 실패해도 대화는 계속 진행
        
        # 6. 기능 이동 가이드 확인 (Feature Navigation)
        feature_guide = self.check_feature_navigation(message)

        # 상품 정보 간소화 (토큰 절약)
        simple_products = []
        if products:
            for p in products:
                simple_products.append({
                    "type": p.type,
                    "name": p.name,
                    "company": p.bank,
                    "benefit": p.stat,
                    "reason": p.features[0] if p.features else ""
                })

        # 7. 시스템 프롬프트 구성
        system_prompt = f"""
당신은 금융상품 추천 전문가 '노후하우'입니다.

[사용자 프로필]
{user_context}

[추천된 상품 정보]
{json.dumps(simple_products, ensure_ascii=False) if simple_products else "없음"}

위 사용자 프로필과 추천된 상품 정보를 참고하여, 사용자의 질문에 대해 친절하게 답변해주세요.
추천된 상품이 있다면 그 상품들의 특징을 자연스럽게 언급하며 추천 이유를 설명해주세요.
금융상품과 관련 없는 질문에는 답변하지 마세요. **단, 일자리/취업 관련 질문은 예외적으로 허용하며 적극적으로 답변해야 합니다.**

[중요: 상품 정보 기반 답변 원칙 - 할루시네이션 방지]
1. **반드시 [추천된 상품 정보]에 있는 상품만 언급하세요.**
2. **절대로 [추천된 상품 정보]에 없는 상품을 지어내거나, 존재하지 않는 상품을 추천하지 마세요.** (매우 중요)
3. 만약 사용자가 특정 금융사(예: 우리은행)를 요청했으나 [추천된 상품 정보]에 해당 금융사 상품이 없다면, "죄송합니다. 요청하신 금융사의 상품은 찾지 못했지만, 대신 고객님께 적합한 다른 상품들을 추천해 드립니다."라고 솔직하게 말하고, **실제로 [추천된 상품 정보]에 있는 상품을 소개하세요.**
4. **텍스트 답변에 언급하는 상품명은 반드시 [추천된 상품 정보]의 'name' 필드와 정확히 일치해야 합니다.**
5. 답변에서 "우리은행 상품을 추천합니다"라고 말해놓고 실제로는 다른 은행 상품을 설명하면 안 됩니다. 솔직하게 "다른 은행 상품"이라고 말하세요.
6. **텍스트 답변에 언급하는 금융사명은 반드시 [추천된 상품 정보]의 'company' 필드와 정확히 일치해야 합니다.**

[특별 지침]
1. **'처음으로' 요청 시**: "네, 처음으로 돌아가겠습니다. 궁금한 점이 있으시면 언제든지 물어봐주세요."라고 답변하고, 추천 키워드에 금융 용어 질문(예: "ETF가 뭔가요?", "ISA란?")을 포함하세요.
2. **'상담' 관련 요청 시**: "전문가와의 상담을 원하시면 아래 링크를 통해 예약하실 수 있습니다."라고 안내하고, 링크(https://spot.wooribank.com/pot/Dream?withyou=CQCSD0008)를 제공하세요.
3. **'다른 상품 추천' 요청 시**: 이전 추천과 다른 새로운 상품을 제안하거나, 사용자의 의도를 파악하여 적절한 대안을 제시하세요.
4. **'일자리/취업' 관련 요청 시 (중요)**: 
   - **거절하지 말고 적극적으로 답변하세요.**
   - "고객님의 안정적인 노후 준비와 자산 관리를 위해 추가적인 소득 창출도 좋은 방법입니다."와 같이 **자산 관리/평가와 연결지어 설명**하세요.
   - "저희 '내 주변 일자리 찾기' 기능을 통해 시니어/중장년을 위한 맞춤형 일자리를 확인해보실 수 있습니다."라고 안내하며 기능을 추천하세요.

[중요: 답변 형식]
1. **답변은 모바일 환경에 맞춰 최대한 간결하고 핵심만 작성하세요.** (장황한 설명 지양)
2. 답변은 마크다운(Markdown) 형식을 사용하여 가독성 있게 작성하세요. (볼드체, 리스트, 표 등 활용)
3. 답변의 맨 마지막 줄에 **[KEYWORDS: ...]** 태그를 사용하여 추천 키워드를 작성해주세요.
   - **기본 키워드**: '다른 상품 추천', '가입 방법', '처음으로'를 반드시 포함하세요.
   - **확장 키워드 (중요)**: 답변 내용에 언급된 금융 용어, 상품 특징, 또는 사용자가 이어서 궁금해할 만한 개념을 **질문 형태**로 2개 이상 추가하세요. (개수 제한 없음, 4개~6개 권장)
   - **목표**: 사용자가 키워드를 클릭하며 지식을 확장해 나갈 수 있도록("신경망처럼") 유도하세요.
   - **단, '처음으로' 요청 시에는 ['예금/적금 추천', '연금저축 추천', '금융 지식 알아보기']와 같이 초기 키워드만 제시하세요.**
   
   FORMAT: [KEYWORDS: 키워드1, 키워드2, 키워드3, 키워드4, ...]
   예시: [KEYWORDS: 다른 상품 추천, 가입 방법, 처음으로, TDF란?, 일자리 추천 받기, 비보장 상품이란?, EFT란? ]
"""

        # 7.1 포트폴리오/자산 분석 요청 감지 및 프롬프트 강화
        is_portfolio_analysis = any(k in message for k in ["자산", "포트폴리오", "내 돈", "진단", "분석", "재산"])
        if is_portfolio_analysis:
            system_prompt += """
            
            [특별 지침: 자산/포트폴리오 분석 요청 시]
            사용자가 자신의 자산 현황이나 포트폴리오 분석을 요청했습니다. 다음 지침에 따라 **'자산 포트폴리오 전문가처럼'** 분석해주세요.
            
            1. **Markdown 표 작성 (필수)**:
               - 사용자의 자산 정보를 바탕으로 [자산 종류 | 금액 | 비중(%)] 컬럼을 가진 표를 작성하세요.
               - 비중은 총 자산 대비 비율을 계산하여 표시하세요.
            
            2. **시각적 요약**:
               - 자산 구성을 한눈에 파악할 수 있도록 이모지(💰, 🏠, 📉 등)를 적극 활용하세요.
               - 예: "부동산(🏠) 비중이 높습니다."
            
            3. **전문적인 진단 및 조언 (3가지)**:
               - 사용자의 나이, 목표(은퇴 등), 투자 성향을 고려하여 앞으로의 자산 증식 방향에 대한 구체적인 조언 3가지를 제시하세요.
               - 예: "30대이시므로 공격적인 투자 비중을 10% 정도 늘리는 것을 추천합니다."
               - 예: "은퇴가 5년 남으셨으므로 현금 흐름 확보를 위해 연금 비중을 높이세요."
            
            4. **톤앤매너**:
               - 전문적인 PB(Private Banker)처럼 신뢰감 있고 명확한 어조를 사용하세요.
               - 사용자의 현재 상황을 긍정적으로 평가하되, 개선점은 명확히 짚어주세요.
            """
        
        # 7. 메시지 구성
        messages = [
            SystemMessage(content=system_prompt)
        ] + history + [HumanMessage(content=message)]
        
        # 8. 사용자 메시지 저장
        self.save_message(user_id, session_id, "user", message)
        
        # 9. LLM 스트리밍 및 응답 생성
        full_response = ""
        buffer = ""
        
        try:
            # 9-1. 텍스트 스트리밍
            async for chunk in self.llm.astream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    token = chunk.content
                    buffer += token
                    
                    # 키워드 포맷 시작 부분 감지 시 버퍼링
                    if "[KEYWORDS:" in buffer:
                        continue
                    
                    # 버퍼가 너무 커지면 출력 (잘림 방지 위해 버퍼 크기 조정 및 조건 완화)
                    if len(buffer) > 50: 
                        to_yield = buffer[:-20] # 뒤에 키워드 태그가 올 수 있으므로 일부 남김
                        buffer = buffer[-20:]
                        full_response += to_yield
                        yield {
                            "type": "token",
                            "content": to_yield
                        }
            
            # 스트림 종료 후 남은 버퍼 처리
            full_response += buffer
            
            # 키워드 추출 및 제거
            keywords_match = re.search(r'\[KEYWORDS:\s*(.*?)\]', full_response, re.DOTALL)
            suggested_keywords = ["다른 상품 추천", "상담 종료"] # 기본값
            
            if keywords_match:
                keywords_str = keywords_match.group(1)
                suggested_keywords = [k.strip() for k in keywords_str.split(',')]
                # 응답 본문에서 키워드 부분 제거
                final_content = full_response.replace(keywords_match.group(0), "").strip()
                
                # 남은 버퍼 중 키워드 부분이 아닌 것만 yield
                # 버퍼에 키워드 태그가 포함되어 있다면, 태그 전까지만 출력해야 함
                if "[KEYWORDS:" in buffer:
                    clean_buffer = buffer.split("[KEYWORDS:")[0]
                    if clean_buffer:
                         yield {
                            "type": "token",
                            "content": clean_buffer
                        }
                else:
                     yield {
                        "type": "token",
                        "content": buffer
                    }
            else:
                 # 키워드가 없으면 남은 버퍼 다 보냄
                 yield {
                    "type": "token",
                    "content": buffer
                }

            
            # 9-2. 상품 정보 전송 (있는 경우)
            if products:
                yield {
                    "type": "products",
                    "products": [p.dict() for p in products]
                }
            
            # 9-3. 기능 이동 가이드 전송 (있는 경우)
            if feature_guide:
                yield feature_guide
            
            # 9-4. 추천 키워드 전송
            yield {
                "type": "keywords",
                "keywords": suggested_keywords
            }
            
            # 10. AI 응답 저장
            self.save_message(user_id, session_id, "assistant", full_response)
            
            # 11. 완료 신호
            yield {
                "type": "done",
                "content": full_response
            }
        
        except Exception as e:
            print(f"스트리밍 오류: {e}")
            yield {
                "type": "error",
                "content": f"오류가 발생했습니다: {str(e)}"
            }
    
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
