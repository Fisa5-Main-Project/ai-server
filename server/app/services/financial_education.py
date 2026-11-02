"""Reviewed explanations contain no individual product or allocation advice."""
import re

EXPLANATIONS = {
    '금리': '금리는 돈을 맡기거나 빌릴 때 적용하는 이자의 비율입니다. 실제 이자는 기간, 세금, 우대조건에 따라 달라집니다.',
    '예금': '정기예금은 목돈을 일정 기간 맡기는 방식입니다. 가입 전 만기, 중도해지 조건, 적용 금리와 보호 여부를 확인해야 합니다.',
    '적금': '적금은 정해진 기간 동안 돈을 나누어 납입하는 방식입니다. 월 납입 여력과 중도해지 조건을 확인해야 합니다.',
    '펀드': '펀드는 여러 투자자의 돈을 모아 운용하는 투자 상품입니다. 위험등급과 비용을 확인해야 하며 원금 손실이 발생할 수 있습니다.',
    '연금': '연금 상품은 노후 소득 마련에 활용됩니다. 상품 유형에 따라 원금 손실 가능성, 수령 조건, 중도해지 불이익이 다릅니다.',
    'ETF': 'ETF는 거래소에서 거래되는 펀드입니다. 가격 변동으로 원금 손실이 발생할 수 있으며, 이 서비스의 추천 대상에는 포함되지 않습니다.',
}


def education_answer(message):
    if not re.search(r'란|무엇|뭔|뜻|설명|차이', message):
        return None
    if re.search(r'추천|가입|좋을|좋아|골라|매수|투자할|짜줘', message):
        return None
    explanations = [text for term, text in EXPLANATIONS.items() if term.lower() in message.lower()]
    return '\n'.join(explanations) if explanations else None
