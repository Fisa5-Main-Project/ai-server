import asyncio
from sqlalchemy.orm import Session
from typing import TypedDict, Annotated, Sequence
import operator

# --- LangGraph & Agent 관련 임포트 ---
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# --- LangChain Tools & Retrievers ---
from langchain.tools.retriever import create_retriever_tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# --- LLM, DB, Models ---
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from app.db.vector_store import (
    deposit_saving_vector_store, 
    annuity_vector_store, fund_vector_store
)
from app.services.profile_service import profile_service
from app.models.recommendation import RecommendationResponse

# 1. Gemini LLM 모델 초기화
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0.1
)

# 2. Vector Store를 Tool로 변환
#products_deposit_saving(예적금), products_funds(펀드), products_annuity(연금저축)
deposit_saving_retriever = deposit_saving_vector_store.as_retriever(search_kwargs={'k': 2})
annuity_retriever = annuity_vector_store.as_retriever(search_kwargs={'k': 2})
fund_retriever = fund_vector_store.as_retriever(search_kwargs={'k': 2})

tools = [
    create_retriever_tool(
        deposit_saving_retriever,
        "search_deposits_and_savings",
        "정기예금 또는 적금 상품을 검색합니다. 정기예금은 사용자가 목돈을 한번에 예치하길 원할 때, 적금은 매달 꾸준히 돈을 모으길 원할 때 유용합니다."
    ),
    create_retriever_tool(
        annuity_retriever,
        "search_annuities",
        "연금저축 상품(펀드, 보험 등)을 검색합니다. 사용자가 은퇴 또는 노후 대비를 원할 때 유용합니다."
    ),
    create_retriever_tool(
        fund_retriever,
        "search_funds",
        "일반 펀드 상품을 검색합니다. 사용자가 주식, 채권 등에 투자하여 자산 증식을 원할 때 유용합니다."
    )
]

# LLM에 tool 바인딩
llm_with_tools = llm.bind_tools(tools)

# 3. Agent State 정의
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    persona: str

# 4. Agent 프롬프트
SYSTEM_PROMPT = """
당신은 사용자의 페르소나에 맞춰 금융 상품을 추천하는 전문 AI 어드바이저 '노후하우'입니다.

당신의 임무는 3가지입니다:
1. [사용자 페르소나]를 분석합니다.
2. 페르소나에 가장 적합한 **예금 또는 적금 1개**, **연금 1개**, **펀드 1개**를 추천하기 위해, 당신에게 제공된 [도구(Tools)]를 사용해야 합니다.
3. 검색된 상품 정보(Tool observation)를 바탕으로, 각 상품을 추천하는 구체적인 이유를 요약합니다.

[중요 규칙]
- 반드시 3가지 카테고리(예/적금, 연금, 펀드) 각각에 대해 도구를 검색하고 추천해야 합니다.
- 사용자가 '안정추구형'이면 'search_deposits'나 'search_savings'를, '공격투자형'이면 'search_funds'를 우선적으로 고려하세요.
- 페르소나에 적합한 상품을 찾지 못하면, 해당 필드는 null로 비워두고 이유는 "추천할 상품을 찾지 못했습니다."라고 명시하세요.

최종 응답은 다음 JSON 형식으로만 답변하세요:
{{
  "deposit_or_saving": {{"product_name": "...", "reason": "..."}},
  "annuity": {{"product_name": "...", "reason": "..."}},
  "fund": {{"product_name": "...", "reason": "..."}}
}}
"""

# 5. Agent 노드 함수들
def agent_node(state: AgentState):
    """Agent가 다음 액션을 결정하는 노드"""
    messages = state["messages"]
    
    # 시스템 프롬프트 + 이전 대화 메시지
    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + messages
    
    response = llm_with_tools.invoke(full_messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    """Tool 호출이 필요한지 판단"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # Tool 호출이 있으면 "continue", 없으면 "end"
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"

# 6. LangGraph 구성
workflow = StateGraph(AgentState)

# 노드 추가
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))

# 시작점 설정
workflow.set_entry_point("agent")

# 조건부 엣지 추가
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "tools",
        "end": END
    }
)

# Tool 실행 후 다시 agent로
workflow.add_edge("tools", "agent")

# Graph 컴파일
agent_graph = workflow.compile()

# 7. RAG 서비스 클래스
class RAGService:
    async def get_recommendations(self, db: Session, user_id: int) -> RecommendationResponse:
        """1. 페르소나 생성 -> 2. Agent 실행 -> 3. JSON 파싱 -> 4. 반환"""
        
        # 1. 사용자 페르소나 생성
        persona = profile_service.get_user_persona(db, user_id)
        
        try:
            # 2. Agent Graph 실행
            result = await agent_graph.ainvoke({
                "messages": [HumanMessage(content=persona)],
                "persona": persona
            })
            
            # 3. 마지막 메시지에서 JSON 추출
            last_message = result["messages"][-1]
            response_text = last_message.content
            
            # 4. JSON 파싱 (간단한 방법)
            import json
            import re
            
            # JSON 부분만 추출
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                
                return RecommendationResponse(
                    deposit_or_saving=data.get("deposit_or_saving"),
                    annuity=data.get("annuity"),
                    fund=data.get("fund")
                )
            else:
                print(f"JSON 형식을 찾을 수 없습니다: {response_text}")
                return RecommendationResponse(
                    deposit_or_saving=None,
                    annuity=None,
                    fund=None
                )
        
        except Exception as e:
            print(f"Agent 실행 실패: {e}")
            import traceback
            traceback.print_exc()
            
            return RecommendationResponse(
                deposit_or_saving=None,
                annuity=None,
                fund=None
            )

rag_service = RAGService()