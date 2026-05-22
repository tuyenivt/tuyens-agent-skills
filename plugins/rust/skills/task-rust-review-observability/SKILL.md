---
name: task-rust-review-observability
description: Rust / Axum observability review: tracing, OpenTelemetry SDK, metrics-exporter-prometheus, tokio-console, sentry-rust, graceful shutdown.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, observability, tracing, opentelemetry, prometheus, tokio-console, sentry, workflow]
  type: workflow
user-invocable: true
---

Stack-specific delegate of `task-code-review-observability` for Rust. Library/SDK-level only - infra config (Datadog, Grafana, alert rules, log forwarders) is out of scope.

## When to Use

- Rust/Axum PR observability review or regression check
- Pre-release or post-incident observability audit
- Adopting `tracing` / OpenTelemetry / Prometheus in a Rust service
- Auditing trace propagation across `tokio::spawn` / Kafka / AMQP

**Not for:** general review (`task-rust-review`), perf (`task-rust-review-perf`), active incidents (`/task-oncall-start`), infra dashboards/alerts.

## Depth

| Depth      | When                                       | What Runs                                          |
| ---------- | ------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single handler / task                      | Steps 1-6, 12                                      |
| `standard` | Default                                    | All steps except 11                                |
| `deep`     | Pre-release of critical service, post-incident | All steps including SLI/SLO (Step 11)          |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Confirm Rust / Axum. If not Rust, stop and redirect to `/task-code-review-observability`. Record data access (sqlx / diesel / mixed) and messaging (Tokio queue / AMQP / Kafka / none) - later steps branch on these.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely if a parent workflow passed the handle plus pre-read artifacts.

### Step 4 - Surface Map

Read instrumentation wiring in `src/main.rs`, `src/observability/`, `Cargo.toml`, and every changed file calling `tracing::*`, `metrics::*`, or registering a tower layer. Also read `migrations/` - a new business column (status, audit, lifecycle) without a corresponding metric / span attribute is a Medium finding.

Produce one verdict per surface: `wired | partial | absent` with file:line evidence. A missing wire is the finding, not a precondition.

| Surface                   | Look for                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------- |
| tracing logging           | `tracing_subscriber::fmt::layer().json()`, formatter + filter + redaction layers in `Registry`          |
| OpenTelemetry SDK         | `opentelemetry_otlp::new_pipeline()...install_batch`, `tracing-opentelemetry` bridge, resource attrs   |
| Metrics exporter          | `metrics-exporter-prometheus` / `axum-prometheus`, `/metrics` bind, `describe_*!` at startup           |
| tokio-console             | `console_subscriber::init`, feature gate, loopback/admin bind                                          |
| Messaging instrumentation | `reqwest-tracing`, `tower-http::TraceLayer`, `rdkafka` / `lapin` traceparent extraction                |
| Error tracker             | `sentry::init`, `sentry-tower`, `sentry-tracing`                                                       |

**Grouping rule.** If a whole surface is `absent`, produce one High finding listing the missing pieces grouped by target file/symbol - not one finding per sub-check. Per-callsite findings only apply when the surface exists.

**Greenfield exception.** If 3+ surfaces are `absent`, run Steps 5-10 at every depth (the absence is the finding); skip the per-step diff-touch gate.

### Step 5 - Structured Logging

