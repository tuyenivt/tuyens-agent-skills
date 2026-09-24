---
name: task-node-review-observability
description: Node.js observability review: pino/winston logs, OpenTelemetry Node SDK, prom-client, BullMQ events, Sentry; identifies telemetry gaps.
agent: node-observability-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, observability, logging, metrics, tracing, opentelemetry, pino, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Node.js Observability Review

Stack-specific delegate of `task-code-review-observability`. Names `pino` / `winston`, the OpenTelemetry Node SDK and its instrumentations, `prom-client`, NestJS lifecycle hooks, BullMQ events and telemetry, and error-tracker SDKs (`@sentry/node`, `@sentry/nestjs`) directly. Library / SDK level only; dashboards, forwarders, and alert rules are out of scope.

## When to Use

- NestJS or Express PR review for observability regressions or new instrumentation gaps
- Pre-release check for a new Node service or major feature
- Post-incident audit when diagnosis was slow or evidence missing (investigation mode, below)

**Not for:** general review (`task-node-review`), known-bottleneck perf (`task-node-review-perf`), infrastructure observability config.

## Depth Levels

| Depth | When | Runs |
| ----- | ---- | ---- |
| `standard` | Default | Steps 1-12, including probe correctness |
| `deep` | Pre-release of a critical service, post-incident, investigation mode | Steps 1-12 + SLI / SLO rows |

Probe correctness (liveness vs readiness vs dependency health) runs at every depth - `task-node-review-reliability` defers probe wiring here.

## Invocation

`/task-node-review-observability [<branch> | pr-<N>] [--base <branch>] [standard | deep]`

Defaults to the current branch vs its base; fails fast on trunk. As the `+Obs` subagent of `task-node-review`, Step 3 is pre-satisfied and Step 12 takes its subagent branch.

**Investigation mode** - decided before Step 3: the request is a post-incident or "diagnosis was slow" audit with no PR. A bare invocation on trunk is not an investigation - Step 3 runs and fails fast. Scope is the paths the request names plus the app's logging, tracing, metrics, and error-tracker setup wherever it lives (bootstrap, modules, filters, processors). Run Steps 4-11 against current code read via `git show HEAD:<path>`; every "diff" wording reads "in scope", and a surface absent from scope states N/A. The run is `deep`. No merge is blocked, so pre-existing gaps file at their full tier. No precondition check, no round gate, no writer: Step 11 verifies inline and the report body is the response. Summary `Target:` names the scope.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`; accept a pre-confirmed stack from a parent. Not Node -> stop and route to `/task-code-review-observability`. Record `Framework` (NestJS, Express, `mixed`, or another server framework - which takes the Express rows at its equivalent sites), `ORM` (Prisma, TypeORM, both, `other` / `none`), `Database` (the TypeORM / raw-driver instrumentation follows it), and the module format (`"type": "module"` or an `.mjs` entry, else CJS - Step 6's preload flag follows it).

### Step 3 - Resolve the Diff (standalone only)

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-observability`. A fail-fast surfaces verbatim and stops. Investigation mode is decided from the invocation before this step and never runs it, so a precondition failure never routes there.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading anything else: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` covers the resolved one (`deep` covers `standard`) -> print `No new commits on <head_short_name> since prior observability review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `head_sha`) and stop. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 12 write overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then read once: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log --oneline <base_ref>..<head_ref>`. Every file outside the diff is read with `git show <head_ref>:<path>`.

### Step 4 - Read the Instrumentation Surface

Open the config so findings cite real lines - NestJS: the logger module (`nestjs-pino`, redaction), `main.ts` / `instrument.ts` / `tracing.ts`, the config schema (`OTEL_*`, log level, Sentry DSN), `package.json`; Express: the logger module, `tracing.ts`, `app.ts` / `index.ts` (middleware order, `/metrics`), `package.json`. Plus every changed file calling a logger, registering a metric, defining an interceptor, or touching trace context.

