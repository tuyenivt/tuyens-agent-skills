---
name: task-dotnet-review-observability
description: ".NET observability review: Serilog structured logging, OpenTelemetry SDK, Prometheus metrics, dotnet-counters, health checks, Sentry."
agent: dotnet-tech-lead
metadata:
  category: backend
  tags: [dotnet, aspnet-core, observability, serilog, opentelemetry, prometheus, dotnet-counters, sentry, application-insights, workflow]
  type: workflow
user-invocable: true
---

# .NET Observability Review

Stack-specific delegate of `task-code-review-observability` for .NET. Library / SDK level only; infra (Datadog dashboards, Grafana panels, alert rules, log forwarders) is out of scope.

## When to Use

- .NET / ASP.NET Core PR for observability regressions or new instrumentation
- Pre-release check for a new service or major feature
- Post-incident review when diagnosis was slow
- Adopting OpenTelemetry / structured logging / Prometheus metrics
- Auditing worker tracing across the request -> job boundary

**Not for:** general .NET review (`task-dotnet-review`); perf with a known bottleneck (`task-dotnet-review-perf`); active incident (`/task-oncall-start`); infra dashboards / alert rules / log forwarders.

## Depth Levels

| Depth      | When                                                | Runs                                       |
| ---------- | --------------------------------------------------- | ------------------------------------------ |
| `quick`    | Single endpoint, handler, or job                    | Steps 1-6 only (logging + metrics)         |
| `standard` | Default                                             | Steps 1-11                                 |
| `deep`     | Pre-release of a critical service, or post-incident | All steps + SLI/SLO (Step 12)              |

Default: `standard`.

## Invocation

| Invocation                                   | Meaning                                                                       |
| -------------------------------------------- | ----------------------------------------------------------------------------- |
| `/task-dotnet-review-observability`          | Current branch vs base; fails fast on a trunk branch                          |
| `/task-dotnet-review-observability <branch>` | `<branch>` vs base (3-dot diff)                                               |
| `/task-dotnet-review-observability pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)                         |

When invoked as a subagent of `task-code-review-observability` or `task-dotnet-review`, parent passes the precondition handle plus the pre-read diff and commit log; Step 3 is skipped.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect`. If not .NET, stop and route to `/task-code-review-observability`. Accept a parent's pre-confirmed stack.

Record data access (EF Core / Dapper / mixed) and messaging (MassTransit / Hangfire / Channel / none).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. If precondition stops with a fail-fast message, surface verbatim and stop. Never run state-changing git. Skip if parent dispatched the handle plus artifacts.

### Step 4 - Map the Instrumentation Surface

Produce a 6-row Surface Map (verdict + one-line citation per surface):

- `wired` = SDK registered AND supporting wiring present (correlation enrichers, auto-instrumentations, `Description`/`Unit` on instruments, redaction policies)
- `partial` = SDK registered but something material is missing or misused
- `absent` = no registration in `Program.cs` / `appsettings.json` / `.csproj` / `Directory.Packages.props`

Surfaces: Structured logging, OpenTelemetry SDK, Metrics exporter, dotnet-counters / dotnet-monitor, Messaging instrumentation, Error tracker.

Read so findings cite real lines: `Program.cs`, `appsettings.json`, `.csproj` / `Directory.Packages.props`, every changed file touching `_logger.Log*` / `Meter` / `Counter<T>` / `Histogram<T>` / `ActivitySource` / middleware, every changed `Migrations/` file (new business columns -> business events; schema change without instrumentation is Medium).

**Greenfield grouping.** When a surface is `absent`, file **one** High-Impact finding for that surface listing missing pieces grouped by target file - not one finding per checkbox.

**Greenfield exception.** When 3+ Surface Map rows are `absent`, run Steps 8-11 at every depth.

### Step 5 - Structured Logging (Serilog / `Microsoft.Extensions.Logging`)

