---
name: task-python-review-observability
description: "Python observability review: structlog, OpenTelemetry, FastAPI/Django/SQLAlchemy/Celery instrumentation, Prometheus, Sentry."
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, observability, logging, metrics, tracing, opentelemetry, structlog, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Python Observability Review

Stack-specific delegate of `task-code-review-observability` for Python. Names `structlog` / stdlib `logging` JSON handlers, OpenTelemetry Python SDK + `opentelemetry-instrumentation-*` (FastAPI / Django / SQLAlchemy / Celery / httpx / requests / Redis), `prometheus-client`, Celery signals (`task_prerun` / `task_postrun` / `task_failure`), and error-tracker SDKs (`sentry-sdk`, `honeybadger`, `rollbar`) directly. Library / SDK level only; infra (Datadog dashboards, log forwarders, alert rules) is out of scope.

## When to Use

- Reviewing a FastAPI or Django PR for observability regressions or new instrumentation gaps
- Pre-release check for a new Python service or major feature
- Post-incident review when Python diagnosis was slow or evidence missing
- Adopting OpenTelemetry / structlog / Prometheus / Celery instrumentation

**Not for:** general Python review (`task-python-review`), known-bottleneck perf (`task-python-review-perf`), active incidents (`/task-oncall-start`), infra observability config.

## Depth Levels

| Depth      | When                                           | Runs                                        |
| ---------- | ---------------------------------------------- | ------------------------------------------- |
| `standard` | Default                                        | All steps                                   |
| `deep`     | Pre-release of critical service, post-incident | All steps + SLI/SLO suggestions             |

Default: `standard`.

## Invocation

| Invocation                                   | Meaning                                                              |
| -------------------------------------------- | -------------------------------------------------------------------- |
| `/task-python-review-observability`          | Current branch vs base; fails fast on trunk                          |
| `/task-python-review-observability <branch>` | `<branch>` vs base (3-dot diff)                                      |
| `/task-python-review-observability pr-<N>`   | PR head fetched into local `pr-<N>` branch (user runs fetch first)   |

As a subagent of `task-code-review-observability` or `task-python-review`, the parent passes the precondition handle plus pre-read diff / commit log; Step 2 is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Skip re-detection if parent confirmed. If not Python, stop and direct user to `/task-code-review-observability`.

Record `Framework: FastAPI | Django | mixed`. Subsequent steps branch on this signal.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once; reuse for all later steps. Skip if running as subagent with pre-read artifacts. If the precondition check fails, surface its message verbatim and stop. No state-changing git from this workflow.

### Step 3 - Read the Instrumentation Surface

**Top-line output:** one verdict per surface (Logging / OTel SDK / Prometheus / Celery / Error tracker) of `wired | partial | absent`. Absence is itself the finding.

**Grouping rule.** When a whole surface is `absent`, produce **one High-Impact finding for that surface**, listing missing pieces grouped by file/symbol they should land in. Per-callsite findings only apply when the surface exists and is misused. Prevents 50-item dumps on greenfield reviews.

Open the config files so findings cite real lines:

