# Safe recommendations implementation plan

**Goal:** Block unsuitable and unrelated products before any recommendation reaches API or chat.
**Architecture:** Structured source profile → constrained LLM intent → metadata retrieval → deterministic suitability policy → canonical response. Log decisions before returning recommendations. Never invent risk data or performance results.
**Tech stack:** Python, LangGraph, MongoDB, existing FastAPI response contracts.
**Approved design:** Chat approval on 2026-11-02: prioritize reducing risky and unrelated products.

- [x] Write failing offline policy tests: risk boundaries, missing/stale metadata, assets, dislikes, category/company mismatch, malformed values, no results.
- [x] Implement pure policy and metadata normalization. Require verified, dated suitability metadata; exclude private/venture funds and high risk grades 1–3 under this conservative service policy.
- [x] Test and implement real LangGraph with injected model/retriever: interpretation cannot relax policy, no invented product identities, missing/error states produce no recommendations.
- [x] Integrate current structured MySQL profile, feedback and persistent decision audit in ProductsService. Preserve response schema and use deterministic recommendation chat responses.
- [x] Test service/chat paths with external dependencies replaced only at IO boundaries; update affected freshness tests.
- [x] Document product metadata provisioning and reproducible offline evaluation; run tests and inspect diff. Do not claim 18% → 2% without paired real measurements.

Verification: `.venv/Scripts/python -m pytest tests/suitability -q` from repository root; compile changed Python modules; run available existing tests with required dependencies.

Results: 39 focused/freshness checks passed. Final run excluding the known admin mismatch: 83 passed. Full-suite run before the final alias regression test: 82 passed, 15 existing admin tests fail because they call /api/admin while the unchanged router is /api/v1/admin. Python compile and git diff whitespace checks passed. No live LLM, catalogue or production DB evaluation was performed. Branch retained uncommitted for review.
