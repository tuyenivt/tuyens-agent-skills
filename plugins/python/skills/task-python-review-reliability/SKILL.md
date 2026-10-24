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

# Python Reliability Review

Stack-specific delegate of `task-code-review-reliability` for Python. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or a worker crashes mid-operation. Names `httpx.AsyncClient` / `httpx.Timeout`, `asyncio.timeout`, `tenacity`, `aiobreaker` / `purgatory` / `pybreaker`, Celery `acks_late` / dead-letter routing, the SQLAlchemy async engine pool and Django 5.1 connection pool, and `asyncio.gather` / `TaskGroup` idioms directly. Every finding names the failure mode and blast radius, with a concrete Python 3.11+ fix.

## Seam With Adjacent Lenses

- **vs. Perf:** perf tunes pool size, worker count, and query shape for throughput; this lens verifies they are bounded and that exhaustion degrades gracefully. A slow query is perf; the untimed query holding a connection until the pool drains is reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback existing and being configured.
- **vs. core Phase B:** Phase B owns happy-path transaction correctness and post-commit dispatch; this lens owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - the umbrella dedups.

## When to Use

- FastAPI or Django PR adding or changing an integration point (`httpx.AsyncClient` call, external SDK, Celery task, lifespan client)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / Celery-consumer correctness under failure

**Not for:** general Python review (`task-python-review`), throughput / N+1 tuning (`task-python-review-perf`), instrumentation wiring (`task-python-review-observability`).

## Depth Levels

| Depth      | When                                              | Runs                                                         |
| ---------- | ------------------------------------------------- | ------------------------------------------------------------ |
| `standard` | Default                                           | Steps 1-12 without the Failure-Mode Map                      |
| `deep`     | Requested, or handed down by `task-python-review` | All, touched files read in full, plus `## Failure-Mode and Blast-Radius Map` |

At `deep`, use skill: `failure-propagation-analysis` on each new / changed dependency; its output fills the map one row per dependency (what happens when it is down or slow, the shared resource on the propagation path - async engine pool, Django connection pool, gunicorn worker slots, event loop, Celery broker - and the loop-breaker that contains it).

## Invocation

`/task-python-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]` - flags compose: `/task-python-review-reliability pr-50273 --base release/2026.05 deep`. No argument reviews the current branch; `pr-<N>` needs the local branch the user fetched.

**Subagent mode** (spawned by `task-python-review` or `task-code-review-reliability`): the parent supplies the stack-detect block, the precondition handle, the read-once diff / name-status / log, and the depth. Step 1 still applies; Steps 2-3 consume the supplied inputs instead of running; Step 12 is skipped and the findings return as the subagent envelope in Output Format (the map included at `deep`) - the parent verifies, reconciles and writes.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 3's precondition fails fast because the current branch is a trunk, do not stop - skip the diff gate and run Steps 4-11 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); a trunk named as the argument while another branch is checked out surfaces the message and stops. Findings cite current code; verify is skipped and every finding is published `Confirmed` with the tally `<N> confirmed, 0 reattributed, 0 unverified, 0 dropped`; the writer gets `branch` = the current branch name, `base_ref` = `head_ref` = `HEAD`, `base_sha` = `head_sha` = the full `git rev-parse HEAD`, `round: 1`; the writer derives the path from `report_type` + `branch` and overwrites a prior sweep report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Framework

