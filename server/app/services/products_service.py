"""
상품 추천 서비스 로직 (Refactored)
"""
import json
import re
from typing import List

from langchain_core.messages import HumanMessage

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
        self.mongo_client = MongoClient(settings.MONGO_DB_URL)
        self.db = self.mongo_client[settings.MONGO_DB_NAME]
        self.chat_logs_collection = self.db["chat_logs"]

    def _apply_feedback_reranking(self, user_id: int, products: List[RecommendedProduct]) -> List[RecommendedProduct]:
        """사용자 피드백 기반 재정렬 (Dislike 제거, Like 상단 노출)"""
        try:
            # 사용자의 모든 피드백 조회
            feedbacks = self.chat_logs_collection.find(
                {"user_id": user_id, "feedback": {"$in": ["like", "dislike"]}}
            )
            
            liked_products = set()
            disliked_products = set()
            
            for log in feedbacks:
                pid = log.get("product_id")
                if not pid: continue
                
                if log["feedback"] == "like":
                    liked_products.add(pid)
                elif log["feedback"] == "dislike":
                    disliked_products.add(pid)
            
            # 1. Dislike 필터링 (싫어요 한 상품 제거)
            filtered_products = [p for p in products if p.product_id not in disliked_products]
            
            # 2. Like 상단 노출 (좋아요 한 상품 우선 정렬)
            # liked에 있으면 0 (앞), 없으면 1 (뒤) -> 오름차순 정렬
            filtered_products.sort(key=lambda p: 0 if p.product_id in liked_products else 1)
            
            return filtered_products
            
        except Exception as e:
            print(f"피드백 재정렬 실패: {e}")
            return products

    async def get_recommendations(self, user_id: int, user_message: str = "") -> RecommendationResponse:
        """사용자 임베딩 기반 금융상품 추천"""
        
        # 1. 사용자 페르소나 가져오기
        user_vector = user_vectorization_service.user_vectors_collection.find_one(
            {"_id": f"user_{user_id}"}
        )
        
        if not user_vector:
            await user_vectorization_service.vectorize_user(user_id)
            user_vector = user_vectorization_service.user_vectors_collection.find_one(
                {"_id": f"user_{user_id}"}
            )
        
        persona = user_vector["persona_text"]
        
        try:
            # 2. Agent Graph 실행
            content = f"{persona}\n\n사용자 요청: {user_message}" if user_message else persona
            
            result = await product_graph.ainvoke({
                "messages": [HumanMessage(content=content)],
                "persona": persona
            })
            
            # 3. 마지막 메시지에서 JSON 추출
            last_message = result["messages"][-1]
            response_text = last_message.content
            
            # 4. JSON 파싱 (개선된 로직)
            json_str = ""
            
            # 4-1. Markdown Code Block 패턴 우선 검색 (```json ... ```)
            code_block_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if code_block_match:
                json_str = code_block_match.group(1)
            else:
                # 4-2. 일반 Code Block 패턴 검색 (``` ... ```)
                code_block_match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
                if code_block_match:
                    json_str = code_block_match.group(1)
                else:
                    # 4-3. 최후의 수단: 가장 바깥쪽 중괄호 찾기
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()
            
            if json_str:
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"JSON 파싱 에러: {e}\n원본 텍스트: {json_str}")
                    # 간단한 복구 시도 (예: trailing comma)
                    try:
                        import ast
                        data = ast.literal_eval(json_str)
                    except:
                        return RecommendationResponse(products=[])

                
                products = []
                if data.get("products"):
                    for p in data["products"]:
                        products.append(RecommendedProduct(**p))
                
                # Legacy format fallback
                if not products:
                    if data.get("deposit_or_saving"):
                        products.append(RecommendedProduct(**data["deposit_or_saving"]))
                    if data.get("annuity"):
                        products.append(RecommendedProduct(**data["annuity"]))
                    if data.get("fund"):
                        products.append(RecommendedProduct(**data["fund"]))

                # 5. 피드백 기반 재정렬 적용
                products = self._apply_feedback_reranking(user_id, products)

                return RecommendationResponse(products=products)
            else:
                print(f"JSON 형식을 찾을 수 없습니다: {response_text}")
                return RecommendationResponse(products=[])
        
        except Exception as e:
            print(f"Agent 실행 실패: {e}")
            import traceback
            traceback.print_exc()
            return RecommendationResponse(products=[])

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

    async def get_chat_products(self, user_id: int, user_message: str = "") -> List[ChatProduct]:
        """챗봇용 상품 추천 목록 반환"""
        rec_response = await self.get_recommendations(user_id, user_message)
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
