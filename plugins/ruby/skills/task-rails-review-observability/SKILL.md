---
name: task-rails-review-observability
description: Rails observability review - ActiveSupport::Notifications, lograge, Sidekiq tracing, Rack correlation IDs, Sentry/Honeybadger/Rollbar wiring.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, observability, logging, metrics, tracing, sidekiq, workflow]
  type: workflow
user-invocable: true
---

# Rails Observability Review

Rails-aware observability review naming `ActiveSupport::Notifications`, `query_log_tags`, `lograge`/`semantic_logger`, Sidekiq middleware, Rack correlation IDs, and error-tracker gem wiring directly. Focuses on whether Rails production behavior is **visible, diagnosable, and alertable** at the gem/library level. Infra-level concerns (ELK, Datadog SaaS, Sentry dashboard config) stay out of scope. Stack-specific delegate of `task-code-review-observability`.

## When to Use

Reviewing a Rails PR for observability regressions or new instrumentation gaps; pre-release check for a new service or major feature; post-incident review when diagnosis was slow; adopting `lograge`/`semantic_logger`/OpenTelemetry/`query_log_tags`; auditing Sidekiq tracing and request -> job correlation.

## Depth

| Depth      | What Runs                                         |
| ---------- | ------------------------------------------------- |
| `quick`    | Steps 4 + 5 only                                  |
| `standard` | All steps except 9 (default)                      |
| `deep`     | All steps + SLI/SLO suggestions                   |

## Invocation

`/task-rails-review-observability [<branch>|pr-<N>] [quick|deep]` - current branch vs base; fails fast on trunk. When invoked as subagent with pre-read artifacts, Steps 1-3 are skipped.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-observability`. Record the **logger** (lograge / semantic_logger / raw), **tracer** (OpenTelemetry / Datadog / New Relic / Scout / Skylight / none), and **error tracker** (Sentry / Honeybadger / Rollbar / none).

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check`. On approval, read diff and log once. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - Logging Hygiene

One rule per new or modified `Rails.logger.*` call and per logger-config change. Inspect `config/environments/*.rb`, `config/initializers/lograge*.rb`/`semantic_logger*.rb`, every `Rails.logger.*` callsite in the diff.

- [ ] **Production logger is structured** - `lograge.enabled = true` with JSON formatter, or `semantic_logger` with JSON appender. No raw text logs in production
- [ ] **Every new logger call**: structured payload (not interpolated string), correct level (`error` for actionable failures, `warn` for recoverable, `info` for state transitions, `debug` for verbose), no PII, not inside an unbounded loop (`find_each`/`each` over large collections must not log per-iteration)
- [ ] **Sidekiq logger** structured (`Sidekiq.logger = Rails.logger` or dedicated); job context tags (`jid`, `class`, `args_summary`)

PII filter coverage (`config.filter_parameters`) belongs to `task-rails-review-security`. Cross-flag here only if a new log line clearly leaks fields the security review wouldn't catch (e.g., custom log of `params.to_unsafe_h`).

### Step 5 - Business Events (ActiveSupport::Notifications & custom spans)

Treat AS::Notifications events and tracer spans as **one axis** - both ask "is this domain operation visible?" One finding per missing-visibility callsite, not one per signal type.

- [ ] **Custom business events instrumented**: new domain operations (`order.fulfilled`, `payment.charged`, `user.activated`) emitted via `ActiveSupport::Notifications.instrument('event.namespace', payload)` AND/OR wrapped in a tracer span (OTel: `tracer.in_span('order.fulfill', attributes: { 'order.id' => id }) { ... }`; Datadog: `Datadog::Tracing.trace('order.fulfill') { |s| s.set_tag('order.id', id) }`)
- [ ] **Subscribers exist or are documented** for emitted events
- [ ] **Event naming follows `verb.namespace`**; high-cardinality data (user/order IDs) in payload, not name
- [ ] **Rails internals consumed** - APM gem (`scout_apm`, `skylight`, `new_relic_rpm`, `ddtrace`) installed or custom subscribers consuming `process.action_controller`, `sql.active_record`, `perform.active_job`

### Step 6 - Correlation Across Layers

Single step covering `query_log_tags`, Rack request IDs, `Current.attributes`, Sidekiq middleware bridge, and outbound `traceparent`/`X-Request-ID`. **Skip when the diff doesn't touch correlation config or add new Sidekiq jobs / outbound HTTP / async paths** - this step exists to keep the request-id thread intact across boundaries.

- [ ] **Rack `ActionDispatch::RequestId`** enabled; load-balancer `X-Request-ID` honored when present
- [ ] **Request-scoped context** via `ActiveSupport::CurrentAttributes` for `user_id`, `tenant_id`, `request_id`. Flag new code adding the legacy `RequestStore` gem instead of extending `Current`
- [ ] **Sidekiq client middleware** captures `request_id`/`trace_id`/`tenant_id` and stores on the job payload at enqueue; **server middleware** restores it on `perform` (into `Current.attributes` or OTel context). Without this, every new job orphans its trace
- [ ] **Outbound HTTP propagates `traceparent` (W3C) and `X-Request-ID`** - Faraday middleware, `Net::HTTP` patch, or APM auto-instrumentation
- [ ] **`config.active_record.query_log_tags_enabled = true`** in production (Rails 7+) with `query_log_tags` covering `:controller`, `:action`, `:job`, `:request_id` (plus `:tenant` if multi-tenant). No PII in tags

