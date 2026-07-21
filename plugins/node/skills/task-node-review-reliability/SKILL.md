---
name: task-node-review-reliability
description: "Node.js reliability review: AbortSignal timeouts, opossum/cockatiel breakers, p-retry, BullMQ DLQ/idempotency, bounded concurrency, graceful shutdown."
agent: node-reliability-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, reliability, resilience, circuit-breaker, idempotency, bullmq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Reliability Review

Node.js-aware reliability review naming `AbortSignal.timeout`, `opossum` / `cockatiel`, `p-retry` / `p-limit`, BullMQ `attempts` / DLQ / `jobId`, the Prisma / TypeORM pool, and `SIGTERM` shutdown draining directly. Reliability = behavior under failure and saturation: what happens when a dependency is slow or down, load spikes, or the process is killed mid-flight. On a single-threaded event loop one unbounded wait or one blocked tick stalls every in-flight request, so the bar is bounded, contained, and recoverable. Findings name the failure mode and blast radius with concrete TypeScript fixes.

Stack-specific delegate of `task-code-review-reliability`.

## When to Use

- NestJS or Express PR / branch adding or changing an integration point (`axios` / `undici` / `fetch` client, BullMQ `@Processor`, `@Cron` / scheduled job)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; recurring resilience-debt sweep
- Dual-write / outbox / consumer-retry correctness under failure

**Not for:** general Node review (`task-node-review`), throughput / latency tuning (`task-node-review-perf`), telemetry wiring (`task-node-review-observability`), security (`task-node-review-security`), a live incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns *fast under normal load* (N+1, pool sizing for throughput, tail-latency contagion from a slow upstream where p99 = max(your work, upstream p99)). This lens owns *survival when that upstream hangs or dies*: the `AbortSignal.timeout` existing so the call cannot hang forever, and the breaker / fallback when it trips. Pool: perf sizes it; this lens verifies it is bounded and that exhaustion sheds rather than blocks. If the fix is "make it faster," it's perf; if the fix is "survive it being slow or down," it's reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback *existing and being configured*. Report the mechanism gap here, the visibility gap in obs.
- **vs. umbrella Phase B:** the umbrella's Phase B owns happy-path correctness and transaction-boundary correctness; this lens owns partial failure, dependency failure, and saturation. Idempotency (HTTP `Idempotency-Key`, BullMQ `jobId`) sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                              | Steps Run                                 |
| ---------- | ------------------------------------------------- | ----------------------------------------- |
| `standard` | Default                                           | All except the Failure-Mode Map           |
| `deep`     | Requested, or handed down by `task-node-review`   | All + `Failure-Mode and Blast-Radius Map` |

At `deep`, trace each new or changed dependency's failure path across service boundaries and shared resources (the DB pool, Redis, the event loop, BullMQ workers) and name the loop-breaker.

Invocation forms (`/task-node-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`) follow `task-code-review-reliability`. When invoked as a subagent, the parent passes the pre-confirmed stack, the precondition handle, and pre-read diff and commit log; Steps 2-3 consume those instead of re-running.

