from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import settings

SQLALCHEMY_DATABASE_URL = settings.MYSQL_DB_URL

try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    print("MySQL (User DB) 연결 엔진 생성 완료.")
except Exception as e:
    print(f"MySQL (User DB) 연결 실패: {e}")

# FastAPI 의존성 주입용 세션
def get_user_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()