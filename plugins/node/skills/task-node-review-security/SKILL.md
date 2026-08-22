---
name: task-node-review-security
description: Node.js / NestJS / Express security review: Guards, JWT, Passport, Zod/ValidationPipe, mass assignment, ORM injection, prototype pollution, OWASP.
agent: node-security-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, security, jwt, passport, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Security Review

Stack-specific delegate of `task-code-review-security`. Names NestJS Guards / Passport / `@nestjs/jwt`, `ValidationPipe` + class-validator / Zod, Express middleware auth, ORM parameterization, and Node-specific risks (prototype pollution, ReDoS, deserialization, RCE via `vm`/`eval`) directly.

## When to Use

- NestJS or Express PR security regression review
- Pre-deploy hardening pass on auth, authz, file upload, payment, or PII paths
- Periodic guard / validation drift sweep
- Auditing JWT flow, new guard, or new Passport strategy

**Not for:** performance (`task-node-review-perf`), general review (`task-node-review`).

**Depth.** This lens always runs every step - security has cliff-edged consequences (auth bypass, RCE), so it scopes by file, not by depth. A depth argument from the user or a parent changes nothing about what runs; pass `depth: deep` to the report writer, whose enum is `standard | deep` and has no `full`.

## Severity Rubric

| Severity     | Definition                                                                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauth RCE, auth bypass, mass exfiltration, working SQLi, secrets/signing keys in source, prototype pollution reaching privileged path, credentials stored under a fast or unsalted hash, path traversal reaching an arbitrary filesystem write. Blocks merge. |
| **High**     | Authenticated priv-esc, IDOR on sensitive data, SSRF to metadata/internal, mass assignment of privilege fields, missing authz on user-data endpoints, no brute-force control on a credential endpoint. |
| **Medium**   | Hardening gap with mitigating control elsewhere, missing field constraints, weak rate limit on non-critical endpoint, debug exposure on non-prod.       |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited threshold, hardening without concrete current attack.                                    |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                            | Meaning                                                                       |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| `/task-node-review-security`          | Current branch vs base; fails fast on trunk                                   |
| `/task-node-review-security <branch>` | `<branch>` vs its base (3-dot)                                                |
| `/task-node-review-security pr-<N>`   | PR head in local branch `pr-<N>` (user fetches first)                         |

`task-node-review` spawns this workflow as its `+Sec` subagent; `task-code-review-security` routes to it rather than embedding it. As a subagent, Step 2 is skipped and pre-read artifacts are reused, and Step 10 takes its subagent branch.

## Workflow

### Step 1 - Load Behavioral Principles and Confirm Stack

Use skill: `behavioral-principles` first, before any other delegation. Then use skill: `stack-detect` to confirm Node.js / TypeScript; if invoked as a delegate (parent already detected), accept the pre-confirmed stack. If not Node, stop and route to `/task-code-review-security`.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express. Record `Framework: NestJS | Express | mixed`. Steps branch on this where idioms differ.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument; forward `--base <branch>` when passed. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Also capture `base_sha` / `head_sha` via `git rev-parse` on those refs - the writer runs no git of its own. Skip entirely as a subagent when the parent passes the handle.

If `review-precondition-check` fails fast, surface verbatim and stop. Never run state-changing git from this workflow.

**Re-review gate (standalone only).** The handle's `prior_checkpoint` is keyed to `review-<branch>.md`, the general review's report - not this lens's. Check for `review-security-<branch>.md` yourself, sanitizing `branch` the way the writer does (`/` and any character outside `[A-Za-z0-9_-]` becomes `-`). If it exists with valid frontmatter and its `head_sha` equals the current head, print `No new commits on <branch> since prior security review at <sha_short>. Prior report unchanged.` and stop without writing. Otherwise `round` = prior + 1, and pass its `head_sha` as `prior_head_sha`. No such file, or one whose frontmatter is missing or invalid -> `round: 1`, no `prior_head_sha`; that is the common path and it is not an error.

**The reviewable surface is the repo at `head_ref`, not the diff.** Step 3 names files to open whether or not they changed; read them. `not verifiable` is for a file you genuinely could not read - absent, or outside the checkout a parent handed you - never for one that merely sits outside the diff. Note each as you go; they populate the report's `Not verifiable from this diff` block, and they are the reason `Overall Posture` may be `Clean (partial coverage)` rather than `Clean`.

