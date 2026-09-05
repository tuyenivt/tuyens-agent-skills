---
name: task-react-review-observability
description: React / Next.js observability review - web-vitals, Sentry, OpenTelemetry browser + instrumentation.ts, RUM, structured logs, PII.
agent: react-observability-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

Stack-specific delegate of `task-code-review-observability` for React. Library/SDK-level only - infra config (Datadog dashboards, Sentry org settings, log forwarders, alert rules) is out of scope.

## When to Use

- React PR observability review or regression check (Next.js App/Pages Router, Vite + React Router)
- Pre-release or post-incident audit of client-side instrumentation
- Adopting `web-vitals` / Sentry / OpenTelemetry / RUM in a React app
- Auditing error-boundary placement and crash-reporting paths

**Not for:** general review (`task-react-review`), perf (`task-react-review-perf`), infra dashboards/alerts.

## Depth

| Depth      | When                                          | What Runs                              |
| ---------- | --------------------------------------------- | -------------------------------------- |
| `standard` | Default                                       | Steps 1-10 (each subject to its own gate) and Step 12 |
| `deep`     | Pre-release of critical app, post-incident    | The same, plus SLI/SLO (Step 11)       |

Step 12 (verify and write) runs at every depth.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Confirm React. Record framework: Next.js App Router | Next.js Pages Router | Vite + React Router. Skip detection and accept the values when a parent passed a pre-confirmed stack and framework. If not React, stop and name the detected stack so the user can invoke that stack's observability workflow.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse. Capture `head_sha = git rev-parse <head_ref>` and `base_sha = git rev-parse <base_ref>` for the report checkpoint. Skip if a parent workflow passed the handle plus pre-read artifacts.

**Audit mode.** When the request is a full pre-release or post-incident audit (not a single PR), set `audit mode`: skip `review-precondition-check` entirely - there is no diff to gate. The target is the current branch at `HEAD`. With no handle, resolve the writer's refs yourself: `branch` = `base_ref` = `head_ref` = `git rev-parse --abbrev-ref HEAD` (if that returns the literal `HEAD`, the checkout is detached - stop and ask for a branch), and `base_sha` = `head_sha` = `git rev-parse HEAD` - a full SHA, never the literal string `HEAD`, which would poison the next round's `prior_head_sha`. Every surface is in scope and the per-step diff-touch gates in Steps 7-10 are lifted (same effect as the greenfield exception), so no surface is skipped for not being "touched". Note `Mode: audit` in the Summary.

### Step 4 - Surface Map

Read instrumentation wiring in the framework-appropriate files below, plus every changed file calling `Sentry.*`, `useReportWebVitals`, OTel APIs, or a logger. Produce one verdict per surface: `wired | partial | absent | n/a` with file:line evidence (`n/a` only where the surface cannot exist on this stack - server OpenTelemetry on Vite). A missing wire is the finding, not a precondition.

| Framework            | Files to open                                                                                                                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Next.js App Router   | `instrumentation.ts` (incl. its `onRequestError` export), `instrumentation-client.ts`, `app/global-error.tsx`, `app/**/error.tsx`, `app/layout.tsx`, `sentry.{server,edge}.config.ts` (and legacy `sentry.client.config.ts`), `next.config.{js,ts,mjs}`, `middleware.ts`, `package.json` |
| Next.js Pages Router | `pages/_app.tsx`, `pages/_document.tsx`, `pages/api/*`, `instrumentation.ts` (stable and router-independent on Next 15), `instrumentation-client.ts`, `sentry.server.config.ts`, `sentry.edge.config.ts` (and legacy `sentry.client.config.ts`), `middleware.ts`, `next.config.{js,ts,mjs}`, `package.json` |
| Vite + React Router  | `src/main.tsx`, `src/router.tsx`, `src/components/ErrorBoundary.tsx`, `vite.config.{js,ts}`, `package.json`                                                                                                     |