Use skill: `stack-detect`. If `Language` is not Python, stop and route to `/task-code-review-reliability`. `Framework` comes from the block (`FastAPI 0.115`, `Django 5.1`); the dependency manifest fills `unknown` and reveals a second framework - `fastapi` -> FastAPI, `django` -> Django; both named -> the one framework the name-status (Step 3) touches, else `mixed` (files under both or neither, and every sweep; both branches of every step run); neither names FastAPI or Django (Flask, plain Python) -> `unknown`: Step 4 reads the framework-neutral categories of both lists, and only the APIs a row names from a framework the project does not use go N/A; its framework-neutral items still run. Record `Framework: FastAPI | Django | mixed | unknown` - FastAPI / Django with a version (the block's when it names that framework with one, else its manifest pin, else omitted) - and the Python version (`Language`, else `requires-python` / `.python-version`, else `unknown`).

### Step 3 - Resolve the Diff and Decide the Round

Use skill: `review-precondition-check` with `argument`, `base` (from `--base`), and `report_type: review-reliability`. On failure, surface its message verbatim and stop - except the trunk case, which takes the whole-service sweep above; never run state-changing git. On success, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`.

**Round gate.** The handle's `prior_checkpoint` is this lens's checkpoint or `legacy`. A valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals the handle's, and whose `depth` the requested depth does not exceed -> print `No new commits since prior reliability review.` and stop: no review, no report. Otherwise a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` (Step 12 overwrites a legacy file). Then read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log <base_ref>..<head_ref>`.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into (a new service method calling an unchanged untimed client is a new failure path at the call site):

**FastAPI:** external-client modules (`httpx.AsyncClient`, SDK wrappers), service methods composing downstream calls, `app/core/config.py` / `.env` (timeout, pool, retry, breaker settings), engine setup (`create_async_engine` `pool_size` / `max_overflow` / `pool_timeout` / `pool_pre_ping` / `pool_recycle`), Celery modules + `celery.py`, lifespan client construction, `run_in_executor` / CPU offload sites, `pyproject.toml` / `requirements.txt` (`tenacity`, `aiobreaker` / `purgatory` / `pybreaker`, `httpx`).

**Django:** external-client modules, service methods, `settings.py` (`DATABASES` `OPTIONS` `connect_timeout` / `pool`, `CONN_MAX_AGE`, `CONN_HEALTH_CHECKS`, `EMAIL_TIMEOUT`, Celery broker config), gunicorn config (`timeout`, `graceful_timeout`, `workers`), Celery modules, `transaction.atomic` / `on_commit` / `select_for_update` sites, `subprocess` and `send_mail` call sites.

To fill the Summary's **Resilience Libraries** field, read the full dependency manifest, not just the diff's added lines, and search the repository's imports for each library found; one with no import is written `<name> (unused)`.

**Gate `ops-resiliency`:** use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns when the surface includes an external client (HTTP, SMTP, SDK, subprocess), a fanning-out service, or breaker / retry / timeout config; skip it on a diff that is purely Celery-idempotency, transaction, or locking work with no synchronous dependency. Gating skips atomic loads, never checklist rows: every row below runs on this skill's own text, and a row goes N/A only when the diff has no matching surface.

### Step 5 - Timeouts and Deadlines

Canonical patterns: Use skill: `python-async-patterns`. Apply the review-scoped scan:

- [ ] **Explicit `httpx.Timeout` on every external call** - a shared `httpx.AsyncClient` sets `httpx.Timeout(connect=, read=, write=, pool=)`. `timeout=None` disables every phase and waits forever on a hung upstream; a client with no argument gets httpx's uniform 5 s default, which ignores the caller's budget - both are findings on a hot path.
- [ ] **Deadline wrapper** - each external call inside `asyncio.timeout(budget)` / `asyncio.wait_for(...)` for a budget independent of the transport timeout; when both apply the stricter wins.
- [ ] **No blocking sync I/O in an async path** - `requests`, a sync `httpx.Client`, a blocking SDK, or a Celery `.delay()` inside `async def` stalls the event loop, so one slow upstream degrades *every* request on that uvicorn worker. Use the async client, or bridge via `run_in_threadpool` / `run_in_executor`.
- [ ] **Timeout budget on chained / fan-out calls** - a request fanning out to N downstreams caps total time; a slow first call leaves budget for the rest or fails fast.
- [ ] **DB acquisition + statement timeout** - SQLAlchemy `pool_timeout` bounds the wait for a connection; a server-side `statement_timeout` (or asyncpg `command_timeout`) so a slow query cannot hold a connection until the pool drains. Django: `connect_timeout` in `OPTIONS`, `EMAIL_TIMEOUT` for SMTP, `subprocess.run(..., timeout=)`, gunicorn `timeout` below the LB idle timeout.

### Step 6 - Retries

Retry-with-backoff from `ops-resiliency` (loaded in Step 4 when the gate opened; a retry surface means an external dependency is present, so load it now if skipped). Celery-side retry is Step 8.

- [ ] **`tenacity` with capped attempts, backoff, and jitter** - `@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(), retry=retry_if_exception_type((httpx.TransportError, ...)))`. A bare `@retry` retries forever and retries programming errors.
- [ ] **Transient errors only** - connection errors, timeouts, 5xx, 429. Never retry 4xx; never retry a non-idempotent operation without an idempotency key (Step 8).
- [ ] **Retry amplification** - chained retries share a per-request budget; retry at one layer, not stacked at every layer, so N services x M attempts cannot multiply.

### Step 7 - Circuit Breakers and Concurrency Isolation

- [ ] **Circuit breaker per external dependency** - `aiobreaker` (async) or `pybreaker` (sync) with `fail_max` + `timeout_duration` / `reset_timeout` (`pybreaker` adds `success_threshold` half-open probes); `purgatory` (sync and async) with `threshold` + `ttl`. A shared or unmonitored breaker counts as missing; breaker-state metering is a visibility gap -> `task-python-review-observability`.
- [ ] **Failure-domain isolation (bulkhead)** - an `asyncio.Semaphore(N)` per downstream, or per-client `httpx.Limits(max_connections=, max_keepalive_connections=)`, so one saturated dependency cannot consume the capacity others share.
- [ ] **Fan-out isolation** - independent downstream calls use `asyncio.gather(return_exceptions=True)` or `TaskGroup`; a bare `gather` propagates the first raise while the surviving siblings keep running detached (leaked work, unobserved exceptions) - `TaskGroup` is what cancels siblings on failure. Pick the semantics deliberately.

### Step 8 - Idempotency and Delivery Semantics

Canonical patterns: Use skill: `python-celery-patterns`. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects; dedup atomic via a DB unique constraint or Redis `SET NX`, not a read-then-write race.
- [ ] **Celery crash-safety** - critical tasks set `acks_late=True` + `reject_on_worker_lost=True` so a worker crash re-queues instead of dropping the message, paired with an idempotent task body; the default `acks_late=False` acks before execution (at-most-once, silent loss on crash).
- [ ] **Bounded Celery retry + dead-letter** - `autoretry_for` / `max_retries` / `retry_backoff` / `retry_jitter`; poison messages route to a dead-letter destination after capped attempts (RabbitMQ: a dead-letter exchange; the Redis broker has no DLX - route terminally failed payloads to a dead-letter queue / task from `on_failure`), never infinite in-place retry; every task sets `soft_time_limit` / `time_limit`. Redis / SQS brokers: `broker_transport_options["visibility_timeout"]` exceeds the longest ETA / countdown including retry backoff (else the scheduled task redelivers and double-runs) and, under `acks_late`, the longest `time_limit` (else a still-running task is redelivered).
- [ ] **`BackgroundTasks` are non-durable** - FastAPI `BackgroundTasks` run in-process; a crash between response and task loses the work. A critical side effect (payment capture, order email) goes to Celery / a durable queue.
- [ ] **No in-transaction dual write** - dispatch after commit: FastAPI `await run_in_threadpool(task.delay, id)` after `await session.commit()`; Django `transaction.on_commit(...)`. Enqueuing inside the transaction fires a task for a row that may roll back, or loses the enqueue on commit failure. Use a transactional outbox where publish must not be lost.
- [ ] **Consumer idempotency** - at-least-once delivery means the task re-fetches state, checks, and returns early on replay.

### Step 9 - Graceful Degradation, Fallbacks, and Load Shedding

- [ ] **Defined fallback per critical dependency** - cached / default / partial data, or an explicit fail-fast (503), rather than an unbounded wait. Fallbacks log the original failure at `warning` with context; no silent `except` hiding degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request; `asyncio.gather(return_exceptions=True)` and handle each slot.
- [ ] **Load shedding / backpressure** - saturation returns 429 / 503 rather than queueing unboundedly: uvicorn `--limit-concurrency`, a `Semaphore`-gated admission, or a bounded `asyncio.Queue` that rejects when full. Sync Django / gunicorn: a bounded worker `timeout` plus upstream rate limiting (`django-ratelimit`, nginx `limit_req`) - the socket backlog is not a shed policy.
- [ ] **No blanket swallow** - a bare `except Exception:` that turns a dependency failure into a wrong-but-200 response is a reliability defect, not style.

### Step 10 - Resource Exhaustion and Saturation

Canonical patterns: Use skill: `python-sqlalchemy-patterns` (pool) and `python-async-patterns` (concurrency).

- [ ] **DB pool bounded** - FastAPI: `create_async_engine` `pool_size` + `max_overflow` per process, times API processes, plus the Celery pool and a reserve, <= DB `max_connections`; `pool_timeout` fails fast; `pool_pre_ping=True` drops dead connections; `pool_recycle` < the DB / proxy idle timeout. Django 5.1: `OPTIONS["pool"]` with `max_size` and `timeout` (then `CONN_MAX_AGE` stays 0), else `CONN_MAX_AGE` + `CONN_HEALTH_CHECKS`. When the ceiling (`max_connections`, deployed worker count) is not in the diff, read repo config; if still unknown, run the check against the stated numbers and record `verify: max_connections unknown` in the finding - never skip the row.
- [ ] **No unbounded `asyncio.gather`** - fan-out over a user-sized collection is capped by `asyncio.Semaphore(N)` or chunked; `TaskGroup` for structured bounded concurrency.
- [ ] **No unbounded accumulation** - large reads stream (`stream_scalars` / `yield_per` + `StreamingResponse`), not fully buffered; queues bounded; caches have eviction / TTL.
- [ ] **Worker limits + graceful shutdown** - uvicorn / gunicorn worker count matched to the pool; uvicorn waits for in-flight requests without limit by default, so set `timeout_graceful_shutdown` (gunicorn `graceful_timeout`, default 30 s) below the orchestrator's kill grace period so the drain finishes before SIGKILL; Celery `worker_max_tasks_per_child` to bound leaks.
- [ ] **GIL offload** - pure-Python CPU work (parsing, templating) runs in a `ProcessPoolExecutor` via `run_in_executor` or in Celery; GIL-releasing C work (hashlib, Pillow) may use the default thread pool. On the event loop either stalls every coroutine on the worker.

### Step 11 - Recoverability and Consistency Under Partial Failure

Cross-aggregate consistency rule (inlined on purpose; no separate consistency atomic): writes that cannot share one transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, saga compensation, safe re-run), not a half-applied change.
- [ ] **Compensation / saga** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Cancellation-safe cleanup** - `asyncio.CancelledError` (client disconnect, deadline) is not swallowed; cleanup runs in `finally` / `async with` so a cancelled request mid-write leaves consistent state. Django concurrent updates use `transaction.atomic` + `select_for_update`.
- [ ] **Readiness reflects dependencies** - `/readyz` gates on the DB pool, Redis, and broker so an instance that cannot serve sheds rather than accepts (probe-wiring depth -> `task-python-review-observability`).
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `python-migration-safety`, `ops-backward-compatibility`); a lock-holding migration on a hot table is a saturation finding here, its DDL safety a perf hand-off.

Defects outside this lens that would corrupt or expose data (raw SQL, an empty `permission_classes`) become `out of lens` lines naming their owner, never findings.

### Step 12 - Verify, Reconcile, Write

Standalone only; subagent runs return the envelope after Step 11.

**Verify.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref` (skipped on a whole-service sweep). Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line`, `Label`, and `Annotation`; its tally is the Summary's `Findings verified:` line.

**Reconcile (round 2+).** Project the prior report at the handle's `report_path` into reconcile's shape: `## High-Impact Findings`, one `### [Label] file:line` heading per finding (the label and bare `file:line` from its `####` heading - a pre-revision report with `- **Location:**` lines gives the Location's bare `file:line` and its own label when it wrote one, else `[Must]` under High Impact, `[Recommend]` otherwise; annotations as separate `_(...)_` groups - `_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`), each followed by an `Issue:` line. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, and `head_sha`; its output renders verbatim under `## Prior Round Reconciliation`. A `Still open` / `Needs re-check` row this round did not re-derive publishes in its prior impact section at its prior label (`[Blocker]` / `[High]` / `[Critical]` -> `[Must]`; other legacy labels -> `[Recommend]`; `[Praise]` never carried) with `_(carried from round <N>)_` after its `file:line` and any annotation; a re-derived row publishes once, as this round's finding.

