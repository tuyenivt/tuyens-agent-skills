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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Python Performance Review

Python-aware performance review naming SQLAlchemy 2.0+ async session, Django ORM `select_related` / `prefetch_related`, asyncio event-loop discipline, FastAPI / Pydantic v2 serialization, Celery task design, and Alembic / Django migration safety. Findings have measured or estimated impact (latency, throughput, query count, event-loop contention) and concrete Python 3.11+ fixes.

## When to Use

- FastAPI or Django PR / branch perf regression review
- Slow endpoint / Celery task / scheduled job investigation
- Pre-merge perf pass on ORM queries, async boundaries, Celery dispatch, event-loop-blocking calls
- Quarterly N+1 / pool-sizing / async-correctness sweep against APM data

**Not for:**
- General Python review (`task-python-review`)
- Security review (`task-python-review-security`)
- Production incident (`/task-oncall-start`)
- Pre-implementation design (`task-python-implement`)

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Profiling-driven with py-spy / Scalene / OTel | All + capacity guidance + load plan |

## Invocation

| Form | Meaning |
|------|---------|
| `/task-python-review-perf` | Current branch vs base; fails fast on trunk |
| `/task-python-review-perf <branch>` | `<branch>` vs base (3-dot) |
| `/task-python-review-perf pr-<N>` | PR head fetched into local branch `pr-<N>` |

When invoked as subagent of `task-code-review-perf` / `task-python-review`, Step 2 is skipped and pre-read diff is reused.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. Then:

- `main.py` + `fastapi` import / `pyproject.toml` `fastapi` dep -> **FastAPI**
- `manage.py` + `settings.py` / `pyproject.toml` `django` dep -> **Django**
- Both -> ask which surface this PR targets; do not guess

If detected stack is not Python, stop and route to `/task-code-review-perf`. Record `Framework: FastAPI | Django | mixed` for the Summary.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. Read diff and log once via `git diff <base>...<head>` and `git log <base>..<head>`; reuse. Skip entirely as subagent with handle + pre-read.

If `review-precondition-check` fails fast (dirty tree, trunk branch, missing PR ref, denied head-vs-current confirmation), surface verbatim and stop. Never run state-changing git.

### Step 3 - Read the Performance Surface

Cite real `file:line` per finding. Open:

**FastAPI:** every changed SQLAlchemy `Mapped[...]` model (`relationship()` `lazy=`, `cascade=`), repository / data-access modules (`select(...)`, `.options(selectinload/joinedload)`, `session.execute`), routers (`async def`, `Depends(get_db)`, `response_model`), Pydantic v2 schemas with non-trivial validators, `core/config.py` / `.env` for `pool_size` / `max_overflow` / `pool_pre_ping` / `pool_recycle`, Alembic migrations under `migrations/versions/`, Celery modules + `celery.py`.

**Django:** every changed model (`Meta.indexes`, `db_index`, `related_name`, `on_delete`), QuerySet / manager methods (`select_related`, `prefetch_related`, `only`, `defer`, `annotate`), ViewSets / views (`get_queryset`, pagination, filter backends), serializers (`SerializerMethodField`, nested), `settings.py` for `CONN_MAX_AGE` / `CONN_HEALTH_CHECKS` / cache / Celery, migrations under `<app>/migrations/`, Celery modules.

If the diff is small but ripples into unchanged code (new endpoint calling an existing N+1 repository), read the unchanged file - the regression lives there.

### Step 4 - ORM Hotspots (SQLAlchemy or Django ORM)

Canonical patterns: Use skill: `python-sqlalchemy-patterns` (FastAPI) or `python-django-patterns` (Django). This step flags deviations - skip the irrelevant subsection on monoglot projects.

**FastAPI / SQLAlchemy:**

- [ ] Traversed `relationship()` eager-loaded via `selectinload` (collections) or `joinedload` (single-valued FK); `joinedload` on collection chains `.unique()`
- [ ] Pydantic `from_attributes=True` response models touch only preloaded relationships - fix on repository, not schema
- [ ] No `MissingGreenlet` risk: relationship access stays inside `async with session.begin()` / `Depends(get_db)` lifespan
- [ ] Existence checks use `await session.scalar(select(exists().where(...)))` not a discarded object load
- [ ] Unbounded reads use `stream_scalars` / `yield_per` + `StreamingResponse`; lists paginated (keyset over `COUNT(*)`-per-page on large tables)
- [ ] Bulk ops via `session.execute(insert/update, [...])`, not per-row loops
- [ ] `expire_on_commit=False` on `async_sessionmaker`; pool sizing documented if config in diff

**Django ORM:**

