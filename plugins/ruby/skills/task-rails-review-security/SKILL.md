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

Rails-aware security review naming Devise, JWT, Pundit/CanCanCan, strong params, Rails credentials, and Rack::Attack idioms directly. Findings include attack scenarios and Rails-specific remediations. Stack-specific delegate of `task-code-review-security`.

## When to Use

- Reviewing a Rails PR for security regressions
- Pre-deploy hardening on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-params / Pundit drift sweep
- Auditing a Devise/JWT flow or new Pundit policy

**Not for:** perf (`task-code-review-perf`), general review (`task-code-review`), incident triage (`/task-oncall-start`).

**Depth.** Always full. Security has cliff-edged consequences (auth bypass, RCE) that don't benefit from a "light" mode. Scope by file, not depth.

## Severity Rubric

| Severity | Definition |
| -------- | ---------- |
| **Critical** | Unauth RCE, auth bypass, mass data exfiltration, SQL injection on prod path, shell interpolation, `Marshal.load`/`YAML.load` on untrusted input, `ERB.new(user_input).result`, secrets/`master.key` committed, `params.permit!` reaching role/admin on `Model.create`. Must fix before deploy. |
| **High** | Authenticated privilege escalation, IDOR via `Model.find(params[:id])` without `policy_scope`, SSRF reaching cloud metadata, mass assignment granting role/admin, missing `authorize @resource` / `verify_authorized`, path traversal via `send_file(params[:path])`, missing CSRF on cookie-auth POST, webhook signature compared via `==`, unauthorized `turbo_stream_from "scope_#{record.id}"`, `redirect_to params[:return_to]` without allowlist. Must fix before merge. |
| **Medium** | Hardening gap with mitigating control elsewhere, missing strong-params allowlist on non-critical endpoint, weak `Rack::Attack` limit, non-prod debug surface (Sidekiq Web / `letter_opener`), `bundle audit` advisory not yet exploited, missing `filter_parameters` entry. Should fix this PR or the next. |
| **Low** | Defense-in-depth, dependency advisory below actively-exploited threshold, hardening without a concrete current attack scenario. |

**Combined-finding rule.** When two findings compose on the **same controller action or shared `before_action` route group** into a worse threat than either alone, file as one finding at the elevated severity citing each component. If either is exploitable alone, file separately. When co-location isn't obvious from the diff, file separately and add `Note: Combined-finding rule applies if both land on the same action; verify before merge` to the lower-severity entry.

Examples: missing `authorize @user` + reachable `params.permit!` with role/admin = **Critical** unauth admin override. SSRF reachable from unauth action = **Critical** unauth SSRF. `Marshal.load(body)` + signature via `==` on a webhook = **Critical** RCE-via-forged-signature.

## Invocation

| Form                                   | Meaning                                              |
| -------------------------------------- | ---------------------------------------------------- |
| `/task-rails-review-security`          | Current branch vs base; fails fast on trunk          |
| `/task-rails-review-security <branch>` | `<branch>` vs base (3-dot diff)                      |
| `/task-rails-review-security pr-<N>`   | PR head fetched into local branch `pr-<N>`           |

