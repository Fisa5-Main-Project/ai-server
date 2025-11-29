"""
스트리밍 챗봇 서비스
LangGraph 기반 대화형 금융상품 추천 챗봇
"""
from typing import List, Dict, Optional
from datetime import datetime
from pymongo import MongoClient
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated, Sequence
import operator
import json

from app.core.config import settings
from app.db.vector_store import (
    deposit_vector_store, saving_vector_store,
    annuity_vector_store, fund_vector_store
)
from app.services.user_vectorization_service import user_vectorization_service
from app.services.products_service import products_service
from app.services.search_tools import SEARCH_TOOLS
from app.models.chatbot_models import ChatStreamChunk, ChatProduct


from app.core.llm_factory import get_llm

class ChatbotService:
    def __init__(self):
        self.llm = get_llm(temperature=0.3, streaming=True)
        
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_logs_collection = self.db["chat_logs"]
        self.chat_history_collection = self.db["chat_history"]
        
        # Vector Search Tools (Shared)
        self.tools = SEARCH_TOOLS
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # LangGraph Agent
        self.agent_graph = self._create_agent_graph()
    
    # _create_tools removed (using shared SEARCH_TOOLS)
    
    def _create_agent_graph(self):
        """LangGraph Agent 생성"""
        class AgentState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], operator.add]
        
        def agent_node(state: AgentState):
            messages = state["messages"]
            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}
        
        def should_continue(state: AgentState):
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "continue"
            return "end"
        
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"continue": "tools", "end": END}
        )
        workflow.add_edge("tools", "agent")
        
        return workflow.compile()
    
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
                    from sqlalchemy import create_engine, text
                    engine = create_engine(settings.MYSQL_DB_URL)
                    
                    with engine.connect() as conn:
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
        """대화 히스토리 가져오기"""
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
        """금융상품 관련 질문인지 판단 (강화된 검증)"""
        financial_keywords = [
            "예금", "적금", "연금", "펀드", "투자", "저축", "금리", "수익",
            "은퇴", "노후", "자산", "재테크", "금융", "상품", "추천",
            "보험", "ETF", "채권", "주식", "ISA", "IRP", "CMA", "MMDA",
            "세금", "세액공제", "비과세", "이자", "배당", "수수료",
            "만기", "가입", "해지", "상담", "은행", "증권", "포트폴리오",
            "목돈", "굴리기", "모으기", "불리기", "노후준비", "은퇴자금"
        ]
        
        # 키워드 매칭
        has_financial_keyword = any(keyword in message for keyword in financial_keywords)
        
        # 비금융 키워드 (더 명확한 거부)
        non_financial_keywords = [
            "날씨", "맛집", "영화", "음악", "게임", "스포츠",
            "뉴스", "정치", "연예", "여행지", "농담", "유머",
            "오늘 뭐 먹지", "심심해", "놀아줘"
        ]
        has_non_financial = any(keyword in message for keyword in non_financial_keywords)
        
        return has_financial_keyword and not has_non_financial
    
    async def stream_chat(
        self,
        user_id: int,
        session_id: str,
        message: str,
        keywords: Optional[List[int]] = None
    ):
        """스트리밍 챗봇 응답 (실제 LLM 스트리밍 + RAG 추천)"""
        
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
            random_terms = ["ETF", "채권", "ISA", "IRP", "CMA", "MMDA"]
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

        # 6. 시스템 프롬프트 구성
        system_prompt = f"""
당신은 금융상품 추천 전문가 '노후하우'입니다.

[사용자 프로필]
{user_context}

[추천된 상품 정보]
{json.dumps(simple_products, ensure_ascii=False) if simple_products else "없음"}

위 사용자 프로필과 추천된 상품 정보를 참고하여, 사용자의 질문에 대해 친절하게 답변해주세요.
추천된 상품이 있다면 그 상품들의 특징을 자연스럽게 언급하며 추천 이유를 설명해주세요.
금융상품과 관련 없는 질문에는 답변하지 마세요.

[중요: 상품 정보 기반 답변 원칙]
1. **반드시 [추천된 상품 정보]에 있는 상품만 언급하세요.**
2. **절대로 [추천된 상품 정보]에 없는 상품을 지어내거나 언급하지 마세요.**
3. 만약 사용자가 특정 금융사(예: 우리은행)를 요청했으나 [추천된 상품 정보]에 해당 금융사 상품이 없다면, "죄송합니다. 요청하신 금융사의 상품은 찾지 못했지만, 대신 고객님께 적합한 다른 상품들을 추천해 드립니다."라고 솔직하게 말하고, **실제로 [추천된 상품 정보]에 있는 상품(예: 경남은행, 부산은행 등)을 소개하세요.**
4. **텍스트 답변에 언급하는 상품명은 반드시 [추천된 상품 정보]의 'name' 필드와 정확히 일치해야 합니다.**
5. 답변에서 "우리은행 상품을 추천합니다"라고 말해놓고 실제로는 다른 은행 상품을 설명하면 안 됩니다. 솔직하게 "다른 은행 상품"이라고 말하세요.
6. **텍스트 답변에 언급하는 금융사명은 반드시 [추천된 상품 정보]의 'company' 필드와 정확히 일치해야 합니다.**

[특별 지침]
1. **'처음으로' 요청 시**: "네, 처음으로 돌아가겠습니다. 궁금한 점이 있으시면 언제든지 물어봐주세요."라고 답변하고, 추천 키워드에 금융 용어 질문(예: "ETF가 뭔가요?", "ISA란?")을 포함하세요.
2. **'상담' 관련 요청 시**: "전문가와의 상담을 원하시면 아래 링크를 통해 예약하실 수 있습니다."라고 안내하고, 링크(https://spot.wooribank.com/pot/Dream?withyou=CQCSD0008)를 제공하세요.
3. **'다른 상품 추천' 요청 시**: 이전 추천과 다른 새로운 상품을 제안하거나, 사용자의 의도를 파악하여 적절한 대안을 제시하세요.

[중요: 답변 형식]
1. **답변은 모바일 환경에 맞춰 최대한 간결하고 핵심만 작성하세요.** (장황한 설명 지양)
2. 답변은 마크다운(Markdown) 형식을 사용하여 가독성 있게 작성하세요. (볼드체, 리스트, 표 등 활용)
3. 답변의 맨 마지막 줄에 **[KEYWORDS: ...]** 태그를 사용하여 추천 키워드를 작성해주세요.
   - **기본 키워드**: '다른 상품 추천', '가입 방법', '처음으로'를 반드시 포함하세요.
   - **확장 키워드 (중요)**: 답변 내용에 언급된 금융 용어, 상품 특징, 또는 사용자가 이어서 궁금해할 만한 개념을 **질문 형태**로 2개 이상 추가하세요. (개수 제한 없음, 4개~6개 권장)
   - **목표**: 사용자가 키워드를 클릭하며 지식을 확장해 나갈 수 있도록("신경망처럼") 유도하세요.
   - **단, '처음으로' 요청 시에는 ['예금/적금 추천', '연금저축 추천', '금융 지식 알아보기']와 같이 초기 키워드만 제시하세요.**
   
   FORMAT: [KEYWORDS: 키워드1, 키워드2, 키워드3, 키워드4, ...]
   예시: [KEYWORDS: 다른 상품 추천, 가입 방법, 처음으로, TDF란?, 비보장 상품이란?, EFT란?]
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
            import re
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
            
            # 9-3. 추천 키워드 전송
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


chatbot_service = ChatbotService()
