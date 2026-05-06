---
name: task-python-review-observability
description: Python observability review for structlog / stdlib logging, OpenTelemetry Python SDK, opentelemetry-instrumentation-* (FastAPI / Django / SQLAlchemy / Celery / requests / httpx), Prometheus client, and error-tracker SDKs (Sentry / Honeybadger / Rollbar). Library-level focus, not infra. Use when reviewing a Python PR for observability gaps, before releasing a new service, or after an incident where Python diagnosis was slow. Stack-specific override of task-code-review-observability for Python.
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, observability, logging, metrics, tracing, opentelemetry, structlog, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Python Observability Review

## Purpose

Python-aware observability review that names structlog / stdlib `logging` JSON handlers, OpenTelemetry Python SDK, the `opentelemetry-instrumentation-*` family (FastAPI / Django / SQLAlchemy / Celery / httpx / requests / Redis / pymongo), `prometheus_client`, Celery signals (`task_prerun` / `task_postrun` / `task_failure`), and error-tracker SDKs (`sentry-sdk`, `honeybadger`, `rollbar`) directly instead of routing through the generic adapter. Focuses on whether Python production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Python. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a FastAPI or Django PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Python service or major feature
- Post-incident review when Python diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / structlog / Prometheus in a Python app
- Auditing async / Celery tracing and correlation across the request → task boundary

**Not for:**

