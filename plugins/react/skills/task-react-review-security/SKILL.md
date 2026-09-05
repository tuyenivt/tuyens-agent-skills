---
name: task-react-review-security
description: React / Next.js security review: XSS, dangerouslySetInnerHTML, Server Actions, RSC leaks, NEXT_PUBLIC, CSP, auth, CSRF, open redirect, OWASP.
agent: react-security-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, security, xss, csp, server-actions, owasp, workflow]
  type: workflow
user-invocable: true
---

# React Security Review

Stack-specific delegate of `task-code-review-security` for React / Next.js / Vite. It preserves the parent's invocation and diff-resolution contract; the Findings and triage shape below is this file's own.

## When to Use

- Reviewing a Next.js or Vite + React PR for security regressions
- Pre-deployment hardening pass on auth, upload, payment, or PII paths
- Auditing a Server Action, Route Handler, middleware, OAuth callback, or new auth flow

**Not for:** performance (`task-react-review-perf`), general review (`task-react-review`), backend API of the React app (run against the backend repo).

**No depth knob.** Security regressions have cliff-edge consequences (XSS account takeover, secret in bundle). Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                  |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS on user input (`dangerouslySetInnerHTML`, a `javascript:` URL reaching `href`, a `data:` URL reaching a script-executing sink, or equivalent). A `data:` URL in `<img src>` does not execute and in an `<iframe src>` loads in an opaque origin - those are High phishing / UI-redress, not same-origin XSS, privileged secret in `NEXT_PUBLIC_*`, auth bypass on Server Action / Route Handler, mass exfiltration via RSC passing entire ORM row to Client Component, `eval` / `new Function` on user input, a webhook handler that skips signature verification when its secret env var is unset, or a merged finding the Combined-finding rule elevates here. Blocks merge. |
| **High**     | Missing input validation on a Server Action that mutates, missing `auth()` on a privileged handler that no other gate covers (when the handler is reachable and the data is sensitive or mutable, that is the Critical auth-bypass row instead), IDOR via path param without ownership check, open redirect via unchecked `redirect(userInput)`, CSRF on cookie-session form, `localStorage` for session tokens, reachable SSRF (caller-influenced server-side fetch with a bypassable hostname check or no `redirect: 'manual'`), webhook signature over a re-serialized body or compared without `timingSafeEqual`. |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but no untrusted HTML rendered), weak rate limit on auth route, Sentry collecting PII without redaction, `<meta>`-delivered CSP on SSR app, `npm audit` advisory not yet exploited, missing webhook replay window, missing `AbortSignal.timeout` on a user-triggered outbound fetch. |
| **Low**      | Defense-in-depth, advisory below actively-exploited threshold, hardening without a concrete current attack scenario.                                                                                                        |

