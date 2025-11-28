"""
상품 추천 서비스 로직
"""
import asyncio
from typing import TypedDict, Annotated, Sequence, List, Optional
import operator
import json
import re

# --- LangGraph & Agent 관련 임포트 ---
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# --- LangChain Tools & Retrievers ---
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# --- LLM, DB, Models ---
from app.core.llm_factory import get_llm
from app.core.config import settings
from app.services.search_tools import SEARCH_TOOLS
from app.services.user_vectorization_service import user_vectorization_service
from app.models.recommendation import RecommendationResponse, RecommendedProduct
from app.models.chatbot_models import ChatProduct

# 1. LLM 모델 초기화 (Factory 사용)
llm = get_llm(temperature=0.1)

# 2. Vector Search Tools 정의 (Shared Tools 사용)
tools = SEARCH_TOOLS

# LLM에 tool 바인딩
llm_with_tools = llm.bind_tools(tools)

# 3. Agent State 정의
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    persona: str

# 4. Agent 프롬프트 (product_id 포함하도록 개선)
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
- Tool 결과에서 [ID:xxx] 형태로 제공된 product_id를 반드시 JSON 응답에 포함하세요.

최종 응답은 다음 JSON 형식으로만 답변하세요:
{{
  "deposit_or_saving": {{
    "product_id": "...",
    "product_type": "예금" or "적금",
    "product_name": "...",
    "company_name": "...",
    "benefit": "최고 연 X.X%",
    "reason": "..."
  }},
  "annuity": {{
    "product_id": "...",
    "product_type": "연금저축",
    "product_name": "...",
    "company_name": "...",
    "benefit": "세액공제 16.5%",
    "reason": "..."
  }},
  "fund": {{
    "product_id": "...",
    "product_type": "펀드",
    "product_name": "...",
    "company_name": "...",
    "benefit": "수익률 12.3%",
    "reason": "..."
  }}
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
    async def get_recommendations(self, user_id: int) -> RecommendationResponse:
        """사용자 임베딩 기반 금융상품 추천"""
        
        # 1. 사용자 페르소나 가져오기
        user_vector = user_vectorization_service.user_vectors_collection.find_one(
            {"_id": f"user_{user_id}"}
        )
        
        if not user_vector:
            # 사용자 벡터가 없으면 먼저 벡터화 실행
            await user_vectorization_service.vectorize_user(user_id)
            user_vector = user_vectorization_service.user_vectors_collection.find_one(
                {"_id": f"user_{user_id}"}
            )
        
        persona = user_vector["persona_text"]
        
        try:
            # 2. Agent Graph 실행
            result = await agent_graph.ainvoke({
                "messages": [HumanMessage(content=persona)],
                "persona": persona
            })
            
            
            # 3. 마지막 메시지에서 JSON 추출
            last_message = result["messages"][-1]
            response_text = last_message.content
            
            
            # 4. JSON 파싱
            # JSON 부분만 추출
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                
                
                # RecommendedProduct 객체로 변환
                deposit_or_saving = None
                if data.get("deposit_or_saving"):
                    deposit_or_saving = RecommendedProduct(**data["deposit_or_saving"])
                
                annuity = None
                if data.get("annuity"):
                    annuity = RecommendedProduct(**data["annuity"])
                
                fund = None
                if data.get("fund"):
                    fund = RecommendedProduct(**data["fund"])
                
                return RecommendationResponse(
                    deposit_or_saving=deposit_or_saving,
                    annuity=annuity,
                    fund=fund
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

    def _convert_to_chat_product(self, product: RecommendedProduct, icon: str) -> ChatProduct:
        """RecommendedProduct를 ChatProduct로 변환"""
        return ChatProduct(
            id=product.product_id,
            icon=icon,
            type=product.product_type,
            name=product.product_name,
            bank=product.company_name,
            features=[product.reason], # 이유를 특징으로 사용하거나 별도 필드 필요
            stat=product.benefit
        )

    async def get_chat_products(self, user_id: int) -> List[ChatProduct]:
        """챗봇용 상품 추천 목록 반환"""
        rec_response = await self.get_recommendations(user_id)
        products = []
        
        if rec_response.deposit_or_saving:
            products.append(self._convert_to_chat_product(rec_response.deposit_or_saving, "💰"))
            
        if rec_response.annuity:
            products.append(self._convert_to_chat_product(rec_response.annuity, "🎯"))
            
        if rec_response.fund:
            products.append(self._convert_to_chat_product(rec_response.fund, "📈"))
            
        return products

rag_service = RAGService()