---
name: task-angular-review-observability
description: Angular observability review: web-vitals, Sentry, OpenTelemetry browser SDK, SSR tracing, structured logs, RUM correlation.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Angular Observability Review

Stack-specific delegate of `task-code-review-observability` for Angular. Preserves the parent contract (depth levels, output format). Focuses on Angular library and SDK wiring: `web-vitals` (`onLCP`/`onINP`/`onCLS`/`onTTFB`/`onFCP`), `@sentry/angular` with `Sentry.createErrorHandler()` provided as `ErrorHandler` and `Sentry.TraceService` for router spans, OpenTelemetry browser SDK (`@opentelemetry/sdk-trace-web` + auto-instrumentations), SSR Node tracing (`@opentelemetry/sdk-node` in `server.ts`), structured client logging, and RUM correlation. Infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config, alert rules) stay out of scope.

## When to Use

- Reviewing an Angular PR for observability regressions or instrumentation gaps
- Pre-release observability check for a new Angular app or major feature
- Post-incident review when client-side diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / Sentry / `web-vitals` in an Angular app
- Auditing global `ErrorHandler` placement and crash reporting paths

**Not for:**

- General Angular code review (use `task-angular-review`)
- Angular performance with a known bottleneck (use `task-angular-review-perf`)
- Active incident investigation (use `/task-oncall-start`)
- Infra-level observability (dashboards, alerts) - not in source code

## Depth Levels

| Depth      | When to Use                                            | What Runs                                          |
| ---------- | ------------------------------------------------------ | -------------------------------------------------- |
| `quick`    | Single component or route                              | Logging + `ErrorHandler` + web-vitals check only   |
| `standard` | Default - full Angular observability review            | All steps                                          |
| `deep`     | Pre-release of a critical app, or post-incident review | All steps + SLI/SLO suggestions per critical route |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                    | Meaning                                                                                               |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-angular-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-angular-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-angular-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent, the parent passes the precondition handle plus the already-read diff and commit log; Step 2 is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If not Angular, stop and tell the user to invoke `/task-code-review-observability`. Record `Angular: <version>`, `SSR: enabled | disabled` (look for `@angular/ssr` + `provideClientHydration`). Steps below branch on the SSR signal.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. On approval, read diff + commit log once and reuse. Skip if the parent passed the handle. If the precondition check fails fast, surface its message verbatim and stop. Never run a state-changing git command.

### Step 3 - Map the Instrumentation Surface

Produce a one-line verdict per surface (web-vitals / error tracker / OTel browser / OTel server SSR / structured logging) of the form `wired | partial | absent`. A missing wire is itself the finding.

**Grouping rule.** When a whole surface is `absent`, emit **one** High-Impact finding for that surface listing all missing pieces grouped by target file/symbol. Per-callsite findings only apply when the surface exists and a callsite misuses it.

Read the files that configure observability so findings cite real lines:

- `app.config.ts` / `app.config.server.ts` - `Sentry.init`, `provideErrorHandler(Sentry.createErrorHandler())`, `Sentry.TraceService` for router spans, OTel browser init via `provideAppInitializer`, web-vitals reporter wiring
- `main.ts` / `main.server.ts` - bootstrap-time SDK init
- `server.ts` - Node-side OTel SDK init, structured logging, request lifecycle hooks
- `*.interceptor.ts` - HTTP error interceptor routing to Sentry / structured logger
- `*.service.ts` - custom `ErrorService` / `LoggerService` if present
- `package.json` - `@sentry/angular` (note: `@sentry/angular-ivy` is the legacy package), `web-vitals` (v4+), `@opentelemetry/sdk-trace-web`, `@opentelemetry/sdk-node`
- `angular.json` - source-map upload plugin config; production `sourceMap: false` (or upload-then-strip)

If the diff touches only one surface, still read the rest - a missing wire elsewhere is in scope.

### Step 4 - Web Vitals Reporting

