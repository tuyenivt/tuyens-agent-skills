---
name: task-rails-review-security
description: Rails-specific security review for strong parameters, Devise/JWT auth, Pundit/CanCanCan authorization, mass assignment, CSRF, and Rails-aware OWASP Top 10. Use when reviewing a Rails PR for security regressions or running an authz drift sweep. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to Ruby/Rails.
agent: rails-security-engineer
metadata:
  category: backend
  tags: [ruby, rails, security, pundit, devise, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Rails Security Review

## Purpose

Rails-aware security review that names Devise, JWT, Pundit/CanCanCan, strong parameters, Rails credentials, and Rack::Attack idioms directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Rails-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Ruby/Rails. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Rails PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-params and Pundit policy drift sweep across controllers
- Auditing a Devise/JWT auth flow or a new Pundit policy

**Not for:**

- Performance review (use `task-code-review-perf` or its Rails delegate)
- General code review (use `task-code-review`)
- Production incident triage (use `/task-oncall-start`)

## Invocation

Mirrors `task-code-review-security`:

| Invocation                             | Meaning                                                                                               |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-rails-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-rails-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-rails-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Ruby / Rails. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-review-security` instead.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - OWASP Quick Check (Rails Lens)

Apply the OWASP Top 10 with Rails-specific framing. Use skill: `rails-security-patterns` for canonical Rails security patterns referenced below.

| Risk                          | Rails-specific check                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | Every controller action has explicit `authorize @resource` (Pundit) or `load_and_authorize_resource` (CanCanCan). No implicit allow.       |
| Injection                     | No string interpolation in `where(...)` or `find_by_sql`. Use `where(name: name)` or `where("name = ?", name)`. No `Arel.sql(user_input)`. |
| Cryptographic Failures        | `Rails.application.credentials` for secrets; `attr_encrypted` / Active Record encryption (Rails 7+) for sensitive columns.                 |
| Security Misconfiguration     | `config.force_ssl = true` in production; `secure_headers` gem or `default_protect_from_forgery true`; CSP set.                             |
| SSRF                          | No `Net::HTTP.get(URI(user_input))` without an allowlist. Validate hostnames before request.                                               |
| XSS                           | No `.html_safe`, `raw`, or `<%== %>` on user input. ERB auto-escapes - do not bypass.                                                      |
| Insecure Design (A04)         | Pundit policy exists for every model exposed via API; default-deny in `ApplicationPolicy`.                                                 |
| Vulnerable Components (A06)   | `bundle audit` clean; no Gemfile.lock entries with known CVEs; `bin/importmap audit` for JS deps.                                          |
| Data Integrity Failures (A08) | No `Marshal.load` on user input; no `YAML.load` (use `YAML.safe_load`); cookie store keys rotated on compromise.                           |
| Logging & Monitoring (A09)    | `config.filter_parameters` includes `:password`, `:token`, `:secret`, `:ssn`, etc. No PII in `Rails.logger.info` calls.                    |

### Step 4 - Authentication (Devise / JWT / Custom)

- [ ] **Devise**: `:lockable`, `:trackable`, `:confirmable`, `:rememberable` configured per threat model; `config.password_length >= 8`; `paranoid: true` for forgot-password
- [ ] **Devise**: custom controllers preserve the `protect_from_forgery` and rate-limit decorators
- [ ] **JWT**: signature algorithm pinned (no `alg: none`); HMAC secret from credentials, not env-only; expiry set; audience/issuer claims validated
- [ ] **JWT**: refresh token rotation; revocation list or short access-token lifetime
- [ ] **Session**: `config.session_store :cookie_store, secure: true, httponly: true, same_site: :lax` (or `:strict` for high-security)
- [ ] **Password**: `has_secure_password` uses bcrypt (Rails default) - never hand-roll hashing
- [ ] **No credentials in code, ENV files committed to git, or `Rails.logger`** - check `master.key`, `.env`, `config/credentials/*.key` are gitignored

### Step 5 - Authorization (Pundit / CanCanCan / Custom)

- [ ] **Pundit**: `include Pundit::Authorization` in `ApplicationController`; `after_action :verify_authorized` and `after_action :verify_policy_scoped` enabled (skip with explicit `skip_authorization` only for genuinely public actions)
- [ ] **Pundit**: every controller action calls `authorize @resource` or uses `policy_scope(Model)` for index actions
- [ ] **Pundit**: `ApplicationPolicy` defaults to `false` for all actions; subclasses opt in explicitly
- [ ] **CanCanCan**: `Ability` class is comprehensive; `load_and_authorize_resource` on every RESTful controller; no orphan actions
- [ ] **Authorization drift sweep**: every new controller action added in the diff has a corresponding policy method (or explicit skip with rationale)
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `current_tenant` at the model layer (`default_scope`, query objects, or `acts_as_tenant`) - never rely on controller-level filtering alone

### Step 6 - Input Validation and Mass Assignment

- [ ] **Strong params**: every `create`/`update` action uses `params.require(:model).permit(...)` with an explicit allowlist
- [ ] **No `params.permit!` or `params.to_unsafe_h`** in production code paths
- [ ] **Nested attributes** (`accepts_nested_attributes_for`) limited to expected child models; nested permit lists explicit
- [ ] **File uploads** (Active Storage, CarrierWave, Shrine):
  - File type validated by content (magic bytes), not just extension
  - Per-file size limit enforced; total request body limit at Rack level (`Rack::Attack`)
  - `Content-Disposition: attachment` on serve to prevent inline rendering of uploaded HTML/SVG
  - Direct-upload signed URLs scoped to single object with short expiry
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: any `File.read` / `send_file` with user-controlled paths uses `File.expand_path` and verifies the result is within an allowed base directory
- [ ] **Shell calls**: no `system(...)`, `` `...` ``, or `Open3` with interpolated user input - use API alternatives

### Step 7 - Common Rails Vulnerability Patterns

- [ ] **CSRF**: `protect_from_forgery with: :exception` in `ApplicationController`; API-only controllers use `protect_from_forgery with: :null_session` only when paired with token auth
- [ ] **CORS**: `rack-cors` configured with explicit origins (no `origins '*'` for credentialed endpoints)
- [ ] **Rack::Attack**: rate limits on `/login`, `/password`, `/signup`, and any expensive search endpoint
- [ ] **SQL injection via order/group**: `params[:sort]` passed to `.order(...)` is whitelisted (`%w[name created_at].include?(params[:sort])`)
- [ ] **Open redirect**: `redirect_to params[:return_to]` validated against an allowlist or uses `redirect_to(..., allow_other_host: false)`
- [ ] **Server-side template injection**: no `ERB.new(user_input).result` on user-controlled templates
- [ ] **Mass assignment via JSON**: API controllers using `params.require(...).permit(...)` not `Model.new(request.raw_post)`
- [ ] **Admin/dev endpoints**: `mount Sidekiq::Web` and `mount Rails::MailersController` are auth-gated in production

### Step 8 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (Active Record encryption or `attr_encrypted`)
- [ ] **`config.filter_parameters`** covers all sensitive keys (`:password`, `:password_confirmation`, `:token`, `:credit_card`, `:ssn`, `:api_key`)
- [ ] **Logger redaction** for any custom log lines containing user data
- [ ] **Database backups** encrypted; access controlled
- [ ] **No sensitive data in URLs** (use POST body or signed tokens, not query strings)
- [ ] **Rails credentials** used for all third-party API keys; environment-specific credential files for prod/staging

## Rules

- Always validate at system boundaries (controller params, external API responses)
- Never bypass strong params with `permit!` or `to_unsafe_h` to fix a `ParameterMissing` error
- Never disable Pundit's `verify_authorized` callback to silence a `AuthorizationNotPerformedError`
- Log security events (login failure, authorization denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny in policies

## Self-Check

- [ ] Stack confirmed as Rails before any Rails-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] OWASP Top 10 reviewed with Rails framing (Step 3) - every category checked, none silently skipped
- [ ] `rails-security-patterns` consulted for canonical Rails patterns
- [ ] Authentication step run for the auth mechanism in use (Devise / JWT / custom)
- [ ] **Authorization drift sweep**: every new controller action in the diff has a matching Pundit/CanCanCan policy method
- [ ] Strong params reviewed on every `create`/`update`; no `permit!` or `to_unsafe_h`
- [ ] File upload, path traversal, and shell-call checks run if applicable
- [ ] CSRF, CORS, Rack::Attack, open redirect, and admin-endpoint gating verified
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] If no findings: explicitly state "No issues found" per category - do not omit sections silently
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

## Output Format

```markdown
## Rails Security Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Auth:** Devise | JWT | Custom | Hybrid
**Authorization:** Pundit | CanCanCan | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Rails-specific risks like missing Pundit `verify_authorized`, `permit!` use, or unfiltered `redirect_to`.]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability described in Rails terms - e.g., "Strong params bypassed via params.permit! in OrdersController#update"]
- **Attack scenario:** [how an attacker exploits this - e.g., "Attacker submits `admin: true` in JSON body and is promoted via mass assignment"]
- **Fix:** [specific Rails remediation with code example - explicit permit list, Pundit policy, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `Rack::Attack` rate limit to /password endpoint", "Enable `verify_policy_scoped` on ApplicationController", "Migrate to Active Record encryption for `users.api_key`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace params.permit! with explicit allowlist in OrdersController#update"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `bundle audit` and upgrade flagged gems - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `admin: true` and gains admin")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Rails idiom applies (say "use Pundit `authorize @resource`", not "add an authorization check")
- Suggesting `params.permit!` or `to_unsafe_h` as a fix for `ActionController::ParameterMissing`
- Disabling `verify_authorized` / `verify_policy_scoped` to silence Pundit warnings instead of adding the missing policy call
- Conflating security review with general code quality or performance review - delegate those to their workflows
