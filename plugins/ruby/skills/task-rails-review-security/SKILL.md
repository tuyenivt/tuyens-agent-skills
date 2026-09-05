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
| **Critical** (block deploy) | Unauth RCE, auth bypass (incl. JWT decode with signature verification disabled or `alg: none` accepted), mass data exfiltration, SQLi on prod path, shell interpolation, `Marshal.load` / `YAML.unsafe_load` (or `load`/`safe_load` with `permitted_classes` or `aliases: true` widened; bare `YAML.load` raises `Psych::DisallowedClass` on Ruby 3.1+ and is not itself the vector) / `ERB.new(user_input).result` on untrusted input, secrets/`master.key` committed, `permit!`/`to_unsafe_h` on a model whose **schema** exposes role/admin/tenant/owner/billing fields (judge by table, not by diff) |
| **High** (block merge) | Authenticated privilege escalation, IDOR via `Model.find(params[:id])` with no `authorize` or policy scoping, SSRF to cloud metadata, missing `authorize`/`verify_authorized`, JWT claim validation disabled (`exp`/`aud`/`iss`), refresh or API tokens stored unhashed, raw-SQL interpolation reachable only through a framework guard (`disallow_raw_sql!` on `.order`/`.pluck`; unguarded paths stay Critical), path traversal via `send_file(params[:path])`, missing CSRF on cookie-auth POST, webhook HMAC compared with `==`, CORS `origins '*'` with `credentials: true`, unauthorized `turbo_stream_from`, open `redirect_to params[:return_to]`, raw `render json: @model` exposing sensitive columns |
| **Medium** | Hardening gap with mitigation present, `force_ssl` off or `config.hosts` empty in production, secrets in ENV instead of credentials, `Rack::Attack` absent or weak on an auth or expensive-search endpoint, non-prod debug surface (Sidekiq Web, `letter_opener`), unfixed `bundle audit` advisory, missing `filter_parameters` entry, raw `render json:` over-exposure of non-sensitive columns, `skip_authorization`/`skip_after_action :verify_authorized` without stated rationale, `Model.find` + `authorize` where scoping would 404 (existence leak) |
| **Low** | Defense-in-depth, advisories below actively-exploited threshold |

**Combined-finding rule.** N actions sharing one missing authorization gate (skipped `before_action`, absent `verify_authorized` enforcement, controller-wide policy hole) file as **one** finding at elevated severity (one level above the worst individual action, capped at Critical), citing the worst payload as the attack scenario. Two defects on one code path with distinct attack chains stay separate findings even when one fix touches both (an unverified JWT signature and an unvalidated `exp` are two) - distinct attack chains, not distinct fixes, is the test here, and it overrides the Output Format's general one-defect-one-finding rule. Findings with their own distinct attack chain (SQLi, path traversal, mass assignment) file separately and do **not** restate the missing-authz dimension - the combined finding owns it.

## Invocation

`/task-rails-review-security [<branch>|pr-<N>]` - current branch vs base; fails fast on trunk. Subagent invocation with pre-read artifacts skips Steps 2-3 (Step 1 still runs - behavioral rules are per-context); still record Step 2's auth/authz flavors from the artifacts in hand (Gemfile, `app/policies/`) - Steps 5-6 gate on them in every mode. Checks needing config outside the evidence in hand (`verify_policy_scoped` enablement, `Rack::Attack` limits): file `[Recommend]` with a `verify:` caveat rather than asserting or skipping.

