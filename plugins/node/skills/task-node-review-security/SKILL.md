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

Stack-specific delegate of `task-code-review-security`. Names NestJS Guards / Passport / `@nestjs/jwt`, `ValidationPipe` + class-validator / Zod, Express middleware auth, ORM parameterization, and Node-specific risks (prototype pollution, ReDoS, SSRF, RCE via `eval` / `vm`) directly.

## When to Use

- NestJS or Express PR security regression review
- Pre-deploy hardening pass on auth, authz, upload, payment, or PII paths
- Periodic guard / validation drift sweep, or a JWT / Passport flow audit (audit mode, below)

**Not for:** performance (`task-node-review-perf`), general review (`task-node-review`).

**Depth.** This lens always runs every step - security consequences are cliff-edged, so it scopes by file, not by depth. A depth argument changes nothing that runs; the writer records `depth: deep`.

## Severity Rubric

| Severity | Definition |
| -------- | ---------- |
| **Critical** | RCE reachable from any caller's input (`eval` / `new Function` / `vm` / `exec(string)`), auth bypass, mass exfiltration, working SQL / NoSQL injection, prototype pollution reaching a privileged path, path traversal to an arbitrary file write or (unauthenticated) read. Blocks merge. |
| **High** | Authenticated privilege escalation; IDOR or a missing object check on sensitive data - including one that lets a caller write to or move money for another user or tenant; SSRF to metadata or internal addresses; mass assignment of a privilege field; missing authz on a user-data endpoint; no brute-force control on a credential endpoint; a race, replay, or duplicate run (caller-triggered or system-driven) that spends or moves money twice; an unverified or unauthenticated webhook that changes state; a signing key or credential committed to the repo; passwords under a fast or unsalted hash; path traversal to an arbitrary read behind authentication; CSRF on a state change; stored XSS; credentialed origin reflection; secrets or tokens written to logs. |
| **Medium** | Hardening gap with a mitigating control elsewhere, missing field constraints, weak rate limit on a non-credential endpoint, reflected XSS, open redirect, ReDoS, stack traces or Swagger exposed in production, debug exposure outside production. |
| **Low** | Defense in depth, a dependency advisory below the actively-exploited threshold, hardening with no concrete attack path. |

When exploitation needs two independent preconditions, rate one tier lower; firing concurrent requests is one precondition, not two. A missing brute-force control on a credential endpoint and an unverified state-changing webhook sit one tier above `task-code-review-security` because both are exploitable here with no second precondition. Summary counts are by tier.

## Invocation

`/task-node-review-security [<branch> | pr-<N>] [--base <branch>] [audit <surface>]`

Defaults to the current branch vs its base; fails fast on trunk. A trailing `standard | deep` is accepted and ignored. `task-code-review-security` dispatches here as a standalone run. `task-node-review` spawns this workflow as its `+Sec` subagent: Step 3 is pre-satisfied and Step 11 takes its subagent branch.

