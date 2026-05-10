---
name: task-go-review-security
description: Go / Gin security review: JWT middleware, ShouldBindJSON validation, GORM SQL injection, mass assignment, secrets, govulncheck, OWASP Top 10.
agent: go-security-engineer
metadata:
  category: backend
  tags: [go, gin, gorm, security, jwt, owasp, govulncheck, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Go Security Review

## Purpose

Go-aware security review that names Gin JWT middleware (`gin-jwt`, `golang-jwt/jwt`), `ShouldBindJSON` + `go-playground/validator` tags, GORM / sqlx parameterization, password hashing (`bcrypt`, `argon2`), Go-specific risks (`exec.Command` injection, path traversal via `filepath.Join`, mass assignment via `mapstructure.Decode(req.Body, target)`, `unsafe` usage), and Go dependency hygiene (`govulncheck`) directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Go-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Go. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Go/Gin PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and middleware drift sweep across endpoints
- Auditing a JWT flow, a new Gin auth middleware, or new `crypto` usage

**Not for:**

- Performance review (use `task-code-review-perf` or `task-go-review-perf`)
- General code review (use `task-code-review` or `task-go-review`)
- Production incident triage (use `/task-oncall-start`)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path (`db.Exec(fmt.Sprintf(..., userInput))`), `exec.Command` with shell + user input, secrets / signing keys committed in source, JWT `alg: none` accepted. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata or internal services, mass assignment via `mapstructure.Decode(req.Body, &user)` granting admin, missing JWT middleware on user-data endpoint, path traversal via `filepath.Join` without `filepath.Clean` + base check. Must fix before merge. |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS allowlist when a reverse proxy enforces origin), missing field-level validator tags, weak rate limiting on a non-critical endpoint, debug exposure on a non-prod profile (`pprof` exposed). Should fix this PR or the next one.  |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold (`govulncheck` info-level), hardening recommendations without a concrete current attack scenario.                                                                            |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file them as a single finding at the elevated severity and cite each component. Examples:

