---
name: task-rails-review-observability
description: Rails-specific observability review for ActiveSupport::Notifications, query_log_tags, lograge / semantic_logger, Sidekiq middleware tracing, Rack correlation IDs, and error-tracker gem wiring (Sentry / Honeybadger / Rollbar). Use when reviewing a Rails PR for observability gaps, before releasing a new Rails service, or after an incident where Rails diagnosis was slow. Stack-specific override of task-code-review-observability for Ruby/Rails.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, observability, logging, metrics, tracing, sidekiq, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rails Observability Review

## Purpose

Rails-aware observability review that names `ActiveSupport::Notifications`, `query_log_tags`, `lograge` / `semantic_logger`, Sidekiq middleware, Rack correlation IDs, and error-tracker gem wiring directly instead of routing through the generic adapter. Focuses on whether Rails production behavior is visible, diagnosable, and alertable - at the _gem and library_ level. Infra-level concerns (ELK, Datadog SaaS, Sentry dashboard config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Ruby/Rails. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a Rails PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Rails service or major feature
- Post-incident review when Rails diagnosis was slow or evidence was missing
- Adopting `lograge` / `semantic_logger` / OpenTelemetry / `query_log_tags` in a Rails app
- Auditing Sidekiq job tracing and correlation across the request → job boundary

**Not for:**

- General Rails code review (use `task-rails-review`)
- Rails performance issues with a known bottleneck (use `task-rails-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Sentry SaaS settings, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                      | What Runs                                           |
| ---------- | ---------------------------------------------------------------- | --------------------------------------------------- |
| `quick`    | Single endpoint, controller action, or job                       | Logging + `ActiveSupport::Notifications` check only |
| `standard` | Default - full Rails observability review                        | All steps                                           |
| `deep`     | Pre-release of a critical Rails service, or post-incident review | All steps + SLI/SLO suggestions for Rails endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                  | Meaning                                                                                               |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-rails-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-rails-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-rails-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-rails-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Ruby / Rails. If invoked as a subagent of a Rails-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-review-observability` instead.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Structured Logging (lograge / semantic_logger / Rails.logger)

Inspect `config/environments/*.rb`, `config/initializers/lograge*.rb`, `config/initializers/semantic_logger*.rb`, and any `Rails.logger.*` callsite in the diff:

- [ ] **Production logger is structured** - `lograge.enabled = true` with JSON formatter, or `semantic_logger` with JSON appender. No raw text logs in production.
- [ ] **`config.lograge.custom_options`** (or semantic_logger payload) injects `request_id`, `user_id` (when authenticated), `tenant_id`, `trace_id`, `span_id`, and any business correlation IDs (`order_id`, `tenant_id`)
- [ ] **`config.filter_parameters`** covers all sensitive keys (`:password`, `:password_confirmation`, `:token`, `:api_key`, `:credit_card`, `:ssn`, `:authorization`) - check the initializer in the diff
- [ ] **No `Rails.logger.info` / `.debug` calls** with sensitive data - inspect new logger calls for tokens, full request bodies on auth endpoints, full PII
- [ ] **Log levels used correctly**: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics
- [ ] **No log spam in hot loops** - `find_each` blocks, serializers, `each` over large collections must not log per-iteration
- [ ] **`tagged_logger`** used for request-scoped tags when `lograge` is not in use (e.g., `Rails.logger.tagged(...)`)
- [ ] **Sidekiq logger** configured (`Sidekiq.logger = Rails.logger` or dedicated structured logger); job context tags (`jid`, `class`, `bid`, `args_summary`) included

### Step 4 - ActiveSupport::Notifications Instrumentation

`ActiveSupport::Notifications` is Rails' built-in instrumentation hook - the canonical way to expose internal events to APM and metrics collectors:

- [ ] **Custom business events instrumented**: any new domain operation (`order.fulfilled`, `payment.charged`, `user.activated`) emitted via `ActiveSupport::Notifications.instrument('event.namespace', payload)` rather than buried in service-object internals
- [ ] **Subscribers exist or are documented**: emitted events have either an in-app subscriber (writing to APM/StatsD) or a documented contract for an external subscriber - emitted-but-unconsumed events are dead weight
- [ ] **Event naming follows the `verb.namespace` convention** (e.g., `process.action_controller`, `sql.active_record`, `enqueue.active_job`) - no ad-hoc names that won't show up cleanly in APM
- [ ] **No high-cardinality fields in event names**: event _name_ is fixed; high-cardinality data (user ID, order ID) goes in the payload, never in the name
- [ ] **Out-of-band Rails internals subscribed when needed**: APM gem (`scout_apm`, `skylight`, `new_relic_rpm`, `ddtrace`) installed and configured; or custom subscribers consuming `process.action_controller`, `sql.active_record`, `perform.active_job` events for self-hosted metrics

### Step 5 - Query Attribution (query_log_tags)

`query_log_tags` annotates every SQL query with controller / action / job context, making APM traces actually useful:

- [ ] **`config.active_record.query_log_tags_enabled = true`** in production (Rails 7+)
- [ ] **`config.active_record.query_log_tags`** includes `:controller`, `:action`, `:job`, `:request_id` at minimum; add `:tenant` if multi-tenant
- [ ] **Custom tags** for app-specific context (`:tenant`, `:feature_flag_cohort`) registered via `ActiveRecord::QueryLogs.taggings`
- [ ] **Tags do not leak PII** - no user IDs, email addresses, or tokens in query log tags

### Step 6 - Distributed Tracing (OpenTelemetry / APM gem)

Inspect tracing initialization (`config/initializers/opentelemetry.rb`, `config/initializers/datadog.rb`, etc.):

- [ ] **Auto-instrumentation enabled** for Rails: `opentelemetry-instrumentation-rails`, `opentelemetry-instrumentation-active_record`, `opentelemetry-instrumentation-active_job`, `opentelemetry-instrumentation-sidekiq`, `opentelemetry-instrumentation-faraday`, `opentelemetry-instrumentation-net_http`, `opentelemetry-instrumentation-redis` - install the ones matching the gems in use
- [ ] **Trace context propagation** via W3C `traceparent` header on outbound HTTP (Faraday middleware, `Net::HTTP` instrumentation)
- [ ] **Sidekiq job tracing**: trace context extracted from job payload on `perform`; new spans linked to the parent request span - not orphaned with a fresh trace ID
- [ ] **ActiveJob tracing** if `Sidekiq` is fronted by `ActiveJob`: instrumentation gem covers both layers
- [ ] **Custom spans for service objects**: long-running orchestrations (`OrderFulfillment.call`) wrap their `.call` in a tracer span so APM traces reflect the business step, not just SQL. Canonical OpenTelemetry-Ruby shape: `OpenTelemetry.tracer_provider.tracer('app').in_span('order.fulfill', attributes: { 'order.id' => order.id }) { ... }`. For Datadog APM: `Datadog::Tracing.trace('order.fulfill') { |span| span.set_tag('order.id', order.id) }`. Cache the tracer at class load (`TRACER = OpenTelemetry.tracer_provider.tracer('app')`) rather than re-resolving per call.
- [ ] **Sampling**: head-based 10-20% for high-traffic apps; always-sample on errors and slow requests

### Step 7 - Sidekiq Observability

Sidekiq has its own middleware chain - request-scoped context does not flow into jobs unless explicitly bridged:

- [ ] **Sidekiq client middleware** captures the current request's `request_id` / `trace_id` / `tenant_id` and stores it on the job payload at enqueue time
- [ ] **Sidekiq server middleware** restores that context on `perform` (e.g., into `Current.attributes`, `RequestStore`, or OTel context)
- [ ] **Job retries logged** with retry count and reason; dead jobs surfaced (Sidekiq dead set monitoring or alert)
- [ ] **Sidekiq metrics**: queue latency, busy workers, retry/dead counts exposed via `sidekiq-prometheus-exporter`, `yabeda-sidekiq`, or APM gem
- [ ] **Sidekiq Web UI** auth-gated in production (already a security check, but flag if observability requires it for diagnosis access)

### Step 8 - Correlation ID and Request Context

- [ ] **Rack middleware** (`ActionDispatch::RequestId` is built-in, but check that load-balancer-injected `X-Request-ID` is honored when present)
- [ ] **Request-scoped context** carried via `ActiveSupport::CurrentAttributes` (Rails 5.2+) for `user_id`, `tenant_id`, `request_id` - reset between requests automatically. Prefer this over the `RequestStore` gem, which is now legacy; flag new code that adds `RequestStore` instead of extending an existing `Current` class.
- [ ] **Outbound HTTP propagates `X-Request-ID`** so downstream services can correlate (Faraday middleware, `Net::HTTP` patch, or APM auto-instrumentation)
- [ ] **`ActiveSupport::Notifications` subscribers** read `Current.user_id` etc. so emitted events carry tenant / user without each emit-site re-fetching it

### Step 9 - Error Tracking (Sentry / Honeybadger / Rollbar - Gem Wiring)

- [ ] **Error-tracker gem installed and initialized**: `sentry-rails`, `honeybadger`, `rollbar`, or equivalent. Initializer in `config/initializers/`
- [ ] **DSN / API key from credentials**, not env-only; not committed to git
- [ ] **`config.before_send`** (or equivalent) scrubs sensitive fields beyond what `filter_parameters` catches: cookies, headers like `Authorization`, `X-Api-Key`
- [ ] **User context attached** when authenticated: `Sentry.set_user(id: current_user.id)` in `ApplicationController` (no email/PII unless privacy policy permits)
- [ ] **Sidekiq integration**: jobs that fail report to error tracker with job class, args summary (no raw args - may contain PII), and retry count
- [ ] **Source maps / release tracking** wired (release identifier set on error reports so deployments can be correlated to error spikes)
- [ ] **Unhandled `rescue_from` errors** still report to the tracker (not silently swallowed by a generic 500 handler)
- [ ] **Test-mode silent**: error tracker disabled or stubbed in `Rails.env.test?` - test failures should not pollute the production tracker

### Step 10 - Health Checks and SLIs (deep depth or explicit request)

Run at `deep` depth or when the user explicitly requests SLI/SLO coverage:

- [ ] **Liveness endpoint** (`/up` or `/health/live`): returns 200 unconditionally as long as the Rails process is responsive. **No DB / Redis / Sidekiq / external checks.** A liveness probe that pings the DB will fail every replica during a routine DB restart and Kubernetes will kill them all simultaneously, taking the app fully down for a survivable blip. Rails 7.1's built-in `/up` (mounted via `Rails::HealthController#show`) is a correct liveness implementation; do not replace it with a deeper check
- [ ] **Readiness endpoint** (`/health/ready`): verifies *own-pod* dependencies the request path requires - DB connection from this pod's pool, Redis connection from this pod's client, in-process caches warmed. **Must NOT include third-party API ping** (Stripe, Twilio, S3, internal microservice). A readiness probe that depends on a third party makes every replica fail readiness simultaneously when that third party degrades; Kubernetes removes all pods and the local outage becomes a cascading outage of an otherwise-recoverable feature. Third-party degradation should surface via the circuit-breaker / retry / bulkhead path, not by removing pods from the load balancer
- [ ] **Dependency-health endpoint** (`/internal/deps` or similar): observability signal for ops dashboards and oncall, **not** wired to Kubernetes pod-removal. This is where third-party reachability checks belong - they answer "is the dependency healthy?" without conflating it with "should this pod receive traffic?". Verify the diff does not point a Kubernetes `readinessProbe` at this endpoint
- [ ] **SLI per critical endpoint**: success rate (non-5xx), p99 latency. Defined as a Prometheus query, Datadog SLO, or in-app metric
- [ ] **SLO target stated** with window (e.g., 99.9% over 30 days for `POST /orders`)
- [ ] **Sidekiq SLI**: queue latency p99 < N seconds for time-sensitive queues; dead-job count under threshold
- [ ] **Alerts page on symptoms** (5xx rate, p99 latency, queue depth), not causes (CPU, memory)

Flag a Rails service with no defined SLI/SLO as a **High** observability gap.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Rails (or accepted from parent dispatcher)
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Structured logging assessed: `lograge` / `semantic_logger` config; `filter_parameters` coverage; no PII in new logger calls; correct log levels
- [ ] `ActiveSupport::Notifications` instrumentation reviewed: business events emitted, subscribers exist, naming convention followed, no high-cardinality event names
- [ ] `query_log_tags` enabled with appropriate tags; no PII in tags
- [ ] Distributed tracing reviewed: auto-instrumentation gems installed for the libraries in use; W3C trace propagation on outbound HTTP and across Sidekiq boundary; custom spans for service objects when warranted
- [ ] Sidekiq middleware reviewed: client middleware captures request context, server middleware restores it; retry/dead visibility configured
- [ ] Correlation ID propagation reviewed: `ActionDispatch::RequestId`, `Current.attributes`, outbound HTTP `X-Request-ID`
- [ ] Error tracker gem wiring reviewed: initialization, scrubbing, user context, Sidekiq integration, release tracking, test-mode silent
- [ ] **Deep depth**: SLIs and health endpoints audited; symptom-based alerting verified
- [ ] Every finding states the missing signal AND what becomes invisible without it - not just "add a log here"
- [ ] Findings ordered by severity; quick wins separated from structural changes
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no observability gaps exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Rails Observability Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Logger:** lograge | semantic_logger | Rails.logger (raw) | other
**Tracing:** OpenTelemetry | New Relic | Datadog APM | Scout | Skylight | none
**Error tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [count by severity: High/Medium/Low]

## Findings

### High Severity (would prevent detection of a Rails production failure)

- **Location:** [file:line, controller, job class, or initializer]
- **Missing:** [the absent signal - log field, AS::Notifications event, query tag, trace span, error-tracker scrubbing, etc.]
- **Impact:** [what becomes invisible or undetectable - e.g., "Sidekiq job failures attributed to wrong request", "p99 latency cannot be derived from current logs", "PII leaks into error tracker"]
- **Fix:** [concrete Rails change with gem and code example - e.g., "Add `lograge.custom_options = ->(event) { { trace_id: event.payload[:headers]['X-Trace-Id'] } }`"]

### Medium Severity (reduces Rails diagnosis speed)

[Same structure]

### Low Severity (nice-to-have, no current blind spot)

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Adopt OpenTelemetry instrumentation across all Rails services", "Migrate from Rails.logger to semantic_logger for JSON output", "Define SLOs for /orders, /checkout endpoints", "Wire `query_log_tags` for tenant attribution"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized instrumentation addition) or `[Delegate]` (cross-service tracing rollout, SLO workshop, alerting overhaul).

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `request_id` and `tenant_id` to lograge custom_options in config/environments/production.rb"]
2. **[Delegate]** [High] [scope: Sidekiq] - [one-line action, e.g., "Bridge request trace context into Sidekiq jobs - spawn middleware-rollout subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no observability gaps were found._

## No Gaps Found

[State explicitly if observability is adequate - do not omit this section silently when no findings exist]
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting "missing log" findings without stating what becomes invisible
- Recommending more logging without considering log volume cost and alerting noise
- Suggesting metrics with high-cardinality labels (request ID, user ID, raw URL) - these break aggregation
- Confusing logging, metrics, and tracing - they answer different questions (what / how often / why this specific request)
- Reviewing infra-level config (Datadog dashboards, Sentry SaaS settings, log forwarder agents) - those are not in source code; this skill stays at the Rails gem and library level
- Conflating observability review with general code review or performance review - delegate those to their workflows
- Recommending observability tooling without addressing alerting - signals nobody acts on are wasted
