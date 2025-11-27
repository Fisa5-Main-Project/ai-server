"""LLM Factory - 다중 프로바이더 지원 (Gemini/Groq/Solar)"""
from typing import Optional, Literal
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from app.core.config import settings

ProviderType = Literal["gemini", "groq"]


class LLMFactory:
    """LLM/Embeddings 생성 Factory"""
    
    @staticmethod
    def create_llm(
        provider: Optional[ProviderType] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        streaming: bool = False
    ):
        """
        LLM 인스턴스 생성
        
        Args:
            provider: gemini 또는 groq (기본값: settings.LLM_PROVIDER)
            model: 모델명 (기본값: provider별 설정값)
            temperature: 온도 (기본값: settings.LLM_TEMPERATURE)
            streaming: 스트리밍 모드 (기본값: False)
        """
        provider = provider or settings.LLM_PROVIDER
        temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        
        if provider == "gemini":
            model_name = model or settings.GEMINI_MODEL
            print(f"🤖 Gemini LLM 생성: {model_name} (temp={temperature}, stream={streaming})")
            
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
                streaming=streaming
            )
        
        elif provider == "groq":
            try:
                from groq import Groq
            except ImportError:
                raise ImportError("Groq 패키지 미설치. 설치: pip install groq")
            
            model_name = model or settings.GROQ_MODEL
            print(f"⚡ Groq LLM 생성: {model_name} (temp={temperature})")
            
            from langchain_groq import ChatGroq
            
            return ChatGroq(
                model=model_name,
                groq_api_key=settings.GROQ_API_KEY,
                temperature=temperature,
                streaming=streaming
            )
        
        else:
            raise ValueError(f"지원하지 않는 provider: {provider}")
    
    @staticmethod
    def create_chatbot_llm(provider: Optional[ProviderType] = None):
        """챗봇용 LLM 생성 (스트리밍 활성화)"""
        return LLMFactory.create_llm(
            provider=provider,
            temperature=settings.CHATBOT_TEMPERATURE,
            streaming=True
        )
    
    @staticmethod
    def create_embeddings(model: Optional[str] = None, provider: Optional[str] = None):
        """
        Embeddings 인스턴스 생성 (Local BGE-m3-ko)
        """
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        except ImportError:
            raise ImportError("langchain-community 또는 sentence-transformers 미설치.")
        
        model_name = model or settings.EMBEDDING_MODEL
        print(f"📝 Local Embeddings 생성: {model_name}")
        
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )


def get_default_llm():
    """기본 LLM 가져오기"""
    return LLMFactory.create_llm()


def get_chatbot_llm():
    """챗봇용 LLM 가져오기"""
    return LLMFactory.create_chatbot_llm()


def get_embeddings():
    """Embeddings 가져오기"""
    return LLMFactory.create_embeddings()
