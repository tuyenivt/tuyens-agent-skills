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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# .NET Observability Review

## Purpose

.NET-aware observability review that names `Microsoft.Extensions.Logging` (the abstraction) + Serilog (the typical structured implementation, configured via `Host.UseSerilog(...)` or `WebApplication`'s `services.AddSerilog(...)`), OpenTelemetry .NET SDK (`OpenTelemetry`, `OpenTelemetry.Extensions.Hosting`, `OpenTelemetry.Exporter.OpenTelemetryProtocol`), auto-instrumentation (`OpenTelemetry.Instrumentation.AspNetCore` for HTTP server, `OpenTelemetry.Instrumentation.EntityFrameworkCore` for EF Core, `OpenTelemetry.Instrumentation.Http` for `HttpClient`, MassTransit's built-in OTel integration), `System.Diagnostics.Metrics.Meter` + `Counter<T>` / `Histogram<T>` instruments (the modern .NET 6+ API replacing `EventCounters` for new code), `OpenTelemetry.Exporter.Prometheus.AspNetCore` (or `prometheus-net.AspNetCore`), `dotnet-counters` / `dotnet-trace` / `dotnet-monitor` for runtime introspection, graceful shutdown via `IHostApplicationLifetime.ApplicationStopping` / `IHostedService.StopAsync`, health checks via `services.AddHealthChecks()...` + `app.MapHealthChecks(...)`, and error-tracker SDKs (`Sentry.AspNetCore`, `Microsoft.ApplicationInsights.AspNetCore`) directly instead of routing through the generic adapter. Focuses on whether .NET production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for .NET. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a .NET / ASP.NET Core PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new .NET service or major feature
- Post-incident review when .NET diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / structured logging / Prometheus metrics in a .NET app
- Auditing background-worker / MassTransit tracing and correlation across the request → job boundary

**Not for:**

