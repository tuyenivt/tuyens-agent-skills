---
name: task-node-review-observability
description: Node.js observability review: pino/winston logs, OpenTelemetry Node SDK, prom-client, BullMQ events, Sentry; identifies telemetry gaps.
agent: node-tech-lead
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

**Not for:** general Node review (`task-node-review`), known-bottleneck perf (`task-node-review-perf`), active incidents (`/task-oncall-start`), infra observability config.

## Depth Levels

| Depth      | When                                           | Runs                                        |
| ---------- | ---------------------------------------------- | ------------------------------------------- |
| `quick`    | Single endpoint / controller / job             | Logging + prom-client only                  |
| `standard` | Default                                        | All steps                                   |
| `deep`     | Pre-release of critical service, post-incident | All steps + SLI/SLO suggestions             |

Default: `standard`.

## Invocation

| Invocation                                 | Meaning                                                              |
| ------------------------------------------ | -------------------------------------------------------------------- |
| `/task-node-review-observability`          | Current branch vs base; fails fast on trunk                          |
| `/task-node-review-observability <branch>` | `<branch>` vs base (3-dot diff)                                      |
| `/task-node-review-observability pr-<N>`   | PR head fetched into local `pr-<N>` branch (user runs fetch first)   |

As a subagent of `task-code-review-observability` or `task-node-review`, the parent passes the precondition handle plus pre-read diff / commit log; Step 2 is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Skip re-detection if parent confirmed. If not Node, stop and direct user to `/task-code-review-observability`.

Record `Framework: NestJS | Express | mixed`, `ORM: Prisma | TypeORM`. Subsequent steps branch on these signals.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once; reuse for all later steps. Skip if running as subagent with pre-read artifacts. If the precondition check fails, surface its message verbatim and stop. No state-changing git from this workflow.

### Step 3 - Read the Instrumentation Surface

**Top-line output:** one verdict per surface (Logging / OTel SDK / prom-client / BullMQ / Error tracker) of `wired | partial | absent`. Absence is itself the finding.

**Grouping rule.** When a whole surface is `absent`, produce **one High-Impact finding for that surface**, listing missing pieces grouped by file/symbol they should land in. Per-callsite findings only apply when the surface exists and is misused. Prevents 50-item dumps on greenfield reviews.

Open the config files so findings cite real lines:

**NestJS:** `src/logger/logger.module.ts` (`nestjs-pino`, redaction), `src/main.ts` / `src/telemetry.ts` (`NodeSDK`, exporters, auto-instrumentations), `src/config/*.ts` / `.env` (`OTEL_*`, log level, Sentry DSN, Prom port), `package.json` (`@opentelemetry/sdk-node`, `auto-instrumentations-node`, `prom-client`, `nestjs-pino`, `@sentry/node`).

**Express:** `src/logger.ts` (pino/winston, redaction, request-id), `src/telemetry.ts` (`NodeSDK` init - MUST run before any other `require`/`import`), `src/server.ts` (middleware order: request-id → logger → OTel context → routes; `/metrics`), `package.json`.

Plus every changed file calling `Logger`/`logger.*`, registering a metric, defining an interceptor, or touching trace context.

### Step 4 - Structured Logging (pino / winston)

