---
name: task-rails-review-observability
description: Rails observability review: ActiveSupport::Notifications, lograge, Sidekiq tracing, Rack correlation IDs, Sentry/Honeybadger/Rollbar wiring.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, observability, logging, metrics, tracing, sidekiq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.

# Rails Observability Review

Rails-aware observability review naming `ActiveSupport::Notifications`, `query_log_tags`, `lograge` / `semantic_logger`, Sidekiq middleware, Rack correlation IDs, and error-tracker gem wiring directly. Focuses on whether Rails production behavior is visible, diagnosable, and alertable - at the **gem and library level**. Infra-level concerns (ELK, Datadog SaaS, Sentry dashboard config) stay out of scope.

Stack-specific delegate of `task-code-review-observability`.

## When to Use

- Reviewing a Rails PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow or evidence was missing
- Adopting `lograge` / `semantic_logger` / OpenTelemetry / `query_log_tags`
- Auditing Sidekiq job tracing and correlation across request -> job boundary

**Not for:** general review (`task-rails-review`), perf with known bottleneck (`task-rails-review-perf`), active incident (`/task-oncall-start`), infra-level (Datadog dashboards, Sentry SaaS, log forwarder).

## Depth

| Depth      | When                                                            | What Runs                                   |
| ---------- | --------------------------------------------------------------- | ------------------------------------------- |
| `quick`    | Single endpoint, controller, or job                             | Logging + `AS::Notifications` only          |
| `standard` | Default - full observability review                             | All steps                                   |
| `deep`     | Pre-release of critical service or post-incident                | All steps + SLI/SLO suggestions             |

Default: `standard`.

## Invocation

| Form                                        | Meaning                                              |
| ------------------------------------------- | ---------------------------------------------------- |
| `/task-rails-review-observability`          | Current branch vs base; fails fast on trunk          |
| `/task-rails-review-observability <branch>` | `<branch>` vs base (3-dot)                           |
| `/task-rails-review-observability pr-<N>`   | PR head fetched into local branch `pr-<N>`           |