### Step 7 - Tracing Setup (config-change PRs only)

Skip unless the diff touches `config/initializers/opentelemetry.rb`, `config/initializers/datadog.rb`, or adds/removes a tracer gem.

- [ ] **Auto-instrumentation** matching gems in use: `opentelemetry-instrumentation-rails`, `-active_record`, `-active_job`, `-sidekiq`, `-faraday`, `-net_http`, `-redis`
- [ ] **ActiveJob tracing** if Sidekiq is fronted by ActiveJob: instrumentation covers both layers
- [ ] **Sampling**: head-based 10-20% for high-traffic apps; always-sample on errors and slow requests
- [ ] **Tracer cached at class load** for custom-span paths

### Step 8 - Sidekiq Observability

- [ ] **Job retries logged** with retry count and reason; **dead jobs alerted** (dead-set monitoring)
- [ ] **Sidekiq metrics** (queue latency, busy workers, retry/dead counts) via `sidekiq-prometheus-exporter`, `yabeda-sidekiq`, or APM gem

Sidekiq Web auth-gating and request-id bridging are owned by Step 6 (correlation) and the security review (admin-endpoint gating).

### Step 9 - Error Tracker Capture

Setup checks (gem install, DSN-from-credentials, test-mode silent, release tracking) only fire on initializer diffs - flag them then. Every PR runs:

- [ ] **Scrub beyond `filter_parameters`** in `config.before_send`: cookies, headers like `Authorization`, `X-Api-Key`
- [ ] **User context** when authenticated: `Sentry.set_user(id: current_user.id)` in `ApplicationController` (no email/PII unless privacy policy permits)
- [ ] **Sidekiq integration**: failed jobs report with class, args summary (not raw args), retry count
- [ ] **Unhandled `rescue_from` errors** still report to tracker (not swallowed by a generic 500 handler). Inspect every new `rescue` in the diff
- [ ] **DSN/API key in credentials, not env-only** (setup PRs only)
- [ ] **Test-mode silent** (setup PRs only)

### Step 10 - Health Checks and SLIs (deep depth or explicit request)

Use skill: `ops-observability` for health-check shapes.

- [ ] **Liveness** (`/up` or `/health/live`): returns 200 unconditionally while Rails is responsive. **No DB/Redis/external checks**. Rails 7.1's built-in `/up` is correct
- [ ] **Readiness** (`/health/ready`): verifies own-pod dependencies the request path requires (DB connection from this pod's pool, Redis from this pod's client, warmed caches). **No third-party API ping**
- [ ] **Dependency-health** (`/internal/deps`): ops-dashboard signal, **not** a `readinessProbe` target
- [ ] **SLI per critical endpoint** (success rate, p99 latency); **SLO target + window**; **Sidekiq SLI** for time-sensitive queues
- [ ] **Alerts page on symptoms** (5xx rate, p99 latency, queue depth), not causes (CPU, memory)

Flag a Rails service with no SLI/SLO as a **High** observability gap.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Print confirmation.

## Output Format

```markdown
## Rails Observability Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Logger:** lograge | semantic_logger | Rails.logger (raw) | other
**Tracing:** OpenTelemetry | New Relic | Datadog APM | Scout | Skylight | none
**Error tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [High/Medium/Low count]

## Findings

### High Severity (would prevent detection of a production failure)

- **Location:** [file:line, controller, job, or initializer]
- **Missing:** [absent signal - log field, AS::Notifications event, query tag, span, scrubbing]
- **Impact:** [what becomes invisible - e.g. "Sidekiq failures attributed to wrong request"]
- **Fix:** [concrete Rails change with gem and code]

### Medium / Low Severity
[Same structure]

_Omit empty sections._

## Recommendations
[Structural changes spanning multiple PRs]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-service tracing rollout, SLO workshop, alerting overhaul).

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: Sidekiq] - [one-line action]

_Omit if no gaps. State "No observability gaps found" explicitly when clean._
```

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent); diff/log read once; logger + tracer + error-tracker recorded
- [ ] Step 4: every new `Rails.logger.*` call assessed; logger-format gaps raised; PII overlap with security only when novel
- [ ] Step 5: business events and custom spans assessed as one axis - no double-counting
- [ ] Step 6: correlation step ran when diff added jobs / outbound HTTP / async paths; skipped with note otherwise
- [ ] Step 7: tracing setup checked only on initializer/gem change
- [ ] Step 8: retry/dead visibility and Sidekiq metrics covered; auth-gating deferred to security
- [ ] Step 9: scrub/user-context/Sidekiq capture covered every PR; setup checks fired only on initializer change
- [ ] Step 10 (deep): liveness/readiness shapes, SLI/SLO, symptom alerts
- [ ] Step 11: report via `review-report-writer`; confirmation printed
- [ ] Every finding states the missing signal AND what becomes invisible without it
- [ ] Findings ordered High > Medium > Low; Next Steps `[Implement]`/`[Delegate]` in same order

## Avoid

- "Missing log" findings without stating what becomes invisible
- More logging without considering volume cost and alerting noise
- Metrics with high-cardinality labels (request ID, user ID, raw URL)
- Conflating logging, metrics, tracing - different questions (what / how often / why this request)
- Reviewing infra-level config - stays at gem/library level
- Filing the same correlation-ID gap as separate findings under logging + Sidekiq + outbound HTTP
- Filing `filter_parameters` coverage as observability - that's security
