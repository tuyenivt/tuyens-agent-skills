---
name: task-rust-review-observability
description: Rust / Axum observability review: tracing crate, OpenTelemetry SDK, prometheus metrics, tokio-console, sentry-rust, graceful shutdown (library-level).
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, observability, tracing, opentelemetry, prometheus, tokio-console, sentry, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rust Observability Review

## Purpose

Rust-aware observability review that names the `tracing` crate (structured logging + spans), `tracing_subscriber` (filter + formatter layers), OpenTelemetry Rust SDK (`opentelemetry`, `opentelemetry_sdk`, `opentelemetry-otlp`), auto-instrumentation (`tower-http::trace::TraceLayer` for Axum, `sqlx`'s built-in tracing, `tracing-opentelemetry` bridge, `reqwest-tracing`, `rdkafka` instrumentation), `metrics` crate / `metrics-exporter-prometheus` / OTel metrics, `tokio-console` / `console_subscriber` for runtime introspection, graceful shutdown via `tokio::signal::ctrl_c` / `signal::unix::SignalKind`, and error-tracker SDKs (`sentry`, `sentry-tower`, `sentry-tracing`) directly instead of routing through the generic adapter. Focuses on whether Rust production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Rust. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a Rust/Axum PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Rust service or major feature
- Post-incident review when Rust diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / `tracing` / Prometheus in a Rust app
- Auditing background-task / Kafka tracing and correlation across the request → task boundary

**Not for:**

- General Rust code review (use `task-rust-review`)
- Rust performance issues with a known bottleneck (use `task-rust-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint, handler, or task                            | Logging + Prometheus metrics check only            |
| `standard` | Default - full Rust observability review                     | All steps                                          |
| `deep`     | Pre-release of a critical Rust service, or post-incident review| All steps + SLI/SLO suggestions for Rust endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                 | Meaning                                                                                               |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `/task-rust-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-rust-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-rust-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-rust-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Async / Data-Access Surface

Use skill: `stack-detect` to confirm Rust / Axum. If invoked as a subagent of a Rust-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Rust, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect data access (sqlx / diesel / mixed) and messaging (Tokio queue / AMQP / Kafka / none). Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (logging / OTel / metrics / tokio-console / messaging instrumentation / error tracker) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below) rather than one-per-bullet.

**Grouping rule.** When a whole surface is `absent` (no `metrics-exporter-prometheus`, no OTel SDK init, no error-tracker SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/symbol they should land in - not one finding per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. This prevents 50-item dumps on greenfield reviews.

Then open the files that actually configure observability so findings cite real lines, not assumptions:

- `src/main.rs` / `src/observability/*.rs` - OpenTelemetry SDK wiring (`opentelemetry_sdk::trace::TracerProvider::builder()...build()`, OTLP exporter setup), `tracing_subscriber::Registry::default().with(layers...).init()`, `tracing-opentelemetry` bridge layer, instrumentation registration (`TraceLayer::new_for_http()`, `reqwest-tracing` middleware)
- `src/observability/logging.rs` (or equivalent) - `tracing_subscriber` setup (formatter, filter, redaction layer)
- `src/main.rs` / config struct - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, `RUST_LOG`, Sentry DSN, Prometheus scrape port
- `Cargo.toml` - confirm `tracing`, `tracing-subscriber`, `tracing-opentelemetry`, `opentelemetry`, `opentelemetry-otlp`, `metrics`, `metrics-exporter-prometheus`, `sentry`, `console-subscriber` presence and versions
- Every changed file in the diff that calls `tracing::*`, registers `metrics::counter!` / `histogram!` / `gauge!`, defines a tower middleware, instruments with OTel, or modifies span context
- Every changed file under `migrations/` - new business columns (status, audit, ownership, lifecycle state) imply business events that should drive a counter / span attribute / log field. A schema change with no corresponding observability change is itself a gap; flag it as a Medium finding (`Schema change without instrumentation`) so the implementer wires a metric or span attribute alongside the column

For diffs touching only one of these surfaces (a new endpoint but no logging change, say), still read the existing config to know whether request-id / trace correlation, instrumentation, and SDKs are wired - a missing wire is the finding.

### Step 4 - Structured Logging (`tracing` crate)

Inspect logging config and any `tracing::*` callsite in the diff:

- [ ] **Production logger emits JSON** - `tracing_subscriber::fmt::layer().json()` (or `bunyan_formatter` for Bunyan-shaped output). No `println!` / `eprintln!` in production code paths
- [ ] **Correlation fields injected** in every log line: `trace_id`, `span_id`, `request_id`, `user_id` (when authenticated), `tenant_id`, plus business correlation IDs (`order_id`, `invoice_id`). Wire via:
  - `tower-http::request_id::SetRequestIdLayer` + `PropagateRequestIdLayer` for the request-id chain
  - `tower-http::trace::TraceLayer::new_for_http().make_span_with(...)` injects `request_id` and `method` / `uri` into the span
  - `#[tracing::instrument(skip_all, fields(order_id = %id))]` on service / handler functions for business correlation IDs
- [ ] **OpenTelemetry log correlation**: the `tracing-opentelemetry` bridge layer (`tracing_opentelemetry::layer().with_tracer(tracer)`) attaches `trace_id` / `span_id` to every event automatically when the OTel tracer is active. Plain `tracing` logs without the bridge layer cannot correlate to traces
- [ ] **Sensitive-field redaction**: a custom `tracing_subscriber::Layer` that drops `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key` keys; OR types implement `Debug` manually (or via `derivative` / `redact`) to override formatting and return a redacted form. `valuable::Valuable` for structured-field representations
- [ ] **No `tracing::info!(?user)` that serializes a domain model**: any `Debug` impl that prints sensitive columns leaks them. Always log specific fields: `tracing::info!(user_id = %u.id, tenant_id = %u.tenant_id, "event")`
- [ ] **User-identity fields emitted as structured key-values, not in the message string**: `tracing::info!(user_id = %user_id, "processing")`, never `tracing::info!("user={user_id} processing")` - a single redaction config can scrub structured fields; it cannot reliably scrub them out of a free-text message
- [ ] **Log levels used correctly**: `error!` for actionable failures, `warn!` for recoverable anomalies, `info!` for state transitions, `debug!` for verbose diagnostics, `trace!` for very fine-grained. Default `RUST_LOG=info` in prod (or per-crate filter: `RUST_LOG=info,sqlx=warn`)
- [ ] **No `println!` / `eprintln!`** in production code paths - flag for replacement with `tracing`; `println!` skips redaction, structured fields, span context, and correlation
- [ ] **No log spam in hot loops** - iterating large slices, scheduled tasks running every second, background workers at high TPS must not log per-iteration; sample or use `debug!`
- [ ] **Error logging includes the wrap chain**: `tracing::error!(error = ?e, "loading order")` - `?e` uses `Debug` which `anyhow::Error` and `thiserror`-generated errors render as the full chain; `%e` only renders the top-level `Display` and loses context

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

Inspect OpenTelemetry config and instrumentation wiring:

- [ ] **OpenTelemetry SDK initialized in `main.rs` BEFORE the Axum router is built**: `let tracer = opentelemetry_otlp::new_pipeline().tracing()...install_batch(...)?;` and the `tracing-opentelemetry` bridge registered in the subscriber happens before `Router::new()`. Late initialization means subsequent middleware / handlers may use the no-op tracer
- [ ] **OTLP exporter configured**: `opentelemetry_otlp::new_exporter().tonic()` (gRPC) or `.http()` pointed at the org's collector / backend; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` set per env
- [ ] **Resource attributes** populated: `service.name`, `service.version`, `deployment.environment`; sourced from build metadata / env vars via `Resource::new(vec![KeyValue::new("service.name", ...)])`
- [ ] **Sampling policy explicit**: `Sampler::ParentBased(Box::new(Sampler::TraceIdRatioBased(rate)))` with `rate` per env (e.g., `0.1` in prod, `1.0` in staging); not `AlwaysOn` in high-traffic prod
- [ ] **Axum auto-instrumentation**: `TraceLayer::new_for_http()` from `tower-http::trace` registered on the router; the `tracing-opentelemetry` bridge converts `tracing` spans to OTel spans. Span name uses the route template (avoid raw URI to prevent high cardinality)
- [ ] **sqlx instrumentation**: sqlx emits `tracing` spans for queries when the `tracing` feature is enabled; with the `tracing-opentelemetry` bridge they propagate to OTel automatically. Confirm the feature is on
- [ ] **HTTP client instrumentation**: `reqwest-tracing` middleware (or `reqwest-middleware` with a tracing layer) wraps the shared `reqwest::Client`; traceparent propagates outbound automatically. Bare `reqwest::Client` without the middleware does not propagate span context
- [ ] **Background task instrumentation**: trace context propagated across the spawn boundary - either via `Span::current()` captured before spawn and entered inside the task, or via OTel's W3C `traceparent` carrier serialized into the task payload and reconstructed on the consumer
- [ ] **Kafka / AMQP instrumentation**: `traceparent` extracted from message headers and consumer span links to the producer span; flag missing instrumentation - cross-process trace stitching breaks
- [ ] **Custom spans** for business operations: `#[tracing::instrument(skip_all, fields(order.id = %order_id))]` on service methods; no over-instrumentation (do not wrap a single sqlx query in a custom span - the SQL span already covers it)
- [ ] **Span attributes**: `tracing::Span::current().record("order.id", &order_id)` after the value is known; keep cardinality bounded
- [ ] **`record_error` / span error status on error paths**: `if let Err(e) = ... { tracing::error!(error = ?e); Span::current().set_status(opentelemetry::trace::Status::error("..."))}` (or use the `tracing-opentelemetry::OpenTelemetrySpanExt` helpers)
- [ ] **`tracer_provider.shutdown()` called on graceful shutdown** so in-flight spans flush; `global::shutdown_tracer_provider()` for the global provider

### Step 6 - Metrics (`metrics` crate / Prometheus exporter)

Inspect `metrics` macros and exporter setup:

- [ ] **`metrics-exporter-prometheus` installed** and `/metrics` endpoint exposed - typical pattern is to bind it on a separate admin port via `PrometheusBuilder::new().with_http_listener("0.0.0.0:9100".parse()?)`. Alternatively, OTel metrics with the Prometheus exporter via `opentelemetry-prometheus`
- [ ] **Default Tokio runtime metrics** scraped: `tokio_runtime_workers_count`, `tokio_runtime_active_tasks_count`, `tokio_runtime_busy_duration_total` - via `tokio-metrics` integration; confirm enabled at startup. Default Prometheus `process_*` metrics exposed via the exporter
- [ ] **HTTP server metrics**: histogram `http_request_duration_seconds` and counter `http_requests_total` with route / method / status labels - via `axum-prometheus` or a custom `tower::Layer`. Critical: route label must be the **template** (`/orders/:id`), not the actual path (`/orders/123`), or cardinality explodes
- [ ] **Custom business metrics** named under a consistent namespace (`acme_orders_placed_total`, `acme_payments_failed_total`); units explicit (`counter!` for counts, `histogram!` for durations, `gauge!` for instantaneous values). Suffix conventions (`_total`, `_seconds`, `_bytes`) followed
- [ ] **Tag (label) cardinality bounded**: labels do not include unbounded values (`user_id`, `order_id`, `request_id`) - causes metric-cardinality blow-up. Allowed label values are enums / known categories (`status`, `tenant_tier`, `region`)
- [ ] **`describe_*!` macros run at startup**: `metrics::describe_counter!("acme_orders_placed_total", "Number of orders placed")` registers the help text and unit; absence means metrics show up in Prometheus without metadata
- [ ] **Histogram buckets** chosen for the SLO: default buckets are seconds-scale; for sub-100ms paths add finer buckets via `PrometheusBuilder::set_buckets_for_metric(...)` or per-histogram configuration. Without explicit buckets, default exponential buckets often miss the relevant percentiles
- [ ] **Multi-instance aggregation**: when running multiple replicas, Prometheus scrapes each replica; ensure no per-replica metric is mistakenly aggregated as a sum (use `rate()` + `sum by(...)` discipline at query time, not in the SDK)

> **Greenfield exception (applies to Steps 7, 8, and 9).** When 3+ rows in the Step 3 Surface Map are `absent`, run Steps 7-9 at every depth regardless of the per-step diff-touch gate. On a greenfield service the *absence* of the surface is itself the finding the gate would otherwise hide - if the diff doesn't touch `console_subscriber` because `console_subscriber` doesn't exist yet, the default skip would silently let the gap go unflagged exactly when it most matters.

### Step 7 - tokio-console / Runtime Introspection

_Skipped at `quick` depth unless the diff touches `console_subscriber` registration or task instrumentation._

- [ ] **`console_subscriber` registered** for live task profiling: `console_subscriber::init()` in `main.rs`, gated behind a feature flag (`#[cfg(feature = "console")]`) or env var so it is not always-on in prod (it adds overhead and exposes a debug port)
- [ ] **Cargo feature `tokio_unstable`** enabled when `console-subscriber` is in use - it requires unstable Tokio APIs
- [ ] **Console binding**: `console_subscriber::ConsoleLayer::builder().server_addr(...)` bound to `127.0.0.1` or behind admin auth, never `0.0.0.0` on a public interface in prod
- [ ] **Task names** set on long-lived tasks: `tokio::task::Builder::new().name("order-processor").spawn(...)` so `tokio-console` shows useful names instead of anonymous task IDs
- [ ] **`#[tracing::instrument]` on async fns** so the call graph shows up in both `tracing` and `tokio-console` views
- [ ] **`console_subscriber` NOT exposed on a public port without auth in prod**: this is a security finding too (`task-rust-review-security`) - flag for delegation if the diff exposes it on a public bind without gating

### Step 8 - Background Tasks / Kafka / AMQP Observability

_Skipped at `quick` depth unless the diff touches background tasks or message brokers._

- [ ] **Trace context propagation across the spawn / dispatch boundary**: when a background task is enqueued inside an HTTP request, the worker span links back to the request span (via captured `Span::current()` for in-process or W3C `traceparent` in payload headers for out-of-process). Flag missing wiring
- [ ] **Per-task metrics**: latency histogram, retry counter, failure counter, queue-depth gauge
- [ ] **Logger context binding inside the task**: `task_id`, `task_type`, sanitized payload fields bound at task start via `#[tracing::instrument(fields(task_id = %task_id))]`; flushed at end
- [ ] **Outbound HTTP from tasks instrumented**: `reqwest::Client` used inside a task is wrapped via `reqwest-tracing` so the worker span chains to the downstream service span; flag tasks that make uninstrumented outbound calls because the downstream timing / errors stay invisible to traces
- [ ] **Scheduled / periodic task instrumentation**: each scheduled task emits a span; missed-execution alerting via stalled-task metric or queue-health endpoint
- [ ] **Kafka (`rdkafka`) consumer instrumentation**: extract `traceparent` from message headers via OTel propagator; consumer span links to producer span. Confirm wiring - `rdkafka` does not auto-instrument
- [ ] **AMQP (`lapin`) instrumentation**: same shape - extract trace context from delivery properties / headers and continue the span on the consumer side

### Step 9 - Lifecycle / Graceful Shutdown Observability

_Skipped at `quick` depth unless the diff touches lifecycle (graceful shutdown, signal handling) or `main.rs`. The Greenfield exception above also applies to this step._

- [ ] **Graceful shutdown via `tokio::signal`**: `tokio::signal::ctrl_c().await?` for SIGINT, `tokio::signal::unix::signal(SignalKind::terminate())` for SIGTERM. Combine via `tokio::select!` so either signal triggers shutdown
- [ ] **`axum::serve(...).with_graceful_shutdown(...)`**: pass an async closure that resolves on the shutdown signal so in-flight requests drain
- [ ] **Bounded shutdown timeout**: a `tokio::time::timeout(Duration::from_secs(30), shutdown_future).await` wrapping the drain so shutdown does not hang indefinitely
- [ ] **OTel TracerProvider shutdown**: `global::shutdown_tracer_provider()` flushes buffered spans before process exit; absent shutdown drops in-flight telemetry
- [ ] **Background-task `CancellationToken` cancelled** on shutdown; worker tasks join via `JoinSet::shutdown().await` for clean drain
- [ ] **Database pool drained / no-op on shutdown**: sqlx pool is dropped at the end of `main`; `pool.close().await` for explicit drain when in-flight queries should complete first
- [ ] **Bootstrap span** (optional but useful for cold-start visibility): `let _enter = tracing::info_span!("app.bootstrap").entered();` around the heavy startup work

### Step 10 - Error Tracking (Sentry SDK)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/API-key handling._

Inspect SDK config:

- [ ] **SDK installed and initialized**: `let _guard = sentry::init((dsn, sentry::ClientOptions { ... }));` in `main.rs`; `sentry-tower::NewSentryLayer` and `sentry-tower::SentryHttpLayer` registered on the Axum router so panics and reported errors flow to Sentry
- [ ] **DSN / API key** in env var or Vault, not committed
- [ ] **Release / environment tags** populated from build metadata (`release: env!("CARGO_PKG_VERSION").into()`, `environment: env.into()`)
- [ ] **PII scrubbing on**: `send_default_pii: false` (default but flag if explicitly `true`); `before_send` strips known sensitive keys; allowlist of breadcrumb fields documented
- [ ] **`sentry-tracing` layer** in the `tracing_subscriber` registry so `tracing::error!` events become Sentry breadcrumbs / events automatically
- [ ] **OpenTelemetry / trace correlation forwarded**: error event includes `trace_id` and `user_id` so incidents link back to traces / users; the `sentry-tracing` integration extracts trace context when the OTel bridge is active
- [ ] **Sample rate explicit**: `traces_sample_rate`, `profiles_sample_rate` per env; not `1.0` in prod for tracing
- [ ] **Ignored errors documented**: domain errors that should not page (e.g., `AppError::NotFound`, `AppError::Validation`) filtered via `before_send`; each ignore has a comment
- [ ] **Panic capture for spawned tasks**: every long-lived `tokio::spawn` includes panic capture (e.g., wrapping in a closure that calls `sentry::integrations::panic::*` or instrumenting via `JoinSet` whose `JoinError::is_panic()` triggers Sentry capture)

### Step 11 - Health Checks and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one Prometheus / OTel SLI (HTTP request rate filtered to the journey URI, success rate, p95 latency)
- [ ] **Three-way health endpoint split** (when running on Kubernetes / any orchestrator with liveness + readiness probes):
  - **`/livez` (liveness, kubelet restart gate):** bare `async fn livez() -> StatusCode { StatusCode::OK }` - **no DB, Redis, Kafka, or external API checks**. Liveness only answers "is the process alive enough to respond." Wiring DB checks here causes a transient DB blip to restart-loop the pod, multiplying the outage
  - **`/readyz` (readiness, load-balancer gate):** own-pod-only checks - sqlx `pool.acquire().await?` (or a quick `SELECT 1`), Redis ping, in-process queue connectivity. **Must NOT include third-party API pings** (Stripe, SendGrid, downstream services). A Stripe blip would otherwise pull every replica out of the LB simultaneously, cascading the upstream outage to your service. Use a circuit breaker (e.g., `failsafe-rs`) on the request path for third-party calls instead
  - **`/internal/deps` or `/debug/health`:** dashboards / on-call only, NOT wired to any K8s probe. Returns rich JSON per dependency (third-party API status, queue lag, replica info). Verify the diff doesn't accidentally point a `readinessProbe.httpGet.path` at this endpoint
- [ ] Readiness/liveness endpoints return JSON with per-dependency status, not just `200 OK` - so probes can distinguish DB-down from queue-stuck (within their respective scopes above)
- [ ] SLO targets documented in code (`src/slo/*.rs` or module README) - not a free-floating Confluence page


### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Rust / Axum (or accepted from parent dispatcher); data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent)
- [ ] Instrumentation surfaces (logging config, OTel wiring, settings, dependencies, changed call sites) read directly before applying checklists
- [ ] Structured logging assessed: JSON `tracing_subscriber` formatter, trace / request-id correlation, sensitive-field redaction, log level discipline, no `println!` / `eprintln!` in prod paths
- [ ] OpenTelemetry SDK and auto-instrumentation reviewed: SDK initialized before Axum router, TraceLayer / sqlx tracing / reqwest-tracing / Kafka instrumentation enabled, sampling explicit, resource attributes populated, `shutdown_tracer_provider` called
- [ ] Metrics assessed: `metrics-exporter-prometheus` exposed (or OTel metrics), default runtime + HTTP server metrics scraped, custom metric naming under namespace, label cardinality bounded, route label is template not actual path, `describe_*!` macros run
- [ ] tokio-console / `console_subscriber` presence + non-prod / auth gating assessed; task names on long-lived spawns
- [ ] Background-task / Kafka / AMQP observability assessed: trace propagation across dispatch boundary, queue / per-task metrics, scheduled task spans, traceparent extraction on consumers
- [ ] Lifecycle / graceful shutdown assessed: `tokio::signal`, `with_graceful_shutdown`, bounded shutdown timeout, `shutdown_tracer_provider`, `CancellationToken` cancellation, pool drain
- [ ] Error tracker integration assessed: SDK wired with `sentry-tower` + `sentry-tracing`, DSN externalized, PII scrubbed, OTel correlation forwarded, sample rate explicit, panic capture for spawned tasks
- [ ] Findings name a Rust / `tracing` / OTel / `metrics` idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/messaging/lifecycle/error-tracker/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Rust Observability Review Summary

**Stack Detected:** Rust <version> / Axum <version>
**Runtime:** Tokio <version>
**Data Access:** sqlx <version> | diesel <version> | mixed
**Messaging:** Tokio queue | AMQP (lapin) | Kafka (rdkafka) | none
**Logging:** tracing (JSON via tracing-subscriber) | tracing (text) | log (legacy) | absent
**Metrics:** metrics-exporter-prometheus | OTel metrics (Prometheus exporter) | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
**tokio-console:** enabled (admin / loopback) | enabled (non-prod only) | enabled (public, prod) [security finding] | absent
**Messaging instrumentation:** trace context propagated | partial | absent | n/a (no messaging)
**Error Tracker:** Sentry (sentry-tower + sentry-tracing) | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

_The 6-row verdict from Step 3, repeated here as the top-line read for the reviewer. Each row is `wired | partial | absent` plus a one-line citation._

| Surface                       | Verdict                        | Evidence                                   |
| ----------------------------- | ------------------------------ | ------------------------------------------ |
| tracing logging               | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK             | wired / partial / absent       | [...]                                      |
| Metrics exporter              | wired / partial / absent       | [...]                                      |
| tokio-console                 | wired / partial / absent       | [...]                                      |
| Messaging instrumentation     | wired / partial / absent / n/a | [...]                                      |
| Error tracker                 | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ of the rows above are `absent` - it tells the reader the review is scaffolding, not auditing, and changes how they prioritize. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Rust idiom: missing tracing redaction for `Authorization` header, unbounded label cardinality on `user_id`, OTel SDK initialized after the Axum router (TraceLayer captures the no-op tracer), missing reqwest-tracing on outbound client, route label is actual path not template, `tokio-console` bound to public interface, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Rust / `tracing` / OTel / `metrics` change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Logging / Tracing / Metrics / tokio-console / Messaging / Error Tracker / Lifecycle) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Move OTel SDK init to a dedicated `src/observability/otel.rs` initialized before any router setup", "Add `reqwest-tracing` middleware to the shared `reqwest::Client`", "Switch from per-handler `metrics::counter!` to module-level `describe_counter!` at startup", "Bind `console_subscriber` to a separate admin port instead of the default", "Add `sentry-tracing` layer to the subscriber so `tracing::error!` becomes Sentry events"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `#[tracing::instrument(skip_all, fields(order_id = %id))]` to `OrderService::place`"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/metrics` endpoint to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Rust / `tracing` / OTel / `metrics` idiom ("add metrics" vs "register `counter!(\"acme_orders_placed_total\")` and `describe_counter!(...)` at module level with bounded labels")
- Recommending generic observability advice when a Rust SDK or auto-instrumentation exists (say "register `tower-http::trace::TraceLayer::new_for_http()`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high label cardinality (`user_id`, `order_id`) as acceptable - metric series cost compounds; require enum / category labels
- Approving template-string logging (`tracing::info!("processing order={}", order_id)`) over structured form (`tracing::info!(order_id = %order_id, "processing")`) - the rendered string locks the formatter and prevents log-aggregation tools from parsing fields
- Suggesting `println!` / `eprintln!` as logging - flag for replacement with `tracing`
- Approving `metrics::counter!` registration without `describe_counter!` - metrics show up in Prometheus without help text or units
- Approving OTel `Sampler::AlwaysOn` in prod for high-traffic services - cost and storage compound
- Approving OTel SDK initialization AFTER `Router::new()` and `TraceLayer` registration - middleware captures the tracer at registration time and may capture the no-op tracer
- Approving `console_subscriber` exposed on a public bind in prod without auth - security and observability finding (delegate to security review for full treatment)
- Prescribing the OTLP endpoint URL or the Sentry DSN value - say "sourced from env / Vault" and stop; concrete URLs are infra config, not source-code review
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
- Approving plain `tracing` logs without the `tracing-opentelemetry` bridge layer when OTel is wired - log-trace correlation requires the bridge so the active OTel span context attaches to the log record