- General .NET code review (use `task-dotnet-review`)
- .NET performance issues with a known bottleneck (use `task-dotnet-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint, handler, or job                             | Logging + Prometheus metrics check only            |
| `standard` | Default - full .NET observability review                     | All steps                                          |
| `deep`     | Pre-release of a critical .NET service, or post-incident review| All steps + SLI/SLO suggestions for .NET endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                   | Meaning                                                                                               |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-dotnet-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-dotnet-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-dotnet-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If invoked as a subagent of a .NET-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not .NET, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect data access (EF Core / Dapper / mixed) and messaging (MassTransit / Hangfire / Channel / none). Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (logging / OTel / metrics / dotnet-counters / messaging instrumentation / error tracker) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below) rather than one-per-bullet.

**Grouping rule.** When a whole surface is `absent` (no Prometheus exporter, no OTel SDK init, no error-tracker SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/class they should land in - not one finding per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. This prevents 50-item dumps on greenfield reviews.

**Verdict rubric.** Use these definitions consistently across the Surface Map and findings:

- `wired` = the SDK / formatter / exporter is registered AND the supporting wiring is present (correlation enrichers for logging, auto-instrumentations for OTel, `Description`/`Unit` on `Meter` instruments, redaction policies for sensitive fields)
- `partial` = the SDK / formatter / exporter is registered BUT something material is missing or misused (Serilog wired but a `_logger.LogInformation($"...")` string-interpolation pattern shows up; OTel SDK registered but `AddHttpClientInstrumentation()` missing; `Meter` registered but instruments lack `Description` / `Unit`). Per-callsite findings apply
- `absent` = no registration anywhere in `Program.cs` / `appsettings.json` / `.csproj` for the surface. Whole-surface grouping rule applies

Then open the files that actually configure observability so findings cite real lines, not assumptions:

- `Program.cs` / `appsettings.json` - OpenTelemetry SDK wiring (`services.AddOpenTelemetry().WithTracing(...).WithMetrics(...)`), Serilog setup (`Host.UseSerilog((ctx, lc) => lc.ReadFrom.Configuration(ctx.Configuration).Enrich.FromLogContext().WriteTo.Console(formatter: new CompactJsonFormatter()))`), instrumentation registration (`AddAspNetCoreInstrumentation()`, `AddEntityFrameworkCoreInstrumentation()`, `AddHttpClientInstrumentation()`)
- `appsettings.json` / config - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, log levels, Sentry / Application Insights connection string, Prometheus scrape port
- `.csproj` / `Directory.Packages.props` - confirm `OpenTelemetry`, `OpenTelemetry.Extensions.Hosting`, `OpenTelemetry.Instrumentation.AspNetCore`, `OpenTelemetry.Instrumentation.EntityFrameworkCore`, `OpenTelemetry.Instrumentation.Http`, `OpenTelemetry.Exporter.OpenTelemetryProtocol`, `OpenTelemetry.Exporter.Prometheus.AspNetCore`, `Serilog.AspNetCore`, `Sentry.AspNetCore` / `Microsoft.ApplicationInsights.AspNetCore` presence and versions
- Every changed file in the diff that calls `_logger.Log*`, registers `Meter` / `Counter<T>` / `Histogram<T>`, defines middleware, instruments with OTel `ActivitySource`, or modifies `Activity.Current` context
- Every changed file under `Migrations/` - new business columns (status, audit, ownership, lifecycle state) imply business events that should drive a `Counter` / span attribute / log property. A schema change with no corresponding observability change is itself a gap; flag it as a Medium finding (`Schema change without instrumentation`) so the implementer wires a metric or span attribute alongside the column

For diffs touching only one of these surfaces (a new endpoint but no logging change, say), still read the existing config to know whether request-id / trace correlation, instrumentation, and SDKs are wired - a missing wire is the finding.

### Step 4 - Structured Logging (`Microsoft.Extensions.Logging` / Serilog)

Inspect logging config and any `_logger.Log*` callsite in the diff:

- [ ] **Production logger emits JSON** - Serilog with `WriteTo.Console(new CompactJsonFormatter())` or `WriteTo.Console(new JsonFormatter())`; or `Microsoft.Extensions.Logging.Console` with `services.AddLogging(b => b.AddJsonConsole(...))`. No `Console.WriteLine` in production code paths
- [ ] **Correlation fields injected** in every log line: `TraceId`, `SpanId`, `RequestId`, `UserId` (when authenticated), `TenantId`, plus business correlation IDs (`OrderId`, `InvoiceId`). Wire via:
  - ASP.NET Core auto-includes `TraceId` / `SpanId` / `RequestId` when OpenTelemetry is registered; Serilog `Enrich.FromLogContext()` and `using (LogContext.PushProperty("OrderId", id)) { ... }` for business IDs
  - `_logger.BeginScope(new Dictionary<string, object> { ["OrderId"] = id })` (built-in `ILogger`) for scoped properties carrying through nested calls
- [ ] **OpenTelemetry log correlation**: with the OpenTelemetry .NET SDK active, ASP.NET Core's request-scoped logging automatically attaches the active `Activity.Current.TraceId` / `SpanId` to every log entry. Serilog enrichers (`Enrich.WithSpan()` from `Serilog.Enrichers.Span` or built-in trace context) ensure `TraceId` lands in the log JSON
- [ ] **Greenfield correlation (when OTel SDK is `absent`)**: do not recommend OTel-derived `TraceId` correlation as the fix when OTel itself isn't wired - that's a separate work item. The minimum correlation story without OTel is Serilog `Enrich.FromLogContext()` registered at host setup plus `using (LogContext.PushProperty("OrderId", id)) { ... }` (or `_logger.BeginScope(...)`) in handlers. Recommend wiring OTel as a follow-up rather than blocking on it - the in-process correlation gap is fixable today
- [ ] **Sensitive-field redaction**: a custom `ILogEventEnricher` (Serilog) or `IDestructuringPolicy` that drops `password`, `token`, `Authorization`, `Cookie`, `credit_card`, `ssn`, `api_key` keys; OR types implement custom serialization to override `ToString()` and return a redacted form. `Destructure.ByTransforming<User>(u => new { u.Id, u.TenantId })` for entity types to control logged fields
- [ ] **No `_logger.LogInformation("user: {@User}", user)` that destructures a domain entity**: the `@` destructuring operator includes every property; entity destructuring leaks sensitive columns. Always log specific fields: `_logger.LogInformation("Processing order {OrderId} for user {UserId}", id, userId)` with positional placeholders
- [ ] **User-identity fields emitted as named placeholders, not in the message string**: `_logger.LogInformation("Processing user {UserId}", userId)`, never `_logger.LogInformation($"Processing user {userId}")` (string interpolation breaks structured logging - the message template is gone, replaced by a rendered string the aggregator cannot field-extract). Roslyn analyzer `Microsoft.CodeAnalysis.NetAnalyzers` rule CA2254 catches this
- [ ] **Log levels used correctly**: `LogError` for actionable failures, `LogWarning` for recoverable anomalies, `LogInformation` for state transitions, `LogDebug` for verbose diagnostics, `LogTrace` for very fine-grained. Default `Microsoft.AspNetCore.*: Warning` and `Microsoft.EntityFrameworkCore.Database.Command: Warning` filters in `appsettings.json` to silence framework chatter at `Information`
- [ ] **No `Console.WriteLine`** in production code paths - flag for replacement with `ILogger`; `Console.WriteLine` skips redaction, structured fields, scope context, and correlation
- [ ] **No log spam in hot loops** - iterating large lists, scheduled jobs running every second, background workers at high TPS must not log per-iteration; sample or use `LogDebug`
- [ ] **Error logging includes the exception**: `_logger.LogError(ex, "Failed to load order {OrderId}", id)` - the `ex` first-positional captures the full stack; bare `_logger.LogError("Failed to load order {OrderId}: {Message}", id, ex.Message)` loses the inner exception chain and stack trace

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

Inspect OpenTelemetry config and instrumentation wiring:

- [ ] **OpenTelemetry SDK initialized in `Program.cs` BEFORE the request pipeline is built**: `services.AddOpenTelemetry().WithTracing(t => t.AddSource(...).AddAspNetCoreInstrumentation().AddOtlpExporter(...))` happens during `WebApplication.CreateBuilder(...)` configuration before `app.Run()`. Late initialization means subsequent middleware / handlers may use a no-op tracer
- [ ] **OTLP exporter configured**: `.AddOtlpExporter(o => o.Endpoint = new Uri("http://collector:4317"))` (gRPC) or `.AddOtlpExporter(o => o.Protocol = OtlpExportProtocol.HttpProtobuf)` pointed at the org's collector / backend; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` set per env
- [ ] **Resource attributes** populated: `service.name`, `service.version`, `deployment.environment`; sourced from build metadata / env vars via `.ConfigureResource(r => r.AddService(serviceName: env.ApplicationName, serviceVersion: ThisAssembly.AssemblyInformationalVersion).AddAttributes(new[] { new KeyValuePair<string, object>("deployment.environment", env.EnvironmentName) }))`
- [ ] **Sampling policy explicit**: `.SetSampler(new ParentBasedSampler(new TraceIdRatioBasedSampler(rate)))` with `rate` per env (e.g., `0.1` in prod, `1.0` in staging); not `AlwaysOnSampler` in high-traffic prod
- [ ] **ASP.NET Core auto-instrumentation**: `.AddAspNetCoreInstrumentation(o => { o.RecordException = true; o.Filter = httpContext => !httpContext.Request.Path.StartsWithSegments("/health"); })` filters out `/health` from traces (otherwise health-check spam dominates trace volume)
- [ ] **EF Core instrumentation**: `.AddEntityFrameworkCoreInstrumentation(o => { o.SetDbStatementForText = true; })` - SQL text included for diagnostic value (do not enable in environments where queries may carry PII; use `o.SetDbStatementForText = false` and rely on the operation name)
- [ ] **HTTP client instrumentation**: `.AddHttpClientInstrumentation()` propagates traceparent on outbound `HttpClient` calls automatically; bare `HttpClient` without the instrumentation does not propagate span context
- [ ] **MassTransit instrumentation**: MassTransit ships built-in OTel support - `services.AddMassTransit(...)` enables it by default; consumer spans link to producer spans via traceparent in message headers. Confirm the OTel `ActivitySource` `MassTransit` is registered in `WithTracing(...).AddSource("MassTransit")`
- [ ] **Background-worker instrumentation**: trace context propagated across the spawn boundary - either via `Activity.Current` captured before `Task.Run` / `Channel<T>` send and restored inside the worker via `Activity.Current = capturedActivity`, or via OTel's W3C `traceparent` carrier serialized into the job payload and reconstructed on the consumer
- [ ] **Custom `ActivitySource` for business operations**: `private static readonly ActivitySource Source = new("Acme.Orders");` and `using var activity = Source.StartActivity("PlaceOrder");`; register the source in `WithTracing(...).AddSource("Acme.Orders")`. No over-instrumentation (do not wrap a single EF Core query in a custom activity - the EF span already covers it)
- [ ] **Activity tags / attributes**: `activity?.SetTag("order.id", orderId)` after the value is known; keep cardinality bounded
- [ ] **`activity?.SetStatus(ActivityStatusCode.Error, "...")` on error paths**: `try { ... } catch (Exception ex) { activity?.SetStatus(ActivityStatusCode.Error, ex.Message); activity?.AddException(ex); throw; }` - propagates exception details to the span
- [ ] **`TracerProvider.Shutdown()` called on graceful shutdown** so in-flight spans flush; the OTel hosted service handles this when registered via `services.AddOpenTelemetry()` - confirm not bypassing the hosted-service registration

### Step 6 - Metrics (`System.Diagnostics.Metrics.Meter` / Prometheus exporter)

Inspect `Meter` / `Counter` / `Histogram` instruments and exporter setup:

- [ ] **Prometheus exporter installed** and `/metrics` endpoint exposed - `services.AddOpenTelemetry().WithMetrics(m => m.AddPrometheusExporter())` and `app.MapPrometheusScrapingEndpoint()` (or `prometheus-net.AspNetCore` with `app.UseHttpMetrics(); app.MapMetrics();`). Bind on a separate admin port via Kestrel endpoint config when scraping should not share the public port
- [ ] **Default ASP.NET Core / runtime metrics** scraped: `services.AddOpenTelemetry().WithMetrics(m => m.AddAspNetCoreInstrumentation().AddHttpClientInstrumentation().AddRuntimeInstrumentation().AddProcessInstrumentation())`. `AddRuntimeInstrumentation` exposes GC pause, thread pool stats, lock contention; `AddProcessInstrumentation` exposes CPU, memory, handle count
- [ ] **HTTP server metrics**: `http.server.duration` histogram and `http.server.active_requests` counter from `AddAspNetCoreInstrumentation()` carry route / method / status labels - confirm the route label is the **route template** (`/api/orders/{id}`), not the actual path (`/api/orders/123`), or cardinality explodes
- [ ] **Custom business metrics** named under a consistent namespace (`acme.orders.placed.count`, `acme.payments.failed.count`); units explicit via the `Meter` API (`meter.CreateCounter<long>("...", unit: "{operations}", description: "...")`, `meter.CreateHistogram<double>("...", unit: "ms", description: "...")`). OTel semantic-convention naming: dot-separated, lowercase
- [ ] **Tag (label) cardinality bounded**: tags do not include unbounded values (`user_id`, `order_id`, `request_id`) - causes metric-cardinality blow-up. Allowed tag values are enums / known categories (`status`, `tenant_tier`, `region`)
- [ ] **`Description` and `Unit` set on every instrument**: `meter.CreateCounter<long>("acme.orders.placed.count", unit: "{orders}", description: "Number of orders placed")` registers metadata that surfaces in Prometheus (`HELP` / `TYPE`); absence means metrics show up without metadata
- [ ] **Histogram buckets** explicit for the SLO: default OTel buckets are seconds-scale; for sub-100ms paths configure custom buckets via Views (`m.AddView(instrumentName: "http.server.duration", new ExplicitBucketHistogramConfiguration { Boundaries = new[] { 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0 } })`). Without explicit buckets, default buckets often miss the relevant percentiles
- [ ] **Multi-instance aggregation**: when running multiple replicas, Prometheus scrapes each replica; ensure no per-replica metric is mistakenly aggregated as a sum (use `rate()` + `sum by(...)` discipline at query time, not in the SDK)

> **Greenfield exception (applies to Steps 7, 8, and 9).** When 3+ rows in the Step 3 Surface Map are `absent`, run Steps 7-9 at every depth regardless of the per-step diff-touch gate. On a greenfield service the *absence* of the surface is itself the finding the gate would otherwise hide - if the diff doesn't touch `dotnet-counters` integration because no observability surface exists yet, the default skip would silently let the gap go unflagged exactly when it most matters.

### Step 7 - dotnet-counters / Runtime Introspection

_Skipped at `quick` depth unless the diff touches runtime-diagnostics enablement or `EventCounters` / `Meter` registration for runtime metrics._

- [ ] **`dotnet-counters` runnable in non-prod**: no code change needed for built-in counters (`System.Runtime`, `Microsoft.AspNetCore.Hosting`, `Microsoft.EntityFrameworkCore`); confirm CI / runbook documents the command (`dotnet-counters monitor --process-id <pid> --counters System.Runtime,Microsoft.AspNetCore.Hosting`)
- [ ] **Custom `EventCounters` only for legacy needs**: `Meter` / `Counter<T>` / `Histogram<T>` (the .NET 6+ `System.Diagnostics.Metrics` API) is the modern path and integrates with OpenTelemetry. New `EventSource` + `EventCounter` registration in new code is a smell unless interop with legacy `dotnet-counters` consumers is required
- [ ] **`dotnet-monitor` sidecar for prod diagnostics**: when a production diagnostic surface is needed (heap dumps, GC dumps, traces on demand), `dotnet-monitor` is the canonical sidecar - flag if the diff exposes raw EventPipe ports or starts trace sessions inside the app process instead
- [ ] **`AddOpenTelemetry().WithMetrics(...)` exposes runtime metrics**: confirm `AddRuntimeInstrumentation()` and `AddProcessInstrumentation()` are registered so GC, thread pool, and process-level signals are scraped
- [ ] **`dotnet-monitor` / diagnostic ports NOT exposed on a public bind without auth in prod**: this is a security finding too (`task-dotnet-review-security`) - flag for delegation if the diff exposes them on a public port without gating

### Step 8 - Background Workers / MassTransit / Hangfire Observability

_Skipped at `quick` depth unless the diff touches background workers or message brokers._

- [ ] **Trace context propagation across the dispatch boundary**: when a MassTransit message is published inside an HTTP request, the consumer span links back to the request span via the `traceparent` header that MassTransit's OTel integration injects automatically. For Hangfire, capture `Activity.Current.TraceId` and pass it as a job argument; restore on the worker side by starting a child activity with the parent context. Flag missing wiring
- [ ] **Per-job metrics**: latency histogram, retry counter, failure counter, queue-depth gauge (where the broker exposes it); MassTransit ships built-in metrics via `AddMassTransit(...)`'s OTel hook
- [ ] **Logger context binding inside the job**: `JobId`, `JobType`, sanitized payload fields bound at job start via `_logger.BeginScope(...)` or Serilog `LogContext.PushProperty(...)` so every log line within the job carries them
- [ ] **Outbound HTTP from jobs instrumented**: `HttpClient` used inside a job is instrumented automatically by `AddHttpClientInstrumentation()` so the job span chains to the downstream service span; flag jobs that bypass `HttpClient` (e.g., raw `WebRequest`) because the downstream timing / errors stay invisible to traces
- [ ] **Scheduled / recurring job instrumentation**: each Hangfire recurring job emits an activity; missed-execution alerting via stalled-job metric or queue-health endpoint
- [ ] **MassTransit consumer instrumentation**: built-in via `AddSource("MassTransit")` in `WithTracing(...)` - confirm registration; consumer spans carry the `messaging.*` semantic conventions
- [ ] **Hangfire dashboard metrics**: `app.UseHangfireDashboard("/hangfire", new DashboardOptions { Authorization = new[] { ... } })` - enabled in non-prod by default; flag if exposed without auth in prod (this is also a security finding)
- [ ] **Bare-loop workers have minimum signal**: a worker with zero logging, zero `Counter<long>`, and no try/catch around the iteration body produces no signal when it silently fails. On greenfield workers (no instrumentation present), require at minimum: one structured log line per iteration start (with the business key being processed), a `Counter<long>` for processed/failed outcomes registered on a module `Meter`, and an outer `try/catch (Exception ex) { _logger.LogError(ex, "..."); _failedCounter.Add(1, ...); }` so the worker remains observable even when not yet OTel-instrumented

### Step 9 - Lifecycle / Graceful Shutdown Observability

_Skipped at `quick` depth unless the diff touches lifecycle (`IHostApplicationLifetime`, `IHostedService`, signal handling) or `Program.cs`. The Greenfield exception above also applies to this step._

- [ ] **Graceful shutdown via `IHostApplicationLifetime`**: ASP.NET Core hooks SIGINT (Ctrl+C) and SIGTERM (Docker `docker stop`) automatically; `IHostApplicationLifetime.ApplicationStopping` fires when shutdown begins, `ApplicationStopped` when complete. Background services should subscribe to `ApplicationStopping` for cleanup
- [ ] **`IHostedService.StopAsync(CancellationToken cancellationToken)` honored**: `BackgroundService.ExecuteAsync(stoppingToken)` exits cleanly when `stoppingToken.IsCancellationRequested` becomes true; do not block in `StopAsync` past the token deadline
- [ ] **Bounded shutdown timeout**: `services.Configure<HostOptions>(o => o.ShutdownTimeout = TimeSpan.FromSeconds(30))` so shutdown does not hang indefinitely; default is 30s on .NET 6+
- [ ] **OTel `TracerProvider.Shutdown()`**: handled by the OpenTelemetry hosted service registered via `services.AddOpenTelemetry()`; confirm not bypassing the hosted-service registration (manual `Sdk.CreateTracerProviderBuilder()` without hosted service skips graceful shutdown)
- [ ] **`Channel<T>` writer completed on shutdown**: producers call `channel.Writer.Complete()` so `await foreach (var item in reader.ReadAllAsync(token))` exits cleanly
- [ ] **EF Core `DbContext` pool drained on shutdown**: handled by the DI container disposing scoped services; explicit `await dbContext.DisposeAsync()` not needed unless using a manually managed `DbContext` factory
- [ ] **MassTransit / Hangfire bus stopped**: MassTransit's hosted service stops on app shutdown; Hangfire's `BackgroundJobServer` likewise. Confirm not bypassing the hosted-service registration
- [ ] **Health check endpoints exposed - three-way split**: `services.AddHealthChecks()` registered with the right tags AND `app.MapHealthChecks(...)` mapped to **three distinct endpoints**, not one or two:
  - **`/livez` (liveness, kubelet restart gate)**: `app.MapHealthChecks("/livez", new HealthCheckOptions { Predicate = _ => false })` - returns 200 if the process is alive. **NO dependency checks.** Liveness failing tells the orchestrator to restart the pod; if it checks DB / Redis, a transient downstream blip causes a restart cascade across every replica. Bare `app.MapHealthChecks("/health")` without a predicate runs all registered checks - that is the cascading-outage anti-pattern when wired to the kubelet liveness probe
  - **`/readyz` (readiness, load-balancer gate)**: `app.MapHealthChecks("/readyz", new HealthCheckOptions { Predicate = c => c.Tags.Contains("ready") })` checks **own-pod-only** dependencies the pod cannot serve traffic without: DB pool acquire (`AddDbContextCheck<AppDbContext>(tags: new[] { "ready" })`), Redis ping, in-process queue health. **Do NOT include third-party API pings** in `/readyz` - a transient Stripe / SendGrid / external API outage will deregister every replica from the LB simultaneously, taking down the service for an upstream issue you do not own. For request-path resilience to upstream tail latency, use a `Polly` v8 circuit breaker on the call site, not a readiness check. Flag any `AddUrlGroup(new Uri("https://api.stripe.com/..."), tags: new[] { "ready" })` or similar third-party readiness check as `[High]`
  - **`/internal/deps` (observability, dashboards / on-call only - NOT wired to K8s probes)**: optional third deep endpoint that pings every dependency including third-party APIs, with per-dependency status JSON via `UIResponseWriter.WriteHealthCheckUIResponse`. This is for human dashboards and Grafana panels only; no orchestrator wires probes to it
  Multi-replica deployments without this three-way split cannot do safe rolling restarts. This is a deploy-time hazard, not a "deep" optional - flag at any depth on multi-replica services

### Step 10 - Error Tracking (Sentry / Application Insights)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/connection-string handling._

Inspect SDK config:

- [ ] **SDK installed and initialized** (Sentry): `services.AddSentry(o => { o.Dsn = ...; o.Environment = env.EnvironmentName; o.Release = ThisAssembly.AssemblyInformationalVersion; })` and `app.UseSentryTracing()` registered. For Application Insights: `services.AddApplicationInsightsTelemetry()` reads the connection string from config / env
- [ ] **DSN / connection string** in env var or Vault, not committed
- [ ] **Release / environment tags** populated from build metadata (`o.Release = ThisAssembly.AssemblyInformationalVersion`, `o.Environment = env.EnvironmentName`)
- [ ] **PII scrubbing on**: Sentry `o.SendDefaultPii = false` (default but flag if explicitly `true`); `o.BeforeSend = ev => { /* strip sensitive */ return ev; }` strips known sensitive keys; allowlist of breadcrumb fields documented. Application Insights: `ITelemetryProcessor` for filtering
- [ ] **Sentry `ILogger` integration** via `Sentry.Extensions.Logging` so `_logger.LogError(...)` events become Sentry events automatically; or `services.AddSentry()` extension on the `IHostBuilder` for ASP.NET Core integration
- [ ] **OpenTelemetry / trace correlation forwarded**: error event includes `TraceId` and `UserId` so incidents link back to traces / users; the Sentry .NET SDK extracts trace context when an active `Activity` is present
- [ ] **Sample rate explicit**: `o.TracesSampleRate = 0.1` per env; not `1.0` in prod for tracing
- [ ] **Ignored errors documented**: domain exceptions that should not page (e.g., `NotFoundException`, `ValidationException`) filtered via `o.BeforeSend` or `o.IgnoreExceptions`; each ignore has a comment
- [ ] **Background-worker exception capture**: `BackgroundService` exceptions surface via the host's `IHostedService` lifecycle; confirm Sentry / Application Insights captures them (Sentry's hosted service hooks unhandled exceptions; for explicit capture inside `ExecuteAsync` use `try { ... } catch (Exception ex) { SentrySdk.CaptureException(ex); throw; }`)

