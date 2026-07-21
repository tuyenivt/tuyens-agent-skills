---
name: task-python-review-reliability
description: "Python reliability review: httpx timeouts, tenacity retries, circuit breakers, Celery acks_late/DLQ, async pool bounds, idempotency, fallbacks."
agent: python-reliability-engineer
metadata:
  category: backend
  tags: [python, fastapi, django, reliability, resilience, idempotency, celery, async, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Python Reliability Review

Stack-specific delegate of `task-code-review-reliability` for Python. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a worker crashes mid-operation. Names `httpx.AsyncClient` / `httpx.Timeout`, `asyncio.timeout`, `tenacity`, `aiobreaker` / `purgatory` / `pybreaker`, Celery `acks_late` / DLQ, SQLAlchemy async engine pool, and `asyncio.gather` / `TaskGroup` idioms directly. Every finding names the failure mode and blast radius, with concrete Python 3.11+ fixes.

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes the async engine pool, worker count, and query shape for throughput; this lens verifies they are bounded and that exhaustion degrades gracefully. A slow query is perf; the untimed query holding a connection until the pool drains is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured.
- **vs. core Phase B:** Phase B owns happy-path transaction correctness and post-commit dispatch; this lens owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - the umbrella dedups.

## When to Use

- FastAPI or Django PR adding or changing an integration point (`httpx.AsyncClient` call, external SDK, Celery task, `@app.on_event` / lifespan client)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / Celery-consumer correctness under failure

**Not for:** general Python review (`task-python-review`), throughput / N+1 tuning (`task-python-review-perf`), instrumentation wiring (`task-python-review-observability`), a live incident (`/task-oncall-start` - mitigate first).

## Depth Levels

| Depth      | When                                              | Runs                                      |
| ---------- | ------------------------------------------------- | ----------------------------------------- |
| `standard` | Default                                           | All steps except the Failure-Mode Map     |
| `deep`     | Requested, or handed down by `task-python-review` | All + `Failure-Mode and Blast-Radius Map` |

At `deep`, use skill: `failure-propagation-analysis` to trace each new / changed dependency's failure path across shared resources (async engine pool, event loop, Celery broker) and name the loop-breaker that contains it.

## Invocation

| Invocation                                | Meaning                                                            |
| ----------------------------------------- | ------------------------------------------------------------------ |
| `/task-python-review-reliability`         | Current branch vs base; fails fast on trunk                        |
| `/task-python-review-reliability <branch>`| `<branch>` vs base (3-dot diff)                                    |
| `/task-python-review-reliability pr-<N>`  | PR head fetched into local `pr-<N>` branch (user runs fetch first) |

Scope and depth flags compose: `/task-python-review-reliability pr-50273 --base release/2026.05 deep`. As a subagent of `task-code-review-reliability` or `task-python-review`, the parent passes the pre-confirmed stack, the precondition handle, and pre-read diff / commit log; Steps 1-2 consume those instead of re-running.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 2 fails fast on trunk, do not stop - skip the diff gate and run Steps 3-11 repo-wide at `HEAD` (Step 3's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept a pre-confirmed stack from parent. Then:

- `main.py` + `fastapi` import / `pyproject.toml` `fastapi` dep -> **FastAPI**
- `manage.py` + `settings.py` / `pyproject.toml` `django` dep -> **Django**
- Both -> ask which surface this PR targets; do not guess

If not Python, stop and route to `/task-code-review-reliability`. Record `Framework: FastAPI | Django | mixed`; steps branch on it.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + pre-read artifacts. If it fails fast (dirty tree, trunk, missing PR ref), surface verbatim and stop - except the whole-service sweep path above. No state-changing git.

### Step 3 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

**FastAPI:** external-client modules (`httpx.AsyncClient`, SDK wrappers), service methods composing multiple downstream calls, `app/core/config.py` / `.env` (timeout, pool, retry, breaker settings), engine setup (`create_async_engine` `pool_size` / `max_overflow` / `pool_timeout` / `pool_pre_ping` / `pool_recycle`), Celery modules + `celery.py`, lifespan / `@app.on_event` client construction, `run_in_executor` / CPU offload sites, `pyproject.toml` / `requirements.txt` (`tenacity`, `aiobreaker` / `purgatory` / `pybreaker`, `httpx`).

**Django:** external-client modules, service methods, `settings.py` (`DATABASES` `OPTIONS` `connect_timeout`, `CONN_MAX_AGE`, `CONN_HEALTH_CHECKS`, Celery broker config), Celery modules, `transaction.atomic` / `on_commit` / `select_for_update` sites.

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns.

### Step 4 - Timeouts and Deadlines

Canonical patterns: Use skill: `python-async-patterns`. Apply the review-scoped scan:

- [ ] **Explicit `httpx.Timeout` on every external call** - a shared `httpx.AsyncClient` sets `httpx.Timeout(connect=, read=, write=, pool=)`; no `timeout=None` and no reliance on an unstated default on a hot path. A naked client with an infinite read waits forever on a hung upstream.
- [ ] **Deadline wrapper** - each external call wrapped in `asyncio.timeout(budget)` / `asyncio.wait_for(...)` for a call budget independent of the transport timeout; when both apply the stricter wins.
- [ ] **No blocking sync I/O in an async path** - `requests`, a sync `httpx.Client`, or a blocking SDK inside `async def` stalls the event loop, so one slow upstream degrades *every* request on that uvicorn worker. Switch to the async client, or bridge via `run_in_executor`.
- [ ] **Timeout budget on chained / fan-out calls** - a request fanning out to N downstreams caps total time; a slow first call leaves budget for the rest or fails fast (`ops-resiliency` timeout budget).
- [ ] **DB acquisition + statement timeout** - SQLAlchemy `pool_timeout` bounds the wait for a connection; a server-side `statement_timeout` (or asyncpg `command_timeout`) so a slow query cannot hold a connection until the pool drains. Django: `connect_timeout` in `OPTIONS`.

### Step 5 - Retries

Use skill: `ops-resiliency` (retry-with-backoff). Celery-side retry is Step 7.

- [ ] **`tenacity` with capped attempts, backoff, and jitter** - `@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(), retry=retry_if_exception_type((httpx.TransportError, ...)))`. A bare `@retry` retries forever and retries programming errors.
- [ ] **Transient errors only** - connection errors, timeouts, 5xx, 429. Never retry 4xx (won't succeed); never retry a non-idempotent operation without an idempotency key (Step 7).
- [ ] **Retry amplification** - chained retries share a per-request budget; retry at one layer, not stacked at every layer, so N services x M attempts is not left to multiply.

### Step 6 - Circuit Breakers and Concurrency Isolation

- [ ] **Circuit breaker per external dependency** - `aiobreaker` / `purgatory` (async) or `pybreaker` (sync) with explicit `fail_max`, reset timeout (open duration), and half-open probes. A shared or unmonitored breaker counts as missing; breaker-state metering is a visibility gap -> `task-python-review-observability`.
- [ ] **Failure-domain isolation (bulkhead)** - an `asyncio.Semaphore(N)` per downstream, or per-client `httpx.Limits(max_connections=, max_keepalive_connections=)`, so one saturated dependency cannot consume the connection capacity others share.
- [ ] **Fan-out isolation** - independent downstream calls use `asyncio.gather(return_exceptions=True)` or `TaskGroup`; a bare `gather` propagates the first raise while the surviving siblings keep running detached (leaked work, unobserved exceptions) - it is `TaskGroup` that cancels siblings on failure. Pick the semantics deliberately; `return_exceptions=True` when optional legs must not sink the batch.

### Step 7 - Idempotency and Delivery Semantics

Canonical patterns: Use skill: `python-celery-patterns`. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup atomic via a DB unique constraint or Redis `SETNX`, not a read-then-write race.
- [ ] **Celery crash-safety** - critical tasks set `acks_late=True` + `task_reject_on_worker_lost=True` so a worker crash re-queues instead of dropping the message; paired with an idempotent task body (default `acks_early` acks before execution = at-most-once, silent loss on crash).
- [ ] **Bounded Celery retry + DLQ** - `autoretry_for` / `max_retries` / `retry_backoff` / `retry_jitter`; poison messages route to a dead-letter destination after capped attempts (RabbitMQ: a dead-letter exchange; the Redis broker has no DLX - route terminally failed payloads to a dead-letter queue/task from an `on_failure` handler), never infinite in-place retry. `visibility_timeout` exceeds the longest task so a redelivery does not double-run a still-running task.
- [ ] **`BackgroundTasks` are non-durable** - FastAPI `BackgroundTasks` run in-process; a crash between response and task loses the work. A critical side effect (payment capture, order email) goes to Celery / a durable queue, not `BackgroundTasks`.
- [ ] **No in-transaction dual write** - dispatch `task.delay(...)` *after* `session.commit()` (FastAPI) or via `transaction.on_commit(...)` (Django). Enqueuing inside the transaction can fire a task for a row that then rolls back, or lose the enqueue on commit failure. Use a transactional outbox where publish must not be lost.
- [ ] **Consumer idempotency** - at-least-once delivery means the task re-fetches state, checks, and returns early on replay.

### Step 8 - Graceful Degradation, Fallbacks, and Load Shedding

- [ ] **Defined fallback per critical dependency** - cached / default / partial data, or an explicit fail-fast (503), rather than an unbounded wait. Fallbacks log the original failure at `warning` with context; no silent `except` that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request; `asyncio.gather(return_exceptions=True)` and handle each slot.
- [ ] **Load shedding / backpressure** - saturation returns 429 / 503 rather than queueing unboundedly: uvicorn `--limit-concurrency`, a `Semaphore`-gated admission, or a bounded `asyncio.Queue` that rejects when full. Sync Django / gunicorn: a bounded worker `timeout` plus upstream rate limiting (`django-ratelimit`, nginx `limit_req`) - the socket backlog is not a shed policy.
- [ ] **No blanket swallow** - a bare `except Exception:` that turns a dependency failure into a wrong-but-200 response is a reliability defect, not just style.

### Step 9 - Resource Exhaustion and Saturation

Canonical patterns: Use skill: `python-sqlalchemy-patterns` (pool) and `python-async-patterns` (concurrency).

- [ ] **Async engine pool bounded** - `create_async_engine` `pool_size` + `max_overflow` <= DB `max_connections` / worker count; `pool_timeout` fails fast; `pool_pre_ping=True` drops dead connections; `pool_recycle` < DB idle timeout. Django: `CONN_MAX_AGE` + `CONN_HEALTH_CHECKS`.
- [ ] **No unbounded `asyncio.gather`** - fan-out over a user-sized collection is capped by `asyncio.Semaphore(N)` or chunked; an unbounded gather exhausts connections and memory. `TaskGroup` for structured bounded concurrency.
- [ ] **No unbounded accumulation** - large reads stream (`stream_scalars` / `yield_per` + `StreamingResponse`), not fully buffered; queues bounded; caches have eviction / TTL.
- [ ] **Worker limits + graceful shutdown** - uvicorn / gunicorn worker count matched to the pool; `timeout_graceful_shutdown` (uvicorn) / `graceful_timeout` (gunicorn) so in-flight requests drain on deploy instead of being cut; Celery `worker_max_tasks_per_child` to bound leaks.
- [ ] **GIL offload** - CPU-bound work (hashing, image / PDF, large parsing) runs in `run_in_executor` with a `ProcessPoolExecutor`, or in Celery; on the event loop it stalls every coroutine on the worker.

### Step 10 - Recoverability and Consistency Under Partial Failure

Use skill: `architecture-data-consistency`.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, saga compensation, safe re-run), not a half-applied change.
- [ ] **Compensation / saga** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Cancellation-safe cleanup** - `asyncio.CancelledError` (client disconnect, deadline) is not swallowed; cleanup runs in `finally` / `async with` so a cancelled request mid-write leaves consistent state. Django concurrent updates use `transaction.atomic` + `select_for_update`.
- [ ] **Readiness reflects dependencies** - `/readyz` gates on the DB pool, Redis, and broker so an instance that cannot serve sheds rather than accepts (probe-wiring depth -> `task-python-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `python-migration-safety`, `ops-backward-compatibility`).

### Step 11 - Write Report

**Subagent mode:** if invoked by `task-python-review` (or `task-code-review-reliability`), do not write a file - return the findings in this skill's Output Format for the parent to merge (the parent owns the report; `review-report-writer` rejects subagent writes). At `deep`, include the Failure-Mode and Blast-Radius Map with the returned findings - the parent preserves it as its own section. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-reliability`. Assemble every checkpoint field the writer requires: `scope: +rel`, `depth` as invoked, `stack = python-<framework>` (e.g., `python-fastapi`, `python-django`), `base_sha` / `head_sha` via `git rev-parse` on the handle's refs (whole-service sweep: both = `HEAD`), and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Write before ending; print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing `httpx.Timeout` on a hot call, uncapped `tenacity` retry, non-idempotent retry, blocking sync I/O in an async path, `BackgroundTasks` for a critical side effect, in-transaction dual write, unbounded `asyncio.gather`); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, consumer not idempotent); Low = hardening with no immediate failure path (missing bulkhead `Semaphore`, fail-fast where stale cache would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`.

```markdown
## Python Reliability Review Summary

**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Resilience Libraries:** tenacity | aiobreaker / purgatory / pybreaker | none detected
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the gap: `httpx.AsyncClient` with no `Timeout`, uncapped `tenacity` retry, `requests.get` in `async def`, `BackgroundTasks` for payment capture, `.delay()` inside the transaction, unbounded `gather`, non-idempotent Celery task with `acks_late`, etc.]
   **Failure Mode:** [what fails and how: "upstream latency spike blocks the coroutine until the async pool exhausts; every request on the worker stalls"]
   **Blast Radius:** [what else is affected: "all endpoints on this uvicorn worker return timeouts / 503"]
   **Fix:** [`httpx.Timeout`, `asyncio.timeout`, circuit breaker, `acks_late` + idempotency guard, outbox, `Semaphore` bound, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins
[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding - e.g., "Wrap the payment client in a `purgatory` breaker with a cached fallback", "Move order-confirmation email from `BackgroundTasks` to a Celery task"]

## Failure-Mode and Blast-Radius Map

_(`deep` only - omit at `standard`.)_
Per new / changed dependency: **what happens when it is down or slow**, the shared resource on the propagation path (async engine pool, event loop, Celery broker), and the loop-breaker that contains it (breaker, timeout, retry budget, load shedding).

## Next Steps

Each item tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Set `httpx.Timeout(connect=2, read=5, write=5, pool=1)` on the shared client in `app/clients/payment.py`"]
2. **[Delegate]** [Recommend] [scope: platform] - [one-line action, e.g., "Provision a dead-letter queue for the `payments` Celery route"]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no Celery, no external clients).

- [ ] Step 1: stack confirmed as Python (or accepted from parent); framework recorded
- [ ] Step 2: `review-precondition-check` ran (or handle received); diff + log read once (or whole-service sweep taken on trunk)
- [ ] Step 3: external clients, composing services, engine / pool config, Celery, lifespan clients, executor sites read; `ops-resiliency` consulted
- [ ] Step 4: `python-async-patterns` consulted; `httpx.Timeout`, `asyncio.timeout` deadline, no blocking sync I/O in async, timeout budget, DB acquisition / statement timeout checked
- [ ] Step 5: `tenacity` retries capped with backoff + jitter; transient-only; per-request retry budget verified
- [ ] Step 6: circuit breaker per dependency; `Semaphore` / `httpx.Limits` bulkhead; fan-out isolation checked
- [ ] Step 7: `python-celery-patterns` + `backend-idempotency` consulted; idempotency keys, `acks_late` + `task_reject_on_worker_lost`, bounded retry + DLQ, `BackgroundTasks` durability, no in-tx dual write, consumer idempotency checked
- [ ] Step 8: fallback per critical dependency; fallbacks log; partial responses; load shedding / backpressure; no blanket swallow verified
- [ ] Step 9: `python-sqlalchemy-patterns` consulted; async pool bounded, no unbounded `gather`, no unbounded accumulation, worker limits + graceful shutdown, GIL offload checked
- [ ] Step 10: `architecture-data-consistency` consulted; crash-safety, compensation, cancellation-safe cleanup, readiness, migration rollout checked
- [ ] Step 11: standalone: report written via `review-report-writer` with full checkpoint fields, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and Blast-Radius Map (via `failure-propagation-analysis`)
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "unbounded `httpx` call to payment-gateway stalls the coroutine until the async pool exhausts")
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Recommending a sync `requests` / blocking SDK call as acceptable inside an `async def` path
- Treating Celery / `tenacity` retries as a substitute for idempotency
- Recommending a circuit breaker with no monitoring, or a fallback that swallows the error silently
- Approving `BackgroundTasks` for a durable / critical side effect - route it to Celery
- Approving `.delay()` inside a transaction, or a `save` + publish dual write without an outbox
- Wrapping `asyncio.timeout` around an outer `gather` for partial results (cancels completed work) - put the timeout inside each task
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
