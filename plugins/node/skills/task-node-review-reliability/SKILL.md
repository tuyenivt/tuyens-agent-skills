---
name: task-node-review-reliability
description: "Node.js reliability review: AbortSignal deadlines, breakers, retries, BullMQ idempotency, bounded concurrency, graceful shutdown."
agent: node-reliability-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, reliability, resilience, circuit-breaker, idempotency, bullmq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Reliability Review

Node.js-aware reliability review naming `AbortSignal.timeout`, `opossum` / `cockatiel`, `p-limit` / `bottleneck`, BullMQ `attempts` / failed set / `jobId`, the Prisma / TypeORM pool, and `SIGTERM` draining directly. Reliability = behavior under failure and saturation: a dependency slow or down, a load spike, a process killed mid-flight. On one event loop, one unbounded wait or one blocked tick stalls every in-flight request, so the bar is bounded, contained, and recoverable. Stack-specific delegate of `task-code-review-reliability`.

## When to Use

- NestJS or Express PR adding or changing an integration point (outbound client, BullMQ processor, `@Cron` / scheduled job)
- Pre-merge pass on side-effecting flows (payments, notifications, provisioning) for idempotency and delivery semantics
- Hardening after a near-miss; a resilience-debt sweep (whole-service sweep, below)

**Not for:** general review (`task-node-review`), throughput / latency tuning (`task-node-review-perf`), telemetry wiring (`task-node-review-observability`), security (`task-node-review-security`).

## Seam With Adjacent Lenses

- **Perf** owns *fast under normal load* (N+1, pool sizing for throughput, tail latency). This lens owns *survival when an upstream hangs or dies*: the deadline that stops the hang, the breaker and fallback when it trips, and a pool that sheds rather than blocks when exhausted.
- **Observability** owns dashboards and alert wiring. A breaker's state hook and a fallback's `warn` log line are part of the mechanism and belong here.
- **Umbrella core** owns happy-path correctness; this lens owns partial failure, dependency failure, and saturation - including dual writes and transaction bounds. Idempotency sits at the seam - the umbrella's merge dedups.

## Depth

| Depth | When | Runs |
| ----- | ---- | ---- |
| `standard` | Default | Steps 1-11 |
| `deep` | Requested, or handed down by `task-node-review` | Steps 1-11 + `## Failure-Mode and Blast-Radius Map` |

`deep` renders Step 9's failure-propagation paths as the Map.

## Invocation

`/task-node-review-reliability [<branch> | pr-<N>] [--base <branch>] [standard | deep] [sweep]`

Defaults to the current branch vs its base; fails fast on trunk. As a subagent of `task-node-review`, Step 3 is pre-satisfied and Step 11 takes its subagent branch.

**Whole-service sweep** - decided before Step 3: the invocation says `sweep`, or the request asks for a resilience-debt pass, pre-freeze audit, or post-incident hardening with no PR. A bare invocation on trunk is not a sweep - Step 3 runs and fails fast. On the sweep:

