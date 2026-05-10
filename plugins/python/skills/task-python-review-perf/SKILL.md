---
name: task-python-review-perf
description: "Python performance review: SQLAlchemy/Django ORM N+1, async event-loop blocking, connection pools, Celery throughput, Pydantic serialization."
agent: python-performance-engineer
metadata:
  category: backend
  tags: [python, fastapi, django, performance, sqlalchemy, async, celery, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Python Performance Review

## Purpose

Python-aware performance review that names SQLAlchemy 2.0+ async session, Django ORM `select_related` / `prefetch_related`, asyncio event-loop discipline, FastAPI dependency / Pydantic v2 serialization, Celery task design, and Alembic / Django migration safety idioms directly instead of routing through the generic backend adapter. Produces findings with measured or estimated impact (latency, throughput, query count, GIL contention) and concrete fixes using Python 3.11+ patterns.

This workflow is the stack-specific delegate of `task-code-review-perf` for Python. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a FastAPI or Django PR or branch for performance regressions
- Investigating a slow endpoint, Celery task, or scheduled job
- Pre-merge perf pass on changes touching ORM queries, async boundaries, Celery dispatch, or event-loop-blocking calls
- Quarterly N+1 / pool-sizing / async-correctness sweep against APM-flagged endpoints

**Not for:**

- General Python code review (use `task-code-review` or `task-python-review`)
- Security review (use `task-code-review-security` or `task-python-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-python-implement`)

## Depth Levels

| Depth      | When to Use                                               | What Runs                                   |
| ---------- | --------------------------------------------------------- | ------------------------------------------- |
| `quick`    | Single endpoint or repository ("is this query ok?")       | Steps 4 + 5 only; ORM hotspots + migrations |
| `standard` | Default - full Python perf review                         | All steps                                   |
| `deep`     | Profiling-driven review with py-spy / Scalene / OTel data | All steps + capacity guidance and load plan |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                          | Meaning                                                                                               |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-python-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-python-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-python-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-python-review` (parent already detected Python), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Python, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Python 3.11+.

Then detect the web framework:

- `main.py` + `fastapi` import / `pyproject.toml` `fastapi` dep → **FastAPI**
- `manage.py` + `settings.py` / `pyproject.toml` `django` dep → **Django**
- Both present → ask the user which surface this PR targets; do not guess

The framework decision drives which checklists in Step 4 apply. Record `Framework: FastAPI | Django | mixed` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern query and concurrency behavior so impact estimates ground in real code:

**FastAPI surface:**

- Every changed SQLAlchemy `Mapped[...]` model (associations, `relationship()` `lazy=` strategy, `cascade=`)
- Every changed repository / data-access module (`select(...)` calls, `.options(selectinload/joinedload)`, `session.execute` patterns)
- Every changed router / endpoint (`async def`, `Depends(get_db)`, response_model usage)
- Every changed Pydantic v2 schema with non-trivial validators or large `model_validator` logic
- `app/core/config.py` / `settings.py` / `.env` for `pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle`
- Alembic migrations under `migrations/versions/`
- Celery task modules; `celery.py` for broker / backend / `task_routes` config

**Django surface:**

- Every changed Django model (`Meta.indexes`, `db_index=True`, `related_name`, `on_delete`)
- Every changed `QuerySet` / manager method - `select_related`, `prefetch_related`, `only`, `defer`, `annotate`
- Every changed ViewSet / view - `get_queryset` overrides, pagination, filter backends
- Every changed serializer - `SerializerMethodField`, nested serializers (N+1 risk via Django ORM)
- `settings.py` / `settings/base.py` for `DATABASES['default']['CONN_MAX_AGE']`, `CONN_HEALTH_CHECKS`, cache, Celery
- Migrations under `<app>/migrations/`
- Celery task modules

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new endpoint calling an existing repository whose query does an N+1), read the unchanged file too - the regression lives there even though the line count attributes it to the new caller.

### Step 4 - ORM Hotspots (FastAPI / SQLAlchemy or Django ORM)

> If `Framework: FastAPI` was recorded in Step 1, **skip the Django subsection entirely** below. Likewise skip the FastAPI subsection on Django-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

Canonical ORM patterns live in the atomic skills - load `python-sqlalchemy-patterns` (FastAPI) or `python-django-patterns` (Django) for the full pattern set (N+1 prevention, eager-loading strategy, `MissingGreenlet`, bulk operations, pool sizing, `select_related`/`prefetch_related`, `iterator()`, `select_for_update`). This step is the **review-scoped scan**: what the reviewer must verify is *present* in the diff, not a re-statement of what the patterns *are*.

**If FastAPI / SQLAlchemy:**

- [ ] Every traversed `relationship()` is eager-loaded via `selectinload` (collections) or `joinedload` (single-valued FK); `joinedload` on a collection chains `.unique()`
- [ ] Pydantic response models with `from_attributes=True` only touch preloaded relationships - fix on repository/service, not schema
- [ ] No `MissingGreenlet` risk: relationship access stays inside `async with session.begin()` / `Depends(get_db)` lifespan
- [ ] Existence checks use `await session.scalar(select(exists().where(...)))` not a discarded object load
- [ ] Unbounded reads use `stream_scalars` / `yield_per` + `StreamingResponse`; list endpoints paginated (keyset preferred over `COUNT(*)` per page on large tables)
- [ ] Bulk ops batch via `session.execute(insert/update, [...])` not per-row loops
- [ ] Filter/sort/group columns referenced in the diff have a backing index migration in the same PR
- [ ] `expire_on_commit=False` on `async_sessionmaker`; pool sizing (`pool_size`, `max_overflow`, `pool_pre_ping`, `pool_recycle`) documented if pool config is in the diff

**If Django / Django ORM:**

- [ ] FK / M2M / reverse-relation traversals preloaded via `select_related` / `prefetch_related`; nested via `prefetch_related("items__product")` or `Prefetch(...)`
- [ ] `SerializerMethodField` / nested serializers backed by `prefetch_related` in `get_queryset()`
- [ ] Large-row columns excluded via `only()` / `defer()`; `values()` / `values_list()` when model instantiation isn't needed
- [ ] `exists()` over `count() > 0`; `iterator(chunk_size=...)` for large result sets
- [ ] `bulk_create` / `bulk_update` with explicit `batch_size`; reviewer aware these skip `save()` signals
- [ ] `select_for_update(nowait=... | skip_locked=...)` scoped inside a transaction for concurrent-update safety
- [ ] Filter/sort columns referenced in the diff have `Meta.indexes` / `db_index=True` / migration index
- [ ] `CONN_MAX_AGE` and `CONN_HEALTH_CHECKS` configured if connection settings are in the diff

### Step 5 - Indexes and Migrations

Use skill: `python-migration-safety` for safe-migration checks on any change in `migrations/versions/` (Alembic) or `<app>/migrations/` (Django).

- [ ] Every column referenced in `where` / `order_by` / `group_by` is backed by an index
- [ ] Composite indexes match the leftmost-prefix pattern of the queries
- [ ] Foreign keys have indexes (PostgreSQL does not auto-index FKs)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL) - Alembic via `op.execute(...)` with `transaction_per_migration=True`; Django via `RunSQL` with `atomic = False`
- [ ] **`SET lock_timeout = '2s'`** before DDL on large tables to fail fast instead of blocking
- [ ] Unique constraints enforced at the database level, not just `unique=True` on a non-managed column
- [ ] Partial indexes used for boolean/enum filters that select a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add column nullable, backfill, switch reads, drop old column in a later release)
- [ ] **Backfill via keyset pagination** (`WHERE id > :last_id ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans the same rows on every iteration)
- [ ] Data migrations isolated from DDL migrations - separate Alembic revision or Django `RunPython` migration

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot in `WHERE` / `ORDER BY` / `GROUP BY` even if no query in the diff currently references it - someone is adding the index for a reason, and the migration is the load-bearing artifact. Validate the index is actually needed (column shape, expected selectivity), then assess migration safety. Conversely, when the diff _adds a column_ the application also queries on, flag the missing index proactively rather than waiting for a separate migration PR.

