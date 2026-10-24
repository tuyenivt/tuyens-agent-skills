---
name: task-python-review-observability
description: "Python observability review: structlog, OpenTelemetry, FastAPI/Django/SQLAlchemy/Celery instrumentation, Prometheus, Sentry."
agent: python-observability-engineer
metadata:
  category: backend
  tags: [python, fastapi, django, observability, logging, metrics, tracing, opentelemetry, structlog, workflow]
  type: workflow
user-invocable: true
---

# Python Observability Review

Stack-specific delegate of `task-code-review-observability` for Python. Names `structlog` / stdlib `logging` JSON handlers, the OpenTelemetry Python SDK + `opentelemetry-instrumentation-*` (FastAPI / Django / SQLAlchemy / Celery / httpx / requests / Redis), `prometheus-client`, Celery signals (`task_prerun` / `task_postrun` / `task_failure`), and error-tracker SDKs (`sentry-sdk`, `honeybadger`, `rollbar`) directly. Library / SDK level only; infra (dashboards, log forwarders, alert rules) is out of scope.

## When to Use

- Reviewing a FastAPI or Django PR for observability regressions or new instrumentation gaps
- Pre-release check for a new Python service or major feature
- Post-incident review when Python diagnosis was slow or evidence missing
- Adopting OpenTelemetry / structlog / Prometheus / Celery instrumentation

**Not for:** general Python review (`task-python-review`), known-bottleneck perf (`task-python-review-perf`), infra observability config.

## Depth Levels

| Depth      | When                                           | Runs                                                        |
| ---------- | ---------------------------------------------- | ----------------------------------------------------------- |
| `standard` | Default                                        | Steps 1-10 and 12; Step 11 skipped                          |
| `deep`     | Pre-release of a critical service, post-incident | All steps, touched files read in full, plus `## SLI / SLO Suggestions` |

## Invocation

`/task-python-review-observability [<branch> | pr-<N>] [standard | deep] [--base <branch>]` - flags compose: `/task-python-review-observability pr-50273 --base release/2026.05 deep`. No argument reviews the current branch and fails fast on trunk; `pr-<N>` needs the local branch the user fetched.

**Subagent mode** (spawned by `task-python-review` or `task-code-review-observability`): the parent supplies the stack-detect block, the precondition handle, the read-once diff / name-status / log, and the depth. Step 1 still applies; Steps 2-3 consume the supplied inputs instead of running; Step 12 is skipped and the findings return as the subagent envelope in Output Format - the parent verifies, reconciles and writes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Framework

Use skill: `stack-detect`. If `Language` is not Python, stop and route to `/task-code-review-observability`. `Framework` comes from the block (`FastAPI 0.115`, `Django 5.1`); the dependency manifest fills `unknown` and reveals a second framework - `fastapi` -> FastAPI, `django` -> Django; both named -> the one framework the name-status (Step 3) touches, else `mixed` (files under both or neither; both branches of every step run); neither names FastAPI or Django (Flask, plain Python) -> `unknown`: Step 4 reads the framework-neutral categories of both lists, and only the APIs a row names from a framework the project does not use go N/A; its framework-neutral items still run. Record `Framework: FastAPI | Django | mixed | unknown` - FastAPI / Django with a version (the block's when it names that framework with one, else its manifest pin, else omitted) - and the Python version (`Language`, else `requires-python` / `.python-version`, else `unknown`).

### Step 3 - Resolve the Diff and Decide the Round

Use skill: `review-precondition-check` with `argument`, `base` (from `--base`), and `report_type: review-observability`. On failure, surface its message verbatim and stop; never run state-changing git. On success, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`.

**Round gate.** The handle's `prior_checkpoint` is this lens's checkpoint or `legacy`. A valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals the handle's, and whose `depth` the requested depth does not exceed -> print `No new commits since prior observability review.` and stop: no review, no report. Otherwise a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` (Step 12 overwrites a legacy file). Then read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log <base_ref>..<head_ref>`.

### Step 4 - Read the Instrumentation Surface

**Top-line output:** one verdict per surface (Logging / OTel SDK / Prometheus / Celery / Error tracker) from the vocabulary `wired | partial | absent`, plus `n/a` for Celery when it is not a dependency. `partial` = configured but missing a wiring piece (text renderer, no trace / request correlation, an instrumentor not registered); `wired` = every wiring piece present - callsite findings do not change the verdict; `absent` = no configuration at all, even with the dependency declared. Absence is itself the finding.

**Grouping rule.** An `absent` surface produces **one High-Impact finding for that surface**, listing the missing pieces grouped by the file / symbol they should land in. It anchors at the existing entry point that should wire the surface (`app/main.py` app construction, `settings.py`, the module defining `Celery(...)`) and verify attributes it like any finding. A `partial` or `wired` surface gets per-callsite findings.

Open the config files so findings cite real lines:

**FastAPI:** `app/core/logging.py` (structlog config, processors, redaction), `app/main.py` / `app/core/telemetry.py` (`TracerProvider`, `MeterProvider`, OTLP exporter, `FastAPIInstrumentor.instrument_app`, `SQLAlchemyInstrumentor`, `HTTPXClientInstrumentor`, `CeleryInstrumentor`), `app/core/config.py` / `.env` (`OTEL_*`, log level, Sentry DSN, Prometheus port), `pyproject.toml` / `requirements.txt` (`opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `prometheus-client`, `structlog`, `sentry-sdk[fastapi]`).