**Combined-finding rule.** When two findings *compose* on the same handler / component / route segment into a worse threat than either alone, file as one finding at the elevated severity citing each component (e.g., missing `auth()` + mass assignment via `Object.fromEntries(formData)` on the same Server Action = Critical unauthenticated admin override; `dangerouslySetInnerHTML` + sanitizer with `ADD_TAGS: ['script']` on the same component = Critical working XSS; `NEXT_PUBLIC_API_KEY` + that key calling an admin API from the browser = Critical exposed admin key). Composition wins over splitting: parts that are also independently exploitable still merge when they land on the same handler - the merged finding cites each part and its standalone severity. File separately only when the defects sit on different handlers or do not compose into something worse. "Worse" means the combination reaches a capability neither part reaches alone (unauthenticated write, working script execution, an exposed privileged credential) - not merely that both are serious. Two defects already at the top tier for the same capability merge; two at the top tier for different capabilities stay separate, however co-located. When co-location is unclear from the diff, file separately and add `Note: Combined-finding rule applies if both land on the same handler; verify before merge` to the lower-severity entry.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                             | Meaning                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------ |
| `/task-react-review-security`          | Review current branch vs its base; fails fast on trunk                   |
| `/task-react-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                               |
| `/task-react-review-security pr-<N>`   | Review PR head fetched into local branch `pr-<N>` (user runs the fetch)  |

`task-react-review` spawns this workflow as a subagent and passes the pre-confirmed stack and framework, `base_ref` / `head_ref`, and the pre-read diff and commit log; Steps 2-3 consume those instead of re-running. `task-code-review-security` does **not** spawn a subagent - it forwards the invocation arguments and stops, so that path is a normal standalone run that owns its own report. A forwarded `--base` goes to `review-precondition-check`; a forwarded `deep` is ignored (see **No depth knob**).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step. Skip re-load when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept the pre-confirmed stack when `task-react-review` passed one. If not React, stop and name the detected stack so the user can invoke that stack's security workflow - do not redirect to `/task-code-review-security`, which is what dispatched here.

Record for the Summary block: `Framework` (Next.js App Router / Pages Router / Vite + React Router), `Auth` (Auth.js / Clerk / Lucia / iron-session / Custom / backend-only), `Sanitizer` (DOMPurify / sanitize-html / none).

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (default: current branch). On approval, read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse. Capture `head_sha = git rev-parse <head_ref>` and `base_sha = git rev-parse <base_ref>` for the report checkpoint. Skip entirely when the parent passed pre-read artifacts. If precondition fails, surface the message verbatim and stop. Never run state-changing git.

### Step 4 - Read the Security Surface

Open the files that actually wire security before applying checklists, so findings cite real lines.

**Next.js:**
- `middleware.ts` - auth checks, `matcher` scope, security headers, redirect logic
- `next.config.{js,ts,mjs}` - `headers()` (CSP, HSTS), `redirects()`, `images.remotePatterns` (`images.domains` is deprecated)
- Auth config (`auth.ts` / `lib/auth.ts`) - session strategy, cookie flags, OAuth callback URL allowlist
- Every changed `app/**/page.tsx`, `layout.tsx`, `route.ts`, and any file marked `'use server'`
- Every component rendering untrusted HTML (`dangerouslySetInnerHTML`, MDX, `rehype-raw`)
- Every `<form action={serverAction}>` and the action body
- `.env.example` / `.env.local` - any `NEXT_PUBLIC_*` naming a server secret
- `package.json` for auth, sanitizer, and rate-limit libraries

**Vite + React Router:**
- Components rendering untrusted HTML
- `.env.example` / `.env` files for any `VITE_*` name that is a server secret
- `index.html` / `vite.config.{js,ts}` for CSP via `server.headers` (dev) or the hosting platform's header config (prod). A `<meta>` CSP is the common Vite shape but is strictly weaker - it cannot carry `frame-ancestors` - so flag it as a hardening gap, not as the Next.js-grade defect
- `vite.config.{js,ts}` `define` (build-time inlining), `server.proxy`, `server.host` and `build.sourcemap`
- React Router `loader` / `action` functions - the SPA's actual authorization boundary
- API client config (`withCredentials`, CSRF header, token storage)
- `package.json` for sanitizer

When the diff removes a CSP rule, drops `DOMPurify`, or widens a middleware `matcher`, `git log -p` the prior revision to confirm what was protected before.

Use skill: `react-nextjs-patterns` - it owns the canonical Server Action rules (schema validation, authorization, the server-only boundary, `"use server"` as a public endpoint) that this lens scores against; `task-react-review` defers that depth here.

### Step 5 - OWASP Triage

One-row-per-category verdict that funnels which downstream checks run carefully. Steps 6-7 produce the findings; do not duplicate here.

| Risk                          | React signal in diff                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | New Server Action / Route Handler without `await auth()`; missing ownership filter; widened `middleware.ts` `matcher`; `redirect(returnTo)` / `navigate(returnTo)` without allowlist |
| Injection                     | `prisma.x.update({ where, data: Object.fromEntries(formData) })`; raw `formData.get(...)` into ORM without Zod                                    |
| XSS                           | `dangerouslySetInnerHTML={{ __html: userInput }}`; markdown render with `rehype-raw`; `DOMPurify` `ADD_TAGS` including `script`/`iframe`   |
| Cryptographic Failures        | Custom crypto on auth path; `crypto.createHash('sha256')` for passwords; `alg: none` accepted in JWT verify                                |
| Security Misconfiguration     | Missing CSP / HSTS; `unsafe-eval` / `unsafe-inline` / wildcard `*` in `script-src`; `<meta>`-delivered CSP; `remotePatterns` wildcard host; `postMessage` listener without origin check |
| SSRF                          | `fetch(searchParams.get('url'))` in Route Handler / Server Component without host allowlist                                                |
| Insecure Design              | A protected surface reachable with no in-handler check; authorization decided in one place and re-derived ad hoc in others                  |
| Vulnerable Components        | `package.json` / lockfile change with stale advisory; Dependabot disabled                                                                  |
| Data Integrity Failures      | `eval` / `new Function`; `JSON.parse(userInput)` spread into Prisma; `'use server'` file re-exporting non-action utility; webhook handler with missing, post-parse, non-raw-body, or skipped-when-secret-unset signature verification |
| Logging & Monitoring         | Sentry browser SDK without `beforeSend` PII strip; client / server logs containing `password` / `token` / `authorization`                  |

Mark each category `yes` or `no signal in diff`.

### Step 6 - Diff-Specific Checks

Apply against changed files. **Gate**: run a sub-block when a related Step 5 row is `yes`, or when its surface appears in the diff regardless of triage verdicts - **authn / authz: any Server Action, Route Handler, `middleware.ts`, auth config or session change - on Vite, any React Router `loader` / `action`, route guard, or API-client auth wiring**; input validation: any of those that reads user input, on either stack; outbound requests / webhooks: any server-side fetch or webhook handler added or changed; Common React vulnerability patterns: any client component or markup changed, **or any change to `middleware.ts`, `next.config.*`, `index.html` or the hosting header config** (the CSP, `remotePatterns` and framing checks live in that block); data protection: any logging, analytics, or env change. Skip a sub-block only when nothing triggers it. This keeps Step 6 a targeted check, not a full OWASP audit.

**Authn / authz**
- [ ] Auth library chosen and consistent (Auth.js / Clerk / Lucia / iron-session); not mixed
- [ ] Every protected Server Action / Route Handler calls `await auth()` **inside** the handler. Middleware does run for Server Actions on Next 15 (they are POSTs to the invoking page's URL), but it is not an authorization boundary: the `matcher` matches the *calling page's* path rather than where the action is defined, and middleware auth was outright bypassable via `x-middleware-subrequest` until 15.2.3 (CVE-2025-29927). Never trust client-side `useSession` for authorization
- [ ] `middleware.ts` `matcher` widening: any path moved to public must have its own in-handler `auth()` check, else Critical
- [ ] IDOR: lookups scope by principal in the WHERE clause (`prisma.order.findFirst({ where: { id, ownerId: session.user.id } })`); not a separate post-fetch check
- [ ] Per-tenant queries scoped by `tenantId` from session, never from URL
- [ ] Roles read from the server-validated session, never from request body / search param / header
- [ ] Password hashing (when handled in-app): `bcrypt` (cost >= 10) or `argon2`; never `crypto.createHash`
- [ ] JWT verify: explicit `algorithms` allowlist; `issuer` / `audience` set; never accept `alg: none`
- [ ] Session cookies: `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'`. Auth.js v5 sets all three by default on `__Secure-authjs.session-token`, so flag only an explicit override - and do not recommend `'strict'`, which breaks the OAuth round-trip: the `authjs.state` and `authjs.pkce.code_verifier` cookies are not sent on the provider's cross-site redirect back, and a Strict session cookie leaves the post-callback landing request looking logged out. Auth.js also ships its own CSRF cookie, named `__Host-authjs.csrf-token` in a secure context. Flag tokens in `localStorage` / `sessionStorage`
- [ ] OAuth / magic-link callbacks validate `state` / `nonce`; `returnTo` checked against an allowlist, or a relative-path test that also rejects backslashes - `url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/\\')` - since browsers normalise `/\evil.com` to a scheme-relative cross-origin URL
- [ ] Brute-force protection on `/api/auth/*` via `@upstash/ratelimit` or platform rate limit
- [ ] CSRF: Next.js protects Server Actions by requiring POST and comparing `Origin` against `Host` - action IDs are build-derived identifiers shipped in the public bundle and are **not** a CSRF control. Behind a proxy that rewrites `Host` / `X-Forwarded-Host` that comparison is defeated, so `experimental.serverActions.allowedOrigins` must pin the accepted origins. **Route Handlers get no built-in protection at all**: a cookie-session `POST /api/*` needs its own token or `sameSite` cookie. Bearer-token APIs require CSRF only on cookie auth

