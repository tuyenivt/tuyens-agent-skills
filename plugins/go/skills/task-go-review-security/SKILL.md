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

**Not for:** perf review (`task-go-review-perf`), general review (`task-go-review`).

**Depth.** This workflow always runs full - security has cliff-edge consequences. Scope by file, not by depth. A parent-supplied depth is recorded and ignored; the report always carries `depth: deep`.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, auth bypass, mass data exfiltration, working SQL injection (`db.Exec(fmt.Sprintf(..., userInput))`), `exec.Command` with shell + user input, secrets / signing keys committed, JWT `alg: none` accepted. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata / internal services, mass assignment via `mapstructure.Decode(req.Body, &user)` granting admin, missing JWT on user-data endpoint, path traversal via `filepath.Join` without `Clean` + base check. Also: **a control removed outright, or degraded until it no longer does its job**, with nothing replacing it - `iss`/`aud`/`exp` validation deleted, an algorithm pin removed, TLS verification disabled (`InsecureSkipVerify`), a work factor dropped to the library's floor, a brute-force limit widened by an order of magnitude on a credential endpoint. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control elsewhere (missing CORS allowlist when proxy enforces origin), missing field-level validator tags, debug exposure on non-prod (`pprof` exposed), **resource exhaustion** reachable without auth (uncapped request body, unbounded upload or fetch), and a **control narrowed but still doing its job** (a limit loosened within a defensible range, a cost lowered but still above the recommended floor). Should fix this PR or next.  |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited (`govulncheck` info), hardening without a concrete current attack.                                                                                                                                    |

**Money and entitlement integrity** rates by what the attacker controls: a value they can set that moves money or grants access is High, Critical when unauthenticated; a value they can only observe is Medium.

**Rate a weakened control by what it still stops, not by whether the line was deleted.** Removal and degradation-to-uselessness are the same defect; `InsecureSkipVerify: true` beside a populated `RootCAs` is a deletion written as an assignment. When another skill's rubric and this one disagree on a tier, take the higher and say which clause you applied.

**A control that is absent but currently inert is Medium with framing (b), not its rubric tier.** A checklist row can fail while the exploit it guards is blocked elsewhere - `mime/multipart` already applies `filepath.Base`, so an unguarded `filepath.Join` does not escape; `golang-jwt` rejects `alg: none` unless `keyFunc` returns `jwt.UnsafeAllowNoneSignatureType`, and rejects RS/ES against a `[]byte` key, so a missing algorithm pin forges nothing while the key stays symmetric. Name what is holding it back and what would remove that, instead of writing an exploit the code does not permit or dropping the finding. This carve-out does not apply when the blocker is itself in the diff, or is a value the team can change without review.

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file as a single finding at the elevated severity. Composition is judged on the resulting threat, not on independent exploitability - both halves of every example below are exploitable alone, and they still compose:

- Missing JWT (High) + mass assignment via `mapstructure.Decode(req.Body, &user)` (High) on the *same handler* = **Critical** unauthenticated admin override
- Missing ownership check (High) + ORM model in `c.JSON` exposing `PasswordHash` (High per the Step 5 triage row) on the *same handler* = **Critical** account takeover
- SSRF (High) + reachable from unauthenticated endpoint (High) = **Critical** unauth SSRF

When several bullets fire on one handler, file **one** finding at the elevated tier listing every constituent - not one per bullet. Split only when the findings sit on different code paths, or when no composition produces a threat worse than the stronger half alone (then each stands at its own severity).

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-security` | Current branch vs base; fails fast on trunk |
| `/task-go-review-security <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-security pr-<N>` | PR head fetched into local branch (user runs fetch) |

**Subagent runs** (of `task-code-review-security` or `task-go-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, the pre-confirmed stack, and the data-access mix. Step 2 is skipped whole, its SHA capture included - never re-run git. The verify pass before Step 8 is skipped (the parent verifies the merged set once). Step 8 returns **the entire Output Format below except the report file** - Summary, OWASP Triage, Findings, Recommendations, Next Steps - not the `## Findings` section alone; the parent's merge consumes all of it. Ignore the writer vocabulary in the Output Format preamble (`report_body` is a writer input that does not exist on this path).

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Go, stop and recommend `/task-code-review-security`.

Detect: data access (GORM / sqlx / database/sql / mixed), JWT library (`golang-jwt/jwt` v4 vs v5, `gin-jwt`, `lestrrat-go/jwx`), password hashing (`bcrypt` vs `argon2`).