### Step 3 - Read the Security Surface

Open files that actually wire security so findings cite real lines:

- **Guards / middleware**: every `@UseGuards(...)` and impl (`AuthGuard('jwt')`, custom `RolesGuard`); Express auth middleware (`requireAuth`, `passport.authenticate`)
- **Strategies / config**: `jwt.strategy.ts`, `local.strategy.ts`, `auth.module.ts`; Express `app.ts` / `server.ts` for `helmet`, `cors`, `express-rate-limit`, body-parser limits
- **Validation**: DTOs with class-validator decorators, Zod schemas; `ValidationPipe` global config in `app.module.ts`
- **Changed routes**: controllers / routers, `@Roles`, `@Public()`, body DTO types
- **Dependencies**: `@nestjs/jwt`, `passport-jwt`, `bcrypt`/`argon2`, `helmet`, `express-rate-limit`, `csurf` (deprecated - flag), `jsonwebtoken`/`jose`
- **Secrets**: `.env.example`, config module for `JWT_SECRET`, `JWT_ALGORITHM`, allowed origins

When the diff removes a guard or relaxes auth, `git log -p` prior revision to confirm what was protected.

### Step 4 - OWASP Triage (Node Lens)

Triage pass only. Findings go in Steps 5-9; do not duplicate here. One verdict per category:

| Verdict | Meaning |
| ------- | ------- |
| `finding` | The diff carries this risk and Steps 5-9 raise it |
| `clean` | The diff exercises this category and the control is correct - name it (`RolesGuard + tenant-scoped findFirst`) |
| `no signal in diff` | The diff neither exercises nor affects this category |
| `not verifiable` | The category depends on a file you could not read at `head_ref` - carry it to the report's `Not verifiable` block |

`clean` is the verdict a well-built PR earns; using `no signal in diff` for a diff that visibly adds two guards states something false and erases the reviewer's actual work.

| Risk                          | Node-specific check                                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every endpoint declares authz: `@UseGuards(AuthGuard('jwt'), RolesGuard)` + `@Roles(...)` or route-level `requireAuth` + `requireRole`. Empty = finding.  |
| Identification & Auth Failures | Hashing algorithm/cost, rate limit on auth routes, token lifetime/rotation, session cookie flags (depth in Step 5).                                      |
| Injection                     | Prisma raw via tagged template `$queryRaw` parameterized; `$queryRawUnsafe(string)` not. TypeORM `repository.query(sql, [positional])` or QueryBuilder `:name` params.  |
| Cryptographic Failures        | `bcrypt` (cost >=10) or `argon2`. Never `md5`/`sha1` for auth. JWT signing key from env, not hardcoded.                                                   |
| Security Misconfiguration     | `helmet()` applied; CORS origin allowlist (not `*` for credentialed); Swagger gated/disabled in prod.                                                     |
| SSRF                          | User-controlled outbound URL: the check must bind to the **resolved IP** at connect time (custom `Agent` / `lookup`), rejecting RFC1918, link-local, and metadata. Validating the hostname then calling `fetch(rawUrl)` re-resolves and does not defeat rebinding. |
| XSS                           | NestJS auto-escapes JSON; Handlebars/EJS `<%-` flagged; Express raw HTML inspected.                                                                       |
| Insecure Design               | Default-deny: NestJS `APP_GUARD` global; Express top-level `requireAuth` before route registration.                                                       |
| Vulnerable Components         | `npm/pnpm/bun audit` clean for High/Critical; Renovate/Dependabot active.                                                                                 |
| Data Integrity Failures       | `eval` / `new Function` / `vm2` flagged - any occurrence critical. `Object.assign(target, userInput)` = mass assignment, and reassigns the target's own prototype via `__proto__`; a recursive merge (`lodash.merge`) is what pollutes `Object.prototype` process-wide. |
| Logging & Monitoring          | Logger never logs `password`/`token`/`authorization`/`cookie`. `@Exclude()` on sensitive fields. Sentry `beforeSend` strips PII.                          |

### Step 5 - Authentication

**Both frameworks:**

- [ ] **Password hashing**: `bcrypt` cost >=10 or `argon2`; flag `crypto.createHash('sha256'/'md5')` or homebrew
- [ ] **Brute-force protection**: rate limit on `/auth/login`, `/refresh`, `/reset-password` (NestJS `@nestjs/throttler`; Express `express-rate-limit` or `rate-limiter-flexible` + Redis for multi-instance)
- [ ] **Password reset tokens**: time-limited, single-use, hashed before storage
- [ ] **No JWT in logs**

