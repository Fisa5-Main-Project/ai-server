"""Conservative service policy, not an assertion of regulatory suitability.

Grade 1 is highest risk, 6 lowest. Missing evidence always fails closed.
Only trusted catalogue metadata and source database profiles enter this module.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

POLICY_VERSION = 'senior-conservative-v1'
PROFILE_FLOORS = {'원금보장형': 6, '안정형': 6, '안정추구형': 5,
                  '위험중립형': 4, '적극투자형': 4, '공격투자형': 4}
CATEGORIES = {'예금': 'deposit', '적금': 'saving', '연금': 'annuity', '펀드': 'fund'}
LABELS = {'deposit': '예금', 'saving': '적금', 'annuity': '연금저축', 'fund': '펀드'}
COMPANIES = ('우리은행', '국민은행', '신한은행', '하나은행', '농협은행', '기업은행',
             '카카오뱅크', '토스뱅크', '케이뱅크', '부산은행', '대구은행', '경남은행',
             '광주은행', '전북은행', '수협은행', 'SC제일은행', '우체국')
NEGATION = r'(?:은|는|을|를)?\s*(?:말고|제외|빼|싫|원하지|안\s*(?:할|하|원))'


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def build_profile(snapshot):
    user = snapshot.get('user', {})
    liquid = [amount(a.get('balance')) for a in snapshot.get('assets', []) if a.get('type') == 'CURRENT']
    funds = sum(liquid, Decimal(0)) if liquid and all(v is not None for v in liquid) else None
    return {'tendency': user.get('investment_tendancy'), 'available_funds': funds}


def resolve_intent(query, interpretation):
    """Explicit request constraints take precedence over untrusted LLM output."""
    query = query or ''
    excluded = {value for key, value in CATEGORIES.items()
                if re.search(key + NEGATION, query)}
    explicit = [value for key, value in CATEGORIES.items() if key in query and value not in excluded]
    if '예적금' in query or '예/적금' in query:
        explicit = [v for v in ('deposit', 'saving') if v not in excluded]
    proposed = interpretation.get('categories', [])
    proposed = proposed if isinstance(proposed, list) else []
    categories = explicit or [v for v in proposed if v in ('deposit', 'saving') and v not in excluded]
    unsupported = bool(re.search(r'비트코인|가상화폐|암호화폐|코인|주식|ETF|ELS|파생|레버리지|인버스|부동산|대출|맛집|영화|일자리|취업|게임|여행', query, re.I))
    # General requests default to capital-preserving product categories, never a mandatory fund allocation.
    generic = not query or bool(re.search(r'추천|상품|노후|저축|목돈', query))
    if not categories and generic and not unsupported:
        categories = [v for v in ('deposit', 'saving') if v not in excluded]
    companies = [name for name in COMPANIES if name in query]
    aliases = [('국민', '국민은행'), ('농협', '농협은행'), ('기업', '기업은행')]
    for alias, name in aliases:
        if alias in query and name not in companies:
            companies.append(name)
    # Unrecognized explicit company names are retained as hard constraints too.
    companies += [v for v in re.findall(r'[가-힣A-Za-z]+(?:은행|증권|자산운용)', query) if v not in companies]
    company = interpretation.get('company')
    if not companies and isinstance(company, str) and company.strip():
        companies = [company.strip()]
    excluded_companies = [c for c in companies if re.search(re.escape(c) + NEGATION, query)]
    excluded_companies.extend(name for alias, name in aliases
                              if re.search(re.escape(alias) + NEGATION, query) and name not in excluded_companies)
    companies = [c for c in companies if c not in excluded_companies]
    budgets = [Decimal(number.replace(',', '')) * {'': 1, '만': 10000, '억': 100000000}[unit]
               for number, unit in re.findall(r'(\d[\d,]*(?:\.\d+)?)\s*(억|만)?\s*원', query)]
    terms = [int(number) * (12 if unit == '년' else 1)
             for number, unit in re.findall(r'(\d+)\s*(개월|년)', query)]
    return {'categories': categories, 'companies': companies,
            'excluded_companies': excluded_companies,
            'budget': str(min(budgets)) if budgets else None,
            'max_term_months': min(terms) if terms else None,
            'supported': not unsupported and bool(categories),
            'principal_only': bool(re.search(r'원금|손실\s*없|안전|안정', query))}


def assess(product, profile, intent, disliked, today=None):
    today = today or date.today()
    reasons = []
    kind = product.get('product_type')
    if kind not in LABELS:
        reasons.append('unsupported_product')
    if not intent.get('supported'):
        reasons.append('request_unsupported')
    if kind not in intent.get('categories', []):
        reasons.append('category_mismatch')
    companies = intent.get('companies', [])
    if companies and not any(c in product.get('company_name', '') for c in companies):
        reasons.append('company_mismatch')
    if any(c in product.get('company_name', '') for c in intent.get('excluded_companies', [])):
        reasons.append('company_excluded')
    if not product.get('product_id') or not product.get('product_name') or not product.get('company_name'):
        reasons.append('identity_unknown')
    if product.get('product_id') in disliked:
        reasons.append('disliked')
    floor = PROFILE_FLOORS.get(profile.get('tendency'))
    if floor is None:
        reasons.append('profile_unknown')
    grade = product.get('risk_grade')
    if type(grade) is not int or not 1 <= grade <= 6:
        reasons.append('risk_unknown')
    else:
        if grade < 4:
            reasons.append('risk_exceeds_policy')
        if floor is not None and grade < floor:
            reasons.append('risk_exceeds_profile')
    if (profile.get('tendency') in ('원금보장형', '안정형') or intent.get('principal_only')) and product.get('principal_guaranteed') is not True:
        reasons.append('principal_not_guaranteed')
    if product.get('retail_available') is not True:
        reasons.append('not_retail')
    if product.get('eligibility_unrestricted') is not True:
        reasons.append('eligibility_unverified')
    if not isinstance(product.get('evidence_source'), str) or not product['evidence_source'].strip():
        reasons.append('metadata_unverified')
    if product.get('schema_version') == 2 and product.get('verification_status') != 'verified':
        reasons.append('evidence_unverified')
    try:
        age = (today - date.fromisoformat(product.get('verified_on', ''))).days
        if not 0 <= age <= 30:
            reasons.append('metadata_stale')
    except (TypeError, ValueError):
        reasons.append('metadata_unverified')
    if product.get('schema_version') == 2:
        # A current listing is evidence of availability, not a fabricated sale-end date.
        if product.get('sales_status') != 'listed':
            reasons.append('availability_unknown')
    else:
        try:
            if date.fromisoformat(product.get('valid_until', '')) < today:
                reasons.append('product_expired')
        except (TypeError, ValueError):
            reasons.append('expiry_unknown')
    funds, minimum = amount(profile.get('available_funds')), amount(product.get('min_amount'))
    if minimum is None:
        reasons.append('amount_unknown')
    if funds is None:
        reasons.append('funds_unknown')
    elif funds <= 0 or (minimum is not None and funds < minimum):
        reasons.append('insufficient_funds')
    budget = amount(intent.get('budget'))
    if budget is not None and minimum is not None and minimum > budget:
        reasons.append('budget_exceeded')
    if intent.get('max_term_months') is not None:
        term = product.get('term_months')
        if type(term) is not int or term < 0:
            reasons.append('term_unknown')
        elif term > intent['max_term_months']:
            reasons.append('term_exceeded')
    return reasons


def render_product(product):
    """Canonical fields only: never render LLM invented identities or returns."""
    internal = (product.get('risk_assessment') or {}).get('basis') == 'internal_policy'
    risk_label = ('내부 위험분류: ' + {'low': '낮음', 'high': '높음', 'unknown': '미확인'}[product['risk_assessment']['level']]
                  if internal else f"위험 {product['risk_grade']}등급")
    reason = f"요청 조건과 투자 성향, 최소 가입금액을 확인했습니다. {risk_label}."
    if internal:
        reason += ' 공식 투자위험등급이 아닌 상품 구조와 확인 근거에 따른 서비스 분류입니다.'
        if product['product_type'] in ('deposit', 'saving'):
            reason += ' 예금자보호에는 금융회사별 합산 한도가 있으며 중도해지 시 이자가 줄어들 수 있습니다.'
    if product['product_type'] not in ('deposit', 'saving') and product.get('principal_guaranteed') is not True:
        reason += ' 투자 상품은 원금 손실 가능성이 있습니다.'
    return {'product_id': product['product_id'], 'product_type': LABELS[product['product_type']],
            'product_name': product['product_name'], 'company_name': product['company_name'],
            'benefit': f"{risk_label} · 최소 가입금액 {product['min_amount']}원",
            'risk_basis': 'internal_policy' if internal else 'provided_metadata',
            'evidence_url': product.get('evidence_source'),
            'reason': reason, 'min_amount': int(Decimal(str(product['min_amount'])))}