### Step 2 - Resolve Diff

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check`. Read diff + log once; reuse. Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

If the clean-tree gate fails and **the only untracked file is this workflow's own prior report** (`review-security-<branch>.md`), the gate is tripping on the artifact the last run wrote; every round-2 review would be unreachable. Say so, treat the tree as clean, continue, and tell the user to gitignore the report path. Any other fail-fast: surface verbatim and stop.

In no-argument mode the handle's `head_ref` is the literal `HEAD`. Pass `branch: <current_branch>` to the writer so the report is named for the branch rather than colliding on `review-security-HEAD.md`; keep `head_ref: HEAD` in the checkpoint. The round itself is resolved in Step 8.

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
- **Static file serving** - `r.Static` / `r.StaticFS` / `http.FileServer` and the directory each serves. A directory that is both writable by an upload handler and served on the app's own origin turns any upload defect into same-origin script execution; Go's file server picks `Content-Type` from the extension, not from whatever the handler validated

When the diff **weakens the authorization posture** - removes middleware, registers a new route outside the authed group, drops `iss`/`aud`/`exp` validation, deletes alg-pinning, widens a limit, or lowers a work factor - `git log -p` the prior revision; the blame trail is authoritative. Any of these is evidence of Insecure Design (A04); call it out even when each change looks "small" in isolation. The team's stated rationale ("internal only, behind the VPC", "we'll add it back later", "QA kept getting locked out") is not a compensating control - a network boundary is not authentication, and a schedule is not a control. Record each removal, the rationale offered, and why it does not compensate, in the Summary paragraph.

### Step 4 - OWASP Triage (Go Lens)

**Triage pass**, not findings list. Steps 5-9 produce findings. One verdict per category, from this enum:

| Verdict | When |
| ------- | ---- |
| `yes` | The listed signal, or another instance of that category, is present anywhere in the surface Step 3 read - including unchanged files. The `Go signal` column is a starting list, not the category's definition: stored XSS via a served upload directory is `yes` on XSS even though the row names `text/template` |
| `no signal in diff` | Checked, nothing found |
| `not verifiable here` | Settling it needs something outside the tree - a CI config, a deployment manifest, a vulnerability database, a live `govulncheck` run. Name what is missing |

Never leave a category blank; three verdicts and a reason cover every case.

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
- [ ] Webhook: raw body via `c.GetRawData()` before binding; signature via `hmac.Equal`; route outside JWT auth group; body capped with `http.MaxBytesReader` **before** the read; **replay window enforced** - the signed timestamp is parsed and compared to the clock (reject beyond ~5 min), not merely folded into the MAC. Binding `t` into the signature stops an attacker editing it; only a clock comparison stops replaying the original `(t, sig, body)` triple, and a dedup table with no retention policy is a weaker substitute
- [ ] Asynq / Kafka payload trust: re-validate inside the handler whenever the queue is a second entry path to a value an HTTP-boundary control protected, or the broker is reachable by anything outside this service - not only when the payload's original source is untrusted. A signed webhook that enqueues an amount, which the worker then writes without re-checking, has moved the trust boundary to the broker
- [ ] `govulncheck ./...` clean in CI. It needs a toolchain and an advisory database; when either is unavailable, record `not verifiable here` in the triage and say so in the finding rather than implying a clean result

### Step 7 - Data Protection

- [ ] PII / sensitive encrypted at rest (AES-GCM, KMS, or DB column encryption)
- [ ] No ORM model returned from handlers (audit columns leak silently when added later)
- [ ] `slog` redaction: never log `password`, `token`, `credit_card`, `ssn`, `api_key`; use `LogValuer` on secret-holding types
- [ ] No sensitive data in URLs (logs / browser history / referer)
- [ ] TLS enforcement at LB; HSTS via `gin-contrib/secure`
- [ ] DB backups encrypted; access controlled
- [ ] Secrets via typed config struct loaded once at startup; no scattered `os.Getenv`; `.env` gitignored

### Step 7.5 - Verify Findings

Assign each draft finding its label first - Critical / High -> `[Must]`, Medium / Low -> `[Recommend]` - because `review-finding-verify` takes labelled findings as input and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - it de-escalates `[Must]` to `[Recommend]` on untouched pre-existing code, and that survives into the finding heading and into Next Steps. Never re-derive a label from the severity tier after this step; a `### Critical` finding tagged `[Recommend]` because it is pre-existing is the correct output, not a contradiction. Carry its provenance annotation (`_(pre-existing)_`, `_(pre-existing; newly reachable)_`, `_(unverified: <reason>)_`) onto the finding heading, and its tally into the Summary's `Findings verified` slot.

Subagent runs skip this step entirely - the parent verifies the merged set once - and return findings tagged by tier alone.

### Step 8 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

**Resolve the round before calling the writer.** Stat `review-security-<branch>.md` in the writer's output directory, applying `review-report-writer`'s branch-sanitizing rule to the name. Absent or frontmatter-less -> `round: 1`. Present and valid -> increment its `round` and pass its `head_sha` as `prior_head_sha`. The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.