When invoked as a subagent with pre-read artifacts, Steps 1-3 are skipped.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-security`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once; reuse. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - OWASP Quick Check (Rails Lens)

Use skill: `rails-security-patterns`.

| Risk                          | Rails check                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every action has explicit `authorize @resource` (Pundit) or `load_and_authorize_resource` (CanCanCan)                              |
| Injection                     | No interpolation in `where(...)`/`find_by_sql`. Use `where(name: name)` or `where("name = ?", name)`. No `Arel.sql(user_input)`    |
| Cryptographic Failures        | `Rails.application.credentials` for secrets; Active Record encryption for sensitive columns                                        |
| Security Misconfiguration     | `config.force_ssl = true`; `secure_headers` or `default_protect_from_forgery true`; CSP set                                        |
| SSRF                          | No `Net::HTTP.get(URI(user_input))` without allowlist; validate hostnames before request                                           |
| XSS                           | No `.html_safe`, `raw`, or unescape on user input. ERB `<%==`, HAML `!=`, Slim `==` default-escape; never bypass. See Step 7      |
| Insecure Design               | Pundit policy exists for every model exposed via API; default-deny in `ApplicationPolicy`                                          |
| Vulnerable Components         | `bundle audit` clean; `bin/importmap audit` for JS deps                                                                            |
| Data Integrity Failures       | No `Marshal.load` on user input; `YAML.safe_load` not `YAML.load`; cookie store keys rotated on compromise                          |
| Logging & Monitoring          | `config.filter_parameters` includes `:password`, `:token`, `:secret`, `:ssn`; no PII in `Rails.logger.info`                        |

### Step 5 - Authentication

- [ ] **Devise**: `:lockable`, `:trackable`, `:confirmable`, `:rememberable` per threat model; `password_length >= 8`; `paranoid: true` for forgot-password; custom controllers preserve `protect_from_forgery` and rate-limit decorators
- [ ] **JWT**: signature pinned (no `alg: none`); HMAC secret from credentials; expiry set; audience/issuer validated; refresh-token rotation or short access-token lifetime
- [ ] **Session**: `cookie_store, secure: true, httponly: true, same_site: :lax|:strict`
- [ ] **Password**: `has_secure_password` uses bcrypt - never hand-roll
- [ ] **Secrets hygiene**: no credentials in code or `.env` in git; `master.key`, `.env`, `config/credentials/*.key` gitignored

### Step 6 - Authorization

- [ ] **Pundit**: `include Pundit::Authorization` in `ApplicationController`; `after_action :verify_authorized` and `:verify_policy_scoped` enabled; `ApplicationPolicy` defaults to `false`
- [ ] **Pundit**: every action calls `authorize @resource` or `policy_scope(Model)` for index
- [ ] **CanCanCan**: `Ability` comprehensive; `load_and_authorize_resource` on every RESTful controller
- [ ] **Drift sweep**: every new controller action in the diff has a matching policy method (or explicit `skip_authorization` with rationale)
- [ ] **IDOR**: prefer `current_user.orders.find(params[:id])` (404 on miss) over `Order.find(params[:id])` + `authorize` (403 leaks existence). With Pundit: `policy_scope(Order).find(params[:id])` + `authorize`
- [ ] **Tenant isolation**: multi-tenant queries scoped by `current_tenant` at the model layer (`default_scope`, query objects, `acts_as_tenant`), never controller-only

### Step 7 - Input Validation, Mass Assignment, View Escaping

Use skill: `rails-security-patterns`. For server-rendered views, also use skill: `rails-view-templates`.

- [ ] **Strong params** explicit allowlist on every `create`/`update`; no `permit!`/`to_unsafe_h`
- [ ] **No privilege-bearing fields in user-facing permits**: `:role`, `:admin`, `:owner_id`, `:user_id`, `:tenant_id`, `:account_id`, `:approved`, `:status` - admin-only controller with separate policy, or drop
- [ ] **`accepts_nested_attributes_for`** limited to expected children; nested permit explicit; `_destroy: true` only when parent policy authorizes child deletion
- [ ] **File uploads**: content-type from magic bytes; size limit; `Content-Disposition: attachment`; signed short-expiry direct-upload URLs; virus scan or accepted-risk documented
- [ ] **Path traversal**: `File.read`/`send_file` with user-controlled paths uses `File.expand_path` + base-directory containment
- [ ] **Shell calls**: no `system(...)`/backticks/`Open3` with interpolated user input
- [ ] **View escaping** (skip for API-only): every diffed `.erb`/`.haml`/`.slim` audited for `<%==`, `!=`, ` == `, `raw`, `.html_safe`. Verify source is trusted (i18n, `link_to`/`form_with`/`tag` helpers) or flag
- [ ] **`sanitize`** with explicit tags/attributes only - bare `sanitize(html)` permits enough to be exploitable
- [ ] **Slim attributes**: bare `class=user_input` executes Ruby; quote literals
- [ ] **Turbo Streams**: content rendered via the same partial as initial render (`turbo_stream.append("id", html: user_input)` is XSS - use `partial:`); `turbo_stream_from "scope_#{record.id}"` requires `subscribed` authorization or `Turbo::StreamsChannel.signed_stream_name`
- [ ] **Markdown / rich-text**: `Commonmarker`/`Redcarpet`/`Kramdown` output passed through `sanitize` with explicit allowlist - allowlist is the trust boundary, not the renderer

### Step 8 - Common Rails Vulnerabilities

- [ ] **CSRF**: `protect_from_forgery with: :exception`; API-only uses `with: :null_session` only when paired with token auth
- [ ] **CORS**: `rack-cors` with explicit origins (no `origins '*'` for credentialed endpoints)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, expensive search
- [ ] **SQL injection via order/group**: `params[:sort]` allowlisted (`%w[name created_at].include?(params[:sort])`)
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated against allowlist or `allow_other_host: false`
- [ ] **Template injection**: no `ERB.new(user_input).result`
- [ ] **Mass assignment via JSON**: API controllers use `params.require(...).permit(...)`, not `Model.new(request.raw_post)`
- [ ] **Admin/dev endpoints**: `mount Sidekiq::Web`, `mount Rails::MailersController` auth-gated in production

### Step 9 - Data Protection

- [ ] PII / sensitive fields encrypted at rest (Active Record encryption or `attr_encrypted`)
- [ ] `config.filter_parameters` covers `:password`, `:password_confirmation`, `:token`, `:credit_card`, `:ssn`, `:api_key`
- [ ] Logger redaction for any custom log lines with user data
- [ ] No sensitive data in URLs - POST body or signed tokens, not query strings
- [ ] Rails credentials for all third-party keys; per-environment credential files for prod/staging

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Print confirmation.

## Output Format

```markdown
## Rails Security Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Auth:** Devise | JWT | Custom | Hybrid
**Authorization:** Pundit | CanCanCan | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment; call out Rails-specific risks like missing `verify_authorized`, `permit!`, or unfiltered `redirect_to`.]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [Rails terms: "Strong params bypassed via params.permit! in OrdersController#update"]
- **Attack scenario:** [how attacker exploits - "Attacker submits `admin: true` in JSON body and is promoted via mass assignment"]
- **Fix:** [Rails remediation with code - explicit permit, Pundit policy, etc.]

### High / Medium / Low

[Same structure]

_Omit empty severity sections. If all omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening - "Add `Rack::Attack` rate limit to /password", "Enable `verify_policy_scoped`", "Migrate to Active Record encryption for `users.api_key`"]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-cutting hardening, dependency upgrade, threat-model). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]

_Omit if no issues found._
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed (or accepted from parent)
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff/log read once
- [ ] Step 4: OWASP Top 10 reviewed with Rails framing; `rails-security-patterns` consulted
- [ ] Step 5: authentication checked for the mechanism in use; secret-hygiene verified
- [ ] Step 6: authorization drift sweep - every new action has matching policy method; IDOR and tenant isolation checked
- [ ] Step 7: strong params on every create/update; view escaping audit on every changed `.erb`/`.haml`/`.slim` (skipped only for API-only); Turbo Stream / sanitize / markdown trust boundaries checked
- [ ] Step 8: CSRF, CORS, Rack::Attack, open redirect, admin-endpoint gating verified
- [ ] Step 9: PII encryption, `filter_parameters`, credential storage verified
- [ ] Step 10: report written via `review-report-writer`; confirmation printed
- [ ] Severity rubric applied; Combined-finding rule applied where two findings compose on the same action
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] Categories with no findings explicitly stated "No issues found"
- [ ] Next Steps `[Implement]`/`[Delegate]` ordered Critical > High > Medium > Low

## Avoid

- Running state-changing git commands
- Vulnerabilities without an attack scenario
- Skipping OWASP categories that appear clean - explicitly state "No issues found"
- Generic security advice when a Rails idiom applies
- `permit!`/`to_unsafe_h` as a fix for `ParameterMissing`
- Disabling `verify_authorized` to silence warnings instead of adding the missing call
- Conflating security with general or perf review
