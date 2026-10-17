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

# Go Security Review

Go-aware security review naming Gin JWT middleware (`gin-jwt`, `golang-jwt/jwt`), `ShouldBindJSON` + `go-playground/validator`, GORM / sqlx parameterization, password hashing (`bcrypt`, `argon2`), Go-specific risks (`exec.Command` injection, path traversal, mass assignment by decoding a request body into a domain model, `unsafe`), and Go dependency hygiene (`govulncheck`). Produces findings with attack scenarios and concrete Go remediations.

Stack-specific delegate of `task-code-review-security` for Go.

## When to Use

- Go/Gin PR security regression review
- Pre-deployment hardening on auth, authz, file upload, payment, PII code
- Periodic validation and middleware drift sweep
- Auditing a JWT flow, new auth middleware, or new `crypto` usage

**Not for:** perf review (`task-go-review-perf`), general review (`task-go-review`).

**Depth.** This workflow always runs full - security has cliff-edge consequences. Scope by file, not by depth. A parent-supplied depth is ignored; the Summary and the writer's `depth` always carry `deep`.

**Envelope precedence.** Every atomic this workflow loads declares its own Output Format; they are rule sets here, and only this skill's Output Format is emitted. Where this rubric and `go-security-patterns` disagree on a tier, this rubric wins; a defect this rubric does not classify takes the higher of the two tiers, naming the clause applied.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                                                            |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, auth bypass, mass data exfiltration, working SQL injection (`db.Exec(fmt.Sprintf(..., userInput))`), `exec.Command` with shell + user input, secrets / signing keys committed, JWT `alg: none` accepted. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata / internal services, mass assignment granting admin (a body decoded straight into the model), missing JWT on user-data endpoint, path traversal via `filepath.Join` with no `os.OpenRoot` or `filepath.Rel` guard, a response that serializes a secret (`PasswordHash`, `MFASecret`, a token), `pprof` on the production listener without auth. Also: **a control removed outright, or degraded until it no longer does its job**, with nothing replacing it - `iss`/`aud`/`exp` validation deleted, an algorithm pin removed, TLS verification disabled (`InsecureSkipVerify`), a work factor dropped to the library's floor, a brute-force limit widened by an order of magnitude on a credential endpoint. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control elsewhere (missing CORS allowlist when proxy enforces origin), missing field-level validator tags, debug exposure on non-prod (`pprof` exposed), **resource exhaustion** reachable without auth (uncapped request body, unbounded upload or fetch), and a **control narrowed but still doing its job** (a limit loosened within a defensible range, a cost lowered but still above the recommended floor). Should fix this PR or next.  |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited (`govulncheck` info), hardening without a concrete current attack - a raw model in `c.JSON` that today serializes nothing sensitive is Low with framing (b).                                        |

**Money and entitlement integrity** rates by what the attacker controls: a value they can set that moves money or grants access is High, Critical when unauthenticated; a value they can only observe is Medium.

**Rate a weakened control by what it still stops, not by whether the line was deleted.** Removal and degradation-to-uselessness are the same defect; `InsecureSkipVerify: true` beside a populated `RootCAs` is a deletion written as an assignment. A removed check makes a pre-existing finding newly reachable only when the removed control guarded that finding's path.

**A control that is absent but currently inert is Medium with framing (b), not its rubric tier.** A checklist row can fail while the exploit it guards is blocked elsewhere - `mime/multipart` already applies `filepath.Base`, so an unguarded `filepath.Join` does not escape; `golang-jwt` rejects `alg: none` unless `keyFunc` returns `jwt.UnsafeAllowNoneSignatureType`, and rejects RS/ES against a `[]byte` key, so a missing algorithm pin forges nothing while the key stays symmetric. Name what is holding it back and what would remove that, instead of writing an exploit the code does not permit or dropping the finding. This carve-out does not apply when the blocker is itself in the diff, or is a value the team can change without review. It overrides `go-security-patterns`' exploit-time severity rule for this workflow's reports. A raw model in `c.JSON` that serializes nothing sensitive stays Low per the rubric; neither this carve-out nor `go-security-patterns`' defense-in-depth tier raises it.

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file as a single finding at the elevated severity. Composition is judged on the resulting threat, not on independent exploitability - both halves of every example below are exploitable alone, and they still compose:

- Missing JWT (High) + mass assignment on the *same handler* (High) = **Critical** unauthenticated admin override
- Missing ownership check (High) + ORM model in `c.JSON` exposing `PasswordHash` (High) on the *same handler* = **Critical** account takeover
- SSRF (High) + reachable from unauthenticated endpoint (High) = **Critical** unauth SSRF

When several bullets fire on one handler, file **one** finding at the elevated tier listing every constituent - not one per bullet. Split only when the findings sit on different code paths, or when no composition produces a threat worse than the stronger half alone (then each stands at its own severity). This replaces `go-security-patterns`' `Chain:` convention: constituents merge and no `Chain:` line is emitted.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review-security` | Current branch vs base; fails fast on trunk |
| `/task-go-review-security <branch>` | `<branch>` vs base (3-dot) |
| `/task-go-review-security pr-<N>` | PR head fetched into local branch (user runs fetch) |

**Subagent runs** (of `task-code-review-security` or `task-go-review`). The parent passes the `review-precondition-check` handle, `base_ref` / `head_ref`, `base_sha` / `head_sha`, the pre-read diff and commit log, the pre-confirmed stack, and the data-access mix. Step 3 is skipped whole, SHA capture included - never re-run git. Steps 9 and 10 are skipped (the parent verifies and reconciles the merged set once): labels come from the tier (Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`), a finding whose cited line the diff did not add carries `_(pre-existing)_` and no other annotation (the parent's verify adds `newly reachable via`) so the parent's verify pass starts from it, and the `Findings verified` and `Round` lines are omitted. Step 11 returns **the entire Output Format below except the report file** - Summary, OWASP Triage, Findings, Out of Lens, Recommendations, Next Steps - not the `## Findings` section alone; the parent's merge consumes all of it.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. A subagent loads it too, unless the spawning prompt inlined its Rules.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed from parent. If not Go, stop and recommend `/task-code-review-security`.

Detect: data access (GORM / sqlx / database/sql / mixed, with versions from the `go.mod` require lines), JWT library (`golang-jwt/jwt` v4 vs v5, `gin-jwt`, `lestrrat-go/jwx`), password hashing (`bcrypt` vs `argon2`).

### Step 3 - Resolve Diff and Round

Standalone only - skip the whole step, SHA capture included, when a subagent received the handle.

Use skill: `review-precondition-check` with `report_type: review-security`. Any fail-fast: surface verbatim and stop. Read diff, log and `git diff --name-status <base_ref>...<head_ref>` once; reuse. Capture `base_sha = git rev-parse <base_ref>` and `head_sha = git rev-parse <head_ref>` (full SHAs). The writer's `branch` is the handle's `head_short_name` in every invocation mode; `head_ref` is the handle's.

**Resolve the round from the handle, before any surface is read.** No `prior_checkpoint`, or `prior_checkpoint: legacy` -> `round: 1`. Valid -> `round = prior_checkpoint.round + 1`, `prior_head_sha = prior_checkpoint.head_sha`. **When `prior_checkpoint.head_sha` equals the current `head_sha`, print `No new commits on <head_short_name> since prior security review at <sha_short>. Prior report unchanged.` and stop** - do not re-review and do not overwrite. On a genuine round 2+, re-review the full range; Step 10 reconciles the prior findings.

### Step 4 - Read the Security Surface

Cite real lines. Open:

- `cmd/api/main.go` + router setup - middleware order (`go-gin-patterns` wires `Logger -> Recovery -> ErrorHandler -> MaxBody -> IPRateLimit` on the engine, then `Auth` at group level; a public rate limit sits before auth so `/auth/login` is covered) and which groups have auth
- `internal/middleware/auth.go` - JWT validation, claim extraction, error responses
- `middleware/cors.go` / CORS setup for origin allowlist
- `middleware/ratelimit.go` for auth-endpoint rate limits
- Every changed handler - auth at group level, ownership checks, request DTO, `ShouldBindJSON` usage
- Every changed DTO's validation tags - `binding:"..."` on a struct Gin binds, `validate:"..."` only for a standalone `validator.New()`; a `validate:` tag on a Gin-bound DTO validates nothing
- Every changed query for parameterization
- Config struct for `JWT_SECRET`, allowed origins, env loading
- `go.mod` / `go.sum` for dependency versions
- `.env.example` for documented env vars
- **Static file serving** - `r.Static` / `r.StaticFS` / `http.FileServer` and the directory each serves. A directory that is both writable by an upload handler and served on the app's own origin turns any upload defect into same-origin script execution; Go's file server picks `Content-Type` from the extension, not from whatever the handler validated

When the diff **weakens the authorization posture** - removes middleware, registers a new route outside the authed group, drops `iss`/`aud`/`exp` validation, deletes alg-pinning, widens a limit, or lowers a work factor - `git log -p` the prior revision; the blame trail is authoritative. Any of these is evidence of Insecure Design (A04); call it out even when each change looks "small" in isolation. The team's stated rationale ("internal only, behind the VPC", "we'll add it back later", "QA kept getting locked out") is not a compensating control - a network boundary is not authentication, and a schedule is not a control. Record each removal, the rationale offered, and why it does not compensate, in the Summary paragraph.

**Defects outside the diff.** A defect on a line the diff did not add: in this lens and made newly reachable by the diff -> a finding (Step 9 attributes it); in this lens and untouched by the diff -> a finding at its tier label with `_(pre-existing)_` (Step 9 de-escalates it to `[Recommend]`; on a subagent run the parent's verify does), at most the three most consequential, the rest one line each under `## Out of Lens`; owned by another lens (a leaked goroutine, a missing index) -> `## Out of Lens` with `file:line` and the owning lens.

### Step 5 - OWASP Triage (Go Lens)

**Triage pass**, not findings list. Steps 6-8 produce findings. One verdict per category, from this enum, each with a one-clause reason:

| Verdict | When |
| ------- | ---- |
| `yes` | The listed signal, or another instance of that category, is present anywhere in the surface Step 4 read - including unchanged files. The `Go signal` column is a starting list, not the category's definition: stored XSS via a served upload directory is `yes` on XSS even though the row names `text/template` |
| `no signal in diff` | Checked, nothing found |
| `not verifiable here` | Settling it needs something outside the tree - a CI config, a deployment manifest, a vulnerability database, a live `govulncheck` run. Name what is missing |

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
| Data Integrity (A08) | `gob.NewDecoder(r).Decode` on untrusted input; request body decoded into a domain model; missing request-size limit; `unsafe` |
| Logging & Monitoring (A09) | `slog` logging `password` / `token` / `authorization`; missing auth event log; Sentry not stripping PII |

### Step 6 - Apply the Pattern Bank

Use skill: `go-security-patterns` for the canonical AuthN, AuthZ, validation, injection, crypto, secrets, and SSRF patterns. The skill owns the recipes; this workflow owns the diff-level triage below.

**AuthN diff triage:**

- [ ] Exact algorithm pinned with `jwt.WithValidMethods` (a `keyFunc` method-family check is not a pin); on `golang-jwt/jwt/v5`, `iss` / `aud` / `exp` enforced via `jwt.WithIssuer` / `WithAudience` / `WithExpirationRequired`; on v4, which has no such options and treats a missing `exp` as valid, `claims.VerifyIssuer` / `VerifyAudience` / `VerifyExpiresAt` with `required = true` are called explicitly - absent calls are the finding
- [ ] Access token lifetime short; refresh rotation; revocation surface (`jti` denylist or refresh UUID)
- [ ] Password hashing via `bcrypt` cost >= 10 or `argon2.IDKey`
- [ ] Gin middleware returns 401 with no body details; brute-force rate limit on `/auth/login`, `/auth/refresh`, `/auth/reset-password`
- [ ] No `slog` / `fmt.Println` leaking JWT, password, or session cookie value
- [ ] Cookie sessions (if used): `Secure`, `HttpOnly`, `SameSite`

**AuthZ diff triage:**

- [ ] Every new endpoint sits under an authed group OR is explicitly public-listed (default-deny)
- [ ] Role / permission checks centralized in middleware, not scattered inline
- [ ] Per-owner lookups scope by principal at the repository (`WHERE id = ? AND owner_id = ?`); another principal's resource is `404`, a wrong role `403`
- [ ] Multi-tenant queries scoped by `tenant_id` at the repository (GORM scope), not the handler
- [ ] CORS allowlist explicit; no `AllowAllOrigins: true` for credentialed requests
- [ ] CSRF protection present iff auth model is cookie-session

**Input validation / mass assignment diff triage:**

- [ ] `ShouldBindJSON` (not `BindJSON`)
- [ ] `binding` tags on every DTO field; no `interface{}` / `map[string]any` body
- [ ] No privilege-bearing fields (`Role`, `IsAdmin`, `OwnerID`, `UserID`, `MerchantID`, `TenantID`, `IsActive`, `Verified`) in input DTOs
- [ ] No request body decoded into a domain model (`json.Unmarshal(body, &domain)`, or JSON -> `map[string]any` -> `mapstructure.Decode(m, &domain)`)
- [ ] Response DTO (not raw model) returned; a model serializing a secret is High, otherwise Low with framing (b)
- [ ] `c.ShouldBindUri` / `c.ShouldBindQuery` for path / query params; `uuid.Parse` for UUID path params
- [ ] File uploads: content-type detected via bytes (not header), size capped, stored outside webroot, filename sanitized
- [ ] Path traversal guarded via `os.OpenRoot` + `root.Open` (Go 1.24+), or `filepath.Rel` against the base rejecting a `..` prefix; a bare `strings.HasPrefix` check is itself a finding
- [ ] `exec.Command(name, args...)` with arg slice; no `sh -c` / `cmd /c` with user input

### Step 7 - Go-specific Vulnerability Patterns

Pattern bank in `go-security-patterns`. Diff-level checks:

- [ ] No `fmt.Sprintf` interpolation into SQL; GORM `?`, or sqlx in the driver's bindvar (`$1` on PostgreSQL, `?` on MySQL / SQLite) or `:name`, only
- [ ] No `text/template` with user-supplied template (SSTI); templates from disk or trusted constant
- [ ] No `gob.NewDecoder(r).Decode` on untrusted input; `xml.Unmarshal` / `json.Unmarshal` of untrusted input only after the body is capped with `http.MaxBytesReader`
- [ ] `unsafe` blocks audited and justified
- [ ] No `reflect` field lookup or set (`FieldByName`, `Set*`) with a user-controlled name
- [ ] No `InsecureSkipVerify: true` outside a test fixture
- [ ] Open redirect: `c.Redirect(..., userInput)` validated against allowlist or relative-path-only
- [ ] `crypto/rand` (not `math/rand`) for tokens, nonces, secrets
- [ ] `crypto/subtle.ConstantTimeCompare` / `hmac.Equal` for HMAC / signature - not `==` / `bytes.Equal`
- [ ] `gin.SetMode(gin.ReleaseMode)` in prod; `pprof` not exposed (or behind admin auth)
- [ ] SSRF: user-controlled outbound URL resolves and rejects metadata / loopback / RFC1918 / link-local
- [ ] Webhook: raw body via `c.GetRawData()` before binding; signature via `hmac.Equal`; route outside JWT auth group; body capped with `http.MaxBytesReader` **before** the read; **replay window enforced** - the signed timestamp is parsed and compared to the clock (reject beyond ~5 min), not merely folded into the MAC. Binding `t` into the signature stops an attacker editing it; only a clock comparison stops replaying the original `(t, sig, body)` triple, and a dedup table with no retention policy is a weaker substitute
- [ ] Asynq / Kafka payload trust: re-validate inside the handler whenever the queue is a second entry path to a value an HTTP-boundary control protected, or the broker is reachable by anything outside this service - not only when the payload's original source is untrusted. A signed webhook that enqueues an amount, which the worker then writes without re-checking, has moved the trust boundary to the broker
- [ ] `govulncheck ./...` clean in CI. It needs a toolchain and an advisory database; when either is unavailable, record `not verifiable here` in the triage and say so in the finding rather than implying a clean result

### Step 8 - Data Protection

- [ ] PII / sensitive encrypted at rest (AES-GCM, KMS, or DB column encryption)
- [ ] No ORM model returned from handlers (audit columns leak silently when added later)
- [ ] `slog` redaction: never log `password`, `token`, `credit_card`, `ssn`, `api_key`; use `LogValuer` on secret-holding types
- [ ] No sensitive data in URLs (logs / browser history / referer)
- [ ] TLS enforcement at LB; HSTS via `gin-contrib/secure`
- [ ] DB backups encrypted; access controlled
- [ ] Secrets via typed config struct loaded once at startup; no scattered `os.Getenv`; `.env` gitignored

### Step 9 - Verify Findings

Assign each draft finding its label first - Critical / High -> `[Must]`, Medium / Low -> `[Recommend]` - because `review-finding-verify` takes labelled findings as input and returns adjusted ones.

Use skill: `review-finding-verify` with those findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`. **The label it returns is final** - it de-escalates `[Must]` to `[Recommend]` on untouched pre-existing code, and that survives into the finding heading and into Next Steps. Never re-derive a label from the severity tier after this step; a `### Critical` finding tagged `[Recommend]` because it is pre-existing is the correct output, not a contradiction. Carry its `Annotation` column verbatim onto the heading (`_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`; only Step 10's projection splits the combined group) and its tally into the Summary's `Findings verified` slot. The verify table is working material; only the tally and the surviving rows' labels and annotations reach the report.

Subagent runs skip this step entirely (see Invocation).

### Step 10 - Reconcile Prior Findings (round 2+, standalone)

Skip on round 1. Otherwise read the prior report at the handle's `report_path` and project its findings into the reconciler's shape: `## High-Impact Findings` holding one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, the label and `file:line` copied from the `#### <n>. [Label] file:line` heading, annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` becomes `_(pre-existing)_ _(newly reachable via X)_`). Use skill: `review-prior-findings-reconcile` with `prior_report` (the projection), `diff`, `name_status`, `head_sha`, and `head_files` (`git ls-tree -r --name-only <head_sha>`). Insert its table under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows re-enter `## Findings` under the severity heading they were last published under (re-rated only when this round re-drafted the defect), with the label and annotation groups they were last published with plus `_(carried from round <N>)_` (N = the round that first raised it, written once) on the heading, so the next round reconciles them again; when this round re-drafted the same defect at the same site, publish only the re-drafted finding with that annotation appended. The table keeps the prior label and line verbatim.

### Step 11 - Write Report

Standalone only - subagent runs return the Output Format to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-security` and every required input: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 3, `stack: go-gin`, `scope: +sec`, `depth: deep` (this workflow always runs full depth), `mode: full`, and the `round` / `prior_head_sha` resolved in Step 3. Write before ending; print confirmation.

## Self-Check

Mark a line N/A with its reason when the diff has no matching surface, or when the invocation mode makes it inapplicable (subagent, round 1).

- [ ] Step 1: `behavioral-principles` loaded, or rules inlined in the spawning prompt
- [ ] Step 2: stack confirmed; data-access mix with versions, JWT library, password hash recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-security` (or handle received); diff, log and name-status read once; `base_sha` / `head_sha` captured; round resolved from the handle; same-SHA no-op honoured; approval obtained when `head_matches_current` was false
- [ ] Step 4: security surface read directly; static file serving checked; prior revision consulted when a control was removed; defects outside the diff routed per the Step 4 rule
- [ ] Step 5: OWASP triage produced one verdict per category from the three-value enum, with a reason; not duplicated as standalone findings
- [ ] Step 6: `go-security-patterns` applied; AuthN, AuthZ, DTO / mass-assignment triage done; **every new endpoint has JWT OR is explicitly public-listed**
- [ ] Step 7: injection, templates, decoders, `unsafe`, `reflect`, `InsecureSkipVerify`, redirect, randomness, constant-time compare, `pprof`, SSRF, webhook, queue trust, `govulncheck` checked where the diff touches them
- [ ] Step 8: data protection (encryption at rest, model on the wire, `slog` redaction, secrets in URLs, TLS / HSTS, typed config) checked
- [ ] Step 9 (standalone): findings labelled before verify; verify's labels and annotations carried onto the headings verbatim; tally in the Summary
- [ ] Step 10 (round 2+): prior report projected and reconciled with `head_sha`; table inserted; `Still open` / `Needs re-check` rows carried into Findings
- [ ] Step 11 (standalone): report written via `review-report-writer` with all checkpoint fields; confirmation printed. Subagent: Output Format returned, no file written
- [ ] Severity rubric applied consistently; every finding has an attack scenario, "regression risk" rationale, or "topology-dependent" framing
- [ ] Next Steps tagged `[Implement]` or `[Delegate]`, ordered Must > Recommend (omitted only when no issues)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Fill rules.** `Overall Posture` counts every published finding by tier, whatever its label: `Issues Found - <N> Critical / <N> High / <N> Medium / <N> Low`. `Depth` is always `deep`. `Password Hash` is `bcrypt | argon2 | weak (<algorithm>) | none | not observable` - `weak` for an unsalted or fast digest (`sha256`, `md5`) used as a password hash, `not observable` when only a verify call (`CompareHashAndPassword`) is in the tree and no hash is generated. `Authorization` is `router-group middleware + ownership checks | inline checks | partial - <where missing> | none`. `Findings verified` is omitted on subagent runs, its parenthetical when K is 0. Any field whose value the repo cannot settle takes the value plus `(inferred from <evidence>)`.

**Each finding is its own numbered block** under its severity heading, headed `#### <n>. [Label] file:line _(annotations)_` where the label and annotations come from Step 9 verbatim (tier-derived label and `_(pre-existing)_` on subagent runs; `_(carried from round <N>)_` on carried findings). Numbering continues across tiers so Recommendations and Next Steps can cite `finding <n>`. Blank lines separate the field lines; consecutive bare `**Label:** value` lines collapse into one paragraph when the report renders.

```markdown
## Go Security Review Summary

- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM <version> | sqlx <version> | database/sql | mixed - <both, named>
- **JWT Library:** golang-jwt/jwt/v5 | golang-jwt/jwt/v4 | gin-jwt | lestrrat-go/jwx | none
- **Password Hash:** bcrypt | argon2 | weak (<algorithm>) | none | not observable
- **Authorization:** router-group middleware + ownership checks | inline checks | partial - <where missing> | none
- **Depth:** deep
- **Overall Posture:** Clean | Issues Found - <N> Critical / <N> High / <N> Medium / <N> Low
- **Round:** <N>                                {round 2 onward; omitted on subagent runs}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)

[2-3 sentence assessment naming Go-specific risks: missing JWT, a body decoded into the model, raw SQL via `fmt.Sprintf`, exposed `pprof`, `InsecureSkipVerify`. When the diff weakened the authorization posture, this is where each removed control, the rationale offered for it, and why that rationale is not a compensating control are recorded.]

## OWASP Triage

| Category                  | Verdict                                             | Reason                                  |
| ------------------------- | --------------------------------------------------- | --------------------------------------- |
| Broken Access Control     | yes \| no signal in diff \| not verifiable here     | [signal cited, or what is missing]      |
| Injection                 | ...                                                 | ...                                     |
| Cryptographic Failures    | ...                                                 | ...                                     |
| Security Misconfiguration | ...                                                 | ...                                     |
| SSRF                      | ...                                                 | ...                                     |
| XSS                       | ...                                                 | ...                                     |
| Insecure Design           | ...                                                 | ...                                     |
| Vulnerable Components     | ...                                                 | ...                                     |
| Data Integrity Failures   | ...                                                 | ...                                     |
| Logging & Monitoring      | ...                                                 | ...                                     |

## Prior Round Reconciliation     {round 2+ only; omit otherwise}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

### Critical

#### 1. [Must] file:line _(annotations)_     {annotation groups only when Step 9, Step 10, or the subagent rule assigned any}

- **Location:** [file:line]

- **Issue:** [vulnerability in Go terms - e.g., "OrderHandler.Update decodes the body straight into `order`; client submits `{ \"user_id\": 999 }` and overrides the server-assigned owner because there is no separate request DTO"]

- **Attack scenario:** [pick one and label: (a) concrete exploit; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether reverse proxy strips X-Forwarded-Proto correctly". When two apply, label the one that sets the tier and name the other in a clause. Do NOT invent an exploit when the realistic threat is regression or topology.]

- **Severity rationale:** [tier] per rubric - [which clause applies; when a composition elevated it, name the constituents]

- **Fix:** [specific Go remediation with code]

#### 2. [Must] file:line

[Same block]

### High / Medium / Low

[Same blocks, numbering continues across tiers]

Omit severity sections with no findings. When every section is empty, write "No security issues found." A composition that empties the High tier by folding its constituents into a Critical is expected - say so in the Summary assessment so the distribution does not read as miscalibrated.

## Out of Lens

[Defects noticed while reading the surface that another lens owns, and pre-existing in-lens defects beyond the three published - each with `file:line` and the owning lens. Omit when there are none.]

## Recommendations

[Prioritized hardening not tied to a finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]` (`[scope: <owning lens or team>]` on delegated items; a row spanning files lists them comma-separated). Order: Must > Recommend. Each item carries its finding's label as published; one row per finding, naming a shared edit on the row rather than repeating it.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: platform team] - [one-line action]

_Omit if no issues found._
```

## Avoid

- `git fetch` / `git checkout` from this workflow
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment")
- Generic advice when Go idiom applies ("apply auth at router-group level via `v1.Group(\"/orders\", auth.Required())`", not "add authorization check")
- Disabling middleware to silence a failing test - fix the test
- Widening authorization (an endpoint moved out of the authed group, a removed JWT check) without a security review note
- Conflating security with general or perf review
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