- [ ] **JSON output** in prod: `pino` (default) or `winston.format.json()`. No raw text
- [ ] **Correlation fields** every line: `traceId`, `spanId`, `requestId`, `userId`, `tenantId`, business IDs. NestJS: `nestjs-pino` `genReqId`. Express: `cls-rtracer` / `als-rtracer` over `AsyncLocalStorage` feeding `pino-http`
- [ ] **OTel log correlation**: `@opentelemetry/instrumentation-pino` or `-winston` injects `trace_id` / `span_id`
- [ ] **Redaction** of secrets: `pino` `redact: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token']`; winston via custom format. Reinforced by `@Exclude()` / Zod schemas
- [ ] **No entity logging**: `logger.log(user)` may trigger lazy queries and leak PII. Log specific fields by ID
- [ ] **Identity fields as structured key-values**, not string interpolation: `logger.info({ userId }, 'event')` not `` `user=${userId}` ``. Redaction cannot scrub free-text reliably
- [ ] **Log levels**: `error` actionable, `warn` recoverable, `info` state transitions, `debug` verbose. Default `info` in prod
- [ ] **No `console.log`** in prod paths - skips redaction, structure, correlation
- [ ] **No hot-loop logging** (large iterations, per-second jobs, high-TPS workers): sample or `debug`
- [ ] **Error logging with cause chain**: `logger.error({ err }, 'msg')` (pino's `err` serializer captures `cause`), not `err.message`

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK initialized BEFORE any other `import` / `require`**: `NodeSDK` in `tracing.ts` loaded first in `main.ts`, or via `node --require ./tracing.js`. Late init means auto-instrumentation cannot patch already-loaded modules
- [ ] **`NodeSDK` configured**: `TracerProvider`, `MeterProvider`, OTLP exporter; `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Sampling explicit**: `ParentBasedSampler(TraceIdRatioBasedSampler(rate))` with `rate` per env; not default
- [ ] **Auto-instrumentation**: `@opentelemetry/auto-instrumentations-node` or individual ones wired
- [ ] **Framework**: NestJS `instrumentation-nestjs-core`; Express `instrumentation-express` + `-http`
- [ ] **Database**: `instrumentation-prisma` (Prisma) or `instrumentation-pg` (TypeORM)
- [ ] **HTTP client**: `instrumentation-http` covers `http`/`https`/`node-fetch`; add `instrumentation-undici` for undici
- [ ] **BullMQ**: `instrumentation-bullmq` so job spans link back via traceparent through Redis
- [ ] **Redis / cache**: `instrumentation-ioredis` or `-redis-4`
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

_Skip at `quick` unless diff touches BullMQ. Defer in-depth queue patterns to `node-bullmq-patterns`._

- [ ] **`instrumentation-bullmq` enabled** for cross-broker trace propagation
- [ ] **Queue events wired**: `completed`/`failed`/`stalled` → counters + duration histograms; `worker.on('error')` for crashes
- [ ] **Per-job metrics**: latency histogram, retry / failure counters, queue-depth gauge (`queue.getJobCounts()` polled)
- [ ] **Trace context across request → job boundary**: instrumentation handles this; flag manual wiring that breaks it
- [ ] **Logger context inside processor**: `jobId`, `name`, sanitized `data` bound at start, cleared at end (CLS / `AsyncLocalStorage`)
- [ ] **Outbound HTTP from jobs instrumented**: `axios`/`fetch`/`undici` covered by `instrumentation-http` so worker span chains downstream
- [ ] **Repeatable jobs**: each repeat emits a span; missed-execution alert via stalled metric

### Step 8 - NestJS Lifecycle / Async Observability

_Skip at `quick` unless diff touches lifecycle hooks or `AsyncLocalStorage`._

- [ ] **Bootstrap span**: `OnApplicationBootstrap` emits `app.bootstrap` for cold-start visibility
- [ ] **Graceful shutdown**: `OnApplicationShutdown` closes Prisma, BullMQ workers, `sdk.shutdown()`; flushes telemetry. Absence drops in-flight spans/metrics
- [ ] **`AsyncLocalStorage` preserved** through `setImmediate`/`setTimeout`/`Promise.then`; flag manual `context.with` that bypasses
- [ ] **`worker_threads`**: re-bind trace context via worker message; auto-propagation does not cross the thread boundary
- [ ] **Long-running streams / async generators**: span covers the full lifecycle
- [ ] **Response-time interceptor** when per-route logged timings are wanted alongside OTel histograms

### Step 9 - Error Tracking (Sentry / Honeybadger / Rollbar)

_Skip at `quick` unless diff modifies error handlers, error-tracker config, or DSN handling._

Canonical rescue strategy and capture-once discipline: Use skill: `node-exception-handling`. This step flags deviations from that contract (double-capture, leaked ORM types, per-handler try/catch that duplicates the global filter).

- [ ] **SDK initialized with framework integration**: `Sentry.init({ integrations: [...] })` with `httpIntegration`, `expressIntegration` / `@sentry/nestjs`, `prismaIntegration`
- [ ] **DSN in env / Vault**, not committed
- [ ] **Release + environment tags** from build metadata
- [ ] **PII scrubbing**: `sendDefaultPii: false`; `beforeSend` strips sensitive keys
- [ ] **OTel / pino correlation forwarded**: events carry `trace_id`, `userId` (Sentry SDK 8+ auto-extracts when OTel active)
- [ ] **Sample rate explicit**: `tracesSampleRate` per env; never `1.0` in high-traffic prod
- [ ] **`ignoreErrors`** lists handled exceptions (`BadRequestException`, validation) with comments
- [ ] **Filter / middleware calls `Sentry.captureException(exc)`** before response transform, preserving stack
- [ ] **`unhandledRejection` / `uncaughtException`** captured before exit

### Step 10 - Health Checks and SLIs (deep only)

- [ ] Critical journeys have an SLI (rate, success, p95)
- [ ] **Liveness `/health`**: 200 if the process is responsive. No DB / Redis / external ping - a flaky dep would restart every replica
- [ ] **Readiness `/ready`**: 200 only when this pod can serve - DB pool, Redis, BullMQ connection. No third-party ping - one upstream outage would pull every replica
- [ ] **Dependency-health endpoint** (`/internal/deps`) for third-party reachability; observability signal only, NOT wired to readiness
- [ ] NestJS: `@nestjs/terminus` `HealthCheckService.check([])` for liveness; `check([prisma, redis])` for readiness
- [ ] Express: liveness returns `{ status: 'ok' }`; readiness checks own-pod deps
- [ ] SLO targets documented in code (decorator / README), not free-floating
- [ ] Synthetic probes hit `/ready`, not just `/health`

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the assembled output to the report file and print the confirmation line.

## Output Format

```markdown
## Node.js Observability Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>
**Logging:** pino (JSON) | winston (JSON) | nestjs-pino | console (text) | absent
**Metrics:** prom-client | OTel metrics (Prometheus exporter) | StatsD | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin) | absent
**BullMQ instrumentation:** @opentelemetry/instrumentation-bullmq | partial | absent | n/a
**Error Tracker:** Sentry | Honeybadger | Rollbar | absent
**Overall:** Adequate | Gaps Found - [count by impact] | Greenfield - no observability surface wired

