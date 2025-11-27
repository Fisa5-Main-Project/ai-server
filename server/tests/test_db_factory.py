import sys
import os
import asyncio

# Add server directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.database_factory import DatabaseFactory
from app.core.config import settings

async def test_mongo_async():
    print("\nTesting MongoDB Async Client...")
    try:
        client = DatabaseFactory.get_mongo_client()
        # Simple command to check connection
        await client.admin.command('ping')
        print("✅ MongoDB Async Connection Successful")
    except Exception as e:
        print(f"❌ MongoDB Async Connection Failed: {e}")

def test_mongo_sync():
    print("\n🧪 Testing MongoDB Sync Client...")
    try:
        client = DatabaseFactory.get_mongo_sync_client()
        client.admin.command('ping')
        print("✅ MongoDB Sync Connection Successful")
    except Exception as e:
        print(f"❌ MongoDB Sync Connection Failed: {e}")

def test_mysql():
    print("\n🧪 Testing MySQL Connection...")
    try:
        engine = DatabaseFactory.get_mysql_engine()
        with engine.connect() as connection:
            print("✅ MySQL Engine Connection Successful")
            
        session = DatabaseFactory.get_mysql_session()
        session.close()
        print("✅ MySQL Session Creation Successful")
    except Exception as e:
        print(f"❌ MySQL Connection Failed: {e}")

if __name__ == "__main__":
    print(f"🔧 Testing DatabaseFactory with:")
    print(f"   MONGO_HOST: {settings.MONGO_HOST}")
    print(f"   MYSQL_DB_URL: {settings.MYSQL_DB_URL}")
    
    # Run Sync Tests
    test_mongo_sync()
    test_mysql()
    
    # Run Async Test
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_mongo_async())
    
    print("\n🎉 All tests completed.")