**Input validation / mass assignment**
- [ ] Every Server Action and Route Handler validates input first. A Zod object schema cannot parse a `FormData` instance - use `Schema.parse(Object.fromEntries(formData))`, or `zod-form-data` for repeated fields and files
- [ ] No `data: Object.fromEntries(formData)` / `data: parsedJson` on a Prisma write - require an explicit Zod schema with a field allowlist
- [ ] No privilege fields (`role`, `isAdmin`, `ownerId`, `tenantId`, `verified`) on user-facing input schemas - server-set only
- [ ] Response is a DTO, not a raw ORM row - prevents `passwordHash` / `mfaSecret` leak as columns are added
- [ ] Dynamic route segments (`params.id`) Zod-validated (UUID / int / slug) before reaching ORM
- [ ] File uploads: type via `file-type` content sniff (not `file.type`), size capped, `instanceof File` checked. `file-type` returns `undefined` for SVG, CSV and every text format, so sniffing alone passes the riskiest uploads - reject on `undefined` and match against an expected-type allowlist. SVG stays a stored-XSS vector even when correctly identified
- [ ] Server Action / Route Handler return value treated as a public surface - no privileged / internal fields

**Server-side outbound requests and inbound webhooks**
- [ ] Server-side `fetch` with a caller-influenced URL validates the **parsed** `hostname` against an allowlist, matched whole. A `startsWith` on the hostname passes `allowed.com.evil.com`; a check against the raw URL string is weaker still, since `https://evil.com/?x=https://allowed.com` and `https://allowed.com@evil.com` both satisfy a naive `includes()` or `startsWith` while parsing to hostname `evil.com`
- [ ] Allowlisted outbound fetch sets `redirect: 'manual'` - an allowed host redirecting to `169.254.169.254` or an internal address defeats a check made only on the original URL. Note that resolving the hostname and rejecting private ranges does **not** stop DNS rebinding: the check-time and connect-time lookups are separate, so a low-TTL record can answer differently for each. Closing that needs the connection pinned to the address that was checked (a custom `lookup` / undici dispatcher) or an egress proxy
- [ ] Outbound fetch on a user-triggered path carries `AbortSignal.timeout(...)`; an unbounded server-side fetch is a denial-of-service primitive
- [ ] Inbound webhook handlers read the **raw** body and verify the signature **before** parsing; parsing first means untrusted input already reached a parser
- [ ] Signature comparison is timing-safe (`crypto.timingSafeEqual`), never `===` or `==`. It takes `Buffer`/`TypedArray` only and **throws `RangeError` on unequal lengths**, so hash both sides (or length-check first) before comparing; it is also unavailable on the Edge runtime Next middleware defaults to
- [ ] Webhook handlers reject timestamps outside a short window (~5 min); without it any captured request is replayable forever
- [ ] Webhook secrets read server-side only; a webhook route that skips verification when the secret env var is unset is Critical

