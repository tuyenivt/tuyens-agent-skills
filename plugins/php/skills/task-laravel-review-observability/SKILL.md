---
name: task-laravel-review-observability
description: Laravel observability review: Monolog structured logs, correlation IDs, OpenTelemetry PHP, Horizon, Telescope, Pulse, Sentry/Bugsnag PII scrubbing.
agent: php-observability-engineer
metadata:
  category: backend
  tags: [php, laravel, observability, monolog, opentelemetry, horizon, telescope, pulse, sentry, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Laravel Observability Review

## Purpose

Laravel-aware observability review at the library/SDK level: Monolog channels, OpenTelemetry PHP SDK + `contrib-auto-laravel`, Horizon/Telescope/Pulse, Sentry/Bugsnag, queue worker lifecycle, `php-fpm` slow-log. Stack-specific delegate of `task-code-review-observability`. Infra-level concerns (Datadog, Sentry org settings, log forwarder config) stay out of scope.

## When to Use

- Laravel PR review for observability regressions or new instrumentation gaps
- Pre-release check for a new Laravel service or major feature
- Post-incident review when Laravel diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / structured logging / Pulse, or auditing queue/scheduled-job tracing

**Not for:** general Laravel code review (`task-laravel-review`); known perf bottleneck (`task-laravel-review-perf`); active incident (`/task-oncall-start`); infra-level (Datadog/Grafana/alert rules/log forwarder).

## Depth Levels

| Depth      | When to Use                                                  | What Runs                                          |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `standard` | Default - full Laravel observability review                  | All steps                                          |
| `deep`     | Pre-release of a critical Laravel service, or post-incident review | All steps + SLI/SLO suggestions for Laravel endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                    | Meaning                                                                                                |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `/task-laravel-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch                                    |
| `/task-laravel-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                             |
| `/task-laravel-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                        |

When invoked as a subagent of `task-code-review-observability` or `task-laravel-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 3 is skipped.

## Severity Rubric

| Severity   | Definition                                                                                                                                                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | Diagnosability cliff: prod failures invisible or undebuggable. Text-only `single` channel in prod; `dd()` in a controller; model destructured into log context (leaks `password`); Sentry/Bugsnag in `require-dev`; Telescope unfiltered in prod; Horizon/Pulse reachable without auth Gate; OTel SDK without `contrib-auto-laravel`; bare `queue:work` in prod; missing `/health`+`/ready` on multi-replica; missing `failed()` on billing job; webhook signature failure unlogged. |
| **Medium** | Observability gap with partial mitigation. Missing request-id correlation; string-concat logging losing structured fields; missing OTel sampling config; missing Horizon job tags; missing `->withoutOverlapping()` on 15+ min schedule; missing Sentry `before_send` PII scrubber; missing `--max-time` on `queue:work`. |
| **Low**    | Hardening / nice-to-have. Missing `Model::shouldBeStrict()` in dev; missing `php-fpm` slow-log threshold; missing OTel resource attributes; missing `view:cache` in deploy. |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Skip when invoked as a subagent of `task-code-review-observability` or `task-laravel-review`.

### Step 2 - Confirm Stack and Detect Runtime Surface

Use skill: `stack-detect` to confirm PHP / Laravel. If not Laravel, route to `/task-code-review-observability`. Detect queue connection (Redis+Horizon / database / sync / Beanstalkd / SQS), cache driver, runtime (PHP-FPM / Octane), and wired dashboards (Horizon, Telescope, Pulse).

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`. Skip when running as a subagent with parent-provided artifacts. Never run state-changing git.

### Step 4 - Read the Instrumentation Surface and Build the Surface Map

**Primary output: `wired | partial | absent` verdict per surface** (logging / OTel SDK / Laravel dashboards / queue / error tracker / lifecycle). A missing wire is itself the finding. When `absent`, Steps 5-10 shift from "audit existing wiring" to "scaffold at the changed call sites".

**Verdict rubric.**

- `wired` = registered AND supporting wiring present (correlation processors, auto-instrumentations, auth Gates, redaction)
- `partial` = registered BUT something material missing (e.g., `stack` channel using `single` text driver in prod; OTel SDK without `contrib-auto-laravel`; `viewHorizon` Gate defaulting to `app()->isLocal()`)
- `absent` = no registration in `config/logging.php` / `bootstrap/app.php` / providers / `composer.json`

**Grouping rule.** When a surface is `absent`, produce **a single High-Impact finding for that surface** listing missing pieces grouped by target file/class - not one per sub-bullet. Per-callsite findings apply only when the surface exists and a specific callsite misuses it.

Read files that configure observability:

- `config/logging.php` - channels, formatter (default vs `JsonFormatter`), processors, level
- `bootstrap/app.php` (Laravel 11+) - middleware order; exception handler (`withExceptions(...)`)
- `app/Providers/AppServiceProvider.php` - `Log::context(...)`, schedule, telemetry bindings
- `composer.json` / `composer.lock` - versions of `sentry/sentry-laravel`, `open-telemetry/{sdk,exporter-otlp,contrib-auto-laravel}`, `laravel/{horizon,telescope,pulse}`
- Changed files calling `Log::*`, registering metrics, defining middleware, opening OTel spans, or modifying request context
- Changed `database/migrations/` - new business columns (status, audit, ownership, lifecycle) imply events that should drive a metric/span/log

### Step 5 - Structured Logging (Monolog / `Log::*`)

- [ ] **Prod logger emits JSON**: `config/logging.php` channel uses `Monolog\Formatter\JsonFormatter` (or Laravel 11+ JSON preset). `single` driver is a foot-gun (unrotated growing file)
- [ ] **No `dd()` / `dump()` / `var_dump()` / `print_r()` in prod paths**
- [ ] **Correlation context bound per request**: `request_id`, `user_id`, `tenant_id`, business IDs via middleware calling `Log::withContext([...])` and a Monolog processor
- [ ] **OTel log correlation when SDK present**: active span's `trace_id`/`span_id` attached via `contrib-auto-laravel` Monolog processor. Greenfield (OTel `absent`): minimum viable is request-id middleware + `Log::withContext(['request_id' => $id])`
- [ ] **Sensitive-field redaction**: Monolog processor drops `password`, `token`, `Authorization`, `Cookie`, `credit_card`, `ssn`, `api_key` from every context
- [ ] **Log specific fields, never the model**: `Log::info('user', ['user' => $user])` serializes every non-`$hidden` column (leaks `password` hash). Use `['order_id' => $order->id, 'user_id' => $order->user_id]`
- [ ] **PSR placeholder syntax**: `Log::info('Processing order {order_id}', ['order_id' => $id])`
- [ ] **Log-level discipline + `LOG_LEVEL=info` in prod**; no per-iteration logging in hot loops
- [ ] **Exceptions as objects**: `Log::error('Failed', ['order_id' => $id, 'exception' => $e])` - the `exception` key triggers Monolog introspection. Bare `Log::error($e->getMessage())` drops the stack trace
- [ ] **Webhook signature failures logged**: every signature/replay/idempotency rejection calls `Log::warning(...)` before returning 4xx

### Step 6 - OpenTelemetry SDK and Auto-Instrumentation

- [ ] **SDK + auto-instrumentation installed**: `open-telemetry/sdk`, `open-telemetry/exporter-otlp`, AND `open-telemetry/contrib-auto-laravel`
- [ ] **SDK initialized in a provider's `register` method**, not `boot` - ready when other providers boot
- [ ] **Exporter + resource attributes from env**: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES=service.version=$VERSION,deployment.environment=$ENV`; explicit sampling (`OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1` in prod)
- [ ] **Auto-instrumentation surfaces verified**: HTTP server, Eloquent (via `DB::listen`), outbound Guzzle (handler stack with traceparent), queue (producer/consumer linked via `traceparent` payload)
- [ ] **Custom span attributes within cardinality budget**: `Span::current()->setAttribute('order.id', $orderId)`; no PII, no IDs reused as metric labels
- [ ] **Span error status on exception paths**: `catch (Throwable $e) { Span::current()->recordException($e)->setStatus(StatusCode::STATUS_ERROR, $e->getMessage()); throw $e; }`
- [ ] **Graceful flush on shutdown** via SDK's registered shutdown handler

### Step 7 - Laravel-Shipped Dashboards (Horizon / Telescope / Pulse)

- [ ] **Horizon**: `laravel/horizon` in `require`; `config/horizon.php` supervisors; **`viewHorizon` Gate** in `AppServiceProvider::boot` (not default `app()->isLocal()` on multi-env apps)
- [ ] **Telescope**: in `require-dev`, or in `require` only with `Telescope::filter(...)` sampling. Always gated by `viewTelescope`. Flag unfiltered in prod
- [ ] **Pulse**: `laravel/pulse` in `require`; `config/pulse.php` recorders (slow queries, requests, exceptions); **`viewPulse` Gate**. Production-safe (~1ms/req)

### Step 8 - Queue Worker / Scheduled Job Observability

- [ ] **Queue tracing via `contrib-auto-laravel`**: producer/consumer spans linked through queue-payload traceparent
- [ ] **Per-job context**: `Log::withContext(['job_id' => $job->getJobId(), 'job_class' => static::class])` at `handle()` entry
- [ ] **`failed(Throwable $e)` on every job**; **Horizon tags** for tag-filtered search: `public function tags(): array { return ['order:'.$this->orderId]; }`
- [ ] **Scheduled commands**: `Schedule::command(...)->onSuccess(...)->onFailure(...)`; `->withoutOverlapping()` at 15+ min interval; `->onOneServer()` on multi-replica; `->runInBackground()` on long jobs
- [ ] **Greenfield job minimum (zero instrumentation)**: one `Log::info(...)` at handle entry with business key, outer `try { ... } catch (Throwable $e) { Log::error($e); throw $e; }`, and a `failed()` method

### Step 9 - Lifecycle / Graceful Shutdown Observability

- [ ] **`queue:work --max-time=N --max-jobs=N`** in prod supervisor (prevents memory bloat); `pcntl` installed for graceful SIGTERM
- [ ] **Deploy pipeline calls `php artisan queue:restart`** after `composer install`; `horizon:terminate` (graceful drain) on Horizon; `octane:reload` on Octane
- [ ] **OTel `Tracer::shutdown()` on worker exit**
- [ ] **Health endpoints - three-way distinction (multi-replica without `/health`+`/ready` can't do safe rolling restarts)**:
  - **`/health` (liveness)**: 200 if process is up. NO DB/Redis/external checks - K8s restarts on liveness failure, so a flaky DB downs every replica
  - **`/ready` (readiness)**: 503 when *this pod* can't serve (own DB pool exhausted, draining). NO third-party API ping - amplifies outages
  - **Dependency-health** (`/health/dependencies` or a Pulse card): observability surface, not a pod-removal signal
- [ ] **`php-fpm` slow-log enabled** (non-prod, sampled in prod): `slowlog` + `request_slowlog_timeout = 5s`

### Step 10 - Error Tracking (Sentry / Bugsnag / Flare)

- [ ] **SDK in `require` (not `require-dev`)** - common deploy bug
- [ ] **DSN externalized** (`SENTRY_LARAVEL_DSN`); **release + environment tags** from build metadata; **sample rate explicit** (`SENTRY_TRACES_SAMPLE_RATE=0.1` in prod; not `1.0`)
- [ ] **PII scrubbing**: `send_default_pii => false`; `before_send` strips sensitive keys from `$event->getRequest()`
- [ ] **`Log::error`/`Log::critical` captured as Sentry events** via the Laravel integration; error events carry `trace_id` + `user_id` when an OTel span is active
- [ ] **Ignored errors documented**: domain 404/422 filtered via `before_send` or `ignore_exceptions`, each entry justified
- [ ] **Queue exceptions captured**: jobs route through Laravel's exception handler

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the fully assembled output; print the confirmation line.

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

> Use **Greenfield** as the `Overall:` headline only when 3+ rows are `absent` AND the reviewed change touches no existing instrumentation (no `wired` or `partial` surface - a new/uninstrumented service); a brownfield PR that merely leaves some surfaces `absent` reports `Gaps Found` and lists them as findings. Use `absent` vocabulary consistently.

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Laravel idiom]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Laravel / Monolog / OTel / Pulse change with code or config example]

