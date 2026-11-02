import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('evaluation', Path(__file__).resolve().parents[2] / 'scripts/evaluate_suitability.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_paired_evaluation_counts_unsafe_and_abstention_separately():
    labels = [{'case_id': 'a', 'allowed_product_ids': ['safe']}, {'case_id': 'b', 'allowed_product_ids': []}]
    before = [{'case_id': 'a', 'product_ids': ['safe', 'bad']}, {'case_id': 'b', 'product_ids': ['bad']}]
    after = [{'case_id': 'a', 'product_ids': ['safe']}, {'case_id': 'b', 'product_ids': []}]
    report = module.compare(labels, before, after)
    assert report['before']['unsuitable_products'] == 2
    assert report['before']['recommended_products'] == 3
    assert report['after']['unsuitable_product_rate'] == 0
    assert report['after']['recommendation_coverage'] == 0.5


def test_empty_output_has_no_misleading_zero_product_rate():
    rows = [{'case_id': 'a', 'product_ids': []}]
    report = module.compare([{'case_id': 'a', 'allowed_product_ids': ['safe']}], rows, rows)
    assert report['after']['unsuitable_product_rate'] is None


def test_different_or_duplicate_cases_cannot_be_compared():
    labels = [{'case_id': 'a', 'allowed_product_ids': []}]
    with pytest.raises(ValueError):
        module.compare(labels, [{'case_id': 'b', 'product_ids': []}], [])
    with pytest.raises(ValueError):
        module.compare(labels, [{'case_id': 'a', 'product_ids': []}] * 2, [])
