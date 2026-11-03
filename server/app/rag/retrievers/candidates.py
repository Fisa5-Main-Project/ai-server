"""Keep source metadata intact; never extract safety claims from free text."""
import asyncio


def normalize_document(doc):
    meta = doc.metadata
    from app.rag.product_evidence import enrich_product
    existing = meta.get('suitability')
    if not isinstance(existing, dict) or existing.get('schema_version') == 2:
        meta = enrich_product(meta)
    kind = meta.get('product_type')
    if kind == 'fund_fsc':
        kind = 'fund'
    policy = meta.get('suitability')
    policy = policy if isinstance(policy, dict) else {}
    return {
        **{key: policy.get(key) for key in (
            'risk_grade', 'principal_guaranteed', 'min_amount', 'eligibility_unrestricted',
            'retail_available', 'verified_on', 'evidence_source', 'valid_until', 'term_months',
            'schema_version', 'verification_status', 'risk_assessment', 'official_risk_grade',
            'sales_status', 'min_term_months', 'max_term_months', 'evidence_id', 'source_fingerprint')},
        'product_id': str(meta['_id']) if meta.get('_id') is not None else '',
        'product_type': kind,
        'product_name': meta.get('product_name') or meta.get('fin_prdt_nm') or meta.get('fndNm') or '',
        'company_name': meta.get('company_name') or meta.get('kor_co_nm') or policy.get('company_name') or '',
    }


async def retrieve_candidates(intent, query, user_embedding=None):
    if user_embedding is not None:
        from app.core.config import settings
        # The product ETL currently embeds with this fixed model (etl_utils.py).
        # Equal dimensions alone do not imply compatible embedding spaces.
        if settings.USER_EMBEDDING_MODEL != 'models/text-embedding-004':
            raise ValueError('User embedding model does not match product embedding model')
    from app.db.vector_store import deposit_vector_store, saving_vector_store, annuity_vector_store, fund_vector_store
    stores = {'deposit': deposit_vector_store, 'saving': saving_vector_store,
              'annuity': annuity_vector_store, 'fund': fund_vector_store}

    async def search(kind):
        store = stores[kind]
        if store is None:
            raise RuntimeError('Product catalogue unavailable')
        kwargs = {'k': 20}
        if kind in ('deposit', 'saving'):
            kwargs['pre_filter'] = {'product_type': kind}
        if user_embedding is None:
            documents = await store.as_retriever(search_kwargs=kwargs).ainvoke(query or '노후 자산 관리')
        else:
            personal, requested = await asyncio.gather(
                asyncio.to_thread(store.similarity_search_by_vector, user_embedding, **kwargs),
                store.as_retriever(search_kwargs=kwargs).ainvoke(query or '노후 자산 관리'))
            # Reciprocal rank fusion gives both searches equal weight. Merge only
            # identical documents across searches; retain conflicting identities
            # and within-search duplicates for the downstream safety check.
            ranked = [[doc, 1 / (60 + rank), False]
                      for rank, doc in enumerate(personal, 1)]
            for rank, doc in enumerate(requested, 1):
                match = next((entry for entry in ranked[:len(personal)]
                              if not entry[2] and doc.metadata.get('_id') is not None
                              and entry[0].metadata == doc.metadata), None)
                if match is None:
                    ranked.append([doc, 1 / (60 + rank), True])
                else:
                    match[1] += 1 / (60 + rank)
                    match[2] = True
            ranked.sort(key=lambda entry: -entry[1])
            documents = [entry[0] for entry in ranked]
        return [normalize_document(doc) for doc in documents]

    batches = await asyncio.gather(*(search(kind) for kind in intent['categories']))
    return [p for batch in batches for p in batch]