**Write.** Use skill: `review-report-writer` with `report_type: review-reliability`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `mode: full`, `round` + `prior_head_sha` from the gate, `scope: +rel`, `depth`, `stack` from `Framework` (`python-fastapi | python-django | python-mixed | python`), and `pr_url` when the prior checkpoint has it. Print the confirmation line.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a fence. **Severity:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing `httpx.Timeout` on a hot call, uncapped `tenacity` retry, a missing or exceeded timeout budget on a chained path, blocking sync I/O in an async path, `BackgroundTasks` for a critical side effect, in-transaction dual write, unbounded `gather`, a non-idempotent retry whose duplicate is financial or irreversible); Medium = failure bounded but recovery or containment impaired (breaker absent where a timeout exists, no fallback for a critical dependency, retry without jitter, consumer not idempotent, a non-idempotent retry whose duplicate is a recoverable write, a lock-holding migration on a hot table); Low = hardening with no immediate failure path (missing bulkhead `Semaphore`, fail-fast where stale cache would serve). Every finding carries exactly one label, `[Must]` or `[Recommend]`: High -> `[Must]`, Medium / Low -> `[Recommend]`, and verify's published `Label` governs every slot naming one. A finding sits in the section of its severity; a `[Recommend]` under High after de-escalation counts toward `<H> High`. On a diff-scoped standalone run, a finding on a file absent from the name-status whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first; an `Unverified` row gets none, an old line in a touched file takes verify's attribution, and a sweep (no name-status) stamps nothing. Subagent runs return only `## Findings` (and the map at `deep`), no annotations.

