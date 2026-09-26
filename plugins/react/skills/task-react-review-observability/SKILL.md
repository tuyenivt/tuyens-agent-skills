---
name: task-react-review-observability
description: React / Next.js observability review - web-vitals, Sentry, OpenTelemetry browser + instrumentation.ts, RUM, structured logs, PII.
agent: react-observability-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

Stack-specific delegate of `task-code-review-observability` for React. Library/SDK-level only - infra config (Datadog dashboards, Sentry org settings, log forwarders, alert rules) is out of scope.

## When to Use

- Next.js 16 App Router PR observability review or regression check
- Pre-release or post-incident audit of client-side instrumentation
- Adopting `web-vitals` / Sentry / OpenTelemetry / RUM in a React app
- Auditing error-boundary placement and crash-reporting paths

**Not for:** general review (`task-react-review`), perf (`task-react-review-perf`), infra dashboards/alerts.

## Depth

| Depth      | When                                          | What Runs                              |
| ---------- | --------------------------------------------- | -------------------------------------- |
| `standard` | Default                                       | Steps 1-10 (each subject to its own gate) and Step 12 |
| `deep`     | Requested; an audit for a pre-release or post-incident review runs at `deep` unless `standard` was asked for | The same, plus SLI/SLO (Step 11)       |

Step 12 (verify and write) runs at every depth.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

When run as the umbrella's subagent (`task-react-review` passed the pre-confirmed stack and framework - `Next.js <version>` with its router suffix - the React version, and the below-floor note or none), accept those, write a passed note in the Summary's `Notes`, and skip detection, the scope stop and the floor check below; a standalone run always does all three. Read the TypeScript version from `package.json` either way.

Standalone: Use skill: `stack-detect`. `stack-detect` keys the primary stack on the root manifest, so in a polyglot repo (a React app under `apps/<name>` beside a Rails root) React may appear only under `Additional`; that counts as React when the diff or request sits inside that package - confirm React against the package's own `package.json`, scope the run to it, and name the package in the Summary's `Notes`. If not React, stop and name the detected stack so the user can invoke that stack's observability workflow. With no `next` dependency (Vite, React Router, Remix): print `task-react-review-observability covers Next.js App Router projects only; <project framework> is out of scope - use core's /task-code-review-observability for a generic review.` and stop. Record the `next` and React versions from `package.json` and the Framework as `Next.js <version>`, suffixed ` (Pages Router)` or ` (App + Pages Router)` when `pages/` routes exist. A declared `next` < 16.3 or `react` < 19: write `<package> <declared> is below the plugin floor (Next.js 16.3, React 19); output targets Next.js 16.3 and React 19 - upgrade first.` in the Summary's `Notes` (`<package>` is `Next.js` or `React`; both below is one line, `Next.js 15.5 and React 18.3 are below the plugin floor ...`) and continue. `<declared>` is the version the lockfile resolves for `next` / `react`, else the lower bound of the `package.json` range (`^16.1.0` -> `16.1.0`). Record the full version, not the major.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-observability`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface a fail-fast verbatim, write no report, and stop.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface. A prior report whose Summary `**Mode:**` bullet reads `audit` counts as no prior for a PR run (round 1; its findings carry no diff attribution to reconcile). Otherwise a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits on <head_short_name> since prior observability review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the report write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse.

**Subagent mode** = a parent passed `base_ref` / `head_ref` plus the pre-read diff, name-status list and log (also when the parent runs this lens inline): skip the precondition, the round gate and the diff reads; the surface read still runs.

**Audit mode.** When the request is a full pre-release or post-incident audit (not a single PR), set `audit mode`: skip `review-precondition-check` entirely - there is no diff to gate. The target is the current branch at `HEAD`. With no handle, resolve the writer's refs yourself: `branch` = `base_ref` = `head_ref` = `git rev-parse --abbrev-ref HEAD` (if that returns the literal `HEAD`, the checkout is detached - stop and ask for a branch), and `base_sha` = `head_sha` = `git rev-parse HEAD` - a full SHA, never the literal string `HEAD`, which would poison the next round's `prior_head_sha`. Every surface is in scope and the per-step diff-touch gates in Steps 7-10 are lifted (same effect as the greenfield exception), so no surface is skipped for not being "touched". An audit has no handle, so it skips the round gate and reconciliation and always writes round 1. Without the precondition's clean-tree gate, it reads every audited file at `HEAD` (`git show HEAD:<path>`) so the checkpoint's `head_sha` is what was reviewed. Note `Mode: audit` in the Summary.