**Common React vulnerability patterns**
- [ ] `dangerouslySetInnerHTML` on user input wrapped in `DOMPurify.sanitize(html)` with default config - plain `dompurify` needs a DOM, so a Server Component, Server Action or Route Handler needs `isomorphic-dompurify` (or `jsdom`), and it does not run on the Edge runtime at all; flag `ADD_TAGS` containing `script` / `iframe` / `object` / `embed` / `style`; flag `ADD_ATTR` containing event handlers (`onload`, `onclick`, `onerror`) - DOMPurify already allows `src` / `href` on permitted tags and filters them through `ALLOWED_URI_REGEXP`, so those two are not by themselves a bypass
- [ ] `href={userInput}` (Next.js `<Link>` and `<a>`) - scheme validated as `http(s):` (block `javascript:`, `data:`, `vbscript:`)
- [ ] Open redirect: `redirect(searchParams.get('returnTo'))` / `navigate(returnTo)` validated against allowlist or relative-path-only check (React Router `navigate()` is same-origin path navigation - Medium unless the value reaches `window.location` or an anchor `href`)
- [ ] Client-bundle secret audit: any `NEXT_PUBLIC_*` (Next) or `VITE_*` / `import.meta.env` reference (Vite) naming an API key, DB URL or signing secret is Critical - both prefixes are inlined into every browser bundle at build time. On Vite also check `vite.config` `define`, which inlines whatever it is given regardless of prefix
- [ ] `'use server'` files export only Server Actions. Next 15 fails the build on a non-`async` export, so the live risk is a re-exported **async** helper becoming a network-callable mutation
- [ ] An auth guard that calls `redirect()` is not wrapped in a `try/catch`: `redirect()` works by throwing `NEXT_REDIRECT`, so a `catch` around an awaited DB call swallows it and the handler falls through **unauthenticated**. Use `unstable_rethrow(error)` (or an `isRedirectError` check) in every catch on a path that redirects
- [ ] Server Component -> Client Component prop projection: never pass entire ORM rows; project via a DTO or Prisma `select`. Prisma `omit` is a denylist, so a newly added sensitive column leaks - it does not satisfy the add-a-column rule above
- [ ] CSP set as an HTTP response header, not `<meta http-equiv>` (a `<meta>` CSP cannot carry `frame-ancestors` and applies only after parsing starts). A **nonce** CSP must come from `middleware.ts`, which can mint a value per request and is what Next reads to nonce its own bootstrap scripts; `next.config` `headers()` emits a static header, so a nonce there is fixed and attacker-known. Require `default-src 'self'`, `frame-ancestors 'none'`, and no wildcard hosts in `connect-src` / `frame-src`. Under `'strict-dynamic'` browsers ignore `'self'` and every host source in `script-src`, so judge that directive by its nonce, not its host list
- [ ] No `unsafe-eval` in production `script-src`. Flag `'unsafe-inline'` only when no nonce is present: in the canonical strict recipe (`'nonce-{r}' 'strict-dynamic' https: 'unsafe-inline'`) the trailing tokens are deliberate CSP2 fallbacks that CSP3 browsers ignore. Dev-only guards via `process.env.NODE_ENV !== 'production'`
- [ ] No `eval` / `new Function(string)` on user input; flag template engines using `new Function` (e.g., `lodash.template`)
- [ ] `postMessage` listeners check `event.origin` against expected
- [ ] `<iframe>` rendering external content has `sandbox` with minimum allowlist; `<iframe src={userInput}>` validated against host allowlist
- [ ] `<a target="_blank">` carries `rel="noreferrer"` where referrer leakage matters (`noopener` has been implied for `target="_blank"` in every current browser since 2021, so its absence is no longer a tabnabbing vector)
- [ ] `next.config.js` `images.remotePatterns` pins hostnames; wildcard subdomains (`*.example.com`) flagged for subdomain-takeover risk
- [ ] Third-party scripts via `<Script>` justified; SRI `integrity` set for non-first-party scripts