| Surface                 | Look for                                                                                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Web Vitals              | `import { onLCP, onINP, onCLS, onTTFB } from 'web-vitals'` + transport; `useReportWebVitals` (Next.js)            |
| Error tracker + boundary| `@sentry/nextjs` or `@sentry/react` `init`; `app/global-error.tsx` + `app/**/error.tsx`; `errorElement` (Vite)    |
| OpenTelemetry (browser) | `WebTracerProvider`, `@opentelemetry/sdk-trace-web`, `@opentelemetry/auto-instrumentations-web`, OTLP exporter    |
| OpenTelemetry (server)  | `instrumentation.ts` registering `@vercel/otel` or `NodeSDK` (Next.js only; `n/a` for Vite)                       |
| Structured logging      | Logger module posting to RUM/Sentry; absence shown by `console.log`/`console.error` in prod paths                 |
| RUM                     | Datadog RUM / Vercel Speed Insights / Cloudflare Web Analytics / custom SDK init at app entry (`@vercel/analytics` is page-view Web Analytics, not RUM) |

**Grouping rule.** If a whole surface is `absent`, produce one High finding listing the missing pieces grouped by target file/symbol - not one finding per sub-check. It also covers a `partial` surface whose missing half is itself entire (tracker installed, no boundaries - or the reverse): group that half as one finding. An `absent` verdict becomes a finding only when its surface's step runs (diff-touched, greenfield, or audit); otherwise it stays a Surface Map row.

**Greenfield exception.** If 3+ surfaces are `absent`, run Steps 5-9 regardless of the diff-touch gate. Step 10 keeps its own gate: with no RUM provider chosen there is nothing to audit.

### Step 5 - Web Vitals

- [ ] `web-vitals` v6 is current (v5 removed the FID export, v4 deprecated it); v6 adds soft-navigation support, which is what makes per-route SPA attribution work. Flag any `onFID` / `getFID` usage. On Next.js the library is bundled behind `useReportWebVitals`, so its **absence from `package.json` is not a finding** when that hook is the reporter
- [ ] The three Core Web Vitals reported - LCP, INP, CLS - plus TTFB and FCP as diagnostics; INP must replace FID
- [ ] Wiring: `useReportWebVitals` in a Client Component imported into `app/layout.tsx` (App Router); `pages/_app.tsx` `reportWebVitals` (Pages); after `createRoot` (Vite)
- [ ] Transport is real: `navigator.sendBeacon` or `fetch` with `keepalive: true` to RUM/analytics endpoint; `console.log` reporter is dev-only
- [ ] Each metric carries route/pathname for per-route segmentation
- [ ] Sample at the reporter, not at metric collection (`onLCP` itself must not be gated)
- [ ] `web-vitals/attribution` build recommended when LCP/INP/CLS values exist but root causes are opaque

### Step 6 - Error Tracker + Error Boundaries

- [ ] Sentry SDK initialized in dedicated config, not in a component body (init inside a component runs after hydration, so early-boot errors are never captured). On `@sentry/nextjs` v9+ with Next 15.3+ the client entry is **`instrumentation-client.ts`**; `sentry.client.config.ts` is the legacy path and still works, so treat a modern file as correct rather than absent. Server and edge configs are only loaded because `register()` imports them behind a `NEXT_RUNTIME` check - verify that wiring, or an orphaned config captures nothing
- [ ] `instrumentation.ts` exports `onRequestError` (`export const onRequestError = Sentry.captureRequestError`) - without it server-side request errors are never reported, and it is the reason a server-render failure can be captured even when `error.tsx` does not call `captureException`
- [ ] DSN from env (`NEXT_PUBLIC_SENTRY_DSN` is acceptable - DSN is a public token); `release` and `environment` from build metadata
- [ ] `tracesSampleRate` and `replaysSessionSampleRate` set per env and not `1.0` in prod for a high-traffic app; `replaysOnErrorSampleRate: 1.0` is the recommended value and is not a finding
- [ ] PII scrubbing: `sendDefaultPii` defaults to `false`, so flag an explicit `true` (the current wizard writes one) rather than its absence; `beforeSend` strips sensitive keys. `replayIntegration` masks text and inputs by default - flag explicit `maskAllText: false` / `maskAllInputs: false` / `blockAllMedia: false`, and any `networkDetailAllowUrls` capturing bodies
- [ ] `ignoreErrors` entries each commented (ResizeObserver loop, browser-extension noise, navigation network errors)

**Boundary tree** (cite as one finding when missing):