**FastAPI:** `app/core/logging.py` (structlog config, processors, redaction), `app/main.py` / `app/core/telemetry.py` (`TracerProvider`, `MeterProvider`, OTLP exporter, `FastAPIInstrumentor.instrument_app`, `SQLAlchemyInstrumentor`, `HTTPXClientInstrumentor`, `CeleryInstrumentor`), `app/core/config.py` / `.env` (`OTEL_*`, log level, Sentry DSN, Prometheus port), `pyproject.toml` / `requirements.txt` (`opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `prometheus-client`, `structlog`, `sentry-sdk[fastapi]`).

**Django:** `settings.py` `LOGGING` dict + filters, OTel config, `DjangoInstrumentor.instrument()` placement (`apps.py` `ready()`), middleware list (OTel, Sentry, request-id), `pyproject.toml` / `requirements.txt` (`opentelemetry-instrumentation-django`, `opentelemetry-instrumentation-celery`, `django-prometheus`, `sentry-sdk[django]`).

Plus every changed file calling `logger.*`, registering a metric, defining middleware, or touching trace context.

### Step 4 - Structured Logging (structlog / stdlib logging)

- [ ] **JSON output** in prod: `structlog` `JSONRenderer`, or stdlib `logging` + `python-json-logger` `JsonFormatter`. No raw text
- [ ] **Correlation fields** every line: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs. FastAPI: middleware + `structlog.contextvars.bind_contextvars`. Django: request-id middleware + `logging.Filter` injecting `LogRecord.request_id`
- [ ] **OTel log correlation**: `LoggingInstrumentor().instrument(set_logging_format=True)` injects `trace_id` / `span_id` into every record
- [ ] **Redaction** of secrets: structlog processor or stdlib filter strips `password`, `token`, `authorization`, `credit_card`, `ssn`, `api_key`. Reinforced by Pydantic `Field(..., repr=False)` / DRF `write_only_fields`
- [ ] **No entity logging**: `logger.info(model_instance)` may trigger lazy loads and leak PII / hashed passwords. Log specific fields by ID
- [ ] **Identity fields as structured key-values**, not in message string: `logger.info("event", user_id=...)` not `f"user={user_id}"`. Redaction cannot scrub free-text reliably
- [ ] **Log levels**: `error` actionable, `warning` recoverable, `info` state transitions, `debug` verbose. Default `INFO` in prod
- [ ] **Parameterized stdlib logging** (`logger.info("order=%s", order_id)`), not f-strings; structlog binds kwargs directly
- [ ] **No hot-loop logging** (large querysets, per-second jobs, high-TPS Celery tasks): sample or `debug`
- [ ] **`exc_info=True`** on `logger.error(...)` inside `except`; structlog `format_exc_info` processor handles it
- [ ] **No request / response body logging in prod**: PII leak + 10-100x volume inflation. Single-payload trace goes behind a feature flag at `debug` level scoped to a request-id allowlist, not unconditional `info`

### Step 5 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK initialized**: `TracerProvider`, `MeterProvider`, `LoggerProvider` configured; OTLP exporter (gRPC or HTTP) pointed at the collector; `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Sampling explicit**: `ParentBased(TraceIdRatioBased(rate))` with `rate` per env (e.g., `0.1` prod, `1.0` staging); not default
- [ ] **Framework**: FastAPI `FastAPIInstrumentor.instrument_app(app)`; Django `DjangoInstrumentor().instrument()` in `apps.py` `ready()`
- [ ] **Database**: `SQLAlchemyInstrumentor().instrument(engine=engine)` or `Psycopg2Instrumentor` - SQL spans attach to request
- [ ] **HTTP client**: `HTTPXClientInstrumentor` (httpx) / `RequestsInstrumentor` (requests); traceparent propagates outbound
- [ ] **Celery**: `CeleryInstrumentor().instrument()` so task spans link to dispatching request via traceparent through the broker
- [ ] **Redis / cache**: `RedisInstrumentor().instrument()` if in use
- [ ] **Custom spans** via `tracer.start_as_current_span(...)`; no double-instrumentation (do not wrap a single SQLAlchemy query when the SQL span already covers it)
- [ ] **Resource attributes**: `service.name`, `service.version`, `deployment.environment` from build / env

### Step 6 - Prometheus Metrics

- [ ] **`prometheus-client` installed** with `/metrics` exposed (FastAPI: `prometheus_fastapi_instrumentator`; Django: `django-prometheus`) or `OTEL_METRICS_EXPORTER=prometheus`
- [ ] **Default Python metrics** scraped: `python_gc_*`, `process_cpu_seconds_total`, `process_resident_memory_bytes`, `python_info`
- [ ] **HTTP server metrics**: `http_requests_total` / `http_request_duration_seconds` via the framework adapter, wired in middleware order to wrap the full request
- [ ] **Custom metrics** under a namespace (`acme_orders_placed_total`); types correct (`Counter`/`Histogram`/`Gauge`/`Summary`); suffixes (`_total`/`_seconds`/`_bytes`)
- [ ] **Label cardinality bounded**: never label by `user_id`/`order_id`/`request_id`; only enums/categories (`status`, `tenant_tier`, `region`)
- [ ] **No registration in hot path**: `Counter(name, ...)` at module / startup level only; per-request causes `ValueError: Duplicated timeseries`
- [ ] **Multi-process mode** for multi-worker (Gunicorn / uvicorn `--workers > 1`): `prometheus-client` `multiprocess` dir / Django `PROMETHEUS_MULTIPROC_DIR`
- [ ] **Histogram buckets** match SLO; for sub-100ms paths add finer buckets (`(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)`)

### Step 7 - Celery / Async Task Observability

- [ ] **`CeleryInstrumentor` enabled**: task spans link to dispatching request via traceparent through the broker
- [ ] **Task signals wired**: `task_prerun` / `task_postrun` / `task_failure` / `task_retry` → counters + duration histograms
- [ ] **`worker_ready` / `worker_shutting_down`** signals wired for lifecycle observability
- [ ] **Per-task metrics**: latency histogram, retry / failure counters, queue-depth gauge (Celery `inspect` or broker introspection)
- [ ] **Trace context across request → task boundary**: `CeleryInstrumentor` handles it; flag manual wiring that breaks it
- [ ] **structlog context inside the task**: `task_id`, sanitized `args` bound at `task_prerun`; cleared at `task_postrun`
- [ ] **Outbound HTTP from tasks instrumented**: `requests`/`httpx` calls covered by their instrumentors so worker spans chain downstream
- [ ] **Beat / scheduled tasks**: each emits a span; missed-execution alerting via metric

### Step 8 - Async / Lifespan Observability (FastAPI)

- [ ] **Lifespan span**: `@asynccontextmanager` lifespan emits `app.startup` / `app.shutdown` for cold-start / drain visibility
- [ ] **`BackgroundTasks`**: trace context propagates to the background task; flag if missing
- [ ] **`asyncio.create_task`**: context preserved via `contextvars` (Python 3.11+); confirm `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` does not exclude `asyncio`
- [ ] **`loop.run_in_executor` boundary**: CPU-bound thread-pool work needs `opentelemetry-instrumentation-threading` or explicit `start_as_current_span` on the executor side
- [ ] **Long-running async generators**: span covers the full lifecycle, not just creation

### Step 9 - Error Tracking (Sentry / Honeybadger / Rollbar)

- [ ] **SDK initialized with framework integration**: `sentry_sdk.init(integrations=[FastApiIntegration(), SqlalchemyIntegration(), CeleryIntegration()])` or Django equivalent
- [ ] **DSN in env / Vault**, not committed
- [ ] **Release + environment tags** from build metadata
- [ ] **PII scrubbing**: `send_default_pii=False`; `before_send` strips sensitive keys
- [ ] **OTel / structlog correlation forwarded**: events carry `trace_id`, `user_id` (Sentry SDK auto-extracts when OTel SDK active)
- [ ] **Sample rate explicit**: `traces_sample_rate`, `profiles_sample_rate` per env; never `1.0` in high-traffic prod
- [ ] **`ignore_errors`** lists handled exceptions (`Http404`, validation) with comments
- [ ] **Custom exception handlers** (`@app.exception_handler` / DRF `EXCEPTION_HANDLER`) call `sentry_sdk.capture_exception(exc)` before transforming, preserving the original stack

### Step 10 - Health Checks and SLIs (deep only)

- [ ] Critical journeys have an SLI (rate, success, p95)
- [ ] **Liveness `/healthz`**: 200 if the process is responsive. No DB / Redis / external ping - a flaky dep would restart every replica
- [ ] **Readiness `/readyz`**: 200 only when this pod can serve - DB pool, Redis, Celery connection. No third-party ping - one upstream outage would pull every replica from rotation
- [ ] **Dependency-health endpoint** (separate route or metric) for third-party reachability; observability signal only, NOT wired to readiness
- [ ] FastAPI: `@app.get("/healthz")` liveness; `@app.get("/readyz")` checks own-pod deps
- [ ] Django: `django-health-check` or custom view with Postgres / Redis / Celery / storage checks
- [ ] SLO targets documented in code (decorator / README), not free-floating
- [ ] Synthetic probes hit `/readyz`, not just `/healthz`

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the assembled output to the report file and print the confirmation line.

## Output Format

```markdown
## Python Observability Review Summary

**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Logging:** structlog (JSON) | stdlib + python-json-logger | stdlib (text) | absent
**Metrics:** Prometheus (prometheus-client) | OTel metrics (Prometheus exporter) | StatsD | absent
**Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin) | absent
**Celery instrumentation:** CeleryInstrumentor | partial | absent | n/a
**Error Tracker:** Sentry | Honeybadger | Rollbar | absent
**Overall:** Adequate | Gaps Found - [count by impact] | Greenfield - no observability surface wired

## Surface Map

| Surface                | Verdict                        | Evidence                                   |
| ---------------------- | ------------------------------ | ------------------------------------------ |
| Logging                | wired / partial / absent       | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired / partial / absent       | [...]                                      |
| Prometheus / metrics   | wired / partial / absent       | [...]                                      |
| Celery instrumentation | wired / partial / absent / n/a | [...]                                      |
| Error tracker          | wired / partial / absent       | [...]                                      |

> Use **Greenfield** as `Overall:` when 3+ rows are `absent`. Use the `absent` vocabulary consistently (not `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Python idiom: missing `bind_contextvars` for request_id, unbounded `user_id` label, `Counter` constructed in handler causing duplicate-registration, missing `CeleryInstrumentor`, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Python / OTel / structlog / prometheus-client change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty sections. Group by surface within a bucket when 3+ share one; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per Step 3._

## Recommendations

[Structural improvements not tied to a single finding - e.g., "Add structlog `JSONRenderer` in prod profile", "Wire `CeleryInstrumentor` for cross-broker trace propagation", "Switch per-request `Counter(...)` to module-level constants"]

## Next Steps

Prioritized action list. Each item `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Bind `order_id` via `structlog.contextvars.bind_contextvars(order_id=...)` at `OrderService.place` entry; clear in `finally`"]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action, e.g., "Wire `/metrics` to org Prometheus scrape config"]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1: Stack confirmed as Python (or accepted from parent); framework recorded
- [ ] Step 2: `review-precondition-check` ran (or handle received from parent); diff and commit log read once and reused
- [ ] Step 3: Instrumentation surfaces (logging config, OTel wiring, settings, dependencies) read; surface map produced with `wired | partial | absent` verdicts; absent surfaces collapsed to one finding each
- [ ] Step 4: Structured logging assessed - JSON, correlation, redaction, level discipline, parameterized form, no body logging, `exc_info`
- [ ] Step 5: OTel SDK and auto-instrumentation reviewed - framework / DB / HTTP / Celery / Redis instrumentations, explicit sampling, resource attributes
- [ ] Step 6: `prometheus-client` assessed - default + HTTP metrics, namespaced custom metrics, bounded label cardinality, module-level registration, multi-process mode
- [ ] Step 7: Celery observability assessed - instrumentation, task signals, trace propagation across dispatch, beat spans
- [ ] Step 8: Async / lifespan assessed - lifespan span, BackgroundTasks, executor-boundary re-binding
- [ ] Step 9: Error tracker assessed - SDK + framework integration, DSN externalized, PII scrubbed, OTel correlation, sample rate
- [ ] Step 10: At `deep`, SLIs / liveness / readiness / dependency-health separation reviewed; skipped otherwise
- [ ] Step 11: Report written via `review-report-writer`; confirmation line printed
- [ ] Findings name a Python / OTel / structlog / prometheus-client idiom directly - not "add observability"
- [ ] Library-level scope respected; infra concerns deferred to ops
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend > Question

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Generic advice when a Python SDK exists ("enable `FastAPIInstrumentor`", not "add HTTP request tracing")
- Reviewing infra (Datadog, Grafana, alert rules, log forwarders, on-call rotation)
- Approving `OTEL_TRACES_SAMPLER=always_on` in high-traffic prod
- Suggesting `logger.error(traceback.format_exc())` instead of `logger.error("...", exc_info=True)`
- Prescribing OTLP endpoint URL or Sentry DSN - say "sourced from env / Vault" and stop
- One finding per missing checkbox when a whole surface is absent - collapse per Step 3
- Recommending only structlog when the team uses stdlib `logging` - `python-json-logger` + `LoggingInstrumentor` is acceptable
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
