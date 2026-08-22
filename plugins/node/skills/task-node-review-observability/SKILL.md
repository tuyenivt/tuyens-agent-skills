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

Stack-specific delegate of `task-code-review-observability` for Node.js. Names `pino` / `winston`, OpenTelemetry Node SDK + auto-instrumentations, `prom-client`, NestJS lifecycle hooks, BullMQ queue events, and error-tracker SDKs (`@sentry/node`, etc.) directly. Library / SDK level only; infra (Datadog dashboards, log forwarders, alert rules) is out of scope.

## When to Use

- Reviewing a NestJS or Express PR for observability regressions or new instrumentation gaps
- Pre-release check for a new Node service or major feature
- Post-incident review when Node diagnosis was slow or evidence missing
- Adopting OpenTelemetry / pino / Prometheus / BullMQ instrumentation

**Not for:** general Node review (`task-node-review`), known-bottleneck perf (`task-node-review-perf`), infra observability config.

## Depth Levels

| Depth      | When                                           | Runs                                        |
| ---------- | ---------------------------------------------- | ------------------------------------------- |
| `standard` | Default                                        | All steps, including probe correctness      |
| `deep`     | Pre-release of critical service, post-incident | All steps + SLI/SLO targets                 |

Default: `standard`. Probe correctness (liveness vs readiness vs dependency-health separation) is diff-visible and runs at `standard` - `task-node-review-reliability` defers probe wiring here, so gating it behind `deep` would leave it uncovered by every lens.

## Invocation

| Invocation                                 | Meaning                                                              |
| ------------------------------------------ | -------------------------------------------------------------------- |
| `/task-node-review-observability`          | Current branch vs base; fails fast on trunk                          |
| `/task-node-review-observability <branch>` | `<branch>` vs base (3-dot diff)                                      |
| `/task-node-review-observability pr-<N>`   | PR head fetched into local `pr-<N>` branch (user runs fetch first)   |

Depth (`standard` | `deep`) and `--base <branch>` compose with any form: `/task-node-review-observability pr-4471 --base release/2026.05 deep`.

`task-node-review` spawns this workflow as its `+Obs` subagent. As a subagent the parent passes the precondition handle plus pre-read diff / commit log; Step 2 is skipped, Step 11's verification is skipped, and Step 12 takes its subagent branch.

## Workflow

### Step 1 - Load Behavioral Principles and Confirm Stack

Use skill: `behavioral-principles` first, before any other delegation. Then use skill: `stack-detect`; skip re-detection if a parent confirmed. If not Node, stop and direct user to `/task-code-review-observability`.