- [ ] Next.js App Router: `app/global-error.tsx` (root, `"use client"`, renders `<html>`/`<body>`) **and** `app/**/error.tsx` per segment
- [ ] Next.js Pages Router: top-level `<ErrorBoundary>` in `_app.tsx`
- [ ] Vite: root `<Sentry.ErrorBoundary>` (or a class boundary - React still ships none) plus React 19's `createRoot` error options, which Sentry wires as `onCaughtError: Sentry.reactErrorHandler()` / `onUncaughtError`. Per-route recovery is `errorElement` on a data router, or a route-module `ErrorBoundary` export in React Router v7 framework mode
- [ ] **Boundary explicitly calls `Sentry.captureException(error)`** - Next.js `error.tsx` / `global-error.tsx` do NOT auto-report client-side errors, so a fallback without capture loses the diagnostic (High). `onRequestError` covers **server**-originated errors (Server Components, Route Handlers, Server Actions, middleware), and `error.tsx` is a Client Component - so a wired `onRequestError` does not cover what this boundary catches. Rate it Medium only when the segment demonstrably renders no client-thrown errors; otherwise High
- [ ] User-facing fallback with retry/reset action, not a blank screen

**Source maps and CSP:**

- [ ] Source maps uploaded via the Sentry plugin and not served publicly. On `@sentry/nextjs` v9+ `sourcemaps.deleteSourcemapsAfterUpload` already defaults to `true`, so the finding is an explicit `false`, not its absence (Vite: set `sourcemaps.filesToDeleteAfterUpload`). `productionBrowserSourceMaps` already defaults to `false` and does not govern the plugin's own emission, so it is not the control here
- [ ] Sentry Replay vs strict CSP: Replay injects no inline scripts, so a nonce CSP does not block it. What it does need is `worker-src 'self' blob:` (fallback `child-src blob:`) for its compression worker and `connect-src` to the Sentry ingest host - flag those, not an inline-script conflict

### Step 7 - OpenTelemetry / Tracing

_Skip unless diff touches OTel config or `instrumentation.ts` (or greenfield / audit mode applies)._

**Browser:**

- [ ] `WebTracerProvider` + `BatchSpanProcessor` + OTLP exporter; `@opentelemetry/auto-instrumentations-web` enables `fetch`, `xhr`, `document-load`, `user-interaction`
- [ ] `traceparent` propagated on outbound fetch to own backend; backend host in the `propagateTraceHeaderCorsUrls` option of `FetchInstrumentation` / `XMLHttpRequestInstrumentation` (it is per-instrumentation, not a provider-level setting); CORS allows `traceparent`
- [ ] Sampling explicit and aggressive on client (`TraceIdRatioBasedSampler`); aligned with backend ratio

**Server (Next.js `instrumentation.ts`):**

- [ ] `register()` initializes `@vercel/otel` (preferred - it supports both the Node and Edge runtimes) or a raw `NodeSDK`. A `NodeSDK` import must sit behind `process.env.NEXT_RUNTIME === 'nodejs'`; an unguarded top-level import breaks the Edge bundle
- [ ] Raw `NodeSDK` setup includes: `BatchSpanProcessor` (not `SimpleSpanProcessor`), `SIGTERM` -> `sdk.shutdown()`, explicit fallback for `runtime = 'edge'` routes
- [ ] Resource attributes: `service.name`, `service.version`, `deployment.environment.name` (`deployment.environment` is deprecated in OTel semconv 1.27+) from build metadata
- [ ] Sampler aware of high-volume noise (health checks, prefetches) - custom `Sampler` dropping them beats flat ratio

### Step 8 - Structured Client Logging

_Skip unless diff modifies logging utilities or adds `console.*` in prod paths (or greenfield / audit mode applies)._

- [ ] No `console.log` / `console.error` in prod paths - routes to `Sentry.captureMessage` / `captureException` or a structured logger that hits RUM
- [ ] No log calls in render bodies (fires every render)
- [ ] Sensitive-field hygiene: payloads exclude `password`, `token`, `authorization`, `Cookie`, raw responses with PII; `beforeBreadcrumb` strips known keys
- [ ] Business actions (signup, checkout step, payment) emit structured RUM events - not page views alone

