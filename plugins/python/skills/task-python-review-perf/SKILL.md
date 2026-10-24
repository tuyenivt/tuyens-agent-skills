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

# Python Performance Review

Performance review of SQLAlchemy 2.0, Django ORM loading, event-loop discipline, Pydantic v2 / DRF serialization, Celery task design, and migration safety. Every finding states measured or estimated impact and a concrete fix.

## When to Use

- FastAPI or Django PR / branch perf regression review
- Slow endpoint / Celery task / scheduled job investigation
- Pre-merge perf pass on ORM queries, async boundaries, Celery dispatch, event-loop-blocking calls
- Periodic N+1 / pool-sizing / async-correctness sweep against APM data

**Not for:** general review (`task-python-review`), security (`task-python-review-security`), pre-implementation design (`task-python-implement`).

## Depth Levels

| Depth      | When                                              | Runs                                             |
| ---------- | ------------------------------------------------- | ------------------------------------------------ |
| `standard` | Default                                           | Steps 1-11; diff hunks plus immediate context    |
| `deep`     | Profiling-driven (py-spy / OTel data)             | All, touched files read in full, plus `## Capacity and Load Plan` |

## Invocation

`/task-python-review-perf [<branch> | pr-<N>] [standard | deep] [--base <branch>]` - flags compose: `/task-python-review-perf pr-50273 --base release/2026.05 deep`. No argument reviews the current branch and fails fast on trunk; `pr-<N>` needs the local branch the user fetched.

**Subagent mode** (spawned by `task-python-review` or `task-code-review-perf`): the parent supplies the stack-detect block, the precondition handle, the read-once diff / name-status / log, and the depth. Step 1 still applies; Steps 2-3 consume the supplied inputs instead of running; Step 11 is skipped and the findings return as the subagent envelope in Output Format - the parent verifies, reconciles and writes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Framework