**Audit mode** - decided before Step 3: the request asks for a drift sweep or flow audit with no PR, or says `audit`. A bare invocation on trunk is not an audit - Step 3 runs and fails fast. Scope is the named surface, read as the code that implements it: an authz / validation sweep covers every router or controller plus the guards, middleware, and DTOs / schemas they use; a flow audit covers credential issuance and verification (auth module, strategies, guards, login / refresh / reset handlers). Run Steps 4-10 against current code read via `git show HEAD:<path>`; every "diff" wording reads "the resolved surface", and a step with no matching surface states its skip. Tiers keep their meaning as fix priority. No precondition check, no round gate, no writer: Step 10 verifies inline and the report body is the response. Summary `Target:` names the surface.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`; accept a pre-confirmed stack from a parent. Not Node -> stop and route to `/task-code-review-security`. Record `Framework` (NestJS, Express, `mixed` - each app's files under its own idioms - or `other` (Fastify, Koa, Hono): the Express middleware checks at its equivalent sites) and `ORM` (Prisma, TypeORM, both - each file under its own ORM's idiom - or `other` / `none`); steps branch on both.

### Step 3 - Resolve the Diff (standalone only)

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-security`. A fail-fast surfaces verbatim and stops. Audit mode is decided from the invocation before this step and never runs it, so a precondition failure never routes there.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading anything else: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` is `deep` -> print `No new commits on <head_short_name> since prior security review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `head_sha`) and stop. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 11 write overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then read once: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log --oneline <base_ref>..<head_ref>`.

### Step 4 - Read the Security Surface

**The reviewable surface is the repo at `head_ref`, not the diff.** Read with `git show <head_ref>:<path>` (audit mode: `HEAD`), whether or not the file changed:

- **Guards / middleware:** every `@UseGuards(...)` and its implementation, `APP_GUARD` registrations, `@Public()` metadata handling; Express `requireAuth` / `passport.authenticate` and where they mount
- **Strategies / config:** `jwt.strategy.ts`, `auth.module.ts`; `main.ts` / `app.ts` for `helmet`, CORS, rate limiting, body limits, the global `ValidationPipe`
- **Validation:** DTOs, Zod schemas, the validation middleware
- **Changed routes** and anything a changed route calls into (services, repositories) - one hop, plus the data layer where authorization is enforced
- **Dependencies:** `package.json` and the lockfile
- **Secrets:** the config module and schema, `.env.example`

When the diff removes a guard or relaxes auth, read the base side (`git show <base_ref>:<path>`) to confirm what was protected.

A control the run cannot confirm goes in `## Not verifiable`: a file absent at `head_ref`, outside the checkout a parent handed over, or unreadable in this environment; or a check that needs a tool the run cannot execute (`pnpm audit`). A file that merely sits outside the diff is never not-verifiable - read it.

### Step 5 - OWASP Triage

Triage only; findings are raised in Steps 6-10, never duplicated here. One verdict per category: `finding` (Steps 6-10 raise it), `clean` (the diff exercises the category and the control is correct - name it), `no signal in diff` (neither exercised nor affected), `not verifiable` (depends on a control in `## Not verifiable`). `clean` is what a well-built PR earns; `no signal` on a diff that visibly adds two guards is false. Each finding homes under its most specific category.

| Category (OWASP Top 10:2025) | Node check |
| ---------------------------- | ---------- |
| A01 Broken Access Control | Every endpoint declares authz (`@UseGuards` + `@Roles`, a global `APP_GUARD` without `@Public()`, or `requireAuth` + `requireRole`); object and tenant scope in the query; SSRF - outbound URLs from user input |
| A02 Security Misconfiguration | `helmet()`; CORS allowlist, never reflecting the request origin with credentials; Swagger / `/api-docs` gated or absent in production; error responses leak no stack or internals |
| A03 Software Supply Chain Failures | Dependency and lockfile changes checked for advisories; `csurf` (deprecated) or an unmaintained sandbox (`vm2`) flagged; CI / build integrity when touched |
| A04 Cryptographic Failures | `argon2id` or `bcrypt` for passwords, never a bare fast hash (md5 / sha1 / sha256); keys from config, not source; TLS enforced |
| A05 Injection | Prisma tagged `$queryRaw` / `$executeRaw` and `...Unsafe(sql, ...values)` bind, while an interpolated string passed to `$queryRawUnsafe` / `$executeRawUnsafe`, or `Prisma.raw(input)`, does not; TypeORM `repository.query(sql, [params])` binds positionally, `:name` is QueryBuilder-only; no `exec(string)`; `eval` / `new Function` / `vm` on input; XSS - EJS `<%-`, Handlebars `{{{ }}}` / `SafeString`, Nunjucks `\| safe`; JSON is safe only as `application/json` with `nosniff` |
| A06 Insecure Design | Default-deny (`APP_GUARD` global, or `requireAuth` mounted before the routers); rate limits on credential and costly endpoints |
| A07 Authentication Failures | JWT verification (algorithms, issuer, audience, expiry); session cookie flags; CSRF for cookie-carried credentials; no credential in the repo |
| A08 Software or Data Integrity Failures | Webhook signatures over the raw body; mass assignment; prototype pollution; unsafe deserialization |
| A09 Logging and Alerting Failures | No password / token / authorization / cookie in logs; auth failures logged |
| A10 Mishandling of Exceptional Conditions | No fail-open: a guard whose `catch` returns `true`, an exception filter that answers 200, a verification error treated as success |

