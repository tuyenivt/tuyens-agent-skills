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
| **Critical** | Working XSS on user input (`dangerouslySetInnerHTML`; a `javascript:` URL reaching a sink React does not guard - `location.href`, `window.open`, `setAttribute`, an HTML string - or JSX `href` on React 18 and earlier, since React 19 blocks `javascript:` URLs in JSX; a `data:` URL reaching a script-executing sink), privileged secret in `NEXT_PUBLIC_*` / `VITE_*`, auth bypass on Server Action / Route Handler / API route, mass exfiltration through any public surface (an RSC prop, a Route Handler or API route response, a Server Action return) carrying an entire ORM row with credential or cross-user columns, `eval` / `new Function` on user input, a webhook handler that skips signature verification when its secret env var is unset, a known-exploited advisory (CISA KEV) in a reachable package, or a merged finding the Combined-finding rule elevates here. Blocks merge. A `data:` URL in `<img src>` does not execute and in an `<iframe src>` loads in an opaque origin - those are High phishing / UI-redress. |
| **High**     | Missing input validation on a Server Action that mutates, missing `auth()` on a privileged handler that no other gate covers (when the handler is reachable and the data is sensitive or mutable, that is the Critical auth-bypass row instead), IDOR via path param without ownership check, open redirect via unchecked `redirect(userInput)`, CSRF on cookie-session form, `localStorage` for session tokens, reachable SSRF (caller-influenced server-side fetch with no hostname check, a bypassable one, or no `redirect: 'manual'`), webhook signature over a re-serialized body or compared without `timingSafeEqual`. |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but no untrusted HTML rendered), weak rate limit on auth route, Sentry collecting PII without redaction, `<meta>`-delivered CSP on SSR app, `npm audit` advisory not yet exploited, missing webhook replay window, missing `AbortSignal.timeout` on a user-triggered outbound fetch. |
| **Low**      | Defense-in-depth, advisory below actively-exploited threshold, hardening without a concrete current attack scenario.                                                                                                        |

