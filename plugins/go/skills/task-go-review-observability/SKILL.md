---
name: task-go-review-observability
description: Go observability review - slog, OpenTelemetry, prometheus/client_golang, pprof, Asynq events, graceful shutdown, Sentry SDK.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, observability, slog, opentelemetry, prometheus, pprof, sentry, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Observability Review

Go-aware review naming `slog`, OpenTelemetry SDK + auto-instrumentation (`otelgin`, `otelhttp`, `otelgorm`, Asynq middleware), `prometheus/client_golang`, `net/http/pprof`, graceful shutdown, error-tracker SDKs (`sentry-go`). Library-level scope; infra (Datadog dashboards, Grafana alert rules, log forwarder config) stays out.

Stack-specific delegate of `task-code-review-observability` for Go.

## When to Use

- Go/Gin PR for observability regressions or instrumentation gaps
- Pre-release check for a new service or major feature
- Post-incident review when diagnosis was slow
- Adopting OpenTelemetry / slog / Prometheus

**Not for:** general review (`task-go-review`), perf with known bottleneck (`task-go-review-perf`), active incident (`/task-oncall-start`), infra observability.

## Depth

| Depth      | What runs                                                |
| ---------- | -------------------------------------------------------- |
| `quick`    | Logging + Prometheus check only                          |
| `standard` | All steps                                                |
| `deep`     | All steps + SLI/SLO suggestions                          |