### Step 6 - Authentication

- [ ] **Password hashing** - `argon2id`, or `bcrypt` cost >= 10 (it truncates input at 72 bytes); a missing user still runs a dummy compare so timing does not enumerate accounts
- [ ] **Brute-force control** on `/auth/login`, `/refresh`, `/reset-password` - `@nestjs/throttler` with a Redis storage, or `express-rate-limit` / `rate-limiter-flexible`, each with a shared store across instances (the default in-memory store allows N times the limit on N replicas)
- [ ] **Reset tokens** time-limited, single-use, stored hashed
- [ ] **JWT verification** - an explicit `algorithms` allowlist, unconditionally (`JwtStrategy` `algorithms`, `JwtModule` `verifyOptions: { algorithms }` for `JwtService.verify` / `verifyAsync`, `jsonwebtoken.verify(token, key, { algorithms })`): defense in depth across libraries and versions (jsonwebtoken <= 8, custom verifiers, mixed-key JWKS); `jose.jwtVerify(token, key, { algorithms, issuer, audience })` preferred. `issuer` / `audience` verified, not just the signature. RS256 whenever another service verifies; HS256 secrets from config
- [ ] **Token lifetime** short (5-15 min access); refresh rotation with revocation (`jti` tracked)
- [ ] **Missing token returns 401** through the real guard path
- [ ] **Session cookies** (Express) - `httpOnly`, `secure` in production, `sameSite`, signed

### Step 7 - Authorization

- [ ] **Authz drift sweep** - every new or changed endpoint has a guard / middleware, or a global `APP_GUARD` covers it with no `@Public()`; Express mounts `requireAuth` before the routers it protects, and a route registered before it is public
- [ ] **Roles centralized** - `RolesGuard` reading `@Roles(...)` via `Reflector.getAllAndOverride`, not inline `if (user.role !== 'admin')` scattered in handlers
- [ ] **Object and tenant scope in the query** - `findFirst` / `findUnique({ where: { id, tenantId: user.tenantId } })`; a load followed by a missing or wrong ownership check is the finding. Tenant scoping in the data layer (a Prisma client extension via `$extends`, a TypeORM scoped repository or query helper), not controllers alone
- [ ] **CSRF** - required whenever the browser sends the credential automatically (session cookie, or a JWT kept in a cookie); not for `Authorization: Bearer`. `csurf` is deprecated - `csrf-csrf`
- [ ] **CORS** - explicit origin allowlist; never reflect the request origin (`origin: true`, a permissive callback or unanchored regex) with `credentials: true`

### Step 8 - Input Validation and Mass Assignment

