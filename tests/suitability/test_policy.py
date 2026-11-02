import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))

from app.rag.suitability import assess, build_profile, resolve_intent

TODAY = date(2026, 11, 2)


def profile(tendency='안정추구형', balance=1000000):
    return build_profile({'user': {'investment_tendancy': tendency},
                          'assets': [{'type': 'CURRENT', 'balance': balance}]})


def product(**changes):
    value = {'product_id': 'd1', 'product_type': 'deposit', 'product_name': '정기예금',
             'company_name': '우리은행', 'risk_grade': 6, 'principal_guaranteed': True,
             'min_amount': 10000, 'eligibility_unrestricted': True, 'retail_available': True,
             'verified_on': TODAY.isoformat(), 'evidence_source': 'issuer document',
             'valid_until': '2026-12-01'}
    value.update(changes)
    return value


def reasons(p, user=None, request='예금 추천', disliked=()):
    return assess(p, user or profile(), resolve_intent(request, {}), set(disliked), TODAY)


def test_verified_affordable_deposit_is_allowed():
    assert reasons(product()) == []


def test_high_risk_rejected_even_for_aggressive_customer():
    assert 'risk_exceeds_policy' in reasons(product(product_type='fund', risk_grade=2),
        profile('공격투자형'), '펀드 추천')


def test_conservative_customer_cannot_receive_grade_four_fund():
    assert 'risk_exceeds_profile' in reasons(product(product_type='fund', risk_grade=4), request='펀드 추천')


def test_missing_and_invalid_risk_never_inferred_from_name():
    for value in (None, True, 0, 7, '안전', 5.5):
        assert 'risk_unknown' in reasons(product(risk_grade=value))


def test_unknown_customer_profile_blocks_recommendation():
    assert 'profile_unknown' in reasons(product(), profile('미등록'))


def test_assets_must_be_liquid_and_sufficient():
    assert 'insufficient_funds' in reasons(product(), profile(balance=1))
    p = build_profile({'user': {'investment_tendancy': '원금보장형', 'asset_total': 999999999},
                       'assets': [{'type': 'REAL_ESTATE', 'balance': 999999999}]})
    assert 'funds_unknown' in reasons(product(), p)


def test_nonfinite_or_negative_assets_are_unknown():
    for value in ('NaN', 'Infinity', -1, True):
        assert 'funds_unknown' in reasons(product(), profile(balance=value))


def test_disliked_product_is_blocked_before_response():
    assert 'disliked' in reasons(product(), disliked=['d1'])


def test_unrelated_category_and_company_are_blocked():
    assert 'category_mismatch' in reasons(product(product_type='fund'), request='우리은행 예금 추천')
    assert 'company_mismatch' in reasons(product(company_name='신한은행'), request='우리은행 예금 추천')


def test_negation_does_not_recommend_excluded_category():
    assert 'category_mismatch' in reasons(product(product_type='fund'), request='펀드 말고 예금 추천')
    assert 'category_mismatch' in reasons(product(), request='예금은 제외하고 적금 추천')


def test_unverified_expired_and_restricted_products_blocked():
    for change, expected in [({'evidence_source': ''}, 'metadata_unverified'),
                             ({'verified_on': '2020-01-01'}, 'metadata_stale'),
                             ({'valid_until': '2026-11-01'}, 'product_expired'),
                             ({'eligibility_unrestricted': False}, 'eligibility_unverified'),
                             ({'retail_available': False}, 'not_retail'),
                             ({'min_amount': None}, 'amount_unknown')]:
        assert expected in reasons(product(**change))


def test_principal_protection_and_venture_exclusion():
    assert 'principal_not_guaranteed' in reasons(product(principal_guaranteed=False), profile('원금보장형'))
    assert 'unsupported_product' in reasons(product(product_type='fund_kvic'), request='펀드 추천')


def test_llm_cannot_override_explicit_category_or_company():
    intent = resolve_intent('우리은행 예금 추천', {'categories': ['fund'], 'company': '신한은행'})
    assert intent['categories'] == ['deposit']
    assert intent['companies'] == ['우리은행']


def test_unsupported_request_does_not_fall_back_to_any_product():
    assert 'request_unsupported' in reasons(product(), request='비트코인 추천')


def test_nonfinancial_recommendation_does_not_return_deposits():
    for query in ('맛집 추천', '일자리 추천', '영화 추천'):
        assert 'request_unsupported' in reasons(product(), request=query)


def test_excluded_bank_is_never_recommended():
    assert 'company_excluded' in reasons(product(), request='우리은행 말고 예금 추천')


def test_requested_budget_and_term_are_hard_constraints():
    assert 'budget_exceeded' in reasons(product(min_amount=200000), request='10만원으로 예금 추천')
    assert 'term_unknown' in reasons(product(), request='3개월 예금 추천')
    assert 'term_exceeded' in reasons(product(term_months=12), request='3개월 예금 추천')


def test_generic_request_does_not_let_model_add_funds():
    assert resolve_intent('상품 추천', {'categories': ['fund']})['categories'] == ['deposit', 'saving']


def test_natural_language_exclusions_are_hard_constraints():
    for query in ('펀드는 원하지 않고 예금 추천', '펀드 안 할래', '펀드 빼줘'):
        assert 'fund' not in resolve_intent(query, {'categories': ['fund']})['categories']


def test_bank_alias_negation_is_applied_before_normalization():
    for query, bank in (('국민 말고 예금 추천', '국민은행'), ('농협은 빼고 적금 추천', '농협은행')):
        intent = resolve_intent(query, {})
        assert bank not in intent['companies']
        assert bank in intent['excluded_companies']
