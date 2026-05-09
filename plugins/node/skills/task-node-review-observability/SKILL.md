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

## Purpose

Node.js-aware observability review that names `pino` / `winston` structured logging, OpenTelemetry Node SDK, auto-instrumentation (`@opentelemetry/instrumentation-http`, `-express`, `-nestjs-core`, `-prisma`, `-ioredis`, `-bullmq`), `prom-client`, NestJS lifecycle hooks (`OnModuleInit`, `OnApplicationBootstrap`, `OnApplicationShutdown`), BullMQ queue events (`completed`, `failed`, `stalled`), and error-tracker SDKs (`@sentry/node`, `honeybadger-io`, `rollbar`) directly instead of routing through the generic adapter. Focuses on whether Node production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Node.js. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a NestJS or Express PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Node service or major feature
- Post-incident review when Node diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / pino / Prometheus in a Node app
- Auditing async / BullMQ tracing and correlation across the request → job boundary

**Not for:**

- General Node code review (use `task-node-review`)
- Node performance issues with a known bottleneck (use `task-node-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                     | What Runs                                          |
| ---------- | --------------------------------------------------------------- | -------------------------------------------------- |
| `quick`    | Single endpoint, controller, or job                             | Logging + prom-client metrics check only           |
| `standard` | Default - full Node observability review                        | All steps                                          |
| `deep`     | Pre-release of a critical Node service, or post-incident review | All steps + SLI/SLO suggestions for Node endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                 | Meaning                                                                                               |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `/task-node-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-node-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-node-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-node-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked as a subagent of a Node-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Node, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect framework: NestJS vs Express (or mixed). Detect ORM: Prisma vs TypeORM. Record `Framework: NestJS | Express | mixed`, `ORM: Prisma | TypeORM`. Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (logging / OTel / prom-client / BullMQ / error tracker) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below) rather than one-per-bullet.

