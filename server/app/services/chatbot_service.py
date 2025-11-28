"""
스트리밍 챗봇 서비스 로직
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
from app.services.rag_service import rag_service
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
            "세금", "세액공제", "비과세", "이자", "배당", "수수료"
        ]
        
        # 키워드 매칭
        has_financial_keyword = any(keyword in message for keyword in financial_keywords)
        
        # 비금융 키워드 (더 명확한 거부)
        non_financial_keywords = [
            "날씨", "맛집", "영화", "음악", "게임", "스포츠",
            "뉴스", "정치", "연예", "여행지"
        ]
        has_non_financial = any(keyword in message for keyword in non_financial_keywords)
        
        return has_financial_keyword or not has_non_financial
    
    async def stream_chat(
        self,
        user_id: int,
        session_id: str,
        message: str,
        keywords: Optional[List[int]] = None
    ):
        """스트리밍 챗봇 응답 (실제 LLM 스트리밍 + RAG 추천)"""
        
        # 1. 금융상품 질문 검증
        if not self.is_financial_question(message):
            yield {
                "type": "error",
                "content": "죄송합니다. 저는 금융상품 추천 전문 AI입니다. 예금, 적금, 연금, 펀드 등 금융상품에 대해 질문해주세요."
            }
            return
        
        # 2. 사용자 컨텍스트 로딩
        user_context = self.get_user_context(user_id, keywords)
        
        # 3. 대화 히스토리 가져오기
        history = self.get_chat_history(user_id, session_id)
        
        # 4. 추천 요청 감지 (단순 키워드 기반)
        is_recommendation = "추천" in message or "상품" in message
        
        products: List[ChatProduct] = []
        
        # 5. 추천 요청인 경우 RAG 서비스 호출
        if is_recommendation:
            try:
                # RAG 서비스를 통해 추천 상품 가져오기
                products = await rag_service.get_chat_products(user_id)
            except Exception as e:
                print(f"RAG 추천 실패: {e}")
                # 실패해도 대화는 계속 진행
        
        # 6. 시스템 프롬프트 구성
        system_prompt = f"""
당신은 금융상품 추천 전문가 '노후하우'입니다.

[사용자 프로필]
{user_context}

[추천된 상품 정보]
{json.dumps([p.dict() for p in products], ensure_ascii=False) if products else "없음"}

위 사용자 프로필과 추천된 상품 정보를 참고하여, 사용자의 질문에 대해 친절하게 답변해주세요.
추천된 상품이 있다면 그 상품들의 특징을 자연스럽게 언급하며 추천 이유를 설명해주세요.
금융상품과 관련 없는 질문에는 답변하지 마세요.
"""
        
        # 7. 메시지 구성
        messages = [
            SystemMessage(content=system_prompt)
        ] + history + [HumanMessage(content=message)]
        
        # 8. 사용자 메시지 저장
        self.save_message(user_id, session_id, "user", message)
        
        # 9. LLM 스트리밍 및 응답 생성
        full_response = ""
        
        try:
            # 9-1. 텍스트 스트리밍
            async for chunk in self.llm.astream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    token = chunk.content
                    full_response += token
                    yield {
                        "type": "token",
                        "content": token
                    }
            
            # 9-2. 상품 정보 전송 (있는 경우)
            if products:
                yield {
                    "type": "products",
                    "products": [p.dict() for p in products]
                }
            
            # 9-3. 추천 키워드 전송 (고정 또는 동적 생성 가능)
            suggested_keywords = ["다른 상품 추천", "상담 종료"]
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
