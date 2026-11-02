from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage


class ProductAgentState(TypedDict, total=False):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    persona: str
    query: str
    profile: dict
    disliked: list[str]
    liked: list[str]
    intent: dict
    candidates: list[dict]
    accepted: list[dict]
    decisions: list[dict]
    products: list[dict]
