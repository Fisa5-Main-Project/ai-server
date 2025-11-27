"""
Shared Vector Search Tools
"""
from langchain_core.tools import tool
from app.db.vector_store import (
    deposit_vector_store, saving_vector_store, 
    annuity_vector_store, fund_vector_store
)

@tool
async def search_deposits(query: str) -> str:
    """정기예금 상품을 검색합니다. 사용자가 목돈을 한번에 예치하길 원할 때 유용합니다."""
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
    """적금 상품을 검색합니다. 사용자가 매달 꾸준히 돈을 모으길 원할 때 유용합니다."""
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
    """연금저축 상품(펀드, 보험 등)을 검색합니다. 사용자가 은퇴 또는 노후 대비를 원할 때 유용합니다."""
    retriever = annuity_vector_store.as_retriever(search_kwargs={'k': 3})
    docs = await retriever.ainvoke(query)
    results = []
    for doc in docs:
        doc_id = doc.metadata.get('_id', 'unknown')
        results.append(f"[ID:{doc_id}] {doc.page_content}")
    return "\n\n".join(results)

@tool
async def search_funds(query: str) -> str:
    """일반 펀드 상품을 검색합니다. 사용자가 주식, 채권 등에 투자하여 자산 증식을 원할 때 유용합니다."""
    retriever = fund_vector_store.as_retriever(search_kwargs={'k': 3})
    docs = await retriever.ainvoke(query)
    results = []
    for doc in docs:
        doc_id = doc.metadata.get('_id', 'unknown')
        results.append(f"[ID:{doc_id}] {doc.page_content}")
    return "\n\n".join(results)

# Export tools list for easy import
SEARCH_TOOLS = [search_deposits, search_savings, search_annuities, search_funds]