### Step 9 - Identity, Session, Trace Correlation

_Skip unless diff touches auth, RUM SDK init, or Sentry context wiring (or greenfield / audit mode applies)._

- [ ] `Sentry.setUser({ id })` after auth; `Sentry.setUser(null)` on logout; `email` only with consent
- [ ] `Sentry.setTag` for low-cardinality dimensions (tenant, role, flag); no PII or unbounded values (no `userId` as tag)
- [ ] `Sentry.setContext` for build version, sanitized route/query
- [ ] **`extra` / `setContext` payloads project user to `{ id }` (or `{ id, role }`)** - never pass `session.user` whole
- [ ] Same `userId` / `sessionId` / `traceId` flow into RUM, Sentry, and OTel so a slow user cross-references to errors and traces

### Step 10 - RUM Integration

_Skip on apps without a chosen RUM provider. Greenfield and audit mode lift the diff-touch gates, not this one: with no provider chosen there is nothing to audit, so the Surface Map row stays `absent` and no finding is raised. Recommend adopting one instead._

- [ ] SDK initialized once at app entry, before any router hook fires (first navigation otherwise unrecorded)
- [ ] SPA navigation tracked: Next.js via `usePathname`; Vite via React Router location; vendor auto-detect verified
- [ ] Custom events for business-critical interactions (checkout step completed, plan upgraded)
- [ ] Opt-out respected where jurisdiction requires: `navigator.globalPrivacyControl` is the enforceable modern signal. Do Not Track was discontinued in 2019 and removed from Safari and Firefox's UI, so a `navigator.doNotTrack` check alone is not compliance
- [ ] Privacy posture documented when Session Replay / session recording is on

### Step 11 - Health and SLIs (deep only)

These are programme-level gaps, not surface wiring: report them as **one** finding per missing capability (not one per checkbox) with `Surface: Health & SLI`, and put any narrative in Recommendations.

- [ ] Critical journeys have at least one SLI (LCP < 2.5s, INP < 200ms, CLS < 0.1, or custom RUM metric)
- [ ] SLOs documented in code (route config / module README) - not free-floating in Confluence
- [ ] Error rate per route alerted via Sentry/RUM
- [ ] Synthetic checks (Datadog Synthetics, Checkly) complement RUM for critical journeys
- [ ] Bundle-size budget per route enforced in CI with a tool that can fail the build - `size-limit` or `bundlesize2`. `@next/bundle-analyzer` only renders a treemap and `bundlesize` is unmaintained, so neither enforces a budget on its own

### Step 12 - Verify Findings and Write Report

**Verify (every depth - not gated by Step 11).** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column into each finding's `Label` slot, and put its tally in the Summary's `Findings verified` slot - the verify table itself is not published. Audit mode: `review-finding-verify` requires a diff it does not have, so run only its claim check - confirm each finding's cited `file:line` still says what the finding says. Its "uncertainty does not delete" rule still holds: a claim you cannot settle from the file stays, marked `(unverified: <reason>)`, and only a claim the file contradicts is dropped. Skip diff-attribution entirely (no `Pre-existing` verdicts, no de-escalation, no `_(pre-existing)_` annotations). The tally is `<N> confirmed, 0 reattributed, <K> dropped (<F> false positive, 0 resolved by diff); <U> of these unverified`, with `reattributed` 0 by construction.

**Subagent mode:** skip verification (the parent verifies the merged set once), return this workflow's Output Format document - Summary, Surface Map, Findings, Recommendations, Next Steps - and write nothing; the parent merges the Findings and Next Steps and carries the Surface Map and Recommendations into its own `## Scope Sections`. Each finding already carries its `Label`.

**Round gate (standalone only).** Run this immediately after Step 3 resolves the refs, before reading any surface - a no-op exit should cost one `git rev-parse`, not a whole review. Resolve `<branch>` first, exactly as the writer call below does: the head's short name, or the handle's `current_branch` when `head_ref` is the literal `HEAD`. The prior-report key is `review-observability-<branch>.md` with the writer's filename sanitization applied (`/` and any character outside `[A-Za-z0-9_-]` replaced, runs collapsed, ends stripped), so a `feature/x` branch looks up `review-observability-feature-x.md`. The `prior_checkpoint` in the precondition handle names the **core** `review-<branch>.md` and is a different report - ignore it. If that file exists with valid frontmatter and its `head_sha` equals the current head, and this run adds no depth, print `No new commits on <branch> since prior observability review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Treat missing or invalid frontmatter as round 1 and overwrite.