**NestJS:**

- [ ] **JWT signing**: HS256 secret in env/Vault; RS256 key pair preferred cross-service; `JwtModule.register` uses `secretOrKeyProvider` for rotation
- [ ] **Algorithm allowlist**: `JwtStrategy` declares `algorithms: ['HS256']` (or `['RS256']`) explicitly. On current `jsonwebtoken` this is what blocks RS256->HS256 confusion; `alg: none` is already rejected whenever a key is supplied, so do not write the finding as an `alg: none` bypass
- [ ] **`issuer` / `audience`** verified in `JwtStrategy` options, not just signature
- [ ] **Access token lifetime** short (5-15 min); refresh rotation with revocable denylist (track `jti` in DB/Redis)
- [ ] **`AuthGuard('jwt')` wired correctly**: missing-token returns 401

**Express:**

- [ ] **JWT verification**: `jsonwebtoken.verify(token, key, { algorithms: ['HS256'] })` - allowlist **mandatory**. On current versions it is what blocks RS256->HS256 confusion, where a public key or certificate is replayed as an HMAC secret; `jsonwebtoken < 9` additionally accepted `alg: none` without it. Keep the rule unconditional. Prefer `jose.jwtVerify(token, key, { algorithms, issuer, audience })` (stricter defaults)
- [ ] **Session cookies**: `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'|'strict'`, signed

### Step 6 - Authorization

**NestJS:**

- [ ] **Authz drift sweep**: every new endpoint has a guard (`@UseGuards(AuthGuard('jwt'))` or stronger), or global `APP_GUARD` covers it and `@Public()` is absent
- [ ] **Role/permission checks** centralized in `RolesGuard`/`PoliciesGuard` via `Reflector.getAllAndOverride` reading `@Roles(...)` metadata - not inline `if (user.role !== 'admin')` scattered in handlers
- [ ] **IDOR**: scope lookups through principal (`findFirst({ where: { id, ownerId: user.sub } })`) rather than `findUnique({ id })` + separate ownership check
- [ ] **Tenant isolation**: scope by `tenantId` at repository/service (Prisma middleware or interceptor), not just controller
- [ ] **CORS**: `enableCors({ origin: [...] })` allowlist (never `'*'` for credentialed)
- [ ] **CSRF**: not required for stateless JWT-bearer; required for cookie-session. `csurf` deprecated - recommend `csrf-csrf`

**Express:**

- [ ] **Authz middleware** per route or router (`router.use(requireAuth)`, `requireRole(...)`)
- [ ] **Object-level authz** in data layer or dedicated authorize step - never controller-surface-only
- [ ] **Default-deny**: top-level `app.use(requireAuth)` mounted before public routes; flag endpoints without auth
- [ ] **CSRF**: same as NestJS

### Step 7 - Input Validation and Mass Assignment

**NestJS (class-validator + class-transformer):**

- [ ] **`ValidationPipe` global**: `new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true })` - strips unknown, 400s on unknown, instantiates DTOs
- [ ] **Every `@Post`/`@Put`/`@Patch`** declares a DTO class - never `@Body() body: any` or `Record<string, unknown>`
- [ ] **Field constraints**: `@IsString`, `@IsEmail`, `@MinLength`, `@MaxLength`, `@Matches`, `@IsInt`, `@Min`, `@Max` on every user-supplied field
- [ ] **No privilege fields in input DTOs**: `role`, `isAdmin`, `ownerId`, `userId`, `tenantId`, `verified` - server-set only; admin path uses separate DTO
- [ ] **Sensitive columns never reach the wire.** `@Exclude()` + `ClassSerializerInterceptor` only works on an instance of a decorated class - a Prisma model is a plain object and serializes every field regardless, so on Prisma the control is `select` / `omit` at the query, or `plainToInstance(UserDto, row, { excludeExtraneousValues: true })` with `@Expose()` on each field - class-transformer exposes everything by default, so a bare `plainToInstance` copies `passwordHash` straight onto the instance
- [ ] **`ParseIntPipe`/`@Transform`** on numeric path params (default string)

**Express (Zod or class-validator):**