**Combined-finding rule.** When two findings *compose* on the same handler / component / route segment into a worse threat than either alone, file as one finding at the elevated severity citing each component (e.g., missing `auth()` + mass assignment via `Object.fromEntries(formData)` on the same Server Action = Critical unauthenticated admin override; `dangerouslySetInnerHTML` + sanitizer with `ADD_TAGS: ['script']` on a server-rendered component (the parser runs it on document load; a client-side `innerHTML` script is inert), or with an event-handler `ADD_ATTR` anywhere = Critical working XSS; mass assignment of a money or privilege field on an authenticated action is High, and Critical only when it composes with missing `auth()`; `NEXT_PUBLIC_API_KEY` + that key calling an admin API from the browser = Critical exposed admin key). Composition wins over splitting: parts that are also independently exploitable still merge when they land on the same handler - the merged finding cites each part and its standalone severity. File separately only when the defects sit on different handlers or do not compose into something worse. "Worse" means the combination reaches a capability neither part reaches alone (unauthenticated write, working script execution, an exposed privileged credential) - not merely that both are serious. Two defects already at the top tier for the same capability merge; two at the top tier for different capabilities stay separate, however co-located. When co-location is unclear from the diff, file separately and add `Note: Combined-finding rule applies if both land on the same handler; verify before merge` to the lower-severity entry.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                             | Meaning                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------ |
| `/task-react-review-security`          | Review current branch vs its base; fails fast on trunk                   |
| `/task-react-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                               |
| `/task-react-review-security pr-<N>`   | Review PR head fetched into local branch `pr-<N>` (user runs the fetch)  |

`task-react-review` spawns this workflow as a subagent and passes the pre-confirmed stack and framework, `base_ref` / `head_ref`, and the pre-read diff, name-status list and commit log; Steps 2-3 consume those instead of re-running. `task-code-review-security` does **not** spawn a subagent - it forwards the invocation arguments and stops, so that path is a normal standalone run that owns its own report. A forwarded `--base` goes to `review-precondition-check`; a forwarded `deep` is ignored (see **No depth knob**).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step. Always runs, subagent mode included; only a parent running this lens inline in its own context has it loaded already.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept the pre-confirmed stack when `task-react-review` passed one. If not React, stop and name the detected stack so the user can invoke that stack's security workflow - do not redirect to `/task-code-review-security`, which is what dispatched here.

`stack-detect` keys the primary stack on the root manifest, so in a polyglot repo (a React app under `apps/<name>` beside a Rails root) React may appear only under `Additional`; that counts as React when the diff or request sits inside that package - confirm React against the package's own `package.json`, scope the run to it, and name the package in the Summary's `Notes`.

Record for the Summary block: `Framework` (Next.js App Router / Pages Router / hybrid App + Pages Router / Vite + React Router), `Auth` (Auth.js / Clerk / Lucia / iron-session / Custom / backend-only / none), `Sanitizer` (DOMPurify / sanitize-html / none).

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-security`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface a fail-fast verbatim, write no report, and stop. Never run state-changing git.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones -> print `No new commits on <head_short_name> since prior security review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the report write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse.

**Subagent mode** = a parent passed `base_ref` / `head_ref` plus the pre-read diff, name-status list and log (also when the parent runs this lens inline): skip the precondition, the round gate and the diff reads; the surface read still runs.

### Step 4 - Read the Security Surface

Open the files that actually wire security before applying checklists, so findings cite real lines.

**Next.js:**
- `middleware.ts` (`proxy.ts` on Next 16) - auth checks, `matcher` scope, security headers, redirect logic
- `next.config.{js,ts,mjs}` - `headers()` (CSP, HSTS), `redirects()`, `images.remotePatterns` (`images.domains` is deprecated)
- Auth config (`auth.ts` / `lib/auth.ts`) - session strategy, cookie flags, OAuth callback URL allowlist
- Every changed `app/**/page.tsx`, `layout.tsx`, `route.ts`, `pages/**` page with `getServerSideProps`, `pages/api/**` API route, and any file marked `'use server'` - on this lens an API route is a Route Handler for every check below
- Every component rendering untrusted HTML (`dangerouslySetInnerHTML`, MDX, `rehype-raw`)
- Every `<form action={serverAction}>` and the action body
- `.env.example` / `.env.local` - any `NEXT_PUBLIC_*` naming a server secret
- `package.json` for auth, sanitizer, and rate-limit libraries, and the RSC runtime version against the Next.js security advisories and `npm audit` - the `next` version (Next bundles the RSC runtime), or `react-server-dom-*` in a non-Next RSC setup. A version still exposed to a known-exploited advisory (CVE-2025-55182, the RSC Flight RCE) is Critical, a later RSC denial-of-service or source-exposure advisory High; the tier stands, and an untouched dependency's label follows the verify pass like any pre-existing finding

**Vite + React Router:**
- Components rendering untrusted HTML
- `.env.example` / `.env` files for any `VITE_*` name that is a server secret
- `index.html` / `vite.config.{js,ts}` for CSP via `server.headers` (dev) or the hosting platform's header config (prod). A `<meta>` CSP is the common Vite shape but is strictly weaker - it cannot carry `frame-ancestors` - so flag it as a hardening gap, not as the Next.js-grade defect
- `vite.config.{js,ts}` `define` (build-time inlining), `server.proxy`, `server.host` and `build.sourcemap`
- React Router `loader` / `action` functions: in a SPA they run in the browser and are UX gating only - authorization lives in the backend API (list it under Could Not Verify); in framework mode with SSR, server loaders / actions are the boundary and need in-handler auth, `createCookieSessionStorage` flags and CSRF on mutating actions like a Route Handler
- API client config (`withCredentials`, CSRF header, token storage)
- `package.json` for sanitizer

When the diff removes a CSP rule, drops `DOMPurify`, or widens a middleware `matcher`, `git log -p` the prior revision to confirm what was protected before.

Use skill: `react-nextjs-patterns` - it owns the canonical Server Action rules (schema validation, authorization, the server-only boundary, `"use server"` as a public endpoint) that this lens scores against; `task-react-review` defers that depth here.

### Step 5 - OWASP Triage

One-row-per-category verdict that funnels which downstream checks run carefully. Step 6 produces the findings; do not duplicate here.

| Risk                          | React signal in diff                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | New Server Action / Route Handler / API route without `await auth()`; missing ownership filter; widened `middleware.ts` `matcher`; `redirect(returnTo)` / `navigate(returnTo)` without allowlist |
| Injection                     | `prisma.x.update({ where, data: Object.fromEntries(formData) })`; raw `formData.get(...)` into ORM without Zod                                    |
| XSS (Injection, split out for React) | `dangerouslySetInnerHTML={{ __html: userInput }}`; markdown render with `rehype-raw`; `DOMPurify` `ADD_TAGS` including `script`/`iframe`   |
| Authentication Failures       | Session cookie override, no rate limit on `/api/auth/*`, JWT verify without `algorithms`, magic-link / OAuth callback without `state` |
| Cryptographic Failures        | Custom crypto on auth path; `crypto.createHash('sha256')` for passwords; `alg: none` accepted in JWT verify                                |
| Security Misconfiguration     | Missing CSP / HSTS; `unsafe-eval`, `unsafe-inline` without a nonce or hash, or a wildcard `*` in `script-src`; `<meta>`-delivered CSP; `remotePatterns` wildcard host; `postMessage` listener without origin check |
| SSRF (Broken Access Control, split out) | `fetch(searchParams.get('url'))` in Route Handler / Server Component without host allowlist                                                |
| Insecure Design              | A protected surface reachable with no in-handler check; authorization decided in one place and re-derived ad hoc in others                  |
| Software Supply Chain Failures | `package.json` / lockfile change with stale advisory; an unpatched `next` / `react` against a known-exploited advisory; Dependabot disabled |
| Data Integrity Failures      | `eval` / `new Function`; `JSON.parse(userInput)` spread into Prisma; `'use server'` file re-exporting non-action utility; webhook handler with missing, post-parse, non-raw-body, or skipped-when-secret-unset signature verification |
| Logging & Alerting Failures  | Sentry browser SDK without `beforeSend` PII strip; client / server logs containing `password` / `token` / `authorization`                  |
| Mishandling of Exceptional Conditions | A `try/catch` around `redirect()` / `auth()` that swallows `NEXT_REDIRECT`; an error path that fails open |

Mark each category `yes` or `no signal in diff`. The rows follow the OWASP Top 10:2025, with XSS and SSRF split out for React.

### Step 6 - Diff-Specific Checks

Apply against changed files. **Gate**: run a sub-block when a related Step 5 row is `yes`, or when its surface appears in the diff regardless of triage verdicts - **authn / authz: any Server Action, Route Handler, API route, `middleware.ts` / `proxy.ts`, auth config or session change - on Vite, any React Router `loader` / `action`, route guard, or API-client auth wiring**; input validation: any of those that reads user input, on either stack; outbound requests / webhooks: any server-side fetch or webhook handler added or changed; Common React vulnerability patterns: any client component or markup changed, **or any change to `middleware.ts` / `proxy.ts`, `next.config.*`, `index.html` or the hosting header config** (the CSP, `remotePatterns` and framing checks live in that block); data protection: any logging, analytics, or env change. Skip a sub-block only when nothing triggers it. This keeps Step 6 a targeted check, not a full OWASP audit.

**Authn / authz**
- [ ] Auth library chosen and consistent (Auth.js / Clerk / Lucia / iron-session); not mixed
- [ ] Every protected Server Action / Route Handler calls `await auth()` **inside** the handler. Middleware does run for Server Actions on Next 15 (they are POSTs to the invoking page's URL), but it is not an authorization boundary: the `matcher` matches the *calling page's* path rather than where the action is defined, and middleware auth was outright bypassable via `x-middleware-subrequest` before 15.2.3 / 14.2.25 / 13.5.9 / 12.3.5 (CVE-2025-29927). Never trust client-side `useSession` for authorization
- [ ] `middleware.ts` / `proxy.ts` `matcher` widening: any path moved to public must have its own in-handler `auth()` check, else the rubric's missing-`auth()` row (Critical when the handler is reachable and its data sensitive or mutable, High otherwise)
- [ ] IDOR: lookups scope by principal in the WHERE clause (`prisma.order.findFirst({ where: { id, ownerId: session.user.id } })`); not a separate post-fetch check
- [ ] Per-tenant queries scoped by `tenantId` from session, never from URL
- [ ] Roles read from the server-validated session, never from request body / search param / header
- [ ] Password hashing (when handled in-app): `bcrypt` (cost >= 10) or `argon2`; never `crypto.createHash`
- [ ] JWT verify: explicit `algorithms` allowlist; `issuer` / `audience` set; never accept `alg: none`
- [ ] Session cookies: `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'`. Auth.js v5 sets all three by default on `__Secure-authjs.session-token`, so flag only an explicit override - and do not recommend `'strict'` on the session cookie: the post-callback redirect chain began cross-site, so a Strict session cookie is withheld and the landing page looks logged out (the state and PKCE cookies are configured separately and stay `lax`). Auth.js also ships its own CSRF cookie, named `__Host-authjs.csrf-token` in a secure context. Flag tokens in `localStorage` / `sessionStorage`
- [ ] OAuth / magic-link callbacks validate `state` / `nonce`; `returnTo` checked against an allowlist, or resolved and compared by origin - `const u = new URL(returnTo, APP_ORIGIN); if (u.origin !== APP_ORIGIN) reject; redirect(u.href)` with `APP_ORIGIN` from config, not the `Host` header (redirecting to `u.pathname` reopens the hole: `/.//evil.com` normalises to pathname `//evil.com`); a `startsWith('/')` prefix test is bypassable, since the URL parser strips tabs and newlines and normalises `/\evil.com` to a cross-origin URL
- [ ] Brute-force protection on `/api/auth/*` via `@upstash/ratelimit` or platform rate limit
- [ ] CSRF: Next.js protects Server Actions by requiring POST and comparing `Origin` against `Host` - action IDs are build-derived identifiers shipped in the public bundle and are **not** a CSRF control. Behind a proxy whose forwarded host differs from the browser origin, legitimate actions are rejected; `experimental.serverActions.allowedOrigins` adds accepted origins, so review it for wildcards and attacker-registrable domains. **Route Handlers get no built-in protection at all**: a cookie-session `POST /api/*` needs its own token or `sameSite` cookie. Bearer-token APIs require CSRF only on cookie auth

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
- [ ] Signature comparison is timing-safe (`crypto.timingSafeEqual`), never `===` or `==`. It takes binary inputs only (`Buffer`, `TypedArray`, `DataView`, `ArrayBuffer`), never strings, and **throws `RangeError` on unequal lengths**, so hash both sides (or length-check first) before comparing; it is also unavailable on the Edge runtime (Next 15 middleware by default; `proxy.ts` on 16 is Node-only)
- [ ] Webhook handlers reject timestamps outside a short window (~5 min); without it any captured request is replayable forever
- [ ] Webhook secrets read server-side only; a webhook route that skips verification when the secret env var is unset is Critical

**Common React vulnerability patterns**
- [ ] `dangerouslySetInnerHTML` on user input wrapped in `DOMPurify.sanitize(html)` with default config - plain `dompurify` needs a DOM, so a Server Component, Server Action or Route Handler needs `isomorphic-dompurify` (or `jsdom`), and it does not run on the Edge runtime at all; flag `ADD_TAGS` containing `script` / `iframe` / `object` / `embed` (`style` is allowed by default - use `FORBID_TAGS: ['style']` where user HTML must not restyle the page); flag `ADD_ATTR` containing event handlers (`onload`, `onclick`, `onerror`) - DOMPurify already allows `src` / `href` on permitted tags and filters them through `ALLOWED_URI_REGEXP`, so those two are not by themselves a bypass
- [ ] `href={userInput}` (Next.js `<Link>` and `<a>`) - scheme validated as `http(s):` (block `javascript:`, `data:`, `vbscript:`)
- [ ] Open redirect: `redirect(searchParams.get('returnTo'))` / `navigate(returnTo)` validated against allowlist or relative-path-only check (React Router `navigate()` is same-origin path navigation - Medium unless the value reaches `window.location` or an anchor `href`; a loader / action `redirect(returnTo)` with an absolute URL navigates the document cross-origin - High)
- [ ] Client-bundle secret audit: any `NEXT_PUBLIC_*` (Next) or `VITE_*` / `import.meta.env` reference (Vite) naming an API key, DB URL or signing secret is Critical - both prefixes are inlined into every browser bundle at build time. On Vite also check `vite.config` `define`, which inlines whatever it is given regardless of prefix
- [ ] `'use server'` files export only Server Actions. Next 15 fails the build on a non-`async` export, so the live risk is a re-exported **async** helper becoming a network-callable mutation
- [ ] An auth guard that calls `redirect()` is not wrapped in a `try/catch`: `redirect()` works by throwing `NEXT_REDIRECT`, so a `catch` around an awaited DB call swallows it and the handler falls through **unauthenticated**. Use `unstable_rethrow(error)` (or an `isRedirectError` check) in every catch on a path that redirects
- [ ] Server Component -> Client Component prop projection: never pass entire ORM rows; project via a DTO or Prisma `select`. Prisma `omit` is a denylist, so a newly added sensitive column leaks - it does not satisfy the add-a-column rule above
- [ ] CSP set as an HTTP response header, not `<meta http-equiv>` (a `<meta>` CSP cannot carry `frame-ancestors` and applies only after parsing starts). A **nonce** CSP must come from `middleware.ts` (`proxy.ts` on 16), which can mint a value per request and is what Next reads to nonce its own bootstrap scripts; `next.config` `headers()` emits a static header, so a nonce there is fixed and attacker-known. Require `default-src 'self'`, `frame-ancestors 'none'`, and no wildcard hosts in `connect-src` / `frame-src`. Under `'strict-dynamic'` browsers ignore `'self'` and every host source in `script-src`, so judge that directive by its nonce, not its host list
- [ ] No `unsafe-eval` in production `script-src`. Flag `'unsafe-inline'` only when no nonce is present: in the canonical strict recipe (`'nonce-{r}' 'strict-dynamic' https: 'unsafe-inline'`) the trailing tokens are fallbacks for older browsers: `'unsafe-inline'` is ignored whenever a nonce is present, `https:` whenever `'strict-dynamic'` is. Dev-only guards via `process.env.NODE_ENV !== 'production'`
- [ ] No `eval` / `new Function(string)` on user input; flag template engines using `new Function` (e.g., `lodash.template`)
- [ ] `postMessage` listeners check `event.origin` against expected
- [ ] `<iframe>` rendering external content has `sandbox` with minimum allowlist; `<iframe src={userInput}>` validated against host allowlist
- [ ] `<a target="_blank">` carries `rel="noreferrer"` where referrer leakage matters (`noopener` has been implied for `target="_blank"` in every current browser since 2021, so its absence is no longer a tabnabbing vector)
- [ ] `next.config.js` `images.remotePatterns` pins hostnames; wildcard subdomains (`*.example.com`) flagged for subdomain-takeover risk, and a bare `**` host (any origin through the image optimizer) - Medium
- [ ] Third-party scripts via `<Script>` justified; SRI `integrity` set for non-first-party scripts

**Data protection**
- [ ] Sentry browser SDK `beforeSend` strips `email` / `password` / `token` / `creditCard`; `sendDefaultPii: false`
- [ ] No tokens / passwords / PII in URLs (search params, path params hit logs + referer)
- [ ] HSTS via `next.config.js` `headers()` or hosting platform; HTTP redirected to HTTPS at edge
- [ ] Server secrets sourced from secret store; `.env.local` gitignored; no literal keys committed
- [ ] `productionBrowserSourceMaps: false` unless intentionally serving

**Collect hardening that is not a specific finding** - controls the diff did not break but that the reviewed surface still lacks - into `## Recommendations`, ordered by the risk they reduce.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, and fill the Summary's `Findings verified` line from its tally. Findings carried from a prior round are not re-verified. Subagent runs skip this - the parent verifies the merged set once.

### Step 7 - Write Report

**Subagent mode** (see Step 3): return this workflow's Output Format document - Summary, OWASP Triage, Findings, Could Not Verify, Recommendations, Next Steps - and write nothing; the parent merges the Findings and Next Steps, reproduces OWASP Triage, Could Not Verify From Diff (with the `+N unverifiable` count) and Recommendations under its `## Scope Sections`, and does not reproduce the Summary. Each finding already carries its `Label`.

**Reconcile (standalone, round 2+).** Re-project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: one `## High-Impact Findings` section and, per prior finding in every tier, a `### [<Label>] <file:line>` heading - the label from its `Label` slot, the bare `file:line` prefix of its `Location` slot (the first when it lists several), then each annotation as its own `_(...)_` group: `_(pre-existing)_` kept, verify's combined `_(pre-existing; newly reachable via <path>)_` written as two groups `_(pre-existing)_ _(newly reachable via <path>)_` (reconcile matches `_(pre-existing)_` exactly), a prior `_(carried from round <N>)_` re-emitted, and an `_(unverified: <reason>)_` finding on a file the diff does not touch also projected with `_(pre-existing)_` (reconcile would otherwise mark it `Addressed`) - followed by `- Issue: <its Issue text>`. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status list and `head_sha`, and render its table and tally under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows carry into the tier the prior report filed them under, at their prior label, with the prior annotation kept and `_(carried from round <N>)_` on the `Location` line (`<N>` = the round the finding first appeared: the prior's own carried marker when present, else the prior report's `round`); a carried finding this round's own pass re-derives publishes once, at the higher of the two labels, keeping the fresh verify annotation plus `_(carried from round <N>)_`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

Then Use skill: `review-report-writer` with `report_type: review-security` and every field it requires: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` and `round` / `prior_head_sha` from the Step 3 round gate, `scope: +sec`, `depth: standard` (this workflow has no depth knob; the writer still requires the field), `stack: typescript-nextjs` (Vite: `typescript-react`), `mode: full`, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present. Print the confirmation line after the report body.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## React Security Review Summary

- **Stack Detected:** React <version> / TypeScript <version>
- **Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Next.js (hybrid App + Pages Router) <version> | Vite + React Router <version>
- **Auth:** Auth.js | Clerk | Lucia | iron-session | Custom | backend-only | none
- **Sanitizer:** DOMPurify | sanitize-html | none
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_. _In subagent mode write exactly `not run (subagent; parent verifies the merged set)`._
- **Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count, +N unverifiable]
- **Round:** <N> _(from round 2 onward)_
- **Notes:** <the package the run was scoped to, a legacy prior report treated as round 1; omit when none>

[2-3 sentence assessment calling out React-specific risks: `dangerouslySetInnerHTML` on user input, `NEXT_PUBLIC_*` secret leak, missing Server Action validation, RSC passing ORM rows to Client Components, missing / weak CSP, open redirect via `returnTo`.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | ...                     |
| XSS                       | ...                     |
| Authentication Failures   | ...                     |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF (Broken Access Control) | ...                  |
| Insecure Design           | ...                     |
| Software Supply Chain Failures | ...                |
| Data Integrity Failures   | ...                     |
| Logging & Alerting Failures | ...                   |
| Mishandling of Exceptional Conditions | ...         |

## Findings

Labels: `Critical` and `High` -> `[Must]`; `Medium` and `Low` -> `[Recommend]` (the verify pass's `Label` column overrides when it ran, so a `[Recommend]` inside `### Critical` is a correct de-escalation of an untouched pre-existing defect, not a mismatch to fix). The tier tracks exploitability, the label tracks the merge gate. Every finding carries its `Label` slot so a consuming workflow never has to re-derive it.

### Critical

- **Label:** [Must] or [Recommend] - the bracketed label itself, emitted as written
- **Location:** [file:line, or comma-separated for multi-site; carry the verify pass's `Annotation` when it is not `-`: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`; a carried finding appends `_(carried from round <N>)_`]
- **Vulnerability class:** [XSS via dangerouslySetInnerHTML | Mass assignment | Auth bypass | Open redirect | NEXT_PUBLIC / VITE_ / `define` secret leak | RSC data leak | CSRF | SSRF | ...]
- **Issue:** [vulnerability in React terms - e.g., "`UserBio` component renders `<div dangerouslySetInnerHTML={{ __html: user.bio }} />` with no sanitizer; `user.bio` is stored verbatim from the profile form Server Action which also lacks Zod"]
- **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether the CDN strips the X-Forwarded-Host header". Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Composed from:** [when the Combined-finding rule merged this: each component and its standalone severity; omit otherwise]
- **Severity rationale:** [tier] per rubric - [which clause applies; for a merged finding cite the Combined-finding rule instead, and for a webhook gap the webhook clause of its tier: Critical verification skipped when the secret is unset, High re-serialized body or non-timing-safe compare, Medium no replay window]
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

[Items that are likely findings but depend on code/infra outside the diff (e.g., a path moved out of the `middleware.ts` matcher whose handler is not in scope - cannot confirm it has its own in-handler `auth()`), saying whether that code is outside the repo or in it but outside this lens (a backend API this lens does not review). State the issue, the severity it would carry if unmitigated, and what to check. Mirror each as a `[Delegate]` Next Step. Do not assign these a confirmed severity in the Findings counts; track them on a separate "+N unverifiable" line. Omit the section when empty.]

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

- [ ] **Step 1**: `behavioral-principles` loaded (accepted as loaded only when a parent runs this lens inline)
- [ ] **Step 2**: Stack confirmed React; `Framework`, `Auth`, `Sanitizer` recorded before any framework-specific check applied
- [ ] **Step 3**: `review-precondition-check` ran with `report_type: review-security` (or subagent mode); round decided from the handle before the diff was read, or the no-op line printed; diff, name-status and log read once and reused
- [ ] **Step 4**: Security surface (middleware, `next.config.js` headers, auth config, changed Server Actions / Route Handlers / RSC / Client Components, `dangerouslySetInnerHTML` sites, env vars, `package.json`) read directly; prior revision consulted when middleware or CSP relaxed; `react-nextjs-patterns` loaded for the Server Action rules (Next.js)
- [ ] **Step 5**: OWASP triage produced one verdict per category, Authentication Failures included (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Step 6**: Diff-specific checks applied for authn/authz, input validation / mass assignment, outbound requests and inbound webhooks, common React vulnerability patterns, and data protection - each run or explicitly skipped because nothing triggered it; severity rubric applied consistently; Combined-finding rule applied where two findings compose on the same handler; every finding has an attack scenario, regression-risk, or topology-dependent label, a `Label`, and a rubric clause
- [ ] **Step 6 (verify)**: `review-finding-verify` ran on the assembled findings; `Dropped` rows excluded; the verify `Label` and `Annotation` columns applied; tally in Summary (subagent runs skip this and write the stated subagent string)
- [ ] **Step 7**: Standalone: prior round reconciled through the projection when round > 1; report written via `review-report-writer` (`branch` = `head_short_name`, `scope: +sec`, `depth: standard`, `stack: typescript-nextjs` / `typescript-react`); confirmation line printed. Subagent: Output Format document returned, nothing written

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
- Approving any of: `dangerouslySetInnerHTML` on user input without `DOMPurify`; `DOMPurify` with `ADD_TAGS: ['script' | 'iframe']` or event-handler `ADD_ATTR`; `NEXT_PUBLIC_*` for a privileged secret; `localStorage` for session tokens; `'use server'` files re-exporting non-action utilities; Server Components passing entire ORM rows to Client Components; `unsafe-eval`, or `unsafe-inline` without a nonce or hash, in production `script-src`; `eval` / `new Function` on user input; `redirect(searchParams.get('next'))` without allowlist; `<meta>`-delivered CSP on a server-rendered app without justification
- Treating client-side `if (user.role === 'admin')` as authorization - it is UX only; the server enforces
- Disabling Server Action validation or middleware auth to silence a failing test - fix the test
- Conflating with general code review or performance review - delegate to their workflows
- Inventing a severity tier outside the four in the rubric