### Step 4 - Surface Map

Read instrumentation wiring in the files below, plus every changed file calling `Sentry.*`, `useReportWebVitals`, OTel APIs, or a logger. Produce one verdict per surface: `wired | partial | absent | n/a` with file:line evidence (`n/a` only where the surface cannot exist - server OpenTelemetry on a static export, `output: 'export'`). A missing wire is the finding, not a precondition.

Files to open: `instrumentation.ts` (incl. its `onRequestError` export) and `instrumentation-client.ts` (root or `src/`), `app/global-error.tsx`, `app/**/error.tsx`, `catchError` wrappers (`next/error`), `app/layout.tsx`, `sentry.server.config.ts` (and legacy `sentry.client.config.ts`; a `sentry.edge.config.ts` matters only while Edge-runtime code remains - a `runtime = 'edge'` route, or a `middleware.ts` (the deprecated name for `proxy.ts`; rename it unless it needs Edge) with no `runtime: 'nodejs'` config - since Proxy runs on Node), `next.config.{js,ts,mjs}` (incl. its `instrumentationClientInject` list), `proxy.ts` / `middleware.ts`, `package.json`.

| Surface                 | Look for                                                                                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Web Vitals              | `import { onLCP, onINP, onCLS, onTTFB, onFCP } from 'web-vitals'` + transport; `useReportWebVitals`; or Core Web Vitals collected by the tracker / RUM SDK (Sentry browser tracing, Datadog RUM, Speed Insights) |
| Error tracker + boundary| `@sentry/nextjs` `init`; `app/global-error.tsx` + `app/**/error.tsx`; `catchError` boundaries (`next/error`)    |
| OpenTelemetry (browser) | `WebTracerProvider`, `@opentelemetry/sdk-trace-web`, `@opentelemetry/auto-instrumentations-web`, OTLP exporter    |
| OpenTelemetry (server)  | `instrumentation.ts` registering `@vercel/otel` or `NodeSDK`; `n/a` for a static export (`output: 'export'`) |
| Structured logging      | Logger module posting to RUM/Sentry, client and server; absence shown by `console.log`/`console.error` in prod paths |
| RUM                     | Datadog RUM / Vercel Speed Insights / Cloudflare Web Analytics / custom SDK init at app entry (`@vercel/analytics` is page-view Web Analytics, not RUM) |

**Grouping rule.** If a whole surface is `absent`, produce one High finding listing the missing pieces grouped by target file/symbol - not one finding per sub-check. It also covers a `partial` surface whose missing half is itself entire (tracker installed, no boundaries - or the reverse): group that half as one finding. An `absent` verdict becomes a finding only when its surface's step runs (diff-touched, greenfield, or audit); otherwise it stays a Surface Map row. Split a grouped finding when its parts take different verify verdicts (new code vs pre-existing).

**Greenfield exception.** If 3+ surfaces are `absent`, run Steps 7-9 regardless of their diff-touch gates (Steps 5-6 always run). Step 10 keeps its own gate: with no RUM provider chosen there is nothing to audit.

### Step 5 - Web Vitals

- [ ] `web-vitals` v6 is current (v5 removed the FID export, v4 deprecated it); a direct v6 import can report per soft navigation with `reportSoftNavs: true` in Chromium browsers. Without it - and always under `useReportWebVitals`, which runs Next's bundled pre-v5 copy - tag each metric with the landing URL captured at load and treat it as page-load-scoped (a pathname read at report time files a whole-session CLS / INP under the route the user left from). Flag any `onFID` / `getFID` import; the hook emitting `metric.name === 'FID'` is not a finding; the reporter must drop that metric. Because that hook bundles its own copy, **`web-vitals` absent from `package.json` is not a finding** when the hook is the reporter
- [ ] The three Core Web Vitals reported - LCP, INP, CLS - plus TTFB and FCP as diagnostics; INP must replace FID
- [ ] Wiring: `useReportWebVitals` in a Client Component imported into `app/layout.tsx`
- [ ] Transport is real: `navigator.sendBeacon` or `fetch` with `keepalive: true` to RUM/analytics endpoint; `console.log` reporter is dev-only
- [ ] Each metric carries route/pathname for per-route segmentation
- [ ] Sampling decided once per page view, not per metric, so a sampled view reports all its metrics
- [ ] Attribution enabled when LCP/INP/CLS values exist but root causes are opaque: `experimental.webVitalsAttribution: ['CLS', 'LCP']` in `next.config` when `useReportWebVitals` is the reporter, the `web-vitals/attribution` build when the app imports `web-vitals` directly

