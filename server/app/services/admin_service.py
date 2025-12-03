from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from app.core.config import settings
import pandas as pd

class AdminService:
    def __init__(self):
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_history = self.db["chat_history"]
        self.chat_logs = self.db["chat_logs"]
        
        self.mysql_engine = create_engine(settings.MYSQL_DB_URL)

        # Connection check and fix for local dev (mysql_db -> localhost)
        try:
            with self.mysql_engine.connect() as conn:
                pass
        except Exception as e:
            error_msg = str(e)
            if "getaddrinfo failed" in error_msg and "mysql_db" in settings.MYSQL_DB_URL:
                print("Warning: 'mysql_db' host not found. Trying 'localhost'...")
                new_url = settings.MYSQL_DB_URL.replace("mysql_db", "localhost")
                self.mysql_engine = create_engine(new_url)
                try:
                    with self.mysql_engine.connect() as conn:
                        print("Successfully connected to MySQL via localhost.")
                except Exception as e2:
                    print(f"Failed to connect to localhost as well: {e2}")
            else:
                print(f"MySQL Connection Error: {e}")

    def get_dashboard_stats(self) -> Dict:
        """대시보드 전체 통계"""
        now = datetime.utcnow()
        last_month = now - timedelta(days=30)
        
        # 1. 총 대화 건수 (세션 수 기준이 아닌 메시지 수 기준)
        total_chats = self.chat_history.count_documents({"role": "user"})
        
        # 2. 총 API 요청 (챗봇 응답 수)
        total_api_calls = self.chat_history.count_documents({"role": "assistant"})
        
        # 3. 평균 만족도 (좋아요 비율)
        total_feedback = self.chat_logs.count_documents({"feedback": {"$in": ["like", "dislike"]}})
        likes = self.chat_logs.count_documents({"feedback": "like"})
        satisfaction_rate = (likes / total_feedback * 100) if total_feedback > 0 else 0
        
        # 4. 활성 사용자 (최근 30일 내 대화한 사용자)
        active_users = len(self.chat_history.distinct("user_id", {"timestamp": {"$gte": last_month}}))
        
        return {
            "total_chats": total_chats,
            "total_api_calls": total_api_calls,
            "satisfaction_rate": round(satisfaction_rate, 1),
            "active_users": active_users
        }

    def get_dashboard_trends(self) -> Dict:
        """대화 및 API 요청 추이 (최근 6개월)"""
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"}
                    },
                    "count": {"$sum": 1},
                    "api_calls": {
                        "$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}
                    },
                    "user_chats": {
                        "$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}
                    }
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]
        
        results = list(self.chat_history.aggregate(pipeline))
        
        # 포맷팅
        formatted_results = []
        for r in results:
            formatted_results.append({
                "date": f"{r['_id']['year']}-{r['_id']['month']:02d}",
                "api_calls": r["api_calls"],
                "user_chats": r["user_chats"]
            })
            
        return {"trends": formatted_results}

    def get_feedback_stats(self) -> Dict:
        """피드백 분포"""
        pipeline = [
            {"$group": {"_id": "$feedback", "count": {"$sum": 1}}}
        ]
        results = list(self.chat_logs.aggregate(pipeline))
        
        stats = {"like": 0, "dislike": 0}
        for r in results:
            if r["_id"] in stats:
                stats[r["_id"]] = r["count"]
                
        return stats

    def get_user_stats(self, page: int = 1, limit: int = 10, search: str = "") -> Dict:
        """사용자별 AI 사용 통계"""
        try:
            offset = (page - 1) * limit
            
            # 1. MySQL에서 사용자 목록 조회
            with self.mysql_engine.connect() as conn:
                query = "SELECT user_id, name, login_id FROM users"
                params = {}
                
                if search:
                    query += " WHERE name LIKE :search OR login_id LIKE :search"
                    params["search"] = f"%{search}%"
                
                query += f" LIMIT {limit} OFFSET {offset}"
                
                users = conn.execute(text(query), params).fetchall()
                
                # 전체 카운트 (페이지네이션용)
                count_query = "SELECT COUNT(*) FROM users"
                if search:
                    count_query += " WHERE name LIKE :search OR login_id LIKE :search"
                total_users = conn.execute(text(count_query), params).scalar()

            user_list = []
            for user in users:
                user_id = user[0]
                
                # MongoDB에서 해당 사용자의 통계 집계
                chat_count = self.chat_history.count_documents({"user_id": user_id, "role": "user"})
                api_count = self.chat_history.count_documents({"user_id": user_id, "role": "assistant"})
                
                likes = self.chat_logs.count_documents({"user_id": user_id, "feedback": "like"})
                dislikes = self.chat_logs.count_documents({"user_id": user_id, "feedback": "dislike"})
                
                satisfaction = 0
                if likes + dislikes > 0:
                    satisfaction = (likes / (likes + dislikes)) * 100
                
                user_list.append({
                    "user_id": user_id,
                    "name": user[1],
                    "login_id": user[2],
                    "chat_count": chat_count,
                    "api_count": api_count,
                    "likes": likes,
                    "dislikes": dislikes,
                    "satisfaction": round(satisfaction, 1)
                })
                
            return {
                "users": user_list,
                "total": total_users,
                "page": page,
                "limit": limit
            }
        except Exception as e:
            import traceback
            print(f"Error in get_user_stats: {e}")
            print(traceback.format_exc())
            raise e

    def get_chat_logs(self, page: int = 1, limit: int = 10, search: str = "") -> Dict:
        """챗봇 대화 로그 목록 (최근 대화순)"""
        try:
            skip = (page - 1) * limit
            
            match_stage = {}
            if search:
                if search.isdigit():
                     match_stage["user_id"] = int(search)
            
            pipeline = [
                {"$match": match_stage},
                {"$sort": {"timestamp": -1}},
                {"$group": {
                    "_id": "$user_id",
                    "last_message": {"$first": "$content"},
                    "last_active": {"$first": "$timestamp"},
                    "total_messages": {"$sum": 1}
                }},
                {"$sort": {"last_active": -1}},
                {"$skip": skip},
                {"$limit": limit}
            ]
            
            agg_results = list(self.chat_history.aggregate(pipeline))
            
            # 사용자 정보 매핑
            logs = []
            for r in agg_results:
                user_id = r["_id"]
                
                # MySQL에서 사용자 이름 조회
                try:
                    with self.mysql_engine.connect() as conn:
                        user = conn.execute(
                            text("SELECT name FROM users WHERE user_id = :uid"),
                            {"uid": user_id}
                        ).first()
                        user_name = user[0] if user else f"Unknown({user_id})"
                except Exception as db_e:
                    print(f"MySQL Error in get_chat_logs for user {user_id}: {db_e}")
                    user_name = f"Error({user_id})"
                
                logs.append({
                    "user_id": user_id,
                    "name": user_name,
                    "last_message": r["last_message"][:50] + "..." if len(r["last_message"]) > 50 else r["last_message"],
                    "last_active": r["last_active"].isoformat(),
                    "total_messages": r["total_messages"]
                })
                
            return {
                "logs": logs,
                "page": page,
                "limit": limit
            }
        except Exception as e:
            import traceback
            print(f"Error in get_chat_logs: {e}")
            print(traceback.format_exc())
            raise e

    def get_user_chat_history(self, user_id: int, page: int = 1, limit: int = 20) -> Dict:
        """특정 사용자의 전체 대화 상세 내역 (페이지네이션 적용)"""
        skip = (page - 1) * limit
        
        total_count = self.chat_history.count_documents({"user_id": user_id})
        
        chats = list(self.chat_history.find({"user_id": user_id})
                     .sort("timestamp", -1)  # 최신순으로 정렬
                     .skip(skip)
                     .limit(limit))
        
        history = []
        for chat in reversed(chats): # UI에서는 과거->현재 순으로 보여주는게 일반적이지만, 페이징은 최신순으로 가져와서 뒤집는게 나을수도. 
            # 하지만 보통 채팅 로그는 위로 스크롤하며 과거를 로딩하거나, 아래로 스크롤하며 최신을 로딩함.
            # 관리자 페이지라면 최신순으로 리스트를 보여주거나, 
            # 전체 대화 흐름을 보려면 과거 -> 현재 순이어야 함.
            # 요청사항: "나눠서 보내주세요" -> 페이지네이션.
            # 여기서는 최신순으로 가져와서 반환하되, 클라이언트가 정렬하도록 하거나
            # timestamp 기준으로 정렬해서 반환.
            # 일단 최신순으로 가져온 것을 다시 시간순(과거->현재)으로 정렬해서 반환하는게 보기 좋음.
            history.append({
                "role": chat["role"],
                "content": chat["content"],
                "timestamp": chat["timestamp"].isoformat()
            })
            
        return {
            "history": history, # 이미 reversed 했으므로 과거 -> 현재 순
            "total": total_count,
            "page": page,
            "limit": limit
        }

admin_service = AdminService()
