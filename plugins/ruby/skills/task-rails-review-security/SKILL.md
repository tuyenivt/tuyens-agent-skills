---
name: task-rails-review-security
description: Rails security review: strong params, Devise/JWT, Pundit/CanCanCan, mass assignment, CSRF, OWASP Top 10.
agent: rails-security-engineer
metadata:
  category: backend
  tags: [ruby, rails, security, pundit, devise, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.

# Rails Security Review

Rails-aware security review naming Devise, JWT, Pundit/CanCanCan, strong params, Rails credentials, and Rack::Attack idioms directly. Findings include attack scenarios and Rails-specific remediations. Stack-specific delegate of `task-code-review-security`.

## When to Use

- Reviewing a Rails PR for security regressions
- Pre-deploy hardening on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-params / Pundit drift sweep
- Auditing a Devise/JWT flow or new Pundit policy

**Not for:** perf (`task-code-review-perf`), general review (`task-code-review`), incident triage (`/task-oncall-start`).

**Depth.** Always full - no `quick`/`standard`/`deep`. Security has cliff-edged consequences (auth bypass, RCE) that don't benefit from a "light" mode. Scope by file, not depth.

## Severity Rubric

| Severity | Definition |
| -------- | ---------- |
| **Critical** | Unauth RCE, auth bypass, mass data exfiltration, SQL injection on prod code path, `system("... #{user_input}")` / backticks, `Marshal.load` on untrusted input, `YAML.load` (not `safe_load`) on untrusted, `ERB.new(user_input).result`, secrets / `master.key` / credentials committed, `params.permit!` on a User/Role model where role elevation reaches `Model.create(params[:user])`. Must fix before deploy. |
| **High** | Authenticated privilege escalation, IDOR with sensitive data via `Model.find(params[:id])` without `policy_scope`, SSRF reaching cloud metadata or internal services, mass assignment granting role/admin, missing `authorize @resource` or `verify_authorized`, path traversal via `send_file(params[:path])` without containment, missing CSRF token on cookie-auth POST, webhook signature compared via `==` (timing attack), unauthorized `turbo_stream_from "scope_#{record.id}"` subscription, `redirect_to params[:return_to]` without `allow_other_host: false` / allowlist. Must fix before merge. |
| **Medium** | Hardening gap with mitigating control elsewhere (CORS allowlist when proxy enforces origin), missing strong-params allowlist on non-critical endpoint, weak `Rack::Attack` rate limit on non-critical, debug surface on non-prod (Sidekiq Web / `letter_opener`), `bundle audit` advisory not yet exploited, missing `filter_parameters` entry. Should fix this PR or the next. |
| **Low** | Defense-in-depth, dependency advisory below actively-exploited threshold, hardening without a concrete current attack scenario. |

**Combined-finding rule.** When two findings compose on the **same code path** into a worse threat than either alone, file as a single finding at the elevated severity citing each component. Examples:

- Missing `authorize @user` (High) + mass assignment via `User.update(params.permit!)` with `role`/`admin` reachable (High) on the **same action** = **Critical** unauth admin override
- Missing `before_action :authenticate_user!` (High) + admin-scope action like `User.find(params[:id]).update(params[:user])` (High) + missing Pundit policy (High) on the **same route** = **Critical** unauth admin takeover
- SSRF via `Net::HTTP.get(URI(params[:url]))` (High) + reachable from unauth action (High) = **Critical** unauth SSRF
- `Marshal.load(webhook_body)` (Critical) + signature via `==` instead of `secure_compare` (High) on a webhook = **Critical** RCE-via-forged-signature

Rule of thumb: if the realistic exploit path **requires both findings to land**, they are one finding. If either is exploitable alone, file separately.

**Same-action co-location.** Combining requires both land on the same controller action or same route group with shared `before_action`. When co-location isn't obvious from the diff, file separately and add `Note: Combined-finding rule applies if both land on the same action; verify and merge before merge` to the lower-severity entry. Don't silently merge or silently keep separate.

## Invocation

| Form                                   | Meaning                                              |
| -------------------------------------- | ---------------------------------------------------- |
| `/task-rails-review-security`          | Current branch vs base; fails fast on trunk          |
| `/task-rails-review-security <branch>` | `<branch>` vs base (3-dot diff)                      |
| `/task-rails-review-security pr-<N>`   | PR head fetched into local branch `pr-<N>`           |

When invoked as a subagent of `task-code-review-security` with the precondition handle + pre-read diff/log, Step 2 is skipped.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Rails, redirect to `/task-code-review-security`.

### Step 2 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read diff and log once via `git diff <base>...<head>` and `git log <base>..<head>`; reuse. Skip if running as subagent with pre-read artifacts. If `review-precondition-check` stops with fail-fast, surface verbatim and stop.

### Step 3 - OWASP Quick Check (Rails Lens)

Use skill: `rails-security-patterns`.

| Risk                          | Rails check                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every action has explicit `authorize @resource` (Pundit) or `load_and_authorize_resource` (CanCanCan)                              |
| Injection                     | No interpolation in `where(...)` / `find_by_sql`. Use `where(name: name)` or `where("name = ?", name)`. No `Arel.sql(user_input)`  |
| Cryptographic Failures        | `Rails.application.credentials` for secrets; Active Record encryption (Rails 7+) for sensitive columns                             |
| Security Misconfiguration     | `config.force_ssl = true` in production; `secure_headers` gem or `default_protect_from_forgery true`; CSP set                      |
| SSRF                          | No `Net::HTTP.get(URI(user_input))` without an allowlist; validate hostnames before request                                        |
| XSS                           | No `.html_safe`, `raw`, or unescape on user input. ERB (`<%==`), HAML (`!=`), Slim (`==`) - default-escape; never bypass. See Step 6.5 |
| Insecure Design               | Pundit policy exists for every model exposed via API; default-deny in `ApplicationPolicy`                                          |
| Vulnerable Components         | `bundle audit` clean; `bin/importmap audit` for JS deps                                                                            |
| Data Integrity Failures       | No `Marshal.load` on user input; `YAML.safe_load` not `YAML.load`; cookie store keys rotated on compromise                          |
| Logging & Monitoring          | `config.filter_parameters` includes `:password`, `:token`, `:secret`, `:ssn`; no PII in `Rails.logger.info`                        |

### Step 4 - Authentication

- [ ] **Devise**: `:lockable`, `:trackable`, `:confirmable`, `:rememberable` per threat model; `password_length >= 8`; `paranoid: true` for forgot-password
- [ ] **Devise**: custom controllers preserve `protect_from_forgery` and rate-limit decorators
- [ ] **JWT**: signature pinned (no `alg: none`); HMAC secret from credentials; expiry set; audience/issuer claims validated
- [ ] **JWT**: refresh token rotation; revocation list or short access-token lifetime
- [ ] **Session**: `cookie_store, secure: true, httponly: true, same_site: :lax` (or `:strict`)
- [ ] **Password**: `has_secure_password` uses bcrypt - never hand-roll
- [ ] **No credentials in code or `.env` in git, no creds in `Rails.logger`** - `master.key`, `.env`, `config/credentials/*.key` gitignored

### Step 5 - Authorization

- [ ] **Pundit**: `include Pundit::Authorization` in `ApplicationController`; `after_action :verify_authorized` and `:verify_policy_scoped` enabled (skip with explicit `skip_authorization` only for genuinely public actions)
- [ ] **Pundit**: every action calls `authorize @resource` or `policy_scope(Model)` for index
- [ ] **Pundit**: `ApplicationPolicy` defaults to `false`; subclasses opt in
- [ ] **CanCanCan**: `Ability` comprehensive; `load_and_authorize_resource` on every RESTful controller
- [ ] **Drift sweep**: every new controller action in the diff has a matching policy method (or explicit skip with rationale)
- [ ] **IDOR**: prefer `current_user.orders.find(params[:id])` (404 on miss = no enumeration) over `Order.find(params[:id])` + `authorize` (403 leaks existence). With Pundit: `policy_scope(Order).find(params[:id])` + `authorize`
- [ ] **Tenant isolation**: multi-tenant queries scoped by `current_tenant` at the model layer (`default_scope`, query objects, `acts_as_tenant`) - never controller-only

### Step 6 - Input Validation and Mass Assignment

Use skill: `rails-security-patterns`.

- [ ] **Strong params** explicit allowlist on every `create`/`update`; no `permit!` / `to_unsafe_h`
- [ ] **No privilege-bearing fields in user-facing permit lists**: `:role`, `:admin`, `:owner_id`, `:user_id`, `:tenant_id`, `:account_id`, `:approved`, `:status` (when server-controlled). Either admin-only controller with separate policy, or drop
- [ ] **`accepts_nested_attributes_for`** limited to expected children; nested permit explicit; `_destroy: true` only when parent policy authorizes child deletion
- [ ] **File uploads**: content-type from magic bytes (not extension); size limit; `Content-Disposition: attachment`; signed short-expiry direct-upload URLs; virus scan or accepted-risk documented
- [ ] **Path traversal**: `File.read` / `send_file` with user-controlled paths uses `File.expand_path` + base-directory containment
- [ ] **Shell calls**: no `system(...)` / backticks / `Open3` with interpolated user input

### Step 6.5 - View-Layer Escaping (server-rendered)

Skip for API-only. Otherwise use skill: `rails-view-templates`.

```bash
git diff <base>...<head> -- '*.erb'  | grep -E '<%==|<%= *raw |\.html_safe'
git diff <base>...<head> -- '*.haml' | grep -E '!= |\.html_safe'
git diff <base>...<head> -- '*.slim' | grep -E ' == |^== |\.html_safe| raw '
```

Every hit is candidate XSS - verify source is trusted (i18n, `link_to` / `form_with` / `tag` helpers) or flag.

- [ ] Engine matched to file (Slim's `==` rule applies to `.slim` only)
- [ ] No `.html_safe` on user input - `sanitize` with explicit allowlist
- [ ] Slim attribute-value Ruby evaluation: bare `class=user_input` executes Ruby - quote literals
- [ ] `sanitize` always with explicit tags/attributes - bare `sanitize(html)` permits enough to be exploitable
- [ ] No HTML built via string interpolation + `.html_safe` - use `link_to` / `tag.a` / `content_tag`
- [ ] Turbo Stream content rendered via same partials as initial render; `turbo_stream.append("id", html: user_input)` is XSS - use `partial:`
- [ ] Turbo Streams subscription authorization: `turbo_stream_from "scope_#{record.id}"` is WebSocket IDOR unless `subscribed` callback verifies access (or stream names signed via `Turbo::StreamsChannel.signed_stream_name`)
- [ ] Stimulus `data-action` values are JS event names - no user-controlled values
- [ ] Markdown / rich-text pipelines (`Commonmarker`, `Redcarpet`, `Kramdown`): always pass rendered HTML through `sanitize` with explicit allowlist. The allowlist is the trust boundary, not the renderer

### Step 7 - Common Rails Vulnerabilities

- [ ] **CSRF**: `protect_from_forgery with: :exception`; API-only uses `with: :null_session` only when paired with token auth
- [ ] **CORS**: `rack-cors` with explicit origins (no `origins '*'` for credentialed endpoints)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, expensive search
- [ ] **SQL injection via order/group**: `params[:sort]` passed to `.order(...)` whitelisted (`%w[name created_at].include?(params[:sort])`)
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated against allowlist or `allow_other_host: false`
- [ ] **Template injection**: no `ERB.new(user_input).result`
- [ ] **Mass assignment via JSON**: API controllers using `params.require(...).permit(...)` not `Model.new(request.raw_post)`
- [ ] **Admin/dev endpoints**: `mount Sidekiq::Web`, `mount Rails::MailersController` auth-gated in production

### Step 8 - Data Protection

- [ ] PII / sensitive fields encrypted at rest (Active Record encryption or `attr_encrypted`)
- [ ] `config.filter_parameters` covers `:password`, `:password_confirmation`, `:token`, `:credit_card`, `:ssn`, `:api_key`
- [ ] Logger redaction for any custom log lines with user data
- [ ] Database backups encrypted; access controlled
- [ ] No sensitive data in URLs - POST body or signed tokens, not query strings
- [ ] Rails credentials for all third-party keys; per-environment credential files for prod/staging

### Step 9 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write before ending. Print confirmation.

## Rules

- Validate at system boundaries (controller params, external API responses)
- Never bypass strong params with `permit!` / `to_unsafe_h`
- Never disable Pundit's `verify_authorized` to silence `AuthorizationNotPerformedError`
- Log security events without sensitive data
- Default-deny in policies

## Self-Check

- [ ] Stack confirmed; `review-precondition-check` ran (or handle received); diff/log read once
- [ ] When `head_matches_current` was false, explicit user approval obtained (skipped if subagent)
- [ ] OWASP Top 10 reviewed with Rails framing - every category checked
- [ ] `rails-security-patterns` consulted for canonical patterns
- [ ] Authentication checked for the mechanism in use
- [ ] Authorization drift sweep: every new action has matching policy method
- [ ] Strong params reviewed on every `create`/`update`; no `permit!` / `to_unsafe_h`
- [ ] View-layer escaping audit (Step 6.5) on every changed `.erb`/`.haml`/`.slim` - skipped only for API-only
- [ ] File upload, path traversal, shell-call checks run if applicable
- [ ] CSRF, CORS, Rack::Attack, open redirect, admin-endpoint gating verified
- [ ] Severity rubric applied consistently; Combined-finding rule applied where two findings compose
- [ ] Every finding includes attack scenario - not just "input not validated"
- [ ] If no findings, explicitly state "No issues found" per category
- [ ] Next Steps with `[Implement]` / `[Delegate]` ordered Critical > High > Medium > Low
- [ ] Report written via `review-report-writer`; confirmation printed

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

## Avoid

- Running state-changing git commands
- Vulnerabilities without an attack scenario
- Skipping OWASP categories that appear clean - explicitly state "No issues found"
- Generic security advice when a Rails idiom applies
- `permit!` / `to_unsafe_h` as a fix for `ParameterMissing`
- Disabling `verify_authorized` to silence warnings instead of adding the missing call
- Conflating security with general or perf review
