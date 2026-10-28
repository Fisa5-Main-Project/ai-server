"""Deterministic persona projection, independent of databases and embedding APIs."""
from datetime import date
from decimal import Decimal
from hashlib import sha256


def money(value):
    return format(Decimal(str(value)), "f")


def build_persona(data: dict, today: date | None = None) -> str:
    user = data["user"]
    info = data.get("user_info", {})
    today = today or date.today()
    birth = date.fromisoformat(str(user["birth"])[:10])
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    parts = [f"만 {age}세 {user.get('gender', '')} 사용자"]
    if user.get("investment_tendancy"):
        parts.append(f"투자 성향: {user['investment_tendancy']}")
    # Exact amounts prevent small balance changes disappearing through rounding.
    if user.get("asset_total") is not None:
        parts.append(f"원천 프로필 총 자산: {money(user['asset_total'])}원")
    balances = {}
    for asset in data.get("assets", []):
        kind = asset["type"]
        balances[kind] = balances.get(kind, Decimal(0)) + Decimal(str(asset["balance"]))
    if balances:
        labels = {"CURRENT": "입출금", "SAVING": "예적금", "INVEST": "투자", "PENSION": "연금",
                  "AUTOMOBILE": "자동차", "REAL_ESTATE": "부동산", "LOAN": "대출"}
        parts.append("현재 자산 분포: " + ", ".join(
            f"{labels.get(kind, kind)} {money(amount)}원" for kind, amount in sorted(balances.items())))
        gross = sum((v for k, v in balances.items() if k != "LOAN"), Decimal(0))
        debt = balances.get("LOAN", Decimal(0))
        parts.append(f"현재 추천 기준 총 자산: {money(gross)}원, 대출: {money(debt)}원, 순자산: {money(gross - debt)}원")
        parts.append("현재 자산 판단은 자산 내역 기준 금액을 우선 사용")
    fields = {
        "annual_income": ("연 소득", "원"), "expectation_monthly_cost": ("은퇴 후 희망 월 생활비", "원"),
        "fixed_monthly_cost": ("고정 월 생활비", "원"), "goal_amount": ("목표 자산", "원"),
        "target_retired_age": ("희망 은퇴 나이", "세"), "goal_target_date": ("목표 달성일", ""),
        "num_dependents": ("부양가족 수", "명"), "mydata_status": ("마이데이터 상태", ""),
    }
    for key, (label, unit) in fields.items():
        if info.get(key) is not None:
            value = money(info[key]) if unit == "원" else str(info[key])
            parts.append(f"{label}: {value}{unit}")
    if info.get("retirement_status") is not None:
        parts.append("은퇴 상태: " + ("은퇴" if info["retirement_status"] else "은퇴 전"))
    if user.get("user_mydata_registration") is not None:
        parts.append("마이데이터 등록: " + ("등록" if user["user_mydata_registration"] else "미등록"))
    names = sorted({kw["name"] for kw in data.get("keywords", [])})
    if names:
        parts.append("관심 키워드: " + ", ".join(names))
    return ". ".join(parts) + "."


def persona_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