```markdown
## Python Reliability Review Summary

- **Stack:** Python <version>
- **Framework:** FastAPI{ <version>} | Django{ <version>} | mixed | unknown
- **Resilience Libraries:** <each of tenacity, aiobreaker, purgatory, pybreaker in the manifest>{ (unused)} | none detected
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Overall:** Resilient | Gaps Found - <H> High / <M> Medium / <L> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}

## Findings

### High Impact

#### [Must] file:line{ _(annotation)_}{ _(carried from round <N>)_}

- **Issue:** [name the gap: `httpx.AsyncClient` with no `Timeout`, bare `@retry`, `requests.get` in `async def`, `BackgroundTasks` for payment capture, `.delay()` inside the transaction, unbounded `gather`, non-idempotent Celery task with `acks_late`]
- **Failure Mode:** [what fails and how: "upstream latency spike blocks the coroutine until the async pool exhausts; every request on the worker stalls"]
- **Blast Radius:** [what else is affected: "all endpoints on this uvicorn worker return timeouts / 503"]
- **Fix:** [`httpx.Timeout`, `asyncio.timeout`, circuit breaker, `acks_late` + idempotency guard, outbox, `Semaphore` bound]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

- **out of lens:** file:line - [defect in one sentence] - owner: task-python-review-security | task-python-review-perf | task-python-review   {one per such defect}

## Recommendations

[Structural resilience improvements not tied to a single finding - "Wrap the payment client in a `purgatory` breaker with a cached fallback", "Move the order-confirmation email from `BackgroundTasks` to a Celery task"]

## Failure-Mode and Blast-Radius Map   {deep only}

| Dependency | Down or slow -> | Shared resource on the path | Loop-breaker |
| ---------- | --------------- | --------------------------- | ------------ |
| [client or task] | [what the caller does] | async engine pool \| Django connection pool \| gunicorn worker slots \| event loop \| Celery broker \| none | [breaker, timeout, retry budget, load shedding, or `missing`] |

## Prior Round Reconciliation   {round 2+ only}

[reconcile's output verbatim]

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Set `httpx.Timeout(connect=2, read=5, write=5, pool=1)` on the shared client in `app/clients/payment.py`"]
2. **[Delegate]** [Recommend] file:line [scope: platform] - [one-line action, e.g., "Provision a dead-letter queue for the `payments` Celery route"]
```