- [ ] Production logger emits JSON (`CompactJsonFormatter` / `JsonFormatter`; or `AddJsonConsole`)
- [ ] Correlation fields: `TraceId`, `SpanId`, `RequestId`, `UserId`, `TenantId`, business IDs (`OrderId`) via `Enrich.FromLogContext()` + `LogContext.PushProperty(...)` or `_logger.BeginScope(...)`
- [ ] When OTel SDK is `absent`, recommend `Enrich.FromLogContext()` + scoped properties now, OTel as follow-up
- [ ] Sensitive-field redaction: `Destructure.ByTransforming<User>(u => new { u.Id, u.TenantId })` or custom `IDestructuringPolicy` strips `password`, `token`, `Authorization`, `Cookie`, `ssn`
- [ ] No entity destructuring (`{@User}`) - leaks columns
- [ ] Named placeholders, not interpolation (CA2254): `_logger.LogInformation("Order {OrderId}", id)`, not `$"Order {id}"`
- [ ] Log levels disciplined; framework chatter filtered (`Microsoft.AspNetCore.*: Warning`, `Microsoft.EntityFrameworkCore.Database.Command: Warning`)
- [ ] No `Console.WriteLine` in production code paths
- [ ] No log spam in hot loops (sample or `LogDebug`)
- [ ] Exception as first positional, not `.Message`: `_logger.LogError(ex, "Failed {OrderId}", id)`, not `LogError("...{Message}", ex.Message)` (loses stack + inner chain)

### Step 6 - Metrics (`System.Diagnostics.Metrics.Meter` / Prometheus)

- [ ] Prometheus exporter exposed (`AddPrometheusExporter()` + `app.MapPrometheusScrapingEndpoint()`, or `prometheus-net.AspNetCore`); bind to a separate admin port via Kestrel when scraping should not share the public port
- [ ] Default instrumentation registered: `AddAspNetCoreInstrumentation()`, `AddHttpClientInstrumentation()`, `AddRuntimeInstrumentation()`, `AddProcessInstrumentation()`
- [ ] HTTP server route tag is the **route template** (`/api/orders/{id}`), not actual path - otherwise cardinality explodes
- [ ] Custom names follow OTel conventions (dot-separated, lowercase): `acme.orders.placed.count`. Snake_case is a flag
- [ ] Tag cardinality bounded - no `user_id`, `order_id`, `request_id` as tag values; only enums / known categories
- [ ] `Description` and `Unit` set on every instrument
- [ ] Histogram buckets explicit via Views when sub-100ms SLO paths need finer resolution than OTel defaults

### Step 7 - OpenTelemetry SDK and Auto-Instrumentation

_Skipped at `quick` unless the diff touches OTel wiring or `ActivitySource`._

