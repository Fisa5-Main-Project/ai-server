from types import SimpleNamespace
from test_policy import reasons, TODAY
from app.rag.retrievers.candidates import normalize_document
import asyncio
import sys
from types import ModuleType
import pytest


def test_user_vector_is_used_for_product_search_and_duplicate_candidates_merge(monkeypatch):
    from app.rag.retrievers.candidates import retrieve_candidates
    doc = lambda key: SimpleNamespace(metadata={'_id': key, 'product_type': 'deposit'})
    class Store:
        def similarity_search_by_vector(self, embedding, **kwargs):
            # This external boundary must receive the persisted vector, not embedded prose.
            assert embedding == [0.2, 0.8]
            assert kwargs['pre_filter'] == {'product_type': 'deposit'}
            return [doc('personal'), doc('shared'), doc('third'), doc('fourth')]
        def as_retriever(self, **kwargs):
            async def invoke(query):
                assert query == '예금 추천'
                return [doc('shared'), doc('query')]
            return SimpleNamespace(ainvoke=invoke)
    module = ModuleType('app.db.vector_store')
    for name in ['deposit_vector_store', 'saving_vector_store', 'annuity_vector_store', 'fund_vector_store']:
        setattr(module, name, Store())
    monkeypatch.setitem(sys.modules, 'app.db.vector_store', module)
    monkeypatch.setitem(sys.modules, 'app.core.config', SimpleNamespace(
        settings=SimpleNamespace(USER_EMBEDDING_MODEL='models/text-embedding-004')))
    result = asyncio.run(retrieve_candidates({'categories': ['deposit']}, '예금 추천',
                                             user_embedding=[0.2, 0.8]))
    assert [p['product_id'] for p in result] == ['shared', 'personal', 'query', 'third', 'fourth']


def test_user_embedding_model_must_match_product_embedding_model(monkeypatch):
    from app.rag.retrievers.candidates import retrieve_candidates
    monkeypatch.setitem(sys.modules, 'app.core.config', SimpleNamespace(
        settings=SimpleNamespace(USER_EMBEDDING_MODEL='different-model')))
    monkeypatch.setitem(sys.modules, 'app.db.vector_store', SimpleNamespace(
        deposit_vector_store=None, saving_vector_store=None,
        annuity_vector_store=None, fund_vector_store=None))
    with pytest.raises(ValueError, match='model'):
        asyncio.run(retrieve_candidates({'categories': ['deposit']}, '예금',
                                         user_embedding=[0.2, 0.8]))


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
