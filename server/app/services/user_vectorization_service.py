"""
사용자 벡터화 서비스
MySQL DB에서 사용자 정보를 직접 조회하여 임베딩 생성 후 MongoDB에 저장
"""
from app.core.config import settings
from app.services.embedding import embeddings
from pymongo import MongoClient
from datetime import datetime, timezone


class UserVectorizationService:
    def __init__(self):
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.DB_NAME]
        self.user_vectors_collection = self.db["user_vectors"]
    
    def get_user_data_from_db(self, user_id: int) -> dict:
        """MySQL DB에서 사용자 정보 직접 조회"""
        from sqlalchemy import create_engine, text
        
        db_url = settings.MYSQL_DB_URL
        # 로컬 실행 시 Docker 서비스명 'mysql_db'를 'localhost'로 변경 시도
        if "mysql_db" in db_url and "localhost" not in db_url:
            try:
                import socket
                socket.gethostbyname("mysql_db")
            except socket.gaierror:
                print("['mysql_db' 호스트를 찾을 수 없음. 'localhost'로 변경합니다.]")
                db_url = db_url.replace("mysql_db", "localhost")
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # 1. Users 테이블 조회
            user_query = text("SELECT * FROM users WHERE user_id = :user_id")
            user_result = conn.execute(user_query, {"user_id": user_id}).mappings().first()
            
            if not user_result:
                raise ValueError(f"User {user_id} not found in database")
            
            # 2. UserInfo 테이블 조회
            info_query = text("SELECT * FROM user_info WHERE user_id = :user_id")
            info_result = conn.execute(info_query, {"user_id": user_id}).mappings().first()
            
            # 3. Keywords 조회
            keyword_query = text("""
                SELECT k.name 
                FROM keyword k 
                JOIN user_keyword uk ON k.keyword_id = uk.keyword_id 
                WHERE uk.user_id = :user_id
            """)
            keyword_results = conn.execute(keyword_query, {"user_id": user_id}).mappings().all()
            
            # 4. Assets 조회 (자산 분포)
            asset_query = text("SELECT type, balance FROM assets WHERE user_id = :user_id")
            asset_results = conn.execute(asset_query, {"user_id": user_id}).mappings().all()
            
            # 데이터 구조 변환
            user_data = {
                "user": dict(user_result),
                "user_info": dict(info_result) if info_result else {},
                "keywords": [{"name": row["name"]} for row in keyword_results],
                "assets": [{"type": row["type"], "balance": float(row["balance"])} for row in asset_results]
            }
            
            # 날짜/Enum 타입 문자열 변환
            if user_data["user"].get("birth"):
                user_data["user"]["birth"] = str(user_data["user"]["birth"])
            
            return user_data

    def generate_persona_text(self, user_data: dict) -> str:
        """사용자 데이터를 페르소나 텍스트로 변환"""
        user = user_data["user"]
        user_info = user_data.get("user_info", {})
        keywords = user_data.get("keywords", [])
        assets = user_data.get("assets", [])
        
        # 나이 계산
        from datetime import datetime
        birth_str = str(user["birth"])
        birth_year = int(birth_str[:4])
        age = datetime.now().year - birth_year + 1
        
        # 페르소나 텍스트 생성
        persona_parts = []
        
        # 1. 기본 정보
        persona_parts.append(f"{age}세 {user['gender']} 사용자")
        if user.get('investment_tendancy'):
            persona_parts.append(f"투자 성향: {user['investment_tendancy']}")
        
        # 2. 자산 정보 (상세 분포 포함)
        if user.get("asset_total"):
            total_asset = float(user["asset_total"])
            asset_billion = total_asset / 100000000
            
            # 자산 타입별 합계 계산
            asset_breakdown = []
            if assets:
                asset_map = {
                    "CURRENT": "입출금", "SAVING": "예적금", "INVEST": "투자", 
                    "PENSION": "연금", "AUTOMOBILE": "자동차", 
                    "REAL_ESTATE": "부동산", "LOAN": "대출"
                }
                
                # 타입별 그룹화
                type_sums = {}
                for asset in assets:
                    atype = asset["type"]
                    balance = asset["balance"]
                    type_sums[atype] = type_sums.get(atype, 0) + balance
                
                # 문자열 변환
                for atype, balance in type_sums.items():
                    korean_type = asset_map.get(atype, atype)
                    if balance >= 100000000:
                        amount_str = f"{balance/100000000:.1f}억원"
                    else:
                        amount_str = f"{balance/10000:.0f}만원"
                    asset_breakdown.append(f"{korean_type} {amount_str}")
            
            if asset_breakdown:
                persona_parts.append(f"자산 분포: {', '.join(asset_breakdown)} (총 {asset_billion:.1f}억원)")
            else:
                persona_parts.append(f"총 자산: {asset_billion:.1f}억원")
        
        # 3. 상세 정보 (소득, 생활비, 목표)
        if user_info:
            if user_info.get("annual_income"):
                income_million = float(user_info["annual_income"]) / 10000
                persona_parts.append(f"연 소득: {income_million:.0f}만원")
            
            if user_info.get("expectation_monthly_cost"):
                monthly_cost = float(user_info["expectation_monthly_cost"]) / 10000
                persona_parts.append(f"은퇴 후 희망 월 생활비: {monthly_cost:.0f}만원")
            
            if user_info.get("target_retired_age") and user_info["target_retired_age"] > 0:
                persona_parts.append(f"희망 은퇴 나이: {user_info['target_retired_age']}세")
            
            if user_info.get("goal_amount"):
                goal_billion = float(user_info["goal_amount"]) / 100000000
                persona_parts.append(f"목표 자산: {goal_billion:.1f}억원")
        
        # 4. 은퇴 후 희망 키워드
        if keywords:
            keyword_names = [kw["name"] for kw in keywords]
            persona_parts.append(f"관심 키워드: {', '.join(keyword_names)}")
        
        persona_text = ". ".join(persona_parts) + "."
        return persona_text

    async def vectorize_user(self, user_id: int) -> dict:
        """사용자 벡터화 실행"""
        try:
            # 1. DB에서 사용자 데이터 가져오기 (Spring Boot API 대신 직접 조회)
            try:
                user_data = self.get_user_data_from_db(user_id)
                print(f"[User {user_id}] DB 조회 성공")
            except Exception as db_error:
                # print(f"[User {user_id}] DB 조회 실패: {db_error}")
                # # DB 조회 실패 시 더미 데이터 사용 (테스트용)
                # print(f"[User {user_id}] 더미 데이터 사용")
                # user_data = {
                #     "user": {
                #         "birth": "2001-03-24",
                #         "gender": "M",
                #         "investment_tendancy": "안정추구형",
                #         "asset_total": 711200000
                #     },
                #     "user_info": {
                #         "annual_income": 1332,
                #         "expectation_monthly_cost": 333333,
                #         "target_retired_age": 65,
                #         "goal_amount": 1000000000
                #     },
                #     "keywords": [
                #         {"name": "안정적 생활비"},
                #         {"name": "여행"},
                #         {"name": "가족/교류"}
                #     ]
                # }
                raise ValueError(f"User {user_id}의 데이터베이스 조회에 실패했습니다.")
            
            # 2. 페르소나 텍스트 생성
            persona_text = self.generate_persona_text(user_data)
            
            # 3. 임베딩 생성
            embedding_vector = embeddings.embed_query(persona_text)
            
            # 4. MongoDB에 저장
            user_vector_doc = {
                "_id": f"user_{user_id}",
                "user_id": user_id,
                "persona_text": persona_text,
                "embedding": embedding_vector,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            self.user_vectors_collection.update_one(
                {"_id": f"user_{user_id}"},
                {"$set": user_vector_doc},
                upsert=True
            )
            
            print(f"[User {user_id}] 벡터화 완료")
            
            return {
                "user_id": user_id,
                "persona_text": persona_text,
                "status": "success"
            }
        
        except Exception as e:
            print(f"[User {user_id}] 벡터화 실패: {e}")
            raise
    
    def get_user_embedding(self, user_id: int) -> list:
        """저장된 사용자 임베딩 가져오기"""
        user_vector = self.user_vectors_collection.find_one({"_id": f"user_{user_id}"})
        if user_vector:
            return user_vector["embedding"]
        return None


user_vectorization_service = UserVectorizationService()
