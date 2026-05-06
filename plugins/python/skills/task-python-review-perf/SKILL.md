---
name: task-python-review-perf
description: Python performance review for SQLAlchemy / Django ORM N+1, async event-loop blocking, sync-in-async traps, connection pool sizing, Celery throughput / acks_late, Pydantic v2 serialization cost, and migration safety. Detects FastAPI vs Django and applies the right framework idioms. Stack-specific override of task-code-review-perf, invoked when stack-detect resolves to Python.
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
- Pre-implementation feature design (use `task-python-new`)

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

Use skill: `stack-detect` to confirm Python. If the detected stack is not Python, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Python 3.11+.

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

> If `Framework: FastAPI` was recorded in Step 1, **skip the Django subsection entirely** below; do not scan it for non-applicable bullets. Likewise skip the FastAPI subsection on Django-only projects. The bifurcation exists for mixed codebases - on monoglot projects it should be one read, not two.

**If FastAPI / SQLAlchemy** - use skill: `python-sqlalchemy-patterns`:

Inspect every changed model, repository, service, and router for:

- [ ] **N+1 in queries**: any `relationship()` traversed after a `select(...)` is preloaded with `.options(selectinload(...))` (collections, default choice) or `.options(joinedload(...))` (single-valued FK / one-to-one). `lazy="raise"` recommended in dev to surface accidental N+1.
- [ ] **N+1 in response serialization**: Pydantic schemas with `model_config = ConfigDict(from_attributes=True)` silently trigger N+1 when they touch a relationship not preloaded. Fix is on the _repository / service_ (eager-load), not the schema.
- [ ] **Multi-level N+1**: nested traversal across two relationships (`order.items` → `item.product`) - resolve with chained `.options(selectinload(Order.items).selectinload(OrderItem.product))`.
- [ ] **`MissingGreenlet` / lazy access outside session**: any access to a relationship outside `async with session.begin()` / the `Depends(get_db)` lifespan. SQLAlchemy async sessions cannot lazy-load - either eager-load or pass IDs to a helper that opens its own session.
- [ ] **`joinedload` on collections without `.unique()`**: row duplication; chain `.unique()` on the result or prefer `selectinload` for collections.
- [ ] **Missing indexes for filter/sort columns**: any field used in `.where(...)` / `.order_by(...)` / `.group_by(...)` without a backing index in the Alembic migration.
- [ ] **`session.scalars(select(X)).all()` without pagination**: any read of an unbounded collection - require keyset / `.limit()` for any list endpoint that can grow.
- [ ] **`exists()` vs `select().first()` for existence**: existence checks must use `await session.scalar(select(exists().where(...)))`, not loading an object then discarding it.
- [ ] **Bulk operations**: `session.execute(insert(X), [{...}, ...])` over loops; `session.execute(update(X).where(...))` over per-row updates; do not iterate `.all()` to issue per-row writes.
- [ ] **`expire_on_commit=False`** on `async_sessionmaker` (the safe default for async); confirm not flipped silently.
- [ ] **Connection pool sizing**: `pool_size` and `max_overflow` documented; `pool_pre_ping=True` on long-lived envs; `pool_recycle` shorter than upstream `wait_timeout`.

**If Django / Django ORM** - use skill: `python-django-patterns`:

- [ ] **N+1 in queryset**: any traversal of a FK / M2M / reverse relation after `.all()` is preloaded with `select_related` (FK / OneToOne, single SQL JOIN) or `prefetch_related` (M2M / reverse FK, separate query). Nested with `prefetch_related("items__product")` or `Prefetch(...)`.
- [ ] **N+1 in serializers**: `SerializerMethodField` / nested serializers iterating over `instance.related.all()` without a `prefetch_related` in `get_queryset()`.
- [ ] **`only()` / `defer()` for large rows**: TextField / JSONField / BinaryField columns excluded when not needed.
- [ ] **`values()` / `values_list()` over model instantiation**: when you only need a few columns, skip model construction entirely.
- [ ] **`exists()` over `count() > 0`**: `count()` runs `SELECT COUNT(*)`; `exists()` runs `SELECT 1 ... LIMIT 1`.
- [ ] **`iterator()` for large result sets**: prevents prefetch cache buildup; `chunk_size` set explicitly.
- [ ] **`bulk_create` / `bulk_update` over loops**: with `batch_size` for large datasets; understand that `bulk_create` skips `save()` signals.
- [ ] **`select_for_update()`** scoped to a transaction for concurrent-update safety; `nowait=True` or `skip_locked=True` documented.
- [ ] **`annotate` / `aggregate` for DB-level computation**: avoid pulling rows to compute totals in Python.
- [ ] **Missing indexes**: `Meta.indexes`, `db_index=True`, or migration-defined index for filter/sort columns.
- [ ] **`CONN_MAX_AGE`** set (typically 60-300s) to avoid per-request connection setup; `CONN_HEALTH_CHECKS=True` (Django 4.1+) to drop stale connections without latency hit.

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

Use skill: `python-async-patterns` for asyncio patterns.