- Missing JWT middleware on a user-data endpoint (High, alone) + mass assignment via `mapstructure.Decode(req.Body, &user)` (High, alone) on the *same handler* = **Critical** unauthenticated admin override (anyone on the internet can `POST /admin/users/:id` with `{"role": "admin"}`).
- Missing ownership check (High, alone) + ORM model returned from `c.JSON` exposing `PasswordHash` (medium, alone) on the *same handler* = **Critical** account takeover (any authenticated user reads any other user's password hash).
- SSRF (High, alone) + reachable from an unauthenticated endpoint (High, alone) = **Critical** unauth SSRF.

The rule of thumb: if the realistic exploit path requires both findings to land for the attack to succeed, they are one finding. If either finding is exploitable on its own, file them separately at their independent severities.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                          | Meaning                                                                                               |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-go-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-go-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-go-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Go / Gin. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-go-review` (parent already detected Go), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Go, stop and tell the user to invoke `/task-code-review-security` instead.

Detect data access (GORM / sqlx / database/sql / mixed) and JWT library (`golang-jwt/jwt` v4 vs v5, `gin-jwt`, `lestrrat-go/jwx`) and password hashing (`golang.org/x/crypto/bcrypt` vs `argon2`). Record `Data Access`, `JWT Library`, `Password Hash` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

- `cmd/api/main.go` and the router setup file - confirm middleware order (recovery → logging → request-id → CORS → auth → rate-limit → handler) and which router groups apply auth
- `internal/middleware/auth.go` (or equivalent) - JWT validation logic, claim extraction, error responses
- `internal/middleware/cors.go` / CORS setup (typically `gin-contrib/cors`) for origin allowlist
- `internal/middleware/ratelimit.go` (typically `gin-contrib/limiter` or `golang.org/x/time/rate`) for auth-endpoint rate limits
- Every changed handler - look for auth middleware applied at group level, ownership checks in handler/service body, request DTO type, `c.ShouldBindJSON` usage
- Every changed DTO with `validate:"..."` struct tags
- Every changed query for parameterization (GORM `Where("id = ?", id)`, sqlx `?` placeholders or `:name` named params)
- `cmd/api/main.go` / config struct for `JWT_SECRET`, allowed origins, env var loading
- `go.mod` / `go.sum` for dependency versions; recent CVE-affected packages
- `.env.example` for documented env vars (without real values)

When the diff removes a middleware or relaxes auth, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 4 - OWASP Triage (Go Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `Injection: yes`, `SSRF: yes`, `Insecure Design: no`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

The triage output funnels which downstream steps must run carefully versus which can be fast-passed. If a category shows no signal, explicitly state `No signal in diff` for that category in the Summary.

| Risk                          | Go-specific check                                                                                                                                                                                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every protected route has JWT middleware applied at the router-group level (`v1.Group("/orders", auth.Required())`); ownership check in the service / handler body for per-owner data. Empty / missing is a finding.                                       |
| Injection                     | GORM uses `?` placeholders or named arguments by default; `db.Raw("SELECT ... WHERE id = ?", id)` is parameterized; `db.Raw(fmt.Sprintf("SELECT ... %s", input))` is **not**. sqlx `db.Select(&out, "WHERE id = ?", id)` parameterized; `db.NamedExec` named params. `exec.Command(name, args...)` with arg slice is fine; `exec.Command("sh", "-c", userInput)` is RCE. |
| Cryptographic Failures        | `bcrypt.GenerateFromPassword(pw, bcrypt.DefaultCost)` (cost ≥ 10) or `argon2.IDKey(...)` for passwords. Never `md5.New()` / `sha1.New()` for auth (only for non-security checksums). JWT signing key from env / Vault, not hardcoded. `crypto/rand` (not `math/rand`) for tokens / nonces. |
| Security Misconfiguration     | `gin-contrib/secure` middleware applied (HSTS, frame-options, content-type-options); CORS origin allowlist (not `AllowAllOrigins: true` in prod); `gin.SetMode(gin.ReleaseMode)` in prod; `pprof` endpoint gated or absent in prod.                        |
| SSRF                          | `http.Get(userControlledURL)` / `http.Client.Do` with user-controlled URL validates hostname against allowlist; rejects RFC1918, link-local, cloud metadata before request.                                                                                |
| XSS                           | Gin auto-escapes JSON responses; if rendering HTML templates (`html/template`, not `text/template`), auto-escapes. `c.HTML(text/template.New(...))` is XSS-prone - flag.                                                                                  |
| Insecure Design (A04)         | Default-deny: top-level router group requiring auth unless explicitly public; explicit public routes whitelisted, not opt-out.                                                                                                                             |
| Vulnerable Components (A06)   | `govulncheck ./...` clean for affected; Renovate / Dependabot active. No pinned-but-stale package with known CVE in `go.sum`.                                                                                                                              |
| Data Integrity Failures (A08) | `json.Unmarshal` on untrusted input bounded by request size limit (`router.MaxMultipartMemory`, `gin-contrib/size`); `gob.Decode` flagged on untrusted input - it instantiates types, classic Go gadget surface; `unsafe` usage flagged. Mass assignment: `mapstructure.Decode(req.Body, &user)` flagged. |
| Logging & Monitoring (A09)    | `slog` does not log `password`, `token`, `authorization`, `cookie`. Auth events logged. Sentry `BeforeSend` strips PII (when wired).                                                                                                                       |

### Step 5 - Authentication

- [ ] **JWT signing**: HS256 secret in env / Vault, never committed. RS256 / ES256 with key pair preferred for cross-service. `golang-jwt/jwt/v5` (v4 is on maintenance only); `lestrrat-go/jwx` is the strict-by-default alternative
- [ ] **`alg: none` rejected**: `jwt.Parse(token, keyFunc)` keyFunc returns the expected key only when `token.Method` matches the expected algorithm (`*jwt.SigningMethodHMAC` for HS256). Never trust the `alg` header value blindly - check `token.Method.(*jwt.SigningMethodHMAC)` and reject otherwise
- [ ] **JWT issuer / audience validated**: `jwt.WithIssuer(...)`, `jwt.WithAudience(...)` validators (jwt/v5) wired; `iss`, `aud`, `exp` checked, not just signature
- [ ] **Access token lifetime** short (5-15 min); refresh token rotation; refresh tokens revocable via DB / Redis denylist (track `jti` claim or refresh-token UUID)
- [ ] **Password hashing**: `bcrypt.GenerateFromPassword(pw, 12)` (cost ≥ 10) or `argon2.IDKey(...)` (preferred for new code). Never `crypto/sha256.Sum256` / `md5.Sum` for passwords. `crypto/subtle.ConstantTimeCompare` for hash comparison
- [ ] **Gin JWT middleware wired correctly**: middleware extracts token from `Authorization: Bearer <token>`, validates, sets claims on `c.Set("claims", ...)`, returns 401 with no body details on failure
- [ ] **Brute-force protection**: rate limiter on `/auth/login`, `/auth/refresh`, `/auth/reset-password` via `gin-contrib/limiter` or `golang.org/x/time/rate`; configured stricter than global rate limit
- [ ] **No `slog.Info("token", token)` / `fmt.Println(token)`** that leaks the JWT to logs
- [ ] **Session cookies (when used instead of bearer JWT)**: `Secure: true` in prod, `HttpOnly: true`, `SameSite: http.SameSiteLaxMode`; signed via `securecookie` or HMAC tag

### Step 6 - Authorization

- [ ] **Authorization drift sweep**: every new endpoint added in the diff has JWT middleware applied at the router group OR explicitly public (whitelisted in a `public` group). No bare `r.GET("/orders", handler)` outside an authed group
- [ ] **Role / permission checks** centralized in middleware (`auth.RequireRole("admin")`) using claims read from `c.Get("claims")`, not inline `if claims.Role != "admin" { c.AbortWithStatus(403); return }` scattered in handlers (easy to miss on new endpoints)
- [ ] **IDOR**: lookups scope through the principal (`db.Where("id = ? AND user_id = ?", orderID, claims.UserID).First(&order)`) rather than `db.First(&order, orderID)` then a separate ownership check. Better: every domain query takes `userID` / `tenantID` in its repository signature
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenant_id` at the repository layer (GORM scope or sqlx wrapper injecting the WHERE clause), not at the handler layer alone. `db.Scopes(TenantScoped(claims.TenantID)).Find(...)` pattern preferred
- [ ] **CORS**: `cors.New(cors.Config{AllowOrigins: [...]})` allowlist (not `AllowAllOrigins: true` for credentialed requests); methods and headers minimal
- [ ] **CSRF**: not required for stateless JWT-bearer APIs; required for cookie-session apps - confirm via auth model. `gorilla/csrf` middleware for cookie-session

### Step 7 - Input Validation and Mass Assignment

- [ ] **`ShouldBindJSON` (not `BindJSON`)** for control over the response shape: `BindJSON` writes 400 directly and returns; `ShouldBindJSON` returns the error. Use `ShouldBindJSON` so the handler can wrap, log, and respond consistently via the error middleware
- [ ] **Validator struct tags on every DTO field**: `validate:"required,email,min=1,max=255"` via `go-playground/validator` (Gin's default). Missing tags means anything-goes input
- [ ] **No `interface{}` / `map[string]interface{}` body**: `c.ShouldBindJSON(&req)` with a typed struct - never `c.ShouldBindJSON(&map[string]interface{}{})` then read fields by string key
- [ ] **No privilege-bearing fields in user-facing input DTOs**: `Role`, `IsAdmin`, `OwnerID`, `UserID`, `TenantID`, `IsActive`, `Verified` - server-set only. If present in `CreateOrderRequest`, reject and require an admin-only path with a separate DTO
- [ ] **No `mapstructure.Decode(req.Body, &user)` / `json.Unmarshal(body, &user)` directly into a domain model**: this is mass-assignment. Define a request DTO, validate it, then map to the domain model with explicit field assignment
- [ ] **Response DTOs (not models) returned from handlers**: `ToOrderResponse(o *model.Order) OrderResponse` maps explicitly, dropping internal fields (`PasswordHash`, `InternalAuditLog`, `IsTest`)
- [ ] **`c.ShouldBindUri` / `c.ShouldBindQuery`** for path params and query strings - validates and converts in one call; raw `c.Param("id")` returns a string with no validation
- [ ] **`uuid.Parse` (or equivalent) for UUID path params**: never trust the raw string format
- [ ] **File uploads**:
  - File type validated by content (`http.DetectContentType`), not just `Content-Type` header (client-controlled) or extension
  - Per-file size limit enforced (`router.MaxMultipartMemory = 5 << 20` for 5MB; `c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxBytes)` for stricter)
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized per the path-traversal rule below (the same `filepath.Clean` + `HasPrefix(base)` check applies)
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `filepath.Clean(userInput)` followed by `filepath.Join(base, cleaned)` and `strings.HasPrefix(joined, base)` check; reject otherwise
- [ ] **Process execution**: `exec.Command(name, args...)` with arg slice (NOT `exec.Command("sh", "-c", userInput)` and NOT a name interpolated from user input); strict allowlist of allowed binaries

### Step 8 - Common Go Vulnerability Patterns

- [ ] **SQL injection via raw query**: `db.Exec(fmt.Sprintf("UPDATE ... WHERE id=%s", userInput))` - flagged as critical; same for `db.Raw(fmt.Sprintf(...))`. Use GORM `db.Where("id = ?", id)`, `db.Raw("SELECT ... WHERE id = ?", id)`, sqlx `?` / `:name`. Even `db.Where("name LIKE ?", "%"+userInput+"%")` is fine (the `?` is parameterized) - the smell is unparameterized interpolation
- [ ] **Command injection**: `exec.Command("sh", "-c", "convert "+userInput+" /tmp/out")` - any concatenation of user input into a shell-interpreted string is RCE; use `exec.Command("convert", userInput, "/tmp/out")` (arg slice, no shell)
- [ ] **`os/exec` with `shell: true` equivalent**: invoking `bash -c` / `sh -c` / `cmd /c` with user input - same RCE
- [ ] **`text/template` with user-supplied template**: `template.New("").Parse(userInput).Execute(...)` is RCE / SSTI; templates must come from disk or a trusted constant. `html/template` is auto-escaping for HTML output, but `Parse(userInput)` is still SSTI
- [ ] **`gob.Decode(userInput)` / `xml.Unmarshal` on untrusted input**: `gob` instantiates types - classic deserialization-gadget surface; `xml.Unmarshal` has billion-laughs / XXE risks (use defaults; flag custom decoders)
- [ ] **`unsafe` package usage**: `unsafe.Pointer` casts in the diff - audit for memory-safety violations; legitimate uses exist (zero-copy string→[]byte) but most are smells
- [ ] **`reflect.Set...` with user-controlled field name / value**: a programmable mass-assignment. Flag any `reflect.ValueOf(target).FieldByName(userKey).Set(...)` pattern
- [ ] **HTTP client with `InsecureSkipVerify: true`**: `&tls.Config{InsecureSkipVerify: true}` flagged unless behind a documented test fixture; same for any direct `&http.Transport{TLSClientConfig: ...}` with InsecureSkipVerify
- [ ] **Open redirect**: `c.Redirect(http.StatusFound, userInput)` validated against an allowlist or relative-path-only check (`strings.HasPrefix(target, "/") && !strings.HasPrefix(target, "//")`)
- [ ] **`crypto/rand` (NOT `math/rand`) for tokens / nonces / secrets**: `math/rand` is deterministic; `crypto/rand.Read(buf)` for security-sensitive randomness. `math/rand/v2` (Go 1.22+) is still not cryptographic
- [ ] **`crypto/subtle.ConstantTimeCompare` for HMAC / signature comparison**: `==` on `[]byte` is timing-attack vulnerable. Stripe / GitHub / Slack webhook signature verification must use constant-time compare
- [ ] **`JWT_SECRET` / signing key** sourced from env / Vault, never committed; rotated when leaked
- [ ] **Debug exposure**: `gin.SetMode(gin.ReleaseMode)` in prod (default `DebugMode` leaks request bodies in logs); `pprof` endpoint registered only in non-prod or behind admin auth (typical pattern: `if env != "prod" { pprof.Register(r) }`)
- [ ] **SSRF depth**: when a user-controlled value flows into an outbound URL or hostname, the allowlist must reject (a) cloud metadata IP `169.254.169.254` and IPv6 equivalent, (b) localhost / `127.0.0.0/8` / `::1`, (c) private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve the host **after** parsing (DNS rebinding bypasses string-only allowlists - re-resolve at request time and re-check). `net/url.Parse` quirks: backslash, IPv4-in-IPv6 (`::ffff:127.0.0.1`) all defeat naive checks
- [ ] **Asynq / Kafka payload trust boundary**: tasks serialize to bytes in Redis / Kafka; consumer `json.Unmarshal(payload, &p)` on input from any source that can publish to the queue is implicit trust. If the queue is reachable from untrusted inputs (webhook → Asynq), validate inside the handler before acting on payload fields
- [ ] **HTTP request smuggling / desync** (Go behind nginx / ALB): Go's `net/http` parser is strict by default; flag custom HTTP/1.1 parsing or proxy / forwarder middleware that re-emits headers without validation
- [ ] **Webhook signature verification**: Stripe / GitHub / Slack webhooks - signature verified via `crypto/subtle.ConstantTimeCompare` (not `bytes.Equal`, not `==`). Read raw body via `c.GetRawData()` before any binding (binding consumes the body)
- [ ] **`govulncheck ./...` integration**: project runs `govulncheck` in CI for known Go vulns; flag unaddressed High/Critical findings

### Step 9 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (`crypto/aes` + GCM, AWS KMS / GCP KMS for key management, or DB-native column encryption)
- [ ] **No ORM model returned from handler responses**: `c.JSON(200, user)` where `user` is `*model.User` leaks every column the GORM struct defines - `PasswordHash`, `RecoveryToken`, `MFASecret`, soft-delete columns, internal audit fields, and any sensitive column added later. Handlers map to a response DTO (`ToUserResponse(u)`) that names exactly the public fields. This is both a Step 7 concern (mass-assignment shape on the way in) and a Step 9 concern (data leak on the way out) - check both directions
- [ ] **`slog` redaction**: structured logger never logs `password`, `token`, `credit_card`, `ssn`, `api_key`. `slog.Handler` wrapper that drops sensitive keys, OR explicit `LogValuer` on types that hold secrets to override marshalling
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit logs, browser history, referer headers
- [ ] **TLS enforcement**: HTTPS-only at LB; HSTS via `gin-contrib/secure`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars from a secret store (Vault / AWS Secrets Manager / GCP Secret Manager / Doppler), never `.env` committed; `.env` gitignored; `os.Getenv("JWT_SECRET")` accessed via typed config struct loaded once at startup so missing-at-startup fails fast


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (Gin body / query / params / URI, Asynq task payloads, Kafka message values, external API responses, webhook payloads)
- Never disable middleware to silence a failing test - fix the test
- Never widen authorization (e.g., moving an endpoint out of an authed router group, removing JWT middleware from a route) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny via authed router group with explicit public whitelist

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as Go / Gin; data-access mix, JWT library, password hash library recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (router setup / middleware order, auth middleware, settings, changed routers / handlers, DTOs) read directly before applying checklists; prior revision consulted when middleware was removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new endpoint in the diff has matching JWT middleware OR is explicitly public-listed
- [ ] DTO validation reviewed; mass-assignment fields, validator tags, separate request vs response DTOs confirmed for changed schemas
- [ ] File upload, path traversal, and process-execution checks run if the diff touches uploads / file paths / `os/exec`
- [ ] SQL parameterization, command injection, `text/template` with user input, `gob.Decode`, `unsafe`, `reflect.FieldByName`, `InsecureSkipVerify`, open redirect checked when the diff touches them
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for test-coverage gaps), or "topology-dependent" framing (for infra-flavored findings) - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Authentication step run for the auth mechanism in use (JWT via `golang-jwt` / `gin-jwt` / `lestrrat-go/jwx`) - applies when the auth module is in scope
- [ ] CORS, rate limiting, secure middleware, debug exposure verified - applies when middleware / config are in scope
- [ ] Password hashing config reviewed (bcrypt cost ≥ 10, argon2 preferred) - skip if hashing config not in diff
- [ ] Sentry `BeforeSend` strips PII - skip if Sentry init not in diff
- [ ] `govulncheck ./...` clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Go Security Review Summary

**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM <version> | sqlx <version> | database/sql | mixed
**JWT Library:** golang-jwt/jwt/v5 | golang-jwt/jwt/v4 | gin-jwt | lestrrat-go/jwx | none
**Password Hash:** bcrypt | argon2 | none
**Authorization:** router-group middleware + ownership checks | inline checks | none
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Go-specific risks like missing JWT middleware on a router group, mass assignment via `mapstructure.Decode`, raw SQL via `fmt.Sprintf`, exposed `pprof` in prod, or `InsecureSkipVerify: true` in HTTP client.]