**Audit mode** (no PR/diff: Pundit / strong-params drift sweep, Devise/JWT flow audit): skip Step 3. Scope = the named surface, read as the code that implements it, not everything reachable through it - a flow audit covers credential issuance and verification (auth config, auth controllers, the `authenticate!` / `require_role!` implementation), not every controller sitting behind them. None named = `app/controllers` + `app/policies` for an authz sweep, auth config + custom auth controllers for a flow audit. Run Steps 4-9 against current code - "diff"-worded checks and gates read as "the resolved surface"; skip axes with no matching surface, state the skip. Severity tiers keep their meanings; read `block deploy/merge` as fix-priority ranks, not gates. Verify: skip `review-finding-verify` (it requires a diff) - instead re-read each cited `file:line` at `HEAD`, drop findings the code does not support, and report `Findings verified: inline (no diff)`. Fill the Summary's `Target:` slot, skip `review-report-writer` checkpointing, and emit the report body as the response - no file is written. Every "skip when the diff ..." gate reads as "skip when the in-scope code has no such surface": gating removes atomic loads and rows with no matching code, never a row whose surface is present.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. Where the project's declared stack and its code disagree, record what the code does and note the divergence.  If not Rails, redirect to `/task-code-review-security`. Record **auth flavor** (Devise / JWT / custom / hybrid when two coexist - record both and run each one's bullets) and **authz flavor** (Pundit / CanCanCan / custom) - flavor-specific bullets below run only for the detected flavor.

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check`. On approval, read `git diff` and `git log` once. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - OWASP Walk (Rails Lens)

Use skill: `rails-security-patterns` for canonical rules. Walk the OWASP axes below against the diff; skip an axis when the diff cannot exercise it (state the skip).

| Axis | Rails check |
| ---- | ----------- |
| Broken Access Control | Every diffed action calls `authorize` (Pundit) or `load_and_authorize_resource` (CanCanCan) |
| Injection | No interpolation in `where`/`find_by_sql`/`Arel.sql`; `params[:sort]` allowlisted |
| Cryptographic Failures | Rails credentials for secrets; AR encryption for sensitive columns |
| Misconfiguration | `force_ssl`, `protect_from_forgery`, CSP set |
| SSRF | No `Net::HTTP.get(URI(user_input))` without hostname allowlist |
| XSS | No `html_safe`/`raw`/unescape on user input (see Step 7) |
| Insecure Design | Pundit policy per API-exposed model; `ApplicationPolicy` default-denies |
| Vulnerable Components | `bundle audit` clean; `bin/importmap audit` for JS |
| Data Integrity | No `Marshal.load` on user input; no `YAML.unsafe_load`, and no widened `permitted_classes` / `aliases: true` |
| Logging | `filter_parameters` covers password/token/secret/ssn/api_key/credit_card/authorization; no PII in `Rails.logger` |

### Step 5 - Authentication (only when the diff touches auth code)

"Touches auth" means the diff changes auth configuration, an auth controller, or a session / token / password path - not merely that new code sits behind an inherited `authenticate!`. A new endpoint under existing auth exercises Step 6, not Step 5.

Run the detected flavor's bullet (Devise or JWT); the Session / Password / Secrets bullets are flavor-independent and always run when the diff touches auth.

- **Devise**: `:lockable`/`:trackable`/`:confirmable`/`:rememberable` per threat model; `password_length >= 8`; `paranoid: true` on forgot-password; custom controllers preserve `protect_from_forgery` + rate limit
- **JWT**: signature pinned (no `alg: none`); HMAC secret from credentials; `exp`/`aud`/`iss` validated; refresh rotation or short access lifetime
- **Session**: `cookie_store, secure: true, httponly: true, same_site: :lax|:strict`
- **Password**: `has_secure_password` (bcrypt); never hand-rolled. Prefer `authenticate_by` (Rails 7.1+, constant-time)
- **Secrets**: no creds in code; `master.key`, `.env`, `config/credentials/*.key` gitignored

### Step 6 - Authorization

- [ ] **Pundit**: `verify_authorized` + `verify_policy_scoped` enabled; `ApplicationPolicy` default-denies; every diffed action calls `authorize` or `policy_scope` (or explicit `skip_authorization` with rationale)
- [ ] **CanCanCan**: `Ability` comprehensive; `load_and_authorize_resource` on every RESTful controller
- [ ] **IDOR**: prefer `current_user.orders.find(params[:id])` (404) over `Order.find` + `authorize` (403 leaks existence). Pundit: `policy_scope(Order).find(params[:id])` + `authorize`
- [ ] **Custom / hand-rolled authz**: every action reaches a role or ownership check on a path the request cannot skip - a `before_action` that `return`s without rendering, a check inside one branch of a conditional, or an action added after the filter list all leave it open. Enumerate actions against checks and name the ones with no check.
- [ ] **Tenant isolation**: scoped at the model layer (`default_scope`, query objects, `acts_as_tenant`), not controller-only

### Step 7 - Input, Mass Assignment, View Escaping

- [ ] **Strong params** explicit allowlist on every diffed `create`/`update`; no `permit!`/`to_unsafe_h`. Privilege-bearing keys (`:role`, `:admin`, `:owner_id`, `:user_id`, `:tenant_id`, `:account_id`, `:approved`, `:status`) require admin-only controller + separate policy, or get dropped from permit. Prefer `params.expect` (Rails 8.0+)
- [ ] **`accepts_nested_attributes_for`** limited to expected children; `_destroy: true` only when parent policy authorizes child deletion
- [ ] **File uploads** (`has_one_attached`/`direct_upload`/variants): magic-byte content-type, size limit, `Content-Disposition: attachment`, signed short-expiry URLs. Use skill `rails-active-storage-patterns`
- [ ] **Path traversal**: `File.expand_path` + base-directory containment on user-controlled paths
- [ ] **Shell**: no `system`/backticks/`Open3` with interpolated user input
- [ ] **Views** (server-rendered): audit diffed `.erb`/`.haml`/`.slim` for `<%==`, `!=`, ` == `, `raw`, `.html_safe`. Use skill `rails-view-templates` when >1 template touched. Slim attributes: bare `class=user_input` evaluates Ruby - quote literals
- [ ] **`sanitize`** requires explicit tag/attribute allowlist - the default list is broader than most features need; the explicit allowlist is the trust boundary
- [ ] **Turbo / ActionCable**: `turbo_stream.append("id", html: user_input)` is XSS - use `partial:`. `turbo_stream_from "scope_#{id}"` signs the scope but does not authorize it - `turbo_stream_from` already calls `signed_stream_name`, and `Turbo::StreamsChannel#subscribed` only verifies that signature, so "add a signed stream name" is a no-op fix. The control is the controller rendering the tag only for entitled viewers, and scoping on model objects (`turbo_stream_from current_user, :orders`) rather than a raw id; anything else needs a custom channel with its own `subscribed` check. Use skill `rails-actioncable-patterns` for new channels
- [ ] **Markdown/rich-text**: `Commonmarker`/`Redcarpet`/`Kramdown` output through `sanitize` with allowlist

### Step 8 - Common Rails Surfaces

- [ ] **CSRF**: `protect_from_forgery with: :exception`; `ActionController::API` does not include `RequestForgeryProtection` at all - `protect_from_forgery` raises `NoMethodError` there, so an API-only app has no CSRF middleware and relies on token / JWT auth; `:null_session` applies only to an `ActionController::Base` app serving API endpoints. Flag bare `skip_before_action :verify_authenticity_token`
- [ ] **CORS**: `rack-cors` explicit origins (no `origins '*'` for credentialed endpoints)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, expensive search
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated or `allow_other_host: false`
- [ ] **Mass assignment via JSON**: `params.require.permit` / `params.expect`, not `Model.new(JSON.parse(request.raw_post))` or `permit!` / `to_unsafe_h` on a wrapped JSON body (`Model.new(request.raw_post)` itself raises - `raw_post` is a String)
- [ ] **Webhook endpoints**: verify via the provider SDK (`Stripe::Webhook.construct_event`) over hand-rolled HMAC; comparisons use `ActiveSupport::SecurityUtils.secure_compare`, never `==`; enforce timestamp/replay tolerance; read `request.body` once (or rewind) - a second read returns empty
- [ ] **Admin/dev mounts**: `Sidekiq::Web`, `Rails::MailersController` auth-gated in production

### Step 9 - Data Protection

- [ ] PII / sensitive fields encrypted at rest (AR encryption or `attr_encrypted`)
- [ ] Custom log lines redact user data (extends `filter_parameters` to manual writes)
- [ ] No sensitive data in URLs - POST body or signed tokens
- [ ] Rails credentials for all third-party keys; per-environment credential files

### Verify Findings (before writing)

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary; dropped rows appear only in the tally, never in the body. Subagent runs skip this - the parent verifies the merged set once.

### Step 10 - Write Report

Standalone runs (resolved diff): use skill `review-report-writer` with `report_type: review-security`. Assemble every checkpoint field the writer requires - `report_body` (the assembled body), `branch` (the head short name; it is also the report filename key), and `base_ref` / `head_ref` as the handle emitted them, plus: `scope: +sec`, `depth: deep` (this skill always runs full depth; `deep` is its writer value), `stack = ruby-rails`, `base_sha` / `head_sha` via `git rev-parse` on the handle's refs, and `mode: full`, `round: 1` - unless `review-security-<branch>.md` already exists with valid frontmatter (filename per the writer's sanitization: `/` and characters outside `[A-Za-z0-9_-]` become `-`), then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Print confirmation. Subagent runs (parent passed pre-read artifacts): skip the writer and return findings in this skill's Output Format to the parent - the parent owns the report. (Audit mode skips the writer too and emits the body as the response - see Invocation.) Security-adjacent correctness bugs found en route (double `body.read`, broken comparisons) stay in the report - they weaken the security posture even when the category is "bug".

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

Fill rules: `Findings verified:` carries the verify tally on standalone runs, the literal `inline (no diff)` in audit mode, and is omitted on subagent runs (the parent verifies). `Target:` appears only in audit mode (it replaces writer checkpointing); omit otherwise. **One defect, one finding.** Several checklist rows, or several call sites, that describe one underlying defect file once - at the site where the fix lands, with the other sites named in the Location line. Genuinely distinct defects at one site, with different fixes, stay separate. Anchor to the narrowest `file:line` the fix touches; a range only when the fix spans contiguous lines. There is no finding count to hit or stay under: file every defect that meets the severity bar and nothing that does not. Two findings are the same defect when one fix removes both; different fixes at one site, or one fix that only masks the second, are two.

```markdown
## Rails Security Review Summary

- **Stack Detected:** Ruby <version> / Rails <version>
- **Auth:** Devise | JWT | Custom | Hybrid
- **Authorization:** Pundit | CanCanCan | Custom
- **Target:** <surface>
- **Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]
- **Findings verified:** <per fill rules: `<N> confirmed, <M> reattributed, <K> dropped` from `review-finding-verify`, plus its false-positive/resolved split and unverified suffix when emitted | inline (no diff) | omitted>

[2-3 sentence assessment; call out Rails-specific risks.]

## Findings

### Critical

- **Location:** [file:line; `Controller#action1, #action2` for combined findings; for an absent control, the file that should carry it (`config/initializers/rack_attack.rb` - absent) or the route it should protect] [+ `_(pre-existing)_` / `_(pre-existing; newly reachable via ...)_` / `_(unverified: <reason>)_` when the verify pass returned one]
- **Label:** [Must] | [Recommend] _(the verified `Label`; else the severity mapping in Next Steps)_
- **Issue:** [Rails terms: "Strong params bypassed via `permit!` in OrdersController#update"]
- **Attack scenario:** [how attacker exploits]
- **Fix:** [Rails remediation with code]

### High / Medium / Low

[Same structure]

_Omit empty severity sections. If all empty, state "No security issues found."_

## Axes Covered

One line per OWASP axis from Step 4 that was skipped, with its reason (`SSRF - no outbound HTTP in the resolved surface`). Omit when every axis ran.

## Recommendations

[Prioritized hardening]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

`[Implement]` = localized fix. `[Delegate]` = cross-cutting hardening / dependency upgrade / threat-model. `[Implement]` / `[Delegate]` and `[Must]` / `[Recommend]` are independent axes - a `[Delegate]` may carry `[Must]`. Order Must > Recommend. Intent per finding: Critical/High -> [Must]; Medium/Low -> [Recommend]; when the verify pass changed a finding's label, its verified `Label` wins over this mapping. No other label is written. Omit if no issues.
```


**A defect this lens does not own is reported, never dropped.** Another lens's category, a plain correctness bug, or something a gate excluded but the reading surfaced: one line under `## Recommendations` giving its location and the workflow that owns it - untiered, uncounted in `Overall`, absent from Next Steps. The exception is a defect that makes this lens's own findings unreachable or wrong (a query that always raises, a guard that never runs): that files here at its own severity, because it changes what the rest of the report means.

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent; audit mode: Step 3 skipped); auth + authz flavor recorded
- [ ] Step 4: OWASP axes walked; skip-reasons stated when an axis didn't apply
- [ ] Step 5: detected flavor's bullet + the flavor-independent bullets ran (only when the diff touches auth)
- [ ] Step 6: every new action has matching policy method; IDOR + tenant isolation checked
- [ ] Step 7: strong params on every diffed create/update; views audited (skipped for API-only)
- [ ] Step 8-9: CSRF/CORS/admin gating/data protection covered
- [ ] Verify pass ran (inline in audit mode; skipped as subagent - the parent verifies); tally or omission per fill rules
- [ ] Step 10: report via `review-report-writer` (subagent: findings returned to parent; audit mode: body emitted as the response); confirmation printed when the writer ran
- [ ] Combined-finding rule applied; every finding has an attack scenario; empty severities stated explicitly

## Avoid

- Vulnerabilities without an attack scenario
- Generic security advice when a Rails idiom applies
- `permit!`/`to_unsafe_h` as a fix for `ParameterMissing`
- Disabling `verify_authorized` instead of adding the missing call
- N near-duplicate findings when one combined finding captures the shared root cause
- Walking flavor-specific bullets when the diff doesn't touch that flavor
