---
name: task-rust-review-observability
description: "Rust / Axum observability review: tracing, tracing-opentelemetry, OTel SDK, metrics-exporter-prometheus, tokio-console, sentry, graceful shutdown."
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, observability, tracing, opentelemetry, prometheus, tokio-console, sentry, workflow]
  type: workflow
user-invocable: true
---

Stack-specific delegate of `task-code-review-observability` for Rust. Library / SDK level only - infra config (Datadog, Grafana, alert rules, log forwarders) is out of scope.

## When to Use

- Rust / Axum PR observability review or regression check
- Pre-release or post-incident observability audit
- Adopting `tracing` / OpenTelemetry / Prometheus in a Rust service
- Auditing trace propagation across `tokio::spawn` / Kafka / AMQP

**Not for:** general review (`task-rust-review`), perf (`task-rust-review-perf`), active incidents (`/task-oncall-start`), infra dashboards / alerts.

## Depth

| Depth      | When                                            | Runs                                |
| ---------- | ----------------------------------------------- | ----------------------------------- |
| `standard` | Default                                         | All steps except 12 (SLI / health)  |
| `deep`     | Pre-release of critical service, post-incident  | All steps including 12              |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Confirm Rust / Axum. If not Rust, stop and redirect to `/task-code-review-observability`. Record data access (sqlx / diesel / mixed) and messaging (Tokio queue / AMQP / Kafka / none) - later steps branch on these.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely if a parent workflow passed the handle plus pre-read artifacts.

### Step 4 - Surface Map

Read instrumentation wiring in `src/main.rs`, `src/observability/`, `Cargo.toml`, and every changed file calling `tracing::*` / `metrics::*` or registering a tower layer. Also read `migrations/` - a new business column (status, audit, lifecycle) without a corresponding metric / span attribute is a Medium finding.

Produce one verdict per surface: `wired | partial | absent` with file:line evidence. A missing wire is the finding, not a precondition.

- `wired` - surface initialized and functional end-to-end.
- `partial` - present but non-functional or incomplete: emit side wired but consumer/exporter absent (e.g. `TraceLayer` registered with no `Registry` init), or surface exists with a callsite defect (unbounded label, actual-path route label). Default to `partial` over `absent` when any wiring exists.
- `absent` - surface not present at all.

| Surface                   | Look for                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------- |
| tracing logging           | `tracing_subscriber::fmt::layer().json()`, formatter + filter + redaction layers in `Registry`          |
| OpenTelemetry SDK         | `opentelemetry_otlp::new_pipeline()...install_batch`, `tracing-opentelemetry` bridge, resource attrs   |
| Metrics exporter          | `metrics-exporter-prometheus` / `axum-prometheus`, `/metrics` bind, `describe_*!` at startup           |
| tokio-console             | `console_subscriber::init`, feature gate, loopback / admin bind                                        |
| Messaging instrumentation | `reqwest-tracing`, `tower-http::TraceLayer`, `rdkafka` / `lapin` traceparent extraction                |
| Error tracker             | `sentry::init`, `sentry-tower`, `sentry-tracing`                                                       |

**Grouping rule.** If a whole surface is `absent`, produce one finding listing the missing pieces grouped by target file / symbol - not one finding per sub-check. Per-callsite findings only apply when the surface exists.

**Severity.** Bucket by production impact, not by checklist position:
- **High** - breaks diagnosability or alertability for a live path, or risks prod stability: OTel SDK init after `Router::new()`, unbounded metric label (`user_id` / `order_id` / actual-path route label), missing `tracing-opentelemetry` bridge when OTel is wired, no subscriber init (logs discarded), `axum::serve` without `with_graceful_shutdown`, missing SIGTERM handling, consumer not extracting `traceparent`, an `absent` core surface (logging / OTel / metrics) on a service that serves traffic.
- **Medium** - degraded but functional: business column with no metric / span attribute, missing spawn-context propagation, `install_batch` without `shutdown_tracer_provider`, no drain timeout, default `Sampler` in prod, missing per-task metrics, bare `reqwest::Client` (dropped traceparent).
- **Low / quick win** - hygiene or optional/dev-only tooling: missing `describe_*!`, unnamed long-lived task, `absent` tokio-console or Sentry (gated, dev/optional surfaces - never High purely for being absent).

**Greenfield exception.** If 3+ surfaces are `absent`, run Steps 5-11 regardless of diff-touch gate (the absence is the finding). Step 12 still depends on depth.

### Step 5 - Structured Logging

