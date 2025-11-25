"""
스트리밍 챗봇 서비스
LangGraph 기반 대화형 금융상품 추천 챗봇
"""
from typing import List, Dict, Optional
from datetime import datetime
from pymongo import MongoClient
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
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


class ChatbotService:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.3,
            streaming=True
        )
        
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.DB_NAME]
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
            return "\n\n".join([doc.page_content for doc in docs])
        
        @tool
        def search_savings(query: str) -> str:
            """적금 상품을 검색합니다."""
            retriever = saving_vector_store.as_retriever(
                search_kwargs={'k': 2, 'pre_filter': {'product_type': 'saving'}}
            )
            docs = retriever.get_relevant_documents(query)
            return "\n\n".join([doc.page_content for doc in docs])
        
        @tool
        def search_annuities(query: str) -> str:
            """연금저축 상품을 검색합니다."""
            retriever = annuity_vector_store.as_retriever(search_kwargs={'k': 2})
            docs = retriever.get_relevant_documents(query)
            return "\n\n".join([doc.page_content for doc in docs])
        
        @tool
        def search_funds(query: str) -> str:
            """펀드 상품을 검색합니다."""
            retriever = fund_vector_store.as_retriever(search_kwargs={'k': 2})
            docs = retriever.get_relevant_documents(query)
            return "\n\n".join([doc.page_content for doc in docs])
        
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
        """금융상품 관련 질문인지 판단"""
        financial_keywords = [
            "예금", "적금", "연금", "펀드", "투자", "저축", "금리", "수익",
            "은퇴", "노후", "자산", "재테크", "금융", "상품", "추천"
        ]
        return any(keyword in message for keyword in financial_keywords)
    
    async def stream_chat(
        self,
        user_id: int,
        session_id: str,
        message: str,
        keywords: Optional[List[int]] = None
    ):
        """스트리밍 챗봇 응답"""
        
        # 1. 금융상품 질문 검증
        if not self.is_financial_question(message):
            yield {
                "type": "error",
                "content": "죄송합니다. 저는 금융상품 추천만 도와드릴 수 있습니다. 예금, 적금, 연금, 펀드 등에 대해 질문해주세요."
            }
            return
        
        # 2. 대화 히스토리 가져오기
        history = self.get_chat_history(user_id, session_id)
        
        # 3. 시스템 프롬프트
        system_prompt = """
당신은 금융상품 추천 전문가 '노후하우'입니다.
사용자의 질문에 대해 적절한 금융상품(예금, 적금, 연금, 펀드)을 추천하고 설명해주세요.
금융상품과 관련 없는 질문에는 답변하지 마세요.
"""
        
        # 4. 메시지 구성
        messages = [
            {"role": "system", "content": system_prompt}
        ] + history + [HumanMessage(content=message)]
        
        # 5. 사용자 메시지 저장
        self.save_message(user_id, session_id, "user", message)
        
        # 6. Agent 실행 및 스트리밍
        full_response = ""
        
        try:
            # Agent Graph 실행
            result = await self.agent_graph.ainvoke({"messages": messages})
            
            # 응답 추출
            last_message = result["messages"][-1]
            response_text = last_message.content
            
            # 스트리밍 시뮬레이션 (실제로는 LLM 스트리밍 사용)
            for char in response_text:
                full_response += char
                yield {
                    "type": "token",
                    "content": char
                }
            
            # 7. AI 응답 저장
            self.save_message(user_id, session_id, "assistant", full_response)
            
            # 8. 완료 신호
            yield {
                "type": "done",
                "content": full_response
            }
        
        except Exception as e:
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
