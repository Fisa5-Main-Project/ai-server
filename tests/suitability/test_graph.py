import asyncio
from test_policy import profile, product, TODAY
from app.rag.graphs.product_graph import build_product_graph


class Model:
    async def ainvoke(self, messages):
        return type('Reply', (), {'content': '{"categories":["fund"],"company":""}'})()


def run(candidates, query='예금 추천', model=None):
    async def retrieve(intent, search):
        assert intent['categories'] == ['deposit']
        return candidates
    graph = build_product_graph(model=model or Model(), retrieve=retrieve, today=lambda: TODAY)
    return asyncio.run(graph.ainvoke({'query': query, 'profile': profile(), 'disliked': ['bad']}))


def test_graph_filters_before_canonical_response_and_records_exclusions():
    result = run([product(), product(product_id='bad'), product(product_id='risky', risk_grade=1),
                  product(product_id='other', product_type='fund')])
    assert [p['product_id'] for p in result['products']] == ['d1']
    assert len(result['decisions']) == 4
    assert result['decisions'][1]['reasons'] == ['disliked']
    assert result['decisions'][0]['status'] == 'selected'
    assert '정기예금' in result['messages'][-1].content


def test_empty_candidates_produce_empty_response():
    assert run([])['products'] == []


def test_model_failure_never_relaxes_explicit_constraints():
    class Broken:
        async def ainvoke(self, messages):
            raise RuntimeError('offline')
    assert len(run([product()], model=Broken())['products']) == 1


def test_duplicate_ids_with_conflicting_risk_are_blocked():
    result = run([product(), product(risk_grade=1)])
    assert result['products'] == []
    assert all('duplicate_identity' in d['reasons'] for d in result['decisions'])


def test_ranking_prefers_lower_risk_not_yield_and_limits_to_three():
    result = run([product(product_id=str(i), risk_grade=5 if i < 3 else 6) for i in range(6)])
    assert [p['product_id'] for p in result['products']] == ['3', '4', '5']
