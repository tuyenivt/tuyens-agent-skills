---
name: task-rails-review-security
description: Rails security review: strong params, Devise/JWT auth, Pundit/CanCanCan authz, mass assignment, CSRF, OWASP Top 10.
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

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path (`Order.where("status = '#{params[:status]}'")`, `find_by_sql("... #{user_input}")`), `system("... #{user_input}")` / `` `... #{user_input}` ``, secrets / `master.key` / `Rails.application.credentials` content / `secret_key_base` committed in source, `Marshal.load` on untrusted input, `YAML.load` (not `YAML.safe_load`) on untrusted input, `ERB.new(user_input).result` on user-controlled template, `<%== user_input %>` (ERB) / `!= user_input` (HAML) / `== user_input` (Slim) on attacker-controlled value reaching a privileged surface, `params.permit!` on a User / Role model where role-elevation field is exposed via `Model.create(params[:user])`. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data via `Model.find(params[:id])` without `policy_scope` / association-scoped lookup, SSRF reaching cloud metadata or internal services, mass assignment via `params.permit!` granting role/admin, missing `authorize @resource` / Pundit policy on user-data action, missing `verify_authorized` callback, path traversal via `send_file(params[:path])` without `File.expand_path` + base check, missing CSRF token on cookie-auth POST, webhook signature compared via `==` (timing attack), unauthorized `turbo_stream_from "scope_#{record.id}"` subscription leaking broadcasts, `redirect_to params[:return_to]` without `allow_other_host: false` / allowlist. Must fix before merge. |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS allowlist when reverse proxy enforces origin), missing strong-params allowlist on a non-critical endpoint, weak `Rack::Attack` rate limiting on a non-critical endpoint, debug exposure on a non-prod profile (Sidekiq Web / `letter_opener` reachable), `bundle audit` advisory not yet exploited, missing `config.filter_parameters` entry for a sensitive key. Should fix this PR or the next one. |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold (`bundle audit` info-level), hardening recommendations without a concrete current attack scenario.                                                                          |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file them as a single finding at the elevated severity and cite each component. Examples:

- Missing `authorize @user` on a user-data action (High, alone) + mass assignment via `User.update(params.permit!)` with privileged fields (`role`, `admin`) reachable (High, alone) on the *same action* = **Critical** unauthenticated admin override (anyone authenticated can `PATCH /users/:id` with `{"role": "admin"}`).
- Missing `before_action :authenticate_user!` on a controller action (High, alone) + admin-scope action like `User.find(params[:id]).update(params[:user])` (High, alone) + missing Pundit policy (High, alone) on the *same route* = **Critical** unauthenticated admin takeover (anyone on the internet can promote any user to admin).
- Missing ownership check (High, alone) + AR model returned via `render json: @user` exposing `password_digest` + `remember_token` (Medium, alone) on the *same action* = **Critical** account takeover.
- Missing `before_action :authenticate_user!` on `GET /orders/:id` (High, alone) + `render json: @order` returning the AR record directly (High, alone) on the *same action* = **Critical** unauthenticated entity exposure.
- SSRF via `Net::HTTP.get(URI(params[:url]))` (High, alone) + reachable from an unauthenticated action (High, alone) = **Critical** unauth SSRF.
- `Marshal.load(webhook_body)` (Critical, alone) + signature verification via `==` instead of `ActiveSupport::SecurityUtils.secure_compare` (High, alone) on a webhook endpoint = **Critical** RCE-via-forged-signature (the `==` is timing-attackable, but with `Marshal.load` the success path itself is the gadget chain trigger - severity stays Critical, but cite both).

The rule of thumb: if the realistic exploit path requires both findings to land for the attack to succeed, they are one finding. If either finding is exploitable on its own, file them separately at their independent severities.

**Same-action co-location.** Combining findings requires confirming both land on the *same code path* (same controller action, or same route group with shared `before_action`). When the diff doesn't make co-location obvious - e.g., the IDOR is in `OrdersController#show` but the AR-leak appears on a different action in the same controller - file the findings separately at their independent severities and add a one-line `Note: Combined-finding rule applies if both land on the same action; verify and merge before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

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

Use skill: `stack-detect` to confirm Ruby / Rails. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-rails-review` (parent already detected Rails), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-review-security` instead.

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
| XSS                           | No `.html_safe`, `raw`, or unescape operators on user input. ERB (`<%==`), HAML (`!=`), Slim (`==`) all auto-escape by default - do not bypass. See Step 6.5 for engine-specific checks. |
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
- [ ] **IDOR (Insecure Direct Object Reference)**: lookups in user-facing controllers scope through the user's association rather than `Model.find(params[:id])` followed by `authorize`. Prefer `current_user.orders.find(params[:id])` (404 on miss = no enumeration) over `Order.find(params[:id])` then `authorize @order` (which gives 403 on someone else's record - leaking that the ID exists). For Pundit users, combine `policy_scope(Order).find(params[:id])` with `authorize` for the same effect.
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `current_tenant` at the model layer (`default_scope`, query objects, or `acts_as_tenant`) - never rely on controller-level filtering alone