### Step 11 - Health Checks and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one Prometheus / OTel SLI (HTTP request rate filtered to the journey URI, success rate, p95 latency)
- [ ] Health endpoint **presence** is checked in Step 9 (it is a deploy-time hazard, not depth-gated). At `deep`, additionally verify: per-dependency depth (DB / cache / broker / external API each has a registered check), and that endpoints return JSON with per-dependency status (`UIResponseWriter.WriteHealthCheckUIResponse` for structured output) so probes can distinguish DB-down from worker-stuck
- [ ] SLO targets documented in code (`src/Slos/*.cs` or module README) - not a free-floating Confluence page


### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as .NET / ASP.NET Core (or accepted from parent dispatcher); data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent)
- [ ] Instrumentation surfaces (Program.cs, logging config, OTel wiring, settings, packages, changed call sites) read directly before applying checklists
- [ ] Structured logging assessed: JSON formatter (Serilog `CompactJsonFormatter` or `AddJsonConsole`), trace / request-id correlation, sensitive-field redaction, log level discipline, no `Console.WriteLine` in prod paths, named placeholders not string interpolation
- [ ] OpenTelemetry SDK and auto-instrumentation reviewed: SDK initialized in `Program.cs` before `app.Run()`, ASP.NET Core / EF Core / HttpClient / MassTransit instrumentation enabled, sampling explicit, resource attributes populated, `TracerProvider.Shutdown()` covered by hosted service
- [ ] Metrics assessed: Prometheus exporter exposed, default ASP.NET Core / runtime / process metrics scraped, custom metric naming under namespace (OTel semantic conventions), tag cardinality bounded, route tag is template not actual path, instrument `Description` / `Unit` set
- [ ] dotnet-counters / `dotnet-monitor` presence + non-prod / auth gating assessed; runtime metrics via `AddRuntimeInstrumentation()`
- [ ] Background-worker / MassTransit / Hangfire observability assessed: trace propagation across dispatch boundary, queue / per-job metrics, scheduled job spans, traceparent extraction on consumers
- [ ] Lifecycle / graceful shutdown assessed: `IHostApplicationLifetime`, `IHostedService.StopAsync`, bounded `ShutdownTimeout`, OTel hosted-service shutdown, `Channel<T>` completion, MassTransit / Hangfire bus stop
- [ ] Error tracker integration assessed: SDK wired (Sentry `AddSentry` + `UseSentryTracing` or Application Insights `AddApplicationInsightsTelemetry`), DSN / connection string externalized, PII scrubbed, OTel correlation forwarded, sample rate explicit, background-worker exception capture
- [ ] Findings name a .NET / Serilog / OTel / `Meter` idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/messaging/lifecycle/error-tracker/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## .NET Observability Review Summary

