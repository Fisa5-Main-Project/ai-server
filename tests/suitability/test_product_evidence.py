from datetime import date
from copy import deepcopy
from pathlib import Path
import json
import pytest
from test_policy import TODAY
from app.rag.product_evidence import enrich_product, classify_risk, load_registry
from app.rag.retrievers.candidates import normalize_document
from app.rag.suitability import assess, render_product
from test_policy import profile
from types import SimpleNamespace


def evidence():
    return {'evidence_id': 'bank-deposit', 'match': {'product_type': 'deposit',
            'company_names': ['우리은행'], 'product_names': ['WON플러스 예금']},
            'checked_on': '2026-11-02', 'sources': [{'id': 'bank', 'url': 'https://spot.wooribank.com/example',
                'publisher': '우리은행', 'document_date': None}],
            'facts': {key: {'value': value, 'source_id': 'bank', 'locator': '상품안내'} for key, value in {
                'instrument': 'ordinary_krw_deposit', 'deposit_protected': True, 'retail_available': True,
                'eligibility_unrestricted': True, 'min_amount': 10000, 'min_term_months': 1,
                'max_term_months': 36}.items()}}


def doc():
    return {'_id': 'actual-id', 'product_type': 'deposit', 'kor_co_nm': '우리은행', 'fin_prdt_nm': 'WON플러스 예금'}


def test_deposit_has_internal_classification_not_invented_official_grade():
    result = enrich_product(doc(), [evidence()], TODAY)
    s = result['suitability']
    assert s['official_risk_grade'] is None
    assert s['risk_assessment']['basis'] == 'internal_policy'
    assert s['risk_assessment']['level'] == 'low'
    assert s['min_amount'] == 10000
    assert s['principal_guaranteed'] is None
    assert 'valid_until' not in s  # A verification TTL must not invent a sales closing date.


def test_names_do_not_imply_risk_without_evidence():
    result = enrich_product(doc(), [], TODAY)
    assert result['suitability']['risk_assessment']['level'] == 'unknown'


def test_exact_company_and_product_required_no_class_or_bank_collision():
    for change in ({'kor_co_nm': '다른은행'}, {'fin_prdt_nm': 'WON플러스 예금 특판'}):
        assert enrich_product({**doc(), **change}, [evidence()], TODAY)['suitability']['verification_status'] == 'unmatched'


def test_expired_or_future_evidence_cannot_renew_itself():
    for checked in ('2026-01-01', '2027-01-01'):
        e = evidence()
        e['checked_on'] = checked
        assert enrich_product(doc(), [e], TODAY)['suitability']['verification_status'] == 'stale'


def test_ambiguous_registry_and_conflicting_source_are_blocked():
    assert enrich_product(doc(), [evidence(), evidence()], TODAY)['suitability']['verification_status'] == 'ambiguous'
    assert enrich_product({**doc(), 'join_deny': '3'}, [evidence()], TODAY)['suitability']['verification_status'] == 'conflict'


def test_facts_must_reference_real_sources_and_locations():
    e = evidence()
    e['facts']['deposit_protected']['source_id'] = 'invented'
    with pytest.raises(ValueError):
        enrich_product(doc(), [e], TODAY)


def test_structured_or_equity_fund_is_high_risk_and_unknown_fund_is_blocked():
    assert classify_risk({'instrument': 'leveraged_fund'})['level'] == 'high'
    assert classify_risk({'instrument': 'equity_fund'})['level'] == 'high'
    assert classify_risk({'instrument': 'fund'})['level'] == 'unknown'
    assert classify_risk({'instrument': 'ordinary_krw_deposit'})['level'] == 'unknown'


def test_normalization_does_not_lose_evidence_or_internal_classification():
    enriched = enrich_product(doc(), [evidence()], TODAY)
    p = normalize_document(SimpleNamespace(metadata=enriched))
    assert p['risk_assessment']['level'] == 'low'
    assert p['verification_status'] == 'verified'
    assert p['risk_grade'] == 6  # policy comparison only; UI must say internal classification


def test_registry_contains_real_sourced_products_not_synthetic_approvals():
    records = load_registry()
    assert len(records) >= 3
    assert all(r['sources'] and r['facts'] for r in records)


def test_sourced_deposit_passes_without_official_risk_or_fake_expiry():
    p = normalize_document(SimpleNamespace(metadata=doc()))
    assert assess(p, profile(), {'supported': True, 'categories': ['deposit']}, set(), TODAY) == []
    response = render_product(p)
    assert '내부 위험분류' in response['benefit']
    assert '6등급' not in response['benefit']
    assert response['risk_basis'] == 'internal_policy'


def test_closed_product_is_not_reopened_by_registry():
    p = enrich_product({**doc(), 'dcls_end_day': '20261031'}, [evidence()], TODAY)
    assert p['suitability']['verification_status'] == 'closed'


def test_name_only_backfill_does_not_preserve_previous_unsafe_approval():
    p = enrich_product({**doc(), 'fin_prdt_nm': '새상품', 'suitability': {'risk_grade': 6}}, [], TODAY)
    assert p['suitability']['risk_grade'] is None


def test_registry_cannot_override_policy_or_treat_text_as_verified_boolean():
    for key, value in (('schema_version', 1), ('deposit_protected', 'true'), ('min_amount', -1)):
        e = evidence()
        e['facts'][key] = {'value': value, 'source_id': 'bank', 'locator': 'section'}
        with pytest.raises(ValueError):
            enrich_product(doc(), [e], TODAY)
