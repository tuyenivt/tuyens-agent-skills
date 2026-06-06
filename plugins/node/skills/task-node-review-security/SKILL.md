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

**Not for:** performance (`task-node-review-perf`), general review (`task-node-review`), incident triage (`/task-oncall-start`).

**Depth.** Always full. Security has cliff-edged consequences (auth bypass, RCE); scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauth RCE, auth bypass, mass exfiltration, working SQLi, secrets/signing keys in source, prototype pollution reaching privileged path. Blocks merge.   |
| **High**     | Authenticated priv-esc, IDOR on sensitive data, SSRF to metadata/internal, mass assignment of privilege fields, missing authz on user-data endpoints.   |
| **Medium**   | Hardening gap with mitigating control elsewhere, missing field constraints, weak rate limit on non-critical endpoint, debug exposure on non-prod.       |
| **Low**      | Defense-in-depth, dependency advisory below actively-exploited threshold, hardening without concrete current attack.                                    |

## Invocation

Mirrors `task-code-review-security`:

| Invocation                            | Meaning                                                                       |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| `/task-node-review-security`          | Current branch vs base; fails fast on trunk                                   |
| `/task-node-review-security <branch>` | `<branch>` vs its base (3-dot)                                                |
| `/task-node-review-security pr-<N>`   | PR head in local branch `pr-<N>` (user fetches first)                         |

When invoked as a subagent of `task-code-review-security`, Step 2 is skipped and pre-read artifacts are reused.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked as a delegate (parent already detected), accept pre-confirmed stack. If not Node, stop and route to `/task-code-review-security`.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express. Record `Framework: NestJS | Express | mixed`. Steps branch on this where idioms differ.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely as a subagent when parent passes the handle.

If `review-precondition-check` fails fast, surface verbatim and stop. Never run state-changing git from this workflow.

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

Triage pass only. One verdict per category (`yes` / `no signal in diff`). Findings go in Steps 5-9; do not duplicate here.

| Risk                          | Node-specific check                                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every endpoint declares authz: `@UseGuards(AuthGuard('jwt'), RolesGuard)` + `@Roles(...)` or route-level `requireAuth` + `requireRole`. Empty = finding.  |
| Injection                     | Prisma raw via tagged template `$queryRaw` parameterized; `$queryRawUnsafe(string)` not. TypeORM `repository.query(sql, params)` or QB `:name` params.    |
| Cryptographic Failures        | `bcrypt` (cost >=10) or `argon2`. Never `md5`/`sha1` for auth. JWT signing key from env, not hardcoded.                                                   |
| Security Misconfiguration     | `helmet()` applied; CORS origin allowlist (not `*` for credentialed); Swagger gated/disabled in prod.                                                     |
| SSRF                          | `fetch`/`axios` with user-controlled URL validates host against allowlist; rejects RFC1918, link-local, metadata pre-request.                             |
| XSS                           | NestJS auto-escapes JSON; Handlebars/EJS `<%-` flagged; Express raw HTML inspected.                                                                       |
| Insecure Design               | Default-deny: NestJS `APP_GUARD` global; Express top-level `requireAuth` before route registration.                                                       |
| Vulnerable Components         | `npm/pnpm/bun audit` clean for High/Critical; Renovate/Dependabot active.                                                                                 |
| Data Integrity Failures       | `eval` / `new Function` / `vm2` flagged - any occurrence critical. `Object.assign(target, userInput)` = prototype pollution.                              |
| Logging & Monitoring          | Logger never logs `password`/`token`/`authorization`/`cookie`. `@Exclude()` on sensitive fields. Sentry `beforeSend` strips PII.                          |

### Step 5 - Authentication

**Both frameworks:**

- [ ] **Password hashing**: `bcrypt` cost >=10 or `argon2`; flag `crypto.createHash('sha256'/'md5')` or homebrew
- [ ] **Brute-force protection**: rate limit on `/auth/login`, `/refresh`, `/reset-password` (NestJS `@nestjs/throttler`; Express `express-rate-limit` or `rate-limiter-flexible` + Redis for multi-instance)
- [ ] **Password reset tokens**: time-limited, single-use, hashed before storage
- [ ] **No JWT in logs**

**NestJS:**

- [ ] **JWT signing**: HS256 secret in env/Vault; RS256 key pair preferred cross-service; `JwtModule.register` uses `secretOrKeyProvider` for rotation
- [ ] **`alg: none` rejected**: `JwtStrategy` declares `algorithms: ['HS256']` (or `['RS256']`) explicitly
- [ ] **`issuer` / `audience`** verified in `JwtStrategy` options, not just signature
- [ ] **Access token lifetime** short (5-15 min); refresh rotation with revocable denylist (track `jti` in DB/Redis)
- [ ] **`AuthGuard('jwt')` wired correctly**: missing-token returns 401

**Express:**

- [ ] **JWT verification**: `jsonwebtoken.verify(token, key, { algorithms: ['HS256'] })` - allowlist **mandatory**; without it some token shapes accept `alg: none`. Prefer `jose.jwtVerify(token, key, { algorithms, issuer, audience })` (stricter defaults)
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
- [ ] **`@Exclude()` on response models** for `passwordHash` etc.; `ClassSerializerInterceptor` enforces
- [ ] **`ParseIntPipe`/`@Transform`** on numeric path params (default string)