**Same-SHA no-op.** When the prior report's `head_sha` equals the current head and the invocation adds nothing, print `No new commits on <branch> since prior security review at <sha_short>. Prior report unchanged.` and stop - do not re-review and do not overwrite the report. On a genuine round 2+, re-review the full range and note in the Summary which findings carry over; this lens has no reconciliation table, so the prior report stays the audit trail.

Use skill: `review-report-writer` with `report_type: review-security` and every required input: `report_body`, `branch` (the branch short name, never the literal `HEAD`), refs from the precondition handle, `base_sha`/`head_sha` from Step 2, `stack: go-gin`, `scope: +sec`, `depth: deep` (this workflow always runs full depth), `mode: full`, and the `round` / `prior_head_sha` resolved above. Write before ending; print confirmation.

## Rules

- Validate at system boundaries (Gin body / query / params / URI, Asynq payloads, Kafka values, external API responses, webhook payloads)
- Never disable middleware to silence a failing test - fix the test
- Never widen authorization (move endpoint out of authed group, remove JWT) without explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Default-deny via authed router group with explicit public whitelist

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface, or when the invocation mode makes it inapplicable (subagent, no-argument mode).

**Verifiable from diff (must check):**

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; data-access mix, JWT library, password hash recorded before any specific check
- [ ] Static file serving read; any directory both upload-writable and publicly served flagged
- [ ] `review-precondition-check` ran (or handle received); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log read once and reused
- [ ] When `head_matches_current` was false: user approval obtained (skipped when subagent)
- [ ] Security surface (router / middleware, auth, settings, changed handlers / DTOs) read directly; prior revision consulted when middleware removed
- [ ] OWASP triage produced one verdict per category from the three-value enum; not duplicated as standalone findings
- [ ] Step 7.5 ran (standalone): findings labelled before verify, verify's labels and provenance annotations carried onto the headings verbatim, tally in the Summary
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

**Fill rules.** `Overall Posture` counts every tier: `Issues Found - <N> Critical / <N> High / <N> Medium / <N> Low`. `Password Hash` takes `not observable` when only a verify call (`CompareHashAndPassword`) is in the tree and no hash is generated - the cost cannot be read from a comparison. `Findings verified` is omitted on subagent runs. Any field whose value the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Each finding is its own numbered block** under its severity heading, headed `#### <n>. [Label] file:line _(provenance)_` where the label and any `_(pre-existing)_` / `_(pre-existing; newly reachable)_` / `_(unverified: <reason>)_` annotation come from Step 7.5 verbatim. Numbering continues across tiers so Recommendations and Next Steps can cite `finding <n>`. Blank lines separate the field lines; consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

```markdown
## Go Security Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - <both, named>
- **JWT Library:** golang-jwt/jwt/v5 | golang-jwt/jwt/v4 | gin-jwt | lestrrat-go/jwx | none
- **Password Hash:** bcrypt | argon2 | none | not observable
- **Authorization:** router-group middleware + ownership checks | inline checks | none
- **Overall Posture:** Clean | Issues Found - <N> Critical / <N> High / <N> Medium / <N> Low
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(parenthetical omitted when K is 0; whole line omitted on subagent runs)_

[2-3 sentence assessment naming Go-specific risks: missing JWT, `mapstructure.Decode`, raw SQL via `fmt.Sprintf`, exposed `pprof`, `InsecureSkipVerify`. When the diff weakened the authorization posture, this is where each removed control, the rationale offered for it, and why that rationale is not a compensating control are recorded.]

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

#### 1. [Must] file:line _(provenance annotation, when Step 7.5 assigned one)_

- **Location:** [file:line]

- **Issue:** [vulnerability in Go terms - e.g., "OrderHandler.Update accepts `req.Body` via `mapstructure.Decode(req.Body, &order)`; client can submit `{ \"user_id\": 999 }` and override server-assigned owner because no separate request DTO"]

- **Attack scenario:** [pick one and label: (a) concrete exploit; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether reverse proxy strips X-Forwarded-Proto correctly". Do NOT invent an exploit when the realistic threat is regression or topology.]

- **Severity rationale:** [tier] per rubric - [which clause applies; when a composition elevated it, name the constituents]

- **Fix:** [specific Go remediation with code]

#### 2. [Must] file:line

[Same block]

### High / Medium / Low

[Same blocks, numbering continues across tiers]

Omit severity sections with no findings. When every section is empty, write "No security issues found." A composition that empties the High tier by folding its constituents into a Critical is expected - say so in the Summary assessment so the distribution does not read as miscalibrated.

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
