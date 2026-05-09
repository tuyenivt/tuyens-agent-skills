---
name: task-go-review-observability
description: Go observability review: slog, OpenTelemetry Go SDK, prometheus/client_golang, pprof, Asynq events, graceful shutdown, Sentry SDK.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, observability, slog, opentelemetry, prometheus, pprof, sentry, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Go Observability Review

## Purpose

Go-aware observability review that names `slog` structured logging (Go 1.21+ stdlib), OpenTelemetry Go SDK (`go.opentelemetry.io/otel`), auto-instrumentation (`otelhttp`, `otelgin`, `otelgorm` / `go-gorm/opentelemetry`, `otelsqlx` via `XRayed`, `otelredis`, Asynq OTel middleware), `prometheus/client_golang` metrics, `net/http/pprof` profiling endpoints, Asynq queue health hooks, graceful shutdown via `signal.NotifyContext` / `os.Signal`, and error-tracker SDKs (`getsentry/sentry-go`, `honeybadger-io/honeybadger-go`) directly instead of routing through the generic adapter. Focuses on whether Go production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Go. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a Go/Gin PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Go service or major feature
- Post-incident review when Go diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / slog / Prometheus in a Go app
- Auditing Asynq / Kafka tracing and correlation across the request → task boundary

**Not for:**