**Grouping rule.** When a whole surface is `absent` (no `prom-client`, no OTel SDK init, no error-tracker SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/symbol they should land in - not one finding per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. This prevents 50-item dumps on greenfield reviews.

Then open the files that actually configure observability so findings cite real lines, not assumptions:

**NestJS:**

- `src/logger/logger.module.ts` (or equivalent) - `nestjs-pino` config, `pinoHttp` options, redaction config
- `src/main.ts` / `src/telemetry.ts` - OpenTelemetry SDK wiring (`NodeSDK`, `Resource`, exporters), instrumentation registration (`@opentelemetry/auto-instrumentations-node`)
- `src/config/*.ts` / `.env` - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, log level, Sentry DSN, Prometheus port
- `package.json` - confirm `@opentelemetry/sdk-node`, `@opentelemetry/auto-instrumentations-node`, `prom-client`, `nestjs-pino` (or `pino`), `@sentry/node` presence
- Every changed file in the diff that calls `Logger`, `logger.*`, registers a `Counter` / `Histogram` / `Gauge`, defines a `@Injectable()` interceptor, instruments with OTel, or modifies trace context

**Express:**

- `src/logger.ts` (or equivalent) - `pino` / `winston` setup, redaction config, request-id middleware
- `src/telemetry.ts` / `tracing.ts` - OpenTelemetry SDK init (must run before any other `require`/`import` for auto-instrumentation to patch correctly)
- `src/server.ts` / `app.ts` - middleware order: request-id, logger, OTel context propagation, then routes; metrics endpoint registration
- `package.json` - confirm `@opentelemetry/sdk-node`, `@opentelemetry/auto-instrumentations-node`, `prom-client`, `pino-http`, `@sentry/node`
- Every changed route / middleware / controller calling logger or registering metrics

For diffs touching only one of these surfaces (a new endpoint but no logging change, say), still read the existing config to know whether request-id / trace correlation, instrumentation, and SDKs are wired - a missing wire is the finding.

### Step 4 - Structured Logging (pino / winston)

Inspect logging config and any `logger.*` callsite in the diff:

- [ ] **Production logger emits JSON** - `pino` (default JSON output) or `winston` with `winston.format.json()`. No raw text logs in production
- [ ] **Correlation fields injected** in every log line: `traceId`, `spanId`, `requestId`, `userId` (when authenticated), `tenantId`, plus business correlation IDs (`orderId`, `invoiceId`). NestJS: `nestjs-pino` automatically wires per-request logger with `genReqId`; Express: request-id middleware (`cls-rtracer` / `als-rtracer` using `AsyncLocalStorage`) sets `req.id` and the logger picks it up via `pino-http`
- [ ] **OpenTelemetry log correlation**: `@opentelemetry/instrumentation-pino` / `@opentelemetry/instrumentation-winston` injects `trace_id` / `span_id` into every log record automatically when OTel is active; flag if absent
- [ ] **Sensitive-field redaction**: `pino` `redact: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token', '*.creditCard']` config; `winston` custom format strips them. NestJS `class-transformer` `@Exclude()` and Zod schema design reinforce so `logger.log({ user })` cannot leak via property access
- [ ] **No `logger.log(user)` / `logger.log(entity)`** that serializes an ORM entity (lazy-loaded relations may trigger queries; PII may leak). Always log specific fields by ID
- [ ] **User-identity fields emitted as structured key-values, not in the message string**: `userId`, `ownerId`, `tenantId`, `email` go in via `logger.info({ userId }, 'event')` (pino) or `logger.info('event', { userId })` (winston), never in ``user=${userId}``. A single redaction config can scrub structured fields; it cannot reliably scrub them out of a free-text message
- [ ] **Log levels used correctly**: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics. Default level `info` in prod; `debug` / `trace` reserved for targeted modules
- [ ] **No `console.log`** in production code paths - flag for replacement with the structured logger; `console.log` skips redaction, structured fields, and correlation
- [ ] **No log spam in hot loops** - iterating large arrays, scheduled jobs running every second, BullMQ workers at high TPS must not log per-iteration; sample or use `debug` level
- [ ] **Error logging includes the cause chain**: `logger.error({ err }, 'message')` (pino's `err` serializer captures `cause` chain) - not `logger.error(err.message)` which loses the stack and `cause`

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

Inspect OpenTelemetry config and instrumentation wiring:

- [ ] **OpenTelemetry SDK initialized BEFORE any other `import` / `require`**: `NodeSDK` initialization must run in `tracing.ts` / `telemetry.ts` loaded as the **first** import in `main.ts` / `server.ts` - or via `--require ./tracing.js` Node CLI flag. Late initialization means auto-instrumentation cannot patch already-loaded modules (silent partial coverage)
- [ ] **`NodeSDK` configured**: `TracerProvider`, `MeterProvider`, OTLP exporter (gRPC or HTTP) pointed at the org's collector / backend; `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` set per env
- [ ] **Sampling policy explicit**: `ParentBasedSampler` wrapping `TraceIdRatioBasedSampler(rate)` with `rate` per env (e.g., `0.1` in prod, `1.0` in staging); not left at default
- [ ] **Auto-instrumentation enabled**: `@opentelemetry/auto-instrumentations-node` registered, or individual instrumentations wired explicitly
- [ ] **Framework auto-instrumentation**:
  - NestJS: `@opentelemetry/instrumentation-nestjs-core` enabled (controllers / providers spans)
  - Express: `@opentelemetry/instrumentation-express` + `-http`
- [ ] **Database auto-instrumentation**: `@opentelemetry/instrumentation-prisma` (Prisma) or `@opentelemetry/instrumentation-pg` (TypeORM uses pg under the hood) - SQL spans attach to the request span
- [ ] **HTTP client instrumentation**: `@opentelemetry/instrumentation-http` covers `http` / `https` / `node-fetch` / `undici` (when `instrumentation-undici` is also enabled); traceparent propagates outbound automatically
- [ ] **BullMQ instrumentation**: `@opentelemetry/instrumentation-bullmq` so job spans link back to the dispatching request span via traceparent header propagation through Redis
- [ ] **Redis / cache instrumentation**: `@opentelemetry/instrumentation-ioredis` or `-redis-4` if Redis is in use
- [ ] **Custom spans** for business operations use `tracer.startActiveSpan(...)` over manual span management; no over-instrumentation (do not wrap a single Prisma query in a custom span - the SQL span already covers it)
- [ ] **Resource attributes** populated: `service.name`, `service.version`, `deployment.environment`; sourced from build metadata / env vars

### Step 6 - Prometheus Metrics (prom-client)

Inspect `prom-client` / metrics registration:

- [ ] **`prom-client` installed** and `/metrics` endpoint exposed (NestJS: `@willsoto/nestjs-prometheus` or manual route; Express: `app.get('/metrics', async (req, res) => res.send(await register.metrics()))`), or `OTEL_METRICS_EXPORTER=prometheus`
- [ ] **Default Node metrics** scraped: `process_cpu_user_seconds_total`, `process_resident_memory_bytes`, `nodejs_eventloop_lag_seconds`, `nodejs_active_handles_total`, `nodejs_heap_size_total_bytes` - confirm `collectDefaultMetrics()` runs at startup
- [ ] **HTTP server metrics**: `prom-client` HTTP histogram registered via middleware (e.g., `express-prom-bundle` for Express; NestJS interceptor wrapping handlers) - `http_request_duration_seconds` and `http_requests_total` with route / method / status labels
- [ ] **Custom business metrics** named under a consistent namespace (`acme_orders_placed_total`, `acme_payments_failed_total`); units explicit (`Counter` for counts, `Histogram` for durations, `Gauge` for instantaneous values, `Summary` for quantile-required cases). Suffix conventions (`_total`, `_seconds`, `_bytes`) followed
- [ ] **Tag (label) cardinality bounded**: labels do not include unbounded values (`userId`, `orderId`, `requestId`) - causes metric-cardinality blow-up. Allowed label values are enums / known categories (`status`, `tenantTier`, `region`)
- [ ] **No metric registration in hot path**: `new Counter({ name, ... })` constructed at module level (or app startup), not per-request - registration in a request handler causes `Error: A metric with the name X has already been registered`
- [ ] **Cluster mode aggregation** for multi-worker deployments (PM2 cluster, Node `cluster` module): `prom-client` `AggregatorRegistry` configured to merge metrics across workers
- [ ] **Histogram buckets** chosen for the SLO: default buckets are seconds-scale; for sub-100ms paths add finer buckets (`[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]`)
- [ ] **Route label normalization**: `req.url` includes path params (`/orders/123`) - normalize to route templates (`/orders/:id`) before labeling, otherwise cardinality explodes per request

### Step 7 - BullMQ / Background Job Observability

_Skipped at `quick` depth unless the diff touches BullMQ._

Inspect BullMQ instrumentation and job observability:

- [ ] **`@opentelemetry/instrumentation-bullmq` enabled**: job spans link to dispatching request via traceparent header propagation; flag missing
- [ ] **Queue events wired** for metrics: `queue.on('completed', ...)`, `queue.on('failed', ...)`, `queue.on('stalled', ...)` increment counters and observe duration histograms; `worker.on('error', ...)` for processor crashes
- [ ] **Per-job metrics**: latency histogram, retry counter, failure counter, queue-depth gauge (via `queue.getJobCounts()` polled into a Gauge)
- [ ] **Trace context propagation across the request → BullMQ boundary**: when `queue.add(...)` is dispatched inside an HTTP request, the worker span links back to the request span (BullMQ instrumentation handles this automatically; flag manual wiring that breaks it)
- [ ] **Logger context binding inside the processor**: `jobId`, `name`, sanitized `data` bound at job start; cleared at end (NestJS uses CLS / `AsyncLocalStorage` for this; Express via `als-rtracer`)
- [ ] **Outbound HTTP from jobs instrumented**: `axios` / `fetch` / `undici` calls inside a processor body are covered by `@opentelemetry/instrumentation-http` so the worker span chains to the downstream service span; flag jobs that make uninstrumented outbound calls because the downstream timing / errors stay invisible to traces
- [ ] **Repeatable / scheduled job instrumentation**: each repeat-scheduled job emits a span; missed-execution alerting via stalled-jobs metric or queue health endpoint
- [ ] **Stalled-jobs detection**: stalled / abandoned jobs emit metrics; not silently re-processed without observability

### Step 8 - NestJS Lifecycle / Async Observability

_Skipped at `quick` depth unless the diff touches NestJS lifecycle hooks (`OnModuleInit`, `OnApplicationBootstrap`, `OnModuleDestroy`, `OnApplicationShutdown`) or `AsyncLocalStorage` context._

- [ ] **Bootstrap span**: `OnApplicationBootstrap` hook emits an `app.bootstrap` span for cold-start visibility
- [ ] **Graceful shutdown**: `OnApplicationShutdown` hook closes Prisma, BullMQ workers, OTel SDK (`sdk.shutdown()`), and flushes metrics / spans before process exit; absent shutdown drops in-flight telemetry
- [ ] **`AsyncLocalStorage` context preservation**: trace context propagates through `setImmediate`, `setTimeout`, `Promise.then` automatically (Node 16+); flag manual `context.with(...)` wraps that bypass it
- [ ] **`worker_threads` boundary**: for CPU-bound work moved to a worker thread, the trace context must be re-bound manually (forward `traceparent` header equivalent via worker message)
- [ ] **Long-running async generators / streams**: span lifecycle covers the full generator, not just creation
- [ ] **NestJS Interceptor for response timing**: response-time interceptor (or `@nestjs/throttler`'s built-in) emits histogram - flag if the only timing source is OTel auto-instrumentation when the team also wants per-route logged timings

### Step 9 - Error Tracking (Sentry / Honeybadger / Rollbar SDKs)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/API-key handling._

Inspect SDK config:

- [ ] **SDK installed and initialized** with framework integration: `Sentry.init({ integrations: [Sentry.httpIntegration(), Sentry.expressIntegration(), Sentry.prismaIntegration()] })` for Express; NestJS via `@sentry/nestjs` package
- [ ] **DSN / API key** in env var or Vault, not committed to settings
- [ ] **Release / environment tags** populated from build metadata (`release: '...'`, `environment: 'prod'`)
- [ ] **PII scrubbing on**: `sendDefaultPii: false` (default but flag if explicitly `true`); `beforeSend` strips known sensitive keys; allowlist of breadcrumb fields documented
- [ ] **OpenTelemetry / pino correlation forwarded**: error event includes `trace_id` and `userId` so incidents link back to traces / users; Sentry SDK auto-extracts trace context when OTel SDK is active (Sentry SDK 8+)
- [ ] **Sample rate explicit**: `tracesSampleRate`, `profilesSampleRate` per env; not `1.0` in prod for tracing
- [ ] **Ignored exceptions documented**: `ignoreErrors: [...]` lists classes that should not page (e.g., `BadRequestException`, validation errors when handled by exception filter); each ignore has a comment
- [ ] **Custom exception filters** (NestJS `@Catch`) / global error middleware (Express) call `Sentry.captureException(exc)` before transforming the exception to a response, so the original stack trace reaches the tracker
- [ ] **Unhandled rejection / uncaughtException**: `process.on('unhandledRejection', ...)` / `process.on('uncaughtException', ...)` capture to Sentry before exit; absent means missed errors

### Step 10 - Health Checks and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one Prometheus / OTel SLI (HTTP request rate filtered to the journey URI, success rate, p95 latency)
- [ ] **Liveness `/health` (or `/healthz`)**: returns 200 unconditionally as long as the process is responsive - no DB ping, no Redis ping, no external-API check. The Kubernetes liveness probe restarts the pod on failure; if a flaky DB connection 500s `/health`, every replica gets restarted simultaneously and the outage gets worse
- [ ] **Readiness `/ready` (or `/readyz`)**: returns 200 only when **this pod** can serve traffic - DB pool initialized, BullMQ worker connected to Redis, in-process caches warmed. Must NOT include third-party API ping - if Stripe is down, every pod fails readiness, the load balancer pulls every replica out of rotation, and you take a self-inflicted outage on a dependency outage
- [ ] **Dependency-health endpoint** (separate, e.g., `/internal/deps`): the place where Stripe / Twilio / S3 reachability lives - this is an observability signal (alert routing, dashboards), NOT a Kubernetes pod-removal signal. Confirm it is NOT wired into the readiness probe
- [ ] NestJS: `@nestjs/terminus` `HealthModule` exposes liveness via `HealthCheckService.check([])` (no checks) and readiness via `check([prisma.pingCheck, redis.pingCheck])` (own-pod deps only); third-party API checks live on a separate route, not the readiness route
- [ ] Express: custom health middleware - `app.get('/health', (req, res) => res.json({ status: 'ok' }))` for liveness; `/ready` checks Postgres pool + Redis + BullMQ queue connectivity; third-party reachability on `/internal/deps`
- [ ] SLO targets documented in code (decorator / module README) - not a free-floating Confluence page
- [ ] Synthetic probes (k6 / Artillery) call `/ready` not just `/health` - readiness reflects ability to serve


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Node.js / TypeScript (or accepted from parent dispatcher); framework and ORM recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent - the parent already gated)
- [ ] Instrumentation surfaces (logging config, OTel wiring, settings, dependencies, changed call sites) read directly before applying checklists
- [ ] Structured logging assessed: JSON output, trace / request-id correlation, sensitive-field redaction, log level discipline, no `console.log` in prod paths
- [ ] OpenTelemetry SDK and auto-instrumentation reviewed: SDK initialized BEFORE other imports, framework / DB / HTTP / BullMQ instrumentation enabled, sampling explicit, resource attributes populated
- [ ] `prom-client` metrics assessed: client on classpath, default Node + HTTP server metrics scraped, custom metric naming under namespace, label cardinality bounded, cluster mode aggregation for multi-worker deploys, route label normalization
- [ ] BullMQ observability assessed: instrumentation enabled, queue events wired, trace propagation across dispatch boundary, repeatable / scheduled job spans
- [ ] Lifecycle / async observability assessed: bootstrap / shutdown hooks, `AsyncLocalStorage` context propagation, worker thread boundary
- [ ] Error tracker integration assessed: SDK wired with framework integrations, DSN externalized, PII scrubbed, OTel correlation forwarded, sample rate explicit, unhandled rejection captured
- [ ] Findings name a Node / OTel / pino / prom-client idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/BullMQ/lifecycle/error-tracker/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Node.js Observability Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>
**Logging:** pino (JSON) | winston (JSON) | nestjs-pino | console (text) | absent
**Metrics:** prom-client | OTel metrics (Prometheus exporter) | StatsD | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
**BullMQ instrumentation:** @opentelemetry/instrumentation-bullmq | partial | absent | n/a (no BullMQ)
**Error Tracker:** Sentry | Honeybadger | Rollbar | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

_The 5-row verdict from Step 3, repeated here as the top-line read for the reviewer. Each row is `wired | partial | absent` plus a one-line citation._

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| Logging                | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| prom-client / metrics  | wired / partial / absent       | [...]                                      |
| BullMQ instrumentation | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ of the rows above are `absent` - it tells the reader the review is scaffolding, not auditing, and changes how they prioritize. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Node idiom: missing pino redaction for `req.headers.authorization`, unbounded label cardinality on `userId`, OTel SDK initialized after `app.module` import (auto-instrumentation does not patch), missing `@opentelemetry/instrumentation-bullmq`, etc.]
- **Impact:** [diagnosability / alertability / cost cost]
- **Fix:** [specific Node / OTel / pino / prom-client change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Logging / Tracing / Metrics / BullMQ / Error Tracker / Lifecycle) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Move `tracing.ts` initialization to `--require` flag in `package.json scripts.start`", "Add `@opentelemetry/instrumentation-bullmq` for cross-broker trace propagation", "Switch from per-request `new Counter(...)` to module-level constants"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Bind `orderId` via `als.run({ orderId }, () => ...)` at OrdersService.place entry; clear in finally"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/metrics` endpoint to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Node / OTel / pino / prom-client idiom ("add metrics" vs "register `prom-client.Counter` named `acme_orders_placed_total` at module level with bounded labels")
- Recommending generic observability advice when a Node SDK or auto-instrumentation exists (say "enable `@opentelemetry/instrumentation-nestjs-core`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high label cardinality (`userId`, `orderId`) as acceptable - metric series cost compounds; require enum / category labels
- Approving template-string logging (`logger.info(`processing order=${orderId}`)`) over structured form (`logger.info({ orderId }, 'processing')`) - the rendered string locks the formatter and prevents log-aggregation tools from parsing fields
- Suggesting `console.log` / `console.error` as logging - flag for replacement with the structured logger
- Approving `new Counter(...)` registration inside a request handler - causes duplicate-registration crashes after the first request
- Approving `OTEL_TRACES_SAMPLER=always_on` in prod for high-traffic services - cost and storage compound
- Approving OTel SDK initialization AFTER application imports - auto-instrumentation cannot patch already-loaded modules; must be the first import or via `--require`
- Prescribing the OTLP endpoint URL or the Sentry DSN value - say "sourced from env / Vault" and stop; concrete URLs are infra config, not source-code review
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
- Producing only `pino` recommendations when the team is on `winston` - both are acceptable JSON loggers if redaction and OTel correlation are wired
