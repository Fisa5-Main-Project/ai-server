"""
상품 추천 서비스 로직 (Refactored)
"""
import logging
from datetime import datetime, timezone
from uuid import uuid4
import asyncio
from typing import List

from app.rag.suitability import POLICY_VERSION, build_profile
from app.gateway.errors import GatewayError

logger = logging.getLogger(__name__)

from app.rag.graphs.product_graph import build_product_graph
from app.services.user_vectorization_service import user_vectorization_service
from app.schemas.recommendation import RecommendationResponse, RecommendedProduct
from app.schemas.chat import ChatProduct

# 그래프는 싱글톤으로 생성
product_graph = build_product_graph()

COMPANY_URLS = {
    "국민": "https://www.kbstar.com/",
    "KB": "https://www.kbstar.com/",
    "신한": "https://www.shinhan.com/",
    "하나": "https://www.kebhana.com/",
    "우리": "https://www.wooribank.com/",
    "농협": "https://banking.nonghyup.com/",
    "NH": "https://banking.nonghyup.com/",
    "엔에이치": "https://banking.nonghyup.com/",
    "기업": "https://www.ibk.co.kr/",
    "IBK": "https://www.ibk.co.kr/",
    "카카오": "https://www.kakaobank.com/",
    "토스": "https://www.tossbank.com/",
    "케이": "https://www.kbanknow.com/",
    "삼성": "https://www.samsungpop.com/",
    "미래": "https://securities.miraeasset.com/",
    "한국투자": "https://securities.koreainvestment.com/",
    "키움": "https://www.kiwoom.com/",
    "대신": "https://www.daishin.com/",
    "메리츠": "https://home.meritz.co.kr/",
    "부산": "https://www.busanbank.co.kr/",
    "광주": "https://www.kjbank.com/",
    "전북": "https://www.jbbank.co.kr/",
    "SC": "https://www.standardchartered.co.kr/",
    "대구": "https://www.dgb.co.kr/",
    "경남": "https://www.knbank.co.kr/",
    "수협": "https://suhyup-bank.com/",
    "신협": "https://www.cu.co.kr/",
    "우체국": "https://www.epostbank.go.kr/",
    "새마을": "https://www.kfcc.co.kr/",
    "한화": "https://www.hanwhawm.com/",
    "유안타": "https://www.myasset.com/",
    "유진": "https://www.eugenefn.com/",
    "교보": "https://www.iprovest.com/",
    "하이": "https://www.hi-ib.com/",
    "현대": "https://www.hmsec.com/",
    "DB": "https://www.db-fi.com/",
    "SK": "https://www.sks.co.kr/",
    "LS": "https://www.ls-sec.co.kr/",
}

from pymongo import MongoClient
from app.core.config import settings

class ProductsService:
    def __init__(self):
        self.mongo_client = MongoClient(settings.MONGO_DB_URL, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=10000)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_logs_collection = self.db["chat_logs"]
        self.audit_collection = self.db["recommendation_audits"]

    def _feedback(self, user_id):
        liked, disliked = set(), set()
        for log in self.chat_logs_collection.find(
            {"user_id": user_id, "feedback": {"$in": ["like", "dislike"]}},
            {"product_id": 1, "feedback": 1},
        ):
            pid = log.get("product_id")
            if pid:
                (disliked if log["feedback"] == "dislike" else liked).add(str(pid))
        return sorted(liked - disliked), sorted(disliked)

    async def get_recommendations(self, user_id: int, user_message: str = "", persona_text: str | None = None) -> RecommendationResponse:
        """Read a fresh structured source profile; prose cannot change eligibility."""
        request_id = str(uuid4())
        record = {"request_id": request_id, "user_id": user_id,
                  "timestamp": datetime.now(timezone.utc), "policy_version": POLICY_VERSION}
        try:
            snapshot, user_embedding = await asyncio.to_thread(
                user_vectorization_service.get_recommendation_context, user_id)
            profile = build_profile(snapshot)
            liked, disliked = await asyncio.to_thread(self._feedback, user_id)
            result = await product_graph.ainvoke({
                "query": user_message, "profile": profile, "liked": liked, "disliked": disliked,
                "user_embedding": user_embedding,
            })
            products = [RecommendedProduct(**p) for p in result["products"]]
            record.update({"status": "completed", "profile": {
                "tendency": profile["tendency"],
                "available_funds": str(profile["available_funds"]) if profile["available_funds"] is not None else None,
            }, "intent": result["intent"], "decisions": result["decisions"],
                "products": [p.model_dump() for p in products]})
            # Do not release recommendations if the validation audit cannot be persisted.
            await asyncio.to_thread(self.audit_collection.insert_one, record)
            return RecommendationResponse(products=products, request_id=request_id,
                status="ok" if products else "no_suitable_products",
                message=None if products else "요청 조건과 투자 성향에 맞고 가입 조건이 확인된 상품이 없습니다.")
        except GatewayError:
            raise
        except Exception as exc:
            logger.warning("Recommendation withheld request_id=%s error_type=%s", request_id, type(exc).__name__)
            try:
                await asyncio.to_thread(self.audit_collection.insert_one, {
                    "request_id": request_id, "user_id": user_id,
                    "timestamp": datetime.now(timezone.utc), "policy_version": POLICY_VERSION,
                    "status": "withheld", "error_type": type(exc).__name__,
                })
            except Exception:
                logger.error("Recommendation audit unavailable request_id=%s", request_id)
            return RecommendationResponse(products=[], request_id=request_id, status="unavailable",
                message="고객 정보 또는 상품 검증 정보를 확인할 수 없어 추천을 보류했습니다.")

    def _convert_to_chat_product(self, product: RecommendedProduct, icon: str) -> ChatProduct:
        """RecommendedProduct를 ChatProduct로 변환"""
        
        link = f"https://search.naver.com/search.naver?query={product.company_name} {product.product_name}"
        
        for key, url in COMPANY_URLS.items():
            if key in product.company_name:
                link = url
                break

        return ChatProduct(
            id=product.product_id,
            icon=icon,
            type=product.product_type,
            name=product.product_name,
            bank=product.company_name,
            features=[product.reason],
            stat=product.benefit,
            link=link
        )

    async def get_chat_products(self, user_id: int, user_message: str = "", persona_text: str | None = None) -> List[ChatProduct]:
        """챗봇용 상품 추천 목록 반환"""
        rec_response = await self.get_recommendations(user_id, user_message, persona_text=persona_text)
        products = []
        
        if rec_response.products:
            for p in rec_response.products:
                icon = "💰"
                if "연금" in (p.product_type or ""):
                    icon = "🎯"
                elif "펀드" in (p.product_type or ""):
                    icon = "📈"
                
                products.append(self._convert_to_chat_product(p, icon))
        
        return products

products_service = ProductsService()