### Medium Impact / ### Low Impact / Quick Wins

[Same structure. Omit sections with no findings. Greenfield reviews collapse a whole surface into one finding per Step 4's grouping rule.]

## Recommendations

[Structural items not tied to a finding]

## Next Steps

Prioritized list, tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops), ordered Must > Recommend > Question.

_Omit if no actionable findings._
```

## Self-Check

- [ ] Steps 1-3: `behavioral-principles` loaded; stack confirmed; `review-precondition-check` ran; diff read once
- [ ] Step 4: instrumentation files read; Surface Map produced with `wired / partial / absent`; greenfield grouping applied when surfaces are `absent`
- [ ] Step 5: JSON formatter, correlation context, redaction, no `dd`/`dump`, PSR placeholders, exception-as-object, webhook signature logging
- [ ] Step 6: OTel SDK + `contrib-auto-laravel`, init in `register`, explicit sampling, resource attributes, cardinality budget, span error status
- [ ] Step 7: Horizon/Telescope/Pulse gates verified; Telescope dev-only or sampled
- [ ] Steps 8-10: applied or skipped per diff signals; gating recorded
- [ ] Step 11: report written via `review-report-writer`; confirmation printed
- [ ] Severity rubric applied; findings name a Laravel/Monolog/OTel/Pulse idiom; library-level scope respected
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend > Question

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Generic advice when a Laravel package or auto-instrumentation exists ("install `open-telemetry/contrib-auto-laravel`", not "add HTTP request tracing")
- Reviewing infra-level concerns (Datadog/Grafana, log forwarder, on-call rotation) - not in source code
- Approving high-cardinality metric tags (`user_id`, `order_id`); require enum/category tags
- Producing one finding per missing checkbox when a surface is absent - collapse per Step 4 grouping rule
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