**Data protection**
- [ ] Sentry browser SDK `beforeSend` strips `email` / `password` / `token` / `creditCard`; `sendDefaultPii: false`
- [ ] No tokens / passwords / PII in URLs (search params, path params hit logs + referer)
- [ ] HSTS via `next.config.js` `headers()` or hosting platform; HTTP redirected to HTTPS at edge
- [ ] Server secrets sourced from secret store; `.env.local` gitignored; no literal keys committed
- [ ] `productionBrowserSourceMaps: false` unless intentionally serving

**Collect hardening that is not a specific finding** - controls the diff did not break but that the reviewed surface still lacks - into `## Recommendations`, ordered by the risk they reduce.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 7 - Write Report

**Subagent mode:** return this workflow's Output Format document - Summary, OWASP Triage, Findings, Could Not Verify, Recommendations, Next Steps - and write nothing; the parent merges the Findings and Next Steps and carries the rest into its own `## Scope Sections`. Each finding already carries its `Label`.

**Round gate (standalone only).** Run this immediately after Step 3 resolves the refs, before reading any surface - a no-op exit should cost one `git rev-parse`, not a whole review. Resolve `<branch>` first, exactly as the writer call below does: the head's short name, or the handle's `current_branch` when `head_ref` is the literal `HEAD`. The prior-report key is `review-security-<branch>.md` with the writer's filename sanitization applied (`/` and any character outside `[A-Za-z0-9_-]` replaced, runs collapsed, ends stripped), so a `feature/x` branch looks up `review-security-feature-x.md`. The `prior_checkpoint` in the precondition handle names the **core** `review-<branch>.md` and is a different report - ignore it. If that file exists with valid frontmatter and its `head_sha` equals the current head, and this run adds no depth, print `No new commits on <branch> since prior security review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Treat missing or invalid frontmatter as round 1 and overwrite.

