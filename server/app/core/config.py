"""환경 설정 관리"""
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
   
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"),
        env_file_encoding='utf-8',
        extra='ignore'
    )
    
    # ========== API 키 ==========
    GEMINI_API_KEY: str
    GROQ_API_KEY: str = ""
    
    # ========== LLM/Embedding 설정 ==========
    LLM_PROVIDER: str = "groq"  # gemini 또는 groq
    EMBEDDING_PROVIDER: str = "local"  # gemini, voyage, local, solar
    
    # 모델명
    GEMINI_MODEL: str = "gemini-2.5-flash" # LLM_PROVIDER가 gemini 일 때
    GROQ_MODEL: str = "llama-3.3-70b-versatile" # LLM_PROVIDER가 groq 일 때
    EMBEDDING_MODEL: str = "dragonkue/BGE-m3-ko"  # Local embedding model
    EMBEDDING_DIMENSION: int = 1024  # BGE-m3-ko dimension
    
    LLM_TEMPERATURE: float = 0.1
    CHATBOT_TEMPERATURE: float = 0.3
    
    # ========== MongoDB 설정 ==========
    MONGO_DB_NAME: str
    MONGO_USERNAME: str
    MONGO_PASSWORD: str
    MONGO_HOST: str
    
    @property
    def MONGO_DB_URL(self):
        return f"mongodb+srv://{self.MONGO_USERNAME}:{self.MONGO_PASSWORD}@{self.MONGO_HOST}"
    
    @property
    def DB_NAME(self):
        return self.MONGO_DB_NAME
    
    # ========== MySQL 설정 ==========
    MYSQL_DB_URL: str
   
settings = Settings()