**Django:** `settings.py` `LOGGING` dict + filters, OTel config, `DjangoInstrumentor().instrument()` placement (`apps.py` `ready()`), middleware list (OTel, Sentry, request-id, `django-prometheus` before / after), `pyproject.toml` / `requirements.txt` (`opentelemetry-instrumentation-django`, `opentelemetry-instrumentation-celery`, `django-prometheus`, `sentry-sdk[django]`).

Plus every changed file calling `logger.*`, `print(...)`, registering a metric, defining middleware, or touching trace context.

### Step 5 - Structured Logging (structlog / stdlib logging)

- [ ] **A logger is configured at all**: `print(...)` in application paths is the greenfield-logging finding - no levels, no structure, unmanaged stdout
- [ ] **JSON output** in prod: `structlog` `JSONRenderer`, or stdlib `logging` + `python-json-logger` `JsonFormatter`. No raw text formatter
- [ ] **Correlation fields** on every line: `trace_id`, `span_id`, `request_id`, `user_id`, `tenant_id`, business IDs. FastAPI: middleware + `structlog.contextvars.bind_contextvars`. Django: request-id middleware + a `logging.Filter` injecting `LogRecord.request_id`
- [ ] **OTel log correlation**: `LoggingInstrumentor().instrument()` injects `otelTraceID` / `otelSpanID` / `otelServiceName` into every stdlib `LogRecord` (`set_logging_format=True` only adds a root format string printing them); structlog needs a processor reading `trace.get_current_span().get_span_context()`
- [ ] **Redaction** of secrets: structlog processor or stdlib filter strips `password`, `token`, `authorization`, `credit_card`, `ssn`, `api_key`. Reinforced by Pydantic `Field(..., repr=False)` / DRF `extra_kwargs={"password": {"write_only": True}}`
- [ ] **No entity logging**: `logger.info(model_instance)` may trigger lazy loads and leak PII / hashed passwords. Log specific fields by ID
- [ ] **Identity fields as structured key-values**, not in the message string: `logger.info("event", user_id=...)` not `f"user={user_id}"` - redaction cannot scrub free text
- [ ] **Log levels**: `error` actionable, `warning` recoverable, `info` state transitions, `debug` verbose. Default `INFO` in prod, never root `DEBUG`
- [ ] **Parameterized stdlib logging** (`logger.info("order=%s", order_id)`), not f-strings; structlog binds kwargs directly
- [ ] **No hot-loop logging** (large querysets, per-second jobs, high-TPS Celery tasks): sample or `debug`
- [ ] **`exc_info=True`** on `logger.error(...)` inside `except`; structlog `format_exc_info` handles it
- [ ] **No request / response body logging in prod**: PII leak + 10-100x volume. A single-payload trace sits behind a feature flag at `debug`, scoped to a request-id allowlist