- General Python code review (use `task-python-review`)
- Python performance issues with a known bottleneck (use `task-python-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                       | What Runs                                            |
| ---------- | ----------------------------------------------------------------- | ---------------------------------------------------- |
| `quick`    | Single endpoint, view, or task                                    | Logging + Prometheus metrics check only              |
| `standard` | Default - full Python observability review                        | All steps                                            |
| `deep`     | Pre-release of a critical Python service, or post-incident review | All steps + SLI/SLO suggestions for Python endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                   | Meaning                                                                                               |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-python-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-python-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-python-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-python-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked as a subagent of a Python-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Python, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect framework: FastAPI vs Django (or mixed). Record `Framework: FastAPI | Django | mixed`. Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (logging / OTel / Prometheus / Celery / error tracker) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below) rather than one-per-bullet.

**Grouping rule.** When a whole surface is `absent` (no `prometheus-client`, no OTel SDK init, no error-tracker SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/symbol they should land in - not one finding per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. This prevents 50-item dumps on greenfield reviews.

Then open the files that actually configure observability so findings cite real lines, not assumptions:

**FastAPI:**

- `app/core/logging.py` (or equivalent) - structlog config, processors, handler / formatter
- `app/main.py` / `app/core/telemetry.py` - OpenTelemetry SDK wiring (`TracerProvider`, `MeterProvider`, exporter config), instrumentation calls (`FastAPIInstrumentor.instrument_app`, `SQLAlchemyInstrumentor`, `HTTPXClientInstrumentor`, `CeleryInstrumentor`)
- `app/core/config.py` / `.env` - `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, log level, Sentry DSN, Prometheus port
- `pyproject.toml` / `requirements.txt` - confirm `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `prometheus-client`, `structlog`, `sentry-sdk[fastapi]` presence
- Every changed file in the diff that calls `logger.*`, registers a `Counter` / `Histogram` / `Gauge`, defines an `@app.middleware`, instruments with OTel, or modifies trace context

**Django:**

- `settings.py` `LOGGING` dict (handlers, formatters, loggers); custom logging filters
- `settings.py` OpenTelemetry config; `manage.py` / `wsgi.py` / `asgi.py` for `DjangoInstrumentor.instrument` placement
- `apps.py` `ready()` hooks that wire instrumentation
- Middleware list - look for `OpenTelemetry`, `Sentry`, request-id middleware
- `pyproject.toml` / `requirements.txt` - confirm `opentelemetry-instrumentation-django`, `opentelemetry-instrumentation-celery`, `django-prometheus`, `sentry-sdk[django]`

For diffs touching only one of these surfaces (a new view but no logging change, say), still read the existing config to know whether request-id / trace correlation, instrumentation, and SDKs are wired - a missing wire is the finding.

### Step 4 - Structured Logging (structlog / stdlib logging)

Inspect logging config and any `logger.*` callsite in the diff:

- [ ] **Production logger emits JSON** - structlog `JSONRenderer`, stdlib `logging` with `python-json-logger` `JsonFormatter`, or equivalent. No raw text logs in production
- [ ] **Correlation fields injected** in every log line: `trace_id`, `span_id`, `request_id`, `user_id` (when authenticated), `tenant_id`, plus business correlation IDs (`order_id`, `invoice_id`). FastAPI: middleware sets `contextvars` / `structlog.contextvars.bind_contextvars`; Django: middleware sets `request.id` and a `LogRecord.request_id` attribute via `logging.Filter`
- [ ] **OpenTelemetry log correlation**: `LoggingInstrumentor().instrument(set_logging_format=True)` injects `trace_id` / `span_id` into every log record automatically when OTel is active; flag if absent
- [ ] **Sensitive-field masking**: structlog processor or stdlib filter strips `password`, `token`, `authorization`, `credit_card`, `ssn`, `api_key`. Pydantic `Field(..., repr=False)` and DRF `write_only_fields` reinforce so `logger.info("payload=%s", obj)` cannot leak via `__repr__`
- [ ] **No `logger.info(user)` / `logger.info(model_instance)`** that serializes an ORM model (triggers lazy loads, may log PII / hashed passwords). Always log specific fields by ID
- [ ] **User-identity fields emitted as structured key-values, not in the message string**: `user_id`, `owner_id`, `tenant_id`, `email` go in via `logger.info("event", user_id=...)` or `bind_contextvars(user_id=...)`, never in `f"user={user_id}"`. A single redaction processor can scrub structured fields; it cannot reliably scrub them out of a free-text message
- [ ] **Log levels used correctly**: `error` for actionable failures, `warning` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics. Default root level `INFO` in prod; `DEBUG`/`TRACE` reserved for targeted modules
- [ ] **Parameterized stdlib logging** (`logger.info("processing order=%s", order_id)`) - not f-strings (`logger.info(f"processing order={order_id}")`); structlog binds keyword args directly so this is automatic
- [ ] **No log spam in hot loops** - iterating large querysets, scheduled jobs running every second, Celery tasks at high TPS must not log per-iteration; sample or use `debug` level
- [ ] **`exc_info=True`** on `logger.error(...)` calls inside `except` blocks so the traceback is captured; structlog `format_exc_info` processor handles this

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

Inspect OpenTelemetry config and instrumentation wiring:

- [ ] **OpenTelemetry SDK initialized**: `TracerProvider`, `MeterProvider`, `LoggerProvider` configured; OTLP exporter (gRPC or HTTP) pointed at the org's collector / backend; `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` set per env
- [ ] **Sampling policy explicit**: `ParentBased(TraceIdRatioBased(rate))` with `rate` per env (e.g., `0.1` in prod, `1.0` in staging); not left at default
- [ ] **Framework auto-instrumentation enabled**:
  - FastAPI: `FastAPIInstrumentor.instrument_app(app)` after app creation
  - Django: `DjangoInstrumentor().instrument()` in `apps.py` `ready()`
- [ ] **Database auto-instrumentation**: `SQLAlchemyInstrumentor().instrument(engine=engine)` (FastAPI) or `Psycopg2Instrumentor` (Django via OTel) - SQL spans attach to the request span
- [ ] **HTTP client instrumentation**: `HTTPXClientInstrumentor().instrument()` (httpx) and / or `RequestsInstrumentor().instrument()` (requests) - traceparent propagates outbound automatically
- [ ] **Celery instrumentation**: `CeleryInstrumentor().instrument()` so task spans link back to the dispatching request span via traceparent header propagation through the broker
- [ ] **Redis / cache instrumentation**: `RedisInstrumentor().instrument()` if Redis is in use
- [ ] **Custom spans** for business operations use `tracer.start_as_current_span(...)` over manual span management; no over-instrumentation (do not wrap a single SQLAlchemy query in a custom span - the SQL span already covers it)
- [ ] **Resource attributes** populated: `service.name`, `service.version`, `deployment.environment`; sourced from build metadata / env vars

### Step 6 - Prometheus Metrics

Inspect Prometheus / metrics registration:

- [ ] **`prometheus-client` installed** and `/metrics` endpoint exposed (FastAPI: `prometheus_fastapi_instrumentator` or manual route; Django: `django-prometheus` middleware), or `OTEL_METRICS_EXPORTER=prometheus`
- [ ] **Default Python metrics** scraped: `python_gc_*`, `process_cpu_seconds_total`, `process_resident_memory_bytes`, `python_info` - confirm they appear at `/metrics`
- [ ] **HTTP server metrics**: `prometheus_fastapi_instrumentator` adds `http_requests_total` / `http_request_duration_seconds`; `django-prometheus` adds equivalents - confirm in middleware order so they wrap the full request path
- [ ] **Custom business metrics** named under a consistent namespace (`acme_orders_placed_total`, `acme_payments_failed_total`); units explicit (`Counter` for counts, `Histogram` for durations, `Gauge` for instantaneous values, `Summary` for quantile-required cases). Suffix conventions (`_total`, `_seconds`, `_bytes`) followed
- [ ] **Tag (label) cardinality bounded**: labels do not include unbounded values (`user_id`, `order_id`, `request_id`) - causes metric-cardinality blow-up. Allowed label values are enums / known categories (`status`, `tenant_tier`, `region`)
- [ ] **No metric registration in hot path**: `Counter(name, ...)` constructed at module level (or app startup), not per-request - registration in a request handler causes `ValueError: Duplicated timeseries`
- [ ] **Multi-process mode** for multi-worker deployments (Gunicorn / uvicorn `--workers > 1`): `prometheus-client` `multiprocess` directory configured; Django: `django-prometheus` `PROMETHEUS_MULTIPROC_DIR`
- [ ] **Histogram buckets** chosen for the SLO: default buckets are seconds-scale; for sub-100ms paths add finer buckets (`(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)`)

### Step 7 - Celery / Async Task Observability

_Skipped at `quick` depth unless the diff touches Celery._

Inspect Celery instrumentation and task observability:

- [ ] **`CeleryInstrumentor` enabled**: task spans link to dispatching request via traceparent header propagation; flag missing
- [ ] **Task signals wired** for metrics: `task_prerun` / `task_postrun` / `task_failure` / `task_retry` increment counters and observe duration histograms
- [ ] **`worker_ready` / `worker_shutting_down`** signals wired for lifecycle observability
- [ ] **Per-task metrics**: latency histogram, retry counter, failure counter, queue-depth gauge (via Celery `inspect` or broker introspection)
- [ ] **Trace context propagation across the request → Celery boundary**: when `task.delay(...)` is dispatched inside an HTTP request, the worker span links back to the request span (CeleryInstrumentor handles this automatically; flag manual wiring that breaks it)
- [ ] **structlog context binding inside the task**: `task_id`, `args` (sanitized) bound at `task_prerun`; cleared at `task_postrun`
- [ ] **Outbound HTTP from tasks instrumented**: `requests.post(...)` / `httpx.AsyncClient.post(...)` calls inside a task body are covered by `RequestsInstrumentor` / `HTTPXClientInstrumentor` so the worker span chains to the downstream service span; flag tasks that make uninstrumented outbound calls because the downstream timing / errors stay invisible to traces
- [ ] **Beat / scheduled task instrumentation**: each beat-scheduled task emits a span; missed-execution alerting via metric

### Step 8 - Async / Lifespan Observability (FastAPI)

_Skipped at `quick` depth unless the diff touches `@app.on_event` / lifespan / `BackgroundTasks` / async generators._

- [ ] **Lifespan span**: `@asynccontextmanager` lifespan handler emits `app.startup` / `app.shutdown` spans for cold-start / drain visibility
- [ ] **`BackgroundTasks`**: the trace context propagates to the background task; flag if missing
- [ ] **`asyncio.create_task` fire-and-forget**: trace context preserved via `contextvars` automatically (Python 3.11+); confirm `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` does not exclude `asyncio`
- [ ] **`loop.run_in_executor` boundary**: for CPU-bound work moved to a thread pool, the trace context must be re-bound manually (`opentelemetry-instrumentation-threading` or explicit `tracer.start_as_current_span` on the executor side)
- [ ] **Long-running async generators**: span lifecycle covers the full generator, not just creation

### Step 9 - Error Tracking (Sentry / Honeybadger / Rollbar SDKs)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/API-key handling._

Inspect SDK config:

- [ ] **SDK installed and initialized** with framework integration: `sentry-sdk.init(integrations=[FastApiIntegration(), SqlalchemyIntegration(), CeleryIntegration()])` or Django equivalent
- [ ] **DSN / API key** in env var or Vault, not committed to settings
- [ ] **Release / environment tags** populated from build metadata (`release="..."`, `environment="prod"`)
- [ ] **PII scrubbing on**: `send_default_pii=False` (Sentry default but flag if explicitly `True`); `before_send` strips known sensitive keys; allowlist of breadcrumb fields documented
- [ ] **OpenTelemetry / structlog correlation forwarded**: error event includes `trace_id` and `user_id` so incidents link back to traces / users; Sentry SDK auto-extracts trace context when OTel SDK is active
- [ ] **Sample rate explicit**: `traces_sample_rate`, `profiles_sample_rate` per env; not `1.0` in prod for tracing
- [ ] **Ignored exceptions documented**: `ignore_errors=[...]` lists classes that should not page (e.g., `Http404`, validation errors when handled by middleware); each ignore has a comment
- [ ] **Custom exception handlers** (`@app.exception_handler` / DRF `EXCEPTION_HANDLER`) call `sentry_sdk.capture_exception(exc)` before transforming the exception to a response, so the original stack trace reaches the tracker

### Step 10 - Health Checks and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one Prometheus / OTel SLI (HTTP request rate filtered to the journey URI, success rate, p95 latency)
- [ ] DB / cache / message broker / external API health checked via dedicated `/health` or `/readyz` endpoint - readiness reflects "ready to serve" (DB up, caches warmed); liveness reflects "process alive"
- [ ] FastAPI: `@app.get("/healthz")` simple liveness, `@app.get("/readyz")` checks DB / Redis / external dep
- [ ] Django: `django-health-check` or custom `views.py` health view; Postgres / Redis / Celery / storage backend checks
- [ ] SLO targets documented in code (decorator / service README) - not a free-floating Confluence page
- [ ] Synthetic probes (k6 / Locust) call `/readyz` not just `/healthz` - readiness reflects ability to serve

## Self-Check

- [ ] Stack confirmed as Python (or accepted from parent dispatcher); framework recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent - the parent already gated)
- [ ] Instrumentation surfaces (logging config, OTel wiring, settings, dependencies, changed call sites) read directly before applying checklists
- [ ] Structured logging assessed: JSON output, trace / request-id correlation, sensitive-field masking, log level discipline, parameterized logging
- [ ] OpenTelemetry SDK and auto-instrumentation reviewed: framework / DB / HTTP / Celery instrumentation enabled, sampling explicit, resource attributes populated
- [ ] Prometheus metrics assessed: client on classpath, default + HTTP server metrics scraped, custom metric naming under namespace, label cardinality bounded, multi-process mode for multi-worker deploys
- [ ] Celery observability assessed: instrumentation enabled, task signals wired, trace propagation across dispatch boundary, beat / scheduled task spans
- [ ] Async / lifespan observability assessed (FastAPI only): lifespan spans, BackgroundTasks context, executor-boundary re-binding
- [ ] Error tracker integration assessed: SDK wired with framework integrations, DSN externalized, PII scrubbed, OTel correlation forwarded, sample rate explicit
- [ ] Findings name a Python / OTel / structlog / Prometheus idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/Celery/async/error-tracker/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low

## Output Format

```markdown
## Python Observability Review Summary

**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Logging:** structlog (JSON) | stdlib logging + python-json-logger | stdlib logging (text) | absent
**Metrics:** Prometheus (prometheus-client) | OTel metrics (Prometheus exporter) | StatsD | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin exporter) | absent
**Celery instrumentation:** CeleryInstrumentor | partial | absent | n/a (no Celery)
**Error Tracker:** Sentry | Honeybadger | Rollbar | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

