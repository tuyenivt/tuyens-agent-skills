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

When invoked as subagent of `task-code-review-security`, parent passes handle + pre-read artifacts; Step 2 skipped.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Go, stop and recommend `/task-code-review-security`.

Detect: data access (GORM / sqlx / database/sql / mixed), JWT library (`golang-jwt/jwt` v4 vs v5, `gin-jwt`, `lestrrat-go/jwx`), password hashing (`bcrypt` vs `argon2`).

### Step 2 - Resolve Diff

Use skill: `review-precondition-check`. Read diff + log once; reuse. Skip if subagent received handle.

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

When the diff removes middleware or relaxes auth, `git log -p` the prior revision - the blame trail is authoritative.

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

### Step 5 - Authentication

- [ ] **JWT signing:** HS256 secret in env / Vault, never committed. RS256 / ES256 preferred for cross-service. `golang-jwt/jwt/v5` (v4 is maintenance only); `lestrrat-go/jwx` strict-by-default alternative
- [ ] **`alg: none` rejected:** `jwt.Parse(token, keyFunc)` returns expected key only when `token.Method` matches expected algorithm (`*jwt.SigningMethodHMAC` for HS256). Never trust `alg` header blindly
- [ ] **`iss` / `aud` / `exp` validated**, not just signature - via `jwt.WithIssuer(...)`, `jwt.WithAudience(...)` (v5)
- [ ] **Access token lifetime** short (5-15 min); refresh token rotation; revocable via DB / Redis denylist (`jti` claim or refresh UUID)
- [ ] **Password hashing:** `bcrypt.GenerateFromPassword(pw, 12)` (cost >= 10) or `argon2.IDKey(...)` (preferred for new code). Never `sha256.Sum256` / `md5.Sum` for passwords. `crypto/subtle.ConstantTimeCompare` for hash comparison
- [ ] **Gin JWT middleware wired correctly:** extracts from `Authorization: Bearer <token>`, validates, sets claims on `c.Set("claims", ...)`, returns 401 with no body details
- [ ] **Brute-force protection:** rate limiter on `/auth/login`, `/auth/refresh`, `/auth/reset-password`; stricter than global
- [ ] **No `slog.Info("token", token)` / `fmt.Println(token)`** leaking the JWT
- [ ] **Session cookies** (when not bearer): `Secure: true` in prod, `HttpOnly: true`, `SameSite: http.SameSiteLaxMode`; signed via `securecookie` or HMAC

### Step 6 - Authorization

- [ ] **Authorization drift sweep:** every new endpoint has JWT middleware at the router group OR explicitly public (whitelisted in a `public` group). No bare `r.GET("/orders", handler)` outside an authed group
- [ ] **Role / permission checks centralized in middleware** (`auth.RequireRole("admin")`) reading claims from `c.Get("claims")`, not inline `if claims.Role != "admin" { ... }` scattered in handlers
- [ ] **IDOR:** lookups scope through principal (`db.Where("id = ? AND user_id = ?", orderID, claims.UserID).First(&order)`), not `db.First(&order, orderID)` + separate check. Best: repository signature takes `userID` / `tenantID`
- [ ] **Tenant isolation** scoped by `tenant_id` at the repository layer (GORM scope or sqlx wrapper), not at the handler. `db.Scopes(TenantScoped(claims.TenantID)).Find(...)` preferred
- [ ] **CORS:** `cors.New(cors.Config{AllowOrigins: [...]})` allowlist; not `AllowAllOrigins: true` for credentialed; minimal methods / headers
- [ ] **CSRF:** not required for stateless JWT-bearer APIs; required for cookie-session - confirm via auth model. `gorilla/csrf` for cookie-session

### Step 7 - Input Validation and Mass Assignment

- [ ] **`ShouldBindJSON` (not `BindJSON`)** so the handler controls the response shape
- [ ] **Validator struct tags on every DTO field:** `validate:"required,email,min=1,max=255"`. Missing tags means anything-goes input
- [ ] **No `interface{}` / `map[string]interface{}` body** - bind to a typed struct
- [ ] **No privilege-bearing fields in input DTOs:** `Role`, `IsAdmin`, `OwnerID`, `UserID`, `TenantID`, `IsActive`, `Verified` are server-set only. If present in `CreateOrderRequest`, reject and require admin-only path with separate DTO
- [ ] **No `mapstructure.Decode(req.Body, &user)` / `json.Unmarshal(body, &user)` directly into a domain model** - mass assignment. Define a request DTO, validate, then explicit field copy
- [ ] **Response DTOs (not models) returned:** `ToOrderResponse(o)` maps explicitly, dropping internal fields
- [ ] **`c.ShouldBindUri` / `c.ShouldBindQuery`** for path / query params - validates and converts. Raw `c.Param("id")` is a string with no validation
- [ ] **`uuid.Parse`** for UUID path params
- [ ] **File uploads:**
  - Type via content (`http.DetectContentType`), not header or extension
  - Per-file size limit (`router.MaxMultipartMemory`, `http.MaxBytesReader`)
  - Stored outside webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized (see path traversal)
  - Virus scan pipeline or accepted-risk documented
