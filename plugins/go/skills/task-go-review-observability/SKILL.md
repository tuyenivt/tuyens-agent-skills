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

# Go Observability Review

Go-aware review naming `slog`, OpenTelemetry SDK + auto-instrumentation (`otelgin`, `otelhttp`, the `gorm.io/plugin/opentelemetry/tracing` plugin, Asynq middleware), `prometheus/client_golang`, `net/http/pprof`, graceful shutdown, error-tracker SDKs (`sentry-go`). Library-level scope; infra (Datadog dashboards, Grafana alert rules, log forwarder config) stays out.

Stack-specific delegate of `task-code-review-observability` for Go.

## When to Use

- Go/Gin PR for observability regressions or instrumentation gaps
- Pre-release check for a new service or major feature
- Post-incident review when diagnosis was slow
- Adopting OpenTelemetry / slog / Prometheus

**Not for:** general review (`task-go-review`), perf with known bottleneck (`task-go-review-perf`), infra observability.

**Version floors.** The checks assume semconv v1.27.0+ (`deployment.environment.name`), sentry-go v0.48.0+ (`ClientOptions.DataCollection`), and asynq v0.26+ (`NewTaskWithHeaders` / `Task.Headers`). Read the pinned versions in `go.mod` before citing a field; below a floor, name the older form the pinned release has.

## Depth

| Depth      | What runs                                                |
| ---------- | -------------------------------------------------------- |
| `standard` | All steps                                                |
| `deep`     | All steps + SLI/SLO suggestions (`### SLI / SLO` under Recommendations) |

Default: `standard`. Request deep by appending `deep` to the invocation (e.g. `/task-go-review-observability <branch> deep`).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-observability` | Current branch vs base; fails fast on trunk |
| `/task-go-review-observability <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-observability pr-<N>` | PR head fetched into local branch (user runs fetch) |

**Subagent runs** (e.g. spawned by `task-go-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, the data-access mix, and messaging. Step 3 is skipped whole, SHA capture included - never re-run git. Steps 13 and 14 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier (High -> `[Must]`, Medium / Low -> `[Recommend]`), a finding whose cited line the diff did not add carries `_(pre-existing)_` and no other annotation (the parent's verify adds `newly reachable via`) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 15 returns the entire Output Format - Summary, Surface Map, Findings, Out of Lens, Recommendations (with the deep `### SLI / SLO` block when the parent's depth is `deep`), Next Steps - instead of writing, and prints no confirmation. Derive `Messaging` from `go.mod` and the diff when the parent did not send it.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its Rules.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Go, stop and recommend `/task-code-review-observability`.

Versions come from `go.mod` - the Go version from the `go` directive, Gin / GORM / sqlx from the `require` lines - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence). Data access is GORM / sqlx / database/sql, or `mixed - GORM <v> + sqlx <v>` when both are required. Messaging is `Asynq`, `Kafka`, `Asynq + Kafka`, or `none`, from `go.mod`: `hibiken/asynq` for Asynq; `twmb/franz-go`, `IBM/sarama` (`Shopify/sarama` before v1.40.0), `segmentio/kafka-go` or `confluentinc/confluent-kafka-go` for Kafka.