_The 5-row verdict from Step 3, repeated here as the top-line read for the reviewer. Each row is `wired | partial | absent` plus a one-line citation._

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| Logging                | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| Prometheus / metrics   | wired / partial / absent       | [...]                                      |
| Celery instrumentation | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as the `Overall:` headline when 3+ of the rows above are `absent` - it tells the reader the review is scaffolding, not auditing, and changes how they prioritize. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Python idiom: missing structlog `bind_contextvars` for request_id, unbounded label cardinality on `user_id`, `Counter` constructed in handler causing duplicate-registration error, missing `CeleryInstrumentor`, etc.]
- **Impact:** [diagnosability / alertability / cost cost]
- **Fix:** [specific Python / OTel / structlog change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Logging / Tracing / Metrics / Celery / Error Tracker / Async-Lifespan) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Add structlog JSON renderer in prod profile", "Wire CeleryInstrumentor for cross-broker trace propagation", "Switch from per-request `Counter(...)` to module-level constants"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Bind `order_id` via `structlog.contextvars.bind_contextvars(order_id=...)` at OrderService.place entry; clear in `finally`"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/metrics` endpoint to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Python / OTel / structlog / Prometheus idiom ("add metrics" vs "register `prometheus_client.Counter` named `acme_orders_placed_total` at module level with bounded labels")
- Recommending generic observability advice when a Python SDK or auto-instrumentation exists (say "enable `FastAPIInstrumentor`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high label cardinality (`user_id`, `order_id`) as acceptable - metric series cost compounds; require enum / category labels
- Approving f-string logging (`logger.info(f"...")`) over parameterized form - the rendered string locks the formatter and prevents log-aggregation tools from parsing fields
- Suggesting `logger.error(traceback.format_exc())` (string-formatted) instead of `logger.error("...", exc_info=True)` (preserves structured exception info)
- Approving `Counter(...)` registration inside a request handler - causes duplicate-registration crashes after the first request
- Approving `OTEL_TRACES_SAMPLER=always_on` in prod for high-traffic services - cost and storage compound
- Treating `print(...)` as logging - flag for replacement
- Prescribing the OTLP endpoint URL or the Sentry DSN value - say "sourced from env / Vault" and stop; concrete URLs are infra config, not source-code review
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
- Producing only structlog recommendations when the team is on stdlib `logging` - `python-json-logger` + `LoggingInstrumentor` is an acceptable target if the team is not ready to adopt structlog
