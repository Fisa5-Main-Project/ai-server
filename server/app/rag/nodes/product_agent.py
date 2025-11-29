from typing import Literal
from langchain_core.messages import BaseMessage
from app.rag.states import ProductAgentState
from app.rag.prompts.product_recommendation import SYSTEM_PROMPT

async def call_model(state: ProductAgentState, model) -> dict:
    """
    LLM 모델을 호출하여 응답을 생성하는 노드
    """
    messages = state["messages"]
    
    # 시스템 프롬프트 + 이전 대화 메시지
    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + messages
    
    response = await model.ainvoke(full_messages)
    return {"messages": [response]}

def should_continue(state: ProductAgentState) -> Literal["tools", "end"]:
    """
    Tool 호출이 필요한지 판단하는 조건부 엣지
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # Tool 호출이 있으면 "tools", 없으면 "end"
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"