Record `Framework: NestJS | Express | mixed`, `ORM: Prisma | TypeORM`. Subsequent steps branch on these signals.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check`; forward `--base <branch>` when passed. On approval, read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once; reuse for all later steps. Also capture `base_sha` / `head_sha` via `git rev-parse` on those refs - the writer runs no git of its own. Skip if running as subagent with pre-read artifacts. If the precondition check fails, surface its message verbatim and stop. No state-changing git from this workflow.

**Re-review gate (standalone only).** The handle's `prior_checkpoint` is keyed to `review-<branch>.md`, the general review's report - not this lens's. Check for `review-observability-<branch>.md` yourself, sanitizing `branch` the way the writer does (`/` and any character outside `[A-Za-z0-9_-]` becomes `-`). If it exists with valid frontmatter, its `head_sha` equals the current head, and the invocation adds no depth beyond it, print `No new commits on <branch> since prior observability review at <sha_short>. Prior report unchanged.` and stop without writing. Otherwise `round` = prior + 1, and pass its `head_sha` as `prior_head_sha`. No such file, or one whose frontmatter is missing or invalid -> `round: 1`, no `prior_head_sha`; that is the common path and it is not an error.

### Step 3 - Read the Instrumentation Surface

**Top-line output:** one verdict per surface (Logging / OTel SDK / prom-client / BullMQ / Error tracker / Probes) of `wired | partial | absent | n/a`. Absence is itself the finding; `n/a` is for a surface the service genuinely has no use for (no queue, so no BullMQ).

**Grouping rule.** When a whole surface is `absent`, produce **one finding for that surface**, listing missing pieces grouped by the file/symbol they should land in. Per-callsite findings only apply when the surface exists and is misused. Prevents 50-item dumps on greenfield reviews.

Rate an absent surface by what it costs *this* service: absent logging correlation or an absent error tracker on a service handling money or auth is High; an absent surface on a service that never had one and is not on a critical path is Medium. Do not default every absent surface to High - on a greenfield review that turns the whole report into merge blockers.

Open the config files so findings cite real lines:

**NestJS:** `src/logger/logger.module.ts` (`nestjs-pino`, redaction), `src/main.ts` / `src/telemetry.ts` (`NodeSDK`, exporters, auto-instrumentations), `src/config/*.ts` / `.env` (`OTEL_*`, log level, Sentry DSN, Prom port), `package.json` (`@opentelemetry/sdk-node`, `auto-instrumentations-node`, `prom-client`, `nestjs-pino`, `@sentry/node`).

**Express:** `src/logger.ts` (pino/winston, redaction, request-id), `src/telemetry.ts` (`NodeSDK` init - MUST run before any other `require`/`import`), `src/server.ts` (middleware order: request-id → logger → OTel context → routes; `/metrics`), `package.json`.

Plus every changed file calling `Logger`/`logger.*`, registering a metric, defining an interceptor, or touching trace context.

### Step 4 - Structured Logging (pino / winston)

- [ ] **JSON output** in prod: `pino` (default) or `winston.format.json()`. No raw text
- [ ] **Correlation fields** every line: `traceId`, `spanId`, `requestId`, `userId`, `tenantId`, business IDs. NestJS: `nestjs-pino` `genReqId`. Express: `cls-rtracer` or an `AsyncLocalStorage`-based request-id middleware feeding `pino-http`
- [ ] **OTel log correlation**: `@opentelemetry/instrumentation-pino` or `-winston` injects `trace_id` / `span_id`
- [ ] **Redaction** of secrets: `pino` `redact: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token']`; winston via custom format. Reinforced by `@Exclude()` / Zod schemas
- [ ] **No entity logging**: `logger.log(user)` serializes every column, leaking PII and secrets the DTO layer excludes. Log the id plus the fields you need
- [ ] **Identity fields as structured key-values**, not string interpolation: `logger.info({ userId }, 'event')` not `` `user=${userId}` ``. Redaction cannot scrub free-text reliably
- [ ] **Log levels**: `error` actionable, `warn` recoverable, `info` state transitions, `debug` verbose. Default `info` in prod
- [ ] **No `console.log`** in prod paths - skips redaction, structure, correlation
- [ ] **No hot-loop logging** (large iterations, per-second jobs, high-TPS workers): sample or `debug`
- [ ] **Error logging with cause chain**: `logger.error({ err }, 'msg')` (pino's `err` serializer captures `cause`), not `err.message`

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK initialized BEFORE any other `import` / `require`**: CJS loads `tracing.js` via `node --require ./tracing.js` or as the first import in `main.ts`; **ESM output needs `node --import ./tracing.mjs`** (`register()` plus the `@opentelemetry/instrumentation/hook.mjs` loader) - `--require` does not patch ESM imports. Late init means auto-instrumentation cannot patch already-loaded modules
- [ ] **`NodeSDK` configured**: it constructs the providers itself, so pass `traceExporter` / `spanProcessors`, `metricReader`, `sampler`, `resource`, `instrumentations` - not a `TracerProvider` or `MeterProvider`. `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Sampling explicit**: `new ParentBasedSampler({ root: new TraceIdRatioBasedSampler(rate) })` with `rate` per env; not default
- [ ] **Auto-instrumentation**: `@opentelemetry/auto-instrumentations-node` or individual ones wired. When enabled it covers the framework, HTTP, Redis, pg, and Step 4's pino / winston log-correlation row - but **not** `@prisma/instrumentation`, which is never bundled and must be registered by hand. Verify coverage and raise **one** finding for whatever it genuinely misses, not one per row
- [ ] **Framework**: NestJS `instrumentation-nestjs-core`; Express `instrumentation-express` + `-http`
- [ ] **Database**: `@prisma/instrumentation` (Prisma) or `instrumentation-pg` (TypeORM)
- [ ] **HTTP client**: `instrumentation-http` covers the `http` / `https` modules and the `node-fetch` package. Node 18+ global `fetch` is undici and bypasses them - it needs `instrumentation-undici`, as does `undici.request`
- [ ] **BullMQ**: there is no `@opentelemetry/instrumentation-bullmq`. Use a community package (e.g. `@appsignal/opentelemetry-instrumentation-bullmq`) so job spans link back via traceparent through Redis, or accept the gap explicitly - never name a bare `instrumentation-bullmq` in a fix
- [ ] **Redis / cache**: `instrumentation-ioredis`, or `@opentelemetry/instrumentation-redis` (which absorbed the deprecated `-redis-4` and covers redis v4/v5)
- [ ] **Custom spans** via `tracer.startActiveSpan(...)`; no double-instrumentation of a single Prisma query
- [ ] **Resource attributes**: `service.name`, `service.version`, `deployment.environment` from build / env

### Step 6 - Prometheus Metrics (prom-client)

- [ ] **`prom-client` installed** with `/metrics` exposed (NestJS: `@willsoto/nestjs-prometheus`; Express: `register.metrics()` route) or `OTEL_METRICS_EXPORTER=prometheus`
- [ ] **Default Node metrics** scraped: `collectDefaultMetrics()` at startup (`process_*`, `nodejs_eventloop_lag_seconds`, `nodejs_active_handles_total`, heap)
- [ ] **HTTP server metrics**: histogram via middleware (`express-prom-bundle` or NestJS interceptor) - `http_request_duration_seconds`, `http_requests_total` with route/method/status
- [ ] **Custom metrics** under a namespace (`acme_orders_placed_total`); types correct (`Counter`/`Histogram`/`Gauge`/`Summary`); suffixes (`_total`/`_seconds`/`_bytes`)
- [ ] **Label cardinality bounded**: never label by `userId`/`orderId`/`requestId`; only enums/categories
- [ ] **No registration in hot path**: `new Counter(...)` at module level only; per-request causes duplicate-registration crashes
- [ ] **Cluster mode**: `AggregatorRegistry` for PM2 / Node `cluster` deployments
- [ ] **Histogram buckets** match SLO; add finer buckets for sub-100ms paths
- [ ] **Route normalization**: label by route template (`/orders/:id`), not `req.url` with path params

### Step 7 - BullMQ / Background Job Observability

_Defer in-depth queue patterns to `node-bullmq-patterns`._

- [ ] **BullMQ trace propagation wired** via the community instrumentation named in Step 5 (this row and Step 5's are the same check - report it once)
- [ ] **Queue events wired**: `completed`/`failed`/`stalled` → counters + duration histograms; `worker.on('error')` for worker-level crashes
- [ ] **Exhausted jobs reach the error tracker**: a worker has no exception filter, so wiring only the filter leaves every exhausted job dark. Capture on the job-failed event, gated on `job.attemptsMade >= job.opts.attempts` (see `node-exception-handling`) - `@OnWorkerEvent('failed')` under `@nestjs/bullmq`, `worker.on('failed', (job, err) => ...)` on a standalone Express worker. Different event from `worker.on('error')` above, which is worker-level
- [ ] **Per-job metrics**: latency histogram, retry / failure counters, queue-depth gauge (`queue.getJobCounts()` polled)
- [ ] **Trace context across request → job boundary**: instrumentation handles this; flag manual wiring that breaks it
- [ ] **Logger context inside processor**: `jobId`, `name`, sanitized `data` bound at start, cleared at end (CLS / `AsyncLocalStorage`)
- [ ] **Outbound HTTP from jobs instrumented**: `axios` and the `http`/`https` modules via `instrumentation-http`; global `fetch` / `undici` via `instrumentation-undici` (Step 5's split applies here too)
- [ ] **Repeatable / scheduled jobs**: each repeat emits a span, and a **missed** execution is alerted on a freshness gauge (time since last completion). `stalled` cannot detect it - that event fires only for an active job whose lock stopped renewing, and a job that never started is never active

### Step 8 - Lifecycle and Async Observability

NestJS hook names are given below; on Express the same checks apply to the equivalent site - the `SIGTERM` handler for shutdown, `main`/`server.ts` for bootstrap. Mark a row N/A only when the construct itself is absent, not because the framework differs.

- [ ] **Bootstrap span**: started in `main.ts` **before** `NestFactory.create()` and ended after `listen()`. A span opened in `OnApplicationBootstrap` runs after every module has initialized and measures nothing
- [ ] **Graceful shutdown**: `OnApplicationShutdown` closes Prisma, BullMQ workers, `sdk.shutdown()`; flushes telemetry. Absence drops in-flight spans/metrics
- [ ] **`AsyncLocalStorage` preserved** through `setImmediate`/`setTimeout`/`Promise.then`; flag manual `context.with` that bypasses
- [ ] **`worker_threads`**: re-bind trace context via worker message; auto-propagation does not cross the thread boundary
- [ ] **Long-running streams / async generators**: span covers the full lifecycle
- [ ] **Response-time interceptor** when per-route logged timings are wanted alongside OTel histograms

### Step 9 - Error Tracking (Sentry / Honeybadger / Rollbar)

Canonical rescue strategy and capture-once discipline: Use skill: `node-exception-handling`. This step flags deviations from that contract (double-capture, leaked ORM types, per-handler try/catch that duplicates the global filter).

- [ ] **SDK initialized with framework integration**: on Sentry v8, `httpIntegration`, `expressIntegration`, `prismaIntegration`, and the `uncaughtException` / `unhandledRejection` handlers are **defaults** - an `init()` with no `integrations` key already has them, so its absence is not a finding. What NestJS does need explicitly is `@sentry/nestjs` with `SentryModule.forRoot()` and `SentryGlobalFilter`
- [ ] **DSN in env / Vault**, not committed
- [ ] **Release + environment tags** from build metadata
- [ ] **PII scrubbing**: `sendDefaultPii: false`; `beforeSend` strips sensitive keys
- [ ] **OTel correlation forwarded**: Sentry v8 is OTel-native and attaches `trace_id` automatically. User identity is **not** automatic under `sendDefaultPii: false` - set it deliberately via `Sentry.setUser({ id })`, an opaque id rather than an email
- [ ] **No duplicate tracing setup**: Sentry v8 installs its own tracer provider on `init()`. `@opentelemetry/api` registration is **first-wins**: the second registrant is refused with a `diag.error` and its spans never reach the global provider, so whichever SDK initializes later is the one that goes dark - either Sentry owns tracing, or it runs with `skipOpenTelemetrySetup: true` wired into the existing provider. Sentry v8 also needs pre-import init (`--import ./instrument.mjs`), the same ordering rule as Step 5
- [ ] **Sample rate explicit**: `tracesSampleRate` per env; never `1.0` in high-traffic prod
- [ ] **`ignoreErrors`** lists handled exceptions (`BadRequestException`, validation) with comments
- [ ] **Filter / middleware calls `Sentry.captureException(exc)`** before response transform, preserving stack
- [ ] **`unhandledRejection` / `uncaughtException`** captured before exit

### Step 10 - Health Checks and SLIs

Probe rows run at every depth. The SLI/SLO rows (marked `deep`) run only at `deep`.

- [ ] _(deep)_ Critical journeys have an SLI (rate, success, p95)
- [ ] **Liveness `/health`**: 200 if the process is responsive. No DB / Redis / external ping - a flaky dep would restart every replica
- [ ] **Readiness `/ready`**: 200 only when this pod can serve - DB pool, Redis, BullMQ connection. No third-party ping - one upstream outage would pull every replica
- [ ] **Dependency-health endpoint** (`/internal/deps`) for third-party reachability; observability signal only, NOT wired to readiness
- [ ] NestJS: `@nestjs/terminus` `HealthCheckService.check([])` for liveness; `check([prisma, redis])` for readiness
- [ ] Express: liveness returns `{ status: 'ok' }`; readiness checks own-pod deps
- [ ] _(deep)_ SLO targets documented in code (decorator / README), not free-floating
- [ ] Synthetic probes hit `/ready`, not just `/health`

### Step 11 - Verify Findings

**One construct, one finding.** A construct carrying several defects (a counter registered in a handler *and* labelled by `userId` *and* missing its `_total` suffix) publishes once at the worst impact, naming the others in its Issue line. Step 3's grouping rule covers absent surfaces; this covers misused ones.

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary.

Its `Label` wins over the impact mapping: a High-Impact finding tagged `[Recommend]` because it is pre-existing and untouched is the correct output, not a contradiction. This matters most on a post-incident review of a mature surface, where most findings are pre-existing. Subagent runs skip this step - the parent verifies the merged set once.

### Step 12 - Write Report

**Subagent mode:** if invoked by `task-node-review`, do not write a file - `review-report-writer` is invoked only by the workflow that owns the report. Return exactly four things, and this list supersedes any generic "return your Output Format" instruction in the parent's prompt:

1. The findings, each carrying its `[Must]` / `[Recommend]` label and its `file:line`
2. `## Next Steps`, tagged and ordered, for the parent to re-sort into its own
3. `## Recommendations`, with the Surface Map's verdicts folded in as bullets (the parent's Summary has no observability fields)
4. Nothing else - omit the Summary block; the parent owns it

Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-observability` and every field it marks required:

- `report_body` (the assembled Markdown), `branch`, `base_ref`, `head_ref` - from the precondition handle
- `base_sha` / `head_sha` captured in Step 2 via `git rev-parse`
- `scope: +obs`, `depth` as invoked, `stack = node-typescript`, `mode: full`
- `round` from Step 2's re-review gate, plus `prior_head_sha` when round > 1

Write the assembled output to the report file and print the confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Impact rubric.** High = an incident would be undiagnosable or a signal is actively wrong (no correlation id anywhere, secrets or PII in logs, OTel init after imports so nothing is traced, a liveness probe that restarts replicas on a third-party outage). An absent surface is rated by Step 3's cost test, not automatically High. Medium = a signal exists but is degraded or costly (unbounded label cardinality, sampling left at default in high-traffic prod, missing DB or BullMQ instrumentation while the rest is wired, no cause chain on errors). Low = hardening with no diagnostic loss today (missing `service.version`, histogram buckets not matched to an SLO). Impact maps to label: High -> `[Must]`; Medium / Low -> `[Recommend]` - unless the verify pass returned a different `Label`, which wins.

**Envelope precedence.** `node-exception-handling` and `node-bullmq-patterns` define their own output blocks. Fold their content into the finding blocks below; do not append their envelopes as separate sections.

Every finding carries exactly one label: `[Must]` or `[Recommend]`. No other label is written.

```markdown
## Node.js Observability Review Summary

- **Stack Detected:** Node.js <version> / TypeScript <version>
- **Framework:** NestJS <version> | Express <version> | mixed
- **ORM:** Prisma <version> | TypeORM <version>
- **Target:** <base_ref>...<head_ref>
- **Logging:** pino | winston | nestjs-pino | NestJS built-in Logger | console | absent - append `(JSON)` or `(text)`
- **Metrics:** prom-client | OTel metrics (Prometheus exporter) | StatsD | absent
- **Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin) | OpenTelemetry (exporter not in scope) | absent
- **BullMQ instrumentation:** wired | partial | absent | n/a
- **Error Tracker:** Sentry | Honeybadger | Rollbar | absent
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(omit the parenthetical when K is 0)_
- **Overall:** Adequate | Gaps Found - [<N> High / <N> Medium / <N> Low] | Greenfield - [<N> High / <N> Medium / <N> Low]

## Surface Map

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| Logging                | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| prom-client / metrics  | wired / partial / absent       | [...]                                      |
| BullMQ instrumentation | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as `Overall:` when 3 or more of the five rows are `absent` - it means "most of the surface is unwired", and it still carries the impact counts. Use the `absent` vocabulary consistently (not `none` / `missing` / `not wired`). `wired` = present and configured; `partial` = present but incomplete or misconfigured; `absent` = not present at all.

## Findings

### High Impact

1. **[Must]** **Location:** [file:line or config key - add `_(pre-existing)_` or `(unverified: <reason>)` when the verify pass returned one]

   **Issue:** [name the Node idiom: missing pino redaction for `req.headers.authorization`, unbounded `userId` label, OTel SDK init after `app.module` import, no BullMQ trace propagation, etc.]

   **Impact:** [diagnosability / alertability / cost - what an on-call engineer cannot answer because of this]

   **Fix:** [specific Node / OTel / pino / prom-client change with code or config example. Several fixes on one construct become a numbered list here.]

### Medium Impact

[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins

[Same]

_Omit empty sections. Group by surface within a bucket when 3+ share one; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per Step 3._

## Recommendations

[Structural improvements not tied to a single finding - e.g., "Preload `tracing.ts` via `--require` (CJS) or `--import` (ESM) in `scripts.start`", "Adopt a community BullMQ instrumentation", "Switch per-request `new Counter` to module-level constants"]

## Next Steps

Prioritized action list. Each item `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Carry each finding's label. Order by label first (Must > Recommend), then by impact within each (High > Medium > Low) - after a de-escalation pass most rows share one label and impact is what still separates them.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Bind `orderId` via `als.run({ orderId }, () => ...)` at `OrdersService.place` entry; clear in finally"]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action, e.g., "Wire `/metrics` to org Prometheus scrape config"]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] `behavioral-principles` loaded first; stack, framework, ORM recorded; diff and log read once, SHAs captured via `git rev-parse`, re-review gate applied (Steps 1-2)
- [ ] Surface map produced with `wired | partial | absent` verdicts; absent surfaces collapsed to one finding each (Step 3)
- [ ] Logging assessed: JSON, correlation, redaction, level discipline, no `console.log`, no entity logging, cause chain (Step 4)
- [ ] OTel SDK reviewed: init BEFORE imports; framework / DB / HTTP / BullMQ / Redis instrumentations; explicit sampling; resource attributes (Step 5)
- [ ] `prom-client` assessed: defaults + HTTP, namespaced customs, bounded labels, module-level registration, cluster aggregation, route normalization (Step 6)
- [ ] BullMQ, lifecycle / async, error tracker assessed when in scope, including the exhausted-job capture site and the Sentry-vs-NodeSDK provider conflict (Steps 7-9)
- [ ] Liveness / readiness / deps separation reviewed at every depth; SLI and SLO rows reviewed at `deep` (Step 10)
- [ ] Step 11: `review-finding-verify` ran and its tally reached the Summary (or the subagent carve-out applied); its `Label` carried, overriding the impact mapping; one construct published one finding
- [ ] Findings name a specific Node / OTel / pino / prom-client idiom, carry one label, and cite a package that exists; library-level scope respected
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend
- [ ] Step 12: standalone: every required writer field assembled, report written, confirmation printed; subagent: labelled findings + Next Steps + Recommendations returned, no file written

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Generic gaps ("add metrics") instead of naming the idiom (`prom-client.Counter` `acme_orders_placed_total` at module level, bounded labels)
- Generic advice when a Node SDK exists - say "enable `instrumentation-nestjs-core`", not "add HTTP tracing"
- Reviewing infra (Datadog, Grafana, alert rules, log forwarders, on-call rotation)
- Accepting high-cardinality labels (`userId`, `orderId`); require enum / category labels
- Approving template-string logging (`` `order=${orderId}` ``) over structured `{ orderId }` form
- Approving `console.log` / `console.error` as logging
- Approving `new Counter(...)` inside a request handler - duplicate-registration crash after first request
- Naming `@opentelemetry/instrumentation-bullmq` or a bare `instrumentation-bullmq` in a fix - no such package is published
- Prescribing `--require` for an ESM build, or `instrumentation-http` as coverage for global `fetch` / undici
- Approving `OTEL_TRACES_SAMPLER=always_on` in high-traffic prod
- Approving OTel SDK init AFTER application imports - auto-instrumentation cannot patch loaded modules
- Prescribing OTLP endpoint URL or Sentry DSN - say "sourced from env / Vault" and stop
- One finding per missing checkbox when a whole surface is absent - collapse per Step 3
- Recommending only `pino` when the team uses `winston` - both are acceptable with JSON + redaction + OTel correlation