- [ ] `web-vitals` v4+ installed; reporter wired in `main.ts` after `bootstrapApplication` or via `provideAppInitializer`; under SSR guard with `isPlatformBrowser` / `afterNextRender`
- [ ] All Core Web Vitals reported: `onLCP` / `onINP` / `onCLS` (+ optional `onTTFB`, `onFCP`); INP must be present - missing INP signals stale config (legacy `getFID` from web-vitals v2)
- [ ] Reporter posts to a real RUM/analytics endpoint via `navigator.sendBeacon` or `fetch({ keepalive: true })` - not `console.log`
- [ ] Sample at the reporter, not at metric collection (`onLCP` itself ungated)
- [ ] Route correlation: subscribe to `Router.events` `NavigationEnd` so SPA navigations get distinct metrics
- [ ] Recommend `web-vitals/attribution` when slow paths exist (element/event-target attribution)

### Step 5 - Error Boundaries and Error Tracking

- [ ] `@sentry/angular` initialized in `main.ts` / `app.config.ts` via `Sentry.init({ dsn, integrations: [browserTracingIntegration(), replayIntegration()] })`
- [ ] `Sentry.createErrorHandler()` provided as `ErrorHandler` in `app.config.ts`; without this, uncaught errors only hit Angular's default handler (console)
- [ ] `Sentry.TraceService` provided after `Router` for route-aware tracing (Medium if missing - perf data without route context)
- [ ] DSN from env or `environment.ts` (public token by design); `release` / `environment` populated from build metadata, not defaults
- [ ] PII discipline: `sendDefaultPii: false`; `beforeSend` strips sensitive keys; `replaysSessionSampleRate` / `replaysOnErrorSampleRate` chosen deliberately with `mask` / `block` selectors on PII inputs
- [ ] HTTP error `HttpInterceptorFn` routes to `Sentry.captureException` or structured logger; flag `catchError(() => of(null))` that swallows
- [ ] Custom `ErrorHandler` (if present, not Sentry's) calls `Sentry.captureException` or chains via `super.handleError`
- [ ] Sample rates explicit per env (`tracesSampleRate`, `profilesSampleRate`); not `1.0` in prod on high traffic
- [ ] Sentry Replay vs. strict CSP: Replay injects inline scripts; a `script-src 'self' 'nonce-XXX'` CSP without `'unsafe-inline'` blocks it - flag the conflict when both surfaces appear in the diff
- [ ] `captureException` / `setContext` payloads do not include PII - project users to `{ id }`; identification flows through `Sentry.setUser`
- [ ] `ignoreErrors: [...]` entries each justified with a comment (extension errors, ResizeObserver loop, navigation aborts)
- [ ] Source maps uploaded (`@sentry/cli` / `@sentry/webpack-plugin`); `angular.json` production `sourceMap: false` or stripped after upload

### Step 6 - OpenTelemetry / Tracing

_Skipped at `quick` depth unless the diff touches OTel config or SSR `server.ts`._

**Browser (`@opentelemetry/sdk-trace-web` + `@opentelemetry/auto-instrumentations-web`):**

- [ ] `WebTracerProvider` with `BatchSpanProcessor` + OTLP exporter; auto-instrumentations for `fetch`, `xhr`, `document-load`, user-interaction; wired in `main.ts` or via `provideAppInitializer`
- [ ] `traceparent` propagated to your backend: backend in `propagateTraceHeaderCorsUrls` allowlist; CORS allows `traceparent`
- [ ] Sampling explicit (not 100%); aligned with backend sampling

**Server (Angular SSR in `server.ts`):**

- [ ] `@opentelemetry/sdk-node` `NodeSDK` initialized at the earliest possible point - before any request handler
- [ ] Auto-instrumentations: HTTP, fetch, Express middleware, any DB client used in resolvers
- [ ] Sampling: `ParentBasedSampler(TraceIdRatioBasedSampler(...))` per env; custom `Sampler` to drop health-check noise
- [ ] Resource attributes from env: `service.name`, `service.version`, `deployment.environment`
- [ ] `BatchSpanProcessor` (not `SimpleSpanProcessor`); `sdk.shutdown()` on `SIGTERM`

### Step 7 - Structured Client Logging

_Skipped at `quick` depth unless the diff modifies logging utilities or routes containing `console.*` calls._

- [ ] No `console.log` / `console.error` in production paths; replaced with structured logger that posts to RUM / Sentry. `console.*` skips sample rates and PII redaction
- [ ] **Replay/breadcrumb compound check.** Sentry's `consoleIntegration` ships every `console.*` as a breadcrumb; Replay records console output. When the diff contains `console.*` of a non-trivial payload AND high Replay sampling, surface as ONE finding cross-referenced to Step 5:
  - **High** when `replaysSessionSampleRate >= 0.5` without input `mask` / `block`
  - **Critical** when the High case also has `sendDefaultPii: true` (or equivalent un-redacted user context)
- [ ] Sensitive-field hygiene: no `password`, `token`, `authorization`, `Cookie`, raw HTTP responses with PII; `Sentry.beforeBreadcrumb` strips known keys
- [ ] No log spam in `constructor` / `ngOnInit` (fires per instantiation - RUM cost in prod)
- [ ] Custom RUM events for business-critical actions (signup, checkout, payment)

### Step 8 - User Identity and Session Correlation

_Skipped at `quick` depth unless the diff touches auth or a Sentry context wrapper._

- [ ] `Sentry.setUser({ id })` on auth success; `Sentry.setUser(null)` on logout. Hook via `effect(() => Sentry.setUser(this.auth.currentUser() ? { id: ... } : null))`. `email` only with explicit consent
- [ ] `Sentry.setTag` for tenant / role / feature-flag keys (bounded cardinality - no full names)
- [ ] `Sentry.setContext` for build version, route, sanitized query params

### Step 9 - RUM Integration

_Skipped at `quick` depth and on apps without a chosen RUM provider._

- [ ] RUM SDK (Datadog / New Relic / Cloudflare / custom) initialized at app entry, before router hooks - else first navigation pageview is lost
- [ ] SPA navigation tracked via `Router.events` `NavigationEnd` (Datadog auto-detects with `trackViewsManually: false`; custom RUM needs explicit subscription)
- [ ] Custom events for business journeys - dashboards do not rely on page views alone
- [ ] DNT / consent respected (`navigator.doNotTrack === '1'` short-circuits init where required)
- [ ] Correlation: shared `userId` / `sessionId` / `traceId` flow into RUM events, Sentry, and OTel

### Step 10 - Health and SLIs (deep depth only)

- [ ] Critical journeys have at least one measurable SLI (Core Web Vitals "good" thresholds: LCP < 2.5s, INP < 200ms, CLS < 0.1; or a journey-specific RUM metric)
- [ ] SLOs documented in code (route-level config / README), not in a free-floating Confluence page
- [ ] Per-route error rate tracked via Sentry / RUM; spike alerts wired
- [ ] Synthetic checks (Datadog Synthetics, Checkly) for critical journeys - complement, not replace RUM
- [ ] `angular.json` `budgets` enforced in CI; LCP regressions correlate with bundle growth

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the assembled output to the report file before ending the session. Print the confirmation line.

## Self-Check

- [ ] Step 1: Stack confirmed as Angular (or accepted from parent); Angular version + SSR status recorded
- [ ] Step 2: `review-precondition-check` ran (or handle received); diff + commit log read once and reused; no state-changing git command issued
- [ ] Step 3: Surface Map produced with `wired | partial | absent` per surface; absent surfaces collapsed into one High finding each per grouping rule
- [ ] Step 4: Web Vitals checked - INP present (not legacy FID), `web-vitals` v4+, real transport, route correlation via `Router.events`
- [ ] Step 5: Error tracker checked - `Sentry.createErrorHandler` provided as `ErrorHandler`, `TraceService` provided, interceptor routes to logger, PII discipline, Replay/CSP conflict flagged when both appear, source maps uploaded but not served
- [ ] Step 6: OpenTelemetry checked - browser SDK + `traceparent` propagation; SSR `NodeSDK` with `BatchSpanProcessor` + `SIGTERM` shutdown + explicit sampling
- [ ] Step 7: Structured logging checked - no `console.*` in prod paths; Replay/breadcrumb compound surfaced as ONE cross-referenced finding when triggered
- [ ] Step 8: Identity / session correlation checked - `setUser({ id })`, bounded-cardinality tags, no PII in tags
- [ ] Step 9: RUM checked when an SDK is in use - SPA tracking via `Router.events`, custom journey events, DNT respected, IDs flow across tools
- [ ] Step 10: At `deep`, SLI/SLO/budgets evaluated; skipped at `quick` / `standard`
- [ ] Step 11: Report written via `review-report-writer`; confirmation line printed
- [ ] Findings name an Angular / SDK idiom directly (not "add observability"); library-level scope respected; infra concerns deferred; Next Steps tagged `[Implement]` / `[Delegate]` and ordered High > Medium > Low

## Output Format

```markdown
## Angular Observability Review Summary

**Stack Detected:** Angular <version> / TypeScript <version>
**SSR:** enabled | disabled
**Web Vitals:** wired (web-vitals + RUM transport) | partial (collected but not reported) | absent
**Error Tracker:** Sentry (@sentry/angular) | Honeybadger | Rollbar | absent
**Tracing (browser):** OpenTelemetry web SDK | absent
**Tracing (server, SSR):** server.ts + @opentelemetry/sdk-node | absent | n/a (SPA only)
**RUM:** Datadog RUM | New Relic | Cloudflare Web Analytics | custom | absent
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low] | Greenfield - no observability surface wired (count by impact: ...)

## Surface Map

| Surface                     | Verdict                        | Evidence                                      |
| --------------------------- | ------------------------------ | --------------------------------------------- |
| Web Vitals                  | wired / partial / absent       | [file:line or "no web-vitals reporter found"] |
| ErrorHandler + Sentry SDK   | wired / partial / absent       | [...]                                         |
| OpenTelemetry (browser)     | wired / partial / absent       | [...]                                         |
| OpenTelemetry (server, SSR) | wired / partial / absent / n/a | [...]                                         |
| Structured logging          | wired / partial / absent       | [...]                                         |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent` - tells the reader the review is scaffolding, not auditing.

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Angular idiom: missing INP reporter, `Sentry.createErrorHandler` not provided as `ErrorHandler`, no `Sentry.TraceService` for router spans, `traceparent` not propagated, source maps served publicly, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Angular / SDK change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within an impact bucket, group by surface when 3+ findings share one; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per Step 3._

## Recommendations

[Structural improvements not tied to a single finding - e.g., "Switch to `web-vitals/attribution` for LCP element identification", "Add `Sentry.TraceService` for router spans", "Add SSR-side OTel via `@opentelemetry/sdk-node` in server.ts"]

## Next Steps

Prioritized actions. Each tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [e.g., "Provide `Sentry.createErrorHandler()` as `ErrorHandler` in app.config.ts:24 so uncaught errors route to Sentry"]
2. **[Delegate]** [High] [scope: ops] - [e.g., "Wire RUM transport endpoint to org analytics ingestion"]
3. **[Implement]** [Medium] file:line - [...]

_Omit if no actionable findings._
```

## Avoid

- Running any state-changing git command (`git fetch`, `git checkout`, etc.)
- Generic phrasing ("add observability", "add error tracking") instead of naming the Angular/SDK idiom (`Sentry.createErrorHandler`, `web-vitals` `onINP` via `sendBeacon` with `Router.events` correlation)
- Reviewing infra (dashboards, alert rules, log forwarders, on-call rotation) - not in source code
- `Sentry.init` inside a component constructor (re-initializes per mount, double-reports); init belongs in `main.ts` / `app.config.ts`
- Approving `Sentry.init` without `Sentry.createErrorHandler()` provided as `ErrorHandler`, or `ErrorHandler` that swallows without forwarding to Sentry / structured logger
- Approving FID-only web-vitals or v2.x APIs (`getFID`) - INP replaced FID as a Core Web Vital
- Approving `console.log` as a production logging strategy, or a `web-vitals` reporter wired only to `console.log`
- Approving `replaysSessionSampleRate: 1.0` on PII-handling apps without `mask` / `block`
- Approving missing source-map upload or publicly-served production source maps
- `Sentry.setUser({ email, name, ... })` when only `id` is needed
- One finding per missing checkbox when an entire surface is absent - collapse per Step 3
