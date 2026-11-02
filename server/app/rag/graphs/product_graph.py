"""Interpret -> retrieve -> validate -> respond. LLM has no suitability authority."""
import json
from collections import Counter
from datetime import date
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from app.rag.states import ProductAgentState
from app.rag.suitability import assess, resolve_intent, render_product


def build_product_graph(model=None, retrieve=None, today=date.today):
    async def interpret(state):
        from app.rag.prompts.product_recommendation import SYSTEM_PROMPT
        parsed = {}
        try:
            active_model = model
            if active_model is None:
                from app.core.llm_factory import get_llm
                active_model = get_llm(temperature=0)
            response = await active_model.ainvoke([
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': state.get('query', '')}])
            parsed = json.loads(response.content)
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception:
            pass  # Explicit parsing still applies; never guess customer risk.
        return {'intent': resolve_intent(state.get('query', ''), parsed)}

    async def search(state):
        if not state['intent']['supported']:
            return {'candidates': []}
        searcher = retrieve
        if searcher is None:
            from app.rag.retrievers.candidates import retrieve_candidates
            searcher = retrieve_candidates
        return {'candidates': await searcher(state['intent'], state.get('query', ''))}

    def validate(state):
        candidates = state.get('candidates', [])
        counts = Counter(p.get('product_id') for p in candidates)
        decisions, accepted = [], []
        for p in candidates:
            reasons = assess(p, state['profile'], state['intent'], set(state.get('disliked', [])), today())
            if counts[p.get('product_id')] > 1:
                reasons.append('duplicate_identity')
            decisions.append({'product_id': p.get('product_id'), 'risk_grade': p.get('risk_grade'),
                              'status': 'excluded' if reasons else 'eligible', 'reasons': reasons,
                              'evidence_source': p.get('evidence_source'), 'verified_on': p.get('verified_on'),
                              'validation_inputs': {key: p.get(key) for key in (
                                  'product_type', 'company_name', 'principal_guaranteed', 'min_amount',
                                  'term_months', 'retail_available', 'eligibility_unrestricted', 'valid_until',
                                  'risk_assessment', 'evidence_id', 'source_fingerprint', 'sales_status')}})
            if not reasons:
                accepted.append(p)
        liked = set(state.get('liked', []))
        accepted.sort(key=lambda p: (-p['risk_grade'], p['product_id'] not in liked, p['product_id']))
        accepted = accepted[:3]
        selected = {p['product_id'] for p in accepted}
        for d in decisions:
            if d['product_id'] in selected:
                d['status'] = 'selected'
            elif d['status'] == 'eligible':
                d['reasons'] = ['lower_priority']
        return {'accepted': accepted, 'decisions': decisions}

    def respond(state):
        products = [render_product(p) for p in state['accepted']]
        return {'products': products, 'messages': [AIMessage(content=json.dumps({'products': products}, ensure_ascii=False))]}

    workflow = StateGraph(ProductAgentState)
    for name, node in [('interpret', interpret), ('retrieve', search), ('validate', validate), ('respond', respond)]:
        workflow.add_node(name, node)
    workflow.set_entry_point('interpret')
    workflow.add_edge('interpret', 'retrieve')
    workflow.add_edge('retrieve', 'validate')
    workflow.add_edge('validate', 'respond')
    workflow.add_edge('respond', END)
    return workflow.compile()
