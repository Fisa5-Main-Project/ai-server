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

    # 2. MongoDB (VectorDB) 설정
    MONGO_DB_URL: str
    DB_NAME: str

    # 3. MySQL (User Profile DB) 설정
    MYSQL_DB_URL: str
    
    # 4. Spring Boot API URL
    SPRING_BOOT_API_URL: str = "http://localhost:8060"
    
    # (API 키는 Airflow Variables에서만 사용하므로 여기서는 제거)

settings = Settings()