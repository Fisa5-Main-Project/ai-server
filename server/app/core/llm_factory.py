from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from app.core.config import settings

def get_llm(temperature: float = 0.3, streaming: bool = False):
    """
    설정에 따라 Gemini 또는 Groq LLM 인스턴스를 반환합니다.
    
    Args:
        temperature (float): 생성 다양성 조절 (0.0 ~ 1.0)
        streaming (bool): 스트리밍 응답 여부
        
    Returns:
        BaseChatModel: 구성된 LLM 인스턴스
    """
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set in .env")
            
        return ChatGroq(
            model_name="llama-3.3-70b-versatile",
            temperature=temperature,
            api_key=settings.GROQ_API_KEY,
            streaming=streaming
        )
        
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
            streaming=streaming
        )
        
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Gemini 혹은 Groq을 사용해주세요.")
