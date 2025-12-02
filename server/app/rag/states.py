from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage

class ProductAgentState(TypedDict):
    """
    상품 추천 에이전트의 상태
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    persona: str