### Step 6 - Error Tracker + Error Boundaries

- [ ] Sentry SDK initialized in dedicated config, not in a component body (init inside a component runs after hydration, so early-boot errors are never captured). The client entry is **`instrumentation-client.ts`** (root or `src/`), or a module listed in `next.config` `instrumentationClientInject`, which runs before it and ahead of hydration. `sentry.client.config.ts` is the legacy path and loads only through webpack entry injection: on a Turbopack build (the Next 16 default for `next build`; `--webpack` opts out) it never runs, so a legacy-only client config is High - client capture absent; under `--webpack` it is Medium. Either way, move the init. `instrumentation-client.ts` also exports `onRouterTransitionStart = Sentry.captureRouterTransitionStart` to trace navigations. The server config (and an edge config, while Edge-runtime code remains) loads only because `register()` imports it behind a `NEXT_RUNTIME` check - verify that wiring, or an orphaned config captures nothing
- [ ] `instrumentation.ts` exports `onRequestError` (`export const onRequestError = Sentry.captureRequestError`) - without it server-side request errors are never reported, and it is the reason a server-render failure can be captured even when `error.tsx` does not call `captureException`. Under `output: 'export'` no Next server exists: skip this check and the `register()` server-config check above
- [ ] DSN from env (`NEXT_PUBLIC_SENTRY_DSN` is acceptable - DSN is a public token); `release` and `environment` from build metadata
- [ ] `tracesSampleRate` and `replaysSessionSampleRate` set per env and not `1.0` in prod for a high-traffic app; `replaysOnErrorSampleRate: 1.0` is the recommended value and is not a finding
- [ ] PII scrubbing, keyed to the declared `@sentry/nextjs` major. v11: `dataCollection` governs PII and its defaults collect user info, cookies, request/response headers and bodies, and query params (only token-like values filtered), so on an app that handles PII the finding is an absent or broad `dataCollection` (restrict `cookies` / `httpHeaders` with `{ deny: [...] }` or `false`, `httpBodies: []`, `userInfo: false` where consent is missing), and a leftover `sendDefaultPii` is a removed option. v10: an explicit `sendDefaultPii: true` is the finding. Either major: `beforeSend` strips sensitive keys. `replayIntegration` masks text and inputs by default - flag explicit `maskAllText: false` / `maskAllInputs: false` / `blockAllMedia: false`, and any `networkDetailAllowUrls` capturing bodies
- [ ] `ignoreErrors` entries each commented (ResizeObserver loop, browser-extension noise, navigation network errors)

**Boundary tree** (cite as one finding when missing):

- [ ] `app/global-error.tsx` (root, `"use client"`, renders `<html>`/`<body>`) **and** `app/**/error.tsx` per segment; a component-level `catchError` boundary (`next/error`) is a boundary too
- [ ] **Boundary explicitly calls `Sentry.captureException(error)`** - `error.tsx`, `global-error.tsx` and `catchError` fallbacks do NOT auto-report client-side errors, so a fallback without capture loses the diagnostic (High). `onRequestError` covers **server**-originated errors (Server Components, Route Handlers, Server Actions, Proxy), so it covers the server-originated errors this boundary displays (with a `digest`), not the client-thrown ones. Rate it Medium only when the segment demonstrably renders no client-thrown errors; otherwise High
- [ ] User-facing fallback with a `retry()` action, not a blank screen

**Source maps and CSP:**