**Reconcile (standalone, round 2+).** When a valid prior report exists and this is a diff-based run, Use skill: `review-prior-findings-reconcile`. It parses a `## High-Impact Findings` section containing one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, which is not this workflow's report shape, so **re-project the prior report first**: emit that exact section heading, then per prior finding a `### [<Label>] <file:line>` heading taking the label from its `Label` slot and the location from its `Location` slot, followed by `- Issue: <its Issue text>` (reconcile reads that line as the finding's summary and cannot match without it). Pass the projection as `prior_report` along with the diff, the `git diff --name-status <base>...<head>` list from Step 3, and `head_sha`. Put the returned table under `## Prior Round Reconciliation`. Carry its `Still open` and `Needs re-check` rows into this round's Findings, in the section the prior report filed them under (the table returns a label, not a bucket - re-read the prior report for the bucket), with `(open since round <N>)` appended to the `Location` line and any `_(pre-existing)_` annotation preserved, since next round's reconcile keys on it. Map any legacy label the table preserved (`[Blocker]`, `[High]`, `[Suggestion]`, `[Question]`, `[Nitpick]`) into `[Must]` or `[Recommend]` before publishing anything outside the reconciliation table itself, which keeps them verbatim. Skip reconciliation entirely when there is no diff (audit mode or a whole-app sweep) and say so in the Summary.

Then Use skill: `review-report-writer` with `report_type: review-security` and every required field: `report_body`, `branch`, `base_ref` / `head_ref` from the precondition handle - when the handle's `head_ref` is the literal `HEAD` (no-argument mode), pass its `current_branch` instead, or the writer produces a `-HEAD.md` file the next round's lookup never finds, `base_sha` / `head_sha` from Step 3, `scope: +sec`, `depth: standard` (this workflow has no depth knob; the writer still requires the field), `stack: typescript-nextjs` (Vite: `typescript-react`), and `mode: full`, `round: 1` - unless `review-security-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself). Write the report; print the confirmation line after the report body.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## React Security Review Summary

- **Stack Detected:** React <version> / TypeScript <version>
- **Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
- **Auth:** Auth.js | Clerk | Lucia | iron-session | Custom | backend-only
- **Sanitizer:** DOMPurify | sanitize-html | none
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_; <U> of these unverified _(that clause only when a surviving row is unverified)_. _In subagent mode write exactly `not run (subagent; parent verifies the merged set)`._
- **Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count, +N unverifiable]

[2-3 sentence assessment calling out React-specific risks: `dangerouslySetInnerHTML` on user input, `NEXT_PUBLIC_*` secret leak, missing Server Action validation, RSC passing ORM rows to Client Components, missing / weak CSP, open redirect via `returnTo`.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | ...                     |
| XSS                       | ...                     |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

Labels: `Critical` and `High` -> `[Must]`; `Medium` and `Low` -> `[Recommend]` (the verify pass's `Label` column overrides when it ran, so a `[Recommend]` inside `### Critical` is a correct de-escalation of an untouched pre-existing defect, not a mismatch to fix). The tier tracks exploitability, the label tracks the merge gate. Every finding carries its `Label` slot so a consuming workflow never has to re-derive it.

### Critical

- **Label:** [Must | Recommend]
- **Location:** [file:line, or comma-separated for multi-site; carry the verify pass's annotation when it set one: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `(unverified: <reason>)`]
- **Vulnerability class:** [XSS via dangerouslySetInnerHTML | Mass assignment | Auth bypass | Open redirect | NEXT_PUBLIC secret leak | RSC data leak | CSRF | SSRF | ...]
- **Issue:** [vulnerability in React terms - e.g., "`UserBio` component renders `<div dangerouslySetInnerHTML={{ __html: user.bio }} />` with no sanitizer; `user.bio` is stored verbatim from the profile form Server Action which also lacks Zod"]
- **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether the CDN strips the X-Forwarded-Host header". Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Composed from:** [when the Combined-finding rule merged this: each component and its standalone severity; omit otherwise]
- **Severity rationale:** [tier] per rubric - [which clause applies; for a merged finding cite the Combined-finding rule instead, and for a webhook-verification gap cite the webhook clause added to Critical]
- **Note:** [only when co-location was unclear from the diff: `Combined-finding rule applies if both land on the same handler; verify before merge`]
- **Fix:** [React remediation with code - Zod schema, `DOMPurify.sanitize` wrapper, `nonce`-CSP via middleware, `select`-projected DTO, `returnTo` allowlist, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit sections with no findings. When every section is empty, `## Findings` still appears and contains exactly `No security issues found.` When a defect outside this lens would break the build or expose data, add one `out of lens: <one line>` at the end of `## Findings` and mirror it as a `[Delegate]` Next Step._

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Could Not Verify From Diff

[Items that are likely findings but depend on code/infra outside the diff (e.g., a path moved out of the `middleware.ts` matcher whose handler is not in scope - cannot confirm it has its own in-handler `auth()`). State the issue, the severity it would carry if unmitigated, and what to check. Mirror each as a `[Delegate]` Next Step. Do not assign these a confirmed severity in the Findings counts; track them on a separate "+N unverifiable" line. Omit the section when empty.]

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `nonce`-based CSP via middleware", "Replace `localStorage` token with httpOnly cookie", "Migrate Pages Router auth to Auth.js v5", "Add `pnpm audit` to CI".]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, dependency upgrade, or threat-model exercise). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Wrap `user.bio` in `DOMPurify.sanitize` (default config) and add Zod schema to `updateProfile` Server Action"]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action, e.g., "Run `pnpm audit` and upgrade flagged packages"]

