---
name: task-rust-review-observability
description: Rust observability review - tracing JSON, tracing-opentelemetry/OTLP, metrics-exporter-prometheus, span propagation, tokio-console, Sentry.
agent: rust-observability-engineer
metadata:
  category: backend
  tags: [rust, axum, observability, tracing, opentelemetry, prometheus, tokio-console, sentry, workflow]
  type: workflow
user-invocable: true
---

# Rust Observability Review

Rust-aware review naming `tracing` + `tracing-subscriber` (JSON), the OpenTelemetry SDK bridged through `tracing-opentelemetry` and exported by `opentelemetry-otlp`, `tower-http`'s `TraceLayer`, `reqwest-tracing`, `metrics` + `metrics-exporter-prometheus` (or the `prometheus` crate), span propagation across `tokio::spawn` and broker hops, `tokio-console`, graceful shutdown with telemetry flush, and `sentry` (sentry-rust). Library-level scope; infra (Datadog dashboards, Grafana alert rules, log forwarder config) stays out.

Stack-specific delegate of `task-code-review-observability` for Rust.

## When to Use

- Rust/Axum PR for observability regressions or instrumentation gaps
- Pre-release check for a new service or major feature
- Post-incident review when diagnosis was slow
- Adopting `tracing` / OpenTelemetry / Prometheus; auditing trace propagation across `tokio::spawn`, Kafka or AMQP

**Not for:** general review (`task-rust-review`), perf with known bottleneck (`task-rust-review-perf`), infra observability.

**Version floors.** The checks assume `opentelemetry` / `opentelemetry_sdk` / `opentelemetry-otlp` 0.28+ (`SdkTracerProvider`, `Resource::builder()`, `SpanExporter::builder()`; `new_pipeline()` and `global::shutdown_tracer_provider()` are gone), `metrics` 0.22+ (`counter!(...)` returns a handle; `increment_counter!` before), and Axum 0.8 route syntax (`/orders/{id}`; `/orders/:id` on 0.7). Read the resolved versions in `Cargo.lock` before citing a symbol; below a floor, name the older form the pinned release has.

## Depth

| Depth      | What runs                                                |
| ---------- | -------------------------------------------------------- |
| `standard` | All steps                                                |
| `deep`     | All steps + SLI/SLO suggestions (`### SLI / SLO` under Recommendations) |

Default: `standard`. Request deep by appending `deep` to the invocation (e.g. `/task-rust-review-observability <branch> deep`).

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rust-review-observability` | Current branch vs base; fails fast on trunk |
| `/task-rust-review-observability <branch>` | `<branch>` vs base (3-dot) |
| `/task-rust-review-observability pr-<N>` | PR head fetched into local branch (user runs fetch) |

**Subagent runs** (e.g. spawned by `task-rust-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, depth, the pre-confirmed stack, the data-access mix, and messaging. Step 3 is skipped whole, SHA capture included - never re-run its git reads. Steps 13 and 14 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier (High -> `[Must]`, Medium / Low -> `[Recommend]`), a finding whose cited line the diff did not add carries `_(pre-existing)_` and no other annotation (the parent's verify adds `newly reachable via`) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 15 returns the entire Output Format (the Step 4 gate's short report when it fired) - Summary, Surface Map, Findings, Out of Lens, Recommendations (with the deep `### SLI / SLO` block when the parent's depth is `deep`), Next Steps - instead of writing, and prints no confirmation. Derive `Messaging` per Step 2 when the parent did not send it.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its whole Rules section and its unverifiable-change disclosure, as that skill specifies.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. A subagent run skips detection: it takes what the parent pre-confirmed (stack, versions, data-access mix, messaging) as passed and reads the manifests below only for a slot the parent left empty. If not Rust, stop and recommend `/task-code-review-observability`.

Versions come from the manifests - the Rust version from `rust-toolchain.toml`'s `channel`, else `Cargo.toml`'s `rust-version`; the HTTP framework, sqlx / diesel and observability crates from their resolved entries in `Cargo.lock` (a `Cargo.toml` requirement such as `0.8` is a range, not a version) - and override any version a `## Tech Stack` line declared (this step's one departure from `stack-detect`'s instruction-file precedence); in a Cargo workspace the member crate under review decides, its `Cargo.toml` read in place of the detected primary stack, versions from the workspace-root `Cargo.lock`. The `Stack` slot is `stack-detect`'s rendering with those versions added (`Rust 1.94.0 / Axum 0.8.9`, `Rust 1.94.0 (no framework detected)`), and the writer's `stack` is `rust-<framework>` lowercased (`rust-axum`, `rust-actix-web`; `rust` when there is none). The checks below name Axum / `tower` constructs; on another framework apply each to that framework's equivalent and skip one that has none. `Data Access` is the data-access crate the crate under review depends on directly - `sqlx`, `diesel` (`diesel-async` included), `SeaORM` (`sea-orm`) or `tokio-postgres` - with its `Cargo.lock` version; one present only transitively (the `sqlx` beneath SeaORM, the `tokio-postgres` beneath `diesel-async`) does not count, and two direct ones are `mixed`, both named with versions. `Messaging` lists every mechanism present in any workspace member (the reviewed crate may enqueue what another member claims), in this order, joined with ` + `: `Postgres job queue` when a worker claims rows from a jobs table (no crate marks it - read the claim query, or the migration creating the table; a claim missing `FOR UPDATE SKIP LOCKED` still counts; an outbox relay's claim is not one); `Kafka` when `rdkafka` or another Kafka client is a direct dependency; `AMQP` for `lapin`; `Tokio queue` when worker tasks drain a `tokio::sync::mpsc` channel of background jobs; `none` when there is none.