**Express (Zod or class-validator):**

- [ ] **Zod schemas** for body/query/params with `.strict()` (rejects unknown); validation middleware 400s on failure
- [ ] **No `req.body` passthrough**: `prisma.user.create({ data: req.body })` is mass-assignment - whitelist: `data: { name: parsed.name, email: parsed.email }`
- [ ] **`.strict()` (or documented `.passthrough()`)**: Zod silently strips unknown by default; prefer `.strict()` for security-sensitive
- [ ] **express-validator** alternative: `validationResult(req).isEmpty()` checked at top of every handler

**Both:**

- [ ] **File uploads**: type by content (`file-type` magic bytes), not `mimetype` header; per-file size limit (`multer({ limits: { fileSize: ... } })`); stored outside webroot, `Content-Disposition: attachment` on serve; filename sanitized (`path.resolve(base, name).startsWith(base)`); virus scan or accepted-risk documented
- [ ] **Path traversal**: `path.resolve(baseDir, userInput)` + `startsWith(baseDir)` check; never `path.join` without normalization
- [ ] **Process exec**: `child_process.execFile([...args])` arg array, never `exec(string)` or `exec(\`... ${userInput} ...\`)`; allowlist binaries; never `shell: true` with user input

### Step 8 - Common Node.js Vulnerability Patterns

Canonical "build it right" patterns: Use skill: `node-security-patterns` (JWT signing/verify, mass-assignment DTOs, prototype pollution, SSRF allowlist, file upload, webhook signatures, secrets, `eval`/`vm` prohibitions, open redirect, `child_process.execFile`, TLS). This step flags deviations.

Surface-specific extras not covered by the atomic:

- [ ] **`JSON.parse` bounded** by body-parser limit (`express.json({ limit: '100kb' })`); unbounded = DoS
- [ ] **`require(userInput)` / dynamic `import(userInput)`** = RCE (delegate canonical handling to `node-security-patterns`)
- [ ] **`fs.writeFile`/`fs.unlink` with user input** without path-base check = FS tampering
- [ ] **Raw SQL injection**: `$queryRawUnsafe(\`...${userInput}\`)` (Prisma) or `repository.query(\`...${userInput}\`)` (TypeORM) = critical. Use tagged template or `:param`
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

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled review to file and print the confirmation line.

## Output Format

```markdown
## Node.js Security Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**Auth:** JWT (jsonwebtoken) | JWT (jose) | NestJS Passport JWT | NestJS Passport Local | Session (cookie) | Custom | Hybrid
**Authorization:** NestJS Guards | Express middleware | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment calling out Node-specific risks: missing `whitelist: true`, prototype pollution from `Object.assign(target, req.body)`, exposed Swagger in prod, `csurf` dep.]

## OWASP Triage

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

- **Location:** [file:line]
- **Issue:** [vulnerability in Node terms - e.g., "CreateOrderDto lacks `whitelist: true`; client submits `{ ownerId: 999 }` and overrides server-assigned owner via mass assignment"]
- **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: ..." for test/monitoring gaps; (c) "Topology-dependent: ..." for infra-flavored. Do NOT invent exploits when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [specific Node remediation with code - `ValidationPipe` config, `@Exclude()`, `@UseGuards(AuthGuard('jwt'))`, etc.]

### High / Medium / Low

[Same structure. Omit sections with no findings. If all omitted, state "No security issues found."]

## Recommendations

[Prioritized hardening not tied to a specific finding - e.g., "Add `@nestjs/throttler` on /auth/login", "Migrate from jsonwebtoken to jose", "Move JWT_SECRET to Vault"]

## Next Steps

Tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting hardening, dependency upgrade, threat model). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Omit if no security issues found._
```

## Self-Check

- [ ] Stack confirmed; framework recorded; diff + log read once; prior revision consulted when guards/auth middleware removed (Steps 1-3)
- [ ] OWASP triage: one verdict per category; findings not duplicated (Step 4)
- [ ] Authn / authz drift sweep covered every new endpoint (Steps 5-6)
- [ ] DTO / Zod validation, mass-assignment fields, `@Exclude()` / `whitelist` / `.strict()` confirmed (Step 7)
- [ ] When touched: file upload, path traversal, exec, prototype pollution, `eval`, raw SQL, dynamic require, `rejectUnauthorized: false`, open redirect (Step 8)
- [ ] Severity rubric applied consistently; every finding has attack scenario, regression-risk, or topology-dependent framing
- [ ] Infra-scope items (CORS, rate limiting, helmet, debug exposure, hashing config, Sentry `beforeSend`, `npm audit`) noted as "could not verify from diff alone - flag for separate audit" when not visible
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend > Question
- [ ] Report written via `review-report-writer`; confirmation printed (Step 10)

## Avoid

- Running state-changing git from this workflow (user runs fetches/checkouts)
- Reporting vulnerabilities without an attack scenario - "input not validated" vs "attacker submits `{role:'admin'}` and gains admin via mass assignment because `whitelist: true` is missing"
- Skipping clean OWASP categories - explicitly state `no signal in diff`
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
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