### Step 3 - Resolve Diff and Round

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check` with `report_type: review-observability`. Any fail-fast: surface verbatim and stop. Read diff, log and `git diff --name-status <base_ref>...<head_ref>` once; reuse. Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs). The writer's `branch` is the handle's `head_short_name`.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha` and the invocation asks for nothing more (no `deep` where the prior was `standard`), print `No new commits on <head_short_name> since prior observability review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite. On a genuine round 2+, re-review the full range; Step 14 reconciles the prior findings.

### Step 4 - Read the Instrumentation Surface

**Most important output:** a one-line verdict per surface - logging, OTel, Prometheus, one instrumentation row per broker `Messaging` reported, pprof, graceful shutdown, error tracker - of the form `wired | partial | absent | n/a`. A missing wire is itself the finding.

The verdict answers **how much of the surface exists**, not whether it is correct: `wired` = every piece is present (misconfigured pieces stay `wired`, with the defect in the Evidence cell and a finding); `partial` = the mechanism is installed but does not cover everything it should (an SDK with no DB or HTTP instrumentation, a shutdown path that misses a client, a logger with no redaction, pprof registered without `SetMutexProfileFraction` / `SetBlockProfileRate`); `absent` = nothing is wired. A correctly-built OTel SDK that instruments no dependency is `partial`, not `wired`.

**Grouping rule.** When a whole surface is `absent`, produce a **single finding** for that surface listing missing pieces grouped by file/symbol - not one finding per sub-bullet. When the surface's gaps straddle impact tiers, keep the grouping and file at the strongest tier; split only when a sub-gap needs a materially different fix - a leaked secret in a `%+v` call is not fixed by wiring a JSON handler, so it is its own finding even though both sit on the logging surface. Per-callsite findings only when the surface exists and a specific callsite misuses it.

**Severity, and the diff-vs-repo scope rule.** A surface the diff touches - or that the diff makes load-bearing, such as sub-instrumentation missing on an unchanged client once this PR installs the tracer that would have used it - is scored on consequence, High when it leaves a failure undiagnosable. A surface the diff never approaches and never activates is **not** a merge blocker on this PR: report it at Medium or Low as standing debt; Step 13 annotates it `_(pre-existing)_`. Absent-surface findings are all in-scope only when the diff adds the service's entrypoint (`cmd/*/main.go` is `A` in the name-status); a Greenfield `Overall` on an existing service keeps the diff-vs-repo scope rule and the three-finding cap. Even then, do not tier them all High. A review that emits one `[Must]` per surface reads as none. Calibrate by what gates first production traffic: **High** for anything that leaks data, hides an active failure, or cannot be retrofitted without a redeploy of every caller (secrets in logs, no error signal, no request metrics); **Medium** for surfaces that make diagnosis slower but are additive later (pprof, queue-depth gauges, custom spans); **Low** for polish. Say in the Summary that the service ships without them and what the first-week follow-up is - a greenfield review is a sequencing document, not a merge gate.

**Defects outside the diff or the lens.** A defect on a line the diff did not add: in this lens and made newly reachable or load-bearing by the diff -> a finding (Step 13 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 13 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential - a grouped absent-surface finding counts once - the rest one line each under `## Out of Lens`; owned by another lens (a leaked `resp.Body`, a missing timeout, an auth gap, an error middleware never mounted) -> `## Out of Lens` with `file:line` and the owning lens.

Open files that configure observability so findings cite real lines:

- `cmd/api/main.go` / `internal/observability/*.go` - OTel SDK wiring, exporter setup, instrumentation registration
- `internal/log/log.go` - `slog` setup (handler, level, redaction)
- Config struct - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, log level, Sentry DSN, Prometheus port
- `go.mod` - the pinned `go.opentelemetry.io/otel`, `prometheus/client_golang`, `getsentry/sentry-go`, `hibiken/asynq` versions against the floors above
- Every changed file calling `slog.*`, registering Prometheus, defining Gin middleware, instrumenting OTel

### Step 5 - Structured Logging (slog)

- [ ] Production logger emits JSON: `slog.NewJSONHandler(os.Stdout, ...)`. No `fmt.Println` / `log.Printf` in prod paths
- [ ] **Correlation fields** in every line: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs (`order_id`). Wired via request-id middleware + derived logger on `gin.Context`, OR via a `slog.Handler` wrapper pulling from `context.Context`
- [ ] **OTel correlation:** `slog.InfoContext(ctx, ...)` through a handler wrapper that reads `trace.SpanContextFromContext(ctx)` and adds `trace_id` / `span_id`. `go.opentelemetry.io/contrib/bridges/otelslog` is an OTLP-logs bridge to a `LoggerProvider` - it adds nothing to the JSON handler's stdout lines, so stdout-shipped logs still need the wrapper. Plain `slog.Info(...)` cannot correlate
- [ ] **Redaction:** `slog.Handler` wrapper drops `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key`; OR types implement `slog.LogValuer` to mask
- [ ] **No `slog.Info("loaded user", "user", user)` serializing a GORM model** - PII leaks via exported fields and JSON tags, unloaded associations print as zero values. Log specific fields
- [ ] **Structured key-values, not message strings.** `slog.Info("event", "user_id", id)`, never `slog.Info(fmt.Sprintf("user=%d", id))` - redaction config cannot scrub free-text, and a bare value with no key prints `!BADKEY`
- [ ] **Log levels:** Error for actionable failures, Warn for recoverable, Info for state transitions, Debug for verbose. Default Info in prod
- [ ] **No log spam in hot loops** - sample or use Debug
- [ ] **Errors as an attribute.** `slog.Error("loading order", "err", err)`, never `slog.Error(err.Error())` - slog prints `Error()` text either way and never walks `Unwrap()`; the defect is an error buried in the free-text message instead of a queryable `err` field

### Step 6 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK initialized in `main.go` BEFORE `gin.New()`.** Not because late init yields a permanent no-op - `otel.Tracer()` returns a delegating global that rewires when `otel.SetTracerProvider` runs, so a finding claiming "no-op tracer" is a false positive. The real defects are that spans emitted between engine construction and SDK init are lost, and that the ordering breaks outright the moment the middleware is given an explicit provider (`otelgin.WithTracerProvider(tp)`), which is the normal way to stop depending on globals
- [ ] **`tp` handle kept and shut down at process exit** - a `defer tp.Shutdown(...)` declared inside the init function runs when *that function* returns, draining the batch processor microseconds after it starts. The handle must reach `main`'s signal-handling block
- [ ] **OTLP exporter:** `otlptracegrpc.New(...)` / `otlptracehttp.New(...)` pointed at the collector; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Resource attributes:** `service.name`, `service.version`, `deployment.environment.name` (`semconv.DeploymentEnvironmentName`; `deployment.environment` on semconv below v1.27.0) via `resource.New(...)`
- [ ] **Sampling explicit:** `sdktrace.ParentBased(sdktrace.TraceIDRatioBased(rate))`; not `AlwaysSample` in high-traffic prod
- [ ] **Gin instrumentation:** `r.Use(otelgin.Middleware("service-name"))` - route templates as span names (avoids high-cardinality)
- [ ] **GORM:** `db.Use(tracing.NewPlugin())` from `gorm.io/plugin/opentelemetry/tracing`; SQL spans attach to the request span via context
- [ ] **sqlx:** `otelsql` wraps the driver; sqlx wraps via `sqlx.NewDb(db, "postgres")`
- [ ] **HTTP client:** `otelhttp.NewTransport(http.DefaultTransport)` wrapped into the shared `*http.Client`
- [ ] **Asynq:** producer sets traceparent via `asynq.NewTaskWithHeaders`; worker middleware reads `task.Headers()` and restarts the span
- [ ] **Redis:** `redisotel.InstrumentTracing(rdb)` from `github.com/redis/go-redis/extra/redisotel/v9` if `go-redis/v9` is in use
- [ ] **Custom spans** for business operations: `ctx, span := tracer.Start(ctx, "OrderService.Place"); defer span.End()`. No over-instrumentation
- [ ] **Span attributes** via `attribute.*` with bounded cardinality
- [ ] **`span.RecordError(err)`** on error paths

### Step 7 - Prometheus Metrics

- [ ] **Client installed** and `/metrics` exposed (`r.GET("/metrics", gin.WrapH(promhttp.Handler()))`), or OTel metrics with Prometheus exporter
- [ ] **Default Go runtime metrics** scraped (`go_goroutines`, `go_memstats_*`, `go_gc_duration_seconds`, `process_*`)
- [ ] **HTTP server metrics:** `http_request_duration_seconds` (histogram) + `http_requests_total` (counter) with route / method / status. **Route label must be the template** (`/orders/:id`), not the actual path (`/orders/123`) - cardinality explodes otherwise
- [ ] **Custom business metrics** under consistent namespace (`acme_orders_placed_total`); suffix conventions (`_total`, `_seconds`, `_bytes`)
- [ ] **Bounded label cardinality** - no `user_id`, `order_id`, `request_id` as labels; only enums / known categories
- [ ] **No metric registration in hot path** - construct at `var (...)` or app startup, not per-request (`panic: duplicate metrics collector registration`)
- [ ] **`MustRegister`** (not `Register`) at startup so errors fail fast
- [ ] **Histogram buckets** chosen for SLO; sub-100ms paths need finer buckets than `prometheus.DefBuckets`

### Step 8 - pprof

- [ ] **`net/http/pprof` registered** on separate admin port, OR non-prod only, OR behind admin auth; on the prod public port without auth it is a security finding - route it to `## Out of Lens`
- [ ] **Profiles accessible**: `/debug/pprof/{heap,goroutine,profile,mutex,block}`
- [ ] **`runtime.SetMutexProfileFraction(rate)` and `SetBlockProfileRate(rate)`** enabled - without these, mutex/block profiles are empty and the surface is `partial`

### Step 9 - Asynq / Kafka / Background Jobs

Skip when `Messaging` is `none`: the Surface Map gets one `Messaging instrumentation | n/a` row and the Summary no broker line. The rows are written Asynq-first; the Kafka column gives the franz-go equivalent, and a row with no equivalent is dropped rather than reported as a gap. For a Kafka client other than franz-go, apply each row's intent through that client's own API and cite it, never a `kgo` / `kadm` symbol.

| Check | Asynq | Kafka (franz-go) |
| ----- | ----- | ---------------- |
| Trace propagation across the dispatch boundary | Middleware on `asynq.ServeMux` extracts traceparent from `task.Headers()` and restarts the span | Producer injects the propagator's carrier into `kgo.RecordHeader`; consumer extracts from `r.Headers` and starts a `SpanKindConsumer` span per record. Absent headers on the producer side is the more common half to miss |
| Queue depth | `asynq.NewInspector(...)` polled into gauges from `QueueInfo` (`Pending`, `Active`, `Scheduled`, `Retry`, `Archived`; plus `Completed` / `Aggregating` when retention or task groups are used) | `kadm.Client.Lag(ctx, group)` polled into a per-topic/partition gauge. Kafka has no per-task states - lag is the signal |
| Per-task / per-record metrics | latency histogram, retry counter, failure counter | same, labelled by `topic` and outcome - never by key, SKU, or record id |
| Handler logger binding | `task_id`, `task_type`, sanitized payload fields | `topic`, `partition`, `offset`, and the record key when it is a bounded identifier - without the offset a poison record cannot be located |
| Outbound HTTP from the worker | `otelhttp.NewTransport(...)` | same |
| Scheduled work | scheduled tasks emit spans; missed-execution alerting | n/a unless a scheduler exists |

### Step 10 - Graceful Shutdown

- [ ] **`signal.NotifyContext`** pattern: `ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT); defer stop()`. HTTP server in goroutine; main blocks on `<-ctx.Done()`; then `srv.Shutdown(shutdownCtx)`
- [ ] **Bounded shutdown timeout:** `context.WithTimeout(context.Background(), 30*time.Second)` - never indefinite
- [ ] **`tp.Shutdown(shutdownCtx)`** flushes buffered spans
- [ ] **`asynq.Server.Shutdown()`** drains workers. For Kafka, `client.Close()` leaves the group and cancels the client context, which **fails** buffered produce records and commits nothing under `kgo.DisableAutoCommit()` (the normal manual-commit setup). The shutdown path is `Flush(ctx)`, then `CommitUncommittedOffsets(ctx)`, then `Close()`; `CloseAllowingRebalance()` applies only to clients using `BlockRebalanceOnPoll`; another client follows its own flush / commit / close sequence. Skipping the commit makes the next member re-read everything since the last commit
- [ ] **DB pool closed** on shutdown: `sqlDB, _ := db.DB(); sqlDB.Close()` for GORM (`*gorm.DB` has no `Close`); `db.Close()` for `*sql.DB` / `*sqlx.DB`

### Step 11 - Error Tracking (Sentry / Honeybadger)

- [ ] **SDK initialized:** `sentry.Init(...)` in `main.go`; `sentrygin.New(...)` middleware applied. `sentrygin` reports **panics only** - it does not forward `c.Errors`, so a handler that logs an error and returns 500 sends Sentry nothing. Check separately that error paths call `sentry.CaptureException` / `hub.CaptureException`, and that the Gin error middleware does so before transforming the error; a service whose dominant failure mode is a failing dependency rather than a panic is otherwise silent in Sentry
- [ ] **DSN / API key** from env / Vault, never committed
- [ ] **Release / environment** populated from build metadata
- [ ] **PII scrubbing:** `ClientOptions.DataCollection` configured (it overrides `SendDefaultPII`; `SendDefaultPII: false` on SDKs that predate it); `BeforeSend` strips sensitive keys
- [ ] **OTel correlation forwarded** so errors link to traces / users
- [ ] **Sample rate explicit:** `TracesSampleRate` or `TracesSampler` per env; not `1.0` in prod
- [ ] **Ignored errors documented:** domain errors filtered via `BeforeSend` / `IgnoreErrors`
- [ ] **`sentry.Recover()` deferred at goroutine boundaries** outside request lifecycle (Gin recovery only covers request goroutines)

### Step 12 - Health and SLIs

The health-endpoint checks run at **all depths** whenever the diff touches health or probe endpoints, or adds a dependency an existing probe now covers - a probe regression is a per-PR finding. Only the SLI/SLO items are deep-gated.

At `deep`, emit `### SLI / SLO` under Recommendations: one row per critical journey naming the objective (quoted from the project's own docs when they state one, `none documented - proposed <value>` otherwise), the PromQL the SLI would be computed from, and what currently blocks it. The `Objective` cell carries the window and the error budget it implies when known (`99.9% / 30d (budget 43m)`).

- [ ] Critical journeys have at least one SLI (request rate, success rate, p95 latency)
- [ ] **Three distinct endpoints, not one `/health`** (single `/health` is a per-PR finding):
  - **`/livez`** - returns 200 unconditionally; no dependency pings (coupling makes a Postgres blip restart all replicas)
  - **`/readyz`** - own-pod-only checks (DB pool, Redis, Asynq client); tight timeouts; no third-party pings (would pull replicas from the LB on an outage)
  - **`/internal/deps`** / **`/debug/health`** - JSON per-dependency status for dashboards; NOT for K8s probes. Verify manifest probes don't point here
- [ ] SLO targets documented in code (`internal/slo/*.go` or README)

### Step 13 - Verify Findings

Runs at every depth. Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - never re-derive one from the impact tier afterwards; a High finding tagged `[Recommend]` because it is pre-existing is correct output. Carry its `Annotation` column verbatim onto the heading (`_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`) and its tally into the Summary's `Findings verified` slot. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report.

Subagent runs skip this step entirely (see Invocation).

### Step 14 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, label and `file:line` copied from the `#### <n>. [Label] file:line - <title>` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its table under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` under the impact heading they were last published under (this round's tier when re-drafted), with the label and annotation groups they were last published with plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 15 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `stack: go-gin`, `scope: +obs`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface, or when the invocation mode makes it inapplicable (subagent, `standard` depth, round 1).

- [ ] Step 1: `behavioral-principles` loaded, or rules inlined in the spawning prompt
- [ ] Step 2: stack confirmed (or accepted from parent); versions from `go.mod`; data-access mix and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-observability` (or handle received); diff, log and name-status read once; `base_sha` / `head_sha` captured; round resolved from the handle; same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: surfaces read directly; Surface Map has one verdict per surface and one row per broker; grouping and diff-vs-repo scope rules applied before tiers; defects outside the diff or lens routed per the Step 4 rule
- [ ] Step 5: `slog` - JSON handler, correlation (handler wrapper for stdout-shipped logs; `otelslog` only when logs ship over OTLP), redaction, level discipline, errors as `err` attribute
- [ ] Step 6: OTel - SDK before the engine, `tp` reaches `main`, instrumentation per dependency, sampling and resource attrs explicit
- [ ] Step 7: Prometheus - client, runtime + HTTP metrics, namespace, bounded labels, template route label
- [ ] Step 8: pprof - gating recorded; mutex/block rates checked
- [ ] Step 9: broker rows applied per broker, or N/A
- [ ] Step 10: shutdown - `signal.NotifyContext`, bounded timeout, `tp.Shutdown`, broker sequence, pool closed
- [ ] Step 11: error tracker - SDK + middleware + explicit capture, DSN externalized, `DataCollection`, sample rate, `sentry.Recover()`
- [ ] Step 12: probe checks ran where the diff touches them; `deep` added `### SLI / SLO` with objective, PromQL, blocker
- [ ] Step 13 (standalone): findings labelled before verify; labels and annotations carried verbatim; tally in the Summary
- [ ] Step 14 (round 2+): prior report projected and reconciled with `head_sha`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 15 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written
- [ ] Findings name a Go / OTel / slog / Prometheus idiom - not "add observability"; library-level scope respected
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Overall` is `Greenfield` when 3+ Surface Map rows are `absent`, `Gaps Found` when `## Findings` publishes any finding (verified this round or carried), the tier counts including carried findings, `Adequate` otherwise. One `**<Broker> instrumentation:**` line per reported broker (`wired | partial | absent`); with `Messaging: none` the Summary has no broker line and the Surface Map one `n/a` row. `Logging` takes the value of the handler the production path constructs (a JSON handler behind an opt-in flag prod does not set reads as its fallback - `slog (text)` or `log (stdlib)`). `pprof` is `enabled (public, prod)` only with the Out of Lens security line present. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0. Any field the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Each finding is its own numbered block** under its impact heading, headed `#### <n>. [Label] file:line - <short title> _(annotations)_` where the label and annotations come from Step 13 verbatim (tier-derived label on subagent runs, with `_(pre-existing)_` on a finding whose line the diff did not add; `_(carried from round <N>)_` on carried findings). Numbering continues across tiers. Within a tier, order by surface when more than two findings share one. Blank lines separate the field lines; consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

```markdown
## Go Observability Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - GORM <version> + sqlx <version>
- **Messaging:** Asynq | Kafka | Asynq + Kafka | none
- **Logging:** slog (JSON) | slog (text) | log (stdlib) | absent
- **Metrics:** prometheus/client_golang | OTel metrics (Prometheus exporter) | absent
- **Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
- **pprof:** enabled (admin port) | enabled (non-prod only) | enabled (public, prod) | absent
- **Graceful shutdown:** wired | partial | absent
- **<Broker> instrumentation:** wired | partial | absent     {one line per broker; omit when Messaging is none}
- **Error Tracker:** Sentry | Honeybadger | absent
- **Overall:** Adequate | Gaps Found - <N> High / <N> Medium / <N> Low | Greenfield - <N> High / <N> Medium / <N> Low
- **Round:** <N>                                {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

[2-3 sentence assessment. On a Greenfield review: what ships without, and the first-week follow-up.]

## Surface Map

| Surface                    | Verdict                        | Evidence                                   |
| -------------------------- | ------------------------------ | ------------------------------------------ |
| slog logging               | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK          | wired / partial / absent       | [...]                                      |
| Prometheus metrics         | wired / partial / absent       | [...]                                      |
| pprof endpoints            | wired / partial / absent       | [...]                                      |
| <broker> instrumentation   | wired / partial / absent       | [one row per broker; with Messaging none, a single `Messaging instrumentation` row reading `n/a`] |
| Graceful shutdown          | wired / partial / absent       | [...]                                      |
| Error tracker              | wired / partial / absent       | [...]                                      |

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### High Impact

#### 1. [Label] file:line - <short title> _(annotations)_     {annotation groups only when Step 13, Step 14, or the subagent rule assigned any}

- **Location:** [file:line or config key]

- **Issue:** [name the idiom: missing slog redaction for `Authorization`, unbounded label cardinality on `user_id`, `tp.Shutdown` deferred inside the init function, missing traceparent on the dispatch boundary, route label is actual path not template]

- **Impact:** [diagnosability | alertability | cost | exposure | availability - pick the one that dominates; a probe that couples liveness to a shared dependency is availability, not diagnosability]

- **Fix:** [specific Go / OTel / slog / Prometheus change with code]

#### 2. [Label] file:line - <short title>

[Same block]

### Medium Impact / Low Impact

[Same blocks, numbering continues]

Omit empty sections. When every section is empty, write "No observability issues found."

## Out of Lens

[Defects another lens owns, and pre-existing in-lens defects beyond the three published - each with `file:line` and the owning lens. Omit when there are none.]

## Recommendations

[Structural improvements not tied to a specific finding]

### SLI / SLO     {deep only}

| Journey | Objective | SLI (PromQL) | Blocked by |
| ------- | --------- | ------------ | ---------- |

## Next Steps

Each tagged `[Implement]` or `[Delegate]` (`[scope: <owner>]` on delegated items). Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting gaps without naming the idiom ("add metrics" vs "register `acme_orders_placed_total` Counter at module level via `MustRegister`")
- Reviewing infra (Datadog settings, Grafana panels, log forwarder, on-call) or prescribing an OTLP endpoint URL / Sentry DSN value - not in source code
- One finding per missing checkbox when a whole surface is absent
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
