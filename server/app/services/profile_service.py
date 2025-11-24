from sqlalchemy.orm import Session
from sqlalchemy import text # SQL 쿼리를 직접 실행

class ProfileService:
    
    def get_user_persona(self, db: Session, user_id: int) -> str:
        """MySQL DB에서 사용자의 모든 정보를 조합하여 RAG 쿼리용 페르소나 텍스트를 생성합니다."""
        
        print(f"user_id={user_id}의 페르소나 생성 시작...")
        
        # 1. users, users_info 테이블 조인 (1:1 관계)
        # Schema Update: 
        # - users: birth, asset_total, investment_tendancy (job 없음)
        # - users_info: goal_amount, annual_income (investment_tendancy 없음)
        user_info_query = text(f"""
            SELECT 
                u.birth, u.asset_total, u.investment_tendancy,
                ui.goal_amount, ui.annual_income
            FROM users u
            JOIN user_info ui ON u.user_id = ui.user_id
            WHERE u.user_id = :user_id
        """)
        user_info = db.execute(user_info_query, {"user_id": user_id}).fetchone()

        if not user_info:
            print(f"사용자 정보(user_id={user_id})를 찾을 수 없습니다.")
            return "일반적인 금융 상품을 추천해줘."

        # 2. user_keyword 테이블 조인 (N:M 관계)
        # Schema Update: user_keyword_map -> user_keyword
        keywords_query = text(f"""
            SELECT k.name
            FROM user_keyword uk
            JOIN keyword k ON uk.keyword_id = k.keyword_id
            WHERE uk.user_id = :user_id
        """)
        keywords_result = db.execute(keywords_query, {"user_id": user_id}).fetchall()
        keywords = [row[0] for row in keywords_result]

        # 3. 페르소나 텍스트 생성
        # (예시: birth(1990-01-01) -> 30대)
        # job 컬럼이 없으므로 제거
        age = "30대" # (실제로는 birth로 계산 로직 필요하지만 일단 고정)
        
        persona = (
            f"사용자 프로필:\n"
            f"- 나이: {age}\n"
            f"- 총 자산: {user_info.asset_total}원, 연 소득: {user_info.annual_income}원\n"
            f"- 투자 성향: {user_info.investment_tendancy}\n"
            f"- 은퇴 목표 금액: {user_info.goal_amount}원\n"
            f"- 희망 키워드: {', '.join(keywords)}"
        )

        
        print(f"생성된 페르sona: {persona}")
        return persona

profile_service = ProfileService()