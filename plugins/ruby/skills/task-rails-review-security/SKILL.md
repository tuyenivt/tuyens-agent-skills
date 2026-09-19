---
name: task-rails-review-security
description: Rails security review - strong params, Devise/JWT, Pundit/CanCanCan, mass assignment, CSRF, OWASP Top 10.
agent: rails-security-engineer
metadata:
  category: backend
  tags: [ruby, rails, security, pundit, devise, owasp, workflow]
  type: workflow
user-invocable: true
---

# Rails Security Review

Stack-specific delegate of `task-code-review-security`. Always full depth - security has cliff-edged consequences; scope by file, not depth.

## When to Use

Rails PR security regression check; pre-deploy hardening on auth/authz/upload/payment/PII paths; Pundit or strong-params drift sweep; Devise/JWT flow audit.

## Severity Rubric

| Severity | Trigger |
| -------- | ------- |
| **Critical** (block deploy) | Unauth RCE, auth bypass (incl. JWT decode with signature verification disabled or `alg: none` accepted), mass data exfiltration, SQLi on prod path, shell interpolation, `Marshal.load` / `YAML.unsafe_load` (or `load`/`safe_load` with `permitted_classes` widened; bare `YAML.load` raises `Psych::DisallowedClass` on Ruby 3.1+ and is not itself the vector, and `aliases: true` is an alias-expansion DoS, filed Medium) / `ERB.new(user_input).result` on untrusted input, secrets/`master.key` committed, `permit!`/`to_unsafe_h` on a model whose **schema** exposes role/admin/tenant/owner/billing fields (judge by table, not by diff) |
| **High** (block merge) | Authenticated privilege escalation, IDOR via `Model.find(params[:id])` with no `authorize` or policy scoping, SSRF to cloud metadata, missing `authorize`/`verify_authorized` (a policy class no controller invokes is this defect, not a second one), a `Scope#resolve` returning `scope.all` outside an admin branch, a webhook with no replay guard on the provider event id, `Sidekiq::Web` or another admin mount reachable in production without auth, JWT claim validation disabled (`exp`/`aud`/`iss`) or no revocation strategy (`jti` denylist), refresh or API tokens stored unhashed, open `redirect_to params[:return_to]` with `raise_on_open_redirects` off, raw-SQL interpolation reachable only through a framework guard (`disallow_raw_sql!` on `.order`/`.pluck`; unguarded paths stay Critical), path traversal via `send_file(params[:path])`, missing CSRF on cookie-auth POST, webhook HMAC compared with `==`, CORS with a reflecting or dynamic `origins` block and `credentials: true` (the literal `'*'` plus credentials raises at boot), unauthorized `turbo_stream_from`, raw `render json: @model` exposing sensitive columns |
| **Medium** | Hardening gap with mitigation present, `force_ssl` off or `config.hosts` empty in production, secrets in ENV instead of credentials, `Rack::Attack` absent or weak on an auth or expensive-search endpoint, non-prod debug gem reachable in production (`letter_opener`, `web-console`), unfixed `bundle audit` advisory with a known exploit path (Low below that), `YAML.load` / `safe_load` with `aliases: true`, open `redirect_to params[:return_to]` with `raise_on_open_redirects` on (same-host paths still reachable), missing `filter_parameters` entry, raw `render json:` over-exposure of non-sensitive columns, `skip_authorization`/`skip_after_action :verify_authorized` without stated rationale, `Model.find` + `authorize` where scoping would 404 (existence leak) |
| **Low** | Defense-in-depth, advisories below actively-exploited threshold |

**Combined-finding rule.** N actions sharing one missing authorization gate (skipped `before_action`, absent `verify_authorized` enforcement, controller-wide policy hole) file as **one** finding per controller at elevated severity (one level above the worst individual action, capped at Critical), citing the worst payload as the attack scenario. Two defects on one code path with distinct attack chains stay separate findings even when one fix touches both (an unverified JWT signature and an unvalidated `exp` are two) - distinct attack chains, not distinct fixes, is the test here, and it overrides the Output Format's general one-defect-one-finding rule. Findings with their own distinct attack chain (SQLi, path traversal, mass assignment) file separately and do **not** restate the missing-authz dimension - the combined finding owns it.

## Invocation

