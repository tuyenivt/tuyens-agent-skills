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
| **Critical** (block deploy) | Unauth RCE, auth bypass (incl. JWT decode with verification disabled or `alg: none` accepted), mass data exfiltration, SQLi on prod path, shell interpolation, `Marshal.load`/`YAML.load` / `ERB.new(user_input).result` on untrusted input, secrets/`master.key` committed, `permit!`/`to_unsafe_h` on a model whose **schema** exposes role/admin/tenant/owner/billing fields (judge by table, not by diff) |
| **High** (block merge) | Authenticated privilege escalation, IDOR via `Model.find(params[:id])` without policy scope, SSRF to cloud metadata, missing `authorize`/`verify_authorized`, path traversal via `send_file(params[:path])`, missing CSRF on cookie-auth POST, webhook HMAC compared with `==`, CORS `origins '*'` with `credentials: true`, unauthorized `turbo_stream_from`, open `redirect_to params[:return_to]`, raw `render json: @model` exposing sensitive columns |
| **Medium** | Hardening gap with mitigation present, secrets in ENV instead of credentials, weak `Rack::Attack` limit, non-prod debug surface (Sidekiq Web, `letter_opener`), unfixed `bundle audit` advisory, missing `filter_parameters` entry, raw `render json:` over-exposure of non-sensitive columns |
| **Low** | Defense-in-depth, advisories below actively-exploited threshold |

**Combined-finding rule.** N actions sharing a missing `before_action` gate file as **one** finding at elevated severity (one level above the worst individual action, capped at Critical), citing the worst payload as the attack scenario. Findings with their own distinct attack chain (SQLi, path traversal, mass assignment) file separately and do **not** restate the missing-authz dimension - the combined finding owns it.

## Invocation

