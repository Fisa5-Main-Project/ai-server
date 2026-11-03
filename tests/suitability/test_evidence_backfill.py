import importlib.util
from pathlib import Path
import mongomock
from test_product_evidence import doc, evidence

spec = importlib.util.spec_from_file_location('enrichment', Path(__file__).resolve().parents[2] / 'scripts/enrich_product_evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_dry_run_preserves_catalogue_and_apply_writes_only_evidence():
    collection = mongomock.MongoClient().db.products
    source = {**doc(), 'embedding': [0.1, 0.2], 'rag_text': 'unchanged'}
    collection.insert_one(source)
    counts = module.backfill(collection, [evidence()])
    assert counts == {'verified': 1}
    assert collection.find_one() == source
    counts = module.backfill(collection, [evidence()], apply=True)
    assert counts == {'verified': 1, 'written': 1}
    stored = collection.find_one()
    assert stored['embedding'] == [0.1, 0.2]
    assert stored['rag_text'] == 'unchanged'
    assert stored['suitability']['risk_assessment']['level'] == 'low'


def test_unmatched_export_keeps_unknown_fields_unknown():
    rows, counts = module.enrich_documents([{**doc(), 'fin_prdt_nm': 'unknown'}], [evidence()])
    assert counts == {'unmatched': 1}
    assert rows[0]['suitability']['risk_grade'] is None


def test_concurrent_restriction_update_is_not_overwritten():
    collection = mongomock.MongoClient().db.products
    collection.insert_one(doc())
    class RacingCollection:
        def find(self, *args):
            rows = list(collection.find(*args))
            collection.update_one({'_id': 'actual-id'}, {'$set': {'join_deny': '3'}})
            return rows
        def update_one(self, *args, **kwargs):
            return collection.update_one(*args, **kwargs)
    counts = module.backfill(RacingCollection(), [evidence()], apply=True)
    assert counts['concurrent_change'] == 1
    assert 'suitability' not in collection.find_one()