**Reconcile (standalone, round 2+).** When a valid prior report exists and this is a diff-based run, Use skill: `review-prior-findings-reconcile`. It parses a `## High-Impact Findings` section containing one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, which is not this workflow's report shape, so **re-project the prior report first**: emit that exact section heading, then per prior finding a `### [<Label>] <file:line>` heading taking the label from its `Label` slot and the location from its `Location` slot, followed by `- Issue: <its Issue text>` (reconcile reads that line as the finding's summary and cannot match without it). Pass the projection as `prior_report` along with the diff, the `git diff --name-status <base>...<head>` list from Step 3, and `head_sha`. Put the returned table under `## Prior Round Reconciliation`. Carry its `Still open` and `Needs re-check` rows into this round's Findings, in the section the prior report filed them under (the table returns a label, not a bucket - re-read the prior report for the bucket), with `(open since round <N>)` appended to the `Location` line and any `_(pre-existing)_` annotation preserved, since next round's reconcile keys on it. Map any legacy label the table preserved (`[Blocker]`, `[High]`, `[Suggestion]`, `[Question]`, `[Nitpick]`) into `[Must]` or `[Recommend]` before publishing anything outside the reconciliation table itself, which keeps them verbatim. Skip reconciliation entirely when there is no diff (audit mode or a whole-app sweep) and say so in the Summary.

Then Use skill: `review-report-writer` with `report_type: review-observability` and every required field: `report_body`, `branch`, `base_ref` / `head_ref` from the precondition handle - when the handle's `head_ref` is the literal `HEAD` (no-argument mode), pass its `current_branch` instead, or the writer produces a `-HEAD.md` file the next round's lookup never finds (audit mode: all three are the current branch name), `base_sha` / `head_sha` from Step 3, `scope: +obs`, `depth` as resolved, `stack: typescript-nextjs` (Vite: `typescript-react`), and `mode: full`, `round: 1` - unless `review-observability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself). The report body is also the chat deliverable; print the confirmation line after it.

## Output Format

The fence below delimits the template for display only - it is not part of the report, and neither is this paragraph. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Labels:** High -> `[Must]`; Medium / Low -> `[Recommend]`; the verify pass's `Label` column overrides when it ran. The bucket tracks impact, the label tracks the merge gate - a pre-existing absence can sit in High Impact carrying `[Recommend]`. Surfaces have no severity of their own: score a gap by what it costs to diagnose an incident.

**Omit empty buckets.** Group by Surface within a bucket when more than two findings share one, under a `**<Surface>**` sub-heading; otherwise list flat. An absent surface collapses into one finding per the Step 4 grouping rule.

**The `Findings verified` parenthetical** is written only when K > 0, and the `; <U> of these unverified` clause only when a surviving row is unverified. In subagent mode write exactly `not run (subagent; parent verifies the merged set)` in that slot.

**Set `Overall`** to the third form when 3+ Surface Map rows are `absent`; the counts are always given.

**Use `absent` consistently** in the Surface Map (not `none` / `missing` / `not wired`).

```markdown
## React Observability Review Summary

- **Stack:** React <version> / TypeScript <version>
- **Framework:** Next.js App Router <version> | Next.js Pages Router <version> | Vite + React Router <version>
- **RUM:** Datadog RUM | Vercel Speed Insights | Cloudflare Web Analytics | custom | absent
- **Depth:** standard | deep
- **Mode:** PR | audit
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff); <U> of these unverified
- **Overall:** Adequate | Gaps Found [High/Medium/Low counts] | Gaps Found [counts] - Greenfield: <n> surfaces absent

## Surface Map