`/task-rails-review-security [<branch>|pr-<N>] [--base <branch>]` - current branch vs base; fails fast on trunk. Subagent invocation with pre-read artifacts skips Steps 2-3 (Step 1 still runs - behavioral rules are per-context); still record Step 2's auth/authz flavors from the artifacts in hand (Gemfile, `app/policies/`) - Steps 5-6 gate on them in every mode. A check whose deciding config is genuinely outside the evidence in hand (an initializer or base controller not readable in this run): file `[Recommend]` with `verify: <what to check>` in its Fix rather than asserting or skipping; a file read in full, or shown absent from a fully listed tree, is evidence.

**Audit mode** (no PR/diff: Pundit / strong-params drift sweep, Devise/JWT flow audit): skip Step 3 (and the round gate). Scope = the named surface, read as the code that implements it, not everything reachable through it - a flow audit covers credential issuance and verification (auth config, auth controllers, the `authenticate!` / `require_role!` implementation), not every controller sitting behind them. None named = `app/controllers` + `app/policies` for an authz sweep, auth config + custom auth controllers for a flow audit. Run Steps 4-9 against current code - "diff"-worded checks and gates read as "the resolved surface"; skip axes with no matching surface, state the skip; Step 5 runs for a flow audit only, never for an authz sweep. Severity tiers keep their meanings; read `block deploy/merge` as fix-priority ranks, not gates. Verify: skip `review-finding-verify` (it requires a diff) - instead re-read each cited `file:line` at `HEAD`, drop findings the code does not support, and report `Findings verified: inline (no diff)`. Fill the Summary's `Target:` slot, skip `review-report-writer` checkpointing, and emit the report body as the response - no file is written. Every "skip when the diff ..." gate reads as "skip when the in-scope code has no such surface": gating removes atomic loads and rows with no matching code, never a row whose surface is present.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. Where the project's declared stack and its code disagree, record what the code does and note the divergence. If not Rails, redirect to `/task-code-review-security`. Record **auth flavor** (Devise / JWT / custom / hybrid when two coexist, `devise-jwt` included - record both and run each one's bullets) and **authz flavor** (Pundit / CanCanCan / custom) - flavor-specific bullets below run only for the detected flavor.

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-security`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface fail-fast verbatim and stop. Skip if parent passed pre-read artifacts.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` equals the captured `head_sha` -> print `No new commits since prior security review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 10 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and log once.

### Step 4 - OWASP Walk (Rails Lens)

Use skill: `rails-security-patterns` for canonical rules. Walk the OWASP axes below against the diff; skip an axis when the diff cannot exercise it (state the skip).

| Axis (OWASP Top 10:2025) | Rails check |
| ---- | ----------- |
| A01 Broken Access Control | Every diffed action calls `authorize` (Pundit) or `load_and_authorize_resource` (CanCanCan); no IDOR; tenant isolation; SSRF - no `Net::HTTP.get(URI(user_input))` without a hostname allowlist |
| A02 Security Misconfiguration | `force_ssl`, `config.hosts`, `protect_from_forgery`, CSP set; admin and debug mounts auth-gated in production; error pages do not leak |
| A03 Software Supply Chain Failures | `bundle audit` clean; `bin/importmap audit` for JS; lockfile changes reviewed |
| A04 Cryptographic Failures | Rails credentials for secrets; AR encryption for sensitive columns; bcrypt via `has_secure_password` |
| A05 Injection | No interpolation in `where`/`find_by_sql`/`Arel.sql`; `params[:sort]` allowlisted; no shell-out with user input; XSS - no `html_safe`/`raw`/unescape on user input (Step 7) |
| A06 Insecure Design | Pundit policy per API-exposed model; `ApplicationPolicy` default-denies; rate limiting on sensitive endpoints |
| A07 Authentication Failures | Session / JWT validation (signature, `exp`, `aud`, `iss`); CSRF on cookie-auth POST; no credentials in VCS |
| A08 Software or Data Integrity Failures | No `Marshal.load` on user input; no `YAML.unsafe_load`, no widened `permitted_classes`, no `aliases: true`; webhook signatures verified |
| A09 Logging and Alerting Failures | `filter_parameters` covers password/token/secret/ssn/api_key/credit_card/authorization; no PII in `Rails.logger`; auth failures logged |
| A10 Mishandling of Exceptional Conditions | No fail-open on exception (a rescue that renders success, a `return` that skips the authz filter); abnormal input never bypasses a guard |

### Step 5 - Authentication (only when the diff touches auth code)

"Touches auth" means the diff changes auth configuration, an auth controller, or a session / token / password path - not merely that new code sits behind an inherited `authenticate!`. A new endpoint under existing auth exercises Step 6, not Step 5.

Run the detected flavor's bullet (Devise or JWT); the Session / Password / Secrets bullets are flavor-independent and always run when the diff touches auth.

- **Devise**: `:lockable`/`:trackable`/`:confirmable`/`:rememberable` per threat model; `password_length >= 8`; `config.paranoid = true` (global - hides account existence across recover, confirm and unlock); custom controllers preserve `protect_from_forgery` + rate limit
- **JWT**: signature pinned (no `alg: none`); HMAC secret from credentials; `exp`/`aud`/`iss` validated; a revocation strategy (`jti` denylist); refresh rotation or short access lifetime. A diff that touches neither flavor's code runs no flavor bullet - state that in `Notes:`
- **Session**: `cookie_store, secure: true, httponly: true, same_site: :lax|:strict`
- **Password**: `has_secure_password` (bcrypt); never hand-rolled. Prefer `authenticate_by` (Rails 7.1+, constant-time)
- **Secrets**: no creds in code; `master.key`, `.env`, `config/credentials/*.key` gitignored

### Step 6 - Authorization

- [ ] **Pundit**: `verify_authorized` + `verify_policy_scoped` enabled (read `ApplicationController` even when untouched - an absent hook is `_(pre-existing)_` context unless the diff adds the first unauthorized action); `ApplicationPolicy` default-denies; every diffed action calls `authorize` or `policy_scope` (or explicit `skip_authorization` with rationale)
- [ ] **CanCanCan**: `Ability` comprehensive; `load_and_authorize_resource` on every RESTful controller
- [ ] **IDOR**: prefer `current_user.orders.find(params[:id])` (404) over `Order.find` + `authorize` (403 leaks existence). Pundit: `policy_scope(Order).find(params[:id])` + `authorize`
- [ ] **Custom / hand-rolled authz**: every action reaches a role or ownership check on a path the request cannot skip - a `before_action` that `return`s without rendering, a check inside one branch of a conditional, or an action added after the filter list all leave it open. Enumerate actions against checks and name the ones with no check.
- [ ] **Tenant isolation**: scoped at the model layer (`default_scope`, query objects, `acts_as_tenant`), not controller-only

### Step 7 - Input, Mass Assignment, View Escaping

- [ ] **Strong params** explicit allowlist on every diffed `create`/`update`; no `permit!`/`to_unsafe_h`. Ownership FKs (`:user_id`, `:owner_id`, `:tenant_id`, `:account_id`) are never permitted - assigned server-side from `current_user`; other privilege-bearing keys (`:role`, `:admin`, `:approved`, `:status`) need an admin-only controller + separate policy, or get dropped from permit. Prefer `params.expect` (Rails 8.0+)
- [ ] **`accepts_nested_attributes_for`** limited to expected children; `_destroy: true` only when parent policy authorizes child deletion
- [ ] **File uploads** (`has_one_attached`/`direct_upload`/variants): magic-byte content-type, size limit, `Content-Disposition: attachment`, a controller gate before a per-call short-expiry `blob.url(expires_in:)` (blob routes carry no authorization and `urls_expire_in` defaults to nil). Use skill: `rails-active-storage-patterns`
- [ ] **Path traversal**: `File.expand_path` + base-directory containment on user-controlled paths
- [ ] **Shell**: no `system`/backticks/`Open3` with interpolated user input
- [ ] **Views** (server-rendered): audit diffed `.erb`/`.haml`/`.slim` for `<%==`, `!=`, `==` (unanchored - it also appears as `href==x` and `.row == x`), `raw`, `.html_safe`. Use skill: `rails-view-templates` when any template is touched. Slim attributes: bare `class=user_input` evaluates Ruby - quote literals
- [ ] **`sanitize`** requires explicit tag/attribute allowlist - the default list is broader than most features need; the explicit allowlist is the trust boundary
- [ ] **Turbo / ActionCable**: `turbo_stream.append("id", user_input)` (positional content, wrapped `html_safe`) or any `html_safe`/`raw` string is XSS - `html: plain_string` is escaped; use `partial:`. `turbo_stream_from "scope_#{id}"` signs the scope but does not authorize it - `turbo_stream_from` already calls `signed_stream_name`, and `Turbo::StreamsChannel#subscribed` only verifies that signature, so "add a signed stream name" is a no-op fix. The control is the controller rendering the tag only for entitled viewers, and scoping on model objects (`turbo_stream_from current_user, :orders`) rather than a raw id; anything else needs a custom channel with its own `subscribed` check. Use skill: `rails-actioncable-patterns` for new channels and every `turbo_stream_from` scope
- [ ] **Markdown/rich-text**: `Commonmarker`/`Redcarpet`/`Kramdown` output through `sanitize` with allowlist

### Step 8 - Common Rails Surfaces

- [ ] **CSRF**: `protect_from_forgery with: :exception`; `ActionController::API` does not include `RequestForgeryProtection` at all - `protect_from_forgery` raises `NoMethodError` there, so an API-only app has no CSRF protection (a controller module, not middleware) and relies on token / JWT auth; `:null_session` applies only to an `ActionController::Base` app serving API endpoints. Flag bare `skip_before_action :verify_authenticity_token`
- [ ] **CORS**: `rack-cors` explicit origins; no reflecting or dynamic `origins` block with `credentials: true` (the literal `'*'` plus credentials raises at boot)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, expensive search - keyed on IP plus the submitted identifier (an IP-only login throttle is bypassed by credential stuffing; `req.params` is blind to a JSON body)
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated or `allow_other_host: false`; check `config.action_controller.raise_on_open_redirects` (on from `load_defaults 7.0`) - it decides the tier
- [ ] **Mass assignment via JSON**: `params.require.permit` / `params.expect`, not `Model.new(JSON.parse(request.raw_post))` or `permit!` / `to_unsafe_h` on a wrapped JSON body (`Model.new(request.raw_post)` itself raises - `raw_post` is a String)
- [ ] **Webhook endpoints**: verify via the provider SDK (`Stripe::Webhook.construct_event`) over hand-rolled HMAC; comparisons use `ActiveSupport::SecurityUtils.secure_compare`, never `==`; enforce timestamp/replay tolerance; read `request.body` once (or rewind) - a second read returns empty
- [ ] **Admin/dev mounts**: `Sidekiq::Web`, `Rails::MailersController` auth-gated in production

### Step 9 - Data Protection

- [ ] PII / sensitive fields encrypted at rest (Active Record Encryption, `encrypts :column`)
- [ ] Custom log lines redact user data (extends `filter_parameters` to manual writes)
- [ ] No sensitive data in URLs - POST body or signed tokens
- [ ] Rails credentials for all third-party keys; per-environment credential files

### Verify Findings (before writing)

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, and fill the Summary's `Findings verified:` line from its tally in the atomic's Summary form; dropped rows appear only in the tally, never in the body. On round 2+, after verification, re-project the prior report's findings - every tier, the file at the handle's `report_path` - into reconcile's parse shape - one `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its `Label:` line (the label alone - a trailing `_(carried from round <N>)_` group is re-emitted on the heading as its own group; when the prior report wrote no label, the one its tier maps to in Next Steps) and the `file:line` prefix of its Location line, keeping a `_(pre-existing)_` annotation on the heading (verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_` - reconcile matches `_(pre-existing)_` exactly), with its `Issue` line written as `Issue:` (the smell) - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line and tally render as `## Prior Round Reconciliation`; `Still open` and `Needs re-check` rows carry into their prior tier at their prior label with `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the Label value and the prior Location annotation kept - the table row and a Next Steps entry are its only other appearances, and a carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried; the reconciliation table is the one place a label outside `[Must]` / `[Recommend]` is written. Subagent runs skip verification and reconciliation both - the parent verifies and reconciles its own merged set once.

### Step 10 - Write Report

Standalone runs (resolved diff): Use skill: `review-report-writer` with `report_type: review-security` and every field the writer requires - `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `scope: +sec`, `depth: deep` (this skill always runs full depth; `deep` is its writer value), `stack = ruby-rails`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line. Subagent runs (parent passed pre-read artifacts): skip the writer and return only `## Findings` with its tier sections and any `out of lens` lines, plus `## Axes Skipped` - no Summary, no Recommendations, no Next Steps, no file - the parent owns the report. (Audit mode skips the writer too and emits the body as the response - see Invocation.) Security-adjacent correctness bugs found en route (double `body.read`, broken comparisons) stay in the report - they weaken the security posture even when the category is "bug".

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

Fill rules: `Findings verified:` carries the verify tally on standalone runs and the literal `inline (no diff)` in audit mode (subagent runs emit no Summary). Verify annotations appear on standalone runs only; a finding sits in the section matching its severity while its `Label:` line carries the published label, so a `[Recommend]` inside a higher section is correct, not a mismatch to fix. `Target:` appears only in audit mode (it replaces writer checkpointing); omit otherwise. **One defect, one finding.** Several checklist rows, or several call sites, that describe one underlying defect file once - at the site where the fix lands, with the other sites named in the Location line. Genuinely distinct defects at one site, with different fixes, stay separate. Anchor to the narrowest `file:line` the fix touches; a range only when the fix spans contiguous lines. There is no finding count to hit or stay under: file every defect that meets the severity bar and nothing that does not. Two findings are the same defect when one fix removes both; different fixes at one site, or one fix that only masks the second, are two.

```markdown
## Rails Security Review Summary

- **Stack Detected:** Ruby <version> / Rails <version>
- **Auth:** Devise | JWT | Custom | Hybrid
- **Authorization:** Pundit | CanCanCan | Custom
- **Round:** <N>   {round 2+ only}
- **Target:** <surface>   {audit mode only}
- **Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count, zeros included]
- **Findings verified:** <per fill rules: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}` from `review-finding-verify` | inline (no diff)>
- **Notes:** <the Step 2 declared-vs-code divergence, each `_(unverified: ...)_` config caveat's source; omit when none>

[2-3 sentence assessment; call out Rails-specific risks.]

## Findings

### Critical

- **Location:** [file:line; `Controller#action1, #action2` for combined findings; for an absent control, the file that should carry it (`config/initializers/rack_attack.rb` - absent) or the route it should protect] [+ the verify Annotation - `_(pre-existing)_` / `_(pre-existing; newly reachable via ...)_` / `_(unverified: <reason>)_` / `_(mechanism: <actual>)_`]
- **Label:** [Must] | [Recommend]   {the verified Label; else the severity mapping in Next Steps; a carried finding appends `_(carried from round <N>)_`}
- **Issue:** [Rails terms: "Strong params bypassed via `permit!` in OrdersController#update"]
- **Attack scenario:** [how attacker exploits]
- **Fix:** [Rails remediation with code]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit empty severity sections. If all empty, state "No security issues found."_

## Prior Round Reconciliation

[table, note line and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Axes Skipped

- <one `- ` bullet per OWASP axis from Step 4 that was skipped, with its reason (`A03 - no dependency change in the diff`)>   {omit the section when every axis ran; subagent runs return it after `## Findings` and the parent does not render it}

## Recommendations

[Prioritized hardening]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

`[Implement]` = localized fix. `[Delegate]` = cross-cutting hardening / dependency upgrade / threat-model. `[Implement]` / `[Delegate]` and `[Must]` / `[Recommend]` are independent axes - a `[Delegate]` may carry `[Must]`. Order Must > Recommend. Intent per finding: Critical/High -> [Must]; Medium/Low -> [Recommend]; when the verify pass changed a finding's label, its verified `Label` wins over this mapping. No other label is written. Omit if no issues.
```


**A defect this lens does not own is reported, never dropped.** Another lens's category, a plain correctness bug, or something a gate excluded but the reading surfaced: one `- **out of lens:** file:line - <the defect in one sentence, and the workflow that owns it>` line at the end of `## Findings` - untiered, uncounted in `Overall`, absent from Next Steps; the parent drafts it as a finding. Atomics loaded by any step feed findings into this template; their own output blocks are not emitted. The exception is a defect that makes this lens's own findings unreachable or wrong (a query that always raises, a guard that never runs): that files here at its own severity, because it changes what the rest of the report means.

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent; audit mode: Step 3 skipped); standalone: `report_type: review-security` passed and the round decided from the handle before the diff was read (or the stop line printed); auth + authz flavor recorded
- [ ] Step 4: OWASP axes walked; skip-reasons stated when an axis didn't apply
- [ ] Step 5: detected flavor's bullet + the flavor-independent bullets ran (only when the diff touches auth)
- [ ] Step 6: every new action has matching policy method; IDOR + tenant isolation checked
- [ ] Step 7: strong params on every diffed create/update; views audited (skipped for API-only)
- [ ] Step 8-9: CSRF/CORS/admin gating/data protection covered
- [ ] Verify pass ran (inline in audit mode; skipped as subagent - the parent verifies); tally or omission per fill rules; prior findings projected and reconciled on round 2+
- [ ] Step 10: report via `review-report-writer` (subagent: findings returned to parent; audit mode: body emitted as the response); confirmation printed when the writer ran
- [ ] Combined-finding rule applied; every finding has an attack scenario; empty severities stated explicitly

## Avoid

- Vulnerabilities without an attack scenario
- Generic security advice when a Rails idiom applies
- `permit!`/`to_unsafe_h` as a fix for `ParameterMissing`
- Disabling `verify_authorized` instead of adding the missing call
- N near-duplicate findings when one combined finding captures the shared root cause
- Walking flavor-specific bullets when the diff doesn't touch that flavor