**Surface verdicts:** one per surface - Logging, OTel SDK, Metrics, BullMQ, Error tracker, Probes - of `wired | partial | absent | n/a`. `n/a` is for a surface the service genuinely has no use for (no queue: BullMQ `n/a`). Use skill: `ops-observability` for the cross-cutting presence baseline; the Node rows below supersede it where they overlap.

**Grouping rule.** A wholly `absent` surface is **one finding** listing the missing pieces by the file or symbol they belong in; per-callsite findings only where a surface exists and is misused. Rate an absent or partial surface by what it costs this service: High when the service is on a critical path (money, auth, or a user-facing write), Medium otherwise.

### Step 5 - Structured Logging

- [ ] **JSON output** in production (`pino`, or `winston.format.json()`); no raw text
- [ ] **Correlation fields** on every line - trace ids (`trace_id` / `span_id` as `instrumentation-pino` / `-winston` write them, or renamed via `logKeys`), a request id, the principal and tenant, business ids. NestJS: `nestjs-pino` with `genReqId`; Express: `pino-http` fed by an `AsyncLocalStorage` request-id middleware. `trace_id` / `span_id` injection comes from `@opentelemetry/instrumentation-pino` / `-winston`
- [ ] **Redaction in the logger** - `pino` `redact: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token']`, or a winston format; class-transformer decorators do nothing for a logger
- [ ] **No entity or request-body logging** - `logger.info(user)` or `{ body: req.body }` serializes every field, leaking PII and secrets; log ids and the fields needed
- [ ] **Identity as structured keys** - `logger.info({ userId }, 'event')`, not `` `user=${userId}` `` (redaction cannot scrub free text)
- [ ] **Levels** - `error` actionable, `warn` recoverable, `info` state transitions, `debug` verbose; `info` default in production
- [ ] **No `console.log`** in production paths; no hot-loop logging without sampling
- [ ] **Errors with cause chain** - `logger.error({ err }, 'msg')` (pino's `err` serializer keeps `cause`), not `err.message`

### Step 6 - OpenTelemetry SDK

- [ ] **Initialized before any other import** - CJS: `node --require ./tracing.js` or the first import in `main.ts`; ESM: `node --import ./tracing.mjs` (with `register()` of the `@opentelemetry/instrumentation/hook.mjs` loader) - `--require` does not patch ESM. An import placed after the app module means nothing already loaded is patched
- [ ] **`NodeSDK` configured** - `serviceName` / `resource`, `traceExporter` or `spanProcessors`, `metricReader` (`metricReaders` on current `sdk-node`), `sampler`, `instrumentations`; it builds the providers itself. `OTEL_SERVICE_NAME` / `OTEL_RESOURCE_ATTRIBUTES` per environment
- [ ] **Sampling explicit** - `new ParentBasedSampler({ root: new TraceIdRatioBasedSampler(rate) })` with `rate` per environment
- [ ] **Instrumentations cover the stack** - `@opentelemetry/auto-instrumentations-node` covers the framework (`instrumentation-nestjs-core`, `-express`), `http`, `undici`, Redis (`-ioredis`, `-redis`), `pg`, `mysql2`, and pino / winston correlation; it never includes `@prisma/instrumentation`, which is registered by hand (Prisma < 6.1 also needs `previewFeatures = ["tracing"]`). TypeORM traces through its driver's instrumentation (`pg` / `mysql2`). Raise **one** finding for whatever the configured set genuinely misses
- [ ] **HTTP clients** - `instrumentation-http` covers `http` / `https` (and axios's default adapter); global `fetch`, `undici.request`, and axios `adapter: 'fetch'` need `instrumentation-undici`
- [ ] **BullMQ** - BullMQ's built-in `telemetry` option (a 5.2x minor onward - check the pinned version) with `bullmq-otel` (`new Queue(name, { connection, telemetry: new BullMQOtel('<service>') })`, and the same on the `Worker`) links producer and job spans; older BullMQ uses a community instrumentation. No package named `@opentelemetry/instrumentation-bullmq` exists
- [ ] **Custom spans** via `tracer.startActiveSpan(...)`, ended in `finally`; no double instrumentation of one call
- [ ] **Resource attributes** - `service.name`, `service.version`, `deployment.environment.name`

### Step 7 - Metrics

- [ ] **Exposed** - `prom-client` with `/metrics` (NestJS `@willsoto/nestjs-prometheus`; Express `register.metrics()` route), or OTel metrics with a Prometheus exporter
- [ ] **Runtime metrics** - `collectDefaultMetrics()` (prom-client: event-loop lag, heap, handles), or `instrumentation-runtime-node` on the OTel path
- [ ] **HTTP server metrics** - a duration histogram labelled by method, route template, and status (`express-prom-bundle` with `includeMethod: true, includePath: true` and path normalization - its `http_request_duration_seconds` `_count` gives the rate - or an interceptor)
- [ ] **Custom metrics** namespaced (`acme_refunds_total`), correct type and suffix (`_total`, `_seconds`, `_bytes`)
- [ ] **Bounded label cardinality** - never `userId` / `orderId` / `requestId`; enums and route templates only
- [ ] **Registered once at module scope** - `new Counter(...)` inside a handler throws a duplicate-registration error on the second call
- [ ] **Multi-process** - Node `cluster`: `AggregatorRegistry` in the primary; PM2 cluster mode: a per-instance metrics port (`base + NODE_APP_INSTANCE`) scraped separately, or a PM2 metrics module
- [ ] **Histogram buckets** match the SLO; finer buckets for sub-100 ms paths

### Step 8 - BullMQ Observability

Use skill: `node-bullmq-patterns` when the diff touches a queue, worker, or scheduler.

- [ ] **Trace propagation** - Step 6's BullMQ row (one finding, not two)
- [ ] **Queue events** - `completed` / `failed` / `stalled` feed counters and duration histograms; `worker.on('error')` for worker-level errors
- [ ] **Exhausted jobs reach the error tracker** - a worker has no exception filter. Capture on the job-failed event when `!job || err.name === 'UnrecoverableError' || job.attemptsMade >= (job.opts.attempts ?? 1)`, skipping errors that map to 4xx (Use skill: `node-exception-handling`) - `@OnWorkerEvent('failed')` under `@nestjs/bullmq`, `worker.on('failed', ...)` on a plain worker
- [ ] **Per-job metrics** - latency histogram, retry / failure counters, a queue-depth gauge (`queue.getJobCounts()` polled)
- [ ] **Logger context in the processor** - `jobId`, job name, and business ids bound for the job's duration (`AsyncLocalStorage` / a child logger)
- [ ] **Scheduled jobs** - a missed run is alerted on a freshness gauge (time since last completion); `stalled` fires only for an active job whose lock stopped renewing, never for a run that never started

### Step 9 - Lifecycle and Async Context

NestJS hook names below; on Express the same checks apply at the equivalent site (the `SIGTERM` handler, the bootstrap file). A row is N/A only when the construct is absent.

- [ ] **Bootstrap span** started in `main.ts` before `NestFactory.create()` and ended after `listen()` - a span opened in `OnApplicationBootstrap` measures nothing
- [ ] **Shutdown flush** - `app.enableShutdownHooks()` in `main.ts` (and in a standalone worker context), without which no shutdown hook runs on `SIGTERM`; `OnApplicationShutdown` calls `await Sentry.close(2000)` and `await sdk.shutdown()` - it runs after `onModuleDestroy` has disconnected Prisma. `@nestjs/bullmq` closes `WorkerHost` workers itself; a plain worker calls `worker.close()`, then flushes, in the `SIGTERM` handler
- [ ] **`AsyncLocalStorage` preserved** - context lost across an `EventEmitter` or pooled-connection callback without `context.bind`, or stashed in a module variable, flagged
- [ ] **`worker_threads`** re-bind trace context from the message; propagation does not cross the thread boundary

### Step 10 - Error Tracking and Probes

The capture contract is `node-exception-handling`'s (Use skill: `node-exception-handling`); flag deviations - double capture, per-handler `try/catch` duplicating the global filter. Another tracker (Honeybadger, Rollbar): the capture-once, PII, and init-before-imports rows apply at its SDK's equivalent; the Sentry-only rows are N/A.

- [ ] **Sentry initialized before imports** (`--import ./instrument.mjs`, the Step 6 ordering rule); DSN, release, and environment from config
- [ ] **One capture path** - NestJS: `SentryModule.forRoot()` plus exactly one of `SentryGlobalFilter` (when the app has no catch-all filter) or the existing global `@Catch()` filter capturing (manually or via `@SentryExceptionCaptured()`), never both. Express: `Sentry.setupExpressErrorHandler(app)` or the terminal error middleware capturing, not both
- [ ] **Default integrations** - `httpIntegration` and the `unhandledRejection` / `uncaughtException` handlers are on by default; the Express / Prisma / Postgres auto-instrumentations join only when `tracesSampleRate` or `tracesSampler` is set
- [ ] **PII** - `sendDefaultPii: false`; `beforeSend` strips sensitive keys; identity set deliberately with `Sentry.setUser({ id })`, an opaque id
- [ ] **One tracer provider** - Sentry v8+ registers its own OpenTelemetry provider on `init()`, and global registration is first-wins: the later SDK's spans go nowhere. Either Sentry owns tracing, or it runs with `skipOpenTelemetrySetup: true` wired into the app's `NodeSDK` (both on the same OpenTelemetry major)
- [ ] **Sample rate explicit** - `tracesSampleRate` per environment, never `1.0` on a high-traffic service
- [ ] **Liveness `/health`** - 200 while the process is responsive; no DB / Redis / third-party ping (a flaky dependency restarts every replica)
- [ ] **Readiness `/ready`** - 200 only when this pod can serve (its DB pool, Redis, queue connection); no third-party ping (one upstream outage pulls every replica). NestJS `@nestjs/terminus`: `health.check([() => this.db.pingCheck('db', this.prisma)])`, Redis via a custom indicator or `MicroserviceHealthIndicator`
- [ ] **Dependency health** on a separate endpoint (`/internal/deps`), never wired to readiness
- [ ] At `deep`: every critical journey has an SLI (rate, success, p95) - a critical journey with none is High - and an SLO target documented beside the code (undocumented: Medium)

### Step 11 - Verify and Reconcile

**One construct, one finding.** Defects removed by one fix are one finding at the worst tier, naming the others in its Issue and numbering the fixes (a counter registered in a handler, labelled by `orderId`, missing `_total`); defects needing different fixes at one site stay separate. Step 4's grouping rule covers absent surfaces. **A defect this lens does not own is reported, never dropped:** one `- **out of lens:** file:line - <the defect, and the workflow that owns it>` line per defect, at the end of `## Findings`, for a defect outside this lens that would break the build, corrupt, lose, or expose data, or block legitimate traffic (anything else is left to `task-node-review`), untiered and uncounted.

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying the `Label` and `Annotation` columns, and fill `Findings verified:` in the atomic's Summary form. A finding spanning a pre-existing construct and new code cites the unchanged construct and names the new trigger in its Issue; the verify pass attributes it. Subagent runs skip verification - the parent verifies the merged set. Investigation mode skips it too: re-read each cited `file:line` at `HEAD`, drop what the code contradicts, mark what cannot be settled in-tree `_(unverified: <reason>)_`, and report `Findings verified: inline (no diff)`.

**Round 2+ (standalone, after verification).** Project the prior report at the handle's `report_path` into reconcile's parse shape: one `## High-Impact Findings` section, and per prior finding (every tier) a `### [<Label>] <file:line>` heading - the label from its bold `[Must]` / `[Recommend]` token (a prior report with none: the label its tier maps to), the `file:line` prefix of its Location, each Location annotation as its own group (`_(pre-existing; newly reachable via ...)_` split into `_(pre-existing)_ _(newly reachable via ...)_`), a prior `_(carried from round <N>)_` kept - followed by its Issue line as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files`. Its table, note line, and tally render as `## Prior Round Reconciliation`. A row is re-derived when this round's findings hold one on the same construct with the same smell. A `Still open` or `Needs re-check` row this round re-derived publishes once, at this round's label; one it did not re-derive republishes its prior block verbatim in its prior tier - every field, the Location with all its annotation groups - at its prior label, with `_(carried from round <N>)_` after the label unless the block already carries one (`<N>` = the round it first appeared), outside the verify tally, plus a Next Steps entry suffixed `(open since round <N>)`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` is never carried.

### Step 12 - Write Report

**Subagent mode** (invoked by `task-node-review`): return only `## Findings` with its tier sections and any `out of lens` lines. No Summary, Surface Map, Recommendations, Next Steps, or file; the parent owns the report. This supersedes any generic "return your Output Format" in the parent's prompt.

**Investigation mode:** emit the report body as the response; no writer.

**Standalone:** Use skill: `review-report-writer` with `report_type: review-observability`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the round gate, `scope: +obs`, `depth` as resolved, `stack = node-typescript`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried one, else `prior_checkpoint.pr_url` when present. Emit the body, then the writer's confirmation line.

## Output Format

Emit `report_body` as raw Markdown; the fence delimits the template for display only, and brace annotations in it are authoring notes, never emitted.

**Impact tiers.** **High** = an incident would be undiagnosable or a signal is actively wrong (secrets or PII in logs, OTel initialized after imports, exhausted jobs never captured where an error tracker exists, a liveness probe that restarts replicas on a third-party outage); an absent or partial surface is rated by Step 4's cost test. **Medium** = a signal exists but is degraded or costly (unbounded label cardinality, default sampling on high traffic, missing DB or BullMQ spans while the rest is wired, no cause chain). **Low** = hardening with no diagnostic loss today (missing `service.version`, buckets not matched to an SLO). Summary counts are by tier and include carried rows. `Overall` is `Adequate` when nothing is published (this round's or carried), `Greenfield` per its annotation, `Gaps Found` otherwise.

**Labels.** High -> `[Must]`; Medium / Low -> `[Recommend]` - unless the verify pass returned a different `Label`, which wins: a finding sits in its tier's section while its label is the published one. No other label is written. **Location** is always a `file:line`: a config key anchors at the line that reads it, a construct absent from a whole new file at `<path>:1`, and a surface absent from the codebase at the bootstrap line it would load before (`NestFactory.create`, the Express `app` creation).

**Envelope precedence.** `ops-observability`, `node-exception-handling`, and `node-bullmq-patterns` feed findings into this template under its tiers; their own blocks are not emitted.

```markdown
## Node.js Observability Review Summary

- **Stack:** Node.js <version> / <TypeScript <version> | JavaScript> / <NestJS | Express | mixed | other> / <Prisma | TypeORM | Prisma + TypeORM | other | none>
- **Target:** <base_ref>...<head_ref> | <the investigated scope at HEAD>
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Logging:** <pino | winston | nestjs-pino | NestJS Logger | console> (JSON | text) | absent   {`console` when stray `console.*` calls are the only logging}
- **Metrics:** prom-client | OTel metrics | StatsD | absent
- **Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (other exporter) | Sentry-owned | absent
- **Error Tracker:** Sentry | Honeybadger | Rollbar | absent
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)} | inline (no diff)
- **Overall:** Adequate | Gaps Found - <n> High / <n> Medium / <n> Low | Greenfield - <n> High / <n> Medium / <n> Low   {Greenfield when 3 or more Surface Map rows are `absent`}
- **Notes:** <the handle's notes, framework / ORM resolution, investigation scope decisions>   {omit when none}

## Surface Map

| Surface | Verdict | Evidence |
| ------- | ------- | -------- |
| Logging | wired \| partial \| absent \| n/a | <file:line, or `no logging config in repo`> |
| OpenTelemetry SDK | wired \| partial \| absent \| n/a | ... |
| Metrics | wired \| partial \| absent \| n/a | ... |
| BullMQ | wired \| partial \| absent \| n/a | ... |
| Error tracker | wired \| partial \| absent \| n/a | ... |
| Probes | wired \| partial \| absent \| n/a | ... |

## Findings

### High Impact

1. **[Must | Recommend]**{ _(carried from round <N>)_} **Location:** <file:line>{ <verify annotation groups>}

   **Issue:** <the Node idiom: no `redact` for `req.headers.authorization`, `orderId` label, OTel init after the app import, exhausted jobs never captured>

   **Impact:** <what an on-call engineer cannot answer because of this>

   **Fix:** <pino / OTel / prom-client / Sentry change with code; several fixes on one construct numbered>

### Medium Impact

<same block; numbering continues across tiers>

### Low Impact / Quick Wins

<same>

- **out of lens:** <file:line - defect, owning workflow>   {only when one exists}

{omit empty tiers; when every tier is empty, write `No observability issues found.`}

## Prior Round Reconciliation   {round 2+ standalone only}

<table, note line, and tally from `review-prior-findings-reconcile`>

## Recommendations   {omit when none}

- <structural improvement not tied to a finding - consolidate three logger factories into one module>

## Next Steps

1. **[Implement]** [Must] <file:line> - <one-line action>
2. **[Delegate]** [Recommend] [scope: ops] - <one-line action>

{one entry per finding, a carried one suffixed ` (open since round <N>)`; `[Implement]` for a local fix, `[Delegate]` for cross-cutting or ops work; ordered by label, carryovers first among equals, then tier; omit when nothing is actionable}
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed; `Framework`, `ORM`, `Database` recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-observability`; round decided from the handle before the diff was read (or the stop line printed); subagent / investigation: step skipped
- [ ] Step 4: surface read; one verdict per surface including Probes and `n/a`; absent surfaces grouped and rated by cost
- [ ] Step 5: JSON, correlation, redaction, entity logging, levels, cause chain
- [ ] Step 6: init order per module format, `NodeSDK`, sampler, instrumentation coverage, BullMQ `telemetry`, resource attributes
- [ ] Step 7: exposure, runtime / HTTP metrics, cardinality, registration, multi-process, buckets
- [ ] Step 8: queue events, exhausted-job capture condition, per-job metrics, processor context, scheduler freshness
- [ ] Step 9: bootstrap span, shutdown flush, context propagation, `worker_threads`
- [ ] Step 10: one capture path, one tracer provider, PII, sampling, probes; SLI / SLO at `deep`
- [ ] Step 11: one construct filed once; verify ran with its tally (or the subagent / investigation carve-out); round 2+ projected and reconciled, unresolved rows carried
- [ ] Step 12: standalone report written with every writer field; subagent: findings returned, no file; investigation: body emitted

## Avoid

- State-changing git from this workflow
- "Add metrics" instead of the idiom (`prom-client` `Counter` `acme_refunds_total` at module scope, bounded labels)
- Reviewing dashboards, alert rules, forwarders, or on-call rotation
- Accepting `userId` / `orderId` labels, template-string logging, or `console.log` as logging
- Prescribing an OTLP endpoint URL or a Sentry DSN - "sourced from config" and stop
- One finding per missing checkbox when a whole surface is absent
