from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AdminService:
    LAST_MESSAGE_TRUNCATE_LENGTH = 50

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
                logger.warning("Warning: 'mysql_db' host not found. Trying 'localhost'...")
                new_url = settings.MYSQL_DB_URL.replace("mysql_db", "localhost")
                self.mysql_engine = create_engine(new_url)
                try:
                    with self.mysql_engine.connect() as conn:
                        logger.info("Successfully connected to MySQL via localhost.")
                except Exception as e2:
                    logger.error(f"Failed to connect to localhost as well: {e2}")
            else:
                logger.error(f"MySQL Connection Error: {e}")

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
                params = {"limit": limit, "offset": offset}
                
                if search:
                    query += " WHERE name LIKE :search OR login_id LIKE :search"
                    params["search"] = f"%{search}%"
                
                query += " LIMIT :limit OFFSET :offset"
                
                users = conn.execute(text(query), params).fetchall()
                
                # 전체 카운트 (페이지네이션용)
                count_query = "SELECT COUNT(*) FROM users"
                count_params = {}
                if search:
                    count_query += " WHERE name LIKE :search OR login_id LIKE :search"
                    count_params["search"] = f"%{search}%"
                total_users = conn.execute(text(count_query), count_params).scalar()

            if not users:
                return {
                    "users": [],
                    "total": total_users,
                    "page": page,
                    "limit": limit
                }

            user_ids = [u[0] for u in users]
            user_map = {u[0]: {"name": u[1], "login_id": u[2]} for u in users}

            # 2. MongoDB Aggregation으로 통계 한 번에 조회 (N+1 해결)
            pipeline = [
                {"$match": {"user_id": {"$in": user_ids}}},
                {"$group": {
                    "_id": "$user_id",
                    "chat_count": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
                    "api_count": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}}
                }}
            ]
            chat_stats = {item["_id"]: item for item in self.chat_history.aggregate(pipeline)}

            # 피드백 통계도 한 번에 조회
            feedback_pipeline = [
                {"$match": {"user_id": {"$in": user_ids}}},
                {"$group": {
                    "_id": "$user_id",
                    "likes": {"$sum": {"$cond": [{"$eq": ["$feedback", "like"]}, 1, 0]}},
                    "dislikes": {"$sum": {"$cond": [{"$eq": ["$feedback", "dislike"]}, 1, 0]}}
                }}
            ]
            feedback_stats = {item["_id"]: item for item in self.chat_logs.aggregate(feedback_pipeline)}

            user_list = []
            for user_id in user_ids:
                c_stat = chat_stats.get(user_id, {"chat_count": 0, "api_count": 0})
                f_stat = feedback_stats.get(user_id, {"likes": 0, "dislikes": 0})
                
                likes = f_stat.get("likes", 0)
                dislikes = f_stat.get("dislikes", 0)
                
                satisfaction = 0
                if likes + dislikes > 0:
                    satisfaction = (likes / (likes + dislikes)) * 100
                
                user_list.append({
                    "user_id": user_id,
                    "name": user_map[user_id]["name"],
                    "login_id": user_map[user_id]["login_id"],
                    "chat_count": c_stat.get("chat_count", 0),
                    "api_count": c_stat.get("api_count", 0),
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
            logger.error(f"Error in get_user_stats: {e}", exc_info=True)
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
            
            if not agg_results:
                 return {
                    "logs": [],
                    "page": page,
                    "limit": limit
                }

            # 사용자 정보 매핑 (N+1 해결)
            user_ids = [r["_id"] for r in agg_results]
            user_name_map = {}
            
            try:
                with self.mysql_engine.connect() as conn:
                    # WHERE IN 절 사용
                    query = text("SELECT user_id, name FROM users WHERE user_id IN :user_ids")
                    # SQLAlchemy의 IN 절 처리를 위해 tuple로 변환하거나 expandparam 사용 필요하지만
                    # text() 사용시에는 :user_ids에 리스트를 넘기면 됨 (driver 지원 여부에 따라 다름)
                    # pymysql/sqlalchemy 조합에서는 리스트 전달 시 자동으로 처리됨
                    users = conn.execute(query, {"user_ids": user_ids}).fetchall()
                    for u in users:
                        user_name_map[u[0]] = u[1]
            except Exception as db_e:
                logger.error(f"MySQL Error in get_chat_logs: {db_e}")
            
            logs = []
            for r in agg_results:
                user_id = r["_id"]
                user_name = user_name_map.get(user_id, f"Unknown({user_id})")
                
                last_msg = r["last_message"]
                if len(last_msg) > self.LAST_MESSAGE_TRUNCATE_LENGTH:
                    last_msg = last_msg[:self.LAST_MESSAGE_TRUNCATE_LENGTH] + "..."

                logs.append({
                    "user_id": user_id,
                    "name": user_name,
                    "last_message": last_msg,
                    "last_active": r["last_active"].isoformat(),
                    "total_messages": r["total_messages"]
                })
                
            return {
                "logs": logs,
                "page": page,
                "limit": limit
            }
        except Exception as e:
            logger.error(f"Error in get_chat_logs: {e}", exc_info=True)
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
        for chat in reversed(chats): 
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
