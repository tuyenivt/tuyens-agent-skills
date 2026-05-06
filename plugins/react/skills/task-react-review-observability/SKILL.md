---
name: task-react-review-observability
description: React observability review for `web-vitals` reporting (LCP / INP / CLS / TTFB), Sentry browser SDK + React error boundaries, OpenTelemetry browser instrumentation, Next.js `instrumentation.ts` server-side tracing, structured client logging, and RUM correlation. Library-level focus, not infra. Use when reviewing a React PR for observability gaps, before releasing a new app, or after an incident where client-side diagnosis was slow. Stack-specific override of task-code-review-observability for React.
agent: react-tech-lead
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# React Observability Review

## Purpose

React-aware observability review that names `web-vitals` (`onLCP`, `onINP`, `onCLS`, `onTTFB`, `onFCP`), Sentry browser SDK + React error boundaries (`Sentry.ErrorBoundary`, `Sentry.withErrorBoundary`, `BrowserTracing` integration), OpenTelemetry web SDK (`@opentelemetry/sdk-trace-web` + `@opentelemetry/auto-instrumentations-web`), Next.js `instrumentation.ts` for server-side OTel, structured client logging, and RUM correlation directly instead of routing through the generic frontend adapter. Focuses on whether React production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for React. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a Next.js or Vite + React PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new React app or major feature
- Post-incident review when client-side diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / Sentry / `web-vitals` in a React app
- Auditing error boundary placement and crash reporting paths

**Not for:**