- [ ] **Zod schemas** for body/query/params with `.strict()` (rejects unknown); validation middleware 400s on failure
- [ ] **No `req.body` passthrough**: `prisma.user.create({ data: req.body })` is mass-assignment - whitelist: `data: { name: parsed.name, email: parsed.email }`
- [ ] **`.strict()` on anything that feeds a write**: `z.object()` strips unknown keys by default, so the parse *result* is safe - the mass-assignment vector is passing `req.body` onward instead of the result. `.strict()` rejects rather than strips, which surfaces the caller's mistake. `.passthrough()` re-opens the vector and is not acceptable on a write path however well documented; a partner that must send extra fields gets them declared, not passed through. (Zod 4 spells these `z.strictObject()` / `z.looseObject()`.)
- [ ] **express-validator** alternative: `validationResult(req).isEmpty()` checked at top of every handler

**Both:**

- [ ] **File uploads**: type by content (`file-type` magic bytes), not `mimetype` header; per-file size limit (Express `multer({ limits: { fileSize } })`; NestJS `FileInterceptor('file', { limits: { fileSize } })`); stored outside webroot, `Content-Disposition: attachment` on serve; filename sanitized with the base-plus-separator check in the next bullet, never a bare prefix match; virus scan or accepted-risk documented
- [ ] **Path traversal**: `path.resolve(baseDir, userInput)` then `startsWith(baseDir + path.sep)` - without the separator, `/var/uploads-evil` passes a `/var/uploads` prefix check. `path.join` normalizes but does not constrain to a base, so it is not the control
- [ ] **Process exec**: `child_process.execFile([...args])` arg array, never `exec(string)` or `exec(\`... ${userInput} ...\`)`; allowlist binaries; never `shell: true` with user input

### Step 8 - Common Node.js Vulnerability Patterns

Canonical "build it right" patterns: Use skill: `node-security-patterns` (JWT signing/verify, mass-assignment DTOs, prototype pollution, SSRF allowlist, file upload, webhook signatures, secrets, `eval`/`vm` prohibitions, open redirect, `child_process.execFile`, TLS). This step flags deviations.

Surface-specific extras not covered by the atomic:

- [ ] **Body size bounded**: body-parser defaults to `100kb`, so a bare `express.json()` is not the finding - a raised `limit`, or `express.raw()` / `express.text()` mounted without one, is (NestJS: `bodyParser` options on the adapter)
- [ ] **`require(userInput)` / dynamic `import(userInput)`** = RCE (delegate canonical handling to `node-security-patterns`)
- [ ] **`fs.writeFile`/`fs.unlink` with user input** without path-base check = FS tampering
- [ ] **Raw SQL injection** = critical. Prisma: the `$queryRaw\`...\`` tagged template parameterizes; `$queryRawUnsafe(string)` does not. TypeORM: `repository.query(sql, params)` binds **positionally** (`$1` on pg, `?` on mysql) - `:name` is QueryBuilder-only (`.where('x = :name', { name })`) and passing it to `.query()` leaves the statement unbound
- [ ] **SSTI**: rendering Handlebars/EJS/Nunjucks with user-controlled template strings = RCE; templates from disk only
- [ ] **Debug exposure**: NestJS Swagger gated behind auth in prod or skipped (`if (NODE_ENV !== 'production')`)
- [ ] **BullMQ payloads**: validate with Zod/class-validator inside processor when queue is reachable from untrusted input
- [ ] **ReDoS**: `@Matches(new RegExp(userInput))` / `z.string().regex(new RegExp(userInput))` from user/config hangs event loop. Compile patterns at module load; consider `safe-regex` at review
- [ ] **HTTP request smuggling/desync**: flag custom HTTP/1.1 parsing or proxy middleware that re-emits headers without validation

### Step 9 - Data Protection

- [ ] **PII encrypted at rest**: KMS/AES-GCM or DB column encryption
- [ ] **Logging filter**: `pino` `redact: ['password', 'token', ...]` or `winston` custom format; `@Exclude()` reinforces
- [ ] **No sensitive data in URLs** (use POST body / headers / signed tokens)
- [ ] **TLS**: HTTPS-only at LB; HSTS via `helmet.hsts({ maxAge: 31536000 })`
- [ ] **DB backups encrypted**; access controlled
- [ ] **Secrets**: from Vault/AWS SM/GCP SM/Doppler; `.env` gitignored; access via typed `ConfigService` so missing-at-startup fails fast