**Stack Detected:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**Messaging:** MassTransit | Hangfire | Channel | none
**Logging:** Serilog (JSON via CompactJsonFormatter) | Microsoft.Extensions.Logging (AddJsonConsole) | text logging | absent
**Metrics:** OpenTelemetry + Prometheus exporter | prometheus-net.AspNetCore | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
**dotnet-counters / dotnet-monitor:** runnable (non-prod) | runnable (prod via dotnet-monitor sidecar) | exposed (public, prod) [security finding] | absent
**Messaging instrumentation:** trace context propagated | partial | absent | n/a (no messaging)
**Error Tracker:** Sentry (Sentry.AspNetCore + Sentry.Extensions.Logging) | Application Insights | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

_The 6-row verdict from Step 3, repeated here as the top-line read for the reviewer. Each row is `wired | partial | absent` plus a one-line citation._

| Surface                       | Verdict                        | Evidence                                   |
| ----------------------------- | ------------------------------ | ------------------------------------------ |
| Structured logging            | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK             | wired / partial / absent       | [...]                                      |
| Metrics exporter              | wired / partial / absent       | [...]                                      |
| dotnet-counters / dotnet-monitor | wired / partial / absent    | [...]                                      |
| Messaging instrumentation     | wired / partial / absent / n/a | [...]                                      |
| Error tracker                 | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ of the rows above are `absent` - it tells the reader the review is scaffolding, not auditing, and changes how they prioritize. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the .NET idiom: missing Serilog destructuring policy for `User` entity (leaks PasswordHash), unbounded tag cardinality on `user_id`, OTel SDK initialized after `app.Build()` (instrumentation captures the no-op tracer), missing `AddHttpClientInstrumentation`, route tag is actual path not template, Hangfire dashboard exposed without auth in prod, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific .NET / Serilog / OTel / `Meter` change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Logging / Tracing / Metrics / dotnet-counters / Messaging / Error Tracker / Lifecycle) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Move OTel SDK init to a dedicated `Observability/Telemetry.cs` extension method invoked before `app.Run()`", "Add `AddHttpClientInstrumentation` to outbound HttpClient registrations", "Switch from per-handler ad-hoc `Counter<long>` to module-level `Meter` registered at startup with `Description` and `Unit`", "Bind Prometheus scraping endpoint to a separate admin port via Kestrel endpoint config", "Wire `Sentry.Extensions.Logging` so `_logger.LogError` becomes Sentry events"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `using var activity = OrderActivitySource.StartActivity(\"PlaceOrder\");` and `activity?.SetTag(\"order.id\", id)` to OrderService.PlaceAsync"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/metrics` endpoint to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the .NET / Serilog / OTel / `Meter` idiom ("add metrics" vs "register `Meter` and `meter.CreateCounter<long>(\"acme.orders.placed.count\", unit: \"{orders}\", description: \"...\")` at module level with bounded tags")
- Recommending generic observability advice when a .NET SDK or auto-instrumentation exists (say "register `AddAspNetCoreInstrumentation()`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high tag cardinality (`user_id`, `order_id`) as acceptable - metric series cost compounds; require enum / category tags
- Approving string-interpolation logging (`_logger.LogInformation($"processing order {orderId}")`) over named-placeholder form (`_logger.LogInformation("processing order {OrderId}", orderId)`) - the rendered string locks the formatter and prevents log-aggregation tools from parsing fields. Roslyn analyzer CA2254 catches this
- Suggesting `Console.WriteLine` as logging - flag for replacement with `ILogger`
- Approving `meter.CreateCounter<long>("...")` registration without `Description` and `Unit` - metrics show up in Prometheus without help text or units
- Approving OTel `AlwaysOnSampler` in prod for high-traffic services - cost and storage compound
- Approving OTel SDK initialization AFTER `app.Build()` and middleware registration - middleware captures the tracer at registration time and may capture the no-op tracer
- Approving Hangfire / Swagger UI / `dotnet-monitor` exposed on a public bind in prod without auth - security and observability finding (delegate to security review for full treatment)
- Prescribing the OTLP endpoint URL or the Sentry DSN value - say "sourced from env / Vault" and stop; concrete URLs are infra config, not source-code review
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
- Approving `BinaryFormatter` / `Newtonsoft.Json` `TypeNameHandling` in telemetry payloads - serialization gadget surface
- Approving `_logger.LogError("...{Message}", ex.Message)` over `_logger.LogError(ex, "...")` - bare `Message` loses the inner exception chain and stack
