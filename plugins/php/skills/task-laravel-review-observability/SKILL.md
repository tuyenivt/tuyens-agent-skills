---
name: task-laravel-review-observability
description: Laravel observability review for `Monolog` + `Log::*` (structured channels, JSON formatter, processors, log levels), correlation IDs (request-id middleware, context binding), OpenTelemetry PHP SDK + Laravel auto-instrumentation, Horizon (Redis queue dashboard) + Telescope (development) gating, Laravel Pulse (production-safe metrics), Sentry / Bugsnag / Flare error tracking with `beforeSend` PII scrubbing, graceful queue worker shutdown, scheduled job overlap protection, and `php-fpm` slow-log / `opcache.log_verbosity_level` runtime introspection. Library-level focus, not infra. Stack-specific override of task-code-review-observability for PHP / Laravel.
agent: php-tech-lead
metadata:
  category: backend
  tags: [php, laravel, observability, monolog, opentelemetry, horizon, telescope, pulse, sentry, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Laravel Observability Review

## Purpose

Laravel-aware observability review that names `Monolog` (the `psr/log` implementation Laravel ships, configured via `config/logging.php` channels), `Log::*` (the facade) + `Log::channel(...)` for explicit channel use + `Log::withContext(...)` for correlation context, structured logging via `Monolog\Formatter\JsonFormatter` or Laravel 11+ JSON channel preset, request-id middleware (custom or `spatie/laravel-request-logger`), OpenTelemetry PHP SDK (`open-telemetry/sdk` + `open-telemetry/exporter-otlp` + `open-telemetry/contrib-auto-laravel` for auto-instrumentation of HTTP / Eloquent / queue / Redis), Laravel-shipped first-party tools (Horizon for Redis queue dashboard with auth Gate `viewHorizon`, Telescope for local dev with auth Gate `viewTelescope`, Pulse for production-safe metrics dashboard), error trackers (Sentry's `sentry/sentry-laravel`, Bugsnag, Flare/Ignition), graceful queue worker shutdown (`queue:work --max-time` / `--max-jobs` for predictable lifecycle, signal handling via `pcntl`), scheduled-command overlap protection (`->withoutOverlapping`, `->onOneServer`), and `php-fpm` slow-log + `opcache` introspection directly instead of routing through the generic adapter. Focuses on whether Laravel production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for PHP / Laravel. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a Laravel PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Laravel service or major feature
- Post-incident review when Laravel diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / structured logging / Pulse in a Laravel app
- Auditing queue / scheduled-job tracing and correlation across the request → job boundary

**Not for:**

- General Laravel code review (use `task-laravel-review`)
- Laravel performance issues with a known bottleneck (use `task-laravel-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single endpoint, controller, or job                          | Logging + metrics check only                       |
| `standard` | Default - full Laravel observability review                  | All steps                                          |
| `deep`     | Pre-release of a critical Laravel service, or post-incident review | All steps + SLI/SLO suggestions for Laravel endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                    | Meaning                                                                                                |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first  |
| `/task-laravel-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-observability` or `task-laravel-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 3 below is skipped.

## Severity Rubric

Use these definitions to keep `High` / `Medium` / `Low` Impact labels consistent across runs.

| Severity     | Definition                                                                                                                                                                                                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**     | Diagnosability cliff: the change makes production failures invisible or undebuggable - no structured logging in prod (text-only `single` driver, `dd()` left in a controller, `Log::info('user', ['user' => $user])` leaking `password` hash), Sentry / Bugsnag SDK in `require-dev` so it does not load in prod, Telescope unfiltered in prod (per-request overhead), Horizon / Pulse dashboards reachable without an auth Gate, OTel SDK installed but `contrib-auto-laravel` missing (no auto HTTP / Eloquent / queue spans), bare `queue:work` in prod supervisor (memory bloat), missing `/health` + `/ready` on a multi-replica deploy, missing `failed(Throwable $e)` on a job that mutates billing / payment state, webhook controller without log line on signature-verification failure (silent rejection of attacker probes). |
| **Medium**   | Observability gap with a partial mitigating control - missing request-id correlation when prod uses single-replica (still recoverable), `Log::info("user $id did thing")` string concat instead of PSR placeholder (loses structured field but message survives), missing OTel sampling config (defaults to always-on or always-off depending on SDK version), missing `Horizon` tags on jobs, missing `->withoutOverlapping()` on a scheduled command running every 15+ minutes, missing `before_send` PII scrubber in Sentry, missing `--max-time` on `queue:work` (workers do not bloat for hours, but eventually do).                                                                                                                          |
| **Low**      | Hardening / nice-to-have - missing `Model::preventLazyLoading()` in dev, missing slow-log config in non-prod, missing `php artisan view:cache` in deploy script, missing `php-fpm` slow-log threshold, missing OTel resource attributes (`service.version`, `deployment.environment`).                                                                                                                                                                                                                              |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step. When invoked as a subagent of `task-code-review-observability` or `task-laravel-review`, accept the parent's confirmation and skip re-loading.

### Step 2 - Confirm Stack and Detect Queue / Cache / Runtime Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If invoked as a subagent of a Laravel-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Laravel, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect queue connection (Redis with Horizon / database / sync / Beanstalkd / SQS), cache driver, runtime (PHP-FPM / Octane), and which dashboards are wired (Horizon, Telescope, Pulse). Each step branches on this signal where the instrumentation surface differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 4 - Read the Instrumentation Surface and Build the Surface Map

**The most important output of this step is a one-line answer per surface (logging / OTel SDK / Laravel dashboards / queue instrumentation / error tracker / lifecycle) of the form `wired | partial | absent`.** This produces the `Surface Map` table that appears in the Output Format. A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 5-10 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below) rather than one-per-bullet.

**Grouping rule.** When a whole surface is `absent` (no JSON formatter, no OTel SDK init, no error-tracker SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/class they should land in - not one finding per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. This prevents 50-item dumps on greenfield reviews.

**Verdict rubric.** Use these definitions consistently across the Surface Map and findings:

- `wired` = the channel / SDK / dashboard is registered AND the supporting wiring is present (correlation processors for logging, auto-instrumentations for OTel, auth Gate for Horizon / Telescope / Pulse, redaction policies for sensitive fields)
- `partial` = the channel / SDK / dashboard is registered BUT something material is missing or misused (`stack` log channel set to `single` text driver in prod; OTel SDK registered but Laravel auto-instrumentation missing; Horizon registered but `viewHorizon` Gate defaults to `app()->isLocal()` only on a multi-env app)
- `absent` = no registration anywhere in `config/logging.php` / `config/app.php` / `bootstrap/app.php` / providers / `composer.json` for the surface. Whole-surface grouping rule applies

Then open the files that actually configure observability so findings cite real lines, not assumptions:

- `config/logging.php` - channels (`stack`, `daily`, `slack`, `papertrail`, `syslog`, `errorlog`, `monolog`, `null`), formatter (default vs `JsonFormatter`), processors (PSR log message processor, request-id processor, custom redactor), level
- `config/app.php` - timezone, locale, providers; legacy app.debug check still relevant
- `bootstrap/app.php` (Laravel 11+) - middleware registration order; exception handler config (`withExceptions(...)` for custom `report` / `render` rules)
- `app/Providers/AppServiceProvider.php` - `Log::context(...)`, `Schedule::*` global registrations, container bindings for telemetry
- `composer.json` / `composer.lock` - confirm `sentry/sentry-laravel`, `open-telemetry/sdk`, `open-telemetry/contrib-auto-laravel`, `open-telemetry/exporter-otlp`, `laravel/horizon`, `laravel/telescope`, `laravel/pulse` presence and versions
- Every changed file in the diff that calls `Log::*`, registers metrics (Pulse cards, custom Prometheus exporter), defines middleware, opens spans via OTel `Tracer`, or modifies request context
- Every changed migration in `database/migrations/` - new business columns (status, audit, ownership, lifecycle state) imply business events that should drive a metric / span attribute / log property. A schema change with no corresponding observability change is itself a gap; flag as a Medium finding (`Schema change without instrumentation`)

For diffs touching only one of these surfaces (a new endpoint but no logging change, say), still read the existing config to know whether request-id / trace correlation, instrumentation, and SDKs are wired - a missing wire is the finding.

### Step 5 - Structured Logging (`Monolog` / `Log::*`)

Inspect logging config and any `Log::*` callsite in the diff:

- [ ] **Production logger emits JSON**: `config/logging.php` channel uses `Monolog\Formatter\JsonFormatter` (or Laravel 11+ JSON formatter preset) - text logs in prod are unparseable by aggregators (Loki, ELK, Datadog Logs). For multi-handler setups, `stack` channel composing `daily` (file rotation) + structured handler. The `single` driver is a foot-gun in prod (one big growing file)
- [ ] **No `dd()` / `dump()` / `var_dump()` / `print_r()` in production code paths**: `dd()` halts the request and dumps to the response - data leak in prod, also kills the request. Flag for replacement with `Log::*` or removal
- [ ] **Correlation fields injected** in every log line: `request_id`, `user_id` (when authenticated), `tenant_id`, plus business correlation IDs (`order_id`, `invoice_id`). Wire via:
  - Custom middleware that generates a `request_id` (UUID) on each request and binds via `Log::withContext(['request_id' => $id])` (Laravel's per-request context that all subsequent `Log::*` calls inherit)
  - Custom Monolog processor (`Monolog\Processor\PsrLogMessageProcessor` for placeholder interpolation; custom processor for adding request-scoped context to every record)
  - Spatie's `spatie/laravel-request-logger` or `cesargb/laravel-magic-make` for ready-made request-id processors
- [ ] **OpenTelemetry log correlation**: with the OpenTelemetry PHP SDK active, the active span's `trace_id` / `span_id` should attach to every log entry. The auto-instrumentation package (`open-telemetry/contrib-auto-laravel`) registers a Monolog processor that injects these. Flag missing OTel-Monolog wiring when the OTel SDK is present
- [ ] **Greenfield correlation (when OTel SDK is `absent`)**: do not recommend OTel-derived `trace_id` correlation as the fix when OTel itself isn't wired - that's a separate work item. The minimum correlation story without OTel is a request-id middleware + `Log::withContext(['request_id' => $id])` at request start. Recommend wiring OTel as a follow-up rather than blocking on it - the in-process correlation gap is fixable today
- [ ] **Sensitive-field redaction**: a custom Monolog processor that drops `password`, `token`, `Authorization`, `Cookie`, `credit_card`, `ssn`, `api_key` keys from every record's context array; OR types implement custom `__toString()` / `JsonSerializable::jsonSerialize()` to return a redacted form. Spatie's `laravel-personal-data-export` or `henzeb/laravel-monolog-tap` for processor wiring
- [ ] **No `Log::info('user', ['user' => $user])` that destructures a model**: Eloquent models JSON-serialize via `__toString()` to all non-`$hidden` fields - leaks every column. Always log specific fields: `Log::info('Processing order', ['order_id' => $order->id, 'user_id' => $order->user_id])`
- [ ] **PSR placeholder syntax used**: `Log::info('Processing order {order_id}', ['order_id' => $id])` lets the PSR log message processor format the message while preserving the structured `order_id` field. String concatenation `Log::info("Processing order $id")` (or `"... " . $id`) loses the structured field - the aggregator can't field-extract `$id`
- [ ] **Log levels used correctly**: `Log::error` for actionable failures, `Log::warning` for recoverable anomalies, `Log::info` for state transitions, `Log::debug` for verbose diagnostics. Default `LOG_LEVEL=info` in prod (set via `.env`). Default `Log::channel('daily')` for fallback file logging
- [ ] **No log spam in hot loops** - iterating large lists, scheduled jobs running every minute, queue workers at high throughput must not log per-iteration; sample or use `Log::debug`
- [ ] **Error logging includes the exception**: `Log::error('Failed to load order', ['order_id' => $id, 'exception' => $e])` - the `'exception' => $e` array key triggers Monolog's exception introspection (full stack trace, previous chain). Bare `Log::error($e->getMessage())` loses the inner-exception chain and stack trace
- [ ] **Exception handler logs unhandled exceptions**: `bootstrap/app.php` `withExceptions(fn ($exceptions) => $exceptions->report(fn (Throwable $e) => Log::error($e)))` (or Laravel's default exception reporter, which logs via the configured `Log` channel)
- [ ] **Webhook controllers log signature-verification failures**: when the diff adds a webhook endpoint (Stripe, GitHub, Slack, Twilio), every signature-mismatch path must `Log::warning('webhook signature verification failed', [...])` before returning 4xx. Silent rejection makes attacker probing invisible to ops; success-only logging means a flood of 401s shows as zero events. Same for replay-window rejections and idempotency-collision rejections

### Step 6 - OpenTelemetry SDK and Auto-Instrumentation

Inspect OpenTelemetry config and instrumentation wiring:

- [ ] **OpenTelemetry PHP SDK installed**: `composer.json` requires `open-telemetry/sdk`, `open-telemetry/exporter-otlp`, AND `open-telemetry/contrib-auto-laravel` for Laravel auto-instrumentation. Without `contrib-auto-laravel`, manual span instrumentation is needed for HTTP / Eloquent / queue / cache - a maintenance burden the auto-instrumentation removes
- [ ] **OTel SDK initialized in a service provider's `register` method**, not in `boot` - service providers' `register` runs before bindings resolve, so the SDK is ready when other providers boot and may emit spans
- [ ] **OTLP exporter configured**: `OTEL_EXPORTER_OTLP_ENDPOINT` env var (gRPC default port 4317, HTTP default 4318); `OTEL_SERVICE_NAME=acme-api`; `OTEL_RESOURCE_ATTRIBUTES=service.version=$VERSION,deployment.environment=$ENV`
- [ ] **Resource attributes** populated: `service.name`, `service.version`, `deployment.environment`; sourced from build metadata / env vars (read once at SDK init, not per request)
- [ ] **Sampling policy explicit**: `OTEL_TRACES_SAMPLER=parentbased_traceidratio` with `OTEL_TRACES_SAMPLER_ARG=0.1` (10% in prod) or `1.0` in staging; not always-on in high-traffic prod
- [ ] **HTTP server auto-instrumentation**: `contrib-auto-laravel` registers middleware that creates a span per request with route, method, status, duration; flag missing package
- [ ] **Eloquent / DB auto-instrumentation**: `contrib-auto-laravel` includes DB query spans via `DB::listen` hook; flag if disabled
- [ ] **Outbound HTTP instrumentation**: Guzzle handler stack auto-wraps with traceparent injection via the contrib package; flag if a separate Guzzle client (constructed manually) bypasses the handler stack
- [ ] **Queue auto-instrumentation**: queue spans (job dispatch as producer span, job execution as consumer span) link via `traceparent` payload; the contrib package handles this, but flag any custom job dispatch path that strips context
- [ ] **Custom span attributes**: business-relevant attributes attached to current span via `Span::current()->setAttribute('order.id', $orderId)`; keep cardinality bounded (no PII, no IDs that explode metric label space if exposed as metric tags too)
- [ ] **Span error status on exception paths**: `try { ... } catch (Throwable $e) { Span::current()->recordException($e)->setStatus(StatusCode::STATUS_ERROR, $e->getMessage()); throw $e; }` - propagates exception to the span
- [ ] **Graceful flush on shutdown**: `Tracer::shutdown()` (or auto via SDK's registered shutdown handler) so in-flight spans flush before the worker exits

### Step 7 - Laravel-Shipped Dashboards (Horizon / Telescope / Pulse)

Inspect dashboard wiring:

- [ ] **Horizon (Redis queues)**: `composer.json` requires `laravel/horizon`; `config/horizon.php` has supervisor configs; `routes/web.php` registers Horizon's UI; **`viewHorizon` Gate** defined in `AppServiceProvider::boot` to control access (`Gate::define('viewHorizon', fn ($user) => $user->is_admin)`). Default Horizon config restricts to `app()->isLocal()` only - flag if production access is needed but not gated, OR if `viewHorizon` opens to authenticated users without role check
- [ ] **Telescope (development only)**: `composer.json` requires `laravel/telescope` in `require-dev` (or with `Telescope::filter(...)` sampling if in prod). `Telescope::filter(fn (IncomingEntry $entry) => $entry->isReportableException() || $entry->isFailedJob() || $entry->isSlowQuery() || ...)` for prod sampling. Always gated by `viewTelescope` Gate. Flag Telescope unfiltered in prod (significant per-request overhead)
- [ ] **Pulse (production metrics)**: `composer.json` requires `laravel/pulse`; `config/pulse.php` defines recorders (slow queries, user requests, exceptions, cache hit rate); routes registered; **`viewPulse` Gate** defined. Pulse is designed to be production-safe (~1ms per request) - prefer it over Telescope for prod observability
- [ ] **Pulse custom recorders**: when domain events should be captured as metrics, register a recorder in `config/pulse.php` `recorders` array; recorders write to the Pulse storage and surface as cards
- [ ] **Pulse cards in dashboard**: `app/Pulse/Cards/*.php` extending `Pulse::card(...)` for custom dashboards
- [ ] **`composer.json` `require-dev` placement**: Telescope in `require-dev` (don't ship to prod by default); Horizon and Pulse in `require` (production-safe)

### Step 8 - Queue Worker / Scheduled Job Observability

_Skipped at `quick` depth unless the diff touches background workers or scheduled commands._

- [ ] **Queue worker tracing**: each job execution emits a span via `contrib-auto-laravel`; the dispatching request's traceparent propagates through the queue payload. Flag missing OTel queue auto-instrumentation
- [ ] **Per-job logging context**: `Log::withContext(['job_id' => $job->getJobId(), 'job_class' => get_class($this)])` at job start (in `handle()` or via a job middleware) so every log line within the job carries the binding
- [ ] **Failed-job notification**: `failed(Throwable $e)` method on every job calls `Log::error(...)` with full context AND optionally notifies (Slack via `Notification::route(...)->notify(...)`)
- [ ] **Horizon tags on jobs**: `public function tags(): array { return ['order:'.$this->orderId]; }` for Horizon's tag-based job filtering - lets ops query Horizon for "all jobs touching order N"
- [ ] **Pulse / Horizon dashboards monitor queue depth**: queue depth alarm thresholds defined in alerting; Horizon's metrics drive supervisors auto-scaling
- [ ] **Scheduled command instrumentation**: `Schedule::command('reports:weekly')->weekly()->onSuccess(fn () => Log::info(...))->onFailure(fn () => Log::error(...))` - explicit success/failure logging beats relying on the scheduler's default
- [ ] **`->withoutOverlapping()` on long-running scheduled commands**: tag-based cache lock prevents two instances from running concurrently when the previous tick's command hasn't finished
- [ ] **`->onOneServer()` on multi-replica deploys**: prevents N replicas from each running the same scheduled command per tick
- [ ] **`->runInBackground()` on long-running scheduled commands**: keeps the scheduler tick from blocking on a 5-minute job
- [ ] **Bare-loop workers have minimum signal**: a job with zero logging, zero metric, and no try/catch around `handle()` produces no signal when it silently fails. On greenfield jobs (no instrumentation present), require at minimum: one `Log::info('Job started', [...])` at handle entry with the business key being processed, an outer `try { ... } catch (Throwable $e) { Log::error($e); throw $e; }` so the worker remains observable even when not yet OTel-instrumented, and a `failed(Throwable $e)` method so DLQ-bound jobs are visible

### Step 9 - Lifecycle / Graceful Shutdown Observability

_Skipped at `quick` depth unless the diff touches lifecycle (queue worker config, signal handling, deploy scripts) or `bootstrap/app.php`. The Greenfield exception above also applies to this step._

- [ ] **`queue:work --max-time=N --max-jobs=N`** for predictable worker lifecycle: workers exit after N seconds or N jobs, supervisor restarts them. Fresh workers prevent memory bloat from long-running PHP processes (especially with Eloquent's static identity cache). Flag bare `queue:work` in prod supervisor config
- [ ] **`pcntl` extension installed**: required for graceful SIGTERM handling in `queue:work`; without it, signals are queued and only processed after the current job finishes - which is fine, but flag if signal handling is custom and `pcntl` is missing
- [ ] **`queue:restart` invoked on deploy**: the deploy pipeline calls `php artisan queue:restart` after `composer install` so workers running pre-deploy code shut down cleanly and supervisor starts new workers with the new code. Without this, workers run stale code until they hit `--max-time`. Flag missing call in deploy script
- [ ] **Horizon graceful shutdown**: `php artisan horizon:terminate` for graceful drain (vs `horizon:purge` which kills); deploy pipeline uses `terminate`
- [ ] **Octane shutdown**: Octane workers persist state between requests; deploys need `php artisan octane:reload` to swap to new code without dropping connections
- [ ] **OTel `Tracer::shutdown()` on worker exit**: handled by the SDK's shutdown handler when registered correctly; confirm not bypassing
- [ ] **Health check endpoints - three-way distinction**: keep liveness, readiness, and dependency-health separate.
  - **`GET /health` (liveness)**: returns 200 if the process is up. Must NOT fail on a downstream blip - Kubernetes restarts the pod on liveness failure, so a flaky DB takes down every replica simultaneously. No DB / Redis / external checks here
  - **`GET /ready` (readiness)**: returns 503 when *this pod* cannot serve traffic right now (own DB pool exhausted, own Redis disconnected, in-flight migrations, lifecycle draining). Pod is removed from the load balancer until it returns 200 again. Should NOT include third-party API health (e.g., Stripe ping) - if every replica fails readiness because Stripe is down, the entire service goes offline even though most requests don't touch Stripe. Including downstream-API ping in `/ready` is an outage amplifier
  - **Dependency-health endpoint** (`/health/dependencies` or a Pulse card): observability metric, not a Kubernetes pod-removal signal. Reports DB / Redis / Stripe / etc. status for dashboards and alerts; a failing dependency here pages on-call but does not pull pods from rotation
  - Multi-replica deployments without `/health` + `/ready` cannot do safe rolling restarts - load balancers cannot tell DB-down from worker-stuck from process-alive. Flag at any depth on multi-replica services. Use `spatie/laravel-health` for ready-made checks but verify the wiring: liveness must NOT include the same checks readiness uses, and readiness must NOT include third-party-API checks
- [ ] **`php-fpm` slow-log enabled in non-prod / sampled in prod**: `php-fpm.conf` `slowlog = /var/log/fpm-slow.log` and `request_slowlog_timeout = 5s` log requests taking longer than 5s along with their PHP backtrace - invaluable for diagnosing slow paths. Flag missing config

### Step 10 - Error Tracking (Sentry / Bugsnag / Flare)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/connection-string handling._

Inspect SDK config:

- [ ] **SDK installed and initialized** (Sentry): `composer require sentry/sentry-laravel`; `config/sentry.php` published; `bootstrap/app.php` (Laravel 11+) `withExceptions(fn ($e) => $e->reportable(...))` integrates Sentry, OR Laravel auto-discovery of the Sentry service provider handles it. Bugsnag: `bugsnag/bugsnag-laravel`. Flare: `spatie/laravel-ignition` (free, replaces Whoops in dev; `flareapp.io` paid for prod)
- [ ] **DSN** in env var (`SENTRY_LARAVEL_DSN`), not committed
- [ ] **Release / environment tags** populated from build metadata: `SENTRY_RELEASE` (commit SHA) and `SENTRY_ENVIRONMENT` (env var)
- [ ] **PII scrubbing on**: `config/sentry.php` `send_default_pii => false` (default but flag if explicitly `true`); `before_send` callback strips known sensitive keys from `$event->getRequest()` (request body, cookies, headers); allowlist of breadcrumb fields documented
- [ ] **`Log::*` integration**: Sentry's Laravel integration captures `Log::error` / `Log::critical` automatically; flag missing config for capturing log entries as Sentry events
- [ ] **OpenTelemetry / trace correlation forwarded**: error event includes `trace_id` and `user_id` so incidents link back to traces / users; the Sentry Laravel SDK extracts trace context when an active OTel span is present
- [ ] **Sample rate explicit**: `SENTRY_TRACES_SAMPLE_RATE=0.1` per env; not `1.0` in prod for performance traces
- [ ] **Ignored errors documented**: domain exceptions that should not page (e.g., `ModelNotFoundException` 404s, `ValidationException` 422s) filtered via `before_send` or `ignore_exceptions` config; each ignore has a comment justifying it
- [ ] **Queue worker exception capture**: queue jobs route exceptions through Laravel's exception handler, which Sentry hooks; confirm not bypassing
- [ ] **No SDK in `require-dev`**: the SDK must be in `require` so it loads in production. Bugsnag / Sentry / Flare in `require-dev` is a common deploy bug; flag


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation (or accepted from parent dispatcher)
- [ ] Stack confirmed as PHP / Laravel (or accepted from parent dispatcher); queue / cache / runtime recorded (Step 2)
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); diff and commit log read once and reused by all steps (Step 3)
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent) (Step 3)
- [ ] Instrumentation surfaces (config/logging.php, OTel config, dashboards, settings, packages, changed call sites) read directly before applying checklists; Surface Map produced with `wired / partial / absent` per row using the verdict rubric (Step 4)
- [ ] Structured logging assessed: JSON formatter, request-id correlation, sensitive-field redaction, log level discipline, no `dd` / `dump` / `print_r` in prod paths, PSR placeholders not string interpolation, exception logged as object not message string, webhook signature-failure paths logged (Step 5)
- [ ] OpenTelemetry SDK and auto-instrumentation reviewed: `contrib-auto-laravel` installed, SDK initialized in service provider register, sampling explicit, resource attributes populated, custom span attributes within cardinality budget (Step 6)
- [ ] Laravel dashboards assessed: Horizon Gate, Telescope filtering / dev-only, Pulse recorders + Gate; Telescope NOT unfiltered in prod (Step 7)
- [ ] Queue / scheduled job observability assessed: per-job context, failed() handler, Horizon tags, scheduled command success/failure handlers, `withoutOverlapping` / `onOneServer` / `runInBackground` for multi-replica (Step 8)
- [ ] Lifecycle / graceful shutdown assessed: `queue:work --max-time` / `--max-jobs`, `queue:restart` on deploy, Horizon `terminate`, Octane `reload`, OTel shutdown, health endpoints (`/health` / `/ready`), php-fpm slow-log (Step 9)
- [ ] Error tracker integration assessed: SDK in `require` (not `require-dev`), DSN externalized, PII scrubbed, OTel correlation forwarded, sample rate explicit (Step 10)
- [ ] Severity rubric applied consistently (High / Medium / Low matches the rubric, not invented)
- [ ] Findings name a Laravel / Monolog / OTel / Pulse idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/queue/lifecycle/error-tracker steps unless diff signals required them; `deep` ran the SLI step
- [ ] Greenfield grouping rule applied: when a whole surface is `absent`, findings collapsed into one High finding per surface (not one per missing checkbox)
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Laravel Observability Review Summary

**Stack Detected:** PHP <version> / Laravel <version>
**Queue:** redis (Horizon) | database | sync
**Cache:** redis | memcached | database | file
**Runtime:** PHP-FPM | Octane (Swoole) | Octane (RoadRunner) | FrankenPHP
**Logging:** Monolog (JSON) | Monolog (text) | absent
**Metrics:** Pulse | custom Prometheus | absent
**Tracing:** OpenTelemetry (contrib-auto-laravel + OTLP) | OpenTelemetry (manual) | absent
**Dashboards:** Horizon (gated) | Telescope (dev-only / sampled) | Pulse (gated) | absent
**Error Tracker:** Sentry (sentry-laravel) | Bugsnag | Flare/Ignition | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

| Surface                  | Verdict                  | Evidence                                       |
| ------------------------ | ------------------------ | ---------------------------------------------- |
| Structured logging       | wired / partial / absent | [file:line or "no logging config in repo"]    |
| OpenTelemetry SDK        | wired / partial / absent | [...]                                          |
| Laravel dashboards       | wired / partial / absent | [Horizon / Telescope / Pulse status]          |
| Queue instrumentation    | wired / partial / absent | [...]                                          |
| Lifecycle / health       | wired / partial / absent | [...]                                          |
| Error tracker            | wired / partial / absent | [...]                                          |

> Use **Greenfield** as the `Overall:` headline when 3+ of the rows above are `absent` - it tells the reader the review is scaffolding, not auditing, and changes how they prioritize. Use the same `absent` vocabulary throughout (do not mix `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Laravel idiom: missing JSON formatter on prod log channel, `dd()` left in production controller, `Log::info('user', ['user' => $user])` destructuring an Eloquent model (leaks `password` hash), Telescope unfiltered in prod, Horizon dashboard reachable without `viewHorizon` Gate in prod, OTel SDK installed but `contrib-auto-laravel` missing (no auto HTTP / Eloquent / queue spans), Sentry SDK in `require-dev` (won't load in prod), missing `--max-time` on `queue:work` causing memory bloat, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Laravel / Monolog / OTel / Pulse change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Logging / Tracing / Dashboards / Queue / Lifecycle / Error Tracker) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 4 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Add a request-id middleware that calls `Log::withContext(['request_id' => Str::uuid()])`", "Install `open-telemetry/contrib-auto-laravel` for HTTP / Eloquent / queue / Redis auto-instrumentation", "Switch from Telescope-in-prod to Pulse for production-safe metrics with custom recorders", "Move Sentry SDK from `require-dev` to `require`; add `before_send` PII scrubber", "Add `queue:restart` to deploy script after `composer install`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Set `LOG_CHANNEL=stack` and configure JSON formatter on `daily` channel in config/logging.php"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/metrics` Pulse endpoint to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Laravel / Monolog / OTel / Pulse idiom ("add metrics" vs "register a Pulse recorder in `config/pulse.php` `recorders` array and add a custom card under `app/Pulse/Cards/`")
- Recommending generic observability advice when a Laravel package or auto-instrumentation exists (say "install `open-telemetry/contrib-auto-laravel`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high tag cardinality (`user_id`, `order_id`) as acceptable on metrics - require enum / category tags
- Approving string-concat logging (`Log::info("user $id did thing")`) over PSR placeholder form (`Log::info('user {user_id} did thing', ['user_id' => $id])`)
- Approving `dd()` / `dump()` / `print_r()` in production code paths
- Approving `Log::info(...)` that destructures an Eloquent model into context array - leaks every column not in `$hidden`; log specific fields by id
- Approving Telescope unfiltered in production - significant per-request overhead
- Approving Horizon / Pulse dashboards reachable without auth Gate in non-local environments
- Approving Sentry / Bugsnag SDK in `require-dev` (won't load in prod)
- Approving OTel SDK initialization without `contrib-auto-laravel` package - manual span instrumentation per HTTP / DB / queue site is a maintenance burden the auto-instrumentation removes
- Prescribing the OTLP endpoint URL or the Sentry DSN value - say "sourced from env / Vault" and stop
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 4's grouping rule
- Approving bare `queue:work` in production supervisor without `--max-time` / `--max-jobs` - memory bloat from long-running PHP processes
- Approving `Log::error($e->getMessage())` over `Log::error('something failed', ['exception' => $e])` - bare message loses the inner-exception chain and stack
