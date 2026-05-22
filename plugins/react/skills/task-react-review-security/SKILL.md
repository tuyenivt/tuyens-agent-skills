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

Stack-specific delegate of `task-code-review-security` for React / Next.js / Vite. Preserves the parent's invocation, diff-resolution, and output contract so callers see a stable shape.

## When to Use

- Reviewing a Next.js or Vite + React PR for security regressions
- Pre-deployment hardening pass on auth, upload, payment, or PII paths
- Auditing a Server Action, Route Handler, middleware, OAuth callback, or new auth flow

**Not for:** performance (`task-react-review-perf`), general review (`task-react-review`), incidents (`/task-oncall-start`), backend API of the React app (run against the backend repo).

**No depth knob.** Security regressions have cliff-edge consequences (XSS account takeover, secret in bundle). Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                  |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Working XSS via `dangerouslySetInnerHTML` on user input, privileged secret in `NEXT_PUBLIC_*`, auth bypass on Server Action / Route Handler, mass exfiltration via RSC passing entire ORM row to Client Component, `eval` / `new Function` on user input. Blocks merge. |
| **High**     | Missing input validation on a Server Action that mutates, missing `auth()` on a privileged handler, IDOR via path param without ownership check, open redirect via unchecked `redirect(userInput)`, CSRF on cookie-session form, `localStorage` for session tokens. |
| **Medium**   | Hardening gap with mitigating control (CSP missing nonce but no untrusted HTML rendered), weak rate limit on auth route, Sentry collecting PII without redaction, `<meta>`-delivered CSP on SSR app, `npm audit` advisory not yet exploited. |
| **Low**      | Defense-in-depth, advisory below actively-exploited threshold, hardening without a concrete current attack scenario.                                                                                                        |

