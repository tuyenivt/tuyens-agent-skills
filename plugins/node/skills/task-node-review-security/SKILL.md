---
name: task-node-review-security
description: Node.js security review for NestJS Guards / JWT / Passport, Express middleware auth, ValidationPipe / Zod input validation, mass assignment, ORM injection, prototype-pollution risks, and Node-aware OWASP Top 10. Detects NestJS vs Express and applies the right framework idioms. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to Node.js / TypeScript.
agent: node-security-engineer
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, security, jwt, passport, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Node.js Security Review

## Purpose

Node.js-aware security review that names NestJS `@UseGuards`, Passport strategies, JWT (`jsonwebtoken`, `jose`), `ValidationPipe` + `class-validator` / Zod, Express middleware-based auth, ORM parameterization, password hashing (`bcrypt`, `argon2`), and Node-specific risks (prototype pollution, ReDoS, deserialization) directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Node-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Node.js. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a NestJS or Express PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and guard drift sweep across endpoints
- Auditing a JWT flow, a new NestJS guard, or new Passport strategy

**Not for:**

- Performance review (use `task-code-review-perf` or `task-node-review-perf`)
- General code review (use `task-code-review` or `task-node-review`)
- Production incident triage (use `/task-oncall-start`)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path, secrets / signing keys exposed in source, prototype pollution reaching a privileged code path. Must fix before deploy; blocks merge.              |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata or internal services, mass assignment of privilege-bearing fields, missing authorization on user-data endpoints. Must fix before merge.                                     |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS when a reverse proxy enforces origin), missing field-level constraints, weak rate limiting on a non-critical endpoint, debug exposure on a non-prod profile. Should fix this PR or the next one. |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                       |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                            | Meaning                                                                                               |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-node-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-node-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-node-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-node-review` (parent already detected Node), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Node, stop and tell the user to invoke `/task-code-review-security` instead.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express (`express` in deps without NestJS). Record `Framework: NestJS | Express | mixed` for the Summary block. Each step that follows branches on this signal where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

**NestJS surface:**

- Every `@UseGuards(...)` decorator and the guard implementations (`AuthGuard('jwt')`, custom `RolesGuard`, `PoliciesGuard`)
- Every changed controller / route handler - look for `@UseGuards`, `@Roles`, `@Public()` decorators, request DTO types
- Every DTO with `class-validator` decorators (`@IsString()`, `@MinLength()`, `@Matches()`) and `class-transformer` `@Transform`
- `auth.module.ts`, `jwt.strategy.ts`, `local.strategy.ts`, Passport strategy implementations
- `app.module.ts` for `ValidationPipe` global config, `helmet` middleware, CORS
- `package.json` for `@nestjs/jwt`, `@nestjs/passport`, `passport-jwt`, `bcrypt` / `argon2`, `helmet`, `@nestjs/throttler`
- `.env.example` / config module for `JWT_SECRET`, `JWT_ALGORITHM`, allowed origins

**Express surface:**

- Every changed router / route file - look for auth middleware (`requireAuth`, `passport.authenticate`), validation middleware
- Every changed Zod schema or class-validator DTO with constraints
- `app.ts` / `server.ts` for `helmet`, `cors`, `express-rate-limit`, body-parser limits
- `package.json` for `helmet`, `cors`, `express-rate-limit`, `jsonwebtoken` / `jose`, `bcrypt` / `argon2`, `csurf` (deprecated - flag if present), `express-validator`
- `.env.example` / config for `JWT_SECRET`, allowed hosts, cookie config

When the diff removes a guard or relaxes auth middleware, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 4 - OWASP Triage (Node Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `Injection: yes`, `SSRF: yes`, `Insecure Design: no`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

The triage output funnels which downstream steps must run carefully versus which can be fast-passed. If a category shows no signal, explicitly state `No signal in diff` for that category in the Summary.

| Risk                          | Node-specific check                                                                                                                                                                                                                                          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | Every endpoint declares authorization explicitly. NestJS: `@UseGuards(AuthGuard('jwt'), RolesGuard)` + `@Roles(...)`. Express: route-level `requireAuth` + `requireRole(...)` middleware. Empty / missing is a finding.                                      |
| Injection                     | Prisma uses parameterized queries by default; raw via `prisma.$queryRaw`...${val}...`` is parameterized, but `prisma.$queryRawUnsafe(string)`is not. TypeORM`repository.query(sql, params)`parameterized;`createQueryBuilder`parameters via`:name`.          |
| Cryptographic Failures        | `bcrypt` (cost ≥ 10) or `argon2` for passwords. Never `crypto.createHash('md5')` / `'sha1'` for auth. JWT signing key from env, not hardcoded.                                                                                                               |
| Security Misconfiguration     | `helmet()` middleware applied; CORS origin allowlist (not `*` for credentialed); `NODE_ENV=production` in prod; debug routes / Swagger gated or disabled in prod.                                                                                            |
| SSRF                          | `fetch` / `axios.get` / `node-fetch` with user-controlled URL validates hostname against allowlist; rejects RFC1918, link-local, cloud metadata before request.                                                                                              |
| XSS                           | NestJS auto-escapes JSON responses; if rendering HTML, templating engine auto-escapes (Handlebars, EJS with `<%-` flagged); React server-rendering sanitizes by default. Express raw HTML responses inspected.                                               |
| Insecure Design (A04)         | Default-deny: NestJS `APP_GUARD` global guard requiring auth unless `@Public()`; Express equivalent: top-level `requireAuth` mounted before route registration.                                                                                              |
| Vulnerable Components (A06)   | `bun audit` / `npm audit` / `pnpm audit` clean for High/Critical; Renovate / Dependabot active. No pinned-but-stale package with known CVE.                                                                                                                  |
| Data Integrity Failures (A08) | `JSON.parse` on untrusted input bounded by body size; `eval` / `new Function(string)` flagged - any occurrence is a critical finding. `vm2` / `vm` modules with user input are RCE vectors. Prototype pollution: `Object.assign(target, userInput)` flagged. |
| Logging & Monitoring (A09)    | Logger does not log `password`, `token`, `authorization`, `cookie`. `class-transformer` `@Exclude()` for sensitive response fields. Auth events logged. Sentry `beforeSend` strips PII.                                                                      |

### Step 5 - Authentication

**NestJS:**

- [ ] **JWT signing**: HS256 secret in env / Vault, never committed. RS256 with key pair preferred for cross-service. `@nestjs/jwt` `JwtModule.register` uses `secretOrKeyProvider` for rotation, or static `secret` from env
- [ ] **`alg: none` rejected**: `passport-jwt` `JwtStrategy` declares `algorithms: ['HS256']` (or `['RS256']`) explicitly; never absent / undefined
- [ ] **JWT issuer / audience validated**: `issuer`, `audience` fields verified in `JwtStrategy` options; not just signature
- [ ] **Access token lifetime** short (5-15 min); refresh token rotation; refresh tokens revocable via DB / Redis denylist (track `jti` claim or refresh-token UUID)
- [ ] **Password hashing**: `bcrypt` `hash(password, 12)` (cost ≥ 10) or `argon2.hash(password)` (preferred for new code). Never plain `crypto.createHash`.
- [ ] **`AuthGuard('jwt')` wired correctly**: `JwtStrategy` exists, `tokenUrl` matches issuer, `auto_error` behavior on missing tokens returns 401
- [ ] **Brute-force protection**: `@nestjs/throttler` (`ThrottlerGuard`) on `/auth/login`, `/auth/refresh`, `/auth/reset-password`; configured stricter than global throttle
- [ ] **No `console.log(token)` / `logger.log(token)`** that leaks the JWT to logs

**Express:**

- [ ] **Password hashing**: `bcrypt` (cost ≥ 10) or `argon2`; flagged `crypto.createHash('sha256')` or homebrew hashing
- [ ] **JWT verification**: `jsonwebtoken.verify(token, key, { algorithms: ['HS256'] })` - the `algorithms` allowlist is **mandatory**; without it `jsonwebtoken` accepts `alg: none` for some token shapes
- [ ] **`jose` (preferred over `jsonwebtoken`)**: `jose.jwtVerify(token, key, { algorithms: ['HS256'], issuer, audience })` - more strict by default
- [ ] **Session cookies (when used)**: `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'` or `'strict'`, signed cookies via `cookie-parser` secret
- [ ] **Brute-force protection**: `express-rate-limit` per IP on auth routes; consider `rate-limiter-flexible` with Redis for multi-instance
- [ ] **Password reset tokens**: time-limited, single-use, hashed before storing in DB - never store the raw token

