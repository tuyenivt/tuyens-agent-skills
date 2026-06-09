---
name: task-rails-review-observability
description: Rails observability review - AS::Notifications, lograge, Sidekiq tracing, Rack correlation IDs, Sentry/Honeybadger/Rollbar.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, observability, logging, metrics, tracing, sidekiq, workflow]
  type: workflow
user-invocable: true
---

# Rails Observability Review

Stack-specific delegate of `task-code-review-observability`. Focuses on whether Rails production behavior is **visible, diagnosable, and alertable** at the gem/library level. Infra config (ELK, Datadog SaaS, Sentry dashboards) is out of scope.

## When to Use

Rails PR observability check; pre-release for new service or major feature; post-incident "diagnosis was slow"; adopting `lograge`/`semantic_logger`/OpenTelemetry/`query_log_tags`; auditing Sidekiq tracing and request -> job correlation.

## Depth

| Depth      | What Runs                         |
| ---------- | --------------------------------- |
| `standard` | All steps except 10 (default)     |
| `deep`     | All steps + SLI/SLO suggestions   |

## Invocation

`/task-rails-review-observability [<branch>|pr-<N>] [standard|deep]` - current branch vs base; fails fast on trunk. Subagent invocation with pre-read artifacts skips Steps 1-3.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-observability`. Record **logger** (lograge / semantic_logger / raw), **tracer** (OpenTelemetry / Datadog / New Relic / Scout / Skylight / none), **error tracker** (Sentry / Honeybadger / Rollbar / none).

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check`. On approval, read diff and log once. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - Logging Hygiene

Inspect `config/environments/*.rb`, `config/initializers/lograge*.rb`/`semantic_logger*.rb`, every diffed `Rails.logger.*` callsite.

- [ ] **Production logger is structured** - `lograge.enabled = true` with JSON formatter, or `semantic_logger` JSON appender. No raw text logs in production
- [ ] **Every new logger call**: structured payload (not interpolated string), correct level (`error` actionable / `warn` recoverable / `info` state transition / `debug` verbose), no PII, not inside an unbounded loop
- [ ] **Sidekiq logger** structured (`Sidekiq.logger = Rails.logger` or dedicated); job context tags (`jid`, `class`, `args_summary`)

`filter_parameters` coverage belongs to `task-rails-review-security`. Cross-flag here only when a new log line clearly leaks fields the security review wouldn't catch (e.g., custom `params.to_unsafe_h` log).

### Step 5 - Business Events (AS::Notifications & custom spans)

Treat `ActiveSupport::Notifications` events and tracer spans as **one axis** - both answer "is this domain operation visible?" One finding per missing-visibility callsite, not one per signal type.

- [ ] **Custom business events instrumented**: domain operations (`order.fulfilled`, `payment.charged`) emitted via `ActiveSupport::Notifications.instrument` AND/OR wrapped in a tracer span (OTel `tracer.in_span`, Datadog `Datadog::Tracing.trace`)
- [ ] **Subscribers exist or are documented** for emitted events
- [ ] **Event naming `verb.namespace`**; high-cardinality data (user/order IDs) in payload, not name
- [ ] **Rails internals consumed**: APM gem (`scout_apm`, `skylight`, `new_relic_rpm`, `ddtrace`) installed, or custom subscribers consuming `process.action_controller`, `sql.active_record`, `perform.active_job`

### Step 6 - Correlation Across Layers

Skip when diff doesn't touch correlation config or add new Sidekiq jobs / outbound HTTP / async paths.

- [ ] **`ActionDispatch::RequestId`** enabled; LB `X-Request-ID` honored when present
- [ ] **Request-scoped context** via `ActiveSupport::CurrentAttributes` for `user_id`, `tenant_id`, `request_id`. Flag new code adding the legacy `RequestStore` gem instead of extending `Current`
- [ ] **Sidekiq middleware bridge**: client middleware captures `request_id`/`trace_id`/`tenant_id` at enqueue; server middleware restores it on `perform` (into `Current` or OTel context). Without this, new jobs orphan their trace
- [ ] **Outbound HTTP propagates `traceparent` (W3C) + `X-Request-ID`** - Faraday middleware, `Net::HTTP` patch, or APM auto-instrumentation
- [ ] **`config.active_record.query_log_tags_enabled = true`** in production (Rails 7+) with `query_log_tags` covering `:controller`, `:action`, `:job`, `:request_id` (+ `:tenant` if multi-tenant). No PII in tags

