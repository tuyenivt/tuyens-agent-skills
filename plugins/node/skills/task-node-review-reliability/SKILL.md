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

**Not for:** general Node review (`task-node-review`), throughput / latency tuning (`task-node-review-perf`), telemetry wiring (`task-node-review-observability`), security (`task-node-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns *fast under normal load* (N+1, pool sizing for throughput, tail-latency contagion from a slow upstream where p99 = max(your work, upstream p99)). This lens owns *survival when that upstream hangs or dies*: the `AbortSignal.timeout` existing so the call cannot hang forever, and the breaker / fallback when it trips. Pool: perf sizes it; this lens verifies it is bounded and that exhaustion sheds rather than blocks. If the fix is "make it faster," it's perf; if the fix is "survive it being slow or down," it's reliability.
- **vs. Observability:** obs owns the breaker-state metric and the fallback log line; this lens owns the breaker and the fallback *existing and being configured*. Report the mechanism gap here, the visibility gap in obs.
- **vs. umbrella Phase B:** the umbrella's Phase B owns happy-path correctness and transaction-boundary correctness; this lens owns partial failure, dependency failure, and saturation. Idempotency (HTTP `Idempotency-Key`, BullMQ `jobId`) sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                              | Steps Run                                 |
| ---------- | ------------------------------------------------- | ----------------------------------------- |
| `standard` | Default                                           | All except the Failure-Mode Map           |
| `deep`     | Requested, handed down by `task-node-review`, or any whole-service sweep | All + `Failure-Mode and Blast-Radius Map` |

At `deep`, trace each new or changed dependency's failure path across service boundaries and shared resources (the DB pool, Redis, the event loop, BullMQ workers) and name the loop-breaker.

Invocation forms (`/task-node-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`) follow `task-code-review-reliability`. When invoked as a subagent, the parent passes the pre-confirmed stack, the precondition handle, and pre-read diff and commit log; Steps 2-3 consume those instead of re-running.

**Whole-service sweep.** Enter this path only when Step 3 fails fast on trunk **and** the invocation asked for a sweep (resilience-debt pass, pre-freeze audit, post-incident hardening) or named a path - being on the wrong branch by accident is not a sweep request, and there the fail-fast stands. On the sweep path:

- Scope is the service's own source root (`src/`, plus `prisma/` / `data-source.ts` / deployment config), or the path the invocation named. Not a monorepo's every package.
- Step 4's categories are read in full rather than per changed file, and every "diff"-worded row below reads as "the in-scope code".
- Findings cite current code at `HEAD`. Verification is inline (Step 9's carve-out), not `review-finding-verify`.
- Writer fields come from the repo, not from a handle: `branch` = current branch short name, `base_ref` = `head_ref` = that same name, `base_sha` = `head_sha` = `git rev-parse HEAD`, `round` from the re-review gate as usual. The Summary's `Target:` names the swept scope.
- Every finding's Location carries `_(pre-existing)_` - on a sweep that is the expected provenance, not a de-escalation trigger.
- Print `Head is trunk - running a repo-wide reliability sweep at HEAD; findings cite current code.` in place of the precondition stop message.
- Seam deferrals (`-> task-node-review-observability`, `-> task-node-review-perf`) have no umbrella to receive them: keep the finding here and tag its Next Step `[Delegate]` with the owning lens named.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Framework

Accept a pre-confirmed stack from a parent (`task-node-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Node, stop and route the user to `/task-code-review-reliability`. Detect `Framework` (NestJS via `nest-cli.json` / `@nestjs/*`; Express otherwise) and `ORM` (Prisma via `schema.prisma`; TypeORM via `data-source.ts`) from evidence - later steps branch on both.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Once the handle is emitted, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim and stop - **except** a trunk fail-fast on a sweep invocation, which routes to the Whole-service sweep above. No state-changing git.

**Re-review gate (standalone only - a subagent owns no report and skips this).** Check for the prior report yourself: `review-reliability-<branch>.md`, with `branch` sanitized the way the writer sanitizes it (`/` and any character outside `[A-Za-z0-9_-]` becomes `-`, so `feature/payouts` is `review-reliability-feature-payouts.md`). The handle's `prior_checkpoint` points at `review-<branch>.md`, a different report - do not chain off it. When the file exists with valid frontmatter, its `head_sha` equals the current head, and the requested depth does not exceed its `depth`, print `No new commits on <branch> since prior reliability review at <sha_short>. Prior report unchanged.` and stop without writing. Otherwise `round` = prior + 1 (Step 10 carries it).

### Step 4 - Read the Reliability Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a small diff ripples: a new service method calling an unchanged untimed client is a new failure path at the call site):

- Outbound clients: `axios.create` / `undici.Pool` / `got.extend` / bare `fetch` callsites and per-vendor wrappers - `AbortSignal.timeout`, breaker, retry
- Service methods composing multiple downstream calls (`Promise.all` / `Promise.allSettled`, fan-out loops) - timeout budget, partial-failure handling
- BullMQ producers (`queue.add`) and `@Processor` / `Worker` classes - `attempts` / `backoff`, DLQ, `jobId`, `stalledInterval` / `lockDuration`, worker `concurrency`, idempotency
- Scheduled work: `@nestjs/schedule` `@Cron` / `@Interval`, `setInterval` - overlap guards, failure isolation
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox
- Config and lifecycle: `main.ts` (`enableShutdownHooks`, `SIGTERM`), `prisma.service.ts` / `data-source.ts` pool config, `ConfigModule`, resilience wiring (`opossum` / `cockatiel` / `p-retry` / `p-limit`), and `package.json` dependency adds

Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns and the Node resilience library - load it when the surface above includes an external client, a fanning-out service, or breaker / retry / timeout config. Skip it on a diff that is purely BullMQ-idempotency, transaction, or locking work with no synchronous dependency - the later steps carry their own atomics.

**Gating skips atomic loads, never checklist rows.** Every checklist row below runs on this skill's own text regardless of which atomics loaded; a row goes N/A only when the diff has no matching surface (the Self-Check rule). Also read the full `package.json` here (not just diff adds) to fill the Summary's `Resilience Libraries:` field - as a subagent, read it from the repo; the parent passes a diff, not the manifest.

### Step 5 - Timeouts, Retries, Circuit Breakers, Bounded Concurrency

When the surface has an outbound call, use skill: `node-http-client-patterns` for the timeout / retry / idempotency / wrapper contract and flag deviations. With no outbound surface, mark these rows N/A rather than loading the atomic.

- [ ] **Timeout on every outbound call** - `AbortSignal.timeout(ms)` (or `axios` `timeout`, `undici` `headersTimeout` + `bodyTimeout`, `got` `timeout.request`). Node `fetch` and `axios` set no timeout by default, and undici's ~300s `headersTimeout` backstop never bounds the body phase - so a missing explicit timeout is an unbounded hang, not a slow call. Write paths bound with `statement_timeout` (see `node-transaction-patterns`).
- [ ] **Client-initiated cancellation, reads only** - abort outbound work when the inbound request dies via `AbortSignal.any([ac.signal, AbortSignal.timeout(ms)])`, with an `AbortController` aborted on the request `close` event (Express/NestJS `IncomingMessage` has no `.signal`; that property exists only on fetch-style `Request` objects). **GET/HEAD only.** Never wire client cancellation into a non-idempotent write - a disconnect then aborts a charge the server may already have accepted, converting a known outcome into an unknown one. Recommending it on a POST/PATCH is itself a finding.
- [ ] **Timeout budget on chained calls** - a request fanning out to multiple downstreams caps total time; a slow first call leaves budget for the rest or fails fast.
- [ ] **Retries bounded and safe** - a retry policy with capped attempts, exponential backoff, and jitter. Retry only transient errors (5xx, timeouts, `ECONNRESET`); never 4xx; never a non-idempotent POST without an `Idempotency-Key`. Library choice is constrained by module format: `p-retry` (v5+) and `p-limit` (v4+) are ESM-only and a default CommonJS NestJS build cannot `require` them, so recommend `cockatiel`, `opossum`, or `bottleneck` there unless the project is already ESM.
- [ ] **Retry amplification** - chained retries share a per-request budget. In-process retry is seconds (2-3 attempts); waits of minutes-to-hours belong to BullMQ, whose queue owns scheduling - a sync handler cannot sleep 5 minutes.
- [ ] **Circuit breaker per external dependency** - `opossum` (`new CircuitBreaker(fn, { errorThresholdPercentage, resetTimeout })`) or `cockatiel` policy with explicit threshold and half-open probe; state metered (visibility gap -> `task-node-review-observability`). A shared or unmonitored breaker counts as missing.
- [ ] **Bounded concurrency / bulkhead** - there are no OS thread pools to isolate on a single-threaded runtime: bound concurrent in-flight calls per dependency with `p-limit` / `bottleneck` (or `cockatiel` bulkhead), and route independent workloads to separate BullMQ queues so one slow dependency cannot starve the others.

### Step 6 - Idempotency and Delivery Semantics

Use skill: `backend-transaction-patterns` (the boundary contract and its severity taxonomy) then `node-transaction-patterns` (the Node/ORM bindings) - the Node atomic states it is not self-contained. Use skill: `node-bullmq-patterns` and `backend-idempotency` for key strategy and atomic dedup.

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

- [ ] **DB pool bounded and failing fast** - the per-process pool is set, not left at its default: Prisma `connection_limit` in the URL (unset means `num_physical_cpus * 2 + 1` read from the **host**, not the container's cgroup); TypeORM `extra.max` (unset means node-`pg`'s flat `10`). Exhaustion must error rather than block: Prisma `pool_timeout` (seconds, in the URL) and TypeORM `extra.connectionTimeoutMillis` - node-`pg` defaults it to `0`, which waits forever. `idleTimeoutMillis` reaps idle node-`pg` connections; Prisma has no equivalent knob, so do not prescribe one. Worker `concurrency` <= pool size (see `node-connection-pool-sizing`). When a ceiling (DB `max_connections`, deployed concurrency) is not in scope, read the repo config for it; still unknown -> run the check anyway and state the assumption in the finding (`verify: max_connections unknown`) - never silently skip it.
- [ ] **No unbounded `Promise.all`** - fanning `Promise.all` over a user-sized or large array opens N connections / sockets at once; bound it with `p-limit`. (Distinct from Step 7's `allSettled` fail-all point - here the hazard is unbounded width.)
- [ ] **No event-loop blocking on request paths** - `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, catastrophic regex stall *every in-flight request on the process*; offload to `worker_threads` (`piscina`) or BullMQ. Presence is the reliability finding; tuning depth -> `task-node-review-perf`.
- [ ] **No unbounded accumulation** - in-memory `Map` / `Set` / cache / buffer that grows with load has a bound or eviction (`lru-cache`); streamed, not fully buffered, for large data.
- [ ] **Scheduled overlap** - a long `@Cron` / `setInterval` job guards against overlapping runs (a running-flag, distributed lock, or `@Interval` sized to worst-case runtime) so a slow run does not stack.

### Step 9 - Recoverability and Consistency Under Failure

`node-transaction-patterns` (already loaded in Step 6 - reuse it) carries the boundary-correctness rules. Cross-aggregate consistency rule (inlined on purpose - do not re-delegate this to a separate consistency atomic; it overlaps the transaction atomic already loaded here, and its one distinct rule is captured below): writes that cannot share one transaction (a charge + a separate provisioning record, a local write + a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; when impossible, make the second step idempotent and retriable so a re-run converges.

- [ ] **Graceful shutdown drains in-flight** - on `SIGTERM`: stop accepting (`app.close()` / `server.close()`), await in-flight, `await worker.close()`, `await prisma.$disconnect()` / `dataSource.destroy()`. NestJS wires this via `app.enableShutdownHooks()` + `OnApplicationShutdown`. Absence drops in-flight HTTP requests and re-queues in-flight jobs on **every deploy**.
- [ ] **Crash-safety** - a multi-step side effect interrupted mid-way leaves recoverable state (outbox pending, safe re-run), not a half-applied change.
- [ ] **No unhandled-rejection crash surface** - fire-and-forget async (`void doThing()` with no `.catch`, floating promises) becomes an `unhandledRejection`; `process.on('unhandledRejection')` / `'uncaughtException')` are registered once as log-and-exit backstops (see `node-exception-handling`), not control flow.
- [ ] **Compensation** - cross-aggregate or cross-service writes that cannot be one transaction have a compensating action on partial failure.
- [ ] **Readiness reflects dependencies** - `/ready` gates on own-pod DB pool + Redis + BullMQ so an unready instance sheds rather than accepts traffic it cannot serve (probe-wiring depth -> `task-node-review-observability`); NestJS `@nestjs/terminus`.
- [ ] **Migration rollout safety** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes (use skill: `node-migration-safety`, `ops-backward-compatibility`).

**One construct, one finding.** A single construct carrying several defects (a retry that is both unbackedoff and non-idempotent; a service method that dual-writes *and* has no timeout budget) publishes once at the worst severity. Name every defect in its Issue line and give each its own numbered item under `Fix:`; do not inflate the count by splitting, and do not drop the lesser defects to fit one line.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary.

Two carve-outs: subagent runs skip it (the parent verifies the merged set once), and whole-service sweeps skip it (with no diff, every finding attributes as `Pre-existing` and every `[Must]` would de-escalate - the inversion a debt sweep exists to prevent). Sweeps verify inline against the code read in Step 4 and report `Findings verified: inline (no diff)`.

### Step 10 - Write Report

**Subagent mode:** if invoked by `task-node-review`, do not write a file - `review-report-writer` is invoked only by the workflow that owns the report. Return exactly four things, and this list supersedes any generic "return your Output Format" instruction in the parent's prompt:

1. The findings, each as the full block below - `Location` (with any `_(pre-existing)_` or `(unverified: <reason>)` annotation), `Issue`, `Failure Mode`, `Blast Radius`, `Assumption` where one applies, `Fix` - carrying its `[Must]` / `[Recommend]` label. In subagent mode you may annotate `(unverified: <reason>)` on your own judgement: a bootstrap file the diff never reaches is the normal case, and silence about it is worse than the annotation
2. `## Next Steps`, tagged and ordered, for the parent to re-sort into its own
3. `## Recommendations`, plus the `Resilience Libraries:` value as one of its bullets (the parent's Summary has no field for it)
4. At `deep`, the Failure-Mode and Blast-Radius Map, which the parent preserves as its own section

Omit the Summary block - the parent owns it, and the counts in it are the parent's after merging. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-reliability` and every field it marks required:

- `report_body` (the assembled Markdown), `branch`, `base_ref`, `head_ref` - from the precondition handle, or from the repo on a sweep (see Whole-service sweep)
- `base_sha` / `head_sha` via `git rev-parse` on those refs
- `scope: +rel`, `depth` as invoked, `stack = node-typescript`, `mode: full`
- `round` from Step 3's re-review gate, plus `prior_head_sha` from the prior report's frontmatter when round > 1 (check for `review-reliability-<branch>.md` yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report)

Write to the report file, then print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (missing timeout on a hot outbound call, uncapped retry, non-idempotent POST retry, in-tx dual write, unbounded `Promise.all` on a hot path, event-loop blocking in a request path, no graceful shutdown dropping in-flight work on deploy); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, missing timeout / retry budget on a chained path, consumer not idempotent, unbounded in-memory accumulation); Low = hardening with no immediate failure path (missing `p-limit` bulkhead, fail-fast where cached data would serve). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`. Unbounded growth is High when it reaches OOM under normal traffic, Medium when it is bounded by a bounded input.

**Envelope precedence.** Every atomic this workflow loads - `ops-resiliency`, `node-http-client-patterns`, `backend-transaction-patterns`, `node-transaction-patterns`, `backend-idempotency`, `node-bullmq-patterns`, `node-connection-pool-sizing` (and through it `backend-connection-pooling`), `node-migration-safety` - defines its own assessment envelope and its own severity scale, several of them declaring the envelope unconditional. This workflow's template supersedes all of them: fold their content into the finding blocks below under this skill's severity scale, and append none of their envelopes as separate sections.

```markdown
## Node.js Reliability Review Summary

- **Stack Detected:** Node.js <version> / TypeScript <version>
- **Framework:** NestJS <version> | Express <version> | mixed
- **ORM:** Prisma <version> | TypeORM <version>
- **Resilience Libraries:** [every one present, by role: breaker / retry / limiter, each marked `(in use)` or `(declared, unused)` - a dependency in `package.json` that nothing imports is the most decision-relevant state this field reports. Write `none` per empty role, e.g. `breaker: none; retry: p-retry@6 (declared, unused); limiter: bottleneck@2 (in use)`]
- **Target:** <base_ref>...<head_ref>, or the swept scope at `HEAD` on a sweep
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff)   _(omit the parenthetical when K is 0; sweeps: `inline (no diff)`)_
- **Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **[Must]** **Location:** [file:line - annotate `_(pre-existing)_`, `_(pre-existing; newly reachable via <file>)_`, or `(unverified: <reason>)` when the verify pass or a sweep returned one]

   **Issue:** [name the gap: `fetch` with no `AbortSignal.timeout`, uncapped `p-retry`, `queue.add` inside `$transaction`, unbounded `Promise.all`, non-idempotent processor, no `SIGTERM` drain, etc.]

   **Failure Mode:** [what fails and how: "SendGrid latency spike leaves the `fetch` hanging with no timeout; the request never resolves and the event loop accrues pending sockets"]

   **Blast Radius:** [what else is affected: "every route sharing the process degrades; the DB pool holds connections behind the stalled handlers"]

   **Assumption:** [any input you could not read, e.g. `verify: max_connections unknown`] _(omit when there is none)_

   **Fix:** [`AbortSignal.timeout(5_000)` + `opossum` breaker + fallback, transactional outbox, `p-limit`, `worker.close()` on `SIGTERM`, etc. Several fixes on one construct become a numbered list here.]

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