- [ ] Source maps uploaded via the Sentry plugin and not served publicly. On Turbopack (the default) the plugin itself sets `productionBrowserSourceMaps: true` and defaults `sourcemaps.deleteSourcemapsAfterUpload` to `true`, but does neither when `productionBrowserSourceMaps` is set explicitly. Flag an explicit `deleteSourcemapsAfterUpload: false`; an explicit `productionBrowserSourceMaps: true` without `deleteSourcemapsAfterUpload: true` (maps public); and an explicit `productionBrowserSourceMaps: false` on Turbopack (no client maps, unreadable traces). Under `--webpack` the plugin emits hidden maps and defaults deletion to `true`
- [ ] Sentry Replay vs strict CSP: Replay injects no inline scripts, so a nonce CSP does not block it. What it does need is `worker-src 'self' blob:` (fallback `child-src blob:`) for its compression worker and `connect-src` to the Sentry ingest host - flag those, not an inline-script conflict

### Step 7 - OpenTelemetry / Tracing

_Skip unless diff touches OTel config or `instrumentation.ts`, or adds `runtime = 'edge'` to a route (or greenfield / audit mode applies)._

**Browser:**

- [ ] `WebTracerProvider` + `BatchSpanProcessor` + OTLP exporter; `@opentelemetry/auto-instrumentations-web` enables `fetch`, `xhr`, `document-load`, `user-interaction`
- [ ] `traceparent` propagated on outbound fetch to own backend; backend host in the `propagateTraceHeaderCorsUrls` option of `FetchInstrumentation` / `XMLHttpRequestInstrumentation` (it is per-instrumentation, not a provider-level setting); CORS allows `traceparent`
- [ ] Sampling explicit and aggressive on client (`TraceIdRatioBasedSampler`); aligned with backend ratio

**Server (Next.js `instrumentation.ts`):**

- [ ] `register()` initializes `@vercel/otel` (`registerOTel({ serviceName })`, preferred) or a raw `NodeSDK` imported behind `process.env.NEXT_RUNTIME === 'nodejs'`
- [ ] Raw `NodeSDK` setup includes: `BatchSpanProcessor` (not `SimpleSpanProcessor`), `SIGTERM` -> `sdk.shutdown()`
- [ ] No `runtime = 'edge'` route: the Edge runtime is deprecated and a `NodeSDK` never reaches it, so the route itself is the finding (move it to Node), not a missing Edge fallback
- [ ] Resource attributes: `service.name`, `service.version`, `deployment.environment.name` (`deployment.environment` is deprecated in OTel semconv 1.27+) from build metadata
- [ ] Sampler aware of high-volume noise (health checks, prefetches) - custom `Sampler` dropping them beats flat ratio

### Step 8 - Structured Logging

_Skip unless diff modifies logging utilities or adds `console.*` in prod paths (or greenfield / audit mode applies)._

- [ ] No `console.log` / `console.error` in prod paths, client or server (Server Actions and Route Handlers included) - routes to `Sentry.logger.*` (v11 sends logs with no enable flag - filter with `beforeSendLog`; v10 needs `enableLogs: true`) or a structured logger; `captureException` for errors, never `captureMessage` for routine logs, which opens an issue per line
- [ ] No log calls in render bodies (fires every render)
- [ ] Sensitive-field hygiene: payloads exclude `password`, `token`, `authorization`, `Cookie`, raw responses with PII; `beforeBreadcrumb` strips known keys
- [ ] Business actions (signup, checkout step, payment) emit structured RUM events - not page views alone

### Step 9 - Identity, Session, Trace Correlation

_Skip unless diff touches auth, RUM SDK init, or Sentry context wiring - `setUser` / `setTag` / `setContext` (or greenfield / audit mode applies)._

- [ ] `Sentry.setUser({ id })` after auth; `Sentry.setUser(null)` on logout; `email` only with consent
- [ ] `Sentry.setTag` for low-cardinality dimensions (tenant, role, flag); no PII or unbounded values (no `userId` as tag)
- [ ] `Sentry.setContext` for build version, sanitized route/query
- [ ] **`extra` / `setContext` payloads project user to `{ id }` (or `{ id, role }`)** - never pass `session.user` whole
- [ ] Same `userId` / `sessionId` / `traceId` flow into RUM, Sentry, and OTel so a slow user cross-references to errors and traces

### Step 10 - RUM Integration

_Skip on apps without a chosen RUM provider. Greenfield and audit mode lift the diff-touch gates, not this one: with no provider chosen there is nothing to audit, so the Surface Map row stays `absent` and no finding is raised. Recommend adopting one instead._

