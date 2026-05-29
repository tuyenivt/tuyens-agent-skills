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

Rails-aware observability review naming `ActiveSupport::Notifications`, `query_log_tags`, `lograge`/`semantic_logger`, Sidekiq middleware, Rack correlation IDs, and error-tracker gem wiring directly. Focuses on whether Rails production behavior is visible, diagnosable, and alertable at the **gem and library level**. Infra-level concerns (ELK, Datadog SaaS, Sentry dashboard config) stay out of scope. Stack-specific delegate of `task-code-review-observability`.

## When to Use

- Reviewing a Rails PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence was missing
- Adopting `lograge`/`semantic_logger`/OpenTelemetry/`query_log_tags`
- Auditing Sidekiq job tracing and request -> job correlation

**Not for:** general review (`task-rails-review`), perf with known bottleneck (`task-rails-review-perf`), active incident (`/task-oncall-start`), infra-level (Datadog dashboards, Sentry SaaS, log forwarder).

## Depth

| Depth      | When                                                            | What Runs                                   |
| ---------- | --------------------------------------------------------------- | ------------------------------------------- |
| `quick`    | Single endpoint, controller, or job                             | Steps 4 + 5 only                            |
| `standard` | Default                                                         | All steps                                   |
| `deep`     | Pre-release of critical service or post-incident                | All steps + SLI/SLO suggestions             |

Default: `standard`.

## Invocation

| Form                                        | Meaning                                              |
| ------------------------------------------- | ---------------------------------------------------- |
| `/task-rails-review-observability`          | Current branch vs base; fails fast on trunk          |
| `/task-rails-review-observability <branch>` | `<branch>` vs base (3-dot)                           |
| `/task-rails-review-observability pr-<N>`   | PR head fetched into local branch `pr-<N>`           |