Every finding carries exactly one label: `[Must]` or `[Recommend]`. No other label is written.

**Merging into `task-node-review`.** The parent's finding block is `Issue / Impact / System Risk / Fix`. `Failure Mode` maps to `Impact`; `Blast Radius` maps to `System Risk` - it is per-finding free text and is not the parent Summary's `Blast Radius` enum (`Narrow | Moderate | Wide | Critical`), which stays the parent's. A finding spanning two files cites the one where the fix lands and names the other in `Blast Radius`.

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no messaging, no scheduled jobs).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Node / TypeScript (or pre-confirmed stack accepted from parent); framework + ORM recorded
- [ ] Step 3: precondition check ran (or handle received); re-review gate applied; a trunk fail-fast either stopped the run or routed to a requested sweep; diff + log read once
- [ ] Step 4: outbound clients, composing services, BullMQ, scheduled jobs, side-effecting flows, config/lifecycle read; full `package.json` read for the Resilience Library field; `ops-resiliency` consulted when a synchronous-dependency surface is present (skipped on idempotency/transaction/locking-only diffs)
- [ ] Step 5: `node-http-client-patterns` consulted; `AbortSignal` timeouts, retry safety/budget, breaker, bounded concurrency checked
- [ ] Step 6: `backend-transaction-patterns` loaded before `node-transaction-patterns`; `backend-idempotency` + `node-bullmq-patterns` consulted; idempotency keys, BullMQ attempts/DLQ/`jobId`, no in-tx dual write, consumer idempotency checked
- [ ] Step 7: fallback per critical dependency; `allSettled` on optional fan-out; fallbacks log; partial responses; load shedding / backpressure verified
- [ ] Step 8: DB pool bounded; no unbounded `Promise.all`; no event-loop blocking; no unbounded accumulation; scheduled overlap guarded
- [ ] Step 9: cross-aggregate compensation rule applied; `SIGTERM` drain, crash-safety, unhandled-rejection backstops, compensation, readiness, migration rollout checked
- [ ] Step 9: `review-finding-verify` ran and its tally reached the Summary - or a documented carve-out applied (subagent, or sweep reporting `inline (no diff)`)
- [ ] Step 10: standalone: every required writer field assembled, report written, confirmation printed; subagent: labelled findings + Next Steps + Recommendations (carrying `Resilience Libraries:`) + the deep map returned, no file written
- [ ] Every finding names the failure mode and blast radius, never just the missing pattern; one construct publishes one finding
- [ ] Depth honored: `standard` ran all; `deep` and every sweep filled the Failure-Mode and Blast-Radius Map
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
- Recommending client-cancellation propagation (`req.signal`) on a POST/PATCH - it makes an accepted write's outcome unknown
- Prescribing node-`pg` pool knobs (`idleTimeoutMillis`) on a Prisma project, or `pool_timeout` on a TypeORM one
- Entering the whole-service sweep because the user was on trunk by accident rather than because a sweep was asked for