- [ ] SDK initialized once at app entry, before any router hook fires (first navigation otherwise unrecorded)
- [ ] Client-side navigation tracked via `usePathname` or `onRouterTransitionStart`; vendor auto-detect verified
- [ ] Custom events for business-critical interactions (checkout step completed, plan upgraded)
- [ ] Opt-out respected where jurisdiction requires: `navigator.globalPrivacyControl` is the enforceable modern signal. Do Not Track was discontinued in 2019 and removed from Safari and Firefox's UI, so a `navigator.doNotTrack` check alone is not compliance
- [ ] Privacy posture documented when Session Replay / session recording is on

### Step 11 - Health and SLIs (deep only)

These are programme-level gaps, not surface wiring: report each missing checkbox below as one finding with `Surface: Health & SLI` (merge two only when one fix closes both), and put any narrative in Recommendations. Alerting and synthetics are infra: raise them only when monitoring-as-code lives in the repo, otherwise as one Recommendations line.

- [ ] Critical journeys have at least one SLI (LCP < 2.5s, INP < 200ms, CLS < 0.1, or custom RUM metric)
- [ ] SLOs documented in code (route config / module README) - not free-floating in Confluence
- [ ] Error rate per route alerted via Sentry/RUM
- [ ] Synthetic checks (Datadog Synthetics, Checkly) complement RUM for critical journeys
- [ ] Bundle-size budget per route enforced in CI with a tool that can fail the build - `size-limit` or `bundlesize2`. `next experimental-analyze` (Turbopack; `@next/bundle-analyzer` is webpack-only) only visualizes, and `bundlesize` is unmaintained, so neither enforces a budget on its own

### Step 12 - Verify Findings and Write Report

**Verify (every depth - not gated by Step 11).** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, and fill the Summary's `Findings verified` line from its tally. Findings carried from a prior round are not re-verified. Subagent runs skip this - the parent verifies the merged set once. Audit mode: `review-finding-verify` requires a diff it does not have, so run only its claim check - confirm each finding's cited `file:line` still says what the finding says. A claim you cannot settle from the file stays, marked `_(unverified: <reason>)_`, and only a claim the file contradicts is dropped; an absence confirmed by reading the construct that would hold it (`package.json` without the SDK) is confirmed. Skip diff-attribution entirely (no `Pre-existing` verdicts, no `_(pre-existing)_` annotations); the tally is `<N> confirmed, 0 reattributed, <U> unverified, <K> dropped`, plus `(<F> false positive, 0 resolved by diff)` only when K > 0. An audit finding carries no annotation except `_(unverified: <reason>)_`.

**Subagent mode** (see Step 3): skip verification (the parent verifies the merged set once), return this workflow's Output Format document - Summary, Surface Map, Findings, Recommendations, Next Steps - and write nothing; the parent merges the Findings and Next Steps and carries the Surface Map and Recommendations into its own `## Scope Sections`. Each finding already carries its `Label`.

**Reconcile (standalone, round 2+).** Re-project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: one `## High-Impact Findings` section and, per prior finding in every tier, a `### [<Label>] <file:line>` heading - the label from its `Label` slot, the bare `file:line` prefix of its `Location` slot (the first when it lists several), then each annotation as its own `_(...)_` group: `_(pre-existing)_` kept, verify's combined `_(pre-existing; newly reachable via <path>)_` written as two groups `_(pre-existing)_ _(newly reachable via <path>)_` (reconcile matches `_(pre-existing)_` exactly), a prior `_(carried from round <N>)_` re-emitted, and an `_(unverified: <reason>)_` finding on a file the diff does not touch also projected with `_(pre-existing)_` (reconcile would otherwise mark it `Addressed`) - followed by `- Issue: <its Issue text>`. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status list and `head_sha`, and render its table and tally under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows carry into the tier the prior report filed them under, at their prior label, with the prior annotation kept and `_(carried from round <N>)_` on the `Location` line (`<N>` = the round the finding first appeared: the prior's own carried marker when present, else the prior report's `round`); a carried finding this round's own pass re-derives publishes once, at the higher of the two labels, keeping the fresh verify annotation plus `_(carried from round <N>)_`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