`/task-rails-review-security [<branch>|pr-<N>]` - current branch vs base; fails fast on trunk. Subagent invocation with pre-read artifacts skips Steps 1-3.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-security`. Record **auth flavor** (Devise / JWT / custom) and **authz flavor** (Pundit / CanCanCan / custom) - flavor-specific bullets below run only for the detected flavor.

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
| Data Integrity | No `Marshal.load` on user input; `YAML.safe_load` not `YAML.load` |
| Logging | `filter_parameters` covers password/token/secret/ssn/api_key/credit_card/authorization; no PII in `Rails.logger` |

### Step 5 - Authentication (only when diff touches auth)

Run only the detected flavor's bullets.

- **Devise**: `:lockable`/`:trackable`/`:confirmable`/`:rememberable` per threat model; `password_length >= 8`; `paranoid: true` on forgot-password; custom controllers preserve `protect_from_forgery` + rate limit
- **JWT**: signature pinned (no `alg: none`); HMAC secret from credentials; `exp`/`aud`/`iss` validated; refresh rotation or short access lifetime
- **Session**: `cookie_store, secure: true, httponly: true, same_site: :lax|:strict`
- **Password**: `has_secure_password` (bcrypt); never hand-rolled. Prefer `authenticate_by` (Rails 7.1+, constant-time)
- **Secrets**: no creds in code; `master.key`, `.env`, `config/credentials/*.key` gitignored

### Step 6 - Authorization

- [ ] **Pundit**: `verify_authorized` + `verify_policy_scoped` enabled; `ApplicationPolicy` default-denies; every diffed action calls `authorize` or `policy_scope` (or explicit `skip_authorization` with rationale)
- [ ] **CanCanCan**: `Ability` comprehensive; `load_and_authorize_resource` on every RESTful controller
- [ ] **IDOR**: prefer `current_user.orders.find(params[:id])` (404) over `Order.find` + `authorize` (403 leaks existence). Pundit: `policy_scope(Order).find(params[:id])` + `authorize`
- [ ] **Tenant isolation**: scoped at the model layer (`default_scope`, query objects, `acts_as_tenant`), not controller-only

### Step 7 - Input, Mass Assignment, View Escaping

- [ ] **Strong params** explicit allowlist on every diffed `create`/`update`; no `permit!`/`to_unsafe_h`. Privilege-bearing keys (`:role`, `:admin`, `:owner_id`, `:user_id`, `:tenant_id`, `:account_id`, `:approved`, `:status`) require admin-only controller + separate policy, or get dropped from permit. Prefer `params.expect` (Rails 8.0+)
- [ ] **`accepts_nested_attributes_for`** limited to expected children; `_destroy: true` only when parent policy authorizes child deletion
- [ ] **File uploads** (`has_one_attached`/`direct_upload`/variants): magic-byte content-type, size limit, `Content-Disposition: attachment`, signed short-expiry URLs. Use skill `rails-active-storage-patterns`
- [ ] **Path traversal**: `File.expand_path` + base-directory containment on user-controlled paths
- [ ] **Shell**: no `system`/backticks/`Open3` with interpolated user input
- [ ] **Views** (server-rendered): audit diffed `.erb`/`.haml`/`.slim` for `<%==`, `!=`, ` == `, `raw`, `.html_safe`. Use skill `rails-view-templates` when >1 template touched. Slim attributes: bare `class=user_input` evaluates Ruby - quote literals
- [ ] **`sanitize`** requires explicit tag/attribute allowlist - the default list is broader than most features need; the explicit allowlist is the trust boundary
- [ ] **Turbo / ActionCable**: `turbo_stream.append("id", html: user_input)` is XSS - use `partial:`. `turbo_stream_from "scope_#{id}"` needs `subscribed` authz or `Turbo::StreamsChannel.signed_stream_name`. Use skill `rails-actioncable-patterns` for new channels
- [ ] **Markdown/rich-text**: `Commonmarker`/`Redcarpet`/`Kramdown` output through `sanitize` with allowlist

### Step 8 - Common Rails Surfaces

- [ ] **CSRF**: `protect_from_forgery with: :exception`; API-only `:null_session` requires token auth. Flag bare `skip_before_action :verify_authenticity_token`
- [ ] **CORS**: `rack-cors` explicit origins (no `origins '*'` for credentialed endpoints)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, expensive search
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated or `allow_other_host: false`
- [ ] **Mass assignment via JSON**: `params.require.permit`, not `Model.new(request.raw_post)`
- [ ] **Webhook endpoints**: verify via the provider SDK (`Stripe::Webhook.construct_event`) over hand-rolled HMAC; comparisons use `ActiveSupport::SecurityUtils.secure_compare`, never `==`; enforce timestamp/replay tolerance; read `request.body` once (or rewind) - a second read returns empty
- [ ] **Admin/dev mounts**: `Sidekiq::Web`, `Rails::MailersController` auth-gated in production

### Step 9 - Data Protection

- [ ] PII / sensitive fields encrypted at rest (AR encryption or `attr_encrypted`)
- [ ] Custom log lines redact user data (extends `filter_parameters` to manual writes)
- [ ] No sensitive data in URLs - POST body or signed tokens
- [ ] Rails credentials for all third-party keys; per-environment credential files

### Step 10 - Write Report

Standalone runs: use skill `review-report-writer` with `report_type: review-security` (checkpoint fields come from Step 3); print confirmation. Subagent runs (parent passed pre-read artifacts): skip the writer and return findings in this skill's Output Format to the parent - the parent owns the report. Security-adjacent correctness bugs found en route (double `body.read`, broken comparisons) stay in the report - they weaken the security posture even when the category is "bug".

## Output Format

```markdown
## Rails Security Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Auth:** Devise | JWT | Custom | Hybrid
**Authorization:** Pundit | CanCanCan | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment; call out Rails-specific risks.]

## Findings

### Critical

- **Location:** [file:line, or `Controller#action1, #action2` for combined findings]
- **Issue:** [Rails terms: "Strong params bypassed via `permit!` in OrdersController#update"]
- **Attack scenario:** [how attacker exploits]
- **Fix:** [Rails remediation with code]

### High / Medium / Low

[Same structure]

_Omit empty severity sections. If all empty, state "No security issues found."_

## Recommendations

[Prioritized hardening]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

`[Implement]` = localized fix. `[Delegate]` = cross-cutting hardening / dependency upgrade / threat-model. Order Must > Recommend > Question. Intent per finding: Critical/High -> [Must]; Medium/Low -> [Recommend]; needs author confirmation (unverifiable from diff) -> [Question]. Omit if no issues.
```

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent); auth + authz flavor recorded
- [ ] Step 4: OWASP axes walked; skip-reasons stated when an axis didn't apply
- [ ] Step 5: only detected auth flavor's bullets ran
- [ ] Step 6: every new action has matching policy method; IDOR + tenant isolation checked
- [ ] Step 7: strong params on every diffed create/update; views audited (skipped for API-only)
- [ ] Step 8-9: CSRF/CORS/admin gating/data protection covered
- [ ] Step 10: report via `review-report-writer`; confirmation printed
- [ ] Combined-finding rule applied; every finding has an attack scenario; empty severities stated explicitly

## Avoid

- Vulnerabilities without an attack scenario
- Generic security advice when a Rails idiom applies
- `permit!`/`to_unsafe_h` as a fix for `ParameterMissing`
- Disabling `verify_authorized` instead of adding the missing call
- N near-duplicate findings when one combined finding captures the shared root cause
- Walking flavor-specific bullets when the diff doesn't touch that flavor
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
