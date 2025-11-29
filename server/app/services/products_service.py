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

# 4. Agent 프롬프트 (유연한 추천 지원)
SYSTEM_PROMPT = """
당신은 사용자의 페르소나에 맞춰 금융 상품을 추천하는 전문 AI 어드바이저 '노후하우'입니다.

당신의 임무는 사용자의 요청에 따라 최적의 금융 상품을 추천하는 것입니다.

[추천 규칙]
1. **특정 카테고리 요청 시** (예: "펀드 추천해줘", "예금 추천해줘"):
   - 해당 카테고리에서 **상위 3개** 상품을 검색하고 추천하세요.
   - 예: 펀드 요청 시 -> 펀드 3개 추천

2. **일반 추천 요청 시** (예: "상품 추천해줘", "나에게 맞는 상품 알려줘"):
   - **예금/적금 1개**, **연금 1개**, **펀드 1개**를 각각 골고루 추천하세요. (총 3개)

[검색 도구 사용]
- 사용자가 '안정추구형'이면 'search_deposits'나 'search_savings'를, '공격투자형'이면 'search_funds'를 우선적으로 고려하세요.
- 페르소나에 적합한 상품을 찾지 못하면, 해당 필드는 제외하고 찾은 상품만 반환하세요.
- Tool 결과에서 [ID:xxx] 형태로 제공된 product_id를 반드시 JSON 응답에 포함하세요.

[상품별 핵심 속성 추출 규칙]
- **연금(annuity)**: 'benefit' 필드에 '세액공제' 대신 **'비보장' 여부, '가입연령', '수령연령'** 등 가입 조건을 요약해서 넣으세요. (예: "비보장, 가입:30세")
- **펀드(fund)**: 'benefit' 필드에 '수익률' 대신 **'펀드유형'(예: 주식형, 채권형)과 '운용사'** 정보를 넣으세요. (예: "주식형 | 삼성자산운용")
- **예/적금**: 기존대로 '최고 연 X.X%' 금리 정보를 유지하세요.

[중요: 검색 결과 활용 원칙]
- 사용자가 특정 금융사(예: 우리은행)를 요청했더라도, Tool 검색 결과에 해당 금융사 상품이 없다면 **검색된 다른 금융사의 상품을 추천하세요.**
- **절대로 빈 목록을 반환하지 마세요.** 검색된 상품 중 가장 적절한 것을 골라 JSON에 채우세요.
- "찾지 못했습니다"라고 판단하여 빈 배열을 반환하면 안 됩니다. 무조건 Tool 결과 내에서 추천하세요.

[최종 응답 형식]
**중요: 반드시 아래 JSON 포맷으로만 응답하세요.**
**서론, 결론, 설명, 마크다운 코드 블록(```json) 등 다른 텍스트를 절대 포함하지 마세요.**
**오직 JSON 문자열만 반환해야 합니다.**

{
  "products": [
    {
      "product_id": "...",
      "product_type": "예금" or "적금" or "연금저축" or "펀드",
      "product_name": "...",
      "company_name": "...",
      "benefit": "...",
      "reason": "..."
    }
  ]
}

[주의사항]
- JSON 형식을 지키지 않으면 시스템 오류가 발생합니다.
- 사용자에게 말을 걸거나 설명을 덧붙이지 마세요.
- 오직 데이터만 반환하세요.
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
class ProductsService:
    async def get_recommendations(self, user_id: int, user_message: str = "") -> RecommendationResponse:
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
            # 사용자 메시지가 있으면 포함, 없으면 페르소나만
            content = f"{persona}\n\n사용자 요청: {user_message}" if user_message else persona
            
            result = await agent_graph.ainvoke({
                "messages": [HumanMessage(content=content)],
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
                
                products = []
                if data.get("products"):
                    for p in data["products"]:
                        products.append(RecommendedProduct(**p))
                
                # Legacy format fallback (혹시 몰라서 유지)
                if not products:
                    if data.get("deposit_or_saving"):
                        products.append(RecommendedProduct(**data["deposit_or_saving"]))
                    if data.get("annuity"):
                        products.append(RecommendedProduct(**data["annuity"]))
                    if data.get("fund"):
                        products.append(RecommendedProduct(**data["fund"]))

                return RecommendationResponse(products=products)
            else:
                print(f"JSON 형식을 찾을 수 없습니다: {response_text}")
                return RecommendationResponse(products=[])
        
        except Exception as e:
            print(f"Agent 실행 실패: {e}")
            import traceback
            traceback.print_exc()
            
            return RecommendationResponse(products=[])

    def _convert_to_chat_product(self, product: RecommendedProduct, icon: str) -> ChatProduct:
        """RecommendedProduct를 ChatProduct로 변환"""
        
        # 금융사 공식 홈페이지 매핑
        company_urls = {
            "국민": "https://www.kbstar.com/",
            "KB": "https://www.kbstar.com/",
            "신한": "https://www.shinhan.com/",
            "하나": "https://www.kebhana.com/",
            "우리": "https://www.wooribank.com/",
            "농협": "https://banking.nonghyup.com/",
            "NH": "https://banking.nonghyup.com/",
            "엔에이치": "https://banking.nonghyup.com/",
            "기업": "https://www.ibk.co.kr/",
            "IBK": "https://www.ibk.co.kr/",
            "카카오": "https://www.kakaobank.com/",
            "토스": "https://www.tossbank.com/",
            "케이": "https://www.kbanknow.com/",
            "삼성": "https://www.samsungpop.com/",
            "미래": "https://securities.miraeasset.com/",
            "한국투자": "https://securities.koreainvestment.com/",
            "키움": "https://www.kiwoom.com/",
            "대신": "https://www.daishin.com/",
            "메리츠": "https://home.meritz.co.kr/",
            "부산": "https://www.busanbank.co.kr/",
            "광주": "https://www.kjbank.com/",
            "전북": "https://www.jbbank.co.kr/",
            "SC": "https://www.standardchartered.co.kr/",
            "대구": "https://www.dgb.co.kr/",
            "경남": "https://www.knbank.co.kr/",
            "수협": "https://suhyup-bank.com/",
            "신협": "https://www.cu.co.kr/",
            "우체국": "https://www.epostbank.go.kr/",
            "새마을": "https://www.kfcc.co.kr/",
            "한화": "https://www.hanwhawm.com/",
            "유안타": "https://www.myasset.com/",
            "유진": "https://www.eugenefn.com/",
            "교보": "https://www.iprovest.com/",
            "하이": "https://www.hi-ib.com/",
            "현대": "https://www.hmsec.com/",
            "DB": "https://www.db-fi.com/",
            "SK": "https://www.sks.co.kr/",
            "LS": "https://www.ls-sec.co.kr/",
        }
        
        # 기본값: 네이버 검색
        link = f"https://search.naver.com/search.naver?query={product.company_name} {product.product_name}"
        
        # 매핑된 URL 찾기 (부분 일치)
        for key, url in company_urls.items():
            if key in product.company_name:
                link = url
                break

        return ChatProduct(
            id=product.product_id,
            icon=icon,
            type=product.product_type,
            name=product.product_name,
            bank=product.company_name,
            features=[product.reason], # 이유를 특징으로 사용하거나 별도 필드 필요
            stat=product.benefit,
            link=link
        )

    async def get_chat_products(self, user_id: int, user_message: str = "") -> List[ChatProduct]:
        """챗봇용 상품 추천 목록 반환"""
        rec_response = await self.get_recommendations(user_id, user_message)
        products = []
        
        if rec_response.products:
            for p in rec_response.products:
                # 아이콘 결정 로직
                icon = "💰"
                if "연금" in (p.product_type or ""):
                    icon = "🎯"
                elif "펀드" in (p.product_type or ""):
                    icon = "📈"
                
                products.append(self._convert_to_chat_product(p, icon))
        
        return products

products_service = ProductsService()