- [ ] JSON formatter in prod (`fmt::layer().json()` or `bunyan_formatter`); no `println!` / `eprintln!` in prod paths
- [ ] Correlation fields: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs - via `tower-http::request_id` + `TraceLayer::make_span_with` + `#[tracing::instrument(fields(order_id = %id))]`
- [ ] `tracing-opentelemetry` bridge registered so logs carry OTel `trace_id` / `span_id`
- [ ] Sensitive-field redaction via custom `Layer` or manual `Debug` impls for `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key`
- [ ] Structured key-values, not template strings: `info!(order_id = %id, "processing")` not `info!("order={id}")` (redaction can't reach interpolated strings)
- [ ] Error logs use `?e` so `anyhow`/`thiserror` chains render: `error!(error = ?e, "loading order")`
- [ ] Levels disciplined; no hot-loop logging
- [ ] No `info!(?user)` dumping domain models - log explicit fields

### Step 6 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] SDK initialized in `main.rs` **before** `Router::new()` - late init means middleware captures the no-op tracer
- [ ] OTLP exporter (`tonic` or `http`); `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` env-driven
- [ ] Resource attributes `service.name`, `service.version`, `deployment.environment` populated
- [ ] Sampling explicit: `Sampler::ParentBased(Sampler::TraceIdRatioBased(rate))` per env; not `AlwaysOn` in high-traffic prod
- [ ] `TraceLayer::new_for_http()` registered; span name uses **route template** not raw URI
- [ ] sqlx `tracing` feature on; `reqwest-tracing` wraps shared `reqwest::Client`; bare clients drop traceparent
- [ ] Spawned tasks propagate context (capture `Span::current()` pre-spawn and `.in_current_span()`, or carry W3C traceparent in payload)
- [ ] Kafka/AMQP consumers extract `traceparent` from headers and link to producer span
- [ ] `#[tracing::instrument(skip_all, fields(...))]` on business methods; don't wrap single sqlx queries (already spanned)
- [ ] Error paths set span error status (`OpenTelemetrySpanExt::set_status`)
- [ ] `global::shutdown_tracer_provider()` on graceful shutdown

### Step 7 - Metrics (`metrics` crate / Prometheus)

- [ ] `metrics-exporter-prometheus` bound to admin port via `PrometheusBuilder::new().with_http_listener(...)` (or OTel Prometheus exporter)
- [ ] Tokio runtime metrics via `tokio-metrics`; default `process_*` metrics exposed
- [ ] HTTP server histogram + counter via `axum-prometheus`; route label is **template** (`/orders/:id`) not actual path
- [ ] Custom metrics use consistent namespace and suffix (`_total`, `_seconds`, `_bytes`); `counter!` / `histogram!` / `gauge!` chosen correctly
- [ ] Label cardinality bounded: no `user_id` / `order_id` / `request_id` as labels - enum/category values only
- [ ] `describe_counter!` / `describe_histogram!` at startup for help text and units
- [ ] Histogram buckets tuned to SLO when sub-100ms paths exist (`set_buckets_for_metric`)

### Step 8 - tokio-console / Runtime Introspection

_Skip at `quick` unless diff touches `console_subscriber` or task instrumentation (or greenfield exception applies)._

- [ ] `console_subscriber::init()` gated by feature flag / env var (overhead + debug port)
- [ ] Cargo `tokio_unstable` enabled when in use
- [ ] Bound to `127.0.0.1` or behind admin auth, never public in prod (also a security finding - delegate)
- [ ] Long-lived tasks named via `tokio::task::Builder::new().name(...)`
- [ ] `#[tracing::instrument]` on async fns for call-graph visibility

### Step 9 - Background Tasks / Messaging

_Skip at `quick` unless diff touches tasks or brokers (or greenfield exception applies)._

- [ ] Trace context crosses spawn/dispatch boundary (in-process: `Span::current()` capture; out-of-process: W3C traceparent in payload)
- [ ] Per-task metrics: latency histogram, retry counter, failure counter, queue-depth gauge
- [ ] `#[tracing::instrument(fields(task_id = %id, task_type = %t))]` at task entry
- [ ] Outbound HTTP from tasks wrapped via `reqwest-tracing`
- [ ] Scheduled tasks emit spans; stalled-task / queue-health metric for missed-execution alerting
- [ ] Kafka (`rdkafka`) / AMQP (`lapin`) consumers extract traceparent from headers - no auto-instrumentation

### Step 10 - Graceful Shutdown

_Skip at `quick` unless diff touches lifecycle / `main.rs` (or greenfield exception applies)._

- [ ] SIGINT + SIGTERM via `tokio::signal::ctrl_c` and `signal::unix::SignalKind::terminate()` combined under `tokio::select!`
- [ ] `axum::serve(...).with_graceful_shutdown(...)` drains in-flight requests
- [ ] `tokio::time::timeout` wraps the drain (e.g., 30s) so shutdown can't hang
- [ ] `global::shutdown_tracer_provider()` flushes spans before exit
- [ ] `CancellationToken` cancelled; worker `JoinSet::shutdown().await` joins cleanly
- [ ] sqlx `pool.close().await` when in-flight queries should complete

### Step 11 - Error Tracking (Sentry)

_Skip at `quick` unless diff touches error handlers, Sentry config, or DSN handling._

- [ ] `sentry::init` in `main.rs`; `sentry-tower::NewSentryLayer` + `SentryHttpLayer` on router
- [ ] DSN in env / Vault, not committed
- [ ] `release` and `environment` from build metadata
- [ ] `send_default_pii: false`; `before_send` scrubs known sensitive keys
- [ ] `sentry-tracing` layer in subscriber so `tracing::error!` becomes Sentry events
- [ ] `traces_sample_rate` / `profiles_sample_rate` per env; not `1.0` in prod
- [ ] Domain errors (`AppError::NotFound`, `AppError::Validation`) filtered in `before_send`, each ignore commented
- [ ] Spawned tasks capture panics (`sentry::integrations::panic` or `JoinError::is_panic` check)

### Step 12 - Health + SLIs (deep only)

- [ ] Critical journeys have at least one SLI (request rate, success rate, p95 latency)
- [ ] **Three-way health split:**
  - `/livez`: returns OK only, no deps - DB blip must not restart-loop pods
  - `/readyz`: own-pod deps (sqlx `pool.acquire`, Redis ping, in-process queue); **no third-party pings** - else a Stripe blip pulls every replica from the LB
  - `/internal/deps`: rich JSON for dashboards, never wired to a probe
- [ ] SLO targets in code (`src/slo/*.rs` or module README), not floating in Confluence

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

_Use `absent` consistently (not `none`/`missing`/`not wired`). Set Overall to `Greenfield` when 3+ rows are `absent`._

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Rust idiom: missing `tracing-opentelemetry` bridge, unbounded `user_id` label, OTel SDK init after `Router::new()`, missing `reqwest-tracing`, route label is actual path, `console_subscriber` on public bind]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific `tracing` / OTel / `metrics` change with code/config]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty buckets. Within each bucket, group by surface when >2 findings share one; otherwise list flat. Greenfield collapses a whole surface into one finding per the Step 4 grouping rule._

