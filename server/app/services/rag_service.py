"""RAG 서비스 - 사용자 맞춤 금융상품 추천"""
import json
import re
from typing import TypedDict, Annotated, Sequence
import operator

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage

from app.core.llm_factory import LLMFactory
from app.db.vector_store import (
    deposit_vector_store, saving_vector_store, 
    annuity_vector_store, fund_vector_store
)
from app.services.user_vectorization_service import user_vectorization_service
from app.models.recommendation import RecommendationResponse, RecommendedProduct

# LLM 초기화
llm = LLMFactory.create_llm()

# Vector Search Tools
@tool
async def search_deposits(query: str) -> str:
    """예금 상품 검색"""
    retriever = deposit_vector_store.as_retriever(
        search_kwargs={'k': 3, 'pre_filter': {'product_type': 'deposit'}}
    )
    docs = await retriever.ainvoke(query)
    results = []
    for doc in docs:
        doc_id = doc.metadata.get('_id', 'unknown')
        results.append(f"[ID:{doc_id}] {doc.page_content}")
    return "\n\n".join(results)

@tool
async def search_savings(query: str) -> str:
    """적금 상품 검색"""
    retriever = saving_vector_store.as_retriever(
        search_kwargs={'k': 3, 'pre_filter': {'product_type': 'saving'}}
    )
    docs = await retriever.ainvoke(query)
    results = []
    for doc in docs:
        doc_id = doc.metadata.get('_id', 'unknown')
        results.append(f"[ID:{doc_id}] {doc.page_content}")
    return "\n\n".join(results)

@tool
async def search_annuities(query: str) -> str:
    """연금 상품 검색"""
    retriever = annuity_vector_store.as_retriever(search_kwargs={'k': 3})
    docs = await retriever.ainvoke(query)
    results = []
    for doc in docs:
        doc_id = doc.metadata.get('_id', 'unknown')
        results.append(f"[ID:{doc_id}] {doc.page_content}")
    return "\n\n".join(results)

@tool
async def search_funds(query: str) -> str:
    """펀드 상품 검색"""
    retriever = fund_vector_store.as_retriever(search_kwargs={'k': 3})
    docs = await retriever.ainvoke(query)
    results = []
    for doc in docs:
        doc_id = doc.metadata.get('_id', 'unknown')
        results.append(f"[ID:{doc_id}] {doc.page_content}")
    return "\n\n".join(results)

tools = [search_deposits, search_savings, search_annuities, search_funds]
llm_with_tools = llm.bind_tools(tools)

# Agent State
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    persona: str

# 시스템 프롬프트
SYSTEM_PROMPT = """
당신은 사용자 맞춤 금융상품을 추천하는 AI 어드바이저입니다.

임무:
1. 사용자 페르소나 분석
2. 예금/적금, 연금, 펀드 각 1개씩 추천
3. 추천 이유 설명

규칙:
- 3가지 카테고리 모두 검색 필수
- Tool 결과의 [ID:xxx] 형태 product_id 포함 필수
- 적합 상품 없으면 null

응답 형식 (JSON):
{
  "deposit_or_saving": {
    "product_id": "...",
    "product_type": "예금/적금",
    "product_name": "...",
    "company_name": "...",
    "benefit": "...",
    "reason": "..."
  },
  "annuity": {...},
  "fund": {...}
}
"""

# Agent 노드
def agent_node(state: AgentState):
    messages = state["messages"]
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    response = llm_with_tools.invoke(full_messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"

# LangGraph 구성
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"continue": "tools", "end": END}
)
workflow.add_edge("tools", "agent")
agent_graph = workflow.compile()

# RAG 서비스
class RAGService:
    async def get_recommendations(self, user_id: int) -> RecommendationResponse:
        """사용자 맞춤 금융상품 추천"""
        
        # 사용자 페르소나 가져오기
        user_vector = user_vectorization_service.user_vectors_collection.find_one(
            {"_id": f"user_{user_id}"}
        )
        
        if not user_vector:
            await user_vectorization_service.vectorize_user(user_id)
            user_vector = user_vectorization_service.user_vectors_collection.find_one(
                {"_id": f"user_{user_id}"}
            )
        
        persona = user_vector["persona_text"]
        
        try:
            # Agent 실행
            result = await agent_graph.ainvoke({
                "messages": [HumanMessage(content=persona)],
                "persona": persona
            })
            
            # JSON 추출 및 파싱
            last_message = result["messages"][-1]
            response_text = last_message.content
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                # 응답 객체 변환
                deposit_or_saving = RecommendedProduct(**data["deposit_or_saving"]) if data.get("deposit_or_saving") else None
                annuity = RecommendedProduct(**data["annuity"]) if data.get("annuity") else None
                fund = RecommendedProduct(**data["fund"]) if data.get("fund") else None
                
                return RecommendationResponse(
                    deposit_or_saving=deposit_or_saving,
                    annuity=annuity,
                    fund=fund
                )
            else:
                print(f"JSON 파싱 실패: {response_text}")
                return RecommendationResponse(
                    deposit_or_saving=None,
                    annuity=None,
                    fund=None
                )
        
        except Exception as e:
            print(f"추천 실패: {e}")
            import traceback
            traceback.print_exc()
            
            return RecommendationResponse(
                deposit_or_saving=None,
                annuity=None,
                fund=None
            )

rag_service = RAGService()