Then Use skill: `review-report-writer` with `report_type: review-observability` and every field it requires: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` and `round` / `prior_head_sha` from the Step 3 round gate, `scope: +obs`, `depth` as resolved, `stack: typescript-nextjs`, `mode: full`, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present. Print the confirmation line after the report body. Audit mode: `branch` = `base_ref` = `head_ref` = the current branch name, `base_sha` = `head_sha` = the full `HEAD` SHA, `round: 1`. The report body is also the chat deliverable.

## Output Format

The fence below delimits the template for display only - it is not part of the report, and neither is this paragraph. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Buckets:** High = a failure class that cannot be detected or diagnosed (an absent surface, a boundary that captures nothing, a server error path with no `onRequestError`, a legacy-only `sentry.client.config.ts` on a Turbopack build) or a PII leak; Medium = detectable but slow, noisy or costly to diagnose (no route tag, no release, a 1.0 sample rate on a high-traffic app, an orphaned config); Low = hygiene with no incident cost today. **Labels:** High -> `[Must]`; Medium / Low -> `[Recommend]`; the verify pass's `Label` column overrides when it ran. The bucket tracks impact, the label tracks the merge gate - a pre-existing absence can sit in High Impact carrying `[Recommend]`.

**Omit empty buckets.** Group by Surface within a bucket when more than two findings share one, under a `**<Surface>**` sub-heading; otherwise list flat. An absent surface collapses into one finding per the Step 4 grouping rule.

**The `Findings verified` parenthetical** is written only when K > 0. In subagent mode write exactly `not run (subagent; parent verifies the merged set)` in that slot.

**Set `Overall`** to the third form when 3+ Surface Map rows are `absent`; the counts are always given, by bucket.

**Out-of-lens defects** that expose data or break the build (a bundler `define` inlining secrets): one `out of lens: <one line>` at the end of `## Findings` and a `[Delegate]` Next Step naming the owning workflow.

**Use `absent` consistently** in the Surface Map (not `none` / `missing` / `not wired`).

```markdown
## React Observability Review Summary

- **Stack:** React <version> / TypeScript <version>
- **Framework:** Next.js <version>{ <Step 2 router suffix>}
- **RUM:** Datadog RUM | Vercel Speed Insights | Cloudflare Web Analytics | custom | absent
- **Depth:** standard | deep
- **Mode:** PR | audit
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff)
- **Round:** <N> _(from round 2 onward)_
- **Notes:** <the Step 2 below-floor line, the package the run was scoped to, a legacy or audit prior report treated as round 1; omit when none>
- **Overall:** Adequate | Gaps Found [High/Medium/Low counts] | Gaps Found [counts] - Greenfield: <n> surfaces absent

## Surface Map

| Surface                  | Verdict                        | Evidence                                         |
| ------------------------ | ------------------------------ | ------------------------------------------------ |
| Web Vitals               | wired / partial / absent       | [file:line or "no web-vitals reporter found"]    |
| Error tracker + boundary | wired / partial / absent       | [file:line]                                      |
| OpenTelemetry (browser)  | wired / partial / absent       | [file:line]                                      |
| OpenTelemetry (server)   | wired / partial / absent / n/a | [file:line; n/a for `output: 'export'`]          |
| Structured logging       | wired / partial / absent       | [file:line]                                      |
| RUM                      | wired / partial / absent       | [file:line]                                      |

## Findings

### High Impact

- **Label:** [Must | Recommend]
- **Location:** [file:line; for an absent package or file, the manifest that would hold it (`package.json:1`), never a bare directory; carry the verify pass's `Annotation` when it is not `-`: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`; a carried finding appends `_(carried from round <N>)_`]
- **Gap Class:** [missing-wire | misconfigured | unsafe-default | pii-leak | noise]
- **Surface:** [Web Vitals | Error tracker + boundary | OpenTelemetry (browser) | OpenTelemetry (server) | Structured logging | RUM | Identity | Health & SLI]
- **Issue:** [name the React/SDK idiom: missing INP reporter, no `app/global-error.tsx`, `error.tsx` without `Sentry.captureException`, `useReportWebVitals` missing route correlation, OTel `traceparent` not propagated, source maps served publicly, `extra: { user: session.user }` shipping PII]
- **Impact:** [diagnosability | alertability | cost | privacy]
- **Suggested Instrumentation:** [specific code/config: API call, file to add, exact SDK option]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Recommendations

