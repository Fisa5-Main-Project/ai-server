from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from functools import partial

from app.rag.states import ProductAgentState
from app.rag.nodes.product_agent import call_model, should_continue
from app.rag.retrievers.tools import SEARCH_TOOLS
from app.core.llm_factory import get_llm

def build_product_graph():
    """
    상품 추천 에이전트 그래프 생성
    """
    # 1. LLM 및 Tools 초기화
    llm = get_llm(temperature=0.1)
    tools = SEARCH_TOOLS
    llm_with_tools = llm.bind_tools(tools)
    
    # 2. 그래프 초기화
    workflow = StateGraph(ProductAgentState)
    
    # 3. 노드 추가
    # call_model에 llm_with_tools 주입
    workflow.add_node("agent", partial(call_model, model=llm_with_tools))
    workflow.add_node("tools", ToolNode(tools))
    
    # 4. 엣지 연결
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )
    
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()
