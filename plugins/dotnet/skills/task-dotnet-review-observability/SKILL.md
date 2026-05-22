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

Stack-specific delegate of `task-code-review-observability` for .NET. Reviews whether production behavior is visible, diagnosable, and alertable at the library / SDK level. Infra-level concerns (Datadog dashboards, Grafana panels, alert rules, log forwarder config) are out of scope.

## When to Use

- Reviewing a .NET / ASP.NET Core PR for observability regressions or new instrumentation
- Pre-release check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / structured logging / Prometheus metrics
- Auditing background-worker / MassTransit / Hangfire tracing across the request -> job boundary

**Not for:** general .NET review (`task-dotnet-review`); perf with a known bottleneck (`task-dotnet-review-perf`); active incident (`/task-oncall-start`); infra-level dashboards / alert rules / log forwarders.

## Depth Levels

| Depth      | When to Use                                      | What Runs                                        |
| ---------- | ------------------------------------------------ | ------------------------------------------------ |
| `quick`    | Single endpoint, handler, or job                 | Steps 1-6 only (logging + metrics)               |
| `standard` | Default - full review                            | Steps 1-10                                       |
| `deep`     | Pre-release of a critical service, or post-incident | All steps + SLI/SLO suggestions (Step 11)     |

Default: `standard`.

## Invocation

| Invocation                                   | Meaning                                                                                               |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch                                   |
| `/task-dotnet-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-dotnet-review-observability pr-<N>`   | Review PR head fetched into local branch `pr-<N>` (user runs the fetch first)                         |

When invoked as a subagent of `task-code-review-observability` or `task-dotnet-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 is skipped.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm Stack and Detect Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If invoked as a subagent of a .NET-aware parent, accept the pre-confirmed stack. If the stack is not .NET, stop and direct the user to `/task-code-review-observability`.

Record data access (EF Core / Dapper / mixed) and messaging (MassTransit / Hangfire / Channel / none).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`; reuse them for all subsequent steps. Skip if a parent dispatcher passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface it verbatim and stop. Never run state-changing git commands.

### Step 4 - Map the Instrumentation Surface

Produce a 6-row Surface Map (verdict + one-line citation per surface). Verdicts:

- `wired` = SDK registered AND supporting wiring present (correlation enrichers, auto-instrumentations, `Description`/`Unit` on instruments, redaction policies)
- `partial` = SDK registered but something material is missing or misused
- `absent` = no registration in `Program.cs` / `appsettings.json` / `.csproj` / `Directory.Packages.props`

Surfaces: Structured logging, OpenTelemetry SDK, Metrics exporter, dotnet-counters / dotnet-monitor, Messaging instrumentation, Error tracker.

Read these files so findings cite real lines:

- `Program.cs` / `appsettings.json` - OTel wiring (`services.AddOpenTelemetry().WithTracing(...).WithMetrics(...)`), Serilog (`Host.UseSerilog(...)`), instrumentation registration, env vars (`OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`), Sentry / Application Insights connection string
- `.csproj` / `Directory.Packages.props` - presence of `OpenTelemetry.*`, `Serilog.AspNetCore`, `Sentry.AspNetCore` / `Microsoft.ApplicationInsights.AspNetCore`
- Every changed file that calls `_logger.Log*`, registers `Meter` / `Counter<T>` / `Histogram<T>`, defines middleware, or uses `ActivitySource` / `Activity.Current`
- Every changed `Migrations/` file - new business columns (status, lifecycle, ownership) imply business events; flag schema changes with no instrumentation as a Medium finding (`Schema change without instrumentation`)

**Greenfield grouping.** When a surface is `absent`, produce **one** High-Impact finding for that surface listing the missing pieces grouped by the file they should land in - not one finding per checkbox.

**Greenfield exception.** When 3+ Surface Map rows are `absent`, run Steps 8-10 at every depth regardless of the per-step diff-touch gate. On a greenfield service the absence is itself the finding.

### Step 5 - Structured Logging (Serilog / `Microsoft.Extensions.Logging`)

