"""Embeddings 인스턴스 생성"""
from app.core.llm_factory import LLMFactory

# Factory를 통해 embeddings 생성
embeddings = LLMFactory.create_embeddings()