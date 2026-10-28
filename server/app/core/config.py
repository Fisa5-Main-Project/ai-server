from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    
    # [수정] .env 파일 경로를 'main-project-ai/server/' 폴더로 변경
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"),
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # 1. Gemini LLM 설정
    GEMINI_API_KEY: str
    GROQ_API_KEY: str | None = None
    LLM_PROVIDER: str = "gemini"  # "gemini"나 "groq"으로 바꾸면 LLM모델을 변경할 수 있습니다.

    # 2. MongoDB (VectorDB) 설정
    MONGO_DB_NAME: str
    MONGO_USERNAME: str
    MONGO_PASSWORD: str
    MONGO_HOST: str
    MONGO_URI: str | None = None

    @property
    def MONGO_DB_URL(self):
        if self.MONGO_URI:
            return self.MONGO_URI
        return f"mongodb+srv://{self.MONGO_USERNAME}:{self.MONGO_PASSWORD}@{self.MONGO_HOST}"
    
    @property
    def DB_NAME(self):
        """MongoDB 데이터베이스 이름"""
        return self.MONGO_DB_NAME

    # 3. MySQL (User Profile DB) 설정
    MYSQL_DB_URL: str
    USER_EMBEDDING_MODEL: str = "models/text-embedding-004"
    CDC_KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    CDC_GROUP_ID: str = "user-persona-refresh-v1"
    CDC_TOPIC_PREFIX: str = "knowhow"
    CDC_DATABASE: str = "knowhow"
    CDC_MAX_ATTEMPTS: int = 5
    CDC_LEASE_SECONDS: int = 120
    CDC_MONITORING_ENABLED: bool = False
    CDC_CONNECT_URL: str = "http://connect:8083"
    CDC_RECONCILE_INTERVAL_SECONDS: int = 900
   
settings = Settings()
