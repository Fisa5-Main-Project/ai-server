from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.core.config import settings

# Gemini Embedding 모델 (API 호출 방식)
EMBEDDING_MODEL = "models/text-embedding-004"
print(f"Embedding 모델 {EMBEDDING_MODEL} 로드 중...")

embeddings = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    google_api_key=settings.GEMINI_API_KEY
)
print("Embedding 모델 로드 완료.")