- [ ] OTel SDK initialized in `Program.cs` BEFORE `app.Run()` so middleware does not capture the no-op tracer
- [ ] OTLP exporter via env (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`); endpoint not hardcoded
- [ ] Resource attributes (`service.name`, `service.version`, `deployment.environment`) via `.ConfigureResource(r => r.AddService(...))`
- [ ] Sampling explicit: `ParentBasedSampler(new TraceIdRatioBasedSampler(rate))`; not `AlwaysOnSampler` in high-traffic prod
- [ ] ASP.NET Core instrumentation filters `/health`, `/livez`, `/readyz`
- [ ] EF Core instrumentation registered when EF Core is used; `SetDbStatementForText = false` if queries may carry PII
- [ ] `AddHttpClientInstrumentation()` registered (propagates `traceparent`)
- [ ] Custom `ActivitySource` for business operations, registered in `WithTracing(...).AddSource("Acme.Orders")`; don't wrap a single EF query (EF span already covers it)
- [ ] Activity tags set after value known; cardinality bounded
- [ ] Error paths: `activity?.SetStatus(ActivityStatusCode.Error, ex.Message); activity?.AddException(ex);`

### Step 8 - dotnet-counters / Runtime Diagnostics

_Skipped at `quick` unless the diff touches diagnostic enablement or `EventCounters`._

- [ ] `dotnet-counters` runnable in non-prod; runbook / CI documents the command
- [ ] New `EventSource` + `EventCounter` is a smell; prefer `Meter` / `Counter<T>` / `Histogram<T>` (integrates with OTel)
- [ ] `dotnet-monitor` sidecar for prod heap dumps / on-demand traces; flag raw EventPipe ports or in-process trace sessions
- [ ] Diagnostic ports NOT exposed on a public bind without auth in prod - flag and delegate to `task-dotnet-review-security`

### Step 9 - Background Workers / MassTransit / Hangfire

_Skipped at `quick` unless the diff touches workers / brokers._

- [ ] Trace context propagated across dispatch. MassTransit handles this when `AddSource("MassTransit")` is registered. Hangfire is manual: capture `Activity.Current.TraceId` as a job argument, restore on the worker by starting a child activity with the parent context
- [ ] Per-job metrics: latency histogram, retry counter, failure counter, queue-depth gauge
- [ ] Logger context bound at job start (`BeginScope` / `LogContext.PushProperty` for `JobId`, `JobType`, sanitized payload fields)
- [ ] Outbound HTTP from jobs uses `HttpClient` (instrumented), not bare `WebRequest`
- [ ] Scheduled jobs emit a span per execution; missed-execution alerting via stalled-job metric
- [ ] Hangfire dashboard requires auth in prod (`DashboardOptions { Authorization = ... }`); also a security finding
- [ ] Bare-loop workers have minimum signal: one log per iteration start, a `Counter<long>` for processed / failed, outer `try/catch` logging the exception and incrementing failure

### Step 10 - Lifecycle / Shutdown / Health Checks

_Skipped at `quick` unless the diff touches lifecycle (`IHostApplicationLifetime`, `IHostedService`, `Program.cs`)._

- [ ] `ApplicationStopping` used for cleanup; `BackgroundService.ExecuteAsync` exits when `stoppingToken` cancels; doesn't block past `HostOptions.ShutdownTimeout` (30s default)
- [ ] OTel `TracerProvider.Shutdown()` covered by `services.AddOpenTelemetry()` hosted service; flag manual `Sdk.CreateTracerProviderBuilder()` that bypasses it
- [ ] `Channel<T>` writers call `Writer.Complete()` on shutdown; MassTransit / Hangfire bus stops via hosted services
- [ ] **Health checks split three ways - flag at any depth on multi-replica services:**
  - **`/livez` (kubelet restart gate):** `Predicate = _ => false`. **No dependency checks.** Bare `MapHealthChecks("/health")` wired to liveness causes restart cascades on transient downstream blips
  - **`/readyz` (LB gate):** `Predicate = c => c.Tags.Contains("ready")`. Own-pod dependencies only (DB pool, Redis, in-process queue). **No third-party API pings** (e.g., `AddUrlGroup("https://api.stripe.com/...", tags: ["ready"])` flag as High - takes every replica out of the LB on an upstream outage). Use a Polly v8 circuit breaker on the call site instead
  - **`/internal/deps` (dashboards only, NOT a probe):** optional deep endpoint pinging every dependency; per-dependency JSON via `UIResponseWriter.WriteHealthCheckUIResponse`

### Step 11 - Error Tracking (Sentry / Application Insights)

_Skipped at `quick` unless the diff modifies error handlers, error-tracker config, or DSN handling._

- [ ] SDK initialized: Sentry `AddSentry(...)` + `UseSentryTracing()`, or `AddApplicationInsightsTelemetry()`
- [ ] DSN / connection string from env / Vault, not committed
- [ ] Release and environment tags from build metadata
- [ ] PII scrubbed: Sentry `SendDefaultPii = false`; `BeforeSend` strips known sensitive keys; AI `ITelemetryProcessor` for filtering. `SendDefaultPii = true` is High
- [ ] `Sentry.Extensions.Logging` wired so `_logger.LogError(...)` becomes Sentry events
- [ ] Error events carry `TraceId` and `UserId` (Sentry .NET reads active `Activity`)
- [ ] Sample rate explicit (`TracesSampleRate = 0.1`), not `1.0` in prod
- [ ] Domain-noise exceptions (`NotFoundException`, `ValidationException`) filtered via `BeforeSend` / `IgnoreExceptions` with a comment
- [ ] `BackgroundService` exceptions surface to the error tracker

### Step 12 - SLIs and Health Endpoint Depth (deep only)

- [ ] Critical journeys have an SLI (request rate, success rate, p95 latency)
- [ ] Per-dependency health checks with JSON output via `UIResponseWriter.WriteHealthCheckUIResponse` so probes can distinguish DB-down from worker-stuck
- [ ] SLO targets documented in code (`src/Slos/*.cs` or module README), not free-floating in Confluence

### Step 13 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the assembled output to the report file; print the confirmation line.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed as .NET / ASP.NET Core (or accepted from parent); data access + messaging recorded
- [ ] Step 3 - precondition-check ran (or handle received); diff + log read once
- [ ] Step 4 - 6-row Surface Map produced with verdict + citation; greenfield grouping applied when surfaces absent
- [ ] Step 5 - logging assessed
- [ ] Step 6 - metrics assessed
- [ ] Step 7 - OTel SDK assessed
- [ ] Step 8 - dotnet-counters / dotnet-monitor assessed
- [ ] Step 9 - workers / MassTransit / Hangfire assessed
- [ ] Step 10 - lifecycle and three-way health-check split assessed
- [ ] Step 11 - error tracker assessed
- [ ] Step 12 - at `deep`, SLIs and per-dependency health depth assessed
- [ ] Step 13 - report written via `review-report-writer`; confirmation line printed

## Output Format

```markdown
## .NET Observability Review Summary

**Stack Detected:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Messaging:** MassTransit | Hangfire | Channel | none
**Logging:** Serilog (JSON) | Microsoft.Extensions.Logging (AddJsonConsole) | text | absent
**Metrics:** OpenTelemetry + Prometheus | prometheus-net.AspNetCore | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (other exporter) | absent
**dotnet-counters / dotnet-monitor:** runnable (non-prod) | runnable (prod via sidecar) | exposed (public, prod) [security finding] | absent
**Error Tracker:** Sentry | Application Insights | absent
**Overall:** Adequate | Gaps Found - [count by impact] | Greenfield - no observability surface wired [count by impact]

## Surface Map

| Surface                          | Verdict                        | Evidence                                   |
| -------------------------------- | ------------------------------ | ------------------------------------------ |
| Structured logging               | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK                | wired / partial / absent       | [...]                                      |
| Metrics exporter                 | wired / partial / absent       | [...]                                      |
| dotnet-counters / dotnet-monitor | wired / partial / absent       | [...]                                      |
| Messaging instrumentation        | wired / partial / absent / n/a | [...]                                      |
| Error tracker                    | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent`. Use the same `absent` vocabulary throughout (don't mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the .NET idiom: missing destructuring policy for `User` (leaks `PasswordHash`), unbounded tag cardinality on `user_id`, OTel SDK initialized after `app.Build()`, missing `AddHttpClientInstrumentation`, route tag is actual path not template, Hangfire dashboard exposed without auth, `SendDefaultPii = true`, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Serilog / OTel / `Meter` change with code]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty sections. Group findings by surface (Logging / Tracing / Metrics / dotnet-counters / Messaging / Error Tracker / Lifecycle) when more than 2 share a surface. Greenfield reviews collapse a whole surface into one finding per the Step 4 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - extract OTel init to `Observability/Telemetry.cs`, move to module-level `Meter` with `Description`/`Unit`, bind Prometheus to a separate admin port, wire `Sentry.Extensions.Logging`.]

## Next Steps

Prioritized. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, dashboards, ops). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- State-changing git (`fetch`, `checkout`, etc.) - user runs these
- Generic advice when a .NET SDK exists ("add HTTP tracing" instead of "register `AddHttpClientInstrumentation()`")
- Reviewing infra-level concerns (Datadog SaaS, Grafana alerts, log forwarders, on-call rotation)
- Approving high-cardinality metric tags (`user_id`, `order_id`, `request_id`)
- Approving string-interpolation logging, bare `.Message` on `LogError`, or `Console.WriteLine` in production
- Approving `Meter` instruments without `Description` and `Unit`
- Approving `AlwaysOnSampler` in high-traffic prod, or OTel SDK init AFTER `app.Build()`
- Approving Hangfire / Swagger UI / `dotnet-monitor` on a public bind without auth in prod
- Prescribing concrete OTLP endpoint URLs or Sentry DSN values (env / Vault config)
- Producing one finding per missing checkbox when a whole surface is absent - collapse per Step 4
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
