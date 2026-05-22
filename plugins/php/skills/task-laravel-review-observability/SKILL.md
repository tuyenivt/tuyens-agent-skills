---
name: task-laravel-review-observability
description: Laravel observability review: Monolog structured logs, correlation IDs, OpenTelemetry PHP, Horizon, Telescope, Pulse, Sentry/Bugsnag PII scrubbing.
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

Laravel-aware observability review at the library/SDK level: Monolog channels, OpenTelemetry PHP SDK + `contrib-auto-laravel`, Horizon/Telescope/Pulse, Sentry/Bugsnag, queue worker lifecycle, `php-fpm` slow-log. Stack-specific delegate of `task-code-review-observability` (preserves depth levels and output format). Infra-level concerns (Datadog, Sentry org settings, log forwarder config) stay out of scope.

## When to Use

- Laravel PR review for observability regressions or new instrumentation gaps
- Pre-release check for a new Laravel service or major feature
- Post-incident review when Laravel diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / structured logging / Pulse, or auditing queue/scheduled-job tracing across the request -> job boundary

**Not for:** general Laravel code review (`task-laravel-review`); known perf bottleneck (`task-laravel-review-perf`); active incident (`/task-oncall-start`); infra-level (Datadog/Grafana/alert rules/log forwarder).

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

| Severity   | Definition                                                                                                                                                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | Diagnosability cliff: prod failures invisible or undebuggable. Examples: text-only `single` channel in prod, `dd()` in a controller, model destructured into log context (leaks `password`), Sentry/Bugsnag in `require-dev`, Telescope unfiltered in prod, Horizon/Pulse reachable without auth Gate, OTel SDK without `contrib-auto-laravel`, bare `queue:work` in prod, missing `/health`+`/ready` on multi-replica, missing `failed()` on billing job, webhook signature failure unlogged. |
| **Medium** | Observability gap with partial mitigation. Examples: missing request-id correlation, string-concat logging losing structured fields, missing OTel sampling config, missing Horizon job tags, missing `->withoutOverlapping()` on 15+ min schedule, missing Sentry `before_send` PII scrubber, missing `--max-time` on `queue:work`.                                  |
| **Low**    | Hardening / nice-to-have. Examples: missing `Model::preventLazyLoading()` in dev, missing `php-fpm` slow-log threshold, missing OTel resource attributes (`service.version`, `deployment.environment`), missing `view:cache` in deploy.                                                                                                                              |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. When invoked as a subagent of `task-code-review-observability` or `task-laravel-review`, accept the parent's confirmation and skip re-loading.

### Step 2 - Confirm Stack and Detect Runtime Surface

Use skill: `stack-detect` to confirm PHP / Laravel (accept pre-confirmed stack from a Laravel-aware parent). If the stack is not Laravel, stop and direct the user to `/task-code-review-observability`.