- Scope is the paths the request named - plus the code they call into and the lifecycle and config files that govern them (the bootstrap file, `SIGTERM` handling, the `DataSource` / Prisma client, deployment config) - or the service's source root when none is named.
- Steps 4-10 read the in-scope code in full; every "diff" wording reads "in scope". Findings cite current code at `HEAD` via `git show HEAD:<path>`, each Location carrying `_(pre-existing)_` - the expected provenance, not a de-escalation.
- Depth is as invoked; on a sweep, "new or changed dependency" reads "each external dependency and shared resource in scope". No precondition check, no round gate, no writer: print `Running a reliability sweep at HEAD (<branch>); findings cite current code.`, verify inline (Step 10), and emit the report body as the response. Summary `Target:` names the scope.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`; accept a pre-confirmed stack from a parent. Not Node -> stop and route to `/task-code-review-reliability`. Record from evidence: `Framework` (NestJS, Express, `mixed`, or `other` - the Express rows at its equivalent sites); `ORM` (Prisma with its major - Prisma 7 / `@prisma/adapter-*` pools through the adapter; TypeORM with its driver, `pg` or `mysql2`; both, each on its own files; or `other` / `none`); and the module format (ESM `"type": "module"` or CJS). A stack fact that conflicts across files (`.nvmrc` vs `engines`) goes in Notes.

### Step 3 - Resolve the Diff (standalone only)

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-reliability`. A fail-fast surfaces verbatim and stops. A sweep is decided from the invocation before this step and never runs it, so a precondition failure never routes there.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading anything else: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` covers the resolved one (`deep` covers `standard`) -> print `No new commits on <head_short_name> since prior reliability review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `head_sha`) and stop. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 11 write overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then read once: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log --oneline <base_ref>..<head_ref>`. Every file outside the diff is read with `git show <head_ref>:<path>`.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into (a new call to an unchanged, untimed client is a new failure path at the call site):

- Outbound clients (`fetch`, `undici`, `axios`, `got`, vendor SDKs) and their wrappers - deadline, retry, breaker
- Services composing several downstream calls (`Promise.all` / `allSettled`, fan-out loops) - budget, partial failure
- BullMQ producers and processors - `attempts` / `backoff`, `jobId`, retention, `concurrency`, idempotency
- Scheduled work - `@Cron` / `@Interval`, `setInterval`, BullMQ job schedulers
- Side-effecting flows (payment, notification, provisioning) - idempotency keys, outbox, call-then-record
- Lifecycle and config - `main.ts` / `index.ts` (`enableShutdownHooks`, `SIGTERM`), the pool config, and the full `package.json` via `git show <head_ref>:package.json` (sweep: `HEAD`) for `Resilience Libraries:`

Use skill: `ops-resiliency` when the surface has any outbound call - synchronous, scheduled, or in a job - or breaker / retry / timeout config. A diff that is purely idempotency, transaction, or locking work skips it; later steps carry their own atomics. **Gating skips atomic loads, never checklist rows:** a row goes N/A only when the in-scope code has no matching surface.

### Step 5 - Deadlines, Retries, Breakers, Bounded Concurrency

Use skill: `node-http-client-patterns` when the surface has an outbound call; each row still runs against its own surface.

- [ ] **A total deadline on every outbound call** - `AbortSignal.timeout(ms)` on `fetch` / `undici.request` / axios `signal`, or `got` `timeout.request`. axios `timeout` and undici `headersTimeout` / `bodyTimeout` (300 s) are idle timers: a body trickled one chunk at a time never trips them; a vendor SDK with no `signal` option takes its own `timeout` client option. A missing total deadline is an unbounded hang
- [ ] **Client-disconnect cancellation, reads only** - abort downstream work when the client leaves via `AbortSignal.any([ac.signal, AbortSignal.timeout(ms)])` (Node 20.3+), with `res.on('close', () => { if (!res.writableFinished) ac.abort(); })` - the request's own `close` fires once its body is consumed, not on disconnect. GET / HEAD only: wiring cancellation into a non-idempotent write turns an accepted charge into an unknown outcome, and recommending it on a POST / PATCH is itself a finding
- [ ] **Budget on chained calls** - a request fanning out to several downstreams caps total time; a slow first call leaves budget for the rest or fails fast
- [ ] **Retries bounded and safe** - capped attempts, exponential backoff with jitter, `Retry-After` honored. Retry 408 / 425 / 429 (and a 409 carrying `Retry-After`), 500 / 502 / 503 / 504, timeouts, and transport errors (`ECONNRESET`); no other status. A non-idempotent POST retries only with an `Idempotency-Key`, or for a failure proven to precede acceptance. `p-retry` (v5+) and `p-limit` (v4+) are ESM-only - a CJS build loads them through `await import()` (a TypeScript build needs `module: node16` / `nodenext`, since `commonjs` rewrites it to `require`) or Node 20.19+ / 22.12+ `require(esm)`; `cockatiel` (retry, breaker, bulkhead) is the CJS-friendly choice. `opossum` is a breaker with timeout and fallback - it has no retry
- [ ] **Retry amplification** - chained retries share one per-request budget; in-process retry is seconds (2-3 attempts), and waits of minutes belong to BullMQ, which owns scheduling
- [ ] **Breaker per external dependency** - `opossum` (`errorThresholdPercentage`, `resetTimeout`) or a `cockatiel` policy with a half-open probe; its state change hooked (`breaker.on('open', ...)` / `onBreak`). A breaker shared across dependencies, or with no state hook, counts as missing
- [ ] **Bounded concurrency per dependency** - `p-limit` / `bottleneck` / a `cockatiel` bulkhead; independent workloads on separate BullMQ queues so one slow dependency cannot starve the rest. The libuv threadpool is shared, so saturating it (`fs`, `dns.lookup`, `crypto.pbkdf2`, `zlib`) starves unrelated work

### Step 6 - Idempotency and Delivery Semantics

Use skill: `backend-transaction-patterns`, then `node-transaction-patterns`; Use skill: `node-bullmq-patterns` and `backend-idempotency`.

- [ ] **Idempotency keys** on money / notification / provisioning side effects - an HTTP `Idempotency-Key`, required on financial endpoints, claimed atomically in the database (unique constraint and a conditional insert, `processing` then `completed` with the stored response), never read-then-write; a vendor call carries the vendor's idempotency key when it offers one (a Redis claim only for a keyless vendor call)
- [ ] **BullMQ delivery** - `attempts` + `backoff: { type: 'exponential', delay }` in the queue's `defaultJobOptions` (unset `attempts` means one try); permanent failures throw `UnrecoverableError`; a stable `jobId` (no `:`) dedupes only while the job is retained, so `removeOnComplete` / `removeOnFail` ages outlive the duplicate window, and the bounded failed set is the visible dead letter
- [ ] **Stall model** - a worker renews its lock on a timer, so a long non-blocking job is safe; a CPU-bound handler that blocks the loop past `lockDuration` stops renewal, and the job re-runs concurrently with the original (up to `maxStalledCount`). Fix: a sandboxed processor or a raised `lockDuration`; the idempotent side effect is what makes a stall safe
- [ ] **Consumer idempotency** - the side effect itself is idempotent (a unique key, the vendor's idempotency key, a conditional update guarded on the prior state); an early-return status read is an optimization, not the guard - two concurrent runs both pass it
- [ ] **No in-transaction dual write** - `queue.add`, a payment call, or `mailer.send` inside `$transaction` / `dataSource.transaction` can roll back the row while the effect survives (charged, no order), holds a pooled connection across the network call, or lets a worker read before `COMMIT`. Post-commit dispatch for best-effort effects; an outbox for at-least-once delivery; call-then-record (a pending row, the call outside any transaction, then the result recorded) for a charge whose result is written back
- [ ] **Write transactions bounded** - `SET LOCAL lock_timeout` / `statement_timeout` inside the transaction (Prisma: plus `maxWait` / `timeout`, which does not cancel a statement blocked on a lock; TypeORM: plus `idle_in_transaction_session_timeout`); a plain `SET` leaks to the next borrower of the pooled connection

### Step 7 - Degradation and Fallbacks

- [ ] **Fallback per critical dependency** - `opossum` `.fallback(...)` / a `cockatiel` fallback returning cached, default, or partial data, or an explicit fast 503 - never an unbounded wait
- [ ] **`Promise.allSettled` for optional fan-out** - `Promise.all` rejects the batch on the first failure
- [ ] **Fallbacks log the original failure** at `warn` with context (`node-exception-handling`); no silent swallow
- [ ] **Partial responses** - an optional downstream (recommendations, enrichment) failing degrades the response, not the request
- [ ] **Load shedding and backpressure** - saturation returns 429 / 503 rather than queueing unboundedly; large payloads stream via `stream.pipeline`; a request wall-clock cap (a custom RxJS `timeout()` interceptor on NestJS) is paired with an `AbortSignal` on reads, while a write's downstream call keeps its own deadline and completes or reconciles

### Step 8 - Resource Exhaustion

- [ ] **Pool bounded and failing fast** - Use skill: `node-connection-pool-sizing`. Prisma 5-6: `connection_limit` and `pool_timeout` in the URL (unset `connection_limit` is `num_physical_cpus * 2 + 1` of the **host**, not the container). Prisma 7 / driver adapter: the adapter's `max` and `connectionTimeoutMillis` (URL pool params are read by nothing). TypeORM on node-`pg`: `extra.max` (else `poolSize`, else 10) and `extra.connectionTimeoutMillis` - node-`pg` defaults it to `0`, which waits forever; mysql2: `connectionLimit` (default 10) - acquisition waits unbounded (`queueLimit: 0`), so cap the queue or bound the call. Summed worker `concurrency` per process (x fan-out) + 2 <= the pool. A ceiling not in scope (`max_connections`, replica count) is read from repo config; still unknown -> run the check and state it in `Assumption:` (`verify: max_connections unknown`)
- [ ] **No unbounded `Promise.all`** over a user-sized or large array - it opens N sockets or queues N pool requests at once; bound it (`p-limit`)
- [ ] **No event-loop blocking on request or job paths** - `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse`, catastrophic regex stall every in-flight request; presence is the reliability finding, tuning depth belongs to perf
- [ ] **No unbounded accumulation** - an in-memory `Map` / `Set` / cache / buffer growing with load has a bound or eviction (`lru-cache`)
- [ ] **Scheduled overlap** - every replica runs `@Cron` / `@Interval` / `setInterval`, so a multi-replica job needs a distributed lock or a BullMQ job scheduler (`upsertJobScheduler`, BullMQ 5.16+); in-process overlap needs a running flag, since `setInterval` never awaits an async handler

### Step 9 - Recoverability

When the change adds or changes a dependency, or couples to a shared resource (the DB pool, Redis, the event loop, BullMQ workers), Use skill: `failure-propagation-analysis` (what-if mode) at any depth, keeping its `(assumed)` / `predicted` markers; its paths feed each finding's Failure Mode and Blast Radius, and at `deep` the Map.

Cross-aggregate consistency (inlined; `node-transaction-patterns` carries the boundary rules): writes that cannot share one transaction (a charge and a provisioning record, a local write and a remote call) need a compensating action or a reconciliation job on partial failure - never a best-effort inline rollback that can itself fail. Prefer one transaction; otherwise make the second step idempotent and retriable so a re-run converges.

- [ ] **Graceful shutdown drains in-flight work** - on `SIGTERM`: stop accepting (`app.close()` / `server.close()`), await in-flight requests, `await worker.close()`, `await prisma.$disconnect()` / `dataSource.destroy()`. NestJS needs `app.enableShutdownHooks()` for any of it to run; without a drain, every deploy drops in-flight requests and re-queues in-flight jobs
- [ ] **Crash safety** - a multi-step side effect interrupted mid-way leaves recoverable state (a pending row a sweeper resolves, an outbox row), not a half-applied change
- [ ] **No unhandled-rejection surface** - fire-and-forget async (`void run()` with no `.catch`, a `setInterval` callback returning a promise) becomes an `unhandledRejection`; `process.on('unhandledRejection')` / `process.on('uncaughtException')` are registered once as log-and-exit backstops (Use skill: `node-exception-handling`)
- [ ] **Readiness reflects own-pod dependencies** - `/ready` gates on this pod's pool, Redis, and queue connection; never a third-party ping (probe depth belongs to observability)
- [ ] **Migration rollout** - write-path migrations are expand-then-contract so a rollback does not corrupt in-flight writes; a write-blocking lock on a large table and a migration runner that races across replicas are High (Use skill: `node-migration-safety` and `ops-backward-compatibility` when a migration is in scope)

### Step 10 - Verify and Reconcile

**One construct, one finding.** Defects removed by one fix are one finding at the worst tier - every defect named in its Issue, each with its own numbered item under `Fix:`; defects needing different fixes stay separate, even in one file. A root cause shared by several call sites files once where the fix lands (one backstop, one config), naming the other sites in its Location. **A defect this lens does not own is reported, never dropped:** one `- **out of lens:** file:line - <the defect, and the workflow that owns it>` line per defect, at the end of `## Findings`, for a defect outside this lens that would break the build, corrupt, lose, or expose data, or block legitimate traffic (anything else is left to `task-node-review`), untiered and uncounted.

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying the `Label` and `Annotation` columns, and fill `Findings verified:` in the atomic's Summary form. Subagent runs skip verification - the parent verifies the merged set. A sweep skips it too (with no diff every finding attributes as pre-existing and every `[Must]` would de-escalate): re-read each cited `file:line` at `HEAD`, drop what the code contradicts, mark what cannot be settled in-tree `_(unverified: <reason>)_`, and report `Findings verified: inline (no diff)`.