- [ ] Production logger emits JSON (`CompactJsonFormatter` / `JsonFormatter`; or `AddJsonConsole`)
- [ ] Correlation fields present: `TraceId`, `SpanId`, `RequestId`, `UserId`, `TenantId`, business IDs (`OrderId`) via `Enrich.FromLogContext()` + `LogContext.PushProperty(...)` or `_logger.BeginScope(...)`
- [ ] When OTel SDK is `absent`, do not recommend OTel-derived `TraceId` as the fix; recommend Serilog `Enrich.FromLogContext()` + scoped properties now, OTel as a follow-up
- [ ] Sensitive-field redaction: `Destructure.ByTransforming<User>(u => new { u.Id, u.TenantId })` or custom `IDestructuringPolicy` / `ILogEventEnricher` strips `password`, `token`, `Authorization`, `Cookie`, `ssn`
- [ ] No entity destructuring (`{@User}`) - leaks columns. Log specific fields with positional placeholders
- [ ] Named placeholders, not string interpolation. Roslyn CA2254 catches this:

  ```csharp
  // bad: template lost, aggregator cannot field-extract
  _logger.LogInformation($"Processing order {orderId}");
  // good
  _logger.LogInformation("Processing order {OrderId}", orderId);
  ```

- [ ] Log levels disciplined; framework chatter filtered (`Microsoft.AspNetCore.*: Warning`, `Microsoft.EntityFrameworkCore.Database.Command: Warning`)
- [ ] No `Console.WriteLine` in production code paths
- [ ] No log spam in hot loops / high-TPS workers (sample or use `LogDebug`)
- [ ] Exception logged as first positional, not `.Message`:

  ```csharp
  // bad: loses stack and inner chain
  _logger.LogError("Failed to load order {OrderId}: {Message}", id, ex.Message);
  // good
  _logger.LogError(ex, "Failed to load order {OrderId}", id);
  ```

### Step 6 - Metrics (`System.Diagnostics.Metrics.Meter` / Prometheus)

- [ ] Prometheus exporter installed and `/metrics` exposed (`AddPrometheusExporter()` + `app.MapPrometheusScrapingEndpoint()`, or `prometheus-net.AspNetCore`); bound on a separate admin port via Kestrel when scraping should not share the public port
- [ ] Default instrumentation registered: `AddAspNetCoreInstrumentation()`, `AddHttpClientInstrumentation()`, `AddRuntimeInstrumentation()`, `AddProcessInstrumentation()`
- [ ] HTTP server route tag is the **route template** (`/api/orders/{id}`), not actual path - otherwise cardinality explodes
- [ ] Custom metric naming follows OTel semantic conventions (dot-separated, lowercase): `acme.orders.placed.count`. Snake_case (`orders_placed`) is a flag
- [ ] Tag cardinality bounded - no `user_id`, `order_id`, `request_id` as tag values; only enums / known categories
- [ ] `Description` and `Unit` set on every instrument:

  ```csharp
  meter.CreateCounter<long>(
      "acme.orders.placed.count",
      unit: "{orders}",
      description: "Number of orders placed");
  ```

- [ ] Histogram buckets explicit for the SLO via Views when sub-100ms paths need finer resolution than the OTel defaults

### Step 7 - OpenTelemetry SDK and Auto-Instrumentation

_Skipped at `quick` depth unless the diff touches OTel wiring or `ActivitySource`._