**Whole-service sweep** (resilience-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-10 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Framework

Accept a pre-confirmed stack from a parent (`task-node-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Node, stop and route the user to `/task-code-review-reliability`. Detect `Framework` (NestJS via `nest-cli.json` / `@nestjs/*`; Express otherwise) and `ORM` (Prisma via `schema.prisma`; TypeORM via `data-source.ts`) from evidence - later steps branch on both.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Once the handle is emitted, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim. No state-changing git.

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- Outbound clients: `axios.create` / `undici.Pool` / `got.extend` / bare `fetch` callsites and per-vendor wrappers - `AbortSignal.timeout`, breaker, retry
- Service methods composing multiple downstream calls (`Promise.all` / `Promise.allSettled`, fan-out loops) - timeout budget, partial-failure handling
- BullMQ producers (`queue.add`) and `@Processor` / `Worker` classes - `attempts` / `backoff`, DLQ, `jobId`, `stalledInterval` / `lockDuration`, worker `concurrency`, idempotency
- Scheduled work: `@nestjs/schedule` `@Cron` / `@Interval`, `setInterval` - overlap guards, failure isolation
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox
- Config and lifecycle: `main.ts` (`enableShutdownHooks`, `SIGTERM`), `prisma.service.ts` / `data-source.ts` pool config, `ConfigModule`, resilience wiring (`opossum` / `cockatiel` / `p-retry` / `p-limit`), and `package.json` dependency adds

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns and the Node resilience library.

### Step 5 - Timeouts, Retries, Circuit Breakers, Bounded Concurrency

Use skill: `node-http-client-patterns` for the outbound timeout / retry / idempotency / wrapper contract. Flag deviations.

- [ ] **Timeout on every outbound call** - `AbortSignal.timeout(ms)` (or `axios` `timeout`, `undici` `headersTimeout` + `bodyTimeout`, `got` `timeout.request`). Node `fetch` and `axios` have **no default timeout** - a missing one is an infinite hang, not a slow call. Client-initiated cancellation propagated: abort outbound work when the inbound request dies - `AbortSignal.any([ac.signal, AbortSignal.timeout(ms)])` with an `AbortController` aborted on the request `close` event (Express/NestJS `IncomingMessage` has no `.signal`; that property exists only on fetch-style `Request` objects). Write paths bound with `statement_timeout` (see `node-transaction-patterns`).
- [ ] **Timeout budget on chained calls** - a request fanning out to multiple downstreams caps total time; a slow first call leaves budget for the rest or fails fast.
- [ ] **Retries bounded and safe** - `p-retry` or `opossum` / `cockatiel` retry policy with capped attempts, exponential backoff, and jitter. Retry only transient errors (5xx, timeouts, `ECONNRESET`); never 4xx; never a non-idempotent POST without an `Idempotency-Key`.
- [ ] **Retry amplification** - chained retries share a per-request budget. In-process retry is seconds (2-3 attempts); waits of minutes-to-hours belong to BullMQ, whose queue owns scheduling - a sync handler cannot sleep 5 minutes.
- [ ] **Circuit breaker per external dependency** - `opossum` (`new CircuitBreaker(fn, { errorThresholdPercentage, resetTimeout })`) or `cockatiel` policy with explicit threshold and half-open probe; state metered (visibility gap -> `task-node-review-observability`). A shared or unmonitored breaker counts as missing.
- [ ] **Bounded concurrency / bulkhead** - there are no OS thread pools to isolate on a single-threaded runtime: bound concurrent in-flight calls per dependency with `p-limit` / `bottleneck` (or `cockatiel` bulkhead), and route independent workloads to separate BullMQ queues so one slow dependency cannot starve the others.

### Step 6 - Idempotency and Delivery Semantics

Use skill: `node-bullmq-patterns` and `node-transaction-patterns`. Use skill: `backend-idempotency` for key strategy and atomic dedup.

- [ ] **Idempotency keys** on money / notification / provisioning side effects - HTTP `Idempotency-Key` deduped by a unique constraint or Redis `SET NX EX`; atomic, not a read-then-write race.
- [ ] **BullMQ durable delivery** - `attempts` + `backoff: { type: 'exponential' }`; a stable `jobId` for server-side dedup; `removeOnFail` bounded so the failed set acts as a visible DLQ (never `removeOnFail: true` where failures must be inspected); `lockDuration` >= job runtime or `stalledInterval` tuned, else BullMQ marks the job stalled and re-runs it (double-execution).
- [ ] **No in-transaction dual write** - `queue.add` / `stripe.charge` / `mailer.send` inside `prisma.$transaction` / `dataSource.transaction` can commit the DB and lose the publish, or let a worker pick the job before `COMMIT` is visible. Capture scalars inside, dispatch after commit, or use a transactional outbox (`node-transaction-patterns`).
- [ ] **Consumer idempotency** - at-least-once delivery means processors re-fetch state, check, and return early on replay; never assume exactly-once.
- [ ] **DLQ with bounded retry** - poison jobs land in the failed set after capped `attempts`; no infinite in-place retry.

### Step 7 - Graceful Degradation and Fallbacks

- [ ] **Defined fallback per critical dependency** - `opossum` `.fallback(...)` / `cockatiel` returning cached / default / partial data, or an explicit fail-fast (503) rather than an unbounded wait.
- [ ] **`Promise.allSettled` over `Promise.all` for optional fan-out** - `Promise.all` rejects the whole batch on the first failure; use `allSettled` when one optional downstream must not sink the others.
- [ ] **Fallbacks log the original failure** at `warn` with context (see `node-exception-handling`); no silent swallow that hides degradation until it compounds.
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the whole request.
- [ ] **Load shedding / backpressure** - saturation returns 429 / 503 or sheds load rather than queueing unboundedly; large payloads stream via `stream.pipeline` (honoring `highWaterMark`) rather than buffering fully; NestJS `TimeoutInterceptor` bounds request wall-clock where a hard ceiling is wanted.

### Step 8 - Resource Exhaustion and Saturation

- [ ] **DB pool bounded** - Prisma `connection_limit` / TypeORM `extra.max` set; `connectionTimeoutMillis` fails fast (1-3s) rather than blocking the caller under exhaustion; `idleTimeoutMillis` reaps idle connections; worker `concurrency` <= pool size (see `node-connection-pool-sizing`).
- [ ] **No unbounded `Promise.all`** - fanning `Promise.all` over a user-sized or large array opens N connections / sockets at once; bound it with `p-limit`. (Distinct from Step 7's `allSettled` fail-all point - here the hazard is unbounded width.)
- [ ] **No event-loop blocking on request paths** - `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, catastrophic regex stall *every in-flight request on the process*; offload to `worker_threads` (`piscina`) or BullMQ. Presence is the reliability finding; tuning depth -> `task-node-review-perf`.
- [ ] **No unbounded accumulation** - in-memory `Map` / `Set` / cache / buffer that grows with load has a bound or eviction (`lru-cache`); streamed, not fully buffered, for large data.
- [ ] **Scheduled overlap** - a long `@Cron` / `setInterval` job guards against overlapping runs (a running-flag, distributed lock, or `@Interval` sized to worst-case runtime) so a slow run does not stack.

### Step 9 - Recoverability and Consistency Under Failure

Use skill: `architecture-data-consistency`. Use skill: `node-transaction-patterns` for boundary correctness.

- [ ] **Graceful shutdown drains in-flight** - on `SIGTERM`: stop accepting (`app.close()` / `server.close()`), await in-flight, `await worker.close()`, `await prisma.$disconnect()` / `dataSource.destroy()`. NestJS wires this via `app.enableShutdownHooks()` + `OnApplicationShutdown`. Absence drops in-flight HTTP requests and re-queues in-flight jobs on **every deploy**.
- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, safe re-run), not a half-applied change.
- [ ] **No unhandled-rejection crash surface** - fire-and-forget async (`void doThing()` with no `.catch`, floating promises) becomes an `unhandledRejection`; `process.on('unhandledRejection')` / `'uncaughtException')` are registered once as log-and-exit backstops (see `node-exception-handling`), not control flow.
- [ ] **Compensation** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Readiness reflects dependencies** - `/ready` gates on own-pod DB pool + Redis + BullMQ so an unready instance sheds rather than accepts traffic it cannot serve (probe-wiring depth -> `task-node-review-observability`); NestJS `@nestjs/terminus`.
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `node-migration-safety`, `ops-backward-compatibility`).

### Step 10 - Write Report

**Subagent mode:** if invoked by `task-node-review`, do not write a file - return the findings in this skill's Output Format for the parent to merge (the parent owns the report; `review-report-writer` rejects subagent writes). At `deep`, include the Failure-Mode and Blast-Radius Map with the returned findings - the parent preserves it as its own section. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-reliability`. Assemble every checkpoint field the writer requires: `scope: +rel`, `depth` as invoked, `stack = node-typescript`, `base_sha` / `head_sha` via `git rev-parse` on the handle's refs (whole-service sweep: both = `HEAD`), and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Write to the report file, then print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing timeout on a hot outbound call, uncapped retry, non-idempotent POST retry, in-tx dual write, unbounded `Promise.all` on a hot path, event-loop blocking in a request path, no graceful shutdown dropping in-flight work on deploy); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, consumer not idempotent, unbounded in-memory accumulation); Low = hardening with no immediate failure path (missing `p-limit` bulkhead, fail-fast where cached data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`.

```markdown
## Node.js Reliability Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>
**Resilience Library:** opossum | cockatiel | p-retry | none detected
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the gap: `fetch` with no `AbortSignal.timeout`, uncapped `p-retry`, `queue.add` inside `$transaction`, unbounded `Promise.all`, non-idempotent processor, no `SIGTERM` drain, etc.]
   **Failure Mode:** [what fails and how: "SendGrid latency spike leaves the `fetch` hanging with no timeout; the request never resolves and the event loop accrues pending sockets"]
   **Blast Radius:** [what else is affected: "every route sharing the process degrades; the DB pool holds connections behind the stalled handlers"]
   **Fix:** [`AbortSignal.timeout(5_000)` + `opossum` breaker + fallback, transactional outbox, `p-limit`, `worker.close()` on `SIGTERM`, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins
[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural resilience improvements not tied to a single finding]

## Failure-Mode and Blast-Radius Map

_(`deep` only - omit at `standard`.)_
Per new / changed dependency: **what happens when it is down or slow**, the shared resource on the propagation path (event loop, DB pool, Redis, BullMQ workers), and the loop-breaker that contains it (timeout, breaker, retry budget, load shedding).

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: platform] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no messaging, no scheduled jobs).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Node / TypeScript (or pre-confirmed stack accepted from parent); framework + ORM recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once
- [ ] Step 4: outbound clients, composing services, BullMQ, scheduled jobs, side-effecting flows, config/lifecycle read
- [ ] Step 5: `node-http-client-patterns` + `ops-resiliency` consulted; `AbortSignal` timeouts, retry safety/budget, breaker, bounded concurrency checked
- [ ] Step 6: `backend-idempotency` + `node-bullmq-patterns` + `node-transaction-patterns` consulted; idempotency keys, BullMQ attempts/DLQ/`jobId`, no in-tx dual write, consumer idempotency checked
- [ ] Step 7: fallback per critical dependency; `allSettled` on optional fan-out; fallbacks log; partial responses; load shedding / backpressure verified
- [ ] Step 8: DB pool bounded; no unbounded `Promise.all`; no event-loop blocking; no unbounded accumulation; scheduled overlap guarded
- [ ] Step 9: `architecture-data-consistency` consulted; `SIGTERM` drain, crash-safety, unhandled-rejection backstops, compensation, readiness, migration rollout checked
- [ ] Step 10: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and Blast-Radius Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode ("add a timeout" vs "untimed `fetch` to SendGrid hangs the handler and pins the event loop")
- Overlapping into perf (throughput / latency tuning) or observability (metric / log wiring) - name the failure-survival gap
- Recommending retries on non-idempotent POSTs without an `Idempotency-Key`
- Recommending a circuit breaker with no monitoring
- Treating BullMQ `attempts` as a substitute for consumer idempotency
- Approving `queue.add` / `stripe.charge` / `mailer.send` inside `$transaction` / `dataSource.transaction`
- Approving `Promise.all` fan-out where one optional failure must not fail the batch (use `allSettled`), or an unbounded `Promise.all` over a large array (bound with `p-limit`)
- Approving sync `fs.readFileSync` / `crypto.pbkdf2Sync` on request paths, or `setTimeout(..., 0)` as a way to "free" the event loop
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
