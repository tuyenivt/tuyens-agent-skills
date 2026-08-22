---
name: task-go-review-observability
description: Go observability review - slog, OpenTelemetry, prometheus/client_golang, pprof, Asynq events, graceful shutdown, Sentry SDK.
agent: go-observability-engineer
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

**Not for:** general review (`task-go-review`), perf with known bottleneck (`task-go-review-perf`), infra observability.

## Depth

| Depth      | What runs                                                |
| ---------- | -------------------------------------------------------- |
| `standard` | All steps                                                |
| `deep`     | All steps + SLI/SLO suggestions                          |

Default: `standard`. Request deep by appending `deep` to the invocation (e.g. `/task-go-review-observability <branch> deep`). Deep's SLI/SLO suggestions are emitted under Recommendations in the report.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-observability` | Current branch vs base; fails fast on trunk |
| `/task-go-review-observability <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-observability pr-<N>` | PR head fetched into local branch (user runs fetch) |

**Subagent runs** (e.g. spawned by `task-go-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, the data-access mix, and messaging. Step 2 is skipped whole, its SHA capture included - never re-run git. Step 11.5 is skipped (the parent verifies the merged set once). Step 12 returns the Output Format instead of writing, and prints no confirmation. Derive `Messaging` from `go.mod` and the diff when the parent did not send it.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Go, stop and recommend `/task-code-review-observability`.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none).

### Step 2 - Resolve Diff

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check`. Read diff + log once via `git diff` and `git log`; reuse. Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

If the clean-tree gate fails and **the only untracked file is this workflow's own prior report** (`review-observability-<branch>.md`), the gate is tripping on the artifact the last run wrote; every round-2 review would be unreachable. Say so, treat the tree as clean, continue, and tell the user to gitignore the report path. Any other fail-fast: surface verbatim and stop.

**Resolve the round now, before any analysis.** Stat that same `review-observability-<branch>.md`. Absent or frontmatter-less -> `round: 1`. Present and valid -> `round = prior.round + 1`, with its `head_sha` as `prior_head_sha`. **When that `head_sha` equals the current head and the invocation asks for nothing more (no `deep` where the prior was `standard`), print `No new commits on <branch> since prior observability review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite. Doing this at Step 12 instead wastes the whole pass and destroys the prior round's findings.

### Step 3 - Read the Instrumentation Surface

**Most important output:** a one-line verdict per surface - logging, OTel, Prometheus, messaging instrumentation (the row is named for whichever broker `Messaging` reported: Asynq, Kafka, or both), pprof, graceful shutdown, error tracker - of the form `wired | partial | absent | n/a`. A missing wire is itself the finding.

The verdict answers **how much of the surface exists**, not whether it is correct: `wired` = every piece is present (misconfigured pieces stay `wired`, with the defect in the Evidence cell and a finding); `partial` = the mechanism is installed but does not cover everything it should (an SDK with no DB or HTTP instrumentation, a shutdown path that misses a client, a logger with no redaction); `absent` = nothing is wired. A correctly-built OTel SDK that instruments no dependency is `partial`, not `wired`.

**Grouping rule.** When a whole surface is `absent`, produce a **single finding** for that surface listing missing pieces grouped by file/symbol - not one finding per sub-bullet. When the surface's gaps straddle impact tiers, keep the grouping and file at the strongest tier; split only when a sub-gap needs a materially different fix - a leaked secret in a `%+v` call is not fixed by wiring a JSON handler, so it is its own finding even though both sit on the logging surface. Per-callsite findings only when the surface exists and a specific callsite misuses it.

**Severity, and the diff-vs-repo scope rule.** A surface the diff touches - or that the diff makes load-bearing, such as sub-instrumentation missing on an unchanged client once this PR installs the tracer that would have used it - is scored on consequence, High when it leaves a failure undiagnosable. A surface the diff never approaches and never activates is **not** a merge blocker on this PR: report it at Medium or Low as standing debt, annotated `_(pre-existing; not introduced by this PR)_`. Absent-surface findings on a greenfield service, where the PR *is* the whole service, are all in-scope - but do not tier them all High. A review that emits one `[Must]` per surface reads as none. Calibrate by what gates first production traffic: **High** for anything that leaks data, hides an active failure, or cannot be retrofitted without a redeploy of every caller (secrets in logs, no error signal, no request metrics); **Medium** for surfaces that make diagnosis slower but are additive later (pprof, queue-depth gauges, custom spans); **Low** for polish. Say in the Summary that the service ships without them and what the first-week follow-up is - a greenfield review is a sequencing document, not a merge gate. Without this, a routine PR collects a `[Must]` for every surface the service has never had.

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

- [ ] **SDK initialized in `main.go` BEFORE `gin.New()`.** Not because late init yields a permanent no-op - `otel.Tracer()` returns a delegating global that rewires when `otel.SetTracerProvider` runs, so a finding claiming "no-op tracer" is a false positive. The real defects are that spans emitted between engine construction and SDK init are lost, and that the ordering breaks outright the moment the middleware is given an explicit provider (`otelgin.WithTracerProvider(tp)`), which is the normal way to stop depending on globals
- [ ] **`tp` handle kept and shut down at process exit** - a `defer tp.Shutdown(...)` declared inside the init function runs when *that function* returns, draining the batch processor microseconds after it starts. The handle must reach `main`'s signal-handling block
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

- [ ] **`net/http/pprof` registered** on separate admin port, OR non-prod only, OR behind admin auth
- [ ] **Profiles accessible**: `/debug/pprof/{heap,goroutine,profile,mutex,block}`
- [ ] **`runtime.SetMutexProfileFraction(rate)` and `SetBlockProfileRate(rate)`** enabled - without these, mutex/block profiles are empty
- [ ] **NOT on prod public port without auth** - delegate to security review

### Step 8 - Asynq / Kafka / Background Jobs

Skip and mark N/A when `Messaging` is `none`. The rows are written Asynq-first; the Kafka column gives the franz-go equivalent, and a row with no equivalent is dropped rather than reported as a gap.

| Check | Asynq | Kafka (franz-go) |
| ----- | ----- | ---------------- |
| Trace propagation across the dispatch boundary | Middleware on `asynq.ServeMux` extracts traceparent from task headers and restarts the span | Producer injects the propagator's carrier into `kgo.RecordHeader`; consumer extracts from `r.Headers` and starts a `SpanKindConsumer` span per record. Absent headers on the producer side is the more common half to miss |
| Queue depth | `asynq.NewInspector(...)` polled into gauges (`pending`, `active`, `scheduled`, `retry`, `archived`) | `kadm.Client.Lag(ctx, group)` polled into a per-topic/partition gauge. Kafka has none of Asynq's five states - lag is the signal |
| Per-task / per-record metrics | latency histogram, retry counter, failure counter | same, labelled by `topic` and outcome - never by key, SKU, or record id |
| Handler logger binding | `task_id`, `task_type`, sanitized payload fields | `topic`, `partition`, `offset`, and the record key when it is a bounded identifier - without the offset a poison record cannot be located |
| Outbound HTTP from the worker | `otelhttp.NewTransport(...)` | same |
| Scheduled work | scheduled tasks emit spans; missed-execution alerting | n/a unless a scheduler exists |

### Step 9 - Graceful Shutdown

- [ ] **`signal.NotifyContext`** pattern: `ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT); defer stop()`. HTTP server in goroutine; main blocks on `<-ctx.Done()`; then `srv.Shutdown(shutdownCtx)`
- [ ] **Bounded shutdown timeout:** `context.WithTimeout(context.Background(), 30*time.Second)` - never indefinite
- [ ] **`tp.Shutdown(shutdownCtx)`** flushes buffered spans
- [ ] **`Asynq.Server.Shutdown()`** drains workers. For Kafka, `client.Close()` leaves the group and flushes produce buffers - it does **not** commit consumed offsets when `kgo.DisableAutoCommit()` is set, which is the normal manual-commit setup. Then the shutdown path must `CommitUncommittedOffsets(ctx)` before `CloseAllowingRebalance()`, or the next member re-reads and re-delivers everything since the last commit
- [ ] **`db.Close()`** on shutdown

### Step 10 - Error Tracking (Sentry / Honeybadger)

- [ ] **SDK initialized:** `sentry.Init(...)` in `main.go`; `sentrygin.New(...)` middleware applied. `sentrygin` reports **panics only** - it does not forward `c.Errors`, so a handler that logs an error and returns 500 sends Sentry nothing. Check separately that error paths call `sentry.CaptureException` / `hub.CaptureException`; a service whose dominant failure mode is a failing dependency rather than a panic is otherwise silent in Sentry
- [ ] **DSN / API key** from env / Vault, never committed
- [ ] **Release / environment** populated from build metadata
- [ ] **PII scrubbing:** `SendDefaultPII: false`; `BeforeSend` strips sensitive keys
- [ ] **OTel correlation forwarded** so errors link to traces / users
- [ ] **Sample rate explicit:** `TracesSampleRate`, `ProfilesSampleRate` per env; not `1.0` in prod for tracing
- [ ] **Ignored errors documented:** domain errors filtered via `BeforeSend` / `IgnoreErrors`
- [ ] **Gin error middleware calls `sentry.CaptureException(err)`** before transforming
- [ ] **`sentry.Recover()` deferred at goroutine boundaries** outside request lifecycle (Gin recovery only covers request goroutines)

### Step 11 - Health and SLIs

The health-endpoint checks run at **all depths** whenever the diff touches health or probe endpoints, or adds a dependency an existing probe now covers - a probe regression is a per-PR finding. Only the SLI/SLO items below are deep-gated, and the verify pass that follows this step is not gated at all.

At `deep`, each SLI/SLO suggestion names: the journey, the objective (quoted from the project's own docs when they state one), the PromQL the SLI would be computed from, and what currently blocks it. Add the error budget the objective implies when the window is known.

- [ ] Critical journeys have at least one SLI (request rate, success rate, p95 latency)
- [ ] **Three distinct endpoints, not one `/health`** (single `/health` is a per-PR finding):
  - **`/livez`** - returns 200 unconditionally; no dependency pings (coupling makes Postgres blip restart all replicas)
  - **`/readyz`** - own-pod-only checks (DB pool, Redis, Asynq client); tight timeouts; no third-party pings (would pull replicas from LB on outage)
  - **`/internal/deps`** / **`/debug/health`** - JSON per-dependency status for dashboards; NOT for K8s probes. Verify manifest probes don't point here
- [ ] Health endpoints return JSON with per-dependency status (on dependency-observability endpoint)
- [ ] SLO targets documented in code (`internal/slo/*.go` or README)

### Step 11.5 - Verify Findings

Runs at every depth. Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - never re-derive one from the impact tier afterwards. Carry its provenance annotation onto the finding heading and its tally into the Summary's `Findings verified` slot. Subagent runs skip this step and return findings tagged by tier alone.

### Step 12 - Write Report

Standalone only - subagent runs return the whole Output Format below (Summary, Surface Map, Findings, Recommendations, Next Steps) to the parent, which writes the single merged report. Ignore the writer vocabulary in the Output Format preamble on that path; there is no `report_body` input when nothing is written.

The round was resolved in Step 2; pass it through. The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.

Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (the branch short name, never the literal `HEAD`), refs from the precondition handle, `base_sha`/`head_sha` from Step 2, `stack: go-gin`, `scope: +obs`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved above. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface, or when the invocation mode makes it inapplicable (subagent, `standard` depth).

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed (or accepted from parent); data-access mix and messaging recorded
- [ ] Surface Map emitted with one verdict per surface; absent surfaces collapsed per the grouping rule; diff-vs-repo scope rule applied before assigning tiers
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
- [ ] Depth honored: every step ran; `deep` added SLI/SLO suggestions with objective, PromQL and blocker
- [ ] Step 11.5 ran (standalone): findings labelled before verify, verify's labels and annotations carried onto the headings verbatim, tally in the Summary
- [ ] Out-of-lens defects routed rather than dropped
- [ ] Next Steps with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend
- [ ] Standalone: report written via `review-report-writer` with the round resolved from `review-observability-<branch>.md`, confirmation printed. Subagent: Output Format returned, no file written, no confirmation

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Go Observability Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
- **Messaging:** Asynq | Kafka | none
- **Logging:** slog (JSON) | slog (text) | log (stdlib) | absent
- **Metrics:** prometheus/client_golang | OTel metrics (Prometheus exporter) | absent
- **Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
- **pprof:** enabled (admin port) | enabled (non-prod only) | enabled (public, prod) [security finding] | absent
- **Graceful shutdown:** wired | partial | absent
- **Messaging instrumentation:** OTel middleware | partial | absent | n/a (no broker) _(name the broker: "Kafka instrumentation", "Asynq instrumentation")_
- **Error Tracker:** Sentry | Honeybadger | absent
- **Overall:** Adequate | Gaps Found - <N> High / <N> Medium / <N> Low | Greenfield - no surface wired, <N> High / <N> Medium / <N> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(parenthetical omitted when K is 0; whole line omitted on subagent runs)_

## Surface Map

| Surface                    | Verdict                        | Evidence                                   |
| -------------------------- | ------------------------------ | ------------------------------------------ |
| slog logging               | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK          | wired / partial / absent       | [...]                                      |
| Prometheus metrics         | wired / partial / absent       | [...]                                      |
| pprof endpoints            | wired / partial / absent       | [...]                                      |
| <broker> instrumentation   | wired / partial / absent / n/a | [...]                                      |
| Graceful shutdown          | wired / partial / absent       | [...]                                      |
| Error tracker              | wired / partial / absent       | [...]                                      |

Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent` - it tells the reader the review is scaffolding, not auditing. Keep the same `absent` vocabulary throughout. A surface that is wired but misconfigured stays `wired`; the defect goes in Evidence and in a finding.

## Findings

### High Impact

#### 1. [Label] file:line - <short title> _(provenance annotation, when Step 11.5 assigned one)_

- **Location:** [file:line or config key]

- **Issue:** [name the idiom: missing slog redaction for `Authorization`, unbounded label cardinality on `user_id`, `tp.Shutdown` deferred inside the init function, missing traceparent on the dispatch boundary, route label is actual path not template]

- **Impact:** [diagnosability | alertability | cost | exposure | availability - pick the one that dominates; a probe that couples liveness to a shared dependency is availability, not diagnosability]

- **Fix:** [specific Go / OTel / slog / Prometheus change with code]

#### 2. [Label] file:line - <short title>

[Same block]

### Medium Impact

[Same blocks, numbering continues]

### Low Impact

[Same blocks, numbering continues]

Omit empty sections. Within a tier, order by surface when more than two findings share one. `[Label]` comes from Step 11.5; on subagent runs derive it from the tier (High -> `[Must]`, Medium / Low -> `[Recommend]`). Blank lines separate the field lines - consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

**A defect outside this lens** found while reading the instrumentation surface - a leaked `resp.Body`, a missing timeout, an auth gap - is not dropped and not filed as an observability finding. Add it to a closing `### Out of Lens` list under Recommendations with its `file:line` and the owning lens, so the reader can route it.

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.
Impact maps to intent: High -> [Must]; Medium / Low -> [Recommend].

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-observability-<branch>.md`
- Writing a report when invoked as a subagent - the parent owns it
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
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