### Step 6 - Input Validation and Mass Assignment

Use skill: `rails-security-patterns` for canonical strong-params, mass-assignment, IDOR, upload-validation, and open-redirect patterns. Apply as the review checklist:

- [ ] **Strong params** with explicit allowlist on every `create`/`update`; no `params.permit!` / `to_unsafe_h`
- [ ] **No privilege-bearing fields in user-facing permit lists**: `:role`, `:admin`, `:owner_id`, `:user_id`, `:tenant_id`, `:account_id`, `:approved`, `:status` (when server-controlled). Either gate behind an admin-only controller with a separate policy, or drop from the permit list
- [ ] **`accepts_nested_attributes_for`** limited to expected children; nested permit list explicit; `_destroy: true` only when the parent policy authorizes child deletion
- [ ] **File uploads** (Active Storage / CarrierWave / Shrine): content-type from magic bytes (not extension); size limit; `Content-Disposition: attachment` on serve; signed direct-upload URLs scoped + short-expiry; virus scan or accepted-risk documented
- [ ] **Path traversal**: `File.read` / `send_file` with user-controlled paths uses `File.expand_path` + base-directory containment check
- [ ] **Shell calls**: no `system(...)` / `` `...` `` / `Open3` with interpolated user input

### Step 6.5 - View-Layer Escaping (server-rendered apps only)

Skip if the app is API-only (no `app/views/` beyond mailers). Otherwise use skill: `rails-view-templates` for engine-specific escape rules and Slim traps; this step adds the review-side scan against changed `.erb` / `.haml` / `.slim` files.

**Per-engine grep recipe** for the unescape surface:

```bash
git diff <base>...<head> -- '*.erb'  | grep -E '<%==|<%= *raw |\.html_safe'
git diff <base>...<head> -- '*.haml' | grep -E '!= |\.html_safe'
git diff <base>...<head> -- '*.slim' | grep -E ' == |^== |\.html_safe| raw '
```

Every hit is a candidate XSS - verify the source is trusted (i18n, `link_to`/`form_with`/`tag` helper output) or flag it.

- [ ] **Engine matched** to changed files (Slim's `==` rule applies to `.slim` only; ERB's `<%==` to `.erb` only). When the diff mixes engines, apply each ruleset to its own files
- [ ] **No `.html_safe` on user input** in views, helpers, or model attributes feeding views; use `sanitize` with an explicit allowlist when HTML must render
- [ ] **Slim attribute-value Ruby evaluation**: bare values (`div class=user_input`) execute Ruby - quote literals (`div class="literal"`) so user-controlled methods can't reach attributes
- [ ] **`sanitize` always with explicit tags/attributes allowlist** - blank `sanitize(html)` permits enough to be exploitable
- [ ] **No HTML built via string interpolation + `.html_safe`** - use `link_to` / `tag.a` / `content_tag` so attributes are escaped
- [ ] **Turbo Stream / frame content** rendered via the same partials as initial render so escape rules can't diverge; `turbo_stream.append("id", html: user_input)` is XSS, use `partial:` form
- [ ] **Turbo Streams subscription authorization**: `turbo_stream_from "scope_#{record.id}"` is a WebSocket IDOR unless the channel's `subscribed` callback verifies access (or stream names are signed via `Turbo::StreamsChannel.signed_stream_name`)
- [ ] **Stimulus `data-action` values** are JS event names - no user-controlled values
- [ ] **Markdown / rich-text pipelines** (`Commonmarker`, `Redcarpet`, `Kramdown`): always pass rendered HTML through `sanitize` with an explicit allowlist before reaching the view. Renderer "safe mode" drifts (`raw_html: true`, `safe_links_only: false`) - the allowlist is the trust boundary

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


### Step 9 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
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
- [ ] **View-layer escaping audit** (Step 6.5) run against every changed `.erb` / `.haml` / `.slim` file - skipped only when the app is API-only; engine-specific unescape operators (`<%==`, `!=`, `==`) verified against trust boundaries; `rails-view-templates` consulted for engine rules
- [ ] File upload, path traversal, and shell-call checks run if applicable
- [ ] CSRF, CORS, Rack::Attack, open redirect, and admin-endpoint gating verified
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented); Combined-finding rule applied where two findings compose on the same action
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] If no findings: explicitly state "No issues found" per category - do not omit sections silently
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

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