- [ ] JSON formatter in prod (`fmt::layer().json()` or `bunyan_formatter`); no `println!` / `eprintln!` in prod paths
- [ ] Correlation fields: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs - via `tower-http::request_id` + `TraceLayer::make_span_with` + `#[tracing::instrument(fields(order_id = %id))]`
- [ ] Sensitive-field redaction via custom `Layer` or manual `Debug` impls for `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key`
- [ ] Structured key-values, not template strings: `info!(order_id = %id, "processing")` not `info!("order={id}")` (redaction can't reach interpolated strings)
- [ ] Error logs render the chain: `error!(error = ?e, "loading order")` so `anyhow` / `thiserror` sources surface
- [ ] Levels disciplined; no hot-loop logging; no `info!(?user)` dumping domain models - log explicit fields

### Step 6 - OpenTelemetry SDK + Auto-Instrumentation

- [ ] SDK initialized in `main.rs` **before** `Router::new()` - late init means middleware captures the no-op tracer
- [ ] `tracing-opentelemetry` bridge registered in the `Registry` so logs carry OTel `trace_id` / `span_id`
- [ ] OTLP exporter (`tonic` or `http`); `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` env-driven
- [ ] Resource attributes `service.name`, `service.version`, `deployment.environment` populated
- [ ] Sampling explicit: `Sampler::ParentBased(Sampler::TraceIdRatioBased(rate))` per env; not `AlwaysOn` in high-traffic prod
- [ ] `TraceLayer::new_for_http()` registered; span name uses **route template** not raw URI
- [ ] sqlx `tracing` feature on; `reqwest-tracing` wraps shared `reqwest::Client`; bare clients drop traceparent
- [ ] Spawned tasks propagate context: capture `Span::current()` pre-spawn and `.in_current_span()`, or carry W3C traceparent in payload across processes
- [ ] Kafka / AMQP consumers extract `traceparent` from headers and link to producer span
- [ ] `#[tracing::instrument(skip_all, fields(...))]` on business async fns; don't wrap single sqlx queries (already spanned)
- [ ] Error paths set span error status (`OpenTelemetrySpanExt::set_status`)
- [ ] `global::shutdown_tracer_provider()` on graceful shutdown (also a Step 10 check)

### Step 7 - Metrics (`metrics` crate / Prometheus)

- [ ] `metrics-exporter-prometheus` bound to admin port via `PrometheusBuilder::new().with_http_listener(...)` (or OTel Prometheus exporter)
- [ ] Tokio runtime metrics via `tokio-metrics`; default `process_*` metrics exposed
- [ ] HTTP server histogram + counter via `axum-prometheus`; route label is the **template** (`/orders/:id`) not the actual path
- [ ] Custom metrics use consistent namespace and suffix (`_total`, `_seconds`, `_bytes`); `counter!` / `histogram!` / `gauge!` chosen correctly
- [ ] Label cardinality bounded: no `user_id` / `order_id` / `request_id` as labels - enum / category values only
- [ ] `describe_counter!` / `describe_histogram!` at startup for help text and units
- [ ] Histogram buckets tuned to SLO when sub-100ms paths exist (`set_buckets_for_metric`)

### Step 8 - tokio-console / Runtime Introspection

_Skip unless diff touches `console_subscriber` or task instrumentation (or greenfield exception applies)._

- [ ] `console_subscriber::init()` gated by feature flag / env var (overhead + debug port)
- [ ] `RUSTFLAGS="--cfg tokio_unstable"` set when the feature is on (else `console_subscriber` compiles to no-op)
- [ ] Bound to `127.0.0.1` or behind admin auth, never public in prod
- [ ] Long-lived tasks named via `tokio::task::Builder::new().name(...)`

### Step 9 - Background Tasks / Messaging

_Skip unless diff touches tasks or brokers (or greenfield exception applies). Spawn-context propagation is owned by Step 6; this step is per-task observability._

- [ ] Per-task metrics: latency histogram, retry counter, failure counter, queue-depth gauge
- [ ] `#[tracing::instrument(fields(task_id = %id, task_type = %t))]` at task entry
- [ ] Outbound HTTP from tasks wrapped via `reqwest-tracing`
- [ ] Scheduled tasks emit spans; stalled-task / queue-health metric for missed-execution alerting

### Step 10 - Graceful Shutdown

_Skip unless diff touches lifecycle / `main.rs` (or greenfield exception applies)._

- [ ] SIGINT + SIGTERM via `tokio::signal::ctrl_c` and `signal::unix::SignalKind::terminate()` combined under `tokio::select!`
- [ ] `axum::serve(...).with_graceful_shutdown(...)` drains in-flight requests
- [ ] `tokio::time::timeout` wraps the drain (e.g., 30s) so shutdown can't hang
- [ ] `global::shutdown_tracer_provider()` flushes spans before exit
- [ ] `CancellationToken` cancelled; worker `JoinSet::shutdown().await` joins cleanly
- [ ] sqlx `pool.close().await` when in-flight queries should complete

### Step 11 - Error Tracking (Sentry)

_Skip unless diff touches error handlers, Sentry config, or DSN handling (or greenfield exception applies)._

- [ ] `sentry::init` in `main.rs`; `sentry-tower::NewSentryLayer` + `SentryHttpLayer` on router
- [ ] DSN, `release`, `environment` from env / build metadata; never committed
- [ ] `send_default_pii: false`; `before_send` scrubs known sensitive keys
- [ ] `sentry-tracing` layer in subscriber so `tracing::error!` becomes Sentry events
- [ ] `traces_sample_rate` / `profiles_sample_rate` per env; not `1.0` in prod
- [ ] Domain errors (`AppError::NotFound`, `AppError::Validation`) filtered in `before_send`, each ignore commented
- [ ] Spawned tasks capture panics (`sentry::integrations::panic` or `JoinError::is_panic` check)

### Step 12 - Health + SLIs (deep only)

- [ ] Critical journeys have at least one SLI (request rate, success rate, p95 latency)
- [ ] Three-way health split:
  - `/livez`: returns OK only, no deps - a DB blip must not restart-loop pods
  - `/readyz`: own-pod deps (sqlx `pool.acquire`, Redis ping, in-process queue); **no third-party pings** - else a Stripe blip pulls every replica from the LB
  - `/internal/deps`: rich JSON for dashboards, never wired to a probe
- [ ] SLO targets live in code (module README or a dedicated module), not floating in a wiki

### Step 13 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the report to file and print the confirmation line.

## Output Format

```markdown
## Rust Observability Review Summary

**Stack:** Rust <version> / Axum <version> / Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Overall:** Adequate | Gaps Found [High/Medium/Low counts] | Greenfield - 3+ surfaces absent

## Surface Map

| Surface                   | Verdict                        | Evidence              |
| ------------------------- | ------------------------------ | --------------------- |
| tracing logging           | wired / partial / absent       | [file:line]           |
| OpenTelemetry SDK         | wired / partial / absent       | [file:line]           |
| Metrics exporter          | wired / partial / absent       | [file:line]           |
| tokio-console             | wired / partial / absent       | [file:line]           |
| Messaging instrumentation | wired / partial / absent / n/a | [file:line]           |
| Error tracker             | wired / partial / absent       | [file:line]           |

_Use `absent` consistently (not `none` / `missing` / `not wired`). Set Overall to `Greenfield` when 3+ rows are `absent`._

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Rust idiom: missing `tracing-opentelemetry` bridge, unbounded `user_id` label, OTel SDK init after `Router::new()`, missing `reqwest-tracing`, route label is actual path, `console_subscriber` on public bind, `axum::serve` without `with_graceful_shutdown`]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific `tracing` / OTel / `metrics` change with code or config]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty buckets. Within each bucket, group by surface when >2 findings share one; otherwise list flat. Greenfield collapses a whole surface into one finding per the Step 4 grouping rule._

## Recommendations

[Structural improvements not tied to a single finding]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: ops] - [action]
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Rust / Axum; data access and messaging recorded
- [ ] Step 3: diff and commit log read once and reused (or handle accepted from parent)
- [ ] Step 4: surface map produced with 6 verdicts and evidence; grouping / severity / greenfield rules applied
- [ ] Step 5: logging assessed (JSON, correlation, redaction, structured fields, error-chain rendering, levels)
- [ ] Step 6: OTel SDK init order, `tracing-opentelemetry` bridge, exporter, sampling, auto-instrumentation, spawn context, span shutdown assessed
- [ ] Step 7: exporter, runtime + HTTP metrics, namespace / labels / buckets, `describe_*!` assessed
- [ ] Step 8: `console_subscriber` gating, `tokio_unstable` cfg, bind safety, task names (run if gate or greenfield fires, else skipped)
- [ ] Step 9: per-task metrics, instrument fields, broker outbound wrapping (run if gate or greenfield fires, else skipped)
- [ ] Step 10: signals, graceful drain + timeout, tracer / pool shutdown (run if gate or greenfield fires, else skipped)
- [ ] Step 11: Sentry SDK, DSN externalization, PII scrub, sample rates, panic capture (run if gate or greenfield fires, else skipped)
- [ ] Step 12: SLIs and three-way health split assessed (deep only)
- [ ] Step 13: report written via `review-report-writer`; confirmation printed

## Avoid

- Generic advice when a Rust idiom exists ("add HTTP tracing" vs "register `TraceLayer::new_for_http()`")
- Per-checkbox findings when a whole surface is absent - collapse per the Step 4 grouping rule
- Approving OTel SDK init after `Router::new()`, unbounded labels (`user_id`, `order_id`), actual-path route labels, `Sampler::AlwaysOn` in high-traffic prod, `metrics::counter!` without `describe_counter!`, plain `tracing` logs without the `tracing-opentelemetry` bridge when OTel is wired, `console_subscriber` on a public bind, `axum::serve` without `with_graceful_shutdown`
- Prescribing concrete OTLP endpoint URLs or Sentry DSN values - say "from env / Vault" and stop
- Infra-level scope (Datadog, Grafana, alerts, forwarders) - belongs to ops review
- State-changing git commands
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
