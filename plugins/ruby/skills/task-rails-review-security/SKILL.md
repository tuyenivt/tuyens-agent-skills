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

Reviewing a Rails PR for security regressions; pre-deploy hardening on auth, authz, file upload, payment, or PII paths; periodic strong-params/Pundit drift sweep; auditing a Devise/JWT flow or new Pundit policy.

**Depth.** Always full. Security has cliff-edged consequences. Scope by file, not depth.

## Severity Rubric

| Severity | Definition |
| -------- | ---------- |
| **Critical** (fix before deploy) | Unauth RCE, auth bypass, mass data exfiltration, SQLi on prod path, shell interpolation, `Marshal.load`/`YAML.load` on untrusted input, `ERB.new(user_input).result`, secrets/`master.key` committed, `params.permit!` on `Model.create`/`Model.update` where the model exposes role/admin/tenant/owner/billing fields (treat by-table-schema, not by current diff) |
| **High** (fix before merge) | Authenticated privilege escalation, IDOR via `Model.find(params[:id])` without `policy_scope`, SSRF reaching cloud metadata, missing `authorize @resource` / `verify_authorized`, path traversal via `send_file(params[:path])`, missing CSRF on cookie-auth POST, webhook signature compared via `==`, unauthorized `turbo_stream_from "scope_#{record.id}"`, `redirect_to params[:return_to]` without allowlist |
| **Medium** | Hardening gap with mitigating control elsewhere, weak `Rack::Attack` limit, non-prod debug surface (Sidekiq Web / `letter_opener`), `bundle audit` advisory not yet exploited, missing `filter_parameters` entry |
| **Low** | Defense-in-depth, dependency advisory below actively-exploited threshold |

**Combined-finding rule.** When N actions share a missing `before_action` gate (auth, admin, tenant), file **one** combined finding at the elevated severity, list all affected actions, and cite the worst dangerous payload as the attack scenario. File separately only when actions have distinct auth paths or distinct attack chains. When two findings on the **same action** compose into a worse threat, file as one. Example: `Admin::ExportsController` missing admin gate + 5 dangerous actions = one Critical "missing admin gate compounds [`Marshal.load`, shell exec, SSRF, path traversal, hardcoded webhook secret]" finding.

## Invocation

`/task-rails-review-security [<branch>|pr-<N>]` - current branch vs base; fails fast on trunk. When invoked as subagent with pre-read artifacts, Steps 1-3 are skipped.

## Workflow

### Step 1 - Load Behavioral Rules
Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack
Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Rails, redirect to `/task-code-review-security`. Record the **auth flavor** (Devise / JWT / custom) and **authz flavor** (Pundit / CanCanCan / custom) - flavor-specific checks below run only for the detected flavor.

### Step 3 - Resolve the Diff
Use skill: `review-precondition-check`. On approval, read `git diff` and `git log` once. Skip if parent passed pre-read artifacts. Surface fail-fast verbatim and stop.

### Step 4 - OWASP Quick Check (Rails Lens)

Use skill: `rails-security-patterns`. Walk each row, but skip when the diff cannot exercise it (e.g., Cryptographic Failures when no new sensitive columns; Vulnerable Components when no `Gemfile.lock` change).

| Risk                          | Rails check                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every action has explicit `authorize @resource` (Pundit) or `load_and_authorize_resource` (CanCanCan)                              |
| Injection                     | No interpolation in `where(...)`/`find_by_sql`; no `Arel.sql(user_input)`; `params[:sort]` allowlisted (`%w[name created_at].include?`) |
| Cryptographic Failures        | `Rails.application.credentials` for secrets; Active Record encryption for sensitive columns                                        |
| Security Misconfiguration     | `config.force_ssl = true`; `protect_from_forgery` enforced; CSP set                                                                |
| SSRF                          | No `Net::HTTP.get(URI(user_input))` without allowlist; validate hostnames before request                                           |
| XSS                           | No `.html_safe`, `raw`, or unescape on user input. ERB `<%==`, HAML `!=`, Slim `==` default-escape; never bypass. See Step 7      |
| Insecure Design               | Pundit policy exists for every model exposed via API; default-deny in `ApplicationPolicy`                                          |
| Vulnerable Components         | `bundle audit` clean; `bin/importmap audit` for JS deps                                                                            |
| Data Integrity Failures       | No `Marshal.load` on user input; `YAML.safe_load` not `YAML.load`; cookie store keys rotated on compromise                          |
| Logging & Monitoring          | `config.filter_parameters` covers `:password`, `:token`, `:secret`, `:ssn`, `:api_key`, `:credit_card`, `:authorization`; no PII in `Rails.logger.info` |

### Step 5 - Authentication (only when diff touches auth)

Run the matching flavor sub-bullets only:

- **Devise**: `:lockable`, `:trackable`, `:confirmable`, `:rememberable` per threat model; `password_length >= 8`; `paranoid: true` for forgot-password; custom controllers preserve `protect_from_forgery` and rate-limit decorators
- **JWT**: signature pinned (no `alg: none`); HMAC secret from credentials; expiry, audience, issuer validated; refresh-token rotation or short access-token lifetime
- **Session**: `cookie_store, secure: true, httponly: true, same_site: :lax|:strict`
- **Password**: `has_secure_password` uses bcrypt; never hand-rolled
- **Secrets hygiene**: no credentials in code or `.env` in git; `master.key`, `.env`, `config/credentials/*.key` gitignored

### Step 6 - Authorization