Use skill: `stack-detect`. If `Language` is not Python, stop and route to `/task-code-review-perf`. `Framework` comes from the block; the dependency manifest fills `unknown` and reveals a second framework - `fastapi` -> FastAPI, `django` -> Django; both named -> the one framework the name-status (Step 3) touches, else `mixed` (files under both or neither; both branches of every step run); neither names FastAPI or Django (Flask, plain Python) -> `unknown`: Step 4 reads the framework-neutral categories of both lists, and only the APIs a row names from a framework the project does not use go N/A; its framework-neutral items still run. Record `Framework: FastAPI | Django | mixed | unknown` - FastAPI / Django with a version (the block's when it names that framework with one, else its manifest pin, else omitted) - and the Python version (`Language`, else `requires-python` / `.python-version`, else `unknown`).

### Step 3 - Resolve the Diff and Decide the Round

Use skill: `review-precondition-check` with `argument` (the invocation target, if any), `base` (from `--base`), and `report_type: review-perf`. On failure, surface its message verbatim and stop; never run state-changing git. On success, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`.

**Round gate.** The handle's `prior_checkpoint` is this lens's checkpoint or `legacy`. A valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals the handle's, and whose `depth` the requested depth does not exceed -> print `No new commits since prior perf review.` and stop. Otherwise a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` (Step 11 overwrites a legacy file). Then read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log <base_ref>..<head_ref>`.

A diff touching no application code skips Steps 4-10: `Overall: Clean - diff contains no performance surface`, `## Findings` holding only that sentence, zero tally, no Next Steps; report still written.

### Step 4 - Read the Performance Surface

Cite real `file:line` per finding; open:

**FastAPI:** every changed SQLAlchemy `Mapped[...]` model (`relationship()` options), repository / data-access modules (`select(...)`, `.options(selectinload / joinedload)`, `session.execute`), routers (`async def`, `Depends(get_db)`, `response_model`), Pydantic v2 schemas with validators, `core/config.py` / `.env` pool settings, Alembic revisions under the `script_location` in `alembic.ini` (`alembic/versions/` after `alembic init alembic`), Celery modules + `celery.py`.

**Django:** every changed model (`Meta.indexes`, `db_index`, `related_name`, `on_delete`), QuerySet / manager methods (`select_related`, `prefetch_related`, `only`, `defer`, `annotate`), ViewSets / views (`get_queryset`, pagination, filter backends), serializers (`SerializerMethodField`, nested, `depth`), `settings.py` (connections, cache, Celery), migrations under `<app>/migrations/`, Celery modules.

A small diff can ripple into unchanged code (a new endpoint calling an N+1 repository): read that file.

### Step 5 - ORM Hotspots

Use skill: `python-sqlalchemy-patterns` (SQLAlchemy) or `python-django-patterns` (Django ORM). Flag deviations; skip the irrelevant subsection.

**FastAPI / SQLAlchemy:**

- [ ] Traversed `relationship()` eager-loaded via `selectinload` (collections) or `joinedload` (single-valued FK); `joinedload` on a collection chains `.unique()`
- [ ] Pydantic `from_attributes=True` response models touch only preloaded relationships - fix on the repository, not the schema
- [ ] No `MissingGreenlet` path: every relationship an `async def` reads is eager-loaded or declared `lazy="raise"`; an open `session.begin()` does not make lazy loads safe
- [ ] Existence checks use `await session.scalar(select(exists().where(...)))`, not a discarded object load
- [ ] Unbounded reads use `stream_scalars` / `yield_per` + `StreamingResponse`; lists paginated (keyset over `COUNT(*)`-per-page on large tables)
- [ ] Bulk ops via `session.execute(insert / update, [...])`, not per-row loops
- [ ] `expire_on_commit=False` on `async_sessionmaker`; the service commits before returning - no commit after `yield` in `get_db` (FastAPI 0.118+ runs it after the response)

**Django ORM:**

- [ ] FK / M2M / reverse traversals preloaded via `select_related` / `prefetch_related`; nested via `prefetch_related("items__product")` or `Prefetch(...)`
- [ ] `SerializerMethodField` / nested serializers backed by `prefetch_related` in `get_queryset()`
- [ ] Large-row columns excluded via `only()` / `defer()`; `values()` / `values_list()` when model instantiation is unneeded
- [ ] `exists()` over `count() > 0`; `iterator(chunk_size=...)` for large result sets
- [ ] `bulk_create` / `bulk_update` with explicit `batch_size`; reviewer aware these skip `save()` signals
- [ ] `select_for_update(nowait=... | skip_locked=...)` scoped inside a transaction
- [ ] `CONN_MAX_AGE` + `CONN_HEALTH_CHECKS`, or Django 5.1 `OPTIONS["pool"]` with bounded `max_size` / `timeout` (then `CONN_MAX_AGE` stays 0), when connection config is in the diff or the diff adds a query path and `settings.py` has neither

### Step 6 - Indexes and Migrations

Use skill: `python-migration-safety` for changes under the Alembic `script_location` or `<app>/migrations/`.

- [ ] Every column in `where` / `order_by` / `group_by` backed by an index; composite indexes match leftmost-prefix
- [ ] FK columns indexed (PostgreSQL does not auto-index FKs; Django's `ForeignKey` does)
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY` - Alembic `with op.get_context().autocommit_block(): op.create_index(..., postgresql_concurrently=True)`; Django `AddIndexConcurrently` in a migration with `atomic = False`
- [ ] `SET LOCAL lock_timeout = '2s'` before each `ACCESS EXCLUSIVE` statement, under Alembic `transaction_per_migration=True`; `lock_timeout = 0` inside the `autocommit_block` (a timed-out `CONCURRENTLY` build leaves an `INVALID` index)
- [ ] Unique constraints at the DB level, not only `unique=True` on a non-managed column
- [ ] Partial indexes for boolean / enum filters selecting a small subset
- [ ] No DDL on hot tables in one release (expand-then-contract: add nullable, backfill, switch reads, drop later)
- [ ] Backfill via keyset pagination (`WHERE id > :last_id ORDER BY id LIMIT N`), never `WHERE col IS NULL LIMIT N`
- [ ] Data migrations in their own revision (Alembic) or a migration containing only `RunPython` (Django)

**Reasoning rule.** An index the diff _adds_ marks the column hot - validate selectivity and shape, then safety. A column the diff _adds_ and queries on without an index is a finding.

**Migration impact.** State it before approving DDL on a hot table: _"A plain `CREATE INDEX` on a 50M-row table holds a `SHARE` lock for minutes - writes block; `ALTER TABLE` rewrites take `ACCESS EXCLUSIVE` and block everything."_ Unknown row count: note "row count not in diff - confirm before deploy."

### Step 7 - Async Correctness and Event Loop

_FastAPI and `unknown` async code; skip on Django._

Canonical patterns: Use skill: `python-async-patterns`. Apply the review-scoped scan:

**Impact heuristic.** A blocking call inside `async def` stalls every request in flight on the worker - phrase impact as worker-wide tail latency; an upstream's p99 becomes yours: strict timeouts plus a fallback.

- [ ] No blocking I/O in `async def`: `time.sleep`, `requests.get`, sync DB drivers, Celery `.delay()` without `run_in_threadpool`
- [ ] No CPU-heavy work on the event loop - pure-Python work to a `ProcessPoolExecutor` via `run_in_executor`, GIL-releasing C work to the thread pool, or Celery
- [ ] Fan-out uses `asyncio.gather` / `TaskGroup` (3.11+); never sequential awaits in a loop for independent calls
- [ ] Every external call wrapped in `asyncio.timeout(...)` with an explicit budget
- [ ] Fan-out over collections bounded by `asyncio.Semaphore(N)` - unbounded `gather` over a large list exhausts connections
- [ ] No sync ORM (`Session`, `session.query`) inside `async def` - use `AsyncSession`
- [ ] `httpx.AsyncClient` constructed once in the lifespan handler and held on `app.state`, with explicit `Timeout` and `Limits` - never per request or at import
- [ ] Pool ceiling, when pool / worker / process config is in the diff: `(pool_size + max_overflow) x API processes + Celery pool + reserve (superuser, migrations) <= max_connections`; values absent from the diff come from repo config / runbooks, else Impact notes "max_connections not in repo - confirm before deploy"

### Step 8 - Serialization (Pydantic / DRF)

- [ ] FastAPI: every endpoint returning structured data declares `response_model` or a return annotation - with neither the raw object returns unfiltered
- [ ] Pydantic v2 - v1 patterns (`class Config:`, `parse_obj`, `.dict()`) flagged for `ConfigDict`, `model_validate`, `model_dump`
- [ ] `from_attributes=True` in `model_config` for response models built via `model_validate(orm_row)`
- [ ] Heavy `@field_validator` / `@model_validator` moved to the service layer
- [ ] `response_model_exclude_unset=True` when partial responses are expected
- [ ] Large JSON payloads: `ORJSONResponse` below FastAPI 0.131; from 0.131 it is deprecated - a declared return type or `response_model` serializes straight to JSON bytes
- [ ] DRF: no `depth = N`; nested serializers only over prefetched relations; `SerializerMethodField` never issues per-row queries; `many=True` over per-item serialization

### Step 9 - Caching and Response Performance

- [ ] Per-request memoization via `Depends` (resolved once per request) or `request.state`; `functools.lru_cache` is process-level, for pure functions on immutable args
- [ ] Process-level: `cachetools.TTLCache` / `aiocache` in-process; Redis (`redis-py` async) for shared / multi-instance
- [ ] Stampede protection: hot keys with expensive regen use single-flight (`asyncio.Lock` per key) or Redis `SET NX EX`
- [ ] Invalidation explicit - documented staleness budget; no never-expiring caches
- [ ] Django view / template fragment cache keyed by user / tenant when content varies
- [ ] HTTP caching (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs
- [ ] `app.add_middleware(GZipMiddleware, minimum_size=2048)` so only payloads of 2 KB or more are compressed (default 500 bytes)

### Step 10 - Celery / Background Work

Canonical patterns: Use skill: `python-celery-patterns`. Apply the review-scoped scan:

- [ ] Tasks idempotent; pass IDs not ORM objects
- [ ] Critical tasks set `acks_late=True` + `reject_on_worker_lost=True`
- [ ] Retry config declared (`autoretry_for`, `max_retries`, `retry_backoff`, `retry_jitter`); dead-letter path for poison messages
- [ ] Queue routing isolates time-sensitive work; workers started with `-Q`
- [ ] Dispatch after commit - FastAPI `await run_in_threadpool(task.delay, id)` after `session.commit()`; Django `transaction.on_commit(...)`
- [ ] Long tasks split (target sub-30s median); chord / chain for longer workflows
- [ ] `soft_time_limit` / `time_limit` set on every task
- [ ] Result backend used only when the result is consumed

**Observability hand-off.** A slow path from this PR with no instrumentation (span or histogram) is a Low finding delegated to `task-python-review-observability`, which owns the rest. Defects outside this lens that would corrupt or expose data (raw SQL, an empty `permission_classes`) become `out of lens` lines, never findings.

### Step 11 - Verify, Reconcile, Write

Standalone only; subagent runs return the envelope after Step 10.

**Verify.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line`, `Label`, and `Annotation`; its tally is the Summary's `Findings verified:` line.

**Reconcile (round 2+).** Project the prior report at the handle's `report_path` into reconcile's shape: `## High-Impact Findings`, one `### [Label] file:line` heading per finding (the label and bare `file:line` from its `####` heading - a pre-revision report with `- **Location:**` lines gives the Location's bare `file:line` and its own label when it wrote one, else `[Must]` under High Impact, `[Recommend]` otherwise; annotations as separate `_(...)_` groups - `_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`), each followed by an `Issue:` line. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, and `head_sha`; its output renders verbatim under `## Prior Round Reconciliation`. A `Still open` / `Needs re-check` row this round did not re-derive publishes in its prior impact section at its prior label (`[Blocker]` / `[High]` / `[Critical]` -> `[Must]`; other legacy labels -> `[Recommend]`; `[Praise]` never carried) with `_(carried from round <N>)_` after its `file:line` and any annotation; a re-derived row publishes once, as this round's finding.

**Write.** Use skill: `review-report-writer` with `report_type: review-perf`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `mode: full`, `round` + `prior_head_sha` from the gate, `scope: +perf`, `depth`, `stack` from `Framework` (`python-fastapi | python-django | python-mixed | python`), and `pr_url` when the prior checkpoint has it. Print the confirmation line.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a fence. Every finding carries exactly one label, `[Must]` or `[Recommend]`: impact sets the draft (High -> `[Must]`, Medium / Low -> `[Recommend]`) and verify's published `Label` governs every slot naming one. A finding sits in the section of its impact; a `[Recommend]` under High after de-escalation counts toward `<H> High`. A standalone finding on a file absent from the name-status whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first; an `Unverified` row gets none, and an old line in a touched file takes verify's attribution. Subagent runs return only `## Findings` (impact sections, `out of lens` lines, no annotations) plus `## Capacity and Load Plan` at `deep`.

```markdown
## Python Performance Review Summary

- **Stack:** Python <version>
- **Framework:** FastAPI{ <version>} | Django{ <version>} | mixed | unknown
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Overall:** Clean | Clean - diff contains no performance surface | Issues Found - <H> High / <M> Medium / <L> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}

## Findings

### High Impact

#### [Must] file:line{ _(annotation)_}{ _(carried from round <N>)_}

- **Issue:** [Python idiom: N+1 via lazy `relationship()`, missing index, `requests.get` in an async endpoint]
- **Impact:** [estimated: "adds ~200 queries per request at 100 orders" / measured: "p95 800ms -> 120ms after fix"]
- **Fix:** [specific change with code, tagged (quick win) or (structural)]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

- **out of lens:** file:line - [defect in one sentence] - owner: task-python-review-security | task-python-review-reliability | task-python-review   {one per such defect}

## Recommendations

[Structural improvements not tied to a finding - keyset pagination, Redis cache, PDF generation in Celery]

## Capacity and Load Plan   {deep only}

[Pool and worker ceilings against the deploy topology; the load test proving the fix (tool, target p95, concurrency)]

## Prior Round Reconciliation   {round 2+ only}

[reconcile's output verbatim]

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: schema] - [one-line action]
```

Empty sections are omitted; within a section `[Must]` first, then by `file:line`. `[Implement]` = a localized fix; `[Delegate]` = cross-cutting or platform work, `[scope: <owner>]` free text. Nothing found writes `No performance issues found.` under `## Findings`.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or inlined in the spawning prompt)
- [ ] Step 2: stack confirmed Python; `Framework` and Python version taken from stack-detect or the manifest; `mixed` settled from the name-status
- [ ] Step 3: precondition called with `argument` / `base` / `report_type: review-perf`; SHAs captured; round gate decided before the diff was read; no-surface diff reported Clean (skipped on subagent runs)
- [ ] Step 4: surface read, including unchanged files the diff calls into
- [ ] Step 5: ORM atomic consulted where an ORM is present; N+1, eager loading, `MissingGreenlet`, pool config checked
- [ ] Step 6: `python-migration-safety` consulted on migration changes; lock timeout, concurrent index, keyset backfill, expand-contract verified
- [ ] Step 7: `python-async-patterns` consulted (skipped on Django); blocking calls, bounded fan-out, `asyncio.timeout`, lifespan client checked; pool formula when pool / worker / process config is in the diff
- [ ] Step 8: serialization cost assessed (Pydantic v2 and DRF rows)
- [ ] Step 9: caching assessed when the diff adds caching
- [ ] Step 10: `python-celery-patterns` consulted on Celery changes; observability hand-off and `out of lens` lines emitted
- [ ] Step 11: verify ran and its `file:line` / `Label` / `Annotation` published; round 2+ projected, reconciled, carried; report written with every writer field, or the gate stop line printed (skipped on subagent runs)
- [ ] Every finding states impact and a (quick win) / (structural) tag; Next Steps `[Must]` first

## Avoid

- Generic advice when a Python pattern applies ("`selectinload`", not "eager loading")