## Recommendations

[Structural improvements not tied to a single finding]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [action]
2. **[Delegate]** [High] [scope: ops] - [action]
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Rust / Axum; data access and messaging recorded
- [ ] Step 3: diff and commit log read once and reused (or handle accepted from parent)
- [ ] Step 4: surface map produced with 6 verdicts and evidence; grouping/greenfield rules applied
- [ ] Step 5: logging assessed (JSON, correlation, redaction, structured fields, error chain rendering)
- [ ] Step 6: OTel SDK init order, exporter, sampling, auto-instrumentation, spawn context, span shutdown assessed
- [ ] Step 7: exporter, runtime + HTTP metrics, namespace/labels/buckets, `describe_*!` assessed
- [ ] Step 8: `console_subscriber` gating + bind safety (skipped per gate when applicable)
- [ ] Step 9: trace propagation, per-task metrics, broker traceparent (skipped per gate when applicable)
- [ ] Step 10: signals, graceful drain + timeout, tracer/pool shutdown (skipped per gate when applicable)
- [ ] Step 11: Sentry SDK, DSN externalization, PII scrub, sample rates, panic capture (skipped per gate when applicable)
- [ ] Step 12: SLIs and three-way health split assessed (deep only)
- [ ] Step 13: report written via `review-report-writer`; confirmation printed

## Avoid

- Generic advice when a Rust idiom exists ("add HTTP tracing" vs "register `TraceLayer::new_for_http()`")
- Per-checkbox findings when a whole surface is absent - collapse per the Step 4 grouping rule
- Approving OTel SDK init after `Router::new()` - middleware captures the no-op tracer
- Approving unbounded labels (`user_id`, `order_id`) or actual-path route labels
- Approving `metrics::counter!` without `describe_counter!`
- Approving `Sampler::AlwaysOn` in high-traffic prod
- Approving `console_subscriber` on a public bind in prod (also delegate to security review)
- Approving plain `tracing` logs without the `tracing-opentelemetry` bridge when OTel is wired
- Prescribing concrete OTLP endpoint URLs or Sentry DSN values - say "from env / Vault" and stop
- Infra-level scope (Datadog, Grafana, alerts, forwarders) - belongs to ops review
- State-changing git commands