**Migration impact template.** Before approving any migration step on a hot table, state the impact: _"DDL on a 50M-row table without `CONCURRENTLY` blocks all writes for the duration of the index build (typically 5-30 min on Postgres at this scale). Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If the row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Async Correctness and Event Loop (FastAPI)

_Skip if Django sync app. Skipped at `quick` depth otherwise - see Depth Levels above._

Canonical asyncio patterns live in `python-async-patterns` (blocking-I/O catalog, `gather`/`TaskGroup`, `Semaphore`, `asyncio.timeout`, `run_in_executor` escape hatch). This step is the **review-scoped scan** for changes touching `async def`, `await`, `asyncio.gather`, `TaskGroup`:

- [ ] No blocking I/O in `async def`: `time.sleep`, `requests.get`, sync DB drivers, sync file I/O on large files - all flagged
- [ ] No CPU-heavy work on the event loop (hashing, image processing, large parsing) - move to `run_in_executor` or Celery
- [ ] Fan-out uses `asyncio.gather` / `TaskGroup` (3.11+); never sequential awaits in a loop for independent calls
- [ ] Every external call wrapped in `asyncio.timeout(...)` with an explicit budget
- [ ] Fan-out over collections bounded by `asyncio.Semaphore(N)` - unbounded `gather` over a large list exhausts connections
- [ ] No sync ORM (`Session`, `session.query`) inside `async def` - use `AsyncSession`
- [ ] `Depends(get_db)` yield-dependency commits/rolls back; no orphan transactions
- [ ] `httpx.AsyncClient` reused as a module-level / app-state singleton with explicit `Timeout` and connection limits - never per-request
- [ ] SQLAlchemy `pool_size + max_overflow` ≤ DB `max_connections / N_workers` if pool config is in the diff

