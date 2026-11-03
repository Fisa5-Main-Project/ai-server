"""Compare actual predictions against independent fixed labels, never fabricate a baseline."""
import argparse
import json
from pathlib import Path


def index(rows, field):
    result = {}
    for row in rows:
        key = row.get('case_id')
        values = row.get(field)
        if not isinstance(key, str) or not key or key in result:
            raise ValueError('Every case_id must be nonempty and unique')
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError(f'{field} must contain product ID strings')
        if len(values) != len(set(values)):
            raise ValueError('Duplicate product IDs would distort the denominator')
        result[key] = set(values)
    return result


def compare(labels, before, after):
    allowed = index(labels, 'allowed_product_ids')
    variants = {'before': index(before, 'product_ids'), 'after': index(after, 'product_ids')}
    if not allowed or any(set(v) != set(allowed) for v in variants.values()):
        raise ValueError('Labels and both prediction files must contain the same nonempty case set')
    report = {'case_count': len(allowed)}
    for name, predictions in variants.items():
        total = sum(len(ids) for ids in predictions.values())
        bad = sum(len(ids - allowed[key]) for key, ids in predictions.items())
        bad_cases = sum(bool(ids - allowed[key]) for key, ids in predictions.items())
        report[name] = {'recommended_products': total, 'unsuitable_products': bad,
                        'unsuitable_product_rate': bad / total if total else None,
                        'unsuitable_response_rate': bad_cases / len(allowed),
                        'recommendation_coverage': sum(bool(ids) for ids in predictions.values()) / len(allowed)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('labels', 'before', 'after'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    def read(path):
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    print(json.dumps(compare(read(args.labels), read(args.before), read(args.after)), indent=2))


if __name__ == '__main__':
    main()