### Step 7 - Tracing Setup (initializer/gem-change PRs only)

Skip unless diff touches `config/initializers/opentelemetry.rb`, `config/initializers/datadog.rb`, or adds/removes a tracer gem.

- [ ] **Auto-instrumentation gems**: `opentelemetry-instrumentation-rails`, `-active_record`, `-active_job`, `-sidekiq`, `-faraday`, `-net_http`, `-redis` as appropriate
- [ ] **ActiveJob tracing** if Sidekiq fronted by ActiveJob - both layers covered
- [ ] **Sampling**: head-based 10-20% for high traffic; always-sample on errors and slow requests
- [ ] **Tracer cached at class load** for custom-span paths

### Step 8 - Sidekiq Observability

- [ ] **Job retries logged** with retry count and reason; **dead jobs alerted**
- [ ] **Sidekiq metrics** (queue latency, busy workers, retry/dead counts) via `sidekiq-prometheus-exporter`, `yabeda-sidekiq`, or APM gem

Sidekiq Web auth-gating belongs to security; request-id bridging belongs to Step 6.

### Step 9 - Error Tracker Capture

Setup checks (gem install, DSN-from-credentials, test-mode silent, release tracking) fire only on initializer diffs. Every PR runs:

- [ ] **Scrub beyond `filter_parameters`** in `before_send`: cookies, `Authorization`, `X-Api-Key`
- [ ] **User context** when authenticated: `Sentry.set_user(id: current_user.id)` in `ApplicationController` (no email/PII unless privacy policy permits)
- [ ] **Sidekiq integration**: failed jobs report with class, args summary (not raw args), retry count
- [ ] **Unhandled `rescue_from` errors** still report to tracker (not swallowed). Inspect every new `rescue` in the diff
- [ ] **DSN/API key in credentials**, test-mode silent (setup PRs only)

### Step 10 - Health Checks and SLIs (deep depth or explicit request)

Use skill: `ops-observability` for liveness/readiness shapes and SLI/SLO definitions. Rails specifics:

- Liveness: Rails 7.1's built-in `/up` is correct - 200 unconditionally, no dependency checks
- Readiness: own-pod DB pool + Redis client + warmed caches; **no third-party pings**
- Dependency-health (`/internal/deps`): ops-dashboard signal, not a probe target
- **Sidekiq SLI** for time-sensitive queues

A Rails service with no SLI/SLO is a **High** observability gap.

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

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: Sidekiq] - [one-line action]

`[Implement]` = localized. `[Delegate]` = cross-service tracing rollout / SLO workshop / alerting overhaul. Order Must > Recommend > Question. Omit if no gaps; state "No observability gaps found" when clean.
```

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent); logger + tracer + error-tracker recorded
- [ ] Step 4: every new `Rails.logger.*` call assessed; PII overlap with security only when novel
- [ ] Step 5: business events and custom spans assessed as one axis
- [ ] Step 6: ran when diff added jobs / outbound HTTP / async paths; skipped with note otherwise
- [ ] Step 7: tracing setup checked only on initializer/gem change
- [ ] Step 8: retry/dead visibility and Sidekiq metrics covered
- [ ] Step 9: scrub/user-context/Sidekiq capture every PR; setup checks only on initializer change
- [ ] Step 10 (deep): liveness/readiness/SLI via `ops-observability`
- [ ] Step 11: report via `review-report-writer`; confirmation printed
- [ ] Every finding states the missing signal AND what becomes invisible; Next Steps ordered Must > Recommend > Question

## Avoid

- "Missing log" findings without stating what becomes invisible
- More logging without considering volume cost and alerting noise
- Metrics with high-cardinality labels (request ID, user ID, raw URL)
- Conflating logging / metrics / tracing - different questions (what / how often / why this request)
- Reviewing infra-level config - stays at gem/library level
- Filing the same correlation-ID gap as separate findings under logging + Sidekiq + outbound HTTP
- Filing `filter_parameters` coverage as observability - that's security
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
