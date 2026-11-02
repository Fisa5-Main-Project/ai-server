from types import SimpleNamespace
from test_policy import reasons, TODAY
from app.rag.retrievers.candidates import normalize_document


def test_raw_rag_claims_never_supply_missing_suitability_metadata():
    doc = SimpleNamespace(page_content='안전한 원금보장 위험 6등급', metadata={
        '_id': 'x', 'product_type': 'deposit', 'fin_prdt_nm': '예금', 'kor_co_nm': '우리은행',
        'risk_grade': 6})
    normalized = normalize_document(doc)
    assert normalized['product_name'] == '예금'
    assert 'risk_unknown' in reasons(normalized)


def test_verified_metadata_is_preserved_but_cannot_override_product_id():
    doc = SimpleNamespace(metadata={'_id': 'real', 'product_type': 'fund_fsc', 'fndNm': '펀드',
        'suitability': {'product_id': 'invented', 'risk_grade': 4, 'company_name': '운용사', 'term_months': 3}})
    p = normalize_document(doc)
    assert p['product_id'] == 'real'
    assert p['product_type'] == 'fund'
    assert p['risk_grade'] == 4
    assert p['term_months'] == 3