> **Impact heuristic - blast radius of an event-loop block.** A blocking call inside `async def` does not just slow the calling request - it stalls _every other request currently in flight on this uvicorn worker_. Phrase the impact as "tail-latency contagion across all endpoints on this worker," not "this request is slow."

> **Synchronous external dependency on the request path.** Even when the call uses `httpx.AsyncClient` correctly, your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker, fire-and-forget) when the call is non-blocking-business; recommend strict timeouts plus fallback values when blocking-business.

### Step 7 - Pydantic / Serialization (FastAPI)

_Skipped at `quick` depth unless the diff touches schemas with non-trivial validators._

- [ ] **`response_model`** declared on every endpoint that returns structured data - FastAPI uses it to filter fields and generate the OpenAPI schema; absent, it falls back to `dict` and skips validation
- [ ] **Pydantic v2 (`pydantic>=2`)** - v1 patterns (`class Config:` with snake_case keys, `parse_obj`, `dict()`) flagged for migration to `model_config = ConfigDict(...)`, `model_validate`, `model_dump`
- [ ] **`from_attributes=True`** in `model_config` for response models built from ORM rows
- [ ] **Heavy `@field_validator` / `@model_validator` not on every request**: validation cost compounds at high QPS - move expensive checks to service layer
- [ ] **`response_model_exclude_unset=True`** when partial responses are expected - reduces payload size
- [ ] **Reuse Pydantic models across endpoints** rather than redefining identical shapes per route - first construction is the slow path
- [ ] **`orjson` / `ujson`** as the response renderer (`default_response_class=ORJSONResponse`) for endpoints with large JSON payloads

### Step 8 - Caching and Response Performance

_Skipped at `quick` depth unless the diff touches caching primitives._