- [ ] **NestJS** - a global `ValidationPipe` (in `main.ts` or as `APP_PIPE`) with `whitelist: true` and `forbidNonWhitelisted: true`; every `@Body()` typed by a DTO class, never `any` / `Record<string, unknown>`; field constraints on every user-supplied field; nested DTOs carry `@ValidateNested()` + `@Type(() => ChildDto)` (`{ each: true }` on arrays) or `whitelist` never reaches them; numeric params through `ParseIntPipe`
- [ ] **Express** - Zod (or equivalent) on body, query, and params; the **parse result** flows onward, never `req.body` (`z.object()` strips unknown keys, so the vector is passing `req.body`); `.strict()` / `z.strictObject()` on write schemas; `.passthrough()` / `z.looseObject()` never on a write path
- [ ] **Privilege fields are a class, not a list** - any field the server assigns (ownership, tenancy, role, entitlement, price, status, requested-by) never comes from input; an admin path uses its own DTO. A spread of a DTO or `req.body` into `create` / `update` is mass assignment
- [ ] **Sensitive columns never reach the wire** - a Prisma result is a plain object, so `@Exclude()` does nothing there: project with `select` / `omit`, or `plainToInstance(Dto, row, { excludeExtraneousValues: true })` with `@Expose()` per field
- [ ] **File uploads** - type by content (`file-type` magic bytes), per-file size limits (`multer({ limits })`, `FileInterceptor` options), stored outside the web root, served with `Content-Disposition: attachment`
- [ ] **Path traversal** - `path.resolve(base, input)` then `startsWith(base + path.sep)`; `path.join` normalizes but does not constrain
- [ ] **Process exec** - `execFile('/abs/bin', [...args])` with an allowlisted binary; never `exec(string)` or `shell: true` with user input

### Step 9 - Node Vulnerability Patterns

Use skill: `node-security-patterns` (JWT, object-level authorization, mass-assignment DTOs, prototype pollution, SSRF guard, uploads, webhook signatures, secrets, `eval` / `vm`, injection, open redirect, `child_process`, TLS, password storage, error disclosure, CSRF). Flag deviations from it; the extras it does not cover:

- [ ] **Body limits** - body-parser defaults every parser (`json`, `raw`, `text`, `urlencoded`) to `100kb`; the finding is a raised `limit` or `Infinity`
- [ ] **ReDoS** - a pattern built at runtime from input (`new RegExp(req.query.q)`), or a catastrophic literal applied to unbounded input; `re2` for user-supplied patterns
- [ ] **SSTI** - templates from disk only, never a user-controlled template string
- [ ] **BullMQ payloads** validated inside the processor when the queue is reachable from untrusted input
- [ ] **Swagger** skipped or auth-gated in production

### Step 10 - Data Protection and Verification

- [ ] **Log redaction** in the logger itself - `pino` `redact: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token']` (a leading `*` matches one level: list nested paths such as `req.body.password`) or a winston format; class-transformer decorators do nothing for a logger
- [ ] **PII at rest** encrypted where required; no sensitive data in URLs
- [ ] **TLS / HSTS** - `helmet()` sends HSTS by default; flag only when it is disabled or `maxAge` lowered
- [ ] **Secrets** from a secret manager or env through a validated config module that fails fast at startup; `.env` ignored by git

**One construct, one finding.** A construct carrying several defects (a handler that is both unauthorized and mass-assignable) files once at the worst tier, naming the others in its Issue and numbering the fixes. When an exploit chains two constructs, file it once where the fix lands and name the other in the attack scenario. **A defect this lens does not own is reported, never dropped:** one `- **out of lens:** file:line - <the defect, and the workflow that owns it>` line per defect, at the end of `## Findings`, for a defect outside this lens that would break the build, corrupt, lose, or expose data, or block legitimate traffic (anything else is left to `task-node-review`), untiered and uncounted; a control that fails closed (it blocks legitimate traffic, opens no exploit) is one. On standalone and audit runs, each also gets a `[Delegate]` Next Step naming the owning workflow. Security-adjacent correctness bugs (a broken comparison, a double body read) stay here.

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying the `Label` and `Annotation` columns, and fill `Findings verified:` in the atomic's Summary form. Subagent runs skip it - the parent verifies the merged set. Audit mode skips it too: re-read each cited `file:line` at `HEAD`, drop what the code contradicts, mark what cannot be settled in-tree `_(unverified: <reason>)_`, and report `Findings verified: inline (no diff)`.