Inspect changes touching `async def`, `await`, `asyncio.gather`, `TaskGroup`:

- [ ] **No blocking I/O in `async def`**: `time.sleep` → `asyncio.sleep`; `requests.get` → `httpx.AsyncClient.get`; sync DB drivers (`psycopg2`) → async driver (`asyncpg` / `psycopg[binary,pool]` async). Sync file I/O on small files is acceptable; large files use `aiofiles`.

> **Impact heuristic - blast radius of an event-loop block.** A blocking call inside `async def` does not just slow the calling request - it stalls _every other request currently in flight on this uvicorn worker_. With `--workers 4` and a 50ms `time.sleep`, a single endpoint can drag tail latency across all four endpoints sharing that worker until it returns. Phrase the impact as "tail-latency contagion across all endpoints on this worker," not "this request is slow."

> **Synchronous external dependency on the request path.** Even when the call uses `httpx.AsyncClient` correctly, an HTTP call to a critical-path service (fraud, auth, pricing) inherits the upstream's tail latency: your p99 = max(your work, upstream p99). Recommend async patterns (decision cache, circuit breaker, fire-and-forget) when the call is non-blocking-business; recommend strict timeouts (`asyncio.timeout(0.5)`) plus fallback values when blocking-business.

- [ ] **No CPU-heavy work in the event loop**: hashing, image processing, parsing large payloads must go to `loop.run_in_executor(None, fn)` or a Celery task; otherwise tail-latency for all in-flight requests degrades.
- [ ] **`asyncio.gather` for fan-out**: independent I/O calls run concurrently, not sequentially in a loop. Use `asyncio.gather(*coros)` or `TaskGroup` (Python 3.11+) for structured concurrency.
- [ ] **`TaskGroup` for new code**: prefer `async with asyncio.TaskGroup() as tg:` over `gather` when one failure should cancel siblings.
- [ ] **`asyncio.timeout(...)`** wraps every external call (Python 3.11+); explicit timeout per call beats relying on httpx defaults.
- [ ] **Concurrency cap**: fan-out over a list uses `asyncio.Semaphore(N)` to bound concurrent calls; unbounded `gather` over a 10k-row list will exhaust connections.
- [ ] **No mixing of sync ORM into async path**: `Session` / `session.query(...)` in an `async def` will block the loop. Use `AsyncSession` / `await session.execute(select(...))`. If unavoidable (legacy migration), wrap in `loop.run_in_executor`.
- [ ] **`Depends(get_db)` lifecycle**: yield-style dependency commits/rolls back at request end; no orphan transactions left open across requests.
- [ ] **HTTP clients** (`httpx.AsyncClient`) reused as a module-level singleton or app-state object, not instantiated per request; explicit `timeout=httpx.Timeout(...)` and connection limits.
- [ ] **Connection pool sized correctly**: SQLAlchemy `pool_size + max_overflow` ≤ DB-side `max_connections / N_workers`. For uvicorn with 4 workers and Postgres `max_connections=100`, target ~20 per worker. Oversize and DB starves.

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

Use skill: `python-celery-patterns` for canonical task patterns.

- [ ] **Tasks idempotent**: re-fetch state, check if work was done, return early. Pass IDs / simple types - never ORM objects (lazy attributes, stale data, pickle issues).
- [ ] **`acks_late=True`** + `task_reject_on_worker_lost=True` for at-least-once semantics on critical tasks; default fire-and-forget only for non-critical
- [ ] **Retry strategy declared**: `autoretry_for`, `max_retries`, `retry_backoff=True`, `retry_backoff_max`, `retry_jitter=True` to prevent thundering herd
- [ ] **Dead-letter queue** for permanently failed tasks; no infinite retry loops on poison messages
- [ ] **Queue routing** (`task_routes`): time-sensitive tasks on dedicated queue; workers started with `-Q` to consume specific queues; avoid one queue serving heterogeneous priorities
- [ ] **`.delay()` AFTER the DB transaction commits** (FastAPI: dispatched after `session.commit()`; Django: `transaction.on_commit(lambda: task.delay(...))`); dispatching inside the transaction means the worker may pick it up before the row is visible
- [ ] **Long-running tasks split**: target sub-30-second median; longer work uses chord / chain or workflow steps
- [ ] **Result backend usage**: only when result is consumed - storing results "just in case" wastes Redis / DB
- [ ] **`time_limit` and `soft_time_limit`** set on tasks that can hang on external I/O

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-python-review-observability`. From a perf perspective, confirm only:

- [ ] Slow paths reachable from this PR have **some** instrumentation (OTel span or `prometheus_client` histogram); if not, raise as a Low/Recommendation finding and delegate to `task-python-review-observability` for a proper instrumentation pass rather than dictating the design here.
- [ ] SQLAlchemy `echo=False` in prod and `django-debug-toolbar` disabled in prod - if visible in the diff. If neither is in the diff, skip.

Anything beyond presence/absence (sampling rates, span attributes, correlation IDs, multi-process Prometheus) → `task-python-review-observability` owns it. Note the gap, do not duplicate the audit here.

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