When invoked as a subagent with pre-read artifacts, Steps 1-3 are skipped.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-observability`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read diff and log once; reuse. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - Structured Logging

Inspect `config/environments/*.rb`, `config/initializers/lograge*.rb`/`semantic_logger*.rb`, and any `Rails.logger.*` callsite in the diff:

- [ ] **Production logger is structured** - `lograge.enabled = true` with JSON formatter, or `semantic_logger` with JSON appender. No raw text logs in production
- [ ] **`lograge.custom_options`** (or `semantic_logger` payload) injects `request_id`, `user_id` (when authenticated), `tenant_id`, `trace_id`, `span_id`, business correlation IDs (`order_id`)
- [ ] **`config.filter_parameters`** covers `:password`, `:password_confirmation`, `:token`, `:api_key`, `:credit_card`, `:ssn`, `:authorization`
- [ ] **No `Rails.logger.info`/`debug`** with sensitive data - inspect new calls for tokens, full bodies on auth endpoints, PII
- [ ] **Log levels**: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics
- [ ] **No log spam in hot loops** - `find_each`/`each` over large collections must not log per-iteration
- [ ] **`tagged_logger`** for request-scoped tags when `lograge` isn't in use
- [ ] **Sidekiq logger** configured (`Sidekiq.logger = Rails.logger` or dedicated structured logger); job context tags (`jid`, `class`, `bid`, `args_summary`)

### Step 5 - ActiveSupport::Notifications

- [ ] **Custom business events instrumented**: new domain operations (`order.fulfilled`, `payment.charged`, `user.activated`) emitted via `ActiveSupport::Notifications.instrument('event.namespace', payload)` rather than buried in service internals
- [ ] **Subscribers exist or are documented**: emitted events have an in-app subscriber (APM/StatsD) or a documented external contract - emitted-but-unconsumed events are dead weight
- [ ] **Event naming follows `verb.namespace`** (`process.action_controller`, `sql.active_record`, `enqueue.active_job`)
- [ ] **No high-cardinality fields in event names** - name is fixed; high-cardinality data (user ID, order ID) goes in the payload
- [ ] **Rails internals subscribed when needed** - APM gem (`scout_apm`, `skylight`, `new_relic_rpm`, `ddtrace`) installed, or custom subscribers consuming `process.action_controller`, `sql.active_record`, `perform.active_job`

### Step 6 - Query Attribution

- [ ] **`config.active_record.query_log_tags_enabled = true`** in production (Rails 7+)
- [ ] **`config.active_record.query_log_tags`** includes `:controller`, `:action`, `:job`, `:request_id`; add `:tenant` if multi-tenant
- [ ] **Custom tags** for app-specific context via `ActiveRecord::QueryLogs.taggings`
- [ ] **No PII in tags** - no user IDs, emails, tokens in query log tags

### Step 7 - Distributed Tracing

Inspect `config/initializers/opentelemetry.rb`, `config/initializers/datadog.rb`:

- [ ] **Auto-instrumentation** matching gems in use: `opentelemetry-instrumentation-rails`, `-active_record`, `-active_job`, `-sidekiq`, `-faraday`, `-net_http`, `-redis`
- [ ] **Trace context propagation** via W3C `traceparent` on outbound HTTP (Faraday middleware, `Net::HTTP` instrumentation)
- [ ] **Sidekiq tracing**: context extracted from job payload on `perform`; new spans linked to parent request span - not orphaned with a fresh trace ID
- [ ] **ActiveJob tracing** if Sidekiq is fronted by ActiveJob: instrumentation covers both layers
- [ ] **Custom spans for service objects**: long-running orchestrations wrap `.call` in a tracer span. OTel: `tracer.in_span('order.fulfill', attributes: { 'order.id' => id }) { ... }`. Datadog: `Datadog::Tracing.trace('order.fulfill') { |span| span.set_tag('order.id', id) }`. Cache the tracer at class load
- [ ] **Sampling**: head-based 10-20% for high-traffic apps; always-sample on errors and slow requests

### Step 8 - Sidekiq Observability

Sidekiq has its own middleware chain - request-scoped context does not flow into jobs unless explicitly bridged:

- [ ] **Sidekiq client middleware** captures `request_id`/`trace_id`/`tenant_id` and stores it on the job payload at enqueue
- [ ] **Sidekiq server middleware** restores that context on `perform` (into `Current.attributes`, `RequestStore`, or OTel context)
- [ ] **Job retries logged** with retry count and reason; dead jobs alerted (dead-set monitoring)
- [ ] **Sidekiq metrics**: queue latency, busy workers, retry/dead counts via `sidekiq-prometheus-exporter`, `yabeda-sidekiq`, or APM gem
- [ ] **Sidekiq Web UI** auth-gated in production

### Step 9 - Correlation ID and Request Context

- [ ] **Rack middleware**: `ActionDispatch::RequestId` enabled; load-balancer-injected `X-Request-ID` honored when present
- [ ] **Request-scoped context** via `ActiveSupport::CurrentAttributes` (Rails 5.2+) for `user_id`, `tenant_id`, `request_id`. Prefer over the legacy `RequestStore` gem; flag new code adding `RequestStore` instead of extending `Current`
- [ ] **Outbound HTTP propagates `X-Request-ID`** so downstream services correlate (Faraday middleware, `Net::HTTP` patch, or APM auto-instrumentation)
- [ ] **`AS::Notifications` subscribers** read `Current.user_id` so events carry tenant/user without each emit-site re-fetching

### Step 10 - Error Tracking

- [ ] **Gem installed**: `sentry-rails`, `honeybadger`, or `rollbar` with initializer in `config/initializers/`
- [ ] **DSN / API key from credentials**, not env-only; not committed
- [ ] **`config.before_send`** scrubs beyond `filter_parameters`: cookies, headers like `Authorization`, `X-Api-Key`
- [ ] **User context** when authenticated: `Sentry.set_user(id: current_user.id)` in `ApplicationController` (no email/PII unless privacy policy permits)
- [ ] **Sidekiq integration**: failed jobs report with class, args summary (no raw args - may contain PII), retry count
- [ ] **Release tracking** wired so deploys correlate to spikes
- [ ] **Unhandled `rescue_from` errors** still report to tracker (not swallowed by a generic 500 handler)
- [ ] **Test-mode silent**: tracker disabled in `Rails.env.test?`

### Step 11 - Health Checks and SLIs (deep depth or explicit request)

Use skill: `ops-observability` for health-check shapes.

- [ ] **Liveness** (`/up` or `/health/live`): returns 200 unconditionally while the Rails process is responsive. **No DB/Redis/external checks** (would fail every replica during routine DB restart). Rails 7.1's built-in `/up` is correct
- [ ] **Readiness** (`/health/ready`): verifies **own-pod** dependencies the request path requires - DB connection from this pod's pool, Redis from this pod's client, warmed in-process caches. **No third-party API ping** (turns local outage into cascading outage)
- [ ] **Dependency-health** (`/internal/deps`): observability signal for ops dashboards, **not** wired to pod removal. Verify diff doesn't point a `readinessProbe` at it
- [ ] **SLI per critical endpoint**: success rate (non-5xx), p99 latency via Prometheus/Datadog/in-app metric
- [ ] **SLO target** with window (e.g., 99.9% over 30 days for `POST /orders`)
- [ ] **Sidekiq SLI**: queue latency p99 < N seconds for time-sensitive queues; dead-job count under threshold
- [ ] **Alerts page on symptoms** (5xx rate, p99 latency, queue depth), not causes (CPU, memory)

Flag a Rails service with no SLI/SLO as a **High** observability gap.

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Print confirmation.

## Output Format

```markdown
## Rails Observability Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Logger:** lograge | semantic_logger | Rails.logger (raw) | other
**Tracing:** OpenTelemetry | New Relic | Datadog APM | Scout | Skylight | none
**Error tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [count by severity: High/Medium/Low]

## Findings

### High Severity (would prevent detection of a production failure)

- **Location:** [file:line, controller, job, or initializer]
- **Missing:** [absent signal - log field, AS::Notifications event, query tag, span, scrubbing]
- **Impact:** [what becomes invisible - "Sidekiq failures attributed to wrong request", "p99 latency cannot be derived", "PII leaks into error tracker"]
- **Fix:** [concrete Rails change with gem and code]

### Medium / Low Severity

[Same structure]

_Omit empty sections._

## Recommendations

[Structural - "Adopt OpenTelemetry across services", "Migrate Rails.logger to semantic_logger", "Define SLOs for /orders, /checkout", "Wire query_log_tags for tenant"]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-service tracing rollout, SLO workshop, alerting overhaul).

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: Sidekiq] - [one-line action]

_Omit if no gaps._

## No Gaps Found

[State explicitly if observability is adequate.]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed (or accepted from parent)
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff/log read once
- [ ] Step 4: structured logging - lograge/semantic_logger config; `filter_parameters` coverage; no PII; correct levels; no hot-loop spam
- [ ] Step 5: `AS::Notifications` - business events emitted, subscribers exist, naming convention, no high-cardinality names
- [ ] Step 6: `query_log_tags` enabled with appropriate tags; no PII in tags
- [ ] Step 7: tracing - auto-instrumentation for libraries in use; W3C propagation on outbound HTTP and Sidekiq boundary; custom spans where warranted
- [ ] Step 8: Sidekiq middleware - client captures context, server restores; retry/dead visibility configured
- [ ] Step 9: correlation - `ActionDispatch::RequestId`, `Current.attributes`, outbound `X-Request-ID`
- [ ] Step 10: error tracker - initialization, scrubbing, user context, Sidekiq integration, release tracking, test-mode silent
- [ ] Step 11 (deep): liveness/readiness shapes correct, SLI/SLO defined, alerts page on symptoms
- [ ] Step 12: report written via `review-report-writer`; confirmation printed
- [ ] Every finding states the missing signal AND what becomes invisible without it
- [ ] Findings ordered by severity; Next Steps `[Implement]`/`[Delegate]` ordered High > Medium > Low

## Avoid

- Running state-changing git commands
- "Missing log" findings without stating what becomes invisible
- More logging without considering volume cost and alerting noise
- Metrics with high-cardinality labels (request ID, user ID, raw URL) - break aggregation
- Confusing logging, metrics, tracing - different questions (what / how often / why this request)
- Reviewing infra-level config - stays at gem/library level
- Conflating observability with general or perf review
- Observability tooling without alerting - signals nobody acts on are wasted