[Structural improvements not tied to a single finding - e.g., enable `experimental.webVitalsAttribution`; move Sentry client init from `sentry.client.config.ts` to `instrumentation-client.ts`; adopt `@vercel/otel` over raw `NodeSDK`]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: ops] - [action]
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: as the umbrella's subagent, the parent's stack, framework, React version and below-floor note accepted; standalone: a `next` dependency confirmed (none: the out-of-scope line printed and the run stopped), versions and the router-suffixed Framework recorded, a below-floor `next` / `react` noted in `Notes`
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-observability` (or subagent mode); round decided from the handle before the diff was read, or the no-op line printed; diff, name-status and log read once; in audit mode the precondition, round gate and reconcile were skipped, `Mode: audit` recorded, round 1 written with refs from `HEAD` as full SHAs
- [ ] Step 4: surface map produced with 6 verdicts and evidence; `Overall` set with counts, and the greenfield suffix added when 3+ rows are `absent`; grouping rules applied
- [ ] Step 5: web-vitals current major, the three Core Web Vitals plus TTFB and FCP, no `onFID` / `getFID` import and the `useReportWebVitals` reporter drops `metric.name === 'FID'`, real transport, route correlation, sampling at reporter
- [ ] Step 6: Sentry client init in `instrumentation-client.ts` or an `instrumentationClientInject` module (a legacy-only client config High on Turbopack), `onRequestError` exported (skipped under `output: 'export'`), server/edge configs imported from `register()`, env-driven release/env, sample rates per env, PII scrub keyed to the Sentry major, error-boundary tree with explicit `captureException`, source maps uploaded but not public, Replay vs CSP conflict checked
- [ ] Step 7: OTel browser SDK + traceparent propagation; `instrumentation.ts` with shutdown and BatchSpanProcessor for raw `NodeSDK`, no `runtime = 'edge'` route (skipped per gate when applicable)
- [ ] Step 8: no `console.*` in client or server prod paths, no log in render, sensitive-field hygiene, RUM events for business actions (skipped per gate)
- [ ] Step 9: `setUser({ id })`, low-cardinality tags, `extra` projects user to `{ id }`, cross-tool correlation (skipped per gate)
- [ ] Step 10: RUM SDK init order, client navigation tracking, custom events, opt-out signal respected (skipped per gate)
- [ ] Step 11: SLIs, SLOs in code, per-route error alerts, synthetics, bundle budgets (deep only)
- [ ] Step 12: findings verified at every depth with `Label` and `Annotation` carried (audit mode: claims only; subagent: skipped, Output Format document returned, nothing written); standalone: prior round reconciled through the projection when round > 1, report written via `review-report-writer` with `branch` = `head_short_name`; confirmation printed

## Avoid

- Generic advice when a React/SDK idiom exists ("add metrics" vs "register `onINP` reporter via `useReportWebVitals` posting through `sendBeacon`")
- Per-checkbox findings when a whole surface is absent - collapse per the Step 4 grouping rule
- Approving Sentry init inside a component body - re-runs every mount, double-reports
- Approving `error.tsx` / `global-error.tsx` / `catchError` fallbacks that render without calling `Sentry.captureException` - Next.js does not auto-capture
- Approving FID-only web-vitals reporting (INP replaced FID in 2024)
- Approving `web-vitals` reporter wired only to `console.log`
- Approving `replaysSessionSampleRate: 1.0` in prod on a high-traffic app, or Replay with `maskAllText` / `maskAllInputs` / `blockAllMedia` set to `false`
- Approving `extra: { user: session.user }` or `setContext` payloads carrying email/phone/address - project to `{ id }`
- Approving public source-map serving in production
- Approving missing source-map upload to Sentry - production stack traces unreadable
- Approving `userId`/`orderId` as Sentry tags (unbounded cardinality)
- Approving Sentry Replay on a strict CSP without `worker-src 'self' blob:` and a `connect-src` entry for the ingest host
- Approving error boundaries with a blank-screen fallback
- Infra scope (Datadog dashboards, Sentry org settings, log forwarders, alert rules) - delegate to ops review
- State-changing git commands
- Inventing a `Surface` value outside the eight in the Findings template - the first six match the Surface Map rows exactly