- [ ] FK / M2M / reverse traversals preloaded via `select_related` / `prefetch_related`; nested via `prefetch_related("items__product")` or `Prefetch(...)`
- [ ] `SerializerMethodField` / nested serializers backed by `prefetch_related` in `get_queryset()`
- [ ] Large-row columns excluded via `only()` / `defer()`; `values()` / `values_list()` when model instantiation unneeded
- [ ] `exists()` over `count() > 0`; `iterator(chunk_size=...)` for large result sets
- [ ] `bulk_create` / `bulk_update` with explicit `batch_size`; reviewer aware these skip `save()` signals
- [ ] `select_for_update(nowait=... | skip_locked=...)` scoped inside a transaction for concurrent-update safety
- [ ] `CONN_MAX_AGE` and `CONN_HEALTH_CHECKS` set if connection config in diff

### Step 5 - Indexes and Migrations

Use skill: `python-migration-safety` for changes in `migrations/versions/` (Alembic) or `<app>/migrations/` (Django).

- [ ] Every column in `where` / `order_by` / `group_by` backed by an index
- [ ] Composite indexes match leftmost-prefix
- [ ] FK columns indexed (PostgreSQL does not auto-index FKs)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` (Alembic: `op.execute(...)` + `transaction_per_migration=True`; Django: `RunSQL` with `atomic = False`)
- [ ] `SET lock_timeout = '2s'` before DDL on large tables - fail fast vs block
- [ ] Unique constraints enforced at the DB level, not just `unique=True` on a non-managed column
- [ ] Partial indexes for boolean/enum filters selecting a small subset
- [ ] No DDL on hot tables in a single migration (expand-then-contract: add nullable, backfill, switch reads, drop in later release)
- [ ] Backfill via keyset pagination (`WHERE id > :last_id ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N` (re-scans same rows)
- [ ] Data migrations isolated from DDL (separate Alembic revision or Django `RunPython`)

**Reasoning rule.** When the diff _adds_ an index, treat that as evidence the column is hot - validate the index is needed (selectivity, shape), then assess safety. When the diff _adds a column_ also queried on, flag the missing index proactively.

**Migration impact template.** State the impact before approving DDL on a hot table: _"DDL on a 50M-row table without `CONCURRENTLY` blocks writes for 5-30 min on Postgres at this scale. Acquires `ACCESS EXCLUSIVE`; every other transaction queues."_ If row count is unknown, ask, or note "row count not in diff - confirm before deploy."

### Step 6 - Async Correctness and Event Loop (FastAPI)

_Skip on Django sync app._

Canonical patterns: Use skill: `python-async-patterns`. Apply the review-scoped scan:

**Impact heuristic.** A blocking call inside `async def` stalls _every request in flight on this uvicorn worker_. Phrase impact as "tail-latency contagion across all endpoints on this worker," not "this request is slow." A synchronous external dependency (even via `httpx.AsyncClient`) inherits its tail: your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker, fire-and-forget) for non-blocking-business; strict timeouts plus fallback for blocking-business.

- [ ] No blocking I/O in `async def`: `time.sleep`, `requests.get`, sync DB drivers, sync file I/O on large files
- [ ] No CPU-heavy work on the event loop (hashing, image processing, large parsing) - move to `run_in_executor` or Celery
- [ ] Fan-out uses `asyncio.gather` / `TaskGroup` (3.11+); never sequential awaits in a loop for independent calls
- [ ] Every external call wrapped in `asyncio.timeout(...)` with an explicit budget
- [ ] Fan-out over collections bounded by `asyncio.Semaphore(N)` - unbounded `gather` over a large list exhausts connections
- [ ] No sync ORM (`Session`, `session.query`) inside `async def` - use `AsyncSession`
- [ ] `Depends(get_db)` yield-dependency commits / rolls back; no orphan transactions
- [ ] `httpx.AsyncClient` as a module / app-state singleton with explicit `Timeout` and connection limits - never per-request
- [ ] `pool_size + max_overflow` <= DB `max_connections / N_workers` if pool config in diff

### Step 7 - Pydantic / Serialization (FastAPI)

- [ ] `response_model` declared on every endpoint returning structured data - absent, FastAPI falls back to `dict` and skips validation / field filtering
- [ ] Pydantic v2 (`pydantic>=2`) - v1 patterns (`class Config:`, `parse_obj`, `dict()`) flagged for migration to `model_config = ConfigDict(...)`, `model_validate`, `model_dump`
- [ ] `from_attributes=True` in `model_config` for response models built from ORM rows
- [ ] Heavy `@field_validator` / `@model_validator` not on every request - move expensive checks to service layer
- [ ] `response_model_exclude_unset=True` when partial responses expected
- [ ] Reuse Pydantic models across endpoints rather than redefining identical shapes per route
- [ ] `orjson` / `ujson` renderer (`default_response_class=ORJSONResponse`) for large JSON payloads

### Step 8 - Caching and Response Performance

- [ ] Per-request memoization: `functools.lru_cache` on pure functions; `request.state` cache for values used by multiple dependencies
- [ ] Process-level: `cachetools.TTLCache` / `aiocache` in-process; Redis (`redis-py` async) for shared / multi-instance
- [ ] Stampede protection: hot keys with expensive regen use single-flight (`asyncio.Lock` per key) or Redis `SET NX EX`
- [ ] Invalidation explicit - document staleness budget; no never-expiring caches
- [ ] Django view / template fragment cache scoped to keys including user / tenant when content varies
- [ ] HTTP caching (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs
- [ ] Response compression (`GZipMiddleware`) for JSON > 2KB

### Step 9 - Celery / Background Work

Canonical patterns: Use skill: `python-celery-patterns`. Apply the review-scoped scan:

- [ ] Tasks idempotent; pass IDs not ORM objects
- [ ] Critical tasks set `acks_late=True` + `task_reject_on_worker_lost=True`
- [ ] Retry config declared (`autoretry_for`, `max_retries`, `retry_backoff`, `retry_jitter`); DLQ path for poison messages
- [ ] Queue routing isolates time-sensitive work; workers started with `-Q`
- [ ] `.delay()` AFTER commit (FastAPI: after `session.commit()`; Django: `transaction.on_commit(...)`) - never inside a transaction
- [ ] Long tasks split (target sub-30s median); chord / chain for longer workflows
- [ ] `soft_time_limit` / `time_limit` set on tasks that can hang on external I/O
- [ ] Result backend used only when result is consumed

### Step 10 - Observability for Perf (delegation hand-off)

Depth on observability belongs to `task-python-review-observability`. Confirm only:

- [ ] Slow paths from this PR have **some** instrumentation (OTel span or `prometheus_client` histogram); if not, raise as Low / Recommendation and delegate
- [ ] SQLAlchemy `echo=False` in prod and `django-debug-toolbar` disabled in prod (only if in diff)

Beyond presence/absence -> `task-python-review-observability` owns it.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Write before ending; print confirmation.

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
- **Issue:** [Python idiom: N+1 via lazy `relationship()` access, missing index, sync `requests.get` in async endpoint, Celery `.delay()` inside transaction, `joinedload` on collection without `.unique()`, etc.]
- **Impact:** [estimated: "N+1 in OrderRouter.list adds ~200 queries per request at 100 orders" / measured: "p95 800ms -> 120ms after fix"]
- **Fix:** [specific Python change with code: `selectinload`, `prefetch_related`, `httpx.AsyncClient`, `transaction.on_commit`, etc.]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a finding - e.g., "Switch list endpoint to keyset pagination", "Add Redis cache for product catalog reads", "Move PDF generation to Celery"]

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Add `.options(selectinload(Order.items).selectinload(OrderItem.product))` to OrderRepository.list"]
2. **[Delegate]** [Recommend] [scope: schema] - [one-line action, e.g., "Add concurrent composite index on (tenant_id, created_at)"]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Stack confirmed as Python; framework (FastAPI / Django / mixed) recorded
- [ ] `review-precondition-check` ran (or handle received); diff / log read once and reused
- [ ] Performance surface read directly (models, repositories / managers, routers / views, schemas / serializers, settings, migrations, Celery)
- [ ] `python-sqlalchemy-patterns` / `python-django-patterns` consulted per framework; N+1, multi-level, projection, `MissingGreenlet` checked
- [ ] `python-migration-safety` consulted on migration changes; `lock_timeout`, concurrent index, keyset backfill, expand-contract verified
- [ ] `python-async-patterns` consulted on `async def` / event-loop changes; blocking-call audit, `gather` / `TaskGroup` / `Semaphore`, `asyncio.timeout` wrapping
- [ ] `python-celery-patterns` consulted on any Celery change; idempotency, `acks_late`, retry, post-commit dispatch verified
- [ ] Pool sizing validated against worker / framework concurrency **if pool config in diff**; otherwise Low / Recommendation
- [ ] Caching assessed (in-process vs Redis, single-flight, invalidation) when caching primitives in diff
- [ ] Pydantic v2 / DRF serializer cost assessed when applicable
- [ ] Every finding states impact - measured (`p95 800ms -> 120ms`) when APM data exists, estimated otherwise (`adds ~N queries per request at K rows`)
- [ ] Depth honored: `standard` ran all; `deep` adds capacity + load plan
- [ ] Next Steps with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend > Question
- [ ] Review report written via `review-report-writer`; confirmation printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Generic advice when a Python pattern applies ("use `selectinload`", not "use eager loading")
- Suggesting `lazy="joined"` on collections to fix N+1 - row duplication; use `selectinload` for collections, `joinedload` for single-valued FK / OneToOne
- Suggesting caching without invalidation strategy
- Treating Celery retries as a substitute for idempotency
- Reporting "missing index" without confirming the column appears in `where` / `order_by` / `group_by`
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