When invoked as a subagent of `task-code-review-observability` or `task-rails-review` with the precondition handle + pre-read diff/log, Step 2 is skipped.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-observability`.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read diff and log once; reuse. Skip if running as subagent with pre-read artifacts. Fail-fast: surface verbatim and stop.

### Step 3 - Structured Logging

Inspect `config/environments/*.rb`, `config/initializers/lograge*.rb` / `semantic_logger*.rb`, and any `Rails.logger.*` callsite in the diff:

- [ ] **Production logger is structured** - `lograge.enabled = true` with JSON formatter, or `semantic_logger` with JSON appender. No raw text logs in production
- [ ] **`lograge.custom_options`** (or `semantic_logger` payload) injects `request_id`, `user_id` (when authenticated), `tenant_id`, `trace_id`, `span_id`, business correlation IDs (`order_id`, `tenant_id`)
- [ ] **`config.filter_parameters`** covers `:password`, `:password_confirmation`, `:token`, `:api_key`, `:credit_card`, `:ssn`, `:authorization`
- [ ] **No `Rails.logger.info`/`debug`** with sensitive data - inspect new calls for tokens, full bodies on auth endpoints, PII
- [ ] **Log levels**: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics
- [ ] **No log spam in hot loops** - `find_each` blocks, serializers, `each` over large collections must not log per-iteration
- [ ] **`tagged_logger`** for request-scoped tags when `lograge` isn't in use
- [ ] **Sidekiq logger** configured (`Sidekiq.logger = Rails.logger` or dedicated structured logger); job context tags (`jid`, `class`, `bid`, `args_summary`)

### Step 4 - ActiveSupport::Notifications

`AS::Notifications` is Rails' built-in instrumentation hook:

- [ ] **Custom business events instrumented**: new domain operations (`order.fulfilled`, `payment.charged`, `user.activated`) emitted via `ActiveSupport::Notifications.instrument('event.namespace', payload)` rather than buried in service internals
- [ ] **Subscribers exist or are documented**: emitted events have an in-app subscriber (APM/StatsD) or a documented external contract - emitted-but-unconsumed events are dead weight
- [ ] **Event naming follows `verb.namespace`** (e.g., `process.action_controller`, `sql.active_record`, `enqueue.active_job`)
- [ ] **No high-cardinality fields in event names** - name is fixed; high-cardinality data (user ID, order ID) goes in the payload
- [ ] **Out-of-band Rails internals subscribed when needed** - APM gem (`scout_apm`, `skylight`, `new_relic_rpm`, `ddtrace`) installed; or custom subscribers consuming `process.action_controller`, `sql.active_record`, `perform.active_job`

### Step 5 - Query Attribution

- [ ] **`config.active_record.query_log_tags_enabled = true`** in production (Rails 7+)
- [ ] **`config.active_record.query_log_tags`** includes `:controller`, `:action`, `:job`, `:request_id`; add `:tenant` if multi-tenant
- [ ] **Custom tags** for app-specific context registered via `ActiveRecord::QueryLogs.taggings`
- [ ] **No PII in tags** - no user IDs, emails, tokens in query log tags

### Step 6 - Distributed Tracing

Inspect `config/initializers/opentelemetry.rb`, `config/initializers/datadog.rb`:

- [ ] **Auto-instrumentation** for Rails: `opentelemetry-instrumentation-rails`, `-active_record`, `-active_job`, `-sidekiq`, `-faraday`, `-net_http`, `-redis` - install those matching gems in use
- [ ] **Trace context propagation** via W3C `traceparent` on outbound HTTP (Faraday middleware, `Net::HTTP` instrumentation)
- [ ] **Sidekiq tracing**: context extracted from job payload on `perform`; new spans linked to parent request span - not orphaned with a fresh trace ID
- [ ] **ActiveJob tracing** if Sidekiq is fronted by ActiveJob: instrumentation covers both layers
- [ ] **Custom spans for service objects**: long-running orchestrations wrap `.call` in a tracer span so APM reflects business steps. OTel: `OpenTelemetry.tracer_provider.tracer('app').in_span('order.fulfill', attributes: { 'order.id' => order.id }) { ... }`. Datadog: `Datadog::Tracing.trace('order.fulfill') { |span| span.set_tag('order.id', order.id) }`. Cache the tracer at class load
- [ ] **Sampling**: head-based 10-20% for high-traffic apps; always-sample on errors and slow requests

### Step 7 - Sidekiq Observability

Sidekiq has its own middleware chain - request-scoped context does not flow into jobs unless explicitly bridged:

- [ ] **Sidekiq client middleware** captures `request_id` / `trace_id` / `tenant_id` and stores it on the job payload at enqueue
- [ ] **Sidekiq server middleware** restores that context on `perform` (into `Current.attributes`, `RequestStore`, or OTel context)
- [ ] **Job retries logged** with retry count and reason; dead jobs alerted (Sidekiq dead set monitoring)
- [ ] **Sidekiq metrics**: queue latency, busy workers, retry/dead counts via `sidekiq-prometheus-exporter`, `yabeda-sidekiq`, or APM gem
- [ ] **Sidekiq Web UI** auth-gated in production

### Step 8 - Correlation ID and Request Context

- [ ] **Rack middleware**: `ActionDispatch::RequestId` enabled; load-balancer-injected `X-Request-ID` honored when present
- [ ] **Request-scoped context** via `ActiveSupport::CurrentAttributes` (Rails 5.2+) for `user_id`, `tenant_id`, `request_id` - reset between requests automatically. Prefer over the legacy `RequestStore` gem; flag new code adding `RequestStore` instead of extending `Current`
- [ ] **Outbound HTTP propagates `X-Request-ID`** so downstream services correlate (Faraday middleware, `Net::HTTP` patch, or APM auto-instrumentation)
- [ ] **`AS::Notifications` subscribers** read `Current.user_id` so events carry tenant/user without each emit-site re-fetching

### Step 9 - Error Tracking

- [ ] **Gem installed**: `sentry-rails`, `honeybadger`, `rollbar`. Initializer in `config/initializers/`
- [ ] **DSN / API key from credentials**, not env-only; not committed
- [ ] **`config.before_send`** scrubs beyond `filter_parameters`: cookies, headers like `Authorization`, `X-Api-Key`
- [ ] **User context** when authenticated: `Sentry.set_user(id: current_user.id)` in `ApplicationController` (no email/PII unless privacy policy permits)
- [ ] **Sidekiq integration**: failed jobs report with class, args summary (no raw args - may contain PII), retry count
- [ ] **Release tracking** wired - release identifier on error reports so deploys correlate to spikes
- [ ] **Unhandled `rescue_from` errors** still report to tracker (not swallowed by a generic 500 handler)
- [ ] **Test-mode silent**: tracker disabled in `Rails.env.test?`

### Step 10 - Health Checks and SLIs (deep depth or explicit request)

- [ ] **Liveness** (`/up` or `/health/live`): returns 200 unconditionally as long as the Rails process is responsive. **No DB / Redis / Sidekiq / external checks.** A liveness probe pinging the DB will fail every replica during routine DB restart and Kubernetes will kill them all simultaneously. Rails 7.1's built-in `/up` is correct; don't replace it with a deeper check
- [ ] **Readiness** (`/health/ready`): verifies *own-pod* dependencies the request path requires - DB connection from this pod's pool, Redis from this pod's client, in-process caches warmed. **No third-party API ping.** A readiness probe depending on a third party makes every replica fail simultaneously when that third party degrades; Kubernetes removes all pods and the local outage becomes a cascading outage. Third-party degradation surfaces via circuit-breaker / retry / bulkhead, not by removing pods
- [ ] **Dependency-health** (`/internal/deps`): observability signal for ops dashboards and oncall, **not** wired to pod removal. Verify the diff doesn't point a `readinessProbe` at this endpoint
- [ ] **SLI per critical endpoint**: success rate (non-5xx), p99 latency. Prometheus query, Datadog SLO, or in-app metric
- [ ] **SLO target** with window (e.g., 99.9% over 30 days for `POST /orders`)
- [ ] **Sidekiq SLI**: queue latency p99 < N seconds for time-sensitive queues; dead-job count under threshold
- [ ] **Alerts page on symptoms** (5xx rate, p99 latency, queue depth), not causes (CPU, memory)

Flag a Rails service with no SLI/SLO as a **High** observability gap.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write before ending. Print confirmation.

## Self-Check

- [ ] Stack confirmed; `review-precondition-check` ran (or handle received); diff/log read once
- [ ] When `head_matches_current` was false, explicit user approval obtained (skipped if subagent)
- [ ] Structured logging: `lograge`/`semantic_logger` config; `filter_parameters` coverage; no PII in new calls; correct levels
- [ ] `AS::Notifications`: business events emitted, subscribers exist, naming convention, no high-cardinality names
- [ ] `query_log_tags` enabled with appropriate tags; no PII in tags
- [ ] Distributed tracing: auto-instrumentation gems for libraries in use; W3C propagation on outbound HTTP and Sidekiq boundary; custom spans for service objects when warranted
- [ ] Sidekiq middleware: client captures context, server restores; retry/dead visibility configured
- [ ] Correlation ID propagation: `ActionDispatch::RequestId`, `Current.attributes`, outbound `X-Request-ID`
- [ ] Error tracker wiring: initialization, scrubbing, user context, Sidekiq integration, release tracking, test-mode silent
- [ ] **Deep**: SLIs and health endpoints audited; symptom-based alerting verified
- [ ] Every finding states the missing signal AND what becomes invisible without it
- [ ] Findings ordered by severity; quick wins separated from structural changes
- [ ] Next Steps `[Implement]` / `[Delegate]` ordered High > Medium > Low
- [ ] Report written via `review-report-writer`; confirmation printed

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

[Structural improvements - "Adopt OpenTelemetry across services", "Migrate Rails.logger to semantic_logger", "Define SLOs for /orders, /checkout", "Wire query_log_tags for tenant"]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-service tracing rollout, SLO workshop, alerting overhaul).

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: Sidekiq] - [one-line action]

_Omit if no gaps._

## No Gaps Found

[State explicitly if observability is adequate.]
```

## Avoid

- Running state-changing git commands
- "Missing log" findings without stating what becomes invisible
- More logging without considering volume cost and alerting noise
- Metrics with high-cardinality labels (request ID, user ID, raw URL) - break aggregation
- Confusing logging, metrics, tracing - different questions (what / how often / why this request)
- Reviewing infra-level config - stays at gem/library level
- Conflating observability with general or perf review
- Observability tooling without alerting - signals nobody acts on are wasted