_Omit if no security issues found._
```

## Self-Check

One item per Workflow step, plus the access-dependent list below.

- [ ] **Step 1**: `behavioral-principles` loaded (or accepted as pre-loaded from a parent workflow)
- [ ] **Step 2**: Stack confirmed React; `Framework`, `Auth`, `Sanitizer` recorded before any framework-specific check applied
- [ ] **Step 3**: `review-precondition-check` ran (or handle received from parent); `base_ref` / `head_ref` / `head_matches_current` captured; diff and log read once and reused; on `head_matches_current=false`, explicit user approval obtained before review (skipped when subagent)
- [ ] **Step 4**: Security surface (middleware, `next.config.js` headers, auth config, changed Server Actions / Route Handlers / RSC / Client Components, `dangerouslySetInnerHTML` sites, env vars, `package.json`) read directly; prior revision consulted when middleware or CSP relaxed
- [ ] **Step 5**: OWASP triage produced one verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Step 6**: Diff-specific checks applied for authn/authz, input validation / mass assignment, outbound requests and inbound webhooks, common React vulnerability patterns, and data protection - each run or explicitly skipped because nothing triggered it; severity rubric applied consistently; Combined-finding rule applied where two findings compose on the same handler; every finding has an attack scenario, regression-risk, or topology-dependent label, a `Label`, and a rubric clause
- [ ] **Step 6 (verify)**: `review-finding-verify` ran on the assembled findings; `Dropped` rows excluded; the verify `Label` column applied; tally in Summary (subagent runs skip this and write the stated subagent string)
- [ ] **Step 7**: Standalone: same-SHA no-op gate applied; prior round reconciled when a valid prior report existed; report written via `review-report-writer` with full checkpoint fields (`scope: +sec`, `depth: standard`, `stack: typescript-nextjs` / `typescript-react`) and a real branch name; confirmation line printed. Subagent: Output Format document returned, nothing written

**Requires repo / infra access (when not visible in the diff, list under `## Could Not Verify From Diff` and mirror as a `[Delegate]` Next Step):**

- [ ] Auth library config (Auth.js / Clerk / Lucia) reviewed - applies when auth module is in scope
- [ ] CSP / HSTS / cookie flags verified - applies when middleware or `next.config.js` `headers()` in scope
- [ ] Sentry browser SDK `beforeSend` strips PII - skip if Sentry init not in diff
- [ ] `pnpm audit` / `npm audit` clean - run separately; this workflow does not execute tools

## Avoid

- Running `git fetch` / `git checkout` or any state-changing git command - the user runs these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario, regression-risk, or topology label
- Skipping OWASP categories that look clean - explicitly state "no signal in diff"
- Generic security advice when a React idiom applies (say "validate Server Action input with Zod", not "add input validation")
- Approving any of: `dangerouslySetInnerHTML` on user input without `DOMPurify`; `DOMPurify` with `ADD_TAGS: ['script' | 'iframe']` or event-handler `ADD_ATTR`; `NEXT_PUBLIC_*` for a privileged secret; `localStorage` for session tokens; `'use server'` files re-exporting non-action utilities; Server Components passing entire ORM rows to Client Components; `unsafe-eval` / `unsafe-inline` in production `script-src`; `eval` / `new Function` on user input; `redirect(searchParams.get('next'))` without allowlist; `<meta>`-delivered CSP on a server-rendered app without justification
- Treating client-side `if (user.role === 'admin')` as authorization - it is UX only; the server enforces
- Disabling Server Action validation or middleware auth to silence a failing test - fix the test
- Conflating with general code review or performance review - delegate to their workflows
- Inventing a severity tier outside the four in the rubric
