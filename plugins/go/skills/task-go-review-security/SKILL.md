---
name: task-go-review-security
description: Go / Gin security review - JWT middleware, ShouldBindJSON validation, SQL injection, mass assignment, secrets, govulncheck, OWASP Top 10.
agent: go-security-engineer
metadata:
  category: backend
  tags: [go, gin, gorm, security, jwt, owasp, govulncheck, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Security Review

Go-aware security review naming Gin JWT middleware (`gin-jwt`, `golang-jwt/jwt`), `ShouldBindJSON` + `go-playground/validator`, GORM / sqlx parameterization, password hashing (`bcrypt`, `argon2`), Go-specific risks (`exec.Command` injection, path traversal, mass assignment via `mapstructure.Decode`, `unsafe`), and Go dependency hygiene (`govulncheck`). Produces findings with attack scenarios and concrete Go remediations.

Stack-specific delegate of `task-code-review-security` for Go.

## When to Use

- Go/Gin PR security regression review
- Pre-deployment hardening on auth, authz, file upload, payment, PII code
- Periodic validation and middleware drift sweep
- Auditing a JWT flow, new auth middleware, or new `crypto` usage

**Not for:** perf review (`task-go-review-perf`), general review (`task-go-review`), production incident (`/task-oncall-start`).

**Depth.** This workflow always runs full - security has cliff-edge consequences. Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, auth bypass, mass data exfiltration, working SQL injection (`db.Exec(fmt.Sprintf(..., userInput))`), `exec.Command` with shell + user input, secrets / signing keys committed, JWT `alg: none` accepted. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata / internal services, mass assignment via `mapstructure.Decode(req.Body, &user)` granting admin, missing JWT on user-data endpoint, path traversal via `filepath.Join` without `Clean` + base check. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control elsewhere (missing CORS allowlist when proxy enforces origin), missing field-level validator tags, weak rate limit on non-critical endpoint, debug exposure on non-prod (`pprof` exposed). Should fix this PR or next.  |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited (`govulncheck` info), hardening without a concrete current attack.                                                                                                                                    |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file as a single finding at the elevated severity. Examples:

- Missing JWT (High) + mass assignment via `mapstructure.Decode(req.Body, &user)` (High) on the *same handler* = **Critical** unauthenticated admin override
- Missing ownership check (High) + ORM model in `c.JSON` exposing `PasswordHash` (Medium) on the *same handler* = **Critical** account takeover
- SSRF (High) + reachable from unauthenticated endpoint (High) = **Critical** unauth SSRF

If either finding is exploitable alone, file separately at independent severities.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-security` | Current branch vs base; fails fast on trunk |
| `/task-go-review-security <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-security pr-<N>` | PR head fetched into local branch (user runs fetch) |

When invoked as subagent (of `task-code-review-security` or `task-go-review`), parent passes handle + pre-read artifacts; Step 2 is skipped and Step 8 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Go, stop and recommend `/task-code-review-security`.

Detect: data access (GORM / sqlx / database/sql / mixed), JWT library (`golang-jwt/jwt` v4 vs v5, `gin-jwt`, `lestrrat-go/jwx`), password hashing (`bcrypt` vs `argon2`).

### Step 2 - Resolve Diff

Use skill: `review-precondition-check`. Read diff + log once; reuse. Skip if subagent received handle.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 3 - Read the Security Surface

Cite real lines. Open:

- `cmd/api/main.go` + router setup - middleware order (recovery -> logging -> request-id -> CORS -> auth -> rate-limit -> handler) and which groups have auth
- `internal/middleware/auth.go` - JWT validation, claim extraction, error responses
- `middleware/cors.go` / CORS setup for origin allowlist
- `middleware/ratelimit.go` for auth-endpoint rate limits
- Every changed handler - auth at group level, ownership checks, request DTO, `ShouldBindJSON` usage
- Every changed DTO with `validate:"..."` tags
- Every changed query for parameterization
- Config struct for `JWT_SECRET`, allowed origins, env loading
- `go.mod` / `go.sum` for dependency versions
- `.env.example` for documented env vars

When the diff removes middleware or relaxes auth, `git log -p` the prior revision - the blame trail is authoritative. A PR that takes a route out of the authed group, drops `iss`/`aud`/`exp` validation, or deletes alg-pinning is itself evidence of Insecure Design (A04) - call this out even when each individual removal looks "small" in isolation; the team's stated rationale ("we'll add it back later", "auth is annoying") is not a compensating control.

### Step 4 - OWASP Triage (Go Lens)

**Triage pass**, not findings list. Per-category verdict (`yes` / `no signal in diff`). Steps 5-9 produce findings.

| Risk | Go signal |
|------|-----------|
| Broken Access Control | Missing JWT at router-group level; missing ownership check |
| Injection | `db.Raw(fmt.Sprintf(...))`; `exec.Command("sh", "-c", userInput)`; unparameterized SQL via `+` |
| Cryptographic Failures | `md5` / `sha1` for auth; hardcoded JWT key; `math/rand` for tokens; missing `bcrypt` / `argon2` |
| Security Misconfiguration | `AllowAllOrigins: true`; `gin.DebugMode` in prod; ungated `pprof`; missing `gin-contrib/secure` |
| SSRF | `http.Get(userURL)` without allowlist; RFC1918 / metadata IP not rejected |
| XSS | `text/template` (not `html/template`); `c.HTML` with user-supplied template |
| Insecure Design (A04) | Default-allow router (auth opt-in instead of opt-out) |
| Vulnerable Components (A06) | Stale package with known CVE; missing `govulncheck` in CI |
| Data Integrity (A08) | `gob.Decode` on untrusted input; `mapstructure.Decode(req.Body, &model)`; missing request-size limit; `unsafe` |
| Logging & Monitoring (A09) | `slog` logging `password` / `token` / `authorization`; missing auth event log; Sentry not stripping PII |

### Step 5 - Apply the Pattern Bank

Use skill: `go-security-patterns` for the canonical AuthN, AuthZ, validation, injection, crypto, secrets, and SSRF patterns. The skill owns the recipes; this workflow owns the diff-level triage below.

**AuthN diff triage:**

- [ ] JWT algorithm pinned in `keyFunc`; `iss` / `aud` / `exp` validated; v5 of `golang-jwt/jwt`
- [ ] Access token lifetime short; refresh rotation; revocation surface (`jti` denylist or refresh UUID)
- [ ] Password hashing via `bcrypt` cost >= 10 or `argon2.IDKey`
- [ ] Gin middleware returns 401 with no body details; brute-force rate limit on `/auth/login`, `/auth/refresh`, `/auth/reset-password`
- [ ] No `slog` / `fmt.Println` leaking JWT, password, or session cookie value
- [ ] Cookie sessions (if used): `Secure`, `HttpOnly`, `SameSite`

**AuthZ diff triage:**

- [ ] Every new endpoint sits under an authed group OR is explicitly public-listed (default-deny)
- [ ] Role / permission checks centralized in middleware, not scattered inline
- [ ] Per-owner lookups scope by principal at the repository (`WHERE id = ? AND owner_id = ?`)
- [ ] Multi-tenant queries scoped by `tenant_id` at the repository (GORM scope), not the handler
- [ ] CORS allowlist explicit; no `AllowAllOrigins: true` for credentialed requests
- [ ] CSRF protection present iff auth model is cookie-session

**Input validation / mass assignment diff triage:**

- [ ] `ShouldBindJSON` (not `BindJSON`)
- [ ] Validator tags on every DTO field; no `interface{}` / `map[string]any` body
- [ ] No privilege-bearing fields (`Role`, `IsAdmin`, `OwnerID`, `UserID`, `TenantID`, `IsActive`, `Verified`) in input DTOs
- [ ] No `mapstructure.Decode(req.Body, &domain)` or `json.Unmarshal(body, &domain)` into domain models
- [ ] Response DTO (not raw model) returned; `c.JSON(200, *model.User)` is `High` regardless of current fields
- [ ] `c.ShouldBindUri` / `c.ShouldBindQuery` for path / query params; `uuid.Parse` for UUID path params
- [ ] File uploads: content-type detected via bytes (not header), size capped, stored outside webroot, filename sanitized
- [ ] Path traversal guarded (`filepath.Clean` + base-prefix check)
- [ ] `exec.Command(name, args...)` with arg slice; no `sh -c` / `cmd /c` with user input

### Step 6 - Go-specific Vulnerability Patterns

Pattern bank in `go-security-patterns`. Diff-level checks:

- [ ] No `fmt.Sprintf` interpolation into SQL; GORM `?` or sqlx `$1` / `:name` only
- [ ] No `text/template` with user-supplied template (SSTI); templates from disk or trusted constant
- [ ] No `gob.Decode` / `xml.Unmarshal` on untrusted input
- [ ] `unsafe` blocks audited and justified
- [ ] No `reflect.Set...` with user-controlled field name
- [ ] No `InsecureSkipVerify: true` outside a test fixture
- [ ] Open redirect: `c.Redirect(..., userInput)` validated against allowlist or relative-path-only
- [ ] `crypto/rand` (not `math/rand`) for tokens, nonces, secrets
- [ ] `crypto/subtle.ConstantTimeCompare` / `hmac.Equal` for HMAC / signature - not `==` / `bytes.Equal`
- [ ] `gin.SetMode(gin.ReleaseMode)` in prod; `pprof` not exposed (or behind admin auth)
- [ ] SSRF: user-controlled outbound URL resolves and rejects metadata / loopback / RFC1918 / link-local
- [ ] Webhook: raw body via `c.GetRawData()` before binding; signature via `hmac.Equal`; route outside JWT auth group
- [ ] Asynq / Kafka payload trust: validate inside the handler when queue is reachable from untrusted inputs
- [ ] `govulncheck ./...` clean in CI

### Step 7 - Data Protection

- [ ] PII / sensitive encrypted at rest (AES-GCM, KMS, or DB column encryption)
- [ ] No ORM model returned from handlers (audit columns leak silently when added later)
- [ ] `slog` redaction: never log `password`, `token`, `credit_card`, `ssn`, `api_key`; use `LogValuer` on secret-holding types
- [ ] No sensitive data in URLs (logs / browser history / referer)
- [ ] TLS enforcement at LB; HSTS via `gin-contrib/secure`
- [ ] DB backups encrypted; access controlled
- [ ] Secrets via typed config struct loaded once at startup; no scattered `os.Getenv`; `.env` gitignored

### Step 8 - Write Report

Standalone only - subagent runs return findings in the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-security` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha`/`head_sha` from Step 2, `stack: go-gin`, `scope: +sec`, `depth: deep` (this workflow always runs full depth), and `mode: full`, `round: 1` - unless `review-security-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Rules

- Validate at system boundaries (Gin body / query / params / URI, Asynq payloads, Kafka values, external API responses, webhook payloads)
- Never disable middleware to silence a failing test - fix the test
- Never widen authorization (move endpoint out of authed group, remove JWT) without explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Default-deny via authed router group with explicit public whitelist

## Self-Check

**Verifiable from diff (must check):**

- [ ] Stack confirmed; data-access mix, JWT library, password hash recorded before any specific check
- [ ] `review-precondition-check` ran (or handle received); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log read once and reused
- [ ] When `head_matches_current` was false: user approval obtained (skipped when subagent)
- [ ] Security surface (router / middleware, auth, settings, changed handlers / DTOs) read directly; prior revision consulted when middleware removed
- [ ] OWASP triage produced one verdict per category; not duplicated as standalone findings
- [ ] **Authorization drift sweep:** every new endpoint has JWT OR is explicitly public-listed
- [ ] DTO validation reviewed; mass-assignment fields, validator tags, separate request vs response DTOs confirmed
- [ ] File upload, path traversal, process exec checked when diff touches them
- [ ] SQL parameterization, command injection, `text/template`, `gob.Decode`, `unsafe`, `reflect.FieldByName`, `InsecureSkipVerify`, open redirect checked when diff touches them
- [ ] Severity rubric applied consistently
- [ ] Every finding includes an attack scenario, "regression risk" rationale, or "topology-dependent" framing
- [ ] Next Steps tagged `[Implement]` or `[Delegate]`; ordered Must > Recommend (omitted only when no issues)

**Requires repo / infra access:**

- [ ] Auth library config reviewed when in scope
- [ ] CORS, rate limiting, secure middleware, debug exposure verified when in scope
- [ ] Password hashing config (bcrypt cost >= 10, argon2 preferred) when in diff
- [ ] Sentry `BeforeSend` strips PII when in diff
- [ ] `govulncheck ./...` clean - run separately
- [ ] Report written via `review-report-writer` with all required checkpoint fields (standalone only; subagent runs return findings to the parent); confirmation printed

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Go Security Review Summary

**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**JWT Library:** golang-jwt/jwt/v5 | golang-jwt/jwt/v4 | gin-jwt | lestrrat-go/jwx | none
**Password Hash:** bcrypt | argon2 | none
**Authorization:** router-group middleware + ownership checks | inline checks | none
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment naming Go-specific risks: missing JWT, `mapstructure.Decode`, raw SQL via `fmt.Sprintf`, exposed `pprof`, `InsecureSkipVerify`.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | ...                     |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| XSS                       | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability in Go terms - e.g., "OrderHandler.Update accepts `req.Body` via `mapstructure.Decode(req.Body, &order)`; client can submit `{ \"user_id\": 999 }` and override server-assigned owner because no separate request DTO"]
- **Attack scenario:** [pick one and label: (a) concrete exploit; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether reverse proxy strips X-Forwarded-Proto correctly". Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [specific Go remediation with code]

### High / Medium / Low

[Same structure]

_Omit severity sections with no findings. If all omitted: "No security issues found."_

## Recommendations

[Prioritized hardening not tied to a finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.
Severity maps to intent: Critical / High -> [Must]; Medium / Low -> [Recommend].

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

_Omit if no issues found._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-security-<branch>.md`
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment")
- Skipping OWASP categories - state "No issues found" per category
- Generic advice when Go idiom applies ("apply auth at router-group level via `v1.Group(\"/orders\", auth.Required())`", not "add authorization check")
- `gin.DebugMode` left as default in prod
- `fmt.Sprintf` interpolation into SQL
- `InsecureSkipVerify: true` outside test fixtures
- `math/rand` for tokens / nonces / secrets
- `bytes.Equal` / `==` for HMAC / signature comparison
- `BindJSON` over `ShouldBindJSON`
- `mapstructure.Decode(req.Body, &domainModel)`
- Disabling middleware to silence a failing test
- Conflating security with general or perf review
- Exposed `pprof` in prod
- `gob.Decode` on untrusted input
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