**Round 2+ (standalone, after verification).** Project the prior report at the handle's `report_path` into reconcile's parse shape: one `## High-Impact Findings` section, and per prior finding (every tier) a `### [<Label>] <file:line>` heading - the label from its bold `[Must]` / `[Recommend]` token (a prior report with none: the label its tier maps to), the `file:line` prefix of its Location, each Location annotation as its own group (`_(pre-existing; newly reachable via ...)_` split into `_(pre-existing)_ _(newly reachable via ...)_`), a prior `_(carried from round <N>)_` kept - followed by its Issue line as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files`. Its table, note line, and tally render as `## Prior Round Reconciliation`. A row is re-derived when this round's findings hold one on the same construct with the same smell. A `Still open` or `Needs re-check` row this round re-derived publishes once, at this round's label; one it did not re-derive republishes its prior block verbatim in its prior tier - every field, the Location with all its annotation groups - at its prior label, with `_(carried from round <N>)_` after the label unless the block already carries one (`<N>` = the round it first appeared), outside the verify tally, plus a Next Steps entry suffixed `(open since round <N>)`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` is never carried.

### Step 11 - Write Report

**Subagent mode** (invoked by `task-node-review`): return only `## Findings` with its tier sections, any `out of lens` lines, and as its last line `- **Resilience Libraries:** <value>`, plus - at `deep` - `## Failure-Mode and Blast-Radius Map`. No Summary, Recommendations, Next Steps, or file; the parent owns the report. This supersedes any generic "return your Output Format" in the parent's prompt.