- [ ] **Pundit**: `include Pundit::Authorization`; `after_action :verify_authorized` and `:verify_policy_scoped` enabled; `ApplicationPolicy` defaults to `false`; every diffed action calls `authorize @resource` or `policy_scope(Model)` (or explicit `skip_authorization` with rationale)
- [ ] **CanCanCan**: `Ability` comprehensive; `load_and_authorize_resource` on every RESTful controller
- [ ] **IDOR**: prefer `current_user.orders.find(params[:id])` (404) over `Order.find(params[:id])` + `authorize` (403 leaks existence). With Pundit: `policy_scope(Order).find(params[:id])` + `authorize`
- [ ] **Tenant isolation**: queries scoped by `current_tenant` at the model layer (`default_scope`, query objects, `acts_as_tenant`), not controller-only

### Step 7 - Input, Mass Assignment, View Escaping

- [ ] **Strong params** explicit allowlist on every diffed `create`/`update`; no `permit!`/`to_unsafe_h`. Privilege-bearing fields (`:role`, `:admin`, `:owner_id`, `:user_id`, `:tenant_id`, `:account_id`, `:approved`, `:status`) require an admin-only controller with a separate policy, or must be dropped from the permit
- [ ] **`accepts_nested_attributes_for`** limited to expected children; nested permit explicit; `_destroy: true` only when parent policy authorizes child deletion
- [ ] **File uploads**: content-type from magic bytes; size limit; `Content-Disposition: attachment`; signed short-expiry direct-upload URLs; virus scan or accepted-risk documented
- [ ] **Path traversal**: `File.read`/`send_file` with user-controlled paths uses `File.expand_path` + base-directory containment
- [ ] **Shell calls**: no `system(...)`/backticks/`Open3` with interpolated user input
- [ ] **View escaping** (server-rendered only - skip for API-only): audit every diffed `.erb`/`.haml`/`.slim` for `<%==`, `!=`, ` == `, `raw`, `.html_safe`. Use skill `rails-view-templates` when the diff has >1 templated file; inline check sufficient for a single small template
- [ ] **`sanitize`** with explicit tags/attributes only - bare `sanitize(html)` permits enough to be exploitable
- [ ] **Slim attributes**: bare `class=user_input` executes Ruby; quote literals
- [ ] **Turbo Streams**: `turbo_stream.append("id", html: user_input)` is XSS - render via `partial:`; `turbo_stream_from "scope_#{record.id}"` requires `subscribed` authorization or `Turbo::StreamsChannel.signed_stream_name`
- [ ] **Markdown / rich-text**: `Commonmarker`/`Redcarpet`/`Kramdown` output passed through `sanitize` with explicit allowlist

### Step 8 - Common Rails Vulnerabilities

- [ ] **CSRF**: `protect_from_forgery with: :exception`; API-only uses `:null_session` only when paired with token auth. Flag any `skip_before_action :verify_authenticity_token` without a stated rationale
- [ ] **CORS**: `rack-cors` with explicit origins (no `origins '*'` for credentialed endpoints)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, expensive search
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated against allowlist or `allow_other_host: false`
- [ ] **Template injection**: no `ERB.new(user_input).result`
- [ ] **Mass assignment via JSON**: API controllers use `params.require(...).permit(...)`, not `Model.new(request.raw_post)`
- [ ] **Admin/dev endpoints**: `mount Sidekiq::Web`, `mount Rails::MailersController` auth-gated in production

### Step 9 - Data Protection

- [ ] PII / sensitive fields encrypted at rest (Active Record encryption or `attr_encrypted`)
- [ ] Logger redaction for custom log lines with user data (extends `filter_parameters` to manual log writes)
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

[2-3 sentence assessment; call out Rails-specific risks.]

## Findings

### Critical

- **Location:** [file:line, or `Controller#action1, #action2, #action3` for combined findings]
- **Issue:** [Rails terms: "Strong params bypassed via `params.permit!` in OrdersController#update"]
- **Attack scenario:** [how attacker exploits]
- **Fix:** [Rails remediation with code]

### High / Medium / Low

[Same structure]

_Omit empty severity sections. If all omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening]

## Next Steps

Prioritized. Each `[Implement]` (localized) or `[Delegate]` (cross-cutting hardening, dependency upgrade, threat-model). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]

_Omit if no issues found._
```

## Self-Check

- [ ] Steps 1-3 ran (or accepted from parent); diff/log read once; auth + authz flavor recorded
- [ ] Step 4: OWASP rows walked; skip-explanations stated when a row didn't apply
- [ ] Step 5: only the detected auth flavor's bullets ran
- [ ] Step 6: drift sweep - every new action has matching policy method; IDOR + tenant isolation checked
- [ ] Step 7: strong params on every create/update; view escaping audited on changed templates (skipped for API-only)
- [ ] Step 8-9: CSRF/CORS/admin gating/data protection covered
- [ ] Combined-finding rule applied - shared-gate vulnerabilities filed as one entry, not N near-duplicates
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] Severity sections with no findings explicitly stated "No issues found"
- [ ] Step 10: report via `review-report-writer`; confirmation printed
- [ ] Next Steps `[Implement]`/`[Delegate]` ordered Critical > High > Medium > Low

## Avoid

- Vulnerabilities without an attack scenario
- Generic security advice when a Rails idiom applies
- `permit!`/`to_unsafe_h` as a fix for `ParameterMissing`
- Disabling `verify_authorized` to silence warnings instead of adding the missing call
- Filing N near-duplicate findings when one combined finding captures the shared root cause
- Walking through flavor-specific bullets (Devise/JWT) when the diff doesn't touch that flavor