**One construct, one finding.** A construct carrying several defects (a handler that is both mass-assignable and unauthorized) publishes once at the worst severity, naming the others in its Issue line. When an exploit chains two constructs, file it once at the point the fix lands and name the other in the attack scenario.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary.

Its `Label` wins over the severity mapping: a `### High` finding tagged `[Recommend]` because it is pre-existing and untouched is the correct output, not a contradiction. Subagent runs skip this step - the parent verifies the merged set once.

### Step 10 - Write Report

**Subagent mode:** if invoked by `task-node-review`, do not write a file - `review-report-writer` is invoked only by the workflow that owns the report. Return exactly four things, and this list supersedes any generic "return your Output Format" instruction in the parent's prompt:

1. The findings, each carrying its `[Must]` / `[Recommend]` label and its `file:line`
2. `## Next Steps`, tagged and ordered, for the parent to re-sort into its own
3. `## Recommendations` (the parent's Summary has no security fields, so anything Summary-shaped that still matters goes here as a bullet). The `Not verifiable` items travel in Next Steps only - do not also list them here
4. The `## OWASP Triage` table only when a row is `finding` or `not verifiable` - a table of eleven `clean` / `no signal` rows is not worth the parent's report

Omit the Summary block - the parent owns it. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-security` and every field it marks required:

- `report_body` (the assembled Markdown), `branch`, `base_ref`, `head_ref` - from the precondition handle
- `base_sha` / `head_sha` captured in Step 2 via `git rev-parse`
- `scope: +sec`, `depth: deep` (this lens always runs full depth; `full` is not a valid `depth` value), `stack = node-typescript`, `mode: full`
- `round` from Step 2's re-review gate, plus `prior_head_sha` when round > 1

Write the assembled review to file and print the confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

Every finding carries exactly one label: `[Must]` (Critical / High) or `[Recommend]` (Medium / Low), unless the verify pass returned a different `Label`, which wins. No other label is written.

```markdown
## Node.js Security Review Summary

- **Stack Detected:** Node.js <version> / TypeScript <version>
- **Framework:** NestJS <version> | Express <version> | mixed
- **ORM:** Prisma <version> | TypeORM <version>
- **Target:** <base_ref>...<head_ref>
- **Auth:** JWT (jsonwebtoken) | JWT (jose) | NestJS Passport JWT | NestJS Passport Local | Session (cookie) | Custom | Hybrid
- **Authorization:** NestJS Guards | Express middleware | Custom
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(omit the parenthetical when K is 0)_
- **Overall Posture:** Clean | Issues Found - [<N> Critical / <N> High / <N> Medium / <N> Low] - append `(partial coverage)` to either whenever the `Not verifiable` block is non-empty

[2-3 sentence assessment calling out Node-specific risks: missing `whitelist: true`, prototype pollution from `Object.assign(target, req.body)`, exposed Swagger in prod, `csurf` dep. On a clean diff, say what the controls actually are rather than restating the verdict.]

## OWASP Triage

| Category                       | Verdict                                              | Basis                                    |
| ------------------------------ | ---------------------------------------------------- | ---------------------------------------- |
| Broken Access Control          | finding / clean / no signal in diff / not verifiable | [the control seen, or the file not in scope] |
| Identification & Auth Failures | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Injection                      | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Cryptographic Failures         | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Security Misconfiguration      | finding / clean / no signal in diff / not verifiable | [...]                                    |
| SSRF                           | finding / clean / no signal in diff / not verifiable | [...]                                    |
| XSS                            | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Insecure Design                | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Vulnerable Components          | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Data Integrity Failures        | finding / clean / no signal in diff / not verifiable | [...]                                    |
| Logging & Monitoring           | finding / clean / no signal in diff / not verifiable | [...]                                    |

## Not verifiable

_Controls that could not be confirmed because the file could not be read at `head_ref`. Not findings - each is a "check this separately" item, and together they are why the posture may read `Clean (partial coverage)`. Omit when everything was visible._

- `main.ts` not in diff - global `ValidationPipe` options unconfirmed
- `package.json` not in diff - no `pnpm audit` signal

## Findings

### Critical

1. **[Must]** **Location:** [file:line - add `_(pre-existing)_` or `(unverified: <reason>)` when the verify pass returned one]

   **Issue:** [vulnerability in Node terms - e.g., "the global `ValidationPipe` runs without `whitelist: true`, so `CreateOrderDto` accepts `{ ownerId: 999 }` and the client overrides the server-assigned owner"]

   **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: ..." for test/monitoring gaps; (c) "Topology-dependent: ..." for infra-flavored. Do NOT invent exploits when the realistic threat is regression or topology.]

   **Severity rationale:** [tier] per rubric - [which clause applies]

   **Fix:** [specific Node remediation with code - `ValidationPipe` config, Prisma `omit`, `@UseGuards(AuthGuard('jwt'))`, etc. Several fixes on one construct become a numbered list here.]

### High / Medium / Low

[Same numbered-block structure; numbering continues across tiers. Omit sections with no findings. If all omitted, state "No security issues found."]

## Recommendations

[Prioritized hardening not tied to a specific finding - e.g., "Add `@nestjs/throttler` on /auth/login", "Migrate from jsonwebtoken to jose", "Move JWT_SECRET to Vault"]

## Next Steps

Tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting hardening, dependency upgrade, threat model). Carry each finding's label. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_With no findings, this section still carries one `[Delegate]` item per `Not verifiable` row, each labelled `[Recommend]` - an unverified control is not a finding, so it never earns `[Must]`. Omit only when there are no findings and nothing was unverifiable._
```

## Self-Check

- [ ] `behavioral-principles` loaded first; stack confirmed; framework recorded; diff + log read once, SHAs captured via `git rev-parse`, re-review gate applied; prior revision consulted when guards/auth middleware removed (Steps 1-3)
- [ ] OWASP triage: one verdict per category from the four-value enum, with its basis; findings not duplicated (Step 4)
- [ ] Authn / authz drift sweep covered every new endpoint (Steps 5-6)
- [ ] DTO / Zod validation, mass-assignment fields, `@Exclude()` / `whitelist` / `.strict()` confirmed (Step 7)
- [ ] When touched: file upload, path traversal, exec, prototype pollution, `eval`, raw SQL, dynamic require, `rejectUnauthorized: false`, open redirect (Step 8)
- [ ] Data protection assessed: PII at rest, log redaction, secrets sourcing, TLS (Step 9)
- [ ] Severity rubric applied consistently; every finding carries one label plus an attack scenario, regression-risk, or topology-dependent framing; one construct published one finding
- [ ] `review-finding-verify` ran and its tally reached the Summary (or the subagent carve-out applied); its `Label` carried, overriding the severity mapping
- [ ] Every control that could not be seen (CORS, rate limiting, helmet, debug exposure, hashing config, Sentry `beforeSend`, `npm audit`) recorded in `Not verifiable from this diff` and carried into Next Steps
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend
- [ ] Step 10: standalone: every required writer field assembled (`depth: deep`, never `full`), report written, confirmation printed; subagent: labelled findings + Next Steps + Recommendations returned, no file written

## Avoid

- Running state-changing git from this workflow (user runs fetches/checkouts)
- Reporting vulnerabilities without an attack scenario - "input not validated" vs "attacker submits `{role:'admin'}` and gains admin via mass assignment because `whitelist: true` is missing"
- Skipping OWASP categories - every row gets a verdict, and a category the diff exercises correctly is `clean`, not `no signal in diff`
- Reporting `Clean` when the files that carry the controls were never in scope - that is `Clean (partial coverage)`
- Recommending `:name` parameters for TypeORM `repository.query`, or `@Exclude()` as the control on a Prisma model
- Generic advice when a Node idiom applies (say "add `@UseGuards(AuthGuard('jwt'))`", not "add an auth check")
- Suggesting `csurf` (deprecated) - recommend `csrf-csrf` or session-anti-CSRF
- Suggesting `@Public()` or removing `requireAuth` as a fix for a failing auth-required test - fix the test
- Disabling guards / `ValidationPipe` to silence failing tests
- Conflating with general code review or perf - delegate to those workflows
- Recommending `algorithms: undefined` for `jsonwebtoken.verify` - explicit allowlist only
- Approving `eval` / `new Function` / `vm`/`vm2` on input not under full server control
- Approving `rejectUnauthorized: false` outside test fixtures
- Approving Swagger UI / `/api-docs` exposed in any non-dev profile
- Recommending `lodash.merge(target, req.body)` - prototype pollution vector
- Accepting `.passthrough()` on a write path because it was "documented"