**Sweep:** emit the report body as the response; no writer.

**Standalone:** Use skill: `review-report-writer` with `report_type: review-reliability`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the round gate, `scope: +rel`, `depth` as resolved, `stack = node-typescript`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried one, else `prior_checkpoint.pr_url` when present. Emit the body, then the writer's confirmation line.

## Output Format

Emit `report_body` as raw Markdown; the fence delimits the template for display only, and brace annotations in it are authoring notes, never emitted.

**Severity.** **High** = an unbounded failure path, or data loss / corruption / a financial or irreversible duplicate under a plausible failure (no deadline on an outbound call, uncapped retry, a keyless retried POST whose duplicate is financial or irreversible, an in-transaction dual write, a consumer whose duplicate run charges or provisions twice, unbounded `Promise.all` over a user-sized input, loop blocking on a request or job path, no shutdown drain, unbounded growth that reaches OOM under normal traffic, a financial state left pending with nothing to resolve it). **Medium** = the failure is bounded but recovery or containment is impaired (a breaker missing where a deadline exists, no fallback for a critical dependency, no budget on a chained path, a retry or consumer whose duplicate is a recoverable write, growth bounded by a bounded input, a non-financial state left pending with no sweeper). **Low** = hardening with no immediate failure path (a missing bulkhead, fail-fast where cached data would serve). Summary counts are by tier.