Default: `standard`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-observability` | Current branch vs base; fails fast on trunk |
| `/task-go-review-observability <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-observability pr-<N>` | PR head fetched into local branch (user runs fetch) |

When invoked as subagent, parent passes precondition handle + pre-read artifacts; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Go, stop and recommend `/task-code-review-observability`.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none).

### Step 2 - Resolve Diff

Use skill: `review-precondition-check`. Read diff + log once via `git diff` and `git log`; reuse. Skip if subagent received the handle.

### Step 3 - Read the Instrumentation Surface

**Most important output:** a one-line verdict per surface (logging / OTel / Prometheus / Asynq / pprof / error tracker) of the form `wired | partial | absent`. A missing wire is itself the finding.

**Grouping rule.** When a whole surface is `absent`, produce a **single High-Impact finding** for that surface listing missing pieces grouped by file/symbol - not one finding per sub-bullet. Per-callsite findings only when the surface exists and a specific callsite misuses it.

Open files that configure observability so findings cite real lines:

- `cmd/api/main.go` / `internal/observability/*.go` - OTel SDK wiring, exporter setup, instrumentation registration
- `internal/log/log.go` - `slog` setup (handler, level, redaction)
- Config struct - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, log level, Sentry DSN, Prometheus port
- `go.mod` - confirm `go.opentelemetry.io/otel`, `prometheus/client_golang`, `getsentry/sentry-go` versions
- Every changed file calling `slog.*`, registering Prometheus, defining Gin middleware, instrumenting OTel

### Step 4 - Structured Logging (slog)

- [ ] Production logger emits JSON: `slog.NewJSONHandler(os.Stdout, ...)`. No `fmt.Println` / `log.Printf` in prod paths
- [ ] **Correlation fields** in every line: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs (`order_id`). Wired via request-id middleware + derived logger on `gin.Context`, OR via `slog.Handler` wrapper pulling from `context.Context`
- [ ] **OTel correlation:** `slog.InfoContext(ctx, ...)` extracts `trace_id`/`span_id` via custom handler wrapper or `go.opentelemetry.io/contrib/bridges/otelslog`. Plain `slog.Info(...)` cannot correlate
- [ ] **Redaction:** `slog.Handler` wrapper drops `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key`; OR types implement `slog.LogValuer` to mask
- [ ] **No `slog.Info("user", user)` serializing a GORM model** - lazy associations may trigger queries; PII leaks via JSON tags. Log specific fields
- [ ] **Structured key-values, not message strings.** `slog.Info("event", "user_id", id)`, never `slog.Info(fmt.Sprintf("user=%d", id))` - redaction config cannot scrub free-text
- [ ] **Log levels:** Error for actionable failures, Warn for recoverable, Info for state transitions, Debug for verbose. Default Info in prod
- [ ] **No log spam in hot loops** - sample or use Debug
- [ ] **Error logging includes wrap chain.** `slog.Error("loading order", "err", err)` prints the chain when error implements `Unwrap()`; `slog.Error(err.Error())` loses it

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK initialized in `main.go` BEFORE `gin.New()`** - middleware captures the tracer at registration; late init means no-op tracer
- [ ] **OTLP exporter:** `otlptracegrpc.New(...)` / `otlptracehttp.New(...)` pointed at the collector; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Resource attributes:** `service.name`, `service.version`, `deployment.environment` via `resource.New(...)` with `semconv`
- [ ] **Sampling explicit:** `sdktrace.ParentBased(sdktrace.TraceIDRatioBased(rate))`; not `AlwaysSample` in high-traffic prod
- [ ] **Gin instrumentation:** `r.Use(otelgin.Middleware("service-name"))` - route templates as span names (avoids high-cardinality)
- [ ] **GORM:** `db.Use(tracing.NewPlugin())` from `go-gorm/opentelemetry`; SQL spans attach to request span via context
- [ ] **sqlx:** `otelsql` wraps the driver; sqlx wraps via `sqlx.NewDb(db, "postgres")`
- [ ] **HTTP client:** `otelhttp.NewTransport(http.DefaultTransport)` wrapped into shared `*http.Client`
- [ ] **Asynq:** middleware extracts traceparent from task headers, restarts span in worker
- [ ] **Redis:** `otelredis` for `go-redis/redis/v9` if in use
- [ ] **Custom spans** for business operations: `ctx, span := tracer.Start(ctx, "OrderService.Place"); defer span.End()`. No over-instrumentation
- [ ] **Span attributes** via `attribute.*` with bounded cardinality
- [ ] **`span.RecordError(err)`** on error paths
- [ ] **`tp.Shutdown(ctx)` on graceful shutdown** flushes in-flight spans

### Step 6 - Prometheus Metrics

- [ ] **Client installed** and `/metrics` exposed (`r.GET("/metrics", gin.WrapH(promhttp.Handler()))`), or OTel metrics with Prometheus exporter
- [ ] **Default Go runtime metrics** scraped (`go_goroutines`, `go_memstats_*`, `go_gc_duration_seconds`, `process_*`)
- [ ] **HTTP server metrics:** `http_request_duration_seconds` (histogram) + `http_requests_total` (counter) with route / method / status. **Route label must be the template** (`/orders/:id`), not the actual path (`/orders/123`) - cardinality explodes otherwise
- [ ] **Custom business metrics** under consistent namespace (`acme_orders_placed_total`); suffix conventions (`_total`, `_seconds`, `_bytes`)
- [ ] **Bounded label cardinality** - no `user_id`, `order_id`, `request_id` as labels; only enums / known categories
- [ ] **No metric registration in hot path** - construct at `var (...)` or app startup, not per-request (`panic: duplicate metrics collector registration`)
- [ ] **`MustRegister`** (not `Register`) at startup so errors fail fast
- [ ] **Histogram buckets** chosen for SLO; sub-100ms paths need finer buckets than `prometheus.DefBuckets`

### Step 7 - pprof

_Skipped at `quick` unless diff touches pprof._

- [ ] **`net/http/pprof` registered** on separate admin port, OR non-prod only, OR behind admin auth
- [ ] **Profiles accessible**: `/debug/pprof/{heap,goroutine,profile,mutex,block}`
- [ ] **`runtime.SetMutexProfileFraction(rate)` and `SetBlockProfileRate(rate)`** enabled - without these, mutex/block profiles are empty
- [ ] **NOT on prod public port without auth** - delegate to security review

### Step 8 - Asynq / Kafka / Background Jobs

_Skipped at `quick` unless diff touches them._

- [ ] **Asynq OTel middleware** enabled - traceparent extracted, worker span links to dispatching request span
- [ ] **Queue metrics:** `asynq.NewInspector(...)` polled into Prometheus gauges (`pending`, `active`, `scheduled`, `retry`, `archived`)
- [ ] **Per-task metrics:** latency histogram, retry counter, failure counter
- [ ] **Trace propagation across dispatch boundary** - `client.Enqueue(...)` inside a request links the worker span back
- [ ] **Logger bound inside handler:** `task_id`, `task_type`, sanitized payload fields
- [ ] **Outbound HTTP from tasks** instrumented via `otelhttp.NewTransport(...)`
- [ ] **Scheduled tasks** emit spans; missed-execution alerting

### Step 9 - Graceful Shutdown

_Skipped at `quick` unless diff touches lifecycle or `main.go`._

- [ ] **`signal.NotifyContext`** pattern: `ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT); defer stop()`. HTTP server in goroutine; main blocks on `<-ctx.Done()`; then `srv.Shutdown(shutdownCtx)`
- [ ] **Bounded shutdown timeout:** `context.WithTimeout(context.Background(), 30*time.Second)` - never indefinite
- [ ] **`tp.Shutdown(shutdownCtx)`** flushes buffered spans
- [ ] **`Asynq.Server.Shutdown()`** drains workers; Kafka `client.Close()` commits in-flight
- [ ] **`db.Close()`** on shutdown

### Step 10 - Error Tracking (Sentry / Honeybadger)

_Skipped at `quick` unless diff modifies error handlers or DSN/API-key handling._

- [ ] **SDK initialized:** `sentry.Init(...)` in `main.go`; `sentrygin.New(...)` middleware applied - panics and `c.Error(err)` flow reach Sentry
- [ ] **DSN / API key** from env / Vault, never committed
- [ ] **Release / environment** populated from build metadata
- [ ] **PII scrubbing:** `SendDefaultPII: false`; `BeforeSend` strips sensitive keys
- [ ] **OTel correlation forwarded** so errors link to traces / users
- [ ] **Sample rate explicit:** `TracesSampleRate`, `ProfilesSampleRate` per env; not `1.0` in prod for tracing
- [ ] **Ignored errors documented:** domain errors filtered via `BeforeSend` / `IgnoreErrors`
- [ ] **Gin error middleware calls `sentry.CaptureException(err)`** before transforming
- [ ] **`sentry.Recover()` deferred at goroutine boundaries** outside request lifecycle (Gin recovery only covers request goroutines)

### Step 11 - Health and SLIs (deep only)

- [ ] Critical journeys have at least one SLI (request rate, success rate, p95 latency)
- [ ] **Three distinct endpoints, not one `/health`** (single `/health` is a per-PR finding):
  - **`/livez`** - returns 200 unconditionally; no dependency pings (coupling makes Postgres blip restart all replicas)
  - **`/readyz`** - own-pod-only checks (DB pool, Redis, Asynq client); tight timeouts; no third-party pings (would pull replicas from LB on outage)
  - **`/internal/deps`** / **`/debug/health`** - JSON per-dependency status for dashboards; NOT for K8s probes. Verify manifest probes don't point here
- [ ] Health endpoints return JSON with per-dependency status (on dependency-observability endpoint)
- [ ] SLO targets documented in code (`internal/slo/*.go` or README)

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write before ending; print confirmation.

## Self-Check

- [ ] Stack confirmed (or accepted from parent); data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused
- [ ] When `head_matches_current` was false: user approval obtained (skipped when subagent)
- [ ] Instrumentation surfaces (logging, OTel, settings, deps, changed callsites) read directly before checklists
- [ ] `slog`: JSON handler, correlation, redaction, level discipline, no `fmt.Println` in prod
- [ ] OTel: SDK initialized before Gin engine; instrumentation enabled; sampling explicit; resource attrs; `tp.Shutdown` called
- [ ] Prometheus: client present, default + HTTP server metrics, custom under namespace, bounded labels, template route label
- [ ] pprof: non-prod / auth gating
- [ ] Asynq / Kafka: OTel middleware, queue metrics, trace propagation across dispatch, scheduled spans
- [ ] Shutdown: `signal.NotifyContext`, bounded timeout, `tp.Shutdown`, `Asynq.Server.Shutdown`, `db.Close`
- [ ] Error tracker: SDK + Gin middleware, DSN externalized, PII scrubbed, OTel correlation, sample rate explicit, `sentry.Recover()` at goroutine boundaries
- [ ] Findings name a Go / OTel / slog / Prometheus idiom - not "add observability"
- [ ] Library-level scope respected; infra concerns deferred to ops
- [ ] Depth honored: `quick` skipped tracing/Asynq/lifecycle/error-tracker/SLI unless signaled; `deep` ran SLI
- [ ] Next Steps with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend > Question
- [ ] Report written via `review-report-writer`; confirmation printed

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
**Overall:** Adequate | Gaps Found - [count by impact] | Greenfield - no surface wired [count by impact]

## Surface Map

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| slog logging           | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| Prometheus metrics     | wired / partial / absent       | [...]                                      |
| pprof endpoints        | wired / partial / absent       | [...]                                      |
| Asynq instrumentation  | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent` - tells the reader the review is scaffolding, not auditing. Use the same `absent` vocabulary throughout.

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the idiom: missing slog redaction for `Authorization`, unbounded label cardinality on `user_id`, OTel SDK initialized after `gin.New()`, missing Asynq OTel middleware, route label is actual path not template]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Go / OTel / slog / Prometheus change with code]

### Medium Impact / Low Impact

[Same structure]

_Omit empty sections. Within each impact bucket, group by surface when > 2 findings share a surface. Greenfield reviews collapse a whole surface into one finding per Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Reporting gaps without naming the idiom ("add metrics" vs "register `acme_orders_placed_total` Counter at module level via `MustRegister`")
- Generic advice when a Go SDK or auto-instrumentation exists
- Reviewing infra (Datadog settings, Grafana panels, log forwarder, on-call) - not in source code
- Treating high label cardinality as acceptable
- Approving template-string logging over structured form
- `fmt.Println` / `log.Printf` as logging
- `prometheus.NewCounter` registration inside a request handler
- `sdktrace.AlwaysSample()` in high-traffic prod
- OTel SDK init AFTER `gin.New()` + `otelgin.Middleware`
- pprof exposed on public mux in prod without auth
- Prescribing OTLP endpoint URL or Sentry DSN value (infra config, not source review)
- One finding per missing checkbox when whole surface is absent
- Plain `slog.Info(...)` when OTel is wired (log-trace correlation needs `slog.InfoContext`)
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