### Step 6 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK initialized**: `TracerProvider`, `MeterProvider`, `LoggerProvider` configured; OTLP exporter pointed at the collector; `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` per env
- [ ] **Sampling explicit**: `ParentBased(TraceIdRatioBased(rate))` with `rate` per env (`0.1` prod, `1.0` staging); never the default
- [ ] **Framework**: FastAPI `FastAPIInstrumentor.instrument_app(app)`; Django `DjangoInstrumentor().instrument()` in `apps.py` `ready()`
- [ ] **Database**: `SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)` for an async engine (the `AsyncEngine` itself raises `NotImplementedError`), or `Psycopg2Instrumentor` - SQL spans attach to the request
- [ ] **HTTP client**: `HTTPXClientInstrumentor` (httpx) / `RequestsInstrumentor` (requests); traceparent propagates outbound
- [ ] **Celery**: `CeleryInstrumentor().instrument()` so task spans link to the dispatching request through the broker
- [ ] **Redis / cache**: `RedisInstrumentor().instrument()` when in use
- [ ] **Custom spans** via `tracer.start_as_current_span(...)`; no double instrumentation (a single SQLAlchemy query already has a SQL span)
- [ ] **Resource attributes**: `service.name`, `service.version`, `deployment.environment.name` (the un-suffixed key is deprecated) from build / env

### Step 7 - Prometheus Metrics

