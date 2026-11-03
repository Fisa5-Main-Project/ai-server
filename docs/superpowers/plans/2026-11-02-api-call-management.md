# API call management implementation plan

**Goal:** Implement the requested shared-key LLM admission, metering and bounded retry policy on the existing recommendation path.

**Architecture:** Verify the existing Spring HS512 access token; never trust body user IDs. A single async gateway owns each physical LLM HTTP attempt. Redis Lua atomically admits global/user sliding-window limits and model concurrency leases. MongoDB records attempts and actual provider usage separately from chat messages. No SDK hidden retries.

**Tech Stack:** FastAPI, httpx, redis asyncio/Lua, PyJWT, PyMongo, pytest/fakeredis Lua.

## Constraints and decisions
- Preserve previous suitability changes and uncommitted work.
- Default rolling 60s global 54/user 30, model concurrency 4. Configurable operational examples, not provider contract claims.
- Redis/server clock, common hash tag, key-group scoped limits, no personal data or API keys in Redis key names/logs.
- A request is charged per outbound attempt, including retry. Denied admission consumes neither global nor user slots.
- Max 2 attempts; retry only explicit provider 429, honor Retry-After and shared cooldown. No timeout/ambiguous error replay. HTTP transport retries disabled.
- Hard total deadline < concurrency lease lifetime. Cancellation releases local lease; process death expires lease. Remote work may outlive client cancellation.
- Persist a started event before sending; finalize tokens/status afterward. Unknown tokens remain unknown. No prompt/response bodies in usage records.
- No response cache for financial recommendations: stale profiles/feedback/evidence must not be reused.
- Scope: interactive LLM chat/recommendation. Existing embedding ETL/CDC are separate pipelines; document their independent quota requirement. Protect manual vectorization as admin-only.

## Tasks
- [x] Write admission, concurrent callers, retries, token metadata, auth ownership, error propagation tests and run red.
- [x] Implement isolated gateway modules (errors/context, limiter Lua, provider adapter, usage store/runtime).
- [x] Integrate auth + context into recommendation/chat; errors survive graph/service fallbacks and SSE preflights before headers with disconnect cancellation.
- [x] Add bounded admin usage aggregation API/UI, readiness/lifespan cleanup and deployment example.
- [x] Run focused tests, existing suitability regression, real Redis/Mongo integration; review diff and document limits.

## Verification outcome
- 2026-11-02: 89 tests passed (`tests/gateway tests/suitability`) with real isolated Redis and MongoDB enabled, including lifespan and revoked JWT checks.
- Five Redis connections, 500 competing requests: exactly 54 admissions for configured rolling-minute global limit.
- Real MongoDB: unique attempts, stale-start protection, token/cost aggregation, user filtering and TTL indexes verified.
- Frontend: Next type generation, TypeScript `--noEmit`, changed-file ESLint passed.
- Review fixes: SSE prefetch disconnect cancellation, work deadline across admission/metering, preserve usage in blocked provider responses, stop retry on 429 ledger finalization failure, bounded cancellation-safe cleanup.
- No actual paid provider calls, deployment, production secret changes or performance percentile claims.

## Validation
No paid provider calls. Use httpx mock transport to verify physical request count and captured provider usage. Execute real Lua in fakeredis and an isolated Redis container if available. Validate multiple gateway instances sharing Redis, denied user/global transactions, lease release/expiry, cooldown, Retry-After date/seconds, cancellation, fail-closed storage outages, and JWT/ownership/admin boundaries. Run existing suitability tests to prevent recommendation policy regression.