### Step 3 - Resolve Diff and Round

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check` with `report_type: review-observability`. Any fail-fast: surface verbatim and stop. On success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs) and resolve the round below; only then read diff, log and `git diff -M --name-status <base_ref>...<head_ref>`, once, for reuse. The writer's `branch` is the handle's `head_short_name`.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha` and the invocation asks for nothing more (no `deep` where the prior was `standard`), print `No new commits on <head_short_name> since prior observability review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite (`<sha_short>` is the first 7 characters of `head_sha`). On a genuine round 2+, re-review the full range; Step 14 reconciles the prior findings.

### Step 4 - Read the Instrumentation Surface

**No-surface gate.** A diff that touches only docs, tests or comments has nothing for this lens to read: skip the rest of Steps 4-13. The whole report is then a Summary of `Stack` and `Overall: Adequate - diff contains no instrumentation surface` - plus, on a standalone run, `Round` on round 2+ and `Findings verified: 0 confirmed, 0 reattributed, 0 unverified, 0 dropped` - and `## Findings` holding `Diff contains no instrumentation surface.` (followed, on a standalone round 2+, by the carried rows) A subagent run returns that; a standalone run still reconciles on round 2+ (Step 14: carried rows publish as usual, with their Next Steps rows, and `Overall` reads `Gaps Found - <counts>`) and writes the report (Step 15).

**Most important output:** a one-line verdict per surface - logging, OTel, Prometheus, runtime introspection, one instrumentation row per `Messaging` value, graceful shutdown, error tracker - of the form `wired | partial | absent | n/a`. A missing wire is itself the finding.

The verdict answers **how much of the surface exists**, not whether it is correct: `wired` = every piece is present (misconfigured pieces stay `wired`, with the defect in the Evidence cell and a finding); `partial` = the mechanism is installed but does not cover everything it should (an OTel layer with no inbound or client propagation, a `TraceLayer` in a registry with no OTel layer, a shutdown path that never calls `provider.shutdown()`, a JSON logger whose `#[instrument]` records raw arguments, `console-subscriber` without `tokio_unstable`); `absent` = nothing is wired (ad hoc log lines on a failure path are not a mechanism). A correctly-built OTel SDK that instruments no dependency is `partial`, not `wired`.

**Grouping rule.** When a whole surface is `absent`, produce a **single finding** for that surface listing missing pieces grouped by file/symbol - not one finding per sub-bullet. When the surface's gaps straddle impact tiers, keep the grouping and file at the strongest tier; split only when a sub-gap needs a materially different fix - a credential recorded by a bare `#[instrument]` is not fixed by wiring a JSON layer, so it is its own finding even though both sit on the logging surface. Per-callsite findings only when the surface exists and a specific callsite misuses it.

**Severity, and the diff-vs-repo scope rule.** A surface the diff touches - or that the diff makes load-bearing, such as client propagation missing on an unchanged `reqwest` client once this PR installs the OTel layer that would have used it - is scored on consequence, High when it leaves a failure undiagnosable. A surface the diff never approaches and never activates is **not** a merge blocker on this PR: report it at Medium or Low as standing debt; Step 13 annotates it `_(pre-existing)_`. Absent-surface findings are all in-scope only when the diff adds the service's entrypoint (`src/main.rs` or a `src/bin/*.rs` is `A` in the name-status); a Greenfield `Overall` on an existing service keeps the diff-vs-repo scope rule and the three-finding cap. Even then, do not tier them all High. A review that emits one `[Must]` per surface reads as none. Calibrate by what gates first production traffic: **High** for anything that leaks data, hides an active failure, or cannot be retrofitted without a redeploy of every caller (secrets in logs, no error signal, no request metrics, no propagator); **Medium** for surfaces that make diagnosis slower but are additive later (tokio-console, queue-depth gauges, custom spans); **Low** for polish. Say in the Summary that the service ships without them and what the first-week follow-up is - a greenfield review is a sequencing document, not a merge gate.