- [ ] **Path traversal:** `filepath.Clean(userInput)` + `filepath.Join(base, cleaned)` + `strings.HasPrefix(joined, base)` check; reject otherwise
- [ ] **Process execution:** `exec.Command(name, args...)` with arg slice (NOT `exec.Command("sh", "-c", userInput)`); strict allowlist of binaries

### Step 8 - Common Go Vulnerability Patterns

- [ ] **SQL injection via raw query:** `db.Exec(fmt.Sprintf("UPDATE ... WHERE id=%s", userInput))` - critical. Use GORM `db.Where("id = ?", id)`, sqlx `?` / `:name`. `db.Where("name LIKE ?", "%"+userInput+"%")` is fine (`?` is parameterized) - the smell is unparameterized interpolation
- [ ] **Command injection:** concatenating user input into a shell-interpreted string is RCE; use arg slice, no shell
- [ ] **`bash -c` / `sh -c` / `cmd /c`** with user input - same RCE
- [ ] **`text/template` with user-supplied template:** `template.New("").Parse(userInput).Execute(...)` is SSTI; templates from disk or trusted constant only
- [ ] **`gob.Decode(userInput)` / `xml.Unmarshal` on untrusted input:** `gob` instantiates types (deserialization gadget); `xml.Unmarshal` has billion-laughs / XXE risks
- [ ] **`unsafe` package** - audit for memory-safety violations; most are smells
- [ ] **`reflect.Set...` with user-controlled field name / value** - programmable mass assignment
- [ ] **`InsecureSkipVerify: true`** flagged unless behind documented test fixture
- [ ] **Open redirect:** `c.Redirect(http.StatusFound, userInput)` validated against allowlist or relative-path-only (`strings.HasPrefix(target, "/") && !strings.HasPrefix(target, "//")`)
- [ ] **`crypto/rand` (NOT `math/rand`) for tokens / nonces / secrets** - `math/rand` is deterministic
- [ ] **`crypto/subtle.ConstantTimeCompare` for HMAC / signature** - `==` / `bytes.Equal` are timing-attack vulnerable. Stripe / GitHub / Slack webhook verification must use constant-time
- [ ] **`JWT_SECRET` / signing key** in env / Vault, never committed; rotated when leaked
- [ ] **Debug exposure:** `gin.SetMode(gin.ReleaseMode)` in prod (default `DebugMode` leaks request bodies); `pprof` registered only in non-prod or behind admin auth
- [ ] **SSRF depth:** when user-controlled value flows into an outbound URL/host, allowlist must reject (a) cloud metadata `169.254.169.254` + IPv6, (b) localhost / `127.0.0.0/8` / `::1`, (c) RFC1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve host **after** parsing (DNS rebinding defeats string-only checks). `url.Parse` quirks: backslash, IPv4-in-IPv6 (`::ffff:127.0.0.1`) defeat naive checks
- [ ] **Asynq / Kafka payload trust:** if the queue is reachable from untrusted inputs (webhook -> Asynq), validate inside the handler before acting
- [ ] **HTTP request smuggling/desync** (Go behind nginx/ALB): flag custom HTTP/1.1 parsing or proxy middleware re-emitting headers without validation
- [ ] **Webhook signature verification** via `crypto/subtle.ConstantTimeCompare` (not `bytes.Equal`, not `==`). Read raw body via `c.GetRawData()` before binding
- [ ] **`govulncheck ./...`** in CI; flag unaddressed High/Critical

### Step 9 - Data Protection

- [ ] **PII / sensitive encrypted at rest** (AES-GCM, AWS/GCP KMS, or DB column encryption)
- [ ] **No ORM model returned from handlers:** `c.JSON(200, user)` leaks every column GORM defines (`PasswordHash`, `RecoveryToken`, `MFASecret`, soft-delete columns, audit fields). Handlers map to response DTO naming exactly the public fields. Both Step 7 (mass-assignment in) and Step 9 (data leak out) concern - check both directions
- [ ] **`slog` redaction:** never log `password`, `token`, `credit_card`, `ssn`, `api_key`. Handler wrapper drops keys, OR `LogValuer` on secret-holding types
- [ ] **No sensitive data in URLs** (use POST body, headers, signed tokens) - URLs hit logs / browser history / referer
- [ ] **TLS enforcement** at LB; HSTS via `gin-contrib/secure`
- [ ] **DB backups** encrypted; access controlled
- [ ] **Secrets** from a secret store (Vault / AWS Secrets Manager / GCP Secret Manager / Doppler), never committed `.env`. `.env` gitignored. `os.Getenv("JWT_SECRET")` via typed config struct loaded once so missing fails fast

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write before ending; print confirmation.

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
- [ ] Next Steps tagged `[Implement]` or `[Delegate]`; ordered Critical > High > Medium > Low (omitted only when no issues)

**Requires repo / infra access:**

- [ ] Auth library config reviewed when in scope
- [ ] CORS, rate limiting, secure middleware, debug exposure verified when in scope
- [ ] Password hashing config (bcrypt cost >= 10, argon2 preferred) when in diff
- [ ] Sentry `BeforeSend` strips PII when in diff
- [ ] `govulncheck ./...` clean - run separately
- [ ] Report written via `review-report-writer`; confirmation printed

## Output Format

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

Each tagged `[Implement]` or `[Delegate]`. Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]

_Omit if no issues found._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
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