**Labels.** High -> `[Must]`; Medium / Low -> `[Recommend]` - unless the verify pass returned a different `Label`, which wins: a finding sits in its tier's section while its label is the published one. A sweep keeps the tier labels. No other label is written.

**Envelope precedence.** Every atomic this workflow loads (`ops-resiliency`, `node-http-client-patterns`, `backend-transaction-patterns`, `node-transaction-patterns`, `backend-idempotency`, `node-bullmq-patterns`, `node-connection-pool-sizing`, `node-exception-handling`, `node-migration-safety`, `ops-backward-compatibility`, `failure-propagation-analysis`) feeds findings into this template, re-rated on this Severity rubric (an atomic's `[Must]` or `Compatible: No` -> High, `[Recommend]` -> Medium); none of their envelopes is emitted, except `failure-propagation-analysis`'s paths, which fill the deep Map.

```markdown
## Node.js Reliability Review Summary

- **Stack:** Node.js <version> / TypeScript <version> / <NestJS | Express | mixed | other> / <Prisma <major> | TypeORM (<driver>) | both | other | none>
- **Target:** <base_ref>...<head_ref> | <the swept scope at HEAD>
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Resilience Libraries:** <by role, each `(in use)` or `(declared, unused)`, `none` per empty role - e.g. `breaker: none; retry: axios-retry@4 (in use); limiter: none`>
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)} | inline (no diff)
- **Overall:** Resilient | Gaps Found - <n> High / <n> Medium / <n> Low
- **Notes:** <stack conflicts, skipped atomics, scope decisions>   {omit when none}

## Findings

### High Impact

1. **[Must | Recommend]**{ _(carried from round <N>)_} **Location:** <file:line>{ <verify annotation groups>}

   **Issue:** <the gap: `fetch` with no `AbortSignal.timeout`, uncapped retry, `queue.add` inside `$transaction`, unbounded `Promise.all`, a processor with no idempotent side effect, no `SIGTERM` drain>

   **Failure Mode:** <what fails and how: "Northbank latency spike leaves `client.post` waiting on axios's idle timer; the nightly run never finishes">

   **Blast Radius:** <what else is affected: "every job on the worker process; the pool holds connections behind the stalled calls">

   **Assumption:** <an input not read from code - unread (`verify: max_connections unknown`) or taken from docs / `CLAUDE.md` prose>   {only when one applies}

   **Fix:** <`AbortSignal.timeout(5_000)` + `opossum` breaker + fallback, outbox, `p-limit`, `worker.close()` on `SIGTERM`; several fixes on one construct numbered>

### Medium Impact

<same block; numbering continues across tiers>

### Low Impact / Quick Wins

<same>

- **out of lens:** <file:line - defect, owning workflow>   {only when one exists}

{omit empty tiers; when every tier is empty, write `No reliability issues found.`}

## Prior Round Reconciliation   {round 2+ standalone only}

<table, note line, and tally from `review-prior-findings-reconcile`>

## Recommendations

- <structural resilience improvement not tied to a finding>

## Failure-Mode and Blast-Radius Map   {deep only}

<per new or changed dependency: what happens when it is down or slow, the shared resource on the propagation path, and the loop-breaker that contains it>

## Next Steps

1. **[Implement]** [Must] <file:line> - <action>
2. **[Delegate]** [Recommend] [scope: platform] - <action>

{one entry per finding, a carried one suffixed ` (open since round <N>)`, and on standalone and sweep runs a `[Delegate]` per `out of lens` line naming the owning workflow; `[Implement]` for a local fix, `[Delegate]` for cross-cutting, platform, or infra work; ordered Must > Recommend, carryovers first among equals; omit when nothing is actionable}
```

**Merging into `task-node-review`.** The parent maps `Failure Mode` -> `Impact` (plus `(assumes: <Assumption>)`) and `Blast Radius` -> `System Risk`. This per-finding `Blast Radius` is free text, not the parent Summary's `Blast Radius` enum.

## Self-Check

Mark a line N/A when the in-scope code has no matching surface.

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed; `Framework`, `ORM` (major / driver), module format recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-reliability`; round decided from the handle before the diff was read (or the stop line printed); subagent / sweep: step skipped
- [ ] Step 4: surface read, unchanged callees included; `ops-resiliency` loaded when any outbound call is in scope; `package.json` read for Resilience Libraries
- [ ] Step 5: total deadlines, disconnect cancellation (reads only), budgets, retry safety, breakers, bounded concurrency
- [ ] Step 6: transaction atomics in order; keys, BullMQ delivery and retention, stall model, idempotent side effects, dual writes, write-transaction bounds
- [ ] Step 7: fallbacks, `allSettled`, fallback logging, partial responses, shedding
- [ ] Step 8: pool bounded per binding; `Promise.all` width; loop blocking; accumulation; scheduled overlap across replicas
- [ ] Step 9: failure-propagation traced when a dependency or shared resource changed; compensation rule; shutdown drain, crash safety, rejection backstops, readiness, migration rollout
- [ ] Step 10: one construct filed once; verify ran with its tally (or the subagent / sweep carve-out); round 2+ projected and reconciled, unresolved rows carried
- [ ] Step 11: standalone report written with every writer field; subagent: findings (+ Resilience Libraries, + deep Map) returned, no file; sweep: body emitted
- [ ] Every finding names its failure mode and blast radius; `deep` filled the Map

## Avoid

- "Add a timeout" without the failure mode ("untimed `fetch` to Northbank hangs the nightly run")
- Overlapping into perf tuning or telemetry wiring - name the survival gap
- Retrying a non-idempotent POST without an `Idempotency-Key`
- Treating BullMQ `attempts` as a substitute for an idempotent side effect
- Approving `queue.add` / a payment call / `mailer.send` inside `$transaction` / `dataSource.transaction`
- Client-disconnect cancellation on a POST / PATCH
- node-`pg` knobs on a Prisma 5-6 URL, or URL pool params on Prisma 7 or TypeORM
- Deferring a blocking call with `setTimeout(..., 0)` / `setImmediate` - it still blocks when it runs; chunk it or move it to a worker thread
- Entering the sweep because the user was on trunk by accident
