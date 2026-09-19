---
name: task-rails-review-observability
description: Rails observability review - AS::Notifications, lograge, Sidekiq tracing, Rack correlation IDs, Sentry/Honeybadger/Rollbar.
agent: rails-observability-engineer
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

| Depth      | What Runs                                                     |
| ---------- | ------------------------------------------------------------- |
| `standard` | All steps (default); Step 10 only when its own trigger fires  |
| `deep`     | All steps; Step 10 always                                     |

## Invocation

`/task-rails-review-observability [<branch>|pr-<N>] [standard|deep] [--base <branch>]` - current branch vs base; fails fast on trunk. Subagent invocation with pre-read artifacts skips Steps 2-3 (Step 1 still runs - behavioral rules are per-context); the logger / tracing / error-tracker determinations are still made, from the artifacts in hand (Gemfile, initializers), and skip notes are omitted (a subagent run emits no Summary).

**Investigation mode** (no PR/diff: post-incident "diagnosis was slow" audit): skip Step 3 (and the round gate). Scope = the paths involved in the incident (controllers, jobs, clients) plus their logging/tracing/tracker config; run Steps 4-10 against current code ("diffed" checks apply to every callsite in scope; a step whose surface doesn't exist in scope states N/A; Step 10 runs regardless of depth). There is no merge to block in this mode: the pre-existing-gap carve-outs don't apply - everything in scope files at its severity. Fill the Summary's `Target:` slot, skip `review-report-writer` checkpointing, and emit the report body as the response - no file is written. Every "skip when the diff ..." gate reads as "skip when the in-scope code has no such surface": gating removes atomic loads and rows with no matching code, never a row whose surface is present.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. Where the project's declared stack and its code disagree, record what the code does and note the divergence. If not Rails, redirect to `/task-code-review-observability`. Record **logger** (lograge / semantic_logger / Rails.logger (raw) / other - name the gem), **tracing** (OpenTelemetry / New Relic / Datadog APM / Scout / Skylight / none), **error tracker** (Sentry / Honeybadger / Rollbar / none) - the Summary's three slots, each as of the head (post-diff) state; a declared stack the code contradicts is recorded as the code has it, with the divergence in `Notes:`.

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-observability`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface fail-fast verbatim and stop. Skip if parent passed pre-read artifacts.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` equals the captured `head_sha` and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits since prior observability review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 11 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and log once.

### Step 4 - Logging Hygiene

Inspect `config/environments/*.rb`, `config/initializers/lograge*.rb`, every diffed `Rails.logger.*` callsite.

- [ ] **Production logger is structured** - `config.lograge.enabled = true` with `Lograge::Formatters::Json`, or `rails_semantic_logger` with `config.rails_semantic_logger.format = :json` in the environment file. No raw text logs in production. (A pre-existing raw logger the diff doesn't touch is surfaced as `[Recommend]` context, not a merge blocker)
- [ ] **Every new logger call**: structured payload (not interpolated string), correct level (`error` actionable / `warn` recoverable / `info` state transition / `debug` verbose), no PII or secrets (tokens, API keys - `removal` kind), not inside an unbounded loop
- [ ] **Sidekiq logger** structured (`config.logger.formatter = Sidekiq::Logger::Formatters::JSON.new` inside `Sidekiq.configure_server`, which keeps the `jid` / `class` context `Sidekiq::Context` sets); job context tags (`jid`, `class`, `args_summary`)

`filter_parameters` coverage belongs to `task-rails-review-security`. Cross-flag here only when a new log line clearly leaks fields the security review wouldn't catch (e.g., custom `params.to_unsafe_h` log).

The pre-existing-gap rule generalizes across Steps 4-9: config or instrumentation the diff doesn't touch files as `[Recommend]` context, never a merge blocker (investigation mode suspends this - see Invocation). Exception: a pre-existing gap that a **new surface in the diff newly depends on** (a new job with no middleware bridge to restore its context, a new outbound call with no propagation) files at full severity, anchored to the new callsite - the diff created the blind spot even though the config predates it. This carve-out decides where the finding is anchored and that it is filed at all - not its published label. Hand it to the verify pass as `newly reachable via <the new callsite>`, which is the kind-change that skill recognises; where it still rules `Pre-existing`, the verified `Label` governs what is published.

### Step 5 - Business Events (AS::Notifications & custom spans)

Treat `ActiveSupport::Notifications` events and tracer spans as **one axis** - both answer "is this domain operation visible?" One finding per missing-visibility callsite, not one per signal type. The same merging applies across Steps 4/5: a callsite lacking both a structured log (an interpolated-string log is not one) and a business event files once, here, with the log fix folded into the same finding.

- [ ] **Custom business events instrumented**: domain operations (`fulfilled.order`, `charged.payment` - Rails orders these `verb.namespace`, as in `perform.active_job`) emitted via `ActiveSupport::Notifications.instrument` AND/OR wrapped in a tracer span (OTel `tracer.in_span`, Datadog `Datadog::Tracing.trace`)
- [ ] **Subscribers exist or are documented** for emitted events
- [ ] **Event naming `verb.namespace`**; high-cardinality data (user/order IDs) in payload, not name
- [ ] **Rails internals consumed**: APM gem (`scout_apm`, `skylight`, `newrelic_rpm`, `datadog` - renamed from `ddtrace` in dd-trace-rb 2.0) installed, or custom subscribers consuming `process_action.action_controller`, `sql.active_record`, `perform.active_job`

### Step 6 - Correlation Across Layers

Skip when diff doesn't touch correlation config (request-id middleware, `CurrentAttributes`, tracer/instrumentation initializers) or add new Sidekiq jobs / outbound HTTP / async paths.

- [ ] **`ActionDispatch::RequestId`** enabled; LB `X-Request-ID` honored when present
- [ ] **Request-scoped context** via `ActiveSupport::CurrentAttributes` for `user_id`, `tenant_id`, `request_id`. Flag new code adding the legacy `RequestStore` gem instead of extending `Current`
- [ ] **Sidekiq middleware bridge**: client middleware captures `request_id`/`trace_id`/`tenant_id` at enqueue; server middleware restores it on `perform` (into `Current` or OTel context). Without this, new jobs orphan their trace
- [ ] **Outbound HTTP propagates `X-Request-ID`** (+ W3C `traceparent` when a tracer is configured - with `Tracing: none`, request-ID propagation alone satisfies this) - Faraday middleware, `Net::HTTP` patch, or APM auto-instrumentation
- [ ] **`config.active_record.query_log_tags_enabled = true`** in production (Rails 7+) with `query_log_tags` covering `:controller`, `:action`, `:job`. `:request_id` and `:tenant` are **not** built-in taggings - a bare symbol resolves against `ActiveSupport::ExecutionContext`, returns nil and is dropped silently, so they must be hash entries with a callable (`{ request_id: ->(ctx) { ctx[:controller]&.request&.request_id } }`). A config listing them as bare symbols emits no such tag - check the form, not just the presence. No PII in tags

### Step 7 - Tracing Setup (initializer/gem-change PRs only)

Skip unless the diff touches an initializer that configures a tracer (`opentelemetry.rb`, `datadog.rb`, or any other name) or adds/removes a tracer gem.

- [ ] **Exporter configured** - `opentelemetry-exporter-otlp` (or vendor agent) plus endpoint env; an SDK with no exporter is inert. Gate instrumentation per environment (no dev/test span noise)
- [ ] **Auto-instrumentation gems**: `opentelemetry-instrumentation-rails`, `-active_record`, `-active_job`, `-sidekiq`, `-faraday`, `-net_http`, `-redis` as appropriate
- [ ] **ActiveJob tracing** if Sidekiq fronted by ActiveJob - both layers covered
- [ ] **Sampling**: head-based 10-20% for high traffic; keeping every errored or slow trace needs tail-based sampling (a head sampler decides before the outcome is known)
- [ ] **Tracer cached at class load** for custom-span paths

### Step 8 - Sidekiq Observability

Skip when the diff touches no job code or Sidekiq runtime config (an instrumentation-gem add alone belongs to Step 7; state the skip).

- [ ] **Job retries logged** with retry count and reason; **dead jobs alerted**
- [ ] **Sidekiq metrics** (queue latency, busy workers, retry/dead counts) via `sidekiq-prometheus-exporter`, `yabeda-sidekiq`, or APM gem

Sidekiq Web auth-gating belongs to security; request-id bridging belongs to Step 6.

### Step 9 - Error Tracker Capture

Setup checks (gem install, DSN-from-credentials, test-mode silent, release tracking) fire only on *error-tracker* initializer diffs (investigation mode: on in-scope tracker config). Every PR runs the checks below; a gap in pre-existing tracker config the diff doesn't touch files as `[Recommend]` context, not a merge blocker (same treatment as Step 4's pre-existing logger):

- [ ] **Scrub beyond `filter_parameters`** in the tracker's hook (Sentry `before_send`, Honeybadger `before_notify`, Rollbar `scrub_fields` / `transform`): cookies, `Authorization`, `X-Api-Key`
- [ ] **User context** when authenticated: `Sentry.set_user(id: current_user.id)` / `Honeybadger.context(user_id:)` / `Rollbar.scope(person: { id: })` in `ApplicationController` (no email/PII unless privacy policy permits)
- [ ] **Sidekiq integration**: failed jobs report with class, args summary (not raw args), retry count; sentry-sidekiq `report_after_job_retries` decides every-retry vs retries-exhausted reporting
- [ ] **Rescued 5xx-class errors still report** - a `rescue_from` or in-job `rescue` that logs and renders must call `Rails.error.report` (under sentry-rails only with `config.rails.register_error_subscriber` on, or nothing receives it; Honeybadger subscribes on its own, Rollbar does not subscribe to `Rails.error` - call its notifier); handled 4xx domain errors are deliberately not reported. Inspect every new `rescue` in the diff
- [ ] **DSN/API key in credentials**, test-mode silent (setup PRs only)
- [ ] **`Error tracker: none`**: every check above is N/A - file one finding that no tracker exists, at High when the diff adds a failure path that would otherwise go unreported, Medium otherwise. Do not file the scrub, user-context, Sidekiq-capture, `rescue_from`-reporting or DSN rows individually against a tracker that is absent

### Step 10 - Health Checks and SLIs (deep depth, explicit request, or a PR introducing a service or a feature with its own success/latency contract)

Use skill: `ops-observability` for SLI/SLO definitions (it carries no probe shapes - the liveness/readiness rules are the Rails specifics below); its assessment block is not emitted - each gap becomes a finding here whose `Missing:` names the signal and its kind (`absent - <log field | metric | trace span | context propagation | alert | dashboard | SLO>` / `removal` / `replacement` / `misuse`), at this lens's severity:

- Liveness: Rails 7.1's built-in `/up` is correct - 200 unconditionally, no dependency checks
- Readiness: own-pod DB pool + Redis client + warmed caches; **no third-party pings**
- Dependency-health (`/internal/deps`): ops-dashboard signal, not a probe target
- **Sidekiq SLI** for time-sensitive queues

A Rails service with no SLI/SLO is a **High** observability gap - when the PR introduces a new critical deployable service, or a feature with its own user-visible success/latency contract (Medium for a non-critical service). A feature riding existing endpoints and existing SLOs does not trigger it. On infra-only PRs (tracing setup, gem bumps), file the absence as a `[Recommend]` finding instead of High. In investigation mode, a missing SLI/SLO for the audited path files High - the mode exists because diagnosis failed.

### Verify Findings (all depths and modes)

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, and fill the Summary's `Findings verified:` line from its tally in the atomic's Summary form; dropped rows appear only in the tally, never in the body. Investigation mode skips it (the skill requires a diff; there is none): instead re-read each cited `file:line` at `HEAD`, drop findings the code does not support, and report `Findings verified: inline (no diff)`. On round 2+, after verification, re-project the prior report's findings - every tier, the file at the handle's `report_path` - into reconcile's parse shape - one `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its `Label:` line (the label alone - a trailing `_(carried from round <N>)_` group is re-emitted on the heading as its own group; when the prior report wrote no label, the one its tier maps to in Next Steps) and the `file:line` prefix of its Location line, keeping a `_(pre-existing)_` annotation on the heading (verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_` - reconcile matches `_(pre-existing)_` exactly), with its `Missing` line written as `Issue:` (the smell) - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line and tally render as `## Prior Round Reconciliation`; `Still open` and `Needs re-check` rows carry into their prior tier at their prior label with `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the Label value and the prior Location annotation kept - the table row and a Next Steps entry are its only other appearances, and a carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried; the reconciliation table is the one place a label outside `[Must]` / `[Recommend]` is written. Subagent runs skip verification and reconciliation both - the parent verifies and reconciles its own merged set once.

### Step 11 - Write Report

Standalone runs (resolved diff): Use skill: `review-report-writer` with `report_type: review-observability` and every field the writer requires - `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `scope: +obs`, `depth` as invoked, `stack = ruby-rails`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line. Subagent runs (parent passed pre-read artifacts): skip the writer and return only `## Findings` with its tier sections and any `out of lens` lines - no Summary, no Recommendations, no Next Steps, no file - the parent owns the report. (Investigation mode skips the writer too and emits the body as the response - see Invocation.)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

Fill rules: `Findings verified:` carries the verify tally on standalone runs and the literal `inline (no diff)` in investigation mode (subagent runs emit no Summary). Verify annotations appear on standalone runs only; a finding sits in the section matching its severity while its `Label:` line carries the published label, so a `[Recommend]` inside a higher section is correct, not a mismatch to fix. `Target:` appears only in investigation mode (it replaces writer checkpointing); omit otherwise. **One defect, one finding.** Several checklist rows, or several call sites, that describe one underlying defect file once - at the site where the fix lands, with the other sites named in the Location line. Genuinely distinct defects at one site, with different fixes, stay separate. Anchor to the narrowest `file:line` the fix touches; a range only when the fix spans contiguous lines. There is no finding count to hit or stay under: file every defect that meets the severity bar and nothing that does not. Two findings are the same defect when one fix removes both; different fixes at one site, or one fix that only masks the second, are two. Pre-existing gaps filed as `[Recommend]` context carry the verify pass's `_(pre-existing)_` on the Location line (subagent runs carry none - the parent verifies), under Medium when the gap would slow diagnosis of a failure the diff can cause, Low otherwise. Tiers: **High** = would prevent detection of a production failure; **Medium** = diagnosis materially slower, or data leaks into telemetry; **Low** = polish. This lens's tier governs over an atomic's severity.

```markdown
## Rails Observability Review Summary

- **Stack Detected:** Ruby <version> / Rails <version>
- **Logger:** lograge | semantic_logger | Rails.logger (raw) | other
- **Tracing:** OpenTelemetry | New Relic | Datadog APM | Scout | Skylight | none
- **Error tracker:** Sentry | Honeybadger | Rollbar | none
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Target:** <path(s)>   {investigation mode only}
- **Overall:** Adequate | Gaps Found - [High/Medium/Low count, zeros included]
- **Findings verified:** <per fill rules: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}` from `review-finding-verify` | inline (no diff)>
- **Notes:** <the Step 2 declared-vs-code divergence, each Step 6-8 or Step 10 skip with its trigger>   {omit when none}

## Findings

### High Severity

- **Location:** [file:line, controller, job, or initializer] [+ the verify Annotation - `_(pre-existing)_` / `_(pre-existing; newly reachable via ...)_` / `_(unverified: <reason>)_` / `_(mechanism: <actual>)_`]
- **Label:** [Must] | [Recommend]   {the verified Label; else the severity mapping in Next Steps; a carried finding appends `_(carried from round <N>)_`}
- **Missing:** [the signal and its kind - `absent - <log field | metric | trace span | context propagation | alert | dashboard | SLO>` | `removal - <what leaks>` | `replacement - <what to replace>` | `misuse - <what>`]
- **Impact:** [what becomes invisible - e.g. "Sidekiq failures attributed to wrong request"]
- **Fix:** [concrete Rails change with gem and code]

### Medium Severity
[Same structure]

### Low Severity
[Same structure]

_Omit empty sections; if all are omitted, state `No observability gaps found.`_

## Prior Round Reconciliation

[table, note line and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Recommendations
[Structural changes spanning multiple PRs; omit when none]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: Sidekiq] - [one-line action]

`[Implement]` = localized. `[Delegate]` = cross-service tracing rollout / SLO workshop / alerting overhaul. Severity maps to intent: High -> [Must], Medium/Low -> [Recommend]; when the verify pass changed a finding's label, its verified `Label` wins over this mapping. No other label is written. `[Implement]` / `[Delegate]` and `[Must]` / `[Recommend]` are independent axes - a `[Delegate]` may carry `[Must]`. Order Must > Recommend. Omit if no gaps.
```


**A defect this lens does not own is reported, never dropped.** Another lens's category, a plain correctness bug, or something a gate excluded but the reading surfaced: one `- **out of lens:** file:line - <the defect in one sentence, and the workflow that owns it>` line at the end of `## Findings` - untiered, uncounted in `Overall`, absent from Next Steps; the parent drafts it as a finding. Atomics loaded by any step feed findings into this template; their own output blocks are not emitted. The exception is a defect that makes this lens's own findings unreachable or wrong (a query that always raises, a guard that never runs): that files here at its draft severity and passes through verify like any other, because it changes what the rest of the report means.

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent; investigation mode: Step 3 skipped); `report_type: review-observability` passed; round decided from the handle before the diff was read (or the stop line printed); logger + tracing + error-tracker recorded
- [ ] Step 4: every new `Rails.logger.*` call assessed; PII overlap with security only when novel
- [ ] Step 5: business events and custom spans assessed as one axis
- [ ] Step 6: ran when the diff touched correlation config *or* added jobs / outbound HTTP / async paths; skipped with note only when neither applied
- [ ] Step 7: tracing setup checked only on initializer/gem change (investigation mode: on in-scope tracer config, or N/A when none)
- [ ] Step 8: retry/dead visibility and Sidekiq metrics covered, or skipped with note (no job code or Sidekiq config in the diff)
- [ ] Step 9: scrub/user-context/Sidekiq capture every PR; setup checks only on initializer change
- [ ] Step 10 ran when triggered (deep / explicit request / service-introducing PR / investigation mode) via `ops-observability`, or skip stated
- [ ] Verify pass ran (inline in investigation mode; skipped as subagent - the parent verifies); tally or omission per fill rules; prior findings projected and reconciled on round 2+
- [ ] Step 11: report via `review-report-writer` (subagent: findings returned to parent; investigation mode: body emitted as the response); confirmation printed when the writer ran
- [ ] Every finding states the missing signal AND what becomes invisible; `out of lens` lines emitted for defects outside the lens; Next Steps ordered Must > Recommend

## Avoid

- "Missing log" findings without stating what becomes invisible
- More logging without considering volume cost and alerting noise
- Metrics with high-cardinality labels (request ID, user ID, raw URL)
- Conflating logging / metrics / tracing - different questions (what / how often / why this request)
- Reviewing infra-level config - stays at gem/library level
- Filing the same correlation-ID gap as separate findings under logging + Sidekiq + outbound HTTP
- Filing `filter_parameters` coverage as observability - that's security