- [ ] OTel SDK initialized in `Program.cs` BEFORE `app.Run()` so middleware does not capture the no-op tracer
- [ ] OTLP exporter configured via env (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`); do not hardcode endpoint URLs in source
- [ ] Resource attributes populated (`service.name`, `service.version`, `deployment.environment`) via `.ConfigureResource(r => r.AddService(...).AddAttributes(...))`
- [ ] Sampling explicit: `ParentBasedSampler(new TraceIdRatioBasedSampler(rate))` per env; not `AlwaysOnSampler` in high-traffic prod
- [ ] ASP.NET Core instrumentation filters `/health`, `/livez`, `/readyz` from traces
- [ ] EF Core instrumentation registered when EF Core is used; `SetDbStatementForText = false` if queries may carry PII
- [ ] `AddHttpClientInstrumentation()` registered - propagates `traceparent` on outbound calls automatically
- [ ] Custom `ActivitySource` for business operations; source registered in `WithTracing(...).AddSource("Acme.Orders")`; do not wrap a single EF query (the EF span already covers it)
- [ ] Activity tags set after value is known; cardinality bounded (no `user_id` raw)
- [ ] Error paths set status and capture exception:

  ```csharp
  catch (Exception ex) {
      activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
      activity?.AddException(ex); throw;
  }
  ```

### Step 8 - dotnet-counters / Runtime Diagnostics

_Skipped at `quick` depth unless the diff touches diagnostic enablement or `EventCounters`._

- [ ] `dotnet-counters` runnable in non-prod; runbook / CI documents the command
- [ ] New `EventSource` + `EventCounter` in new code is a smell; prefer `Meter` / `Counter<T>` / `Histogram<T>` (integrates with OTel)
- [ ] `dotnet-monitor` sidecar used for prod heap dumps / on-demand traces; flag if the diff exposes raw EventPipe ports or starts trace sessions in-process
- [ ] `dotnet-monitor` / diagnostic ports NOT exposed on a public bind without auth in prod - flag and delegate to `task-dotnet-review-security`

### Step 9 - Background Workers / MassTransit / Hangfire

_Skipped at `quick` depth unless the diff touches workers / brokers._

- [ ] Trace context propagated across the dispatch boundary. MassTransit's OTel integration handles this when `AddSource("MassTransit")` is registered. Hangfire requires manual: capture `Activity.Current.TraceId` as a job argument, restore on the worker by starting a child activity with the parent context
- [ ] Per-job metrics: latency histogram, retry counter, failure counter, queue-depth gauge
- [ ] Logger context bound at job start (`_logger.BeginScope` or `LogContext.PushProperty` for `JobId`, `JobType`, sanitized payload fields)
- [ ] Outbound HTTP from jobs uses `HttpClient` (instrumented), not bare `WebRequest`
- [ ] Scheduled / recurring jobs emit a span per execution; missed-execution alerting via stalled-job metric
- [ ] Hangfire dashboard requires auth in prod (`DashboardOptions { Authorization = ... }`); also a security finding
- [ ] Bare-loop workers have minimum signal: one structured log per iteration start, a `Counter<long>` for processed / failed outcomes, an outer `try/catch` logging the exception and incrementing the failure counter

### Step 10 - Lifecycle / Shutdown / Health Checks

_Skipped at `quick` depth unless the diff touches lifecycle (`IHostApplicationLifetime`, `IHostedService`, `Program.cs`)._

- [ ] `IHostApplicationLifetime.ApplicationStopping` used for cleanup; `BackgroundService.ExecuteAsync` exits when `stoppingToken` cancels; do not block past `HostOptions.ShutdownTimeout` (default 30s)
- [ ] OTel `TracerProvider.Shutdown()` covered by `services.AddOpenTelemetry()` hosted service; flag manual `Sdk.CreateTracerProviderBuilder()` that bypasses it
- [ ] `Channel<T>` writers call `Writer.Complete()` on shutdown; MassTransit / Hangfire bus stop via their hosted services (not bypassed)

- [ ] **Health checks split three ways - flag at any depth on multi-replica services:**

  - **`/livez` (kubelet restart gate)** - `Predicate = _ => false`. **No dependency checks.** A bare `MapHealthChecks("/health")` wired to the liveness probe causes restart cascades on transient downstream blips
  - **`/readyz` (LB gate)** - `Predicate = c => c.Tags.Contains("ready")`. Own-pod dependencies only (DB pool, Redis, in-process queue). **No third-party API pings** (`AddUrlGroup("https://api.stripe.com/...", tags: ["ready"])` flag as High - takes every replica out of the LB on an upstream outage). For upstream resilience, use a Polly v8 circuit breaker on the call site
  - **`/internal/deps` (dashboards only, NOT a probe)** - optional deep endpoint pinging every dependency including third parties; per-dependency JSON via `UIResponseWriter.WriteHealthCheckUIResponse`

### Step 11 - Error Tracking (Sentry / Application Insights)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN handling._

- [ ] SDK initialized: Sentry `AddSentry(...)` + `UseSentryTracing()`, or `AddApplicationInsightsTelemetry()`
- [ ] DSN / connection string from env / Vault, not committed
- [ ] Release and environment tags from build metadata
- [ ] PII scrubbed: Sentry `SendDefaultPii = false`; `BeforeSend` strips known sensitive keys; AI `ITelemetryProcessor` for filtering. Flag `SendDefaultPii = true` as High
- [ ] `Sentry.Extensions.Logging` wired so `_logger.LogError(...)` becomes Sentry events
- [ ] Trace correlation: error events carry `TraceId` and `UserId` (Sentry .NET SDK reads active `Activity`)
- [ ] Sample rate explicit (`TracesSampleRate = 0.1` per env), not `1.0` in prod
- [ ] Ignored domain exceptions (`NotFoundException`, `ValidationException`) filtered via `BeforeSend` / `IgnoreExceptions`, each with a comment
- [ ] `BackgroundService` exceptions surface to the error tracker

### Step 12 - SLIs and Health Endpoint Depth (deep only)

- [ ] Critical journeys have a Prometheus / OTel SLI (request rate, success rate, p95 latency)
- [ ] Per-dependency health checks registered (DB / cache / broker / external) with JSON output via `UIResponseWriter.WriteHealthCheckUIResponse` so probes can distinguish DB-down from worker-stuck
- [ ] SLO targets documented in code (`src/Slos/*.cs` or module README), not free-floating in Confluence

### Step 13 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the assembled output to the report file before ending; print the confirmation line.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed as .NET / ASP.NET Core (or accepted from parent); data access + messaging recorded
- [ ] Step 3 - precondition-check ran (or handle received); diff + log read once and reused
- [ ] Step 4 - 6-row Surface Map produced with verdict + citation; greenfield grouping applied when surfaces absent
- [ ] Step 5 - logging assessed (JSON formatter, correlation, redaction, named placeholders, no `Console.WriteLine`, exception as first positional)
- [ ] Step 6 - metrics assessed (exporter exposed, default instrumentations, route template tag, OTel naming, bounded cardinality, `Description`/`Unit`)
- [ ] Step 7 - OTel SDK reviewed (init before `app.Run()`, OTLP via env, resource attrs, sampler, EF/HTTP/MassTransit instrumentation, custom `ActivitySource`, error status)
- [ ] Step 8 - dotnet-counters / dotnet-monitor presence and prod auth gating assessed
- [ ] Step 9 - workers / MassTransit / Hangfire assessed (trace propagation, per-job metrics, scoped logging, bare-loop minimum signal)
- [ ] Step 10 - lifecycle and three-way health-check split assessed
- [ ] Step 11 - error tracker assessed (SDK wired, DSN externalized, PII scrubbed, trace correlation, sample rate, background-worker capture)
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
**Messaging instrumentation:** wired | partial | absent | n/a
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

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent`. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

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

[Structural improvements not tied to a specific finding - e.g., extract OTel init to `Observability/Telemetry.cs`, move to module-level `Meter` with `Description`/`Unit`, bind Prometheus to a separate admin port, wire `Sentry.Extensions.Logging`.]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, dashboards, ops). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: ops] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Generic advice when a .NET SDK exists ("add HTTP tracing" instead of "register `AddHttpClientInstrumentation()`")
- Reviewing infra-level concerns (Datadog SaaS, Grafana alerts, log forwarders, on-call rotation)
- Approving high-cardinality metric tags (`user_id`, `order_id`, `request_id`)
- Approving string-interpolation logging or bare `.Message` on `LogError` over the exception positional
- Approving `Console.WriteLine` in production code paths
- Approving `Meter` instruments without `Description` and `Unit`
- Approving `AlwaysOnSampler` in high-traffic prod
- Approving OTel SDK initialization AFTER `app.Build()` and middleware registration
- Approving Hangfire / Swagger UI / `dotnet-monitor` on a public bind without auth in prod
- Prescribing concrete OTLP endpoint URLs or Sentry DSN values (those are env / Vault config)
- Producing one finding per missing checkbox when a whole surface is absent - collapse per the Step 4 grouping rule
- Approving `_logger.LogError("...{Message}", ex.Message)` over `_logger.LogError(ex, "...")`