- [ ] **`prometheus-client` installed** with `/metrics` exposed (FastAPI: `prometheus_fastapi_instrumentator`; Django: `django-prometheus`) or `OTEL_METRICS_EXPORTER=prometheus`
- [ ] **Default Python metrics** scraped: `python_gc_*`, `process_cpu_seconds_total`, `process_resident_memory_bytes`, `python_info`
- [ ] **HTTP server metrics**: FastAPI `http_requests_total` / `http_request_duration_seconds` via the instrumentator; Django `django_http_requests_total_by_method` / `django_http_requests_latency_seconds_by_view_method` with `PrometheusBeforeMiddleware` first and `PrometheusAfterMiddleware` last
- [ ] **Custom metrics** under a namespace (`acme_orders_placed_total`); types correct (`Counter` / `Histogram` / `Gauge` / `Summary`); suffixes (`_total` / `_seconds` / `_bytes`)
- [ ] **Label cardinality bounded**: never label by `user_id` / `order_id` / `request_id`; only enums / categories
- [ ] **No registration in the hot path**: `Counter(name, ...)` at module / startup level only; per-request raises `ValueError: Duplicated timeseries`
- [ ] **Multi-process mode** for multi-worker (gunicorn / uvicorn `--workers > 1`): the `PROMETHEUS_MULTIPROC_DIR` env var (prometheus-client's, not a Django setting) + `multiprocess.MultiProcessCollector`
- [ ] **Histogram buckets** match the SLO; sub-100 ms paths need buckets below the default 5 ms floor (`(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)`)

### Step 8 - Celery / Async Task Observability

- [ ] **Task signals wired**: `task_prerun` / `task_postrun` / `task_failure` / `task_retry` -> counters + duration histograms
- [ ] **`worker_ready` / `worker_shutting_down`** signals wired for lifecycle visibility
- [ ] **Per-task metrics**: latency histogram, retry / failure counters, queue-depth gauge (Celery `inspect` or broker introspection)
- [ ] **Trace context across the request -> task boundary**: `CeleryInstrumentor` (Step 6) carries it; flag manual header wiring that breaks it
- [ ] **structlog context inside the task**: `task_id`, sanitized `args` bound at `task_prerun`; cleared at `task_postrun`
- [ ] **Outbound HTTP from tasks instrumented**: `requests` / `httpx` instrumentors so worker spans chain downstream
- [ ] **Beat / scheduled tasks**: each emits a span; missed-execution alerting via a metric

### Step 9 - Async / Lifespan Observability (FastAPI)

_Skip on Django._

- [ ] **Lifespan span**: the `@asynccontextmanager` lifespan emits `app.startup` / `app.shutdown` for cold-start / drain visibility
- [ ] **`BackgroundTasks`**: trace context propagates to the background task; flag when missing
- [ ] **`asyncio.create_task`**: the copied `contextvars` context carries the active span; flag code running the coroutine under a fresh `contextvars.Context()` or a detached OTel context
- [ ] **`loop.run_in_executor` boundary**: thread-pool work needs `opentelemetry-instrumentation-threading` or an explicit `start_as_current_span` on the executor side
- [ ] **Long-running async generators**: span covers the full lifecycle, not just creation

### Step 10 - Error Tracking (Sentry / Honeybadger / Rollbar)

- [ ] **SDK initialized with framework integration**: `sentry_sdk.init(integrations=[FastApiIntegration(), SqlalchemyIntegration(), CeleryIntegration()])` or the Django equivalent
- [ ] **DSN in env / Vault**, not committed
- [ ] **Release + environment tags** from build metadata
- [ ] **PII scrubbing**: `send_default_pii=False`; `before_send` strips sensitive keys
- [ ] **OTel correlation**: `sentry_sdk.init(instrumenter="otel")` with `SentrySpanProcessor` + `SentryPropagator` registered; without them Sentry does not pick up OTel spans, and `set_tag` / `set_user` carry `trace_id` / `user_id` by hand
- [ ] **Sample rate explicit**: `traces_sample_rate`, `profiles_sample_rate` per env; never `1.0` in high-traffic prod
- [ ] **`ignore_errors`** lists handled exceptions (`Http404`, validation) with comments
- [ ] **Custom exception handlers** (`@app.exception_handler` / DRF `EXCEPTION_HANDLER`) call `sentry_sdk.capture_exception(exc)` before transforming

### Step 11 - Health Checks and SLIs (deep only)

- [ ] Critical journeys have an SLI (rate, success, p95); SLO targets documented in code (decorator / README), not free-floating
- [ ] **Liveness `/healthz`**: 200 when the process is responsive. No DB / Redis / external ping - a flaky dependency restarts every replica
- [ ] **Readiness `/readyz`**: 200 only when this pod can serve - DB pool, Redis, Celery connection. No third-party ping - one upstream outage pulls every replica from rotation
- [ ] **Dependency-health endpoint** for third-party reachability; an observability signal only, never wired to readiness
- [ ] FastAPI: `@app.get("/healthz")` liveness; `@app.get("/readyz")` checks own-pod dependencies. Django: `django-health-check` or a custom view with Postgres / Redis / Celery / storage checks
- [ ] Synthetic probes hit `/readyz`, not just `/healthz`

### Step 12 - Verify, Reconcile, Write

Standalone only; subagent runs return the envelope after Step 11.

**Verify.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line`, `Label`, and `Annotation`; its tally is the Summary's `Findings verified:` line.

**Reconcile (round 2+).** Project the prior report at the handle's `report_path` into reconcile's shape: `## High-Impact Findings`, one `### [Label] file:line` heading per finding (the label and bare `file:line` from its `####` heading - a pre-revision report with `- **Location:**` lines gives the Location's bare `file:line` and its own label when it wrote one, else `[Must]` under High Impact, `[Recommend]` otherwise; annotations as separate `_(...)_` groups - `_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`), each followed by an `Issue:` line. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, and `head_sha`; its output renders verbatim under `## Prior Round Reconciliation`. A `Still open` / `Needs re-check` row this round did not re-derive publishes in its prior impact section at its prior label (`[Blocker]` / `[High]` / `[Critical]` -> `[Must]`; other legacy labels -> `[Recommend]`; `[Praise]` never carried) with `_(carried from round <N>)_` after its `file:line` and any annotation; a re-derived row publishes once, as this round's finding.

**Write.** Use skill: `review-report-writer` with `report_type: review-observability`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `mode: full`, `round` + `prior_head_sha` from the gate, `scope: +obs`, `depth`, `stack` from `Framework` (`python-fastapi | python-django | python-mixed | python`), and `pr_url` when the prior checkpoint has it. Print the confirmation line.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a fence. Every finding carries exactly one label, `[Must]` or `[Recommend]`: impact sets the draft (High -> `[Must]`, Medium / Low -> `[Recommend]`) and verify's published `Label` governs every slot naming one. A finding sits in the section of its impact; a `[Recommend]` under High after de-escalation counts toward `<H> High`. A standalone finding on a file absent from the name-status whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first; an `Unverified` row gets none, and an old line in a touched file takes verify's attribution. `Overall` reads `Greenfield` when 3+ Surface Map rows are `absent`, whatever the other rows read. Subagent runs return only `## Surface Map` and `## Findings` (no annotations).

```markdown
## Python Observability Review Summary

- **Stack:** Python <version>
- **Framework:** FastAPI{ <version>} | Django{ <version>} | mixed | unknown
- **Logging:** structlog (JSON) | structlog (text) | stdlib + python-json-logger | stdlib (text) | absent
- **Metrics:** Prometheus (prometheus-client) | OTel metrics (Prometheus exporter) | StatsD | other (<library>) | absent
- **Tracing:** OpenTelemetry (OTLP) | OpenTelemetry (Jaeger / Zipkin) | absent
- **Celery instrumentation:** wired | partial | absent | n/a
- **Error Tracker:** Sentry | Honeybadger | Rollbar | absent
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Overall:** Adequate | Gaps Found - <H> High / <M> Medium / <L> Low | Greenfield - <N> of 5 surfaces absent
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}

## Surface Map

| Surface                | Verdict                              | Evidence                                   |
| ---------------------- | ------------------------------------ | ------------------------------------------ |
| Logging                | wired \| partial \| absent           | [file:line or "no logging config in repo"] |
| OpenTelemetry SDK      | wired \| partial \| absent           | [...]                                      |
| Prometheus / metrics   | wired \| partial \| absent           | [...]                                      |
| Celery instrumentation | wired \| partial \| absent \| n/a    | [...]                                      |
| Error tracker          | wired \| partial \| absent           | [...]                                      |

## Findings

### High Impact

#### [Must] file:line{ _(annotation)_}{ _(carried from round <N>)_}

- **Issue:** [Python idiom: missing `bind_contextvars` for request_id, unbounded `user_id` label, `Counter` constructed in a handler; an absent surface lists its missing pieces grouped by target file]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Python / OTel / structlog / prometheus-client change with code or config]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

## Recommendations

[Structural improvements not tied to a single finding - "structlog `JSONRenderer` in the prod profile"]

## SLI / SLO Suggestions   {deep only}

[Per critical journey: SLI, target, the metric or span that measures it, and the liveness / readiness split findings]

## Prior Round Reconciliation   {round 2+ only}

[reconcile's output verbatim]

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: ops] - [one-line action]
```

Empty sections are omitted; within a section `[Must]` first, then by `file:line`; group by surface when 3+ findings share one. `[Implement]` = a localized fix; `[Delegate]` = cross-cutting or platform work, `[scope: <owner>]` free text. Nothing found writes `No observability issues found.` under `## Findings`.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed Python; `Framework` and Python version taken from stack-detect or the manifest; `mixed` settled from the name-status
- [ ] Step 3: precondition called with `argument` / `base` / `report_type: review-observability`; SHAs captured; round gate decided before the diff was read (skipped on subagent runs)
- [ ] Step 4: surfaces read; Surface Map produced with `wired | partial | absent | n/a`; each `absent` surface collapsed to one finding
- [ ] Step 5: structured logging assessed - JSON, correlation, OTel record attributes, redaction, levels, parameterized form, no body logging, `exc_info`
- [ ] Step 6: OTel SDK and auto-instrumentation reviewed - framework / DB (`sync_engine`) / HTTP / Celery / Redis, explicit sampling, resource attributes
- [ ] Step 7: `prometheus-client` assessed - default + framework HTTP metrics, namespaced custom metrics, bounded cardinality, module-level registration, multi-process mode
- [ ] Step 8: Celery observability assessed - signals, per-task metrics, trace propagation, beat spans
- [ ] Step 9: async / lifespan assessed on FastAPI (skipped on Django)
- [ ] Step 10: error tracker assessed - framework integration, DSN externalized, PII scrubbed, OTel wiring, sample rate
- [ ] Step 11: at `deep`, SLIs / liveness / readiness / dependency-health separation reviewed; skipped otherwise
- [ ] Step 12: verify ran, `file:line` / `Label` / `Annotation` published, tally in Summary; round 2+ projected, reconciled, carried; report written with every writer field, or the gate stop line printed (all skipped on subagent runs)
- [ ] Findings name a Python / OTel / structlog / prometheus-client idiom, never "add observability"; infra concerns deferred to ops

## Avoid

- Prescribing an OTLP endpoint URL or Sentry DSN - say "sourced from env / Vault" and stop
- Recommending only structlog when the team uses stdlib `logging` - `python-json-logger` + `LoggingInstrumentor` is acceptable
