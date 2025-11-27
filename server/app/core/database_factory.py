"""Database Factory - MongoDB & MySQL Connection Management"""
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

class DatabaseFactory:
    """데이터베이스 연결 관리 Factory (Singleton 패턴 적용)"""
    
    _mongo_client: Optional[AsyncIOMotorClient] = None
    _mongo_sync_client: Optional[MongoClient] = None
    _mysql_engine: Optional[Engine] = None
    _mysql_session_maker: Optional[sessionmaker] = None

    @classmethod
    def get_mongo_client(cls) -> AsyncIOMotorClient:
        """MongoDB Async Client (Motor) 반환"""
        if cls._mongo_client is None:
            print(f"🔌 MongoDB 연결 초기화: {settings.MONGO_HOST}")
            cls._mongo_client = AsyncIOMotorClient(settings.MONGO_DB_URL)
        return cls._mongo_client

    @classmethod
    def get_mongo_sync_client(cls) -> MongoClient:
        """MongoDB Sync Client (PyMongo) 반환 (동기 작업용)"""
        if cls._mongo_sync_client is None:
            print(f"🔌 MongoDB Sync 연결 초기화: {settings.MONGO_HOST}")
            import certifi
            cls._mongo_sync_client = MongoClient(
                settings.MONGO_DB_URL,
                tlsCAFile=certifi.where()
            )
        return cls._mongo_sync_client

    @classmethod
    def get_mysql_engine(cls) -> Engine:
        """MySQL SQLAlchemy Engine 반환"""
        if cls._mysql_engine is None:
            print(f"🔌 MySQL Engine 초기화")
            cls._mysql_engine = create_engine(
                settings.MYSQL_DB_URL,
                pool_pre_ping=True,
                pool_recycle=3600
            )
        return cls._mysql_engine

    @classmethod
    def get_mysql_session(cls) -> Session:
        """MySQL Session 반환"""
        if cls._mysql_session_maker is None:
            engine = cls.get_mysql_engine()
            cls._mysql_session_maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        return cls._mysql_session_maker()

    @classmethod
    def close_all(cls):
        """모든 연결 종료"""
        if cls._mongo_client:
            cls._mongo_client.close()
            cls._mongo_client = None
        if cls._mongo_sync_client:
            cls._mongo_sync_client.close()
            cls._mongo_sync_client = None
        # MySQL Engine은 보통 애플리케이션 종료 시까지 유지