| Surface                  | Verdict                        | Evidence                                         |
| ------------------------ | ------------------------------ | ------------------------------------------------ |
| Web Vitals               | wired / partial / absent       | [file:line or "no web-vitals reporter found"]    |
| Error tracker + boundary | wired / partial / absent       | [file:line]                                      |
| OpenTelemetry (browser)  | wired / partial / absent       | [file:line]                                      |
| OpenTelemetry (server)   | wired / partial / absent / n/a | [file:line; n/a for Vite]                        |
| Structured logging       | wired / partial / absent       | [file:line]                                      |
| RUM                      | wired / partial / absent       | [file:line]                                      |

## Findings

### High Impact

- **Label:** [Must | Recommend]
- **Location:** [file:line; a bare config key only when no line exists, in which case the verify pass will return it unverified. Carry its annotation when it set one: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `(unverified: <reason>)`]
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

[Structural improvements not tied to a single finding - e.g., swap `web-vitals` for `web-vitals/attribution`; move Sentry init from `_app.tsx` to `sentry.client.config.ts`; adopt `@vercel/otel` over raw `NodeSDK`]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: ops] - [action]
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed React; framework recorded (App Router / Pages Router / Vite)
- [ ] Step 3: diff and commit log read once and reused (or handle accepted from parent); in audit mode the precondition was skipped, `Mode: audit` recorded in Summary, and the writer's refs resolved directly from `HEAD` as full SHAs
- [ ] Step 4: surface map produced with 6 verdicts and evidence; `Overall` set with counts, and the greenfield suffix added when 3+ rows are `absent`; grouping rules applied
- [ ] Step 5: web-vitals current major, the three Core Web Vitals plus TTFB, real transport, route correlation, sampling at reporter
- [ ] Step 6: Sentry init in config file, env-driven release/env, sample rates per env, PII scrub, error-boundary tree with explicit `captureException`, source maps uploaded but not public, Replay vs CSP conflict checked
- [ ] Step 7: OTel browser SDK + traceparent propagation; Next.js `instrumentation.ts` with shutdown, BatchSpanProcessor, Edge fallback for raw `NodeSDK` (skipped per gate when applicable)
- [ ] Step 8: no `console.*` in prod paths, no log in render, sensitive-field hygiene, RUM events for business actions (skipped per gate)
- [ ] Step 9: `setUser({ id })`, low-cardinality tags, `extra` projects user to `{ id }`, cross-tool correlation (skipped per gate)
- [ ] Step 10: RUM SDK init order, SPA nav tracking, custom events, opt-out signal respected (skipped per gate)
- [ ] Step 11: SLIs, SLOs in code, per-route error alerts, synthetics, bundle budgets (deep only)
- [ ] Step 12: findings verified at every depth (audit mode: claims only; subagent: skipped, Output Format document returned, nothing written); standalone: same-SHA no-op gate applied, prior round reconciled when a valid prior report existed, report written via `review-report-writer` with full checkpoint fields and a real branch name; confirmation printed

## Avoid

- Generic advice when a React/SDK idiom exists ("add metrics" vs "register `onINP` reporter via `useReportWebVitals` posting through `sendBeacon`")
- Per-checkbox findings when a whole surface is absent - collapse per the Step 4 grouping rule
- Approving Sentry init inside a component body - re-runs every mount, double-reports
- Approving `error.tsx` / `global-error.tsx` that render a fallback without calling `Sentry.captureException` - Next.js does not auto-capture
- Approving FID-only web-vitals reporting (INP replaced FID in 2024)
- Approving `web-vitals` reporter wired only to `console.log`
- Approving `replaysSessionSampleRate: 1.0` in prod without `mask`/`block` on PII inputs
- Approving `extra: { user: session.user }` or `setContext` payloads carrying email/phone/address - project to `{ id }`
- Approving public source-map serving in production
- Approving missing source-map upload to Sentry - production stack traces unreadable
- Approving `userId`/`orderId` as Sentry tags (unbounded cardinality)
- Approving Sentry Replay on a strict CSP without `worker-src 'self' blob:` and a `connect-src` entry for the ingest host
- Approving error boundaries with a blank-screen fallback
- Infra scope (Datadog dashboards, Sentry org settings, log forwarders, alert rules) - delegate to ops review
- State-changing git commands
- Inventing a `Surface` value outside the eight in the Findings template - the first six match the Surface Map rows exactly
