"""
스트리밍 챗봇 서비스
LangGraph 기반 대화형 금융상품 추천 챗봇
"""
from typing import List, Dict, Optional
from datetime import datetime
from pymongo import MongoClient
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
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


class ChatbotService:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.3,
            streaming=True
        )
        
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_logs_collection = self.db["chat_logs"]
        self.chat_history_collection = self.db["chat_history"]
        
        # Vector Search Tools
        self.tools = self._create_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # LangGraph Agent
        self.agent_graph = self._create_agent_graph()
    
    def _create_tools(self):
        """Vector Search 도구 생성"""
        from langchain_core.tools import tool
        
        @tool
        def search_deposits(query: str) -> str:
            """정기예금 상품을 검색합니다."""
            retriever = deposit_vector_store.as_retriever(
                search_kwargs={'k': 2, 'pre_filter': {'product_type': 'deposit'}}
            )
            docs = retriever.get_relevant_documents(query)
            results = []
            for doc in docs:
                doc_id = doc.metadata.get('_id', 'unknown')
                results.append(f"[ID:{doc_id}] {doc.page_content}")
            return "\n\n".join(results)
        
        @tool
        def search_savings(query: str) -> str:
            """적금 상품을 검색합니다."""
            retriever = saving_vector_store.as_retriever(
                search_kwargs={'k': 2, 'pre_filter': {'product_type': 'saving'}}
            )
            docs = retriever.get_relevant_documents(query)
            results = []
            for doc in docs:
                doc_id = doc.metadata.get('_id', 'unknown')
                results.append(f"[ID:{doc_id}] {doc.page_content}")
            return "\n\n".join(results)
        
        @tool
        def search_annuities(query: str) -> str:
            """연금저축 상품을 검색합니다."""
            retriever = annuity_vector_store.as_retriever(search_kwargs={'k': 2})
            docs = retriever.get_relevant_documents(query)
            results = []
            for doc in docs:
                doc_id = doc.metadata.get('_id', 'unknown')
                results.append(f"[ID:{doc_id}] {doc.page_content}")
            return "\n\n".join(results)
        
        @tool
        def search_funds(query: str) -> str:
            """펀드 상품을 검색합니다."""
            retriever = fund_vector_store.as_retriever(search_kwargs={'k': 2})
            docs = retriever.get_relevant_documents(query)
            results = []
            for doc in docs:
                doc_id = doc.metadata.get('_id', 'unknown')
                results.append(f"[ID:{doc_id}] {doc.page_content}")
            return "\n\n".join(results)
        
        return [search_deposits, search_savings, search_annuities, search_funds]
    
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
        """스트리밍 챗봇 응답 (실제 LLM 스트리밍)"""
        
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
        
        # 4. 시스템 프롬프트 (사용자 컨텍스트 포함)
        system_prompt = f"""
당신은 금융상품 추천 전문가 '노후하우'입니다.

[사용자 프로필]
{user_context}

위 사용자 프로필을 참고하여, 사용자의 질문에 대해 적절한 금융상품(예금, 적금, 연금, 펀드)을 추천하고 설명해주세요.
상품 추천 시 [ID:xxx] 형태로 제공된 product_id를 포함해주세요.
금융상품과 관련 없는 질문에는 답변하지 마세요.
"""
        
        # 5. 메시지 구성
        messages = [
            SystemMessage(content=system_prompt)
        ] + history + [HumanMessage(content=message)]
        
        # 6. 사용자 메시지 저장
        self.save_message(user_id, session_id, "user", message)
        
        # 7. LLM 스트리밍
        full_response = ""
        
        try:
            # 실제 LLM 스트리밍 사용
            async for chunk in self.llm.astream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    token = chunk.content
                    full_response += token
                    yield {
                        "type": "token",
                        "content": token
                    }
            
            # 8. AI 응답 저장
            self.save_message(user_id, session_id, "assistant", full_response)
            
            # 9. 완료 신호
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