**Defects outside the diff or the lens.** A defect on a line the diff did not add: in this lens and made newly reachable or load-bearing by the diff -> a finding (Step 13 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 13 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential (highest tier first; within a tier a defect an incident record or measurement in the repo names before any other, then a file the diff touches before one it does not, then path and line order), counting only findings this round publishes for the first time - a grouped absent-surface finding counts once - the rest one line each under `## Out of Lens`; owned by another lens, or by none (a missing timeout, an auth gap, a handler panic with no `CatchPanicLayer`; a compile break or logic error is `task-rust-review`'s) -> `## Out of Lens` with `file:line` and the owner.

Open files that configure observability so findings cite real lines, each file read at `head_ref` (`git show <head_ref>:<path>`, on subagent runs too) - the working tree may be on another branch:

- `src/main.rs` / `src/telemetry.rs` / `src/observability/*.rs` - subscriber registry and layer order, OTel provider, exporter, propagator
- Config struct - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, `RUST_LOG`, Sentry DSN, metrics port
- `Cargo.toml` / `Cargo.lock` - the pinned `opentelemetry*`, `tracing-opentelemetry`, `metrics*`, `sentry`, `rdkafka` / `lapin` versions against the floors above, and features (`tracing-subscriber`'s `json` / `env-filter`, tokio's `tracing`)
- `.cargo/config.toml` - `--cfg tokio_unstable` rustflags
- Every changed file calling `tracing::*` or `#[instrument]`, recording `metrics::*`, adding a `tower` layer, spawning tasks

### Step 5 - Structured Logging (tracing)

- [ ] Production subscriber emits JSON: `tracing_subscriber::fmt::layer().json()` (crate feature `json`) in the `registry()`, `EnvFilter` from `RUST_LOG` defaulting to `info` with noisy crates capped (`sqlx=warn,hyper=warn`). No `println!` / `eprintln!` / `dbg!` on prod paths
- [ ] **Correlation fields** in every line: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs (`order_id`). Recorded on the request span (`TraceLayer::make_span_with`, `request_id` from `tower_http::request_id::SetRequestIdLayer`) and printed per event because the JSON layer includes the current span's fields
- [ ] **OTel correlation:** `tracing-opentelemetry` exports spans; it puts no `trace_id` on the stdout JSON line. Declare `trace_id = tracing::field::Empty` in `make_span_with` and record it from `OpenTelemetrySpanExt::context()` once the span exists, or format it in a custom `FormatEvent`. `opentelemetry-appender-tracing` (`OpenTelemetryTracingBridge`) is an OTLP-logs bridge - it adds nothing to stdout lines, so stdout-shipped logs still need the field
- [ ] **Redaction lives in types:** credentials as `secrecy::SecretString` (its `Debug` redacts), hand-written `Debug` on DTOs carrying `password`, `token`, `authorization`, `cookie`, `credit_card`, `ssn`, `api_key`; `SetSensitiveRequestHeadersLayer` marks `Authorization` / `Cookie` so `TraceLayer` never prints them (`DefaultMakeSpan::include_headers(true)` otherwise records them)
- [ ] **`#[instrument]` records every argument via `Debug`.** Use `skip_all` plus explicit `fields(...)`; a bare `#[instrument]` on `login(req: LoginRequest)` logs the password, and on a handler taking `State<AppState>` dumps the state
- [ ] **No `info!(?user, "loaded user")` dumping a sqlx `FromRow` struct** - every column, PII included, reaches the log. Log specific fields
- [ ] **Structured fields, not message strings.** `info!(order_id = %id, "order placed")`, never `info!("order placed {id}")` - an interpolated value is not a queryable field and no type-level redaction reaches it
- [ ] **Log levels:** `error!` for actionable failures, `warn!` for recoverable, `info!` for state transitions, `debug!` for verbose
- [ ] **No log spam in hot loops** - sample or use `debug!`
- [ ] **Errors as a field.** `error!(error = ?e, "loading order")`, never `error!("{e}")` - on `anyhow::Error`, `?` renders the context chain and `%` only the outermost context
- [ ] **Writer guards held.** `tracing_appender::non_blocking` returns a `WorkerGuard` bound in `main` (`let (writer, _guard) = ...`); `let (writer, _) = ...` drops it at once and buffered lines are lost on exit

### Step 6 - OpenTelemetry SDK and Instrumentation

- [ ] **Subscriber installed first in `main`**, before the pool, router and spawned tasks - events and spans recorded before `init()` are dropped. The OTel layer takes its tracer from the concrete provider (`provider.tracer("svc")`), and `global::set_tracer_provider(provider.clone())` runs before any `global::tracer(...)` call: a tracer obtained from the global before the provider is set stays a no-op. Building the `Router` before `init()` loses nothing on its own - request spans are created per request
- [ ] **Provider handle reaches shutdown** - the `SdkTracerProvider` is kept in `main` and `provider.shutdown()` runs after the server drains (Step 10); without it the batch processor's buffered spans die with the process
- [ ] **OTLP exporter:** `opentelemetry_otlp::SpanExporter::builder().with_tonic()` (or `.with_http()`) `.build()` behind `with_batch_exporter`, never `with_simple_exporter` in prod (exports on the thread that ends the span); `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Resource attributes:** `service.name`, `service.version` (`env!("CARGO_PKG_VERSION")`), `deployment.environment.name` via `Resource::builder()`
- [ ] **Sampling explicit:** `Sampler::ParentBased(Box::new(Sampler::TraceIdRatioBased(rate)))`; not `AlwaysOn` in high-traffic prod
- [ ] **Propagator set:** `global::set_text_map_propagator(TraceContextPropagator::new())` - the default global propagator is a no-op, so every inject and extract silently carries nothing
- [ ] **Axum instrumentation:** `TraceLayer::new_for_http()` with a `make_span_with` that names the span from `MatchedPath` (`otel.name = "GET /orders/{id}"`, `otel.kind = "server"`) - the default span records the raw URI. Inbound `traceparent` extracted and set as parent (`span.set_parent(cx)`, or `axum-tracing-opentelemetry`'s `OtelAxumLayer`); `TraceLayer` alone starts a fresh trace per request
- [ ] **sqlx:** emits per-statement log events (`log_statements`, `log_slow_statements` on `PgConnectOptions`), no spans; DB spans come from `#[instrument(skip_all, fields(otel.kind = "client"))]` on repository functions
- [ ] **HTTP client:** one shared `reqwest_middleware::ClientWithMiddleware` with `reqwest_tracing::TracingMiddleware`, its `opentelemetry_0_xx` feature matching the pinned `opentelemetry` - without that feature the client opens spans but injects no `traceparent`
- [ ] **Spawned work:** `tokio::spawn(fut.in_current_span())` or `.instrument(span)` (`tracing::Instrument`); a bare `tokio::spawn` starts with no parent span, so its events and child spans detach from the request trace. `spawn_blocking` closures run inside a captured span (`span.in_scope(...)`). Never hold `span.enter()`'s guard across `.await` - the span stays entered while the task is parked and other tasks' events land in it
- [ ] **Custom spans** for business operations: `#[instrument(skip_all, fields(order_id = %cmd.order_id))]` on service functions. No span per single query on top of the repository span
- [ ] **Span fields** with bounded cardinality where they become attributes used for grouping
- [ ] **Error status recorded** on error paths: `#[instrument(err)]` or an `error!` event inside the span, which `tracing-opentelemetry` maps to error status; or `otel.status_code` recorded explicitly

### Step 7 - Prometheus Metrics

- [ ] **Recorder installed once at startup**, before the first macro call - `metrics` macros record into a no-op until `install()` / `install_recorder()` runs. `/metrics` served by `PrometheusBuilder::new().with_http_listener(addr).install()` on an admin port, or `install_recorder()` plus a route rendering `handle.render()`; or a `prometheus::Registry` + `TextEncoder`; or OTel metrics with a Prometheus exporter
- [ ] **Process and runtime gauges** exported - Rust exports none by default: `process_*` (the `prometheus` crate's `process` feature, or `metrics-process`) and Tokio's `num_alive_tasks` / `global_queue_depth` from `Handle::current().metrics()` (or `tokio-metrics`). The alive-task count is the task-leak signal
- [ ] **HTTP server metrics:** a duration histogram + request counter with route / method / status (`axum-prometheus`, or a middleware reading `MatchedPath`). **Route label must be the template** (`/orders/{id}`), never `req.uri().path()` (`/orders/123`) - cardinality explodes otherwise; requests with no `MatchedPath` (404s) share one fixed label
- [ ] **Custom business metrics** under consistent namespace (`acme_orders_placed_total`); suffix conventions (`_total`, `_seconds`, `_bytes`)
- [ ] **Bounded label cardinality** - no `user_id`, `order_id`, `request_id` as labels; only enums / known categories
- [ ] **Static metric names** - `counter!("acme_orders_placed_total")`, never `counter!(format!("orders_{kind}_total"))`; with the `prometheus` crate, register once at startup (a `LazyLock` or a registry in state), never per request (`AlreadyReg`)
- [ ] **`describe_counter!` / `describe_histogram!`** at startup with help text and units
- [ ] **Histogram buckets set** - `metrics-exporter-prometheus` renders a histogram with no configured buckets as a summary, whose client-side quantiles cannot be aggregated across replicas. `set_buckets` / `set_buckets_for_metric(Matcher::Full(...), ...)`, finer than the defaults for sub-100ms paths

### Step 8 - Runtime Introspection (tokio-console, profiling)

- [ ] **`console-subscriber` composed as a layer** (`console_subscriber::spawn()` added to the registry); `console_subscriber::init()` installs its own global subscriber and collides with the app's
- [ ] **`--cfg tokio_unstable`** in `RUSTFLAGS` or `.cargo/config.toml`, plus tokio's `tracing` feature - without both the console lists no tasks and the surface is `partial`
- [ ] **Gated and bound privately** - behind a cargo feature or env flag, on loopback (default `127.0.0.1:6669`, `TOKIO_CONSOLE_BIND`) or an admin network; a public bind in prod is a security finding - route it to `## Out of Lens`
- [ ] **Long-lived tasks named** (`tokio::task::Builder::new().name(...)`, `tokio_unstable`) so console and task dumps identify them
- [ ] **CPU / heap profiling reachable** when the service needs it - a `pprof`-crate flamegraph endpoint, jemalloc heap profiling (`tikv-jemallocator` + `jemalloc_pprof`) - on the admin port only

### Step 9 - Kafka / AMQP / Background Jobs

Skip when `Messaging` is `none`: the Surface Map gets one `Messaging instrumentation | n/a` row and the Summary no broker line. Apply the column of each `Messaging` value; a row with no equivalent is dropped rather than reported as a gap. For a Kafka or AMQP client other than `rdkafka` / `lapin`, apply each row's intent through that client's own API and cite it.

| Check | Kafka (rdkafka) | AMQP (lapin) | Tokio queue | Postgres job queue |
| ----- | --------------- | ------------ | ----------- | ------------------ |
| Trace propagation across the dispatch boundary | Producer injects the propagator's carrier into `OwnedHeaders`; consumer extracts from `msg.headers()` and calls `set_parent` on a per-record `otel.kind = "consumer"` span. Absent headers on the producer side is the more common half to miss | Same through `BasicProperties::with_headers` / `delivery.properties.headers()` | The job carries the enqueuing `Span` (or its OTel `Context`); the worker instruments the job with a span that `follows_from` it | The enqueue writes the propagator's carrier into a column on the job row (a `trace_context` jsonb) inside the enqueue transaction; the worker extracts it and calls `set_parent` on a per-job span. Without the column every job starts a fresh trace |
| Queue depth | Consumer lag polled into a per-topic/partition gauge - the `statistics.interval.ms` stats callback (`consumer_lag`) or `fetch_watermarks` minus the committed offset | Passive `queue_declare` polled into gauges from `message_count()` / `consumer_count()` | `max_capacity() - capacity()` on the `Sender` as a gauge | Gauges of runnable `queued` rows and of the oldest one's age (`now() - min(run_at)`), polled once per process on an interval, never per claim |
| Per-message / per-job metrics | latency histogram, retry counter, failure counter, labelled by `topic` and outcome - never by key or record id | same, labelled by `queue` and outcome | same, labelled by job type and outcome | same, labelled by `kind` and outcome (`done`, retried, `dead`); a gauge of `dead` rows feeds the dead-letter alert |
| Handler span fields | `topic`, `partition`, `offset`, and the key when it is a bounded identifier - without the offset a poison record cannot be located | `queue`, `routing_key`, `delivery_tag`, `message_id` | `job_id`, `job_type` | `job_id`, `kind`, `attempts` - without `attempts` a retry storm reads as fresh traffic |
| Outbound HTTP from the worker | `reqwest-tracing` on the shared client | same | same | same |
| Scheduled work | n/a unless a scheduler exists | n/a unless a scheduler exists | each `interval` tick runs in its own span; a last-success timestamp gauge feeds missed-execution alerting | each period's `dedupe_key` job is instrumented like any other `kind`; a last-success timestamp gauge per periodic `kind` feeds missed-execution alerting |

### Step 10 - Graceful Shutdown

- [ ] **Signal handling:** a `shutdown_signal()` awaiting `tokio::signal::ctrl_c()` and `signal::unix::signal(SignalKind::terminate())` under `tokio::select!`, passed to `axum::serve(listener, app).with_graceful_shutdown(...)`. Without SIGTERM the pod is SIGKILLed at the end of its grace period and nothing below runs
- [ ] **Bounded drain** - `with_graceful_shutdown` waits for every open connection with no limit; once the signal fires the serve future races a deadline (e.g. 30s), so one stuck connection cannot consume the grace period and skip the flush
- [ ] **Telemetry flushed after the drain:** `provider.shutdown()` on the tracer provider (and the meter / logger providers when OTLP metrics or logs are wired); the `sentry::init` guard and any `WorkerGuard` drop at the end of `main`. No `std::process::exit` on that path - it runs no destructors, so no guard flushes
- [ ] **Workers drained:** `CancellationToken` cancelled, `JoinSet` / `TaskTracker` joined inside the deadline. Kafka: `producer.flush(timeout)` before exit (queued records are otherwise lost) and final offsets committed synchronously (`commit_consumer_state(CommitMode::Sync)`) under `enable.auto.commit=false`; AMQP: in-flight deliveries acked or nacked, then the channel and connection closed; Postgres job queue: workers stop claiming and settle the job in hand before the pool closes
- [ ] **DB pool closed** on shutdown: `pool.close().await` after the server and workers stop

### Step 11 - Error Tracking (Sentry)

- [ ] **SDK initialized and the guard held:** `let _guard = sentry::init((dsn, ClientOptions { .. }))` at the top of a sync `main`, before the Tokio runtime is built, so runtime threads inherit the hub; `let _ = sentry::init(...)` drops the guard and disables the client immediately
- [ ] **Errors reach Sentry, not only panics.** `sentry-tower`'s `NewSentryLayer` + `SentryHttpLayer` on the router give a hub and request data per request; the default panic integration reports panics. An `AppError` mapped to 500 in `IntoResponse` sends Sentry nothing unless `sentry-tracing`'s layer is in the registry (ERROR events become Sentry events) or the 5xx arm calls `sentry::capture_error` / `capture_anyhow` (`anyhow` feature) before transforming the error; a service whose dominant failure mode is a failing dependency rather than a panic is otherwise silent in Sentry
- [ ] **DSN** from env / Vault, never committed
- [ ] **Release / environment** populated: `release: sentry::release_name!()`, `environment` from config
- [ ] **PII scrubbing:** `send_default_pii: false` kept; `before_send` strips sensitive keys
- [ ] **Trace correlation forwarded** - the request hub's scope carries `trace_id` and the user, so errors link to traces / users
- [ ] **Sample rate explicit:** `traces_sample_rate` (or `traces_sampler`) per env; not `1.0` in prod
- [ ] **Ignored errors documented:** domain errors (`AppError::NotFound`, `AppError::Validation`) filtered in `before_send` or logged at `WARN` / `INFO` so `sentry-tracing` keeps them as breadcrumbs (its default filter ignores `DEBUG` / `TRACE`), each filter commented
- [ ] **Spawned tasks bound to a hub** - `.bind_hub(Hub::new_from_top(Hub::current()))` (`sentry::SentryFutureExt`) on tasks outside the request, so their events carry scope

### Step 12 - Health and SLIs

The health-endpoint checks run at **all depths** whenever the diff touches health or probe endpoints, or adds a dependency an existing probe now covers - a probe regression is a per-PR finding. Only the SLI/SLO items are deep-gated.

At `deep`, emit `### SLI / SLO` under Recommendations: one row per critical journey naming the objective (quoted from the project's own docs when they state one, `none documented - proposed <value>` otherwise), the PromQL the SLI would be computed from, and what currently blocks it. The `Objective` cell carries the window and the error budget it implies when known (`99.9% / 30d (budget 43m)`).

- [ ] Critical journeys have at least one SLI (request rate, success rate, p95 latency)
- [ ] **Three distinct endpoints, not one `/health`** (single `/health` is a per-PR finding):
  - **`/livez`** - returns 200 unconditionally; no dependency pings (coupling makes a Postgres blip restart all replicas)
  - **`/readyz`** - own-pod-only checks (pool initialised, broker connection, draining flag); tight timeouts; no third-party pings (would pull replicas from the LB on an outage)
  - **`/internal/deps`** / **`/debug/health`** - JSON per-dependency status for dashboards; NOT for K8s probes. Verify manifest probes don't point here
- [ ] SLO targets documented in code (`src/slo.rs` or README)

### Step 13 - Verify Findings

Runs at every depth. Assign each draft finding its label first (High -> `[Must]`, Medium / Low -> `[Recommend]`), since `review-finding-verify` takes labelled findings and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - never re-derive one from the impact tier afterwards; a High finding tagged `[Recommend]` because it is pre-existing is correct output. Carry its `Annotation` column verbatim onto the heading (`_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`) and its tally into the Summary's `Findings verified` slot; the tally counts this round's drafts only, a carried finding among them only when this round re-drafted it. A finding on a file the name-status does not list gets `_(pre-existing)_`, written first, unless its annotations already have a group opening `pre-existing` or `unverified`. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report.

Subagent runs skip this step entirely (see Invocation).

### Step 14 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, label and `file:line` copied from the `#### <n>. [Label] file:line - <title>` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, `base_ref`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its output - the table, any note lines, the tally line - under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` with the body the prior report gave them, cited where reconcile places the smell now, under the impact heading they were last published under (this round's tier when re-drafted; the higher tier when the prior heading combined two), with the label and annotation groups they were last published with (`_(pre-existing)_` written first when the name-status does not list the file and no group opens `pre-existing` or `unverified`) plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 15 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `stack` per Step 2, `scope: +obs`, `depth` as resolved from the Depth table, `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; chat then carries the handle notes, the report body and the writer's confirmation line, in that order.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface, or when the invocation mode makes it inapplicable (subagent, `standard` depth, round 1).

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed (or accepted from parent); versions from `Cargo.lock` / toolchain file; data-access mix and messaging recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-observability` (or handle received); diff, log and name-status read once; `base_sha` / `head_sha` captured; round resolved from the handle; same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: no-surface gate applied to a docs / tests / comments-only diff; surfaces read directly; Surface Map has one verdict per surface and one row per `Messaging` value; grouping and diff-vs-repo scope rules applied before tiers; defects outside the diff or lens routed per the Step 4 rule
- [ ] Step 5: `tracing` - JSON layer, correlation (`trace_id` field for stdout-shipped logs; appender bridge only when logs ship over OTLP), type-level redaction, `#[instrument(skip_all)]`, errors as a field, guards held
- [ ] Step 6: OTel - subscriber first, provider handle reaches shutdown, propagator set, inbound / client / spawn / DB propagation, sampling and resource attrs explicit
- [ ] Step 7: Prometheus - recorder before first use, process + runtime gauges, HTTP metrics with `MatchedPath` label, namespace, bounded labels, buckets set
- [ ] Step 8: tokio-console - layered, `tokio_unstable`, gating and bind recorded; profiling access checked
- [ ] Step 9: messaging rows applied per `Messaging` value, or N/A
- [ ] Step 10: shutdown - signals, bounded drain, `provider.shutdown()`, guards dropped, workers and broker sequence, pool closed
- [ ] Step 11: error tracker - guard held, error paths captured, DSN externalized, PII, sample rate, task hubs
- [ ] Step 12: probe checks ran where the diff touches them; `deep` added `### SLI / SLO` with objective, PromQL, blocker
- [ ] Step 13 (standalone): findings labelled before verify; labels and annotations carried verbatim; tally in the Summary
- [ ] Step 14 (round 2+): prior report projected and reconciled with `head_sha` and `base_ref`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 15 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written. Either way: findings name a Rust / `tracing` / OTel / `metrics` idiom - not "add observability"; library-level scope respected; Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Overall` is `Greenfield` when 3+ Surface Map rows are `absent`, `Gaps Found` when `## Findings` publishes any finding (verified this round or carried), the tier counts including carried findings, `Adequate` otherwise. One `**<Broker> instrumentation:**` line per `Messaging` value, `**Postgres job queue instrumentation:**` included (`wired | partial | absent`); with `Messaging: none` the Summary has no broker line and the Surface Map one `n/a` row. `Logging` takes the value of the layer the production path constructs (a JSON layer behind an opt-in flag prod does not set reads as its fallback - `tracing (text)`). When the binaries the diff touches differ on a surface (api JSON, worker text), its Summary slot and Surface Map verdict take the weaker and the Evidence cell names each binary's state. `Runtime introspection` is `tokio-console (public, prod)` only with the Out of Lens security line present. Placement is by tier and the label by Step 13 (Step 14 for carried findings): a High finding de-escalated to `[Recommend]` stays under `### High Impact`. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0. Any field the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Each finding is its own numbered block** under its impact heading, headed `#### <n>. [Label] file:line - <short title> _(annotations)_` where the label and annotations come from Step 13 verbatim (tier-derived label on subagent runs, with `_(pre-existing)_` on a finding whose line the diff did not add; `_(carried from round <N>)_` on carried findings). Numbering continues across tiers. Within a tier, order by surface when more than two findings share one. Blank lines separate the field lines; consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

```markdown
## Rust Observability Review Summary

- **Stack:** Rust <version> / <framework> <version> | Rust <version> (no framework detected)
- **Data Access:** sqlx <version> | diesel <version> | SeaORM <version> | tokio-postgres <version> | mixed - <crate> <version> + <crate> <version>
- **Messaging:** Postgres job queue | Kafka | AMQP | Tokio queue | <several, joined by " + "> | none
- **Logging:** tracing (JSON) | tracing (text) | log / env_logger | absent
- **Metrics:** metrics-exporter-prometheus | prometheus crate | OTel metrics (Prometheus exporter) | absent
- **Tracing:** OpenTelemetry (OTLP) | tracing spans only (no exporter) | absent
- **Runtime introspection:** tokio-console (loopback / admin) | tokio-console (non-prod only) | tokio-console (public, prod) | absent
- **Graceful shutdown:** wired | partial | absent
- **<Broker> instrumentation:** wired | partial | absent     {one line per `Messaging` value; omit when Messaging is none}
- **Error Tracker:** Sentry | absent
- **Overall:** Adequate | Gaps Found - <N> High / <N> Medium / <N> Low | Greenfield - <N> High / <N> Medium / <N> Low     {`Adequate - diff contains no instrumentation surface` under the Step 4 gate}
- **Round:** <N>                                {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

[2-3 sentence assessment. On a Greenfield review: what ships without, and the first-week follow-up.]

## Surface Map

| Surface                    | Verdict                        | Evidence                                   |
| -------------------------- | ------------------------------ | ------------------------------------------ |
| tracing logging            | wired / partial / absent       | [file:line or "no subscriber init in repo"] |
| OpenTelemetry SDK          | wired / partial / absent       | [...]                                      |
| Prometheus metrics         | wired / partial / absent       | [...]                                      |
| Runtime introspection      | wired / partial / absent       | [...]                                      |
| <broker> instrumentation   | wired / partial / absent       | [one row per `Messaging` value; with Messaging none, a single `Messaging instrumentation` row reading `n/a`] |
| Graceful shutdown          | wired / partial / absent       | [...]                                      |
| Error tracker              | wired / partial / absent       | [...]                                      |

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

<note line>     {one paragraph per note line reconcile emitted; omit when none}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### High Impact

#### 1. [Label] file:line - <short title> _(annotations)_     {annotation groups only when Step 13, Step 14, or the subagent rule assigned any}

- **Location:** [file:line or config key]

- **Issue:** [name the idiom: bare `#[instrument]` recording a `LoginRequest`, unbounded label cardinality on `user_id`, `SdkTracerProvider` never shut down, no text-map propagator so `traceparent` is never injected, route label is `uri().path()` not `MatchedPath`]

- **Impact:** [diagnosability | alertability | cost | exposure | availability - pick the one that dominates; a probe that couples liveness to a shared dependency is availability, not diagnosability]

- **Fix:** [specific `tracing` / OTel / `metrics` / Sentry change with code]

#### 2. [Label] file:line - <short title>

[Same block]

### Medium Impact

[Same blocks, numbering continues]

### Low Impact

[Same blocks, numbering continues]

Omit empty sections. When every section is empty, write "No observability issues found." (the Step 4 gate writes its own sentence instead)

## Out of Lens

[Defects another lens or `task-rust-review` owns, each with `file:line` and the owner, and pre-existing in-lens defects beyond the three published, each with `file:line`. Omit when there are none.]

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
- Reporting gaps without naming the idiom ("add metrics" vs "`describe_counter!` `acme_orders_placed_total` at startup and record it via `counter!(...).increment(1)`")
- Reviewing infra (Datadog settings, Grafana panels, log forwarder, on-call) or prescribing an OTLP endpoint URL / Sentry DSN value - not in source code
- One finding per missing checkbox when a whole surface is absent
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