**Combined-finding rule.** When two findings *compose* on the same handler / component / route segment into a worse threat than either alone, file as one finding at the elevated severity citing each component (e.g., missing `auth()` + mass assignment via `Object.fromEntries(formData)` on the same Server Action = Critical unauthenticated admin override; `dangerouslySetInnerHTML` + sanitizer with `ADD_TAGS: ['script']` on the same component = Critical working XSS; `NEXT_PUBLIC_API_KEY` + that key calling an admin API from the browser = Critical exposed admin key). If either is independently exploitable, file separately. When co-location is unclear from the diff, file separately and add `Note: Combined-finding rule applies if both land on the same handler; verify before merge` to the lower-severity entry.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                             | Meaning                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------ |
| `/task-react-review-security`          | Review current branch vs its base; fails fast on trunk                   |
| `/task-react-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                               |
| `/task-react-review-security pr-<N>`   | Review PR head fetched into local branch `pr-<N>` (user runs the fetch)  |

When invoked as a subagent of `task-code-review-security`, Step 3 is skipped and pre-read diff/log are reused.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Governs every subsequent step. Skip re-load when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept the pre-confirmed stack when invoked as a delegate of `task-code-review-security` or subagent of `task-react-review`. If not React, stop and redirect to `/task-code-review-security`.

Record for the Summary block: `Framework` (Next.js App Router / Pages Router / Vite + React Router), `Auth` (Auth.js / Clerk / Lucia / iron-session / Custom / backend-only), `Sanitizer` (DOMPurify / sanitize-html / none).

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (default: current branch). On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip entirely when the parent passed pre-read artifacts. If precondition fails, surface the message verbatim and stop. Never run state-changing git.

### Step 4 - Read the Security Surface

Open the files that actually wire security before applying checklists, so findings cite real lines.

**Next.js:**
- `middleware.ts` - auth checks, `matcher` scope, security headers, redirect logic
- `next.config.{js,ts,mjs}` - `headers()` (CSP, HSTS), `redirects()`, `images.domains` / `remotePatterns`
- Auth config (`auth.ts` / `lib/auth.ts`) - session strategy, cookie flags, OAuth callback URL allowlist
- Every changed `app/**/page.tsx`, `layout.tsx`, `route.ts`, and any file marked `'use server'`
- Every component rendering untrusted HTML (`dangerouslySetInnerHTML`, MDX, `rehype-raw`)
- Every `<form action={serverAction}>` and the action body
- `.env.example` / `.env.local` - any `NEXT_PUBLIC_*` naming a server secret
- `package.json` for auth, sanitizer, and rate-limit libraries

**Vite + React Router:**
- Components rendering untrusted HTML
- `index.html` / `vite.config.{js,ts}` for CSP via `<meta>` or `server.headers`
- API client config (`withCredentials`, CSRF header, token storage)
- `package.json` for sanitizer

When the diff removes a CSP rule, drops `DOMPurify`, or widens a middleware `matcher`, `git log -p` the prior revision to confirm what was protected before.

### Step 5 - OWASP Triage

One-row-per-category verdict that funnels which downstream checks run carefully. Steps 6-7 produce the findings; do not duplicate here.

| Risk                          | React signal in diff                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | New Server Action / Route Handler without `await auth()`; missing ownership filter; widened `middleware.ts` `matcher`                       |
| Injection                     | `prisma.x.update({ data: Object.fromEntries(formData) })`; raw `formData.get(...)` into ORM without Zod                                    |
| XSS                           | `dangerouslySetInnerHTML={{ __html: userInput }}`; markdown render with `rehype-raw`; `DOMPurify` `ADD_TAGS` including `script`/`iframe`   |
| Cryptographic Failures        | Custom crypto on auth path; `crypto.createHash('sha256')` for passwords; `alg: none` accepted in JWT verify                                |
| Security Misconfiguration     | Missing CSP / HSTS; `unsafe-eval` / `unsafe-inline` / wildcard `*` in `script-src`; `<meta>`-delivered CSP; `remotePatterns` wildcard host  |
| SSRF                          | `fetch(searchParams.get('url'))` in Route Handler / Server Component without host allowlist                                                |
| Insecure Design (A04)         | Middleware allows by default; auth enforced per-route instead of router-level default-deny                                                 |
| Vulnerable Components (A06)   | `package.json` / lockfile change with stale advisory; Dependabot disabled                                                                  |
| Data Integrity Failures (A08) | `eval` / `new Function`; `JSON.parse(userInput)` spread into Prisma; `'use server'` file re-exporting non-action utility                    |
| Logging & Monitoring (A09)    | Sentry browser SDK without `beforeSend` PII strip; client / server logs containing `password` / `token` / `authorization`                  |

Mark each category `yes` or `no signal in diff`.

### Step 6 - Diff-Specific Checks

Apply against changed files.

**Authn / authz**
- [ ] Auth library chosen and consistent (Auth.js / Clerk / Lucia / iron-session); not mixed
- [ ] Every protected Server Action / Route Handler calls `await auth()` **inside** the handler (middleware does not run for Server Actions in all versions); never trust client-side `useSession` for authorization
- [ ] `middleware.ts` `matcher` widening: any path moved to public must have its own in-handler `auth()` check, else Critical
- [ ] IDOR: lookups scope by principal in the WHERE clause (`prisma.order.findFirst({ where: { id, ownerId: session.user.id } })`); not a separate post-fetch check
- [ ] Per-tenant queries scoped by `tenantId` from session, never from URL
- [ ] Roles read from the server-validated session, never from request body / search param / header
- [ ] Password hashing (when handled in-app): `bcrypt` (cost >= 10) or `argon2`; never `crypto.createHash`
- [ ] JWT verify: explicit `algorithms` allowlist; `issuer` / `audience` set; never accept `alg: none`
- [ ] Session cookies: `httpOnly: true`, `secure: true` in prod, `sameSite: 'lax'` (or `'strict'` for high-sensitivity); flag tokens in `localStorage` / `sessionStorage`
- [ ] OAuth / magic-link callbacks validate `state` / `nonce`; `returnTo` checked against allowlist or `url.startsWith('/') && !url.startsWith('//')`
- [ ] Brute-force protection on `/api/auth/*` via `@upstash/ratelimit` or platform rate limit
- [ ] CSRF: cookie-session forms either rely on Next.js Server Action Origin + action-ID protection, or use `sameSite: 'strict' | 'lax'` cookies; bearer-token APIs require CSRF only on cookie auth

**Input validation / mass assignment**
- [ ] Every Server Action and Route Handler validates input first: `Schema.parse(formData)` / `safeParse`; `zod-form-data` for typed FormData parsing
- [ ] No `prisma.x.update({ data: Object.fromEntries(formData) })` / `data: parsedJson` - require explicit Zod schema with field allowlist
- [ ] No privilege fields (`role`, `isAdmin`, `ownerId`, `tenantId`, `verified`) on user-facing input schemas - server-set only
- [ ] Response is a DTO, not a raw ORM row - prevents `passwordHash` / `mfaSecret` leak as columns are added
- [ ] Dynamic route segments (`params.id`) Zod-validated (UUID / int / slug) before reaching ORM
- [ ] File uploads: type via `file-type` content sniff (not `file.type`), size capped, `instanceof File` checked
- [ ] Server Action / Route Handler return value treated as a public surface - no privileged / internal fields

**Common React vulnerability patterns**
- [ ] `dangerouslySetInnerHTML` on user input wrapped in `DOMPurify.sanitize(html)` with default config; flag `ADD_TAGS` containing `script` / `iframe` / `object` / `embed` / `style`; flag `ADD_ATTR` containing event handlers (`onload`, `onclick`, `onerror`) or URL attrs (`src`, `href`)
- [ ] `href={userInput}` (Next.js `<Link>` and `<a>`) - scheme validated as `http(s):` (block `javascript:`, `data:`, `vbscript:`)
- [ ] Open redirect: `redirect(searchParams.get('returnTo'))` / `navigate(returnTo)` validated against allowlist or relative-path-only check
- [ ] `NEXT_PUBLIC_*` audit: any `NEXT_PUBLIC_*` naming an API key / DB URL / signing secret is Critical - those compile into every browser bundle
- [ ] `'use server'` files export only Server Actions; re-exported non-action utilities become network-callable mutations
- [ ] Server Component -> Client Component prop projection: never pass entire ORM rows; project via DTO or Prisma `select` / `omit`
- [ ] CSP set as HTTP response header (via `next.config.js` `headers()` or `middleware.ts`), not `<meta http-equiv>`; `default-src 'self'`; `script-src 'self' 'nonce-XXX' 'strict-dynamic'`; `frame-ancestors 'none'`; no wildcard hosts in `script-src` / `connect-src` / `frame-src`
- [ ] No `unsafe-eval` / `unsafe-inline` in production `script-src`; dev-only guards via `process.env.NODE_ENV !== 'production'`
- [ ] No `eval` / `new Function(string)` on user input; flag template engines using `new Function` (e.g., `lodash.template`)
- [ ] `postMessage` listeners check `event.origin` against expected
- [ ] `<iframe>` rendering external content has `sandbox` with minimum allowlist; `<iframe src={userInput}>` validated against host allowlist
- [ ] `<a target="_blank">` includes `rel="noopener noreferrer"`
- [ ] `next.config.js` `images.remotePatterns` pins hostnames; wildcard subdomains (`*.example.com`) flagged for subdomain-takeover risk
- [ ] Third-party scripts via `<Script>` justified; SRI `integrity` set for non-first-party scripts

**Data protection**
- [ ] Sentry browser SDK `beforeSend` strips `email` / `password` / `token` / `creditCard`; `sendDefaultPii: false`
- [ ] No tokens / passwords / PII in URLs (search params, path params hit logs + referer)
- [ ] HSTS via `next.config.js` `headers()` or hosting platform; HTTP redirected to HTTPS at edge
- [ ] Server secrets sourced from secret store; `.env.local` gitignored; no literal keys committed
- [ ] `productionBrowserSourceMaps: false` unless intentionally serving

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write the assembled output to the report file; print the confirmation line.

## Output Format

```markdown
## React Security Review Summary

**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Auth:** Auth.js | Clerk | Lucia | iron-session | Custom | backend-only
**Sanitizer:** DOMPurify | sanitize-html | none
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

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

### Critical

- **Location:** [file:line, or comma-separated for multi-site]
- **Vulnerability class:** [XSS via dangerouslySetInnerHTML | Mass assignment | Auth bypass | Open redirect | NEXT_PUBLIC secret leak | RSC data leak | CSRF | SSRF | ...]
- **Issue:** [vulnerability in React terms - e.g., "`UserBio` component renders `<div dangerouslySetInnerHTML={{ __html: user.bio }} />` with no sanitizer; `user.bio` is stored verbatim from the profile form Server Action which also lacks Zod"]
- **Attack scenario:** [pick one and label: (a) concrete exploit walkthrough; (b) "Regression risk: next refactor silently removes one of these protections"; (c) "Topology-dependent: depends on whether the CDN strips the X-Forwarded-Host header". Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [React remediation with code - Zod schema, `DOMPurify.sanitize` wrapper, `nonce`-CSP via middleware, `select`-projected DTO, `returnTo` allowlist, etc.]

### High / Medium / Low

[Same structure. Omit sections with no findings. If all empty, state "No security issues found."]

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `nonce`-based CSP via middleware", "Replace `localStorage` token with httpOnly cookie", "Migrate Pages Router auth to Auth.js v5", "Add `pnpm audit` to CI".]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, dependency upgrade, or threat-model exercise). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Wrap `user.bio` in `DOMPurify.sanitize` (default config) and add Zod schema to `updateProfile` Server Action"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `pnpm audit` and upgrade flagged packages"]

_Omit if no security issues found._
```

## Self-Check

Aligns 1:1 with the Workflow steps above.

- [ ] **Step 1**: `behavioral-principles` loaded (or accepted as pre-loaded from a parent workflow)
- [ ] **Step 2**: Stack confirmed React; `Framework`, `Auth`, `Sanitizer` recorded before any framework-specific check applied
- [ ] **Step 3**: `review-precondition-check` ran (or handle received from parent); `base_ref` / `head_ref` / `head_matches_current` captured; diff and log read once and reused; on `head_matches_current=false`, explicit user approval obtained before review (skipped when subagent)
- [ ] **Step 4**: Security surface (middleware, `next.config.js` headers, auth config, changed Server Actions / Route Handlers / RSC / Client Components, `dangerouslySetInnerHTML` sites, env vars, `package.json`) read directly; prior revision consulted when middleware or CSP relaxed
- [ ] **Step 5**: OWASP triage produced one verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Step 6**: Diff-specific checks applied for authn/authz, input validation / mass assignment, common React vulnerability patterns, data protection; severity rubric applied consistently; Combined-finding rule applied where two findings compose on the same handler; every finding has an attack scenario, regression-risk, or topology-dependent label
- [ ] **Step 7**: Report written to file via `review-report-writer`; confirmation line printed

**Requires repo / infra access (note as "could not verify from diff alone - flag for separate audit" when not visible):**

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