Empty sections are omitted; within a section `[Must]` first, then by `file:line`. `[Implement]` = a localized fix; `[Delegate]` = cross-cutting or platform work, `[scope: <owner>]` free text. Nothing found writes `No reliability issues found.` under `## Findings`.

## Self-Check

Mark a line N/A when the diff has no matching surface (no Celery, no external clients).

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed Python; `Framework` and Python version taken from stack-detect or the manifest; a both-present `Framework` settled from the name-status (`mixed` on a sweep)
- [ ] Step 3: precondition called with `argument` / `base` / `report_type: review-reliability`; SHAs captured; round gate decided before the diff was read, or the whole-service sweep taken on trunk (skipped on subagent runs)
- [ ] Step 4: external clients, composing services, engine / pool config, Celery, lifespan clients, executor sites, gunicorn / SMTP / subprocess settings read; dependency manifest read for Resilience Libraries; `ops-resiliency` loaded when the surface has a synchronous dependency (gating never skips a checklist row)
- [ ] Step 5: `python-async-patterns` consulted; `httpx.Timeout`, `asyncio.timeout` deadline, no blocking sync I/O in async, timeout budget, DB / SMTP / subprocess / gunicorn timeouts checked
- [ ] Step 6: `tenacity` retries capped with backoff + jitter; transient-only; per-request retry budget verified
- [ ] Step 7: circuit breaker per dependency with library-correct parameters; `Semaphore` / `httpx.Limits` bulkhead; fan-out isolation checked
- [ ] Step 8: `python-celery-patterns` + `backend-idempotency` consulted; idempotency keys, `acks_late` + `reject_on_worker_lost`, bounded retry + dead-letter + `visibility_timeout`, `BackgroundTasks` durability, dispatch after commit via `run_in_threadpool` / `on_commit`, consumer idempotency checked
- [ ] Step 9: fallback per critical dependency; fallbacks log; partial responses; load shedding / backpressure; no blanket swallow verified
- [ ] Step 10: `python-sqlalchemy-patterns` consulted; DB pool bounded (FastAPI formula or Django `OPTIONS["pool"]`), no unbounded `gather`, no unbounded accumulation, graceful shutdown below the kill grace period, GIL offload checked
- [ ] Step 11: cross-aggregate compensation rule applied; crash-safety, compensation, cancellation-safe cleanup, readiness, migration rollout checked; `out of lens` lines emitted
- [ ] Step 12: verify ran, `file:line` / `Label` / `Annotation` published, tally in Summary; round 2+ projected, reconciled, carried; report written with every writer field, or the gate stop line printed (all skipped on subagent runs; verify skipped on a sweep)
- [ ] Every finding names the failure mode and blast radius; depth honored (`deep` filled the map via `failure-propagation-analysis`)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "unbounded `httpx` call to payment-gateway stalls the coroutine until the async pool exhausts")
- Overlapping into perf (throughput tuning) or observability (metric / log wiring) - name the failure-survival gap
- Treating Celery / `tenacity` retries as a substitute for idempotency
- Recommending a circuit breaker with no monitoring, or a fallback that swallows the error silently
- Approving `BackgroundTasks` for a durable / critical side effect - route it to Celery
- Wrapping `asyncio.timeout` around an outer `gather` for partial results (cancels completed work) - put the timeout inside each task