- [ ] **Per-request memoization**: `functools.lru_cache` on pure functions; `request.state` cache for values used by multiple dependencies
- [ ] **Process-level cache**: `cachetools.TTLCache` or `aiocache` for in-process; Redis (`redis-py` async or `aioredis`) for shared / multi-instance
- [ ] **Cache stampede protection**: hot keys with expensive regeneration use single-flight (`asyncio.Lock` per key) or a Redis `SET NX EX` lock
- [ ] **Cache invalidation explicit** - no caches that never expire and never invalidate; document staleness budget
- [ ] **Django view cache / template fragment cache** scoped to keys that include the user / tenant when content varies
- [ ] **HTTP caching** (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GET endpoints
- [ ] **Response compression** middleware (`GZipMiddleware` for FastAPI; `GZipMiddleware` for Django) for JSON responses > 2KB

### Step 9 - Celery / Background Work

_Skipped at `quick` depth unless the diff touches Celery._

Canonical task patterns live in `python-celery-patterns` (idempotency, `acks_late` semantics, retry/backoff/jitter, queue routing, canvas, time limits). This step is the **review-scoped scan**:

- [ ] Tasks idempotent; pass IDs not ORM objects
- [ ] Critical tasks set `acks_late=True` + `task_reject_on_worker_lost=True`; non-critical may default
- [ ] Retry config declared (`autoretry_for`, `max_retries`, `retry_backoff`, `retry_jitter`); DLQ path for poison messages
- [ ] Queue routing isolates time-sensitive work; workers started with `-Q`
- [ ] `.delay()` dispatched AFTER commit (FastAPI: after `session.commit()`; Django: `transaction.on_commit(...)`)
- [ ] Long tasks split (target sub-30s median); chord/chain for longer workflows
- [ ] `soft_time_limit` / `time_limit` set on tasks that can hang on external I/O
- [ ] Result backend used only when result is consumed

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-python-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (OTel span or `prometheus_client` histogram); if not, raise as a Low/Recommendation finding and delegate to `task-python-review-observability` for a proper instrumentation pass rather than dictating the design here.
- [ ] SQLAlchemy `echo=False` in prod and `django-debug-toolbar` disabled in prod - if visible in the diff. If neither is in the diff, skip.

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process Prometheus) → `task-python-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Python; framework (FastAPI / Django / mixed) recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface read directly (models, repositories / managers, routers / views, schemas / serializers, settings, migrations, Celery tasks)
- [ ] `python-sqlalchemy-patterns` consulted for FastAPI / SQLAlchemy projects; N+1, multi-level N+1, `MissingGreenlet` risk, `joinedload` `.unique()`, projection use checked
- [ ] `python-django-patterns` consulted for Django projects; `select_related` / `prefetch_related`, `only` / `defer`, `exists`, `bulk_*`, `iterator` checked
- [ ] `python-migration-safety` consulted for any migration change; `lock_timeout`, concurrent index, keyset-pagination backfill, expand-contract verified
- [ ] `python-async-patterns` consulted for any `async def` / event-loop change; blocking-call audit, `gather` / `TaskGroup` / `Semaphore` use, `asyncio.timeout` wrapping
- [ ] `python-celery-patterns` consulted for any Celery change; idempotency, `acks_late`, retry policy, post-commit dispatch verified
- [ ] Connection pool sizing validated against worker / framework concurrency model **if pool config is in the diff**; otherwise note as Low / Recommendation and skip rather than fail the check
- [ ] Caching strategy assessed (in-process vs Redis, single-flight, invalidation explicit)
- [ ] Pydantic v2 / DRF serializer cost assessed when applicable
- [ ] Every finding states impact - measured (`p95: 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and load-test plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Python Performance Review Summary

**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Scope:** Backend (Python)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Python idiom: N+1 via lazy `relationship()` access, missing index, sync `requests.get` in async endpoint, Celery `.delay()` inside transaction, `joinedload` on collection without `.unique()`, etc.]
- **Impact:** [estimated effect - e.g., "N+1 in OrderRouter.list adds ~200 queries per request at 100 orders" or measured "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Python change with code example - `selectinload`, `prefetch_related`, `httpx.AsyncClient`, `transaction.on_commit`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Move PDF generation to Celery"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, schema migration, or load-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `.options(selectinload(Order.items).selectinload(OrderItem.product))` to OrderRepository.list"]
2. **[Delegate]** [High] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenant_id, created_at) - spawn DB migration subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Python idiom ("this is slow" vs "N+1 from lazy `relationship()`; add `selectinload` on the repository call")
- Recommending generic backend advice when a Python pattern applies (say "use `selectinload`", not "use eager loading")
- Suggesting `lazy="joined"` on collections to fix N+1 - it causes row duplication; use `selectinload` for collections, `joinedload` only for single-valued FK / OneToOne
- Suggesting caching without an invalidation strategy
- Conflating performance review with general code review or security review - delegate those to their workflows
- Treating Celery retries as a substitute for idempotency - retries with non-idempotent tasks cause double-charging / double-emailing
- Recommending `requests` / `urllib3` synchronous calls in `async def` paths - they block the event loop and stall every other in-flight request
- Recommending `time.sleep` in `async def` - same blocking problem
- Reporting "missing index" without confirming the column actually appears in a `where` / `order_by` / `group_by` in the diff