## OWASP Triage

_The Step 4 verdicts. One row per category, `yes` (signal present, see Findings) or `no signal in diff`._

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | yes / no signal in diff |
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

- **Location:** [file:line, or comma-separated list for multi-site findings]
- **Issue:** [vulnerability described in Go terms - e.g., "OrderHandler.Update accepts `req.Body` directly into a domain model via `mapstructure.Decode(req.Body, &order)`; client can submit `{ \"user_id\": 999 }` and override the server-assigned owner via mass assignment because there is no separate request DTO with explicit fields"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" - for test-coverage / monitoring gaps; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto correctly" - for infra-flavored findings. Pick one and label which. Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific Go remediation with code example - separate request DTO + explicit field copy, `db.Where("id = ? AND user_id = ?", id, claims.UserID)`, JWT middleware at group level, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `gin-contrib/limiter` rate limit on /auth/login", "Migrate from golang-jwt/jwt/v4 to v5 (stricter defaults)", "Move JWT_SECRET from .env literal to Vault", "Add `govulncheck` to CI"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `mapstructure.Decode(req.Body, &order)` with a typed `UpdateOrderRequest` DTO + explicit field copy in OrderHandler.Update"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `govulncheck ./...` and upgrade flagged packages - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment because handler binds directly into `User` model")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Go idiom applies (say "apply auth middleware at the router-group level via `v1.Group(\"/orders\", auth.Required())`", not "add an authorization check")
- Suggesting `gin.SetMode(gin.DebugMode)` left as default in prod - leaks request bodies in logs; flag if prod uses default
- Suggesting `fmt.Sprintf` interpolation into SQL as acceptable - parameterize via `?` / named args
- Suggesting `InsecureSkipVerify: true` outside test fixtures
- Suggesting `math/rand` for tokens / nonces / secrets - use `crypto/rand`
- Suggesting `bytes.Equal` / `==` for HMAC / signature comparison - use `crypto/subtle.ConstantTimeCompare`
- Suggesting `BindJSON` over `ShouldBindJSON` - `BindJSON` writes 400 directly and you lose control of the response
- Suggesting `mapstructure.Decode(req.Body, &domainModel)` as acceptable - mass-assignment vector
- Disabling middleware to silence a failing test - fix the test
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Approving exposed `pprof` in prod profile
- Approving `gob.Decode` on untrusted input