**Round 2+ (standalone, after verification).** Project the prior report at the handle's `report_path` into reconcile's parse shape: one `## High-Impact Findings` section, and per prior finding (every tier) a `### [<Label>] <file:line>` heading - the label from its bold `[Must]` / `[Recommend]` token (a prior report with none: the label its tier maps to), the `file:line` prefix of its Location, each Location annotation as its own group (`_(pre-existing; newly reachable via ...)_` split into `_(pre-existing)_ _(newly reachable via ...)_`), a prior `_(carried from round <N>)_` kept - followed by its Issue line as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files`. Its table, note line, and tally render as `## Prior Round Reconciliation`. A row is re-derived when this round's findings hold one on the same construct with the same smell. A `Still open` or `Needs re-check` row this round re-derived publishes once, at this round's label; one it did not re-derive republishes its prior block verbatim in its prior tier - every field, the Location with all its annotation groups - at its prior label, with `_(carried from round <N>)_` after the label unless the block already carries one (`<N>` = the round it first appeared), outside the verify tally, plus a Next Steps entry suffixed `(open since round <N>)`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` is never carried.

### Step 11 - Write Report

**Subagent mode** (invoked by `task-node-review`): return only `## Findings` with its tier sections and any `out of lens` lines, plus `## Not verifiable` when it has an entry. No Summary, OWASP table, Recommendations, Next Steps, or file; the parent owns the report. This supersedes any generic "return your Output Format" in the parent's prompt.

**Audit mode:** emit the report body as the response; no writer.

**Standalone:** Use skill: `review-report-writer` with `report_type: review-security`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the round gate, `scope: +sec`, `depth: deep`, `stack = node-typescript`, `mode: full`, `round` and `prior_head_sha` from the round gate, and `pr_url` when the request carried one, else `prior_checkpoint.pr_url` when present. Emit the body, then the writer's confirmation line.

## Output Format

Emit `report_body` as raw Markdown; the fence delimits the template for display only, and brace annotations in it are authoring notes, never emitted.

**Labels.** Critical / High -> `[Must]`; Medium / Low -> `[Recommend]` - unless the verify pass returned a different `Label`, which wins: a finding sits in its tier's section while its label is the published one. No other label is written. Every finding carries an attack scenario framed as one of: a concrete exploit walkthrough; `Regression risk: ...` for a test or monitoring gap; `Topology-dependent: ...` for an infrastructure-conditioned risk; `Latent: ...` for vulnerable code not yet reachable - never an invented exploit. Several fixes on one construct are a numbered list inside `Fix:`.

**Envelope precedence.** `node-security-patterns` feeds findings into this template under this rubric; its own block is not emitted.