## Surface Map

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| Logging                | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| prom-client / metrics  | wired / partial / absent       | [...]                                      |
| BullMQ instrumentation | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as `Overall:` when 3+ rows are `absent`. Use the `absent` vocabulary consistently (not `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Node idiom: missing pino redaction for `req.headers.authorization`, unbounded `userId` label, OTel SDK init after `app.module` import, missing `instrumentation-bullmq`, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Node / OTel / pino / prom-client change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty sections. Group by surface within a bucket when 3+ share one; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per Step 3._

## Recommendations

[Structural improvements not tied to a single finding - e.g., "Move `tracing.ts` to `--require` in `scripts.start`", "Add `instrumentation-bullmq`", "Switch per-request `new Counter` to module-level constants"]

## Next Steps

Prioritized action list. Each item `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Bind `orderId` via `als.run({ orderId }, () => ...)` at `OrdersService.place` entry; clear in finally"]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action, e.g., "Wire `/metrics` to org Prometheus scrape config"]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Stack, framework, ORM recorded; diff and log read once (Steps 1-2)
- [ ] Surface map produced with `wired | partial | absent` verdicts; absent surfaces collapsed to one finding each (Step 3)
- [ ] Logging assessed: JSON, correlation, redaction, level discipline, no `console.log`, no entity logging, cause chain (Step 4)
- [ ] OTel SDK reviewed: init BEFORE imports; framework / DB / HTTP / BullMQ / Redis instrumentations; explicit sampling; resource attributes (Step 5)
- [ ] `prom-client` assessed: defaults + HTTP, namespaced customs, bounded labels, module-level registration, cluster aggregation, route normalization (Step 6)
- [ ] BullMQ, lifecycle / async, error tracker assessed when in scope and depth permits (Steps 7-9)
- [ ] `deep`: SLIs and liveness / readiness / deps separation reviewed (Step 10)
- [ ] Findings name a specific Node / OTel / pino / prom-client idiom; library-level scope respected
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend > Question
- [ ] Report written via `review-report-writer`; confirmation printed (Step 11)

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Generic gaps ("add metrics") instead of naming the idiom (`prom-client.Counter` `acme_orders_placed_total` at module level, bounded labels)
- Generic advice when a Node SDK exists - say "enable `instrumentation-nestjs-core`", not "add HTTP tracing"
- Reviewing infra (Datadog, Grafana, alert rules, log forwarders, on-call rotation)
- Accepting high-cardinality labels (`userId`, `orderId`); require enum / category labels
- Approving template-string logging (`` `order=${orderId}` ``) over structured `{ orderId }` form
- Approving `console.log` / `console.error` as logging
- Approving `new Counter(...)` inside a request handler - duplicate-registration crash after first request
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Approving `OTEL_TRACES_SAMPLER=always_on` in high-traffic prod
- Approving OTel SDK init AFTER application imports - auto-instrumentation cannot patch loaded modules
- Prescribing OTLP endpoint URL or Sentry DSN - say "sourced from env / Vault" and stop
- One finding per missing checkbox when a whole surface is absent - collapse per Step 3
- Recommending only `pino` when the team uses `winston` - both are acceptable with JSON + redaction + OTel correlation