Detect queue connection (Redis+Horizon / database / sync / Beanstalkd / SQS), cache driver, runtime (PHP-FPM / Octane), and wired dashboards (Horizon, Telescope, Pulse). Subsequent steps branch on this signal.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (default: current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`; reuse for all subsequent steps. Skip entirely if running as a subagent with parent-provided artifacts.

If `review-precondition-check` stops with a fail-fast message, surface it verbatim and stop. Do not run any state-changing git command.

### Step 4 - Read the Instrumentation Surface and Build the Surface Map

**Primary output: a `wired | partial | absent` verdict per surface (logging / OTel SDK / Laravel dashboards / queue / error tracker / lifecycle).** This produces the `Surface Map` table. A missing wire is itself the finding. When `absent`, Steps 5-10 shift from "audit existing wiring" to "scaffold at the changed call sites".

**Verdict rubric.**

- `wired` = registered AND supporting wiring present (correlation processors, auto-instrumentations, auth Gates, redaction)
- `partial` = registered BUT something material missing (e.g., `stack` channel using `single` text driver in prod; OTel SDK without `contrib-auto-laravel`; `viewHorizon` Gate defaulting to `app()->isLocal()` on a multi-env app)
- `absent` = no registration in `config/logging.php` / `bootstrap/app.php` / providers / `composer.json`. Grouping rule applies

**Grouping rule.** When a surface is `absent`, produce **a single High-Impact finding for that surface** listing missing pieces grouped by target file/class - not one per sub-bullet. Per-callsite findings only apply when the surface exists and a specific callsite misuses it. Prevents 50-item dumps on greenfield reviews.

Read files that configure observability so findings cite real lines:

- `config/logging.php` - channels, formatter (default vs `JsonFormatter`), processors, level
- `bootstrap/app.php` (Laravel 11+) - middleware order; exception handler (`withExceptions(...)`)
- `app/Providers/AppServiceProvider.php` - `Log::context(...)`, schedule, telemetry bindings
- `composer.json` / `composer.lock` - versions of `sentry/sentry-laravel`, `open-telemetry/{sdk,exporter-otlp,contrib-auto-laravel}`, `laravel/{horizon,telescope,pulse}`
- Changed files calling `Log::*`, registering metrics, defining middleware, opening OTel spans, or modifying request context
- Changed `database/migrations/` - new business columns (status, audit, ownership, lifecycle) imply events that should drive a metric/span/log. Schema change without observability is a Medium finding (`Schema change without instrumentation`)

For diffs touching only one surface, still read existing config - a missing wire is the finding.

### Step 5 - Structured Logging (Monolog / `Log::*`)

- [ ] **Prod logger emits JSON**: `config/logging.php` channel uses `Monolog\Formatter\JsonFormatter` (or Laravel 11+ JSON preset). Text is unparseable by aggregators; `single` driver is a foot-gun (unrotated growing file)
- [ ] **No `dd()` / `dump()` / `var_dump()` / `print_r()` in prod paths** - halts the request, leaks data
- [ ] **Correlation context bound per request**: `request_id`, `user_id`, `tenant_id`, business IDs (`order_id`, `invoice_id`) via middleware calling `Log::withContext([...])` and a Monolog processor (`PsrLogMessageProcessor` + request-context processor), or `spatie/laravel-request-logger`
- [ ] **OTel log correlation when SDK present**: active span's `trace_id`/`span_id` attached via `contrib-auto-laravel` Monolog processor (flag missing wiring). **Greenfield (OTel `absent`)**: do not block on `trace_id`; minimum viable is request-id middleware + `Log::withContext(['request_id' => $id])`, OTel is follow-up
- [ ] **Sensitive-field redaction**: Monolog processor drops `password`, `token`, `Authorization`, `Cookie`, `credit_card`, `ssn`, `api_key` from every context
- [ ] **Log specific fields, never the model**: `Log::info('user', ['user' => $user])` serializes every non-`$hidden` column (leaks `password` hash). Use `['order_id' => $order->id, 'user_id' => $order->user_id]`
- [ ] **PSR placeholder syntax**: `Log::info('Processing order {order_id}', ['order_id' => $id])`. String concat loses the structured field
- [ ] **Log-level discipline + `LOG_LEVEL=info` in prod**; no per-iteration logging in hot loops or high-throughput workers (sample or use `debug`)
- [ ] **Exceptions as objects + unhandled exceptions reported**: `Log::error('Failed', ['order_id' => $id, 'exception' => $e])` - the `exception` key triggers Monolog introspection (stack trace + previous chain). Bare `Log::error($e->getMessage())` drops both. Reporter wired via `bootstrap/app.php` `withExceptions(...)` or Laravel default
- [ ] **Webhook signature failures logged**: every signature/replay/idempotency rejection (Stripe/GitHub/Slack/Twilio) calls `Log::warning(...)` before returning 4xx - silent rejection hides attacker probing

### Step 6 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK + auto-instrumentation installed**: `open-telemetry/sdk`, `open-telemetry/exporter-otlp`, AND `open-telemetry/contrib-auto-laravel`. Without `contrib-auto-laravel`, every HTTP/Eloquent/queue/cache span is manual
- [ ] **SDK initialized in a provider's `register` method**, not `boot` - ready when other providers boot
- [ ] **Exporter + resource attributes from env**: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES=service.version=$VERSION,deployment.environment=$ENV`; explicit sampling (`OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1` in prod)
- [ ] **Auto-instrumentation surfaces verified**: HTTP server (request span with route/method/status), Eloquent (via `DB::listen`), outbound Guzzle (handler stack with traceparent - flag manually constructed clients that bypass), queue (producer/consumer linked via `traceparent` payload - flag custom dispatch paths that strip context)
- [ ] **Custom span attributes within cardinality budget**: `Span::current()->setAttribute('order.id', $orderId)`; no PII, no IDs reused as metric labels
- [ ] **Span error status on exception paths**: `catch (Throwable $e) { Span::current()->recordException($e)->setStatus(StatusCode::STATUS_ERROR, $e->getMessage()); throw $e; }`
- [ ] **Graceful flush on shutdown** via SDK's registered shutdown handler (or explicit `Tracer::shutdown()`)

### Step 7 - Laravel-Shipped Dashboards (Horizon / Telescope / Pulse)

- [ ] **Horizon**: `laravel/horizon` in `require`; `config/horizon.php` supervisors; **`viewHorizon` Gate** in `AppServiceProvider::boot` (not default `app()->isLocal()` on multi-env apps; not open to authenticated users without role check)
- [ ] **Telescope**: in `require-dev`, or in `require` only with `Telescope::filter(fn (IncomingEntry $e) => $e->isReportableException() || $e->isFailedJob() || $e->isSlowQuery())` sampling. Always gated by `viewTelescope`. Flag unfiltered in prod (significant per-request overhead)
- [ ] **Pulse**: `laravel/pulse` in `require`; `config/pulse.php` recorders (slow queries, requests, exceptions, cache hit rate); **`viewPulse` Gate**. Production-safe (~1ms/req) - prefer over Telescope for prod metrics. Custom recorders/cards for domain events under `app/Pulse/Cards/`

### Step 8 - Queue Worker / Scheduled Job Observability

_Skipped at `quick` depth unless the diff touches background workers or scheduled commands._

- [ ] **Queue tracing via `contrib-auto-laravel`**: producer/consumer spans linked through queue-payload traceparent. Flag missing
- [ ] **Per-job context**: `Log::withContext(['job_id' => $job->getJobId(), 'job_class' => static::class])` at `handle()` entry (or via job middleware)
- [ ] **`failed(Throwable $e)` on every job** (`Log::error(...)` + optional notification); **Horizon tags** for tag-filtered search: `public function tags(): array { return ['order:'.$this->orderId]; }`
- [ ] **Scheduled commands**: `Schedule::command(...)->onSuccess(...)->onFailure(...)`; `->withoutOverlapping()` at 15+ min interval; `->onOneServer()` on multi-replica; `->runInBackground()` on long jobs
- [ ] **Greenfield job minimum (zero instrumentation)**: one `Log::info(...)` at handle entry with business key, outer `try { ... } catch (Throwable $e) { Log::error($e); throw $e; }`, and a `failed()` method

### Step 9 - Lifecycle / Graceful Shutdown Observability

_Skipped at `quick` depth unless the diff touches lifecycle, signal handling, deploy scripts, or `bootstrap/app.php`. Greenfield grouping rule from Step 4 also applies here._

- [ ] **`queue:work --max-time=N --max-jobs=N`** in prod supervisor (prevents memory bloat, especially Eloquent's static identity cache); `pcntl` installed for graceful SIGTERM. Flag bare `queue:work`
- [ ] **Deploy pipeline calls `php artisan queue:restart`** after `composer install` (otherwise workers run stale code until `--max-time`); `horizon:terminate` (graceful drain, not `horizon:purge`) on Horizon; `octane:reload` on Octane
- [ ] **OTel `Tracer::shutdown()` on worker exit** (handled by SDK shutdown handler when registered correctly)
- [ ] **Health endpoints - three-way distinction (multi-replica without `/health`+`/ready` can't do safe rolling restarts)**:
  - **`/health` (liveness)**: 200 if process is up. NO DB/Redis/external checks - K8s restarts on liveness failure, so a flaky DB downs every replica
  - **`/ready` (readiness)**: 503 when *this pod* can't serve (own DB pool exhausted, own Redis disconnected, in-flight migrations, draining). NO third-party API ping - if every replica fails readiness because Stripe is down, the whole service goes offline (outage amplifier)
  - **Dependency-health** (`/health/dependencies` or a Pulse card): observability surface, not a pod-removal signal. Failures page on-call but don't pull pods
  - `spatie/laravel-health` is fine but verify liveness doesn't reuse readiness checks and readiness excludes third-party APIs
- [ ] **`php-fpm` slow-log enabled** (non-prod, sampled in prod): `slowlog = /var/log/fpm-slow.log` + `request_slowlog_timeout = 5s` captures backtrace for slow paths

### Step 10 - Error Tracking (Sentry / Bugsnag / Flare)

_Skipped at `quick` depth unless the diff modifies error handlers, error-tracker config, or DSN/connection-string handling._

- [ ] **SDK in `require` (not `require-dev`)** - common deploy bug. Sentry: `sentry/sentry-laravel` auto-discovered or wired via `bootstrap/app.php` `withExceptions(...)`. Bugsnag: `bugsnag/bugsnag-laravel`. Flare: `spatie/laravel-ignition`
- [ ] **DSN externalized** (`SENTRY_LARAVEL_DSN`); **release + environment tags** from build metadata (`SENTRY_RELEASE`=commit SHA, `SENTRY_ENVIRONMENT`); **sample rate explicit** (`SENTRY_TRACES_SAMPLE_RATE=0.1` per env; not `1.0` in prod)
- [ ] **PII scrubbing**: `send_default_pii => false`; `before_send` strips sensitive keys from `$event->getRequest()` (body, cookies, headers); breadcrumb allowlist documented
- [ ] **`Log::error`/`Log::critical` captured as Sentry events** via the Laravel integration; error events carry `trace_id` + `user_id` when an OTel span is active
- [ ] **Ignored errors documented**: domain 404/422 (`ModelNotFoundException`, `ValidationException`) filtered via `before_send` or `ignore_exceptions`, each entry justified
- [ ] **Queue exceptions captured**: jobs route through Laravel's exception handler (Sentry hooks); confirm not bypassed

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the fully assembled output to the report file before ending the session; print the confirmation line to console.

## Output Format

```markdown
## Laravel Observability Review Summary

**Stack:** PHP <version> / Laravel <version>; Queue: redis(Horizon)|database|sync; Cache: redis|memcached|file; Runtime: PHP-FPM|Octane|FrankenPHP
**Overall:** Adequate | Gaps Found [High/Medium/Low counts] | Greenfield - no observability surface wired [counts]

## Surface Map

| Surface                  | Verdict                  | Evidence                                       |
| ------------------------ | ------------------------ | ---------------------------------------------- |
| Structured logging       | wired / partial / absent | [file:line or "no logging config in repo"]    |
| OpenTelemetry SDK        | wired / partial / absent | [...]                                          |
| Laravel dashboards       | wired / partial / absent | [Horizon / Telescope / Pulse status]          |
| Queue instrumentation    | wired / partial / absent | [...]                                          |
| Lifecycle / health       | wired / partial / absent | [...]                                          |
| Error tracker            | wired / partial / absent | [...]                                          |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent`. Use `absent` vocabulary consistently (not `none` / `missing` / `not wired`).

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Laravel idiom: missing JSON formatter, `dd()` in controller, model destructured in log context, Telescope unfiltered, Horizon without `viewHorizon` Gate, OTel SDK without `contrib-auto-laravel`, Sentry in `require-dev`, missing `--max-time`, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Laravel / Monolog / OTel / Pulse change with code or config example]

### Medium Impact / ### Low Impact / Quick Wins

[Same structure. Omit sections with no findings. Within each bucket, group by surface when >2 findings share a surface. Greenfield reviews collapse a whole surface into one finding per Step 4's grouping rule.]

## Recommendations

[Structural items not tied to a finding - e.g., add request-id middleware, install `contrib-auto-laravel`, switch Telescope-in-prod to Pulse, move Sentry to `require`, add `queue:restart` to deploy]

## Next Steps

Prioritized list, tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops), ordered High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: ops] - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Steps 1-3: `behavioral-principles` loaded; stack confirmed PHP/Laravel with queue/cache/runtime recorded; `review-precondition-check` ran (or handle received) and diff read once for reuse
- [ ] Step 4: instrumentation files read; Surface Map produced with `wired / partial / absent` per verdict rubric; greenfield grouping applied when surfaces are `absent`
- [ ] Step 5: JSON formatter, correlation context, redaction, no `dd`/`dump`, PSR placeholders, exception-as-object, webhook signature logging
- [ ] Step 6: OTel SDK + `contrib-auto-laravel`, init in `register`, explicit sampling, resource attributes, cardinality budget, span error status
- [ ] Step 7: Horizon/Telescope/Pulse gates verified; Telescope dev-only or sampled
- [ ] Step 8: per-job context, `failed()`, Horizon tags, scheduled-command lifecycle modifiers
- [ ] Step 9: `queue:work --max-time`, `queue:restart` on deploy, `horizon:terminate`, `octane:reload`, `/health` vs `/ready` vs dependency-health, php-fpm slow-log
- [ ] Step 10: error tracker in `require`, DSN externalized, PII scrubbed, trace correlation, explicit sample rate
- [ ] Step 11: report written via `review-report-writer`; confirmation printed
- [ ] Severity rubric applied; findings name a Laravel/Monolog/OTel/Pulse idiom; library-level scope respected; depth honored (`quick` skipped tracing/queue/lifecycle/error-tracker unless diff required; `deep` ran SLI)
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered High > Medium > Low

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Generic advice when a Laravel package or auto-instrumentation exists ("install `open-telemetry/contrib-auto-laravel`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog/Grafana, log forwarder, on-call rotation) - not in source code
- Approving high-cardinality metric tags (`user_id`, `order_id`); require enum/category tags. Prescribing OTLP endpoint URLs or Sentry DSN values - say "sourced from env / Vault"
- Producing one finding per missing checkbox when a surface is absent - collapse per Step 4 grouping rule