- General Go code review (use `task-go-review`)
- Go performance issues with a known bottleneck (use `task-go-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint, handler, or task                            | Logging + Prometheus metrics check only            |
| `standard` | Default - full Go observability review                       | All steps                                          |
| `deep`     | Pre-release of a critical Go service, or post-incident review| All steps + SLI/SLO suggestions for Go endpoints   |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                               | Meaning                                                                                               |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-go-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-go-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-go-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-go-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Data-Access Mix

Use skill: `stack-detect` to confirm Go / Gin. If invoked as a subagent of a Go-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Go, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none). Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (logging / OTel / Prometheus / Asynq / pprof / error tracker) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below) rather than one-per-bullet.

**Grouping rule.** When a whole surface is `absent` (no `prometheus/client_golang`, no OTel SDK init, no error-tracker SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/symbol they should land in - not one finding per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. This prevents 50-item dumps on greenfield reviews.

Then open the files that actually configure observability so findings cite real lines, not assumptions:

- `cmd/api/main.go` / `internal/observability/*.go` - OpenTelemetry SDK wiring (`otel.SetTracerProvider`, `otel.SetMeterProvider`, OTLP exporter setup), instrumentation registration (`otelgin.Middleware`, `otelhttp.NewTransport`)
- `internal/log/log.go` (or equivalent) - `slog` setup (handler, level, redaction)
- `cmd/api/main.go` / config struct - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, log level, Sentry DSN, Prometheus scrape port
- `go.mod` - confirm `go.opentelemetry.io/otel`, `go.opentelemetry.io/contrib/instrumentation/...`, `prometheus/client_golang`, `getsentry/sentry-go` presence and versions
- Every changed file in the diff that calls `slog.*`, registers a `prometheus.Counter` / `Histogram` / `Gauge`, defines a Gin middleware, instruments with OTel, or modifies trace context

For diffs touching only one of these surfaces (a new endpoint but no logging change, say), still read the existing config to know whether request-id / trace correlation, instrumentation, and SDKs are wired - a missing wire is the finding.

### Step 4 - Structured Logging (slog)

Inspect logging config and any `slog.*` callsite in the diff:

- [ ] **Production logger emits JSON** - `slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})` (Go 1.21+ stdlib). No `fmt.Println` / `log.Printf` in production code paths
- [ ] **Correlation fields injected** in every log line: `trace_id`, `span_id`, `request_id`, `user_id` (when authenticated), `tenant_id`, plus business correlation IDs (`order_id`, `invoice_id`). Wire via:
  - Gin request-id middleware (`gin-contrib/requestid`) sets `c.Set("request_id", ...)`
  - A logger derived per request: `reqLogger := slog.With("request_id", c.GetString("request_id"))` stored on `gin.Context`, then handlers/services read it via `c.MustGet("logger").(*slog.Logger)`
  - Or `slog.Handler` wrapper that pulls request-scoped context via `context.Context` (passed as first arg to `slog.InfoContext(ctx, ...)`)
- [ ] **OpenTelemetry log correlation**: `slog.InfoContext(ctx, ...)` extracts `trace_id` / `span_id` from the context's active span via a custom `slog.Handler` wrapper or via `go.opentelemetry.io/contrib/bridges/otelslog`. Plain `slog.Info(...)` (no `Context`) cannot correlate
- [ ] **Sensitive-field redaction**: `slog.Handler` wrapper that drops `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key` keys; OR types implement `slog.LogValuer` to override marshalling and return a redacted form
- [ ] **No `slog.Info("user", user)` that serializes a GORM model**: lazy-loaded associations may trigger queries; PII may leak via JSON tags. Always log specific fields: `slog.Info("event", "user_id", u.ID, "tenant_id", u.TenantID)`
- [ ] **User-identity fields emitted as structured key-values, not in the message string**: `slog.Info("event", "user_id", userID)`, never `slog.Info(fmt.Sprintf("user=%d processing", userID))` - a single redaction config can scrub structured fields; it cannot reliably scrub them out of a free-text message
- [ ] **Log levels used correctly**: `slog.LevelError` for actionable failures, `slog.LevelWarn` for recoverable anomalies, `slog.LevelInfo` for state transitions, `slog.LevelDebug` for verbose diagnostics. Default level `Info` in prod
- [ ] **No `fmt.Println` / `log.Printf`** in production code paths - flag for replacement with `slog`; `fmt.Println` skips redaction, structured fields, and correlation
- [ ] **No log spam in hot loops** - iterating large slices, scheduled jobs running every second, Asynq workers at high TPS must not log per-iteration; sample or use `slog.LevelDebug`
- [ ] **Error logging includes the wrap chain**: `slog.Error("loading order", "err", err)` - `slog`'s default formatter prints the full chain when error implements `Unwrap()`; `slog.Error(err.Error())` loses the chain

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

Inspect OpenTelemetry config and instrumentation wiring:

- [ ] **OpenTelemetry SDK initialized in `main.go` BEFORE the Gin engine starts**: `tp := sdktrace.NewTracerProvider(...)`, `otel.SetTracerProvider(tp)` happens before `r := gin.New()`. Late initialization means subsequent middleware / handlers may use the no-op tracer
- [ ] **OTLP exporter configured**: `otlptracegrpc.New(...)` or `otlptracehttp.New(...)` pointed at the org's collector / backend; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` set per env
- [ ] **Resource attributes** populated: `service.name`, `service.version`, `deployment.environment`; sourced from build metadata / env vars via `resource.New(...)` with `semconv` attributes
- [ ] **Sampling policy explicit**: `sdktrace.ParentBased(sdktrace.TraceIDRatioBased(rate))` with `rate` per env (e.g., `0.1` in prod, `1.0` in staging); not `AlwaysSample` in high-traffic prod
- [ ] **Gin auto-instrumentation**: `r.Use(otelgin.Middleware("service-name"))` from `go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin` - creates spans per request with route templates as span names (avoids high-cardinality)
- [ ] **GORM auto-instrumentation**: `db.Use(tracing.NewPlugin())` from `go-gorm/opentelemetry` (Go 1.21+) or equivalent; SQL spans attach to the request span via context propagation
- [ ] **sqlx instrumentation**: `otelsql` (`XRayed/otelsql`) wraps the driver to emit spans on `*sql.DB`; sqlx wraps the result via `sqlx.NewDb(db, "postgres")`
- [ ] **HTTP client instrumentation**: `otelhttp.NewTransport(http.DefaultTransport)` wrapped into the shared `*http.Client`; traceparent propagates outbound automatically
- [ ] **Asynq instrumentation**: Asynq's middleware option includes OTel propagation (extract traceparent from task headers, restart span in worker); flag missing instrumentation - cross-process trace stitching breaks
- [ ] **Redis instrumentation**: `otelredis` for `go-redis/redis/v9` if Redis is in use
- [ ] **Custom spans** for business operations: `ctx, span := tracer.Start(ctx, "OrderService.Place"); defer span.End()`; no over-instrumentation (do not wrap a single GORM query in a custom span - the SQL span already covers it)
- [ ] **Span attributes via `attribute.*`**: `span.SetAttributes(attribute.String("order.id", orderID), attribute.Int("order.item_count", count))`; keep cardinality bounded
- [ ] **`span.RecordError(err)` on error paths**: marks the span as error and attaches the error message
- [ ] **`tp.Shutdown(ctx)` called on graceful shutdown** so in-flight spans flush

### Step 6 - Prometheus Metrics (prometheus/client_golang)

Inspect `prometheus/client_golang` / metrics registration:

- [ ] **`prometheus/client_golang` installed** and `/metrics` endpoint exposed (typical Gin pattern: `r.GET("/metrics", gin.WrapH(promhttp.Handler()))`), or OTel metrics with Prometheus exporter via `go.opentelemetry.io/otel/exporters/prometheus`
- [ ] **Default Go runtime metrics** scraped: `go_goroutines`, `go_memstats_heap_inuse_bytes`, `go_gc_duration_seconds`, `process_cpu_seconds_total`, `process_resident_memory_bytes` - confirm `prometheus.MustRegister(collectors.NewGoCollector(), collectors.NewProcessCollector(...))` runs at startup (default registry includes them but explicit is clearer)
- [ ] **HTTP server metrics**: histogram `http_request_duration_seconds` and counter `http_requests_total` with route / method / status labels - via `gin-contrib/prometheus` or a custom middleware. Critical: route label must be the **template** (`/orders/:id`), not the actual path (`/orders/123`), or cardinality explodes
- [ ] **Custom business metrics** named under a consistent namespace (`acme_orders_placed_total`, `acme_payments_failed_total`); units explicit (`Counter` for counts, `Histogram` for durations, `Gauge` for instantaneous values, `Summary` for quantile-required cases). Suffix conventions (`_total`, `_seconds`, `_bytes`) followed
- [ ] **Tag (label) cardinality bounded**: labels do not include unbounded values (`user_id`, `order_id`, `request_id`) - causes metric-cardinality blow-up. Allowed label values are enums / known categories (`status`, `tenant_tier`, `region`)
- [ ] **No metric registration in hot path**: `prometheus.NewCounter(...)` constructed at `var (...)` block or `init()` (or app startup), not per-request - registration in a request handler causes `panic: duplicate metrics collector registration attempted` after the first request
- [ ] **`MustRegister` (not `Register`)** at startup so a registration error fails fast; `Register` returns the error which is easy to ignore
- [ ] **Histogram buckets** chosen for the SLO: default buckets are seconds-scale (`prometheus.DefBuckets`); for sub-100ms paths add finer buckets via `prometheus.HistogramOpts{Buckets: []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}}`
- [ ] **Multi-instance aggregation**: when running multiple replicas, Prometheus scrapes each replica; ensure no per-replica metric is mistakenly aggregated as a sum (use `rate()` + `sum by(...)` discipline at query time, not in the SDK)

### Step 7 - pprof Profiling Endpoints

_Skipped at `quick` depth unless the diff touches pprof registration._

- [ ] **`net/http/pprof` registered** for live profiling: typical pattern is to register on a **separate admin port** (not the main `/api` mux) to keep it off the public surface, OR register on the main mux but **only in non-prod** (`if env != "prod" { pprof.Register(r) }`), OR behind admin auth middleware
- [ ] **`/debug/pprof/heap`, `/debug/pprof/goroutine`, `/debug/pprof/profile`, `/debug/pprof/mutex`, `/debug/pprof/block` accessible** from the registered endpoint - useful for live debugging via `go tool pprof http://...`
- [ ] **`runtime.SetMutexProfileFraction(rate)` and `runtime.SetBlockProfileRate(rate)`** enabled (e.g., `1` to sample everything; higher is sparser) - without these, mutex / block profiles return empty
- [ ] **pprof endpoint NOT exposed on prod public port without auth**: this is a security finding too (`task-go-review-security`) - flag for delegation if the diff exposes `/debug/pprof` on the public mux without gating

### Step 8 - Asynq / Kafka / Background Job Observability

_Skipped at `quick` depth unless the diff touches Asynq or Kafka._

- [ ] **Asynq OTel middleware enabled**: traceparent extracted from task payload headers and worker span links to the dispatching request span; flag missing
- [ ] **Asynq queue metrics**: `asynq.NewInspector(...)` polled into Prometheus gauges for queue depth (`pending`, `active`, `scheduled`, `retry`, `archived`, `completed`); per-queue counter for completed / failed
- [ ] **Per-task metrics**: latency histogram, retry counter, failure counter, queue-depth gauge
- [ ] **Trace context propagation across the request → Asynq boundary**: when `client.Enqueue(...)` is dispatched inside an HTTP request, the worker span links back to the request span (Asynq OTel middleware handles this; flag manual wiring that breaks it)
- [ ] **Logger context binding inside the handler**: `task_id`, `task_type`, sanitized payload fields bound at task start via a derived `slog.Logger`; flushed at end
- [ ] **Outbound HTTP from tasks instrumented**: `http.Client` used inside an Asynq handler is wrapped via `otelhttp.NewTransport(...)` so the worker span chains to the downstream service span; flag tasks that make uninstrumented outbound calls because the downstream timing / errors stay invisible to traces
- [ ] **Scheduled / periodic task instrumentation**: each scheduled task emits a span; missed-execution alerting via stalled-task metric or queue health endpoint

### Step 9 - Lifecycle / Graceful Shutdown Observability

_Skipped at `quick` depth unless the diff touches lifecycle (graceful shutdown, signal handling) or `main.go`._

- [ ] **Graceful shutdown via `signal.NotifyContext`**: `ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT); defer stop()` - the canonical Go 1.16+ pattern. The HTTP server runs in a goroutine; main blocks on `<-ctx.Done()`, then calls `srv.Shutdown(shutdownCtx)`
- [ ] **Bounded shutdown timeout**: `shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second); defer cancel(); srv.Shutdown(shutdownCtx)` - never indefinite shutdown wait
- [ ] **OTel TracerProvider shutdown**: `tp.Shutdown(shutdownCtx)` flushes buffered spans before process exit; absent shutdown drops in-flight telemetry
- [ ] **Asynq `Server.Shutdown()`** called for graceful worker drain; Kafka `client.Close()` for in-flight commit
- [ ] **GORM / sqlx `db.Close()`** on shutdown (typically deferred at startup via `defer db.Close()`)
- [ ] **Bootstrap span** (optional but useful for cold-start visibility): `ctx, span := tracer.Start(ctx, "app.bootstrap"); ...; span.End()` around the heavy startup work

### Step 10 - Error Tracking (Sentry / Honeybadger SDKs)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/API-key handling._

Inspect SDK config:

- [ ] **SDK installed and initialized**: `sentry.Init(sentry.ClientOptions{Dsn: ..., Environment: ..., Release: ...})` in `main.go`; `sentry-go/gin` middleware applied (`r.Use(sentrygin.New(...))`) so panics and `c.Error(err)` flows reach Sentry
- [ ] **DSN / API key** in env var or Vault, not committed to settings
- [ ] **Release / environment tags** populated from build metadata (`Release: version.Build`, `Environment: env.Name`)
- [ ] **PII scrubbing on**: `SendDefaultPII: false` (default but flag if explicitly `true`); `BeforeSend` strips known sensitive keys; allowlist of breadcrumb fields documented
- [ ] **OpenTelemetry / trace correlation forwarded**: error event includes `trace_id` and `user_id` so incidents link back to traces / users; Sentry SDK extracts trace context when OTel SDK is active
- [ ] **Sample rate explicit**: `TracesSampleRate`, `ProfilesSampleRate` per env; not `1.0` in prod for tracing
- [ ] **Ignored errors documented**: domain errors that should not page (e.g., `ErrNotFound`, validation errors handled by the error middleware) filtered via `BeforeSend` or `IgnoreErrors`; each ignore has a comment
- [ ] **Gin error middleware calls `sentry.CaptureException(err)`** before transforming the error to a response, so the original wrapped error reaches the tracker
- [ ] **`sentry.Recover()` deferred at goroutine boundaries**: every long-lived goroutine launched outside the request lifecycle includes `defer sentry.Recover()` so panics reach the tracker (Gin's recovery middleware only covers request goroutines)

### Step 11 - Health Checks and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one Prometheus / OTel SLI (HTTP request rate filtered to the journey URI, success rate, p95 latency)
- [ ] **Liveness vs readiness vs dependency-health are three distinct endpoints, not one** - this is the most-misused pattern in Go services and a per-PR finding when a single `/health` does all three:
  - **`/livez` (liveness)**: returns 200 unconditionally as long as the Go process can serve HTTP. NO DB ping, NO Redis ping, NO Asynq inspector call, NO outbound HTTP. The kubelet uses this to decide "kill and restart this pod"; coupling it to a dependency means a Postgres blip restarts every replica simultaneously, amplifying the outage. A bare `func(c *gin.Context) { c.Status(200) }` is the correct implementation
  - **`/readyz` (readiness)**: own-pod-only checks - DB pool reachable from THIS pod (`db.PingContext(ctx)` with a tight timeout), Redis reachable, Asynq client connected. Used by the kubelet to gate traffic. Crucially it MUST NOT include third-party API pings (Stripe, Twilio, Sentry, S3) - if Stripe has a 5min outage, you do NOT want the kubelet to pull every replica out of the LB; that turns Stripe's outage into your full outage. Use a circuit breaker (`gobreaker`) on the request path instead
  - **`/internal/deps` or `/debug/health` (dependency observability)**: returns JSON with per-dependency status including third-party APIs - this is for dashboards and on-call investigation, NOT for K8s probes. Verify any K8s manifest in the diff doesn't point `readinessProbe` or `livenessProbe` at this URL (would re-create the cascading-outage problem above)
- [ ] Health endpoints return JSON with per-dependency status (on the dependency-observability endpoint, not the K8s probe endpoints), so on-call can distinguish DB-down from worker-stuck without `kubectl exec`
- [ ] SLO targets documented in code (`internal/slo/*.go` or module README) - not a free-floating Confluence page


### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Go / Gin (or accepted from parent dispatcher); data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent - the parent already gated)
- [ ] Instrumentation surfaces (logging config, OTel wiring, settings, dependencies, changed call sites) read directly before applying checklists
- [ ] Structured logging assessed: JSON `slog` handler, trace / request-id correlation, sensitive-field redaction, log level discipline, no `fmt.Println` / `log.Printf` in prod paths
- [ ] OpenTelemetry SDK and auto-instrumentation reviewed: SDK initialized before Gin engine, Gin / GORM / HTTP / Asynq instrumentation enabled, sampling explicit, resource attributes populated, `tp.Shutdown` called
- [ ] Prometheus metrics assessed: client on classpath, default Go runtime + HTTP server metrics scraped, custom metric naming under namespace, label cardinality bounded, route label is template not actual path
- [ ] pprof presence + non-prod / auth gating assessed
- [ ] Asynq / Kafka observability assessed: OTel middleware enabled, queue metrics, trace propagation across dispatch boundary, scheduled task spans
- [ ] Lifecycle / graceful shutdown assessed: `signal.NotifyContext`, bounded shutdown timeout, `tp.Shutdown`, `Asynq.Server.Shutdown`, `db.Close`
- [ ] Error tracker integration assessed: SDK wired with Gin middleware, DSN externalized, PII scrubbed, OTel correlation forwarded, sample rate explicit, `sentry.Recover()` deferred at goroutine boundaries
- [ ] Findings name a Go / OTel / slog / Prometheus idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/Asynq/lifecycle/error-tracker/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Go Observability Review Summary

**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Logging:** slog (JSON) | slog (text) | log (stdlib) | absent
**Metrics:** prometheus/client_golang | OTel metrics (Prometheus exporter) | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
**pprof:** enabled (admin port) | enabled (non-prod only) | enabled (public, prod) [security finding] | absent
**Asynq instrumentation:** OTel middleware | partial | absent | n/a (no Asynq)
**Error Tracker:** Sentry | Honeybadger | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

_The 5-row verdict from Step 3, repeated here as the top-line read for the reviewer. Each row is `wired | partial | absent` plus a one-line citation._

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| slog logging           | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| Prometheus metrics     | wired / partial / absent       | [...]                                      |
| pprof endpoints        | wired / partial / absent       | [...]                                      |
| Asynq instrumentation  | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ of the rows above are `absent` - it tells the reader the review is scaffolding, not auditing, and changes how they prioritize. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Go idiom: missing slog redaction for `Authorization` header, unbounded label cardinality on `user_id`, OTel SDK initialized after `r := gin.New()` (otelgin middleware uses no-op tracer), missing Asynq OTel middleware, route label is actual path not template, etc.]
- **Impact:** [diagnosability / alertability / cost cost]
- **Fix:** [specific Go / OTel / slog / Prometheus change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Logging / Tracing / Metrics / pprof / Asynq / Error Tracker / Lifecycle) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Move OTel SDK init to a dedicated `internal/observability/otel.go` initialized before any router setup", "Add `otelgorm` plugin to GORM for SQL span correlation", "Switch from `prometheus.NewCounter` per-handler to module-level `var` block", "Register pprof on a separate admin port instead of the public mux"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Bind `order_id` via `slog.With(\"order_id\", id)` at OrderService.Place entry"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/metrics` endpoint to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Go / OTel / slog / Prometheus idiom ("add metrics" vs "register `prometheus.NewCounterVec` named `acme_orders_placed_total` at module level with bounded labels via `MustRegister`")
- Recommending generic observability advice when a Go SDK or auto-instrumentation exists (say "enable `otelgin.Middleware`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high label cardinality (`user_id`, `order_id`) as acceptable - metric series cost compounds; require enum / category labels
- Approving template-string logging (`slog.Info(fmt.Sprintf("processing order=%d", orderID))`) over structured form (`slog.Info("processing", "order_id", orderID)`) - the rendered string locks the formatter and prevents log-aggregation tools from parsing fields
- Suggesting `fmt.Println` / `log.Printf` as logging - flag for replacement with `slog`
- Approving `prometheus.NewCounter(...)` registration inside a request handler - panics on duplicate registration after the first request
- Approving `sdktrace.AlwaysSample()` in prod for high-traffic services - cost and storage compound
- Approving OTel SDK initialization AFTER `r := gin.New()` and `otelgin.Middleware` registration - middleware captures the tracer at registration time and may capture the no-op tracer
- Approving `pprof` exposed on the public mux in prod without auth - security and observability finding (delegate to security review for full treatment)
- Prescribing the OTLP endpoint URL or the Sentry DSN value - say "sourced from env / Vault" and stop; concrete URLs are infra config, not source-code review
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
- Approving plain `slog.Info(...)` (without `Context`) when OTel is wired - log-trace correlation requires `slog.InfoContext(ctx, ...)` so the handler can extract the active span
