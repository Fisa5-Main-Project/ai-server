"""Enrich an exported catalogue or backfill MongoDB. Mongo defaults to dry-run."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from app.rag.product_evidence import enrich_product, load_registry

COLLECTIONS = ('products_deposit_saving', 'products_annuity', 'products_funds')


def enrich_documents(documents, records):
    updated = [enrich_product(doc, records) for doc in documents]
    counts = Counter(doc['suitability']['verification_status'] for doc in updated)
    return updated, dict(counts)


def backfill(collection, records, apply=False):
    counts = Counter()
    for doc in collection.find({}, {'embedding': 0}):
        enriched = enrich_product(doc, records)
        policy = enriched['suitability']
        counts[policy['verification_status']] += 1
        if apply:
            # Optimistic concurrency for every read source field; never overwrite a changed catalogue row.
            query = {k: v for k, v in doc.items() if k not in ('suitability', 'rag_text')}
            for key in ('join_deny', 'dcls_end_day', 'options'):
                if key not in doc:
                    query[key] = {'$exists': False}
            result = collection.update_one(query, {'$set': {'suitability': policy}}, upsert=False)
            counts['written' if result.matched_count else 'concurrent_change'] += 1
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--input', type=Path, help='JSON array exported from catalogue')
    mode.add_argument('--mongo', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--apply', action='store_true', help='Persist MongoDB updates (default: dry-run)')
    args = parser.parse_args()
    records = load_registry(args.registry)
    if args.input:
        if not args.output or args.output.resolve() == args.input.resolve():
            parser.error('--output must be a different file, preserving the source export')
        updated, counts = enrich_documents(json.loads(args.input.read_text(encoding='utf-8')), records)
        args.output.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(counts))
        return
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    uri, database = os.getenv('MONGO_URI'), os.getenv('MONGO_DB_NAME')
    if not uri or not database:
        parser.error('Configure MONGO_URI and MONGO_DB_NAME; credentials are never accepted as command arguments')
    from pymongo import MongoClient
    with MongoClient(uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=10000) as client:
        print(json.dumps({name: backfill(client[database][name], records, args.apply) for name in COLLECTIONS}))


if __name__ == '__main__':
    main()
