"""Field-level source evidence and conservative internal risk classification.

Internal levels are service policy, not issuer investment-risk grades.
The registry is a reviewed snapshot; reading it never refreshes its check date.
"""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlparse

REGISTRY = Path(__file__).with_name('data') / 'product_evidence.json'
RISK_POLICY = 'evidence-risk-v1'
BOOLEAN_FACTS = {'deposit_protected', 'retail_available', 'eligibility_unrestricted'}
INTEGER_FACTS = {'min_amount', 'min_term_months', 'max_term_months', 'min_age'}
ALLOWED_FACTS = BOOLEAN_FACTS | INTEGER_FACTS | {'instrument', 'sales_status'}


def load_registry(path=None):
    return json.loads(Path(path or REGISTRY).read_text(encoding='utf-8'))['products']


def classify_risk(facts):
    instrument = facts.get('instrument')
    level, grade, reasons = 'unknown', None, ['상품 구조의 확인 근거 부족']
    if instrument == 'ordinary_krw_deposit' and facts.get('deposit_protected') is True:
        level, grade = 'low', 6
        reasons = ['일반 원화 예금 구조 확인', '해당 상품의 예금자보호 대상 여부 확인']
    elif instrument in ('leveraged_fund', 'derivative', 'structured_note', 'equity_fund', 'venture_fund'):
        level, grade, reasons = 'high', 2, ['레버리지·주가·파생·벤처 관련 손실 노출 구조']
    # A fund being called MMF/bond/etc. is insufficient to infer a low risk grade.
    return {'basis': 'internal_policy', 'policy_version': RISK_POLICY,
            'level': level, 'comparison_grade': grade, 'reasons': reasons}


def normalized(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def source_fingerprint(doc):
    raw = {k: v for k, v in doc.items() if k not in ('suitability', 'embedding', 'rag_text')}
    return sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def verified_facts(record):
    sources = {s['id']: s for s in record['sources']}
    if len(sources) != len(record['sources']):
        raise ValueError('Duplicate evidence source IDs')
    for source in sources.values():
        url = urlparse(source['url'])
        if url.scheme != 'https' or not url.hostname or not source.get('publisher'):
            raise ValueError('Evidence needs an HTTPS source and named publisher')
    facts = {}
    for key, entry in record['facts'].items():
        if key not in ALLOWED_FACTS:
            raise ValueError('Unsupported evidence field')
        if entry.get('source_id') not in sources or not entry.get('locator') or 'value' not in entry:
            raise ValueError('Each fact must reference a source and document section')
        if key in BOOLEAN_FACTS and type(entry['value']) is not bool:
            raise ValueError('Evidence booleans must be literal true/false')
        if key in INTEGER_FACTS and (type(entry['value']) is not int or entry['value'] < 0):
            raise ValueError('Evidence amounts and limits must be nonnegative integers')
        if key in ('instrument', 'sales_status') and not isinstance(entry['value'], str):
            raise ValueError('Evidence category must be a string')
        facts[key] = entry['value']
    return facts


def enrich_product(doc, records=None, today=None):
    today = today or date.today()
    records = load_registry() if records is None else records
    result = deepcopy(doc)
    company = doc.get('company_name') or doc.get('kor_co_nm') or ''
    name = doc.get('product_name') or doc.get('fin_prdt_nm') or doc.get('fndNm') or ''
    matches = [r for r in records if r['match']['product_type'] == doc.get('product_type')
               and normalized(company) in {normalized(v) for v in r['match']['company_names']}
               and normalized(name) in {normalized(v) for v in r['match']['product_names']}]
    policy = {'schema_version': 2, 'verification_status': 'unmatched',
              'official_risk_grade': None, 'risk_grade': None, 'principal_guaranteed': None,
              'risk_assessment': classify_risk({}), 'source_fingerprint': source_fingerprint(doc),
              'observed_conditions': {key: doc[key] for key in ('join_deny', 'join_member', 'join_way', 'etc_note', 'max_limit') if key in doc}}
    result['suitability'] = policy
    if len(matches) != 1:
        if len(matches) > 1:
            policy['verification_status'] = 'ambiguous'
        return result
    # Financial-product disclosure ending is not the deposit's maturity date.
    closing = doc.get('dcls_end_day')
    if closing:
        try:
            closing_text = str(closing)
            closing_date = (datetime.strptime(closing_text, '%Y%m%d').date()
                            if re.fullmatch(r'\d{8}', closing_text) else date.fromisoformat(closing_text))
        except ValueError:
            policy['verification_status'] = 'conflict'
            return result
        if closing_date <= today:
            policy['verification_status'] = 'closed'
            return result
    record = matches[0]
    facts = verified_facts(record)
    policy.update(evidence_id=record['evidence_id'], verified_on=record['checked_on'],
                  evidence_sources=deepcopy(record['sources']), evidence_facts=deepcopy(record['facts']),
                  evidence_source=record['sources'][0]['url'])
    age = (today - date.fromisoformat(record['checked_on'])).days
    if not 0 <= age <= 30:
        policy['verification_status'] = 'stale'
        return result
    # Raw-source restrictions win over any broad statement in the registry.
    if str(doc.get('join_deny', '1')) != '1' and facts.get('eligibility_unrestricted') is True:
        policy['verification_status'] = 'conflict'
        return result
    policy.update(facts)
    policy['verification_status'] = 'verified'
    policy['risk_assessment'] = classify_risk(facts)
    policy['risk_grade'] = policy['risk_assessment']['comparison_grade']
    # A range is preserved; it must not become an invented single maturity option.
    policy['term_months'] = facts.get('min_term_months')
    policy['review_due_on'] = date.fromordinal(date.fromisoformat(record['checked_on']).toordinal() + 30).isoformat()
    return result