```markdown
## Node.js Security Review Summary

- **Stack:** Node.js <version> / TypeScript <version> / <NestJS | Express | mixed | other> / <Prisma | TypeORM | Prisma + TypeORM | other | none>
- **Target:** <base_ref>...<head_ref> | <the audited surface at HEAD>
- **Round:** <N>   {round 2+ only}
- **Auth:** JWT (jsonwebtoken) | JWT (jose) | NestJS Passport JWT | Passport Local | Session (cookie) | Custom | Hybrid | None (internal / network-gated)
- **Authorization:** NestJS Guards | Express middleware | Custom
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)} | inline (no diff)
- **Overall Posture:** Clean | Issues Found - <n> Critical / <n> High / <n> Medium / <n> Low   {append ` (partial coverage)` whenever Not verifiable has an entry}

<2-3 sentences on the Node-specific risks; on a clean run, name the controls that make it clean>

## OWASP Triage

| Category | Verdict | Basis |
| -------- | ------- | ----- |
| A01 Broken Access Control | finding \| clean \| no signal in diff \| not verifiable | <the control seen, or the control that could not be read> |
| A02 Security Misconfiguration | ... | ... |
| A03 Software Supply Chain Failures | ... | ... |
| A04 Cryptographic Failures | ... | ... |
| A05 Injection | ... | ... |
| A06 Insecure Design | ... | ... |
| A07 Authentication Failures | ... | ... |
| A08 Software or Data Integrity Failures | ... | ... |
| A09 Logging and Alerting Failures | ... | ... |
| A10 Mishandling of Exceptional Conditions | ... | ... |

## Not verifiable   {only when a control could not be confirmed}

- <control> - <why it could not be confirmed: `src/main.ts` absent at head_ref; `pnpm audit` not runnable here>

## Findings

### Critical

1. **[Must | Recommend]**{ _(carried from round <N>)_} **Location:** <file:line>{ <verify annotation groups>}

   **Issue:** <the vulnerability in Node terms - "the global `ValidationPipe` runs without `whitelist`, so `CreateRefundDto` accepts `requestedBy` and the caller forges the audit trail">

   **Attack scenario:** <exploit walkthrough | `Regression risk: ...` | `Topology-dependent: ...`>

   **Severity rationale:** <tier> - <the rubric clause that applies>

   **Fix:** <Node remediation with code; several fixes on one construct numbered>

### High

<same block; numbering continues across tiers>

### Medium

<same>

### Low

<same>

- **out of lens:** <file:line - defect, owning workflow>   {only when one exists}

{omit empty tiers; when every tier is empty, write `No security issues found.`}

## Prior Round Reconciliation   {round 2+ standalone only}

<table, note line, and tally from `review-prior-findings-reconcile`>

## Recommendations

- <hardening not tied to a finding - CSP directives for the admin UI, rotate `JWT_SECRET` through the secret manager>

## Next Steps

1. **[Implement]** [Must] <file:line> - <action>
2. **[Delegate]** [Recommend] [scope: dependencies] - <action>
3. **[Delegate]** [Recommend] [scope: verify] - confirm <control> (not verifiable)

{one entry per finding, a carried one suffixed ` (open since round <N>)`; `[Implement]` for a localized fix, `[Delegate]` for cross-cutting hardening, an upgrade, or a threat model; one `[Delegate]` `[Recommend]` per Not verifiable entry; ordered Must > Recommend, carryovers first among equals; omit only when there are no findings and nothing was unverifiable}
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed; `Framework` and `ORM` recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-security`; round decided from the handle before the diff was read (or the stop line printed); subagent / audit: step skipped
- [ ] Step 4: surface read at `head_ref` (audit: `HEAD`); prior revision consulted when auth was relaxed; unconfirmable controls recorded in `## Not verifiable`
- [ ] Step 5: one verdict per OWASP 2025 category with its basis; findings not duplicated
- [ ] Step 6: hashing, brute force, JWT verification, token lifetime, cookies
- [ ] Step 7: authorization drift, roles, object and tenant scope, CSRF, CORS for every new or changed endpoint
- [ ] Step 8: validation, nested DTOs, mass assignment, sensitive columns, uploads, traversal, exec
- [ ] Step 9: `node-security-patterns` consulted; body limits, ReDoS, SSTI, payloads, Swagger checked when touched
- [ ] Step 10: data protection assessed; one construct filed once; verify ran with its tally (or the subagent / audit carve-out); round 2+ projected and reconciled, unresolved rows carried
- [ ] Step 11: standalone report written with every writer field (`depth: deep`); subagent: findings and Not verifiable returned, no file; audit: body emitted
- [ ] Every finding has a label, a rubric clause, and an attack-scenario framing; each Not verifiable entry has a `[Delegate]` Next Step

## Avoid

- State-changing git from this workflow
- "Input not validated" with no attack - say what the attacker sends and gains
- `Clean` when a control could not be confirmed - that is `(partial coverage)`
- `:name` parameters for TypeORM `repository.query`, or `@Exclude()` as the control on a Prisma result
- Generic advice where a Node idiom exists ("add `@UseGuards(AuthGuard('jwt'))`", not "add an auth check")
- `@Public()`, a removed `requireAuth`, or a disabled `ValidationPipe` as the fix for a failing test
- `algorithms: undefined` for `jsonwebtoken.verify`
- Approving `eval` / `new Function` / `vm` / `vm2` on input not under full server control, `rejectUnauthorized: false` outside test fixtures, Swagger exposed in production, or `.passthrough()` on a write path