- General React code review (use `task-react-review`)
- React performance issues with a known bottleneck (use `task-react-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules) - those are not in source code

## Depth Levels

| Depth      | When to Use                                            | What Runs                                          |
| ---------- | ------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single component or route                              | Logging + error boundary + web-vitals check only   |
| `standard` | Default - full React observability review              | All steps                                          |
| `deep`     | Pre-release of a critical app, or post-incident review | All steps + SLI/SLO suggestions per critical route |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                  | Meaning                                                                                               |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-react-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-react-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-react-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-react-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm React. If invoked as a subagent of a React-aware parent, accept the pre-confirmed stack. If not React, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect framework: Next.js (App Router / Pages Router) vs Vite + React Router. Record `Framework: ...`. Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. On approval, read diff + commit log once and reuse. Skip entirely if running as a subagent and the parent passed the handle.

If the precondition check stops with a fail-fast message, surface it verbatim and stop. Do not run any state-changing git command.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (web-vitals / error tracker / OTel browser / OTel server (Next.js) / structured logging) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below).

**Grouping rule.** When a whole surface is `absent` (no `web-vitals`, no Sentry SDK init, no OTel browser SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/symbol they should land in. Per-callsite findings only apply when the surface exists and a specific callsite misuses it.

Then open the files that actually configure observability so findings cite real lines:

**Next.js (App Router):**

- `instrumentation.ts` (Next.js convention; runs once per process lifecycle for both Node and Edge runtimes when `experimental.instrumentationHook` is enabled in older versions; on by default in Next 15+)
- `app/global-error.tsx` (root error boundary), `app/**/error.tsx` (per-route error boundaries)
- `app/layout.tsx` and any provider component setting up `Sentry.ErrorBoundary` / RUM SDK / web-vitals reporter
- `next.config.{js,ts,mjs}` - Sentry webpack plugin (source map upload), OTel exporter env vars
- `package.json` - confirm `@sentry/nextjs`, `web-vitals`, `@opentelemetry/sdk-trace-web` (browser), `@opentelemetry/sdk-node` (Next.js server) presence
- `app/**/page.tsx` and `app/**/route.ts` for any direct logger / tracer usage
- `middleware.ts` for tracing context propagation

**Next.js (Pages Router):**

- `pages/_app.tsx` (RUM init, error boundary, web-vitals reporter), `pages/_document.tsx` (script tags for any non-SDK RUM)
- `pages/api/*` route handlers - Sentry server-side, OTel
- `next.config.js` Sentry plugin

**Vite + React Router:**

- `src/main.tsx` - Sentry browser SDK init, OTel browser SDK init, `web-vitals` reporter wiring
- `src/router.tsx` / route definitions - error elements (`errorElement` per route)
- `src/components/ErrorBoundary.tsx` (or wherever error boundaries live)
- `vite.config.{js,ts}` - Sentry plugin (source map upload)
- `package.json` for SDK presence

For diffs touching only one of these surfaces (a new route but no Sentry change, say), still read the existing config to know whether SDKs / error boundaries / web-vitals are wired - a missing wire is the finding.

### Step 4 - Web Vitals Reporting

Inspect web-vitals wiring and any reporter callsite in the diff:

- [ ] **`web-vitals` library installed and reporter wired**: `import { onLCP, onINP, onCLS, onTTFB, onFCP } from 'web-vitals'` with each metric posted to the analytics / RUM endpoint. Next.js: `useReportWebVitals` from `next/web-vitals` works in both routers; App Router needs a small Client Component (`<WebVitalsReporter />`) imported into `app/layout.tsx` because `useReportWebVitals` is a hook and `layout.tsx` is a Server Component by default. Vite: wire in `src/main.tsx` after `createRoot`
- [ ] **All four core metrics reported**: LCP, INP (replaced FID in 2024), CLS, plus optional TTFB and FCP. INP must be present; missing INP signals stale config (FID-only or `web-vitals` < 4.0). Confirm `web-vitals` is at v4+ in `package.json` - v2.x exports `getFID` not `onINP`
- [ ] **Attribution build used for slow paths**: `web-vitals/attribution` provides element-level / event-target attribution for LCP / INP / CLS - much more useful than a bare metric value. Recommend swapping `web-vitals` import for `web-vitals/attribution` if RUM data is uninformative
- [ ] **Reporter has a transport**: metric is `fetch`'d / `navigator.sendBeacon`'d to a real endpoint (RUM / analytics); a `console.log` reporter is dev-only. Use `sendBeacon` (or `fetch` with `keepalive: true`) so the report survives page unload
- [ ] **Sample rate applied at the reporter, not at metric collection**: collect every metric (cheap), throttle reporting (downstream cost). Do not gate `onLCP` itself behind a sample
- [ ] **Route correlation**: every reported metric includes the current route / pathname so dashboards can segment per route

### Step 5 - Error Boundaries and Error Tracking (Sentry / Honeybadger / Rollbar SDKs)

Inspect SDK config and error boundary placement:

- [ ] **Error tracker SDK installed and initialized**:
  - Next.js: `@sentry/nextjs` configured via `sentry.client.config.ts`, `sentry.server.config.ts`, `sentry.edge.config.ts` and the `withSentryConfig` wrapper in `next.config.js`
  - Vite: `@sentry/react` initialized in `src/main.tsx` with `BrowserTracing`, `Replay` integrations
- [ ] **DSN / API key from env**, not committed; `NEXT_PUBLIC_SENTRY_DSN` is acceptable here (DSN is a public token by design, but document the choice)
- [ ] **Release / environment tags** populated from build metadata (`release: process.env.NEXT_PUBLIC_BUILD_ID`, `environment: process.env.NODE_ENV`); flag bare default values
- [ ] **PII scrubbing on**: `sendDefaultPii: false` (default - flag explicit `true`); `beforeSend` strips known sensitive keys; `replaysSessionSampleRate` / `replaysOnErrorSampleRate` chosen deliberately (Replay records DOM and can inadvertently capture sensitive content - use `mask` / `block` selectors for inputs containing PII)
- [ ] **Error boundary tree (Next.js App Router)**: `app/global-error.tsx` (catches errors during render, including layout); `app/**/error.tsx` per route segment (catches per-route render errors). Both must exist for full coverage; the root error boundary requires `"use client"` and renders inside `<html>` / `<body>`
- [ ] **Error boundary (Vite)**: top-level `<ErrorBoundary>` (Sentry's `Sentry.ErrorBoundary` or React 19+ built-in) at root; per-route via React Router `errorElement`
- [ ] **Error boundary surfaces user-facing fallback**: not just a blank screen - "Something went wrong, please refresh" with a retry action. Reset key for navigation-driven recovery
- [ ] **Error boundary captures explicitly to Sentry**: Next.js `app/**/error.tsx` and `app/global-error.tsx` do NOT auto-report to Sentry - the boundary's body must call `Sentry.captureException(error)` (or `useEffect(() => Sentry.captureException(error), [error])` in the function component). A boundary that renders a fallback but does not capture loses the diagnostic; flag as High
- [ ] **Sample rate explicit**: `tracesSampleRate`, `profilesSampleRate`, `replaysSessionSampleRate` per env; not `1.0` in prod for tracing on a high-traffic app (cost + sampling-induced noise). Prefer a `tracesSampler` callback when a few high-volume routes (`/api/health`, `/api/ping`) need lower sample than the default
- [ ] **Sentry Replay vs. CSP `nonce`**: Sentry Session Replay injects inline scripts at runtime. A strict CSP (`script-src 'self' 'nonce-XXX'`) without `'unsafe-inline'` blocks Replay. When the diff adds Replay to a project with strict CSP (or vice versa), flag the conflict and recommend either adopting Sentry's CSP-compatible setup or scoping Replay to non-CSP routes
- [ ] **`Sentry.captureMessage` / `captureException` payloads do not include PII**: `extra: { user: session.user }` ships email, phone, address, and any other session-attached field to Sentry. Project the captured user to `{ id }` (or `{ id, role }`) before passing through `extra` / `setContext`. The `Sentry.setUser` flow is the right channel for identification - `extra` should only carry diagnostic detail not already on `setUser`
- [ ] **Ignored errors documented**: `ignoreErrors: [...]` lists noise classes (browser extension errors, ResizeObserver loop limit, network errors during navigation); each entry has a comment justifying
- [ ] **Source maps uploaded**: build pipeline uploads source maps to Sentry (Next.js Sentry plugin / Vite Sentry plugin) so stack traces are deobfuscated; absent means production stack traces are unreadable
- [ ] **Source maps NOT served publicly**: `productionBrowserSourceMaps: false` (Next.js default); Vite default is to embed source maps only on `--sourcemap`. Public source maps are an information disclosure risk

### Step 6 - OpenTelemetry / Tracing

_Skipped at `quick` depth unless the diff touches OTel config or `instrumentation.ts`._

**Browser-side (`@opentelemetry/sdk-trace-web` + `@opentelemetry/auto-instrumentations-web`):**

- [ ] **Browser SDK initialized**: `WebTracerProvider` registered with `BatchSpanProcessor` + OTLP exporter; auto-instrumentations enabled for `fetch`, `xhr`, `document-load`, user-interaction
- [ ] **`traceparent` propagation**: outbound `fetch` calls to your own backend include `traceparent` header so backend spans link to the originating browser request. Cross-origin: backend must be in `propagateTraceHeaderCorsUrls` allowlist; CORS must allow `traceparent`
- [ ] **Sampling**: browser-side OTel must sample aggressively (not 100%) - cost on the client side is cheap, but downstream backend sampling alignment matters

**Server-side (Next.js `instrumentation.ts`):**

- [ ] **`instrumentation.ts` registers OTel SDK**: `@opentelemetry/sdk-node` `NodeSDK` with `@vercel/otel` (the recommended wrapper) or manual `NodeSDK` setup. Initialized in `register()` for the `nodejs` runtime; for Edge runtime, OTel support is limited - document the gap. When the project chose raw `NodeSDK` over `@vercel/otel`, also confirm: (a) graceful shutdown via `sdk.shutdown()` on `SIGTERM`, (b) `BatchSpanProcessor` (not `SimpleSpanProcessor` which blocks the event loop), (c) explicit Edge-runtime fallback for routes marked `runtime = 'edge'`
- [ ] **Auto-instrumentations**: HTTP, fetch, Prisma / pg, ioredis - same as a Node service, applied to Next.js Server Components / Route Handlers / Server Actions
- [ ] **Sampling explicit and noise-aware**: `ParentBasedSampler(TraceIdRatioBasedSampler(0.1))` per env; not left at default. For repos where a few high-volume / low-signal routes dominate (health checks, prefetches, asset routes), prefer a custom `Sampler` that returns `RECORD_AND_SAMPLED` for business routes and `DROP` for noise - flat ratio sampling burns budget on noise
- [ ] **Resource attributes populated**: `service.name`, `service.version`, `deployment.environment` - from build metadata / env vars
- [ ] **Trace context propagation**: Next.js Route Handlers receive `traceparent` from upstream; Server Actions inherit context from the request that triggered them; verify auto-instrumentation does this without manual wrapping

### Step 7 - Structured Client Logging

_Skipped at `quick` depth unless the diff modifies logging utilities or routes containing `console.*` calls._

- [ ] **No `console.log` / `console.error` in production paths**: replaced with a structured logger that posts to RUM / Sentry (`Sentry.captureMessage` for warnings, `Sentry.captureException` for errors). `console.log` skips error-tracker integration, sample rates, and PII redaction
- [ ] **Log levels respected**: `console.error` only for actual errors caught by error boundaries; navigation / interaction events go to RUM events, not the console
- [ ] **Sensitive-field hygiene**: log payloads do not include `password`, `token`, `authorization`, `Authorization`, `Cookie`, raw API responses with PII; `Sentry.beforeBreadcrumb` strips known sensitive keys
- [ ] **No log spam in render paths**: a `console.log(props)` inside a render function fires on every render (cheap-but-noisy in dev, real cost in prod via RUM); flag for removal
- [ ] **Custom events for RUM**: significant user actions (signup, checkout, payment) emit a structured RUM event so retention / funnel analytics ground in real data, not page views alone

### Step 8 - User Identity and Session Correlation

_Skipped at `quick` depth unless the diff touches auth providers or a Sentry context wrapper._

- [ ] **`Sentry.setUser({ id, email? })`** called after auth succeeds; `Sentry.setUser(null)` on logout. `email` only when consent / privacy posture allows
- [ ] **`Sentry.setTag` for tenant / role / feature flag**: tenant ID, user role, A/B test variant, feature flag keys exposed as tags so filters work in Sentry / RUM
- [ ] **`Sentry.setContext` for richer per-event metadata**: build version, route, query parameters (sanitized) - structured, queryable
- [ ] **No PII in tags**: tags are searchable strings - keep cardinality bounded (tenant ID OK, full name not OK)

### Step 9 - Real User Monitoring (RUM) Integration

_Skipped at `quick` depth and on apps without a chosen RUM provider._

When a RUM SDK is in use (Datadog RUM, New Relic, Vercel Analytics, Cloudflare Web Analytics, Plausible, custom):

- [ ] **SDK initialized once at app entry**, before any router hooks execute - missed pageviews on first navigation otherwise
- [ ] **SPA navigation tracked**: SDK detects route changes via the framework's router (Next.js: `usePathname` from `next/navigation`; Vite: React Router's location); Vercel Analytics / Datadog RUM auto-detect when wired correctly
- [ ] **Custom events / actions** for business-critical interactions (checkout step completed, plan upgraded) - synthetic dashboards should not rely solely on page views
- [ ] **Privacy / DNT respected**: Do-Not-Track header / cookie banner integration; `navigator.doNotTrack === '1'` short-circuits init in privacy-sensitive jurisdictions
- [ ] **Correlation with error tracker / OTel**: same `userId` / `sessionId` / `traceId` flow into RUM events so a slow user can be cross-referenced to their errors and traces

### Step 10 - Health and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one measurable SLI (LCP < 2.5s, INP < 200ms, CLS < 0.1 - the Core Web Vitals "good" thresholds; or a custom RUM metric for a journey-specific outcome)
- [ ] SLOs documented in code (decorator / module README, route-level config) - not a free-floating Confluence page
- [ ] Error rate per route tracked via Sentry / RUM; spike alerts wired
- [ ] Synthetic checks (Datadog Synthetics, Checkly) for critical journeys; these complement RUM but do not replace it
- [ ] Build-size budgets per route enforced in CI (`@next/bundle-analyzer` thresholds, `bundlesize`); LCP regressions correlate with bundle growth

## Self-Check

- [ ] Stack confirmed as React (or accepted from parent dispatcher); framework recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent - the parent already gated)
- [ ] Instrumentation surfaces (web-vitals reporter, error boundary tree, Sentry / OTel SDK init, structured logger, RUM SDK) read directly before applying checklists; Surface Map produced
- [ ] Web Vitals (LCP / INP / CLS / TTFB / FCP) reporting verified; INP present (not legacy FID); `web-vitals` v4+ confirmed; attribution build recommended where slow paths exist
- [ ] Error boundary tree assessed: `app/global-error.tsx` + per-route `error.tsx` (Next.js App Router) / route `errorElement` (Vite + React Router); Sentry SDK wired with framework integration; boundary explicitly calls `Sentry.captureException` (Next.js does not auto-capture)
- [ ] OpenTelemetry assessed: browser SDK + auto-instrumentation, Next.js `instrumentation.ts` for server, sampling explicit and noise-aware, source maps uploaded but not served; raw `NodeSDK` setups have shutdown + BatchSpanProcessor + Edge fallback
- [ ] Sentry Replay vs. CSP `nonce` conflict checked when both surfaces appear in the diff
- [ ] `Sentry.captureMessage` / `captureException` `extra` / `setContext` payloads checked for PII (project user objects to `{ id }` before passing)
- [ ] Structured client logging assessed: no `console.log` in prod paths, sensitive-field redaction, RUM events for business-critical actions
- [ ] User identity / session correlation assessed: `Sentry.setUser` / tags / context for tenant / role / flag, no PII in high-cardinality tags
- [ ] RUM integration assessed when a RUM SDK is in use: SPA navigation tracked, custom events for journeys, privacy / DNT respected
- [ ] Findings name a React / web-vitals / Sentry / OTel idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/logging-detail/identity/RUM/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low

## Output Format

```markdown
## React Observability Review Summary

**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Web Vitals:** wired (web-vitals + RUM transport) | partial (collected but not reported) | absent
**Error Tracker:** Sentry (@sentry/nextjs) | Sentry (@sentry/react) | Honeybadger | Rollbar | absent
**Tracing (browser):** OpenTelemetry web SDK | absent
**Tracing (server, Next.js):** instrumentation.ts + @vercel/otel | absent | n/a (Vite)
**RUM:** Datadog RUM | Vercel Analytics | Cloudflare Web Analytics | custom | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

| Surface                       | Verdict                        | Evidence                                      |
| ----------------------------- | ------------------------------ | --------------------------------------------- |
| Web Vitals                    | wired / partial / absent       | [file:line or "no web-vitals reporter found"] |
| Error boundaries + Sentry SDK | wired / partial / absent       | [...]                                         |
| OpenTelemetry (browser)       | wired / partial / absent       | [...]                                         |
| OpenTelemetry (server)        | wired / partial / absent / n/a | [...]                                         |
| Structured logging            | wired / partial / absent       | [...]                                         |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent` - it tells the reader the review is scaffolding, not auditing. Use the same `absent` vocabulary throughout.

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the React idiom: missing INP reporter (only legacy FID), no `app/global-error.tsx`, Sentry initialized in component body (re-runs every render), `useReportWebVitals` missing route correlation, OTel `traceparent` not propagated to backend, source maps served publicly, etc.]
- **Impact:** [diagnosability / alertability / cost cost]
- **Fix:** [specific React / SDK change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Web Vitals / Error Tracker / Tracing / Logging / RUM) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch to `web-vitals/attribution` build for LCP element identification", "Add `instrumentation.ts` with `@vercel/otel`", "Move Sentry init from `_app.tsx` to the dedicated `sentry.client.config.ts` Next.js convention"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting instrumentation, dashboard work, ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `app/global-error.tsx` with `<Sentry.ErrorBoundary>` and a user-facing fallback"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire RUM transport endpoint to org analytics ingestion"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the React / SDK idiom ("add metrics" vs "register `web-vitals` `onINP` reporter and post via `sendBeacon` to RUM endpoint")
- Recommending generic observability advice when a React SDK or Next.js convention exists (say "use `instrumentation.ts` with `@vercel/otel`", not "add server-side tracing")
- Reviewing infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config, on-call rotation) - those are not in source code
- Approving Sentry initialization inside a component body (re-initializes on every mount and may cause double-reporting); init goes in the dedicated config file (Next.js) or `main.tsx` (Vite)
- Approving `console.log` as a logging strategy in production paths - flag for replacement with the structured logger / RUM event
- Approving `web-vitals` reporter wired only to `console.log` - that is dev-only; production needs a real transport
- Approving `replaysSessionSampleRate: 1.0` in prod for an app handling PII without `mask` / `block` configuration on Sentry Replay
- Approving FID-only web-vitals reporting - INP replaced FID in 2024 as a Core Web Vital; missing INP signals stale config
- Approving error boundaries that render a blank screen - the user-facing fallback must surface the error and offer recovery
- Approving missing source-map upload to Sentry - production stack traces are then unreadable
- Approving public source-map serving in production (`productionBrowserSourceMaps: true` without justification) - information disclosure
- Recommending `Sentry.setUser({ email, name, ... })` when only `id` is needed - PII minimization first
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