### Step 6 - Authorization

**NestJS:**

- [ ] **Authorization drift sweep**: every new endpoint added in the diff has a guard (`@UseGuards(AuthGuard('jwt'))` or stronger) - or the global `APP_GUARD` covers it and `@Public()` is not present
- [ ] **Role / permission checks** centralized in a guard (`RolesGuard`, `PoliciesGuard`) using `Reflector.getAllAndOverride` to read `@Roles(...)` metadata - not inline `if (user.role !== 'admin') throw new ForbiddenException()` scattered in handlers
- [ ] **IDOR**: lookups scope through the principal (`prisma.order.findFirst({ where: { id, ownerId: user.sub } })`) rather than `findUnique({ id })` then a separate ownership check
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenantId` at the repository / service layer (Prisma middleware or interceptor injecting `tenantId` into every query); not just at the controller
- [ ] **CORS**: `app.enableCors({ origin: [...] })` allowlist (not `'*'` for credentialed requests); methods and headers minimal
- [ ] **CSRF**: not required for stateless JWT-bearer APIs; required for cookie-session apps - confirm via auth model. `csurf` is deprecated (npm) - flag if present and recommend `csrf-csrf` or session-anti-CSRF token

**Express:**

- [ ] **Authorization middleware** declared per route or per router (`router.use(requireAuth)`); `requireRole(...)` for role-gated routes
- [ ] **Object-level authorization**: per-object checks live in the data layer or a dedicated authorize step - never `req.user.id === resource.ownerId` only at the controller surface (race conditions and easy to miss on new endpoints)
- [ ] **Default-deny**: top-level `app.use(requireAuth)` mounted before public routes are registered (or `requireAuth` opts in via per-router mounting); flagged endpoints with no auth middleware on them
- [ ] **CSRF**: same rules as NestJS; for cookie-session apps, use `csrf-csrf` or similar; `csurf` is deprecated

### Step 7 - Input Validation and Mass Assignment

**NestJS / class-validator + class-transformer:**

- [ ] **`ValidationPipe` global config**: `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` - `whitelist` strips unknown fields, `forbidNonWhitelisted` 400s on unknown fields, `transform` runs `class-transformer` so DTO types are real instances
- [ ] **Every `@Post` / `@Put` / `@Patch` controller method** declares a DTO class as the body parameter type - never `@Body() body: any` or unstructured `Record<string, unknown>`
- [ ] **Field constraints**: `@IsString()`, `@IsEmail()`, `@MinLength()`, `@MaxLength()`, `@Matches(/regex/)`, `@IsInt()`, `@Min()`, `@Max()` on every user-supplied field
- [ ] **No privilege-bearing fields in user-facing input DTOs**: `role`, `isAdmin`, `ownerId`, `userId`, `tenantId`, `isActive`, `verified` - server-set only. If present in `CreateOrderDto`, reject and require admin-only path with a separate DTO
- [ ] **`@Exclude()` on response models** strips internal fields (`passwordHash`, `internalNotes`); `ClassSerializerInterceptor` enforces it
- [ ] **`@Transform` on `id` / numeric fields** in path params: NestJS path params are strings by default - `@Param('id', ParseIntPipe)` or `@Transform` converts and validates

**Express / Zod or class-validator:**

- [ ] **Zod schemas for body, query, params**: `z.object({ ... })` with `.strict()` (rejects unknown fields - the Zod equivalent of `extra: 'forbid'`); validation middleware runs `schema.parse(req.body)` and 400s on failure
- [ ] **No `req.body` direct passthrough**: `await prisma.user.create({ data: req.body })` is mass-assignment - whitelist explicitly: `data: { name: parsed.name, email: parsed.email }`
- [ ] **`zod.strict()` (or `.passthrough()` documented)**: by default Zod silently strips unknown keys; for security-sensitive endpoints, prefer `.strict()` so unknown fields raise
- [ ] **express-validator** alternative: chain `.isString().isLength({...}).trim()` on every field; `validationResult(req).isEmpty()` checked at the top of every handler

**Both:**

- [ ] **File uploads**:
  - File type validated by content (`file-type` package, magic-byte detection), not just `mimetype` header (client-controlled) or extension
  - Per-file size limit enforced (`multer({ limits: { fileSize: 5 * 1024 * 1024 } })` + `app.use(express.json({ limit: '100kb' }))`)
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized via `path.resolve(base, name).startsWith(base)` check before write; reject directory traversal
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `path.resolve(baseDir, userInput)` followed by `startsWith(baseDir)` check; never `path.join(baseDir, userInput)` without normalization
- [ ] **Process execution**: `child_process.execFile([...args])` with arg array (not `exec(string)` and not `exec(`... ${userInput} ...`)`); strict allowlist of allowed binaries; never `shell: true` with user input

### Step 8 - Common Node.js Vulnerability Patterns

- [ ] **Prototype pollution**: `Object.assign(target, JSON.parse(userInput))`, `_.merge(...)` on user input, `Object.assign({}, defaults, req.query)` are prototype-pollution vectors. Use `Object.create(null)` for trusted-prototype maps; `lodash.merge` is unsafe - use `lodash.mergeWith` with a sanitizer or switch to `defu` / Object spread
- [ ] **`eval` / `new Function(string)` / `vm.runInNewContext(string)`** on user input - any occurrence is a critical finding regardless of "controlled" framing. `vm2` is deprecated (CVEs) - flag if present
- [ ] **`JSON.parse` on untrusted bounded** by body-parser limit (`express.json({ limit: '100kb' })` or NestJS platform default); unbounded parsing is a DoS surface
- [ ] **`require(userInput)` / dynamic `import(userInput)`** - arbitrary module loading is RCE
- [ ] **`fs.writeFile(userInput, content)` / `fs.unlink(userInput)`** without path-base check - file system tampering
- [ ] **HTTP client with `verify: false` / `rejectUnauthorized: false`**: `https.request({ rejectUnauthorized: false })` flagged unless behind a documented test fixture; `axios.create({ httpsAgent: new https.Agent({ rejectUnauthorized: false }) })` similarly
- [ ] **Open redirect**: `res.redirect(userInput)` validated against an allowlist or relative-path-only check (`url.startsWith('/') && !url.startsWith('//')`)
- [ ] **SQL injection via raw query**: `prisma.$queryRawUnsafe(`SELECT ... ${userInput}`)` - flagged as critical; `repository.query(`... ${userInput}`)` (TypeORM) similarly. Use tagged template (`prisma.$queryRaw`...${val}...``) or `:param` placeholders
- [ ] **Server-side template injection**: rendering Handlebars / EJS / Nunjucks with user-controlled template strings is RCE; templates must come from disk
- [ ] **`JWT_SECRET` / signing key** sourced from env / Vault, never committed; rotated when leaked
- [ ] **Debug exposure**: NestJS Swagger UI (`SwaggerModule.setup`) gated behind auth in prod, or skipped (`if (process.env.NODE_ENV !== 'production') SwaggerModule.setup(...)`); Express `debug` namespace patterns reviewed
- [ ] **SSRF depth**: when a user-controlled value flows into an outbound URL or hostname, the allowlist must reject (a) cloud metadata IP `169.254.169.254` and IPv6 equivalent `fd00:ec2::254`, (b) localhost / `127.0.0.0/8` / `::1`, (c) private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve the host **after** parsing (DNS rebinding bypasses string-only allowlists - re-resolve at request time and re-check). `URL` constructor quirks: backslash, unicode normalization, IPv4-in-IPv6 (`::ffff:127.0.0.1`) all defeat naive checks.
- [ ] **BullMQ job payload**: jobs serialize to JSON in Redis; worker `JSON.parse(payload)` on input from any source that can publish to the queue is implicit trust. If the queue is reachable from untrusted inputs (webhook → queue), validate with Zod / class-validator inside the processor before acting on payload fields
- [ ] **ReDoS via user-supplied regex**: `@Matches(new RegExp(userInput))` / `z.string().regex(new RegExp(userInput))` constructed from user input or config-driven patterns can hang the event loop on adversarial inputs. Compile patterns once at module load; never accept patterns from request bodies; consider `safe-regex` to detect catastrophic-backtracking patterns at review time
- [ ] **HTTP request smuggling / desync** (Node behind nginx / ALB): Node 18+ HTTP parser is stricter; flag custom HTTP/1.1 parsing or proxy / forwarder middleware that re-emits headers without validation
- [ ] **Webhook signature verification**: Stripe / GitHub / Slack webhooks - signature verified via `crypto.timingSafeEqual` (not `===` - timing attack). `bodyParser.raw` used to access raw bytes (signed payload), not parsed JSON

### Step 9 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (`crypto.subtle` AES-GCM, AWS KMS / GCP KMS for key management, or DB-native column encryption)
- [ ] **Logging filter** masks sensitive keys (`password`, `token`, `creditCard`, `ssn`, `apiKey`); `pino` `redact: ['password', 'token']` or `winston` custom format strips them; `class-transformer` `@Exclude()` reinforces
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit logs, browser history, referer headers
- [ ] **TLS enforcement**: HTTPS-only at LB; HSTS via `helmet.hsts({ maxAge: 31536000 })`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars from a secret store (Vault / AWS Secrets Manager / GCP Secret Manager / Doppler), never `.env` committed; `.env` gitignored; `process.env.JWT_SECRET` accessed via typed config service (`@nestjs/config` `ConfigService`) so missing-at-startup fails fast


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (NestJS body / query / params, Express body, BullMQ job payloads, external API responses, webhook payloads)
- Never disable guards or validation pipes to silence a failing test - fix the test
- Never widen authorization (e.g., `@Public()` on a previously-protected route, removing `requireAuth` middleware) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny via global guard / top-level middleware

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as Node.js / TypeScript; framework (NestJS / Express / mixed) recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (auth strategies / guards / middleware, settings, changed routers / controllers, DTOs / schemas) read directly before applying checklists; prior revision consulted when guards or auth middleware were removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new endpoint in the diff has a matching guard or auth middleware
- [ ] DTO / Zod validation reviewed; mass-assignment fields, `@Exclude()` / `whitelist` / `.strict()` confirmed for changed schemas
- [ ] File upload, path traversal, and process-execution checks run if the diff touches uploads / file paths / `child_process`
- [ ] Prototype pollution, `eval` / `new Function`, raw SQL, dynamic `require` / `import`, `rejectUnauthorized: false`, open redirect checked when the diff touches them
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for test-coverage gaps), or "topology-dependent" framing (for infra-flavored findings) - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Authentication step run for the auth mechanism in use (NestJS JWT / Passport or Express session / `jose`) - applies when the auth module is in scope
- [ ] CORS, rate limiting, helmet, debug exposure verified - applies when middleware / config are in scope
- [ ] Password hashing config reviewed (bcrypt cost ≥ 10, argon2 preferred) - skip if hashing config not in diff
- [ ] Sentry `beforeSend` strips PII - skip if Sentry init module not in diff
- [ ] `bun audit` / `npm audit` clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Node.js Security Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**Auth:** JWT (jsonwebtoken) | JWT (jose) | NestJS Passport JWT | NestJS Passport Local | Session (cookie) | Custom | Hybrid
**Authorization:** NestJS Guards | Express middleware | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Node-specific risks like missing `whitelist: true` on `ValidationPipe`, prototype pollution from `Object.assign(target, req.body)`, exposed Swagger in prod, or `csurf` deprecated dependency.]

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
- **Issue:** [vulnerability described in Node terms - e.g., "CreateOrderDto lacks `whitelist: true` enforcement; client can submit `{ ownerId: 999 }` and override the server-assigned owner via mass assignment because `ValidationPipe` config in app.module.ts is missing `forbidNonWhitelisted`"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" — for test-coverage / monitoring gaps; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto correctly" — for infra-flavored findings. Pick one and label which. Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific Node remediation with code example - `ValidationPipe` config, `@Exclude()`, `@UseGuards(AuthGuard('jwt'))`, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `@nestjs/throttler` rate limit on /auth/login", "Migrate from jsonwebtoken to jose (stricter defaults)", "Move JWT_SECRET from .env literal to Vault"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Add `forbidNonWhitelisted: true, whitelist: true` to ValidationPipe in app.module.ts; remove `ownerId` from CreateOrderDto"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `bun audit` / `npm audit` and upgrade flagged packages - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"admin\"}` and gains admin via mass assignment because `ValidationPipe` is missing `whitelist: true`")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Node idiom applies (say "add `@UseGuards(AuthGuard('jwt'))`", not "add an authorization check")
- Suggesting `csurf` as a CSRF fix - it is deprecated; recommend `csrf-csrf` or session-anti-CSRF token
- Suggesting `@Public()` decorator as a fix for a failing auth-required test - validate the test sends a token instead
- Disabling guards / `ValidationPipe` to silence a failing test - fix the test
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Recommending `algorithms: undefined` / unspecified for `jsonwebtoken.verify` - explicit allowlist is the only safe form
- Recommending `eval` / `new Function` / `vm` modules / `vm2` as acceptable on any input not under full server control
- Approving `rejectUnauthorized: false` on TLS clients outside test fixtures
- Approving exposed Swagger UI / `/api-docs` in any non-dev profile
- Recommending `lodash.merge(target, req.body)` for "merging defaults" - prototype pollution vector; use `Object.create(null)` or sanitize keys
