---
name: task-angular-review-observability
description: Angular observability review for `web-vitals` reporting (LCP / INP / CLS / TTFB), Sentry Angular SDK + global `ErrorHandler`, OpenTelemetry browser instrumentation, SSR server-side tracing, structured client logging, RUM correlation. Library-level focus, not infra. Use when reviewing an Angular PR for observability gaps, before releasing a new app, or after an incident where client-side diagnosis was slow. Stack-specific override of task-code-review-observability for Angular.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Angular Observability Review

## Purpose

Angular-aware observability review that names `web-vitals` (`onLCP`, `onINP`, `onCLS`, `onTTFB`, `onFCP`), Sentry Angular SDK + global `ErrorHandler` (`Sentry.init({...})` in `app.config.ts`, `Sentry.createErrorHandler()` provided as `ErrorHandler`, `TraceService` for router instrumentation), OpenTelemetry web SDK (`@opentelemetry/sdk-trace-web` + `@opentelemetry/auto-instrumentations-web`), Angular SSR Node-side tracing (server.ts hook, `@opentelemetry/sdk-node`), structured client logging, and RUM correlation directly instead of routing through the generic frontend adapter. Focuses on whether Angular production behavior is visible, diagnosable, and alertable - at the _library and SDK_ level. Infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Angular. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing an Angular PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Angular app or major feature
- Post-incident review when client-side diagnosis was slow or evidence was missing
- Adopting OpenTelemetry / Sentry / `web-vitals` in an Angular app
- Auditing global `ErrorHandler` placement and crash reporting paths

**Not for:**

- General Angular code review (use `task-angular-review`)
- Angular performance issues with a known bottleneck (use `task-angular-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules) - those are not in source code

## Depth Levels

| Depth      | When to Use                                            | What Runs                                                |
| ---------- | ------------------------------------------------------ | -------------------------------------------------------- |
| `quick`    | Single component or route                              | Logging + `ErrorHandler` + web-vitals check only         |
| `standard` | Default - full Angular observability review            | All steps                                                |
| `deep`     | Pre-release of a critical app, or post-incident review | All steps + SLI/SLO suggestions per critical route       |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                    | Meaning                                                                                               |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-angular-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-angular-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-angular-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-angular-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If invoked as a subagent of an Angular-aware parent, accept the pre-confirmed stack. If not Angular, stop and tell the user to invoke `/task-code-review-observability` instead.

Detect: Angular major version, SSR enabled (`@angular/ssr` + `provideClientHydration`). Record `Angular: <version>`, `SSR: enabled | disabled`. Each step branches on this signal where the instrumentation surface differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. On approval, read diff + commit log once and reuse. Skip entirely if running as a subagent and the parent passed the handle.

If the precondition check stops with a fail-fast message, surface it verbatim and stop. Do not run any state-changing git command.

### Step 3 - Read the Instrumentation Surface

**The most important output of this step is a one-line answer per surface (web-vitals / error tracker / OTel browser / OTel server (SSR) / structured logging) of the form `wired | partial | absent`.** A missing wire is itself the finding, not a precondition for review. If the surface is `absent`, Steps 4-9 shift mode from "audit existing wiring" to "scaffold from zero at the changed call sites" - and findings consolidate one-per-surface (see grouping rule below).

**Grouping rule.** When a whole surface is `absent` (no `web-vitals`, no Sentry SDK init, no OTel browser SDK), produce a **single High-Impact finding for that surface** listing all the missing pieces grouped by the file/symbol they should land in. Per-callsite findings only apply when the surface exists and a specific callsite misuses it.

Then open the files that actually configure observability so findings cite real lines:

- `app.config.ts` - `Sentry.init({...})`, `provideAppInitializer(() => Sentry.captureMessage(...))`, `provideErrorHandler(Sentry.createErrorHandler({...}))`, OTel browser SDK init, `web-vitals` reporter wiring, `TraceService` for router span instrumentation
- `app.config.server.ts` - server-side OTel / Sentry init under SSR
- `main.ts` / `main.server.ts` - bootstrap-time SDK init
- `server.ts` (SSR) - Node-side OTel SDK init, structured logging, request lifecycle hooks
- `app.component.ts` / root component - error boundary patterns, global event handlers
- `*.interceptor.ts` - HTTP error interceptor routing to Sentry / structured logger
- `*.service.ts` for `ErrorService` / `LoggerService` if the project has a custom logger
- `package.json` - confirm `@sentry/angular` (note: `@sentry/angular-ivy` is the older package; new code uses `@sentry/angular`), `web-vitals`, `@opentelemetry/sdk-trace-web`, `@opentelemetry/sdk-node` presence
- `angular.json` - source map upload plugin config (Sentry CLI hook)

For diffs touching only one of these surfaces (a new route but no Sentry change, say), still read the existing config to know whether SDKs / `ErrorHandler` / web-vitals are wired - a missing wire is the finding.

### Step 4 - Web Vitals Reporting

Inspect web-vitals wiring and any reporter callsite in the diff:

- [ ] **`web-vitals` library installed and reporter wired**: `import { onLCP, onINP, onCLS, onTTFB, onFCP } from 'web-vitals'` with each metric posted to the analytics / RUM endpoint. Wire in `main.ts` after `bootstrapApplication`, or in an `APP_INITIALIZER` / `provideAppInitializer`. Under SSR, register only on the client (`isPlatformBrowser` guard or in `afterNextRender`)
- [ ] **All four core metrics reported**: LCP, INP (replaced FID in 2024), CLS, plus optional TTFB and FCP. INP must be present; missing INP signals stale config (FID-only or `web-vitals` < 4.0). Confirm `web-vitals` is at v4+ in `package.json` - v2.x exports `getFID` not `onINP`
- [ ] **Attribution build used for slow paths**: `web-vitals/attribution` provides element-level / event-target attribution for LCP / INP / CLS - much more useful than a bare metric value. Recommend swapping `web-vitals` import for `web-vitals/attribution` if RUM data is uninformative
- [ ] **Reporter has a transport**: metric is `fetch`'d / `navigator.sendBeacon`'d to a real endpoint (RUM / analytics); a `console.log` reporter is dev-only. Use `sendBeacon` (or `fetch` with `keepalive: true`) so the report survives page unload
- [ ] **Sample rate applied at the reporter, not at metric collection**: collect every metric (cheap), throttle reporting (downstream cost). Do not gate `onLCP` itself behind a sample
- [ ] **Route correlation**: every reported metric includes the current route / pathname so dashboards can segment per route. Subscribe to `Router.events` for `NavigationEnd` to track SPA navigations correctly - a `web-vitals` reporter without route info attributes all metrics to the initial URL

### Step 5 - Error Boundaries and Error Tracking (Sentry / Honeybadger / Rollbar SDKs)

Inspect SDK config and `ErrorHandler` placement:

- [ ] **Error tracker SDK installed and initialized**: `@sentry/angular` (Angular 17+; for older projects `@sentry/angular-ivy`) initialized in `main.ts` or `app.config.ts` via `Sentry.init({ dsn, integrations: [Sentry.browserTracingIntegration(), Sentry.replayIntegration()] })`. The Angular integration must be wired via `Sentry.createErrorHandler()` provided as `ErrorHandler`, and `Sentry.TraceService` provided after the router for route-aware tracing
- [ ] **`provideErrorHandler` for Sentry**: `app.config.ts` includes `{ provide: ErrorHandler, useValue: Sentry.createErrorHandler({ showDialog: false }) }`. Without this, uncaught errors hit Angular's default `ErrorHandler` (logs to console) instead of routing to Sentry. Flag absence on apps using `@sentry/angular`
- [ ] **`Sentry.TraceService` for router spans**: `app.config.ts` includes `{ provide: Sentry.TraceService, deps: [Router] }, provideAppInitializer(() => inject(Sentry.TraceService))` so route changes generate transaction spans. Flag absence as Medium - perf data without route context is hard to use
- [ ] **DSN / API key from env**, not committed; `environment.ts` `sentryDsn` is acceptable (DSN is a public token by design, but document the choice)
- [ ] **Release / environment tags** populated from build metadata (`release: process.env.BUILD_ID`, `environment: environment.production ? 'prod' : 'dev'`); flag bare default values
- [ ] **PII scrubbing on**: `sendDefaultPii: false` (default - flag explicit `true`); `beforeSend` strips known sensitive keys; `replaysSessionSampleRate` / `replaysOnErrorSampleRate` chosen deliberately (Replay records DOM and can inadvertently capture sensitive content - use `mask` / `block` selectors for inputs containing PII)
- [ ] **Custom `ErrorHandler` interaction**: if the project provides a custom `ErrorHandler` (not Sentry's), it must call `Sentry.captureException(error)` (or chain via `extends ErrorHandler` with `super.handleError` calling Sentry). A custom handler that swallows errors without forwarding loses every uncaught exception
- [ ] **HTTP error interceptor routes to logger**: a functional `HttpInterceptorFn` that catches HTTP errors should `Sentry.captureException` or pass to a structured logger - flag bare `catchError(() => of(null))` swallowing errors
- [ ] **Sample rate explicit**: `tracesSampleRate`, `profilesSampleRate`, `replaysSessionSampleRate` per env; not `1.0` in prod for tracing on a high-traffic app (cost + sampling-induced noise)
- [ ] **Sentry Replay vs. CSP `nonce`**: Sentry Session Replay injects inline scripts at runtime. A strict CSP (`script-src 'self' 'nonce-XXX'`) without `'unsafe-inline'` blocks Replay. When the diff adds Replay to a project with strict CSP (or vice versa), flag the conflict
- [ ] **`Sentry.captureMessage` / `captureException` payloads do not include PII**: `extra: { user: this.authService.currentUser() }` ships email, phone, address. Project the captured user to `{ id }` before passing through `extra` / `setContext`. The `Sentry.setUser` flow is the right channel for identification
- [ ] **Ignored errors documented**: `ignoreErrors: [...]` lists noise classes (browser extension errors, ResizeObserver loop limit, network errors during navigation); each entry has a comment justifying
- [ ] **Source maps uploaded**: build pipeline uploads source maps to Sentry (`@sentry/cli` post-build hook or `@sentry/webpack-plugin` for older Angular builders); absent means production stack traces are unreadable
- [ ] **Source maps NOT served publicly**: `angular.json` `"sourceMap": false` for production (or upload-then-strip via Sentry plugin). Public source maps are an information disclosure risk

### Step 6 - OpenTelemetry / Tracing

_Skipped at `quick` depth unless the diff touches OTel config or SSR server.ts._

**Browser-side (`@opentelemetry/sdk-trace-web` + `@opentelemetry/auto-instrumentations-web`):**

- [ ] **Browser SDK initialized**: `WebTracerProvider` registered with `BatchSpanProcessor` + OTLP exporter; auto-instrumentations enabled for `fetch`, `xhr`, `document-load`, user-interaction. Wire in `main.ts` before `bootstrapApplication` or in `app.config.ts` via `provideAppInitializer`
- [ ] **`traceparent` propagation**: outbound `HttpClient` calls to your own backend include `traceparent` header so backend spans link to the originating browser request. Cross-origin: backend must be in `propagateTraceHeaderCorsUrls` allowlist; CORS must allow `traceparent`. The `@opentelemetry/instrumentation-fetch` and `instrumentation-xml-http-request` auto-add the header for whitelisted origins
- [ ] **Sampling**: browser-side OTel must sample aggressively (not 100%) - cost on the client side is cheap, but downstream backend sampling alignment matters

**Server-side (Angular SSR):**

- [ ] **OTel registered in `server.ts`**: `@opentelemetry/sdk-node` `NodeSDK` with auto-instrumentations (HTTP, fetch, Express middleware - the SSR server runs on Express by default). Initialize before any request handler runs - earliest possible point in `server.ts`
- [ ] **Auto-instrumentations**: applied to Express middleware, fetch calls from server context, any database client used in `Resolver` server-side
- [ ] **Sampling explicit and noise-aware**: `ParentBasedSampler(TraceIdRatioBasedSampler(0.1))` per env; not left at default. For SSR with health checks dominating volume, prefer custom `Sampler` returning `RECORD_AND_SAMPLED` for business endpoints and `DROP` for noise
- [ ] **Resource attributes populated**: `service.name`, `service.version`, `deployment.environment` - from build metadata / env vars
- [ ] **Trace context propagation**: SSR server receives `traceparent` from upstream load balancer; verify auto-instrumentation does this without manual wrapping. Graceful shutdown via `sdk.shutdown()` on `SIGTERM`; `BatchSpanProcessor` (not `SimpleSpanProcessor` which blocks the event loop)

### Step 7 - Structured Client Logging

_Skipped at `quick` depth unless the diff modifies logging utilities or routes containing `console.*` calls._

- [ ] **No `console.log` / `console.error` in production paths**: replaced with a structured logger that posts to RUM / Sentry (`Sentry.captureMessage` for warnings, `Sentry.captureException` for errors). `console.log` skips error-tracker integration, sample rates, and PII redaction
- [ ] **`console.*` payloads are amplified by Sentry Replay / breadcrumbs**: Sentry's default `consoleIntegration` captures every `console.*` call as a breadcrumb, and Replay records console output as part of the session. A single `console.log(JSON.stringify(largeObject))` therefore (a) ships the payload to every Sentry event's breadcrumb trail and (b) lands in every recorded Replay session. Cross-reference any `console.*` finding here with the Replay sample rate and `sendDefaultPii` setting from Step 5, then escalate by stack-up:
  - **High** - high replay sampling (e.g., `replaysSessionSampleRate >= 0.5`) + console-of-PII without input `mask` / `block` selectors. The breadcrumb-trail leak alone is enough.
  - **Critical** - the High case **plus** `sendDefaultPii: true` (or equivalent un-redacted user context). The second pathway (default PII attached to every event) compounds the breadcrumb leak.

  Note the compound in **one** finding with the cross-reference, not three loosely-related findings.
- [ ] **Log levels respected**: `console.error` only for actual errors caught by `ErrorHandler`; navigation / interaction events go to RUM events, not the console
- [ ] **Sensitive-field hygiene**: log payloads do not include `password`, `token`, `authorization`, `Authorization`, `Cookie`, raw HTTP responses with PII; `Sentry.beforeBreadcrumb` strips known sensitive keys
- [ ] **No log spam in component constructor / `ngOnInit`**: a `console.log(this.input())` inside `ngOnInit` fires on every component instantiation (cheap-but-noisy in dev, real cost in prod via RUM); flag for removal
- [ ] **Custom events for RUM**: significant user actions (signup, checkout, payment) emit a structured RUM event so retention / funnel analytics ground in real data, not page views alone

### Step 8 - User Identity and Session Correlation

_Skipped at `quick` depth unless the diff touches auth providers or a Sentry context wrapper._

- [ ] **`Sentry.setUser({ id, email? })`** called after auth succeeds; `Sentry.setUser(null)` on logout. `email` only when consent / privacy posture allows. For Angular with auth library, hook into the auth state via a service: `effect(() => { const user = this.authService.currentUser(); Sentry.setUser(user ? { id: user.id } : null); })`
- [ ] **`Sentry.setTag` for tenant / role / feature flag**: tenant ID, user role, A/B test variant, feature flag keys exposed as tags so filters work in Sentry / RUM
- [ ] **`Sentry.setContext` for richer per-event metadata**: build version, route, query parameters (sanitized) - structured, queryable
- [ ] **No PII in tags**: tags are searchable strings - keep cardinality bounded (tenant ID OK, full name not OK)

### Step 9 - Real User Monitoring (RUM) Integration

_Skipped at `quick` depth and on apps without a chosen RUM provider._

When a RUM SDK is in use (Datadog RUM, New Relic, Cloudflare Web Analytics, custom):

- [ ] **SDK initialized once at app entry**, before any router hooks execute - missed pageviews on first navigation otherwise
- [ ] **SPA navigation tracked**: SDK detects route changes via `Router.events` `NavigationEnd`; Datadog RUM auto-detects when wired correctly via `trackViewsManually: false`. Custom RUM may need explicit `Router.events.subscribe(e => ... if e instanceof NavigationEnd ...)`
- [ ] **Custom events / actions** for business-critical interactions (checkout step completed, plan upgraded) - synthetic dashboards should not rely solely on page views
- [ ] **Privacy / DNT respected**: Do-Not-Track header / cookie banner integration; `navigator.doNotTrack === '1'` short-circuits init in privacy-sensitive jurisdictions
- [ ] **Correlation with error tracker / OTel**: same `userId` / `sessionId` / `traceId` flow into RUM events so a slow user can be cross-referenced to their errors and traces

### Step 10 - Health and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one measurable SLI (LCP < 2.5s, INP < 200ms, CLS < 0.1 - the Core Web Vitals "good" thresholds; or a custom RUM metric for a journey-specific outcome)
- [ ] SLOs documented in code (decorator / module README, route-level config) - not a free-floating Confluence page
- [ ] Error rate per route tracked via Sentry / RUM; spike alerts wired
- [ ] Synthetic checks (Datadog Synthetics, Checkly) for critical journeys; these complement RUM but do not replace it
- [ ] Build-size budgets per route enforced in CI (`angular.json` `budgets`); LCP regressions correlate with bundle growth


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Angular (or accepted from parent dispatcher); SSR status recorded
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent - the parent already gated)
- [ ] Instrumentation surfaces (web-vitals reporter, `ErrorHandler` / Sentry SDK init, OTel browser / SSR SDK init, structured logger, RUM SDK) read directly before applying checklists; Surface Map produced
- [ ] Web Vitals (LCP / INP / CLS / TTFB / FCP) reporting verified; INP present (not legacy FID); `web-vitals` v4+ confirmed; attribution build recommended where slow paths exist; SPA route correlation verified via `Router.events`
- [ ] Error tracker assessed: Sentry SDK wired with `Sentry.createErrorHandler()` provided as `ErrorHandler`, `Sentry.TraceService` provided for router span instrumentation, HTTP error interceptor routes to logger
- [ ] OpenTelemetry assessed: browser SDK + auto-instrumentation + `traceparent` propagation, SSR `server.ts` OTel init, sampling explicit and noise-aware, source maps uploaded but not served; raw `NodeSDK` setups have shutdown + BatchSpanProcessor
- [ ] Sentry Replay vs. CSP `nonce` conflict checked when both surfaces appear in the diff
- [ ] `Sentry.captureMessage` / `captureException` `extra` / `setContext` payloads checked for PII (project user objects to `{ id }` before passing)
- [ ] Structured client logging assessed: no `console.log` in prod paths, sensitive-field redaction, RUM events for business-critical actions
- [ ] When both `console.*` of a non-trivial payload AND high Replay sampling / `sendDefaultPii: true` appear in the same diff, they are surfaced as one compound finding (with cross-reference) rather than three disconnected ones
- [ ] User identity / session correlation assessed: `Sentry.setUser` / tags / context for tenant / role / flag, no PII in high-cardinality tags
- [ ] RUM integration assessed when a RUM SDK is in use: SPA navigation tracked via `Router.events`, custom events for journeys, privacy / DNT respected
- [ ] Findings name an Angular / web-vitals / Sentry / OTel idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/logging-detail/identity/RUM/SLI steps unless diff signals required them; `deep` ran the SLI step
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

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

| Surface                       | Verdict                        | Evidence                                      |
| ----------------------------- | ------------------------------ | --------------------------------------------- |
| Web Vitals                    | wired / partial / absent       | [file:line or "no web-vitals reporter found"] |
| ErrorHandler + Sentry SDK     | wired / partial / absent       | [...]                                         |
| OpenTelemetry (browser)       | wired / partial / absent       | [...]                                         |
| OpenTelemetry (server, SSR)   | wired / partial / absent / n/a | [...]                                         |
| Structured logging            | wired / partial / absent       | [...]                                         |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent` - it tells the reader the review is scaffolding, not auditing. Use the same `absent` vocabulary throughout.

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Angular idiom: missing INP reporter (only legacy FID), `Sentry.createErrorHandler` not provided as `ErrorHandler`, no `Sentry.TraceService` for router spans, web-vitals reporter missing route correlation via `Router.events`, OTel `traceparent` not propagated to backend, source maps served publicly, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Angular / SDK change with code or config example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. Within each impact bucket, group findings by surface (Web Vitals / Error Tracker / Tracing / Logging / RUM) when more than 2 findings share a surface; otherwise list flat. Greenfield reviews collapse a whole surface into one finding per the Step 3 grouping rule._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Switch to `web-vitals/attribution` build for LCP element identification", "Add `Sentry.TraceService` provider for router span instrumentation", "Add SSR-side OTel via `@opentelemetry/sdk-node` in server.ts"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting instrumentation, dashboard work, ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Provide `Sentry.createErrorHandler()` as `ErrorHandler` in app.config.ts:24 so uncaught errors route to Sentry"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire RUM transport endpoint to org analytics ingestion"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Angular / SDK idiom ("add metrics" vs "register `web-vitals` `onINP` reporter and post via `sendBeacon` to RUM endpoint from `main.ts` after `bootstrapApplication`, with route correlation via `Router.events` `NavigationEnd`")
- Recommending generic observability advice when an Angular SDK or convention exists (say "use `@sentry/angular` with `Sentry.createErrorHandler()` provided as `ErrorHandler`", not "add error tracking")
- Reviewing infra-level concerns (Datadog dashboards, Sentry org settings, log forwarder config, on-call rotation) - those are not in source code
- Approving Sentry initialization inside a component constructor (re-initializes on every mount and may cause double-reporting); init goes in `main.ts` / `app.config.ts`
- Approving `Sentry.init({ dsn })` without `Sentry.createErrorHandler()` provided as `ErrorHandler` - errors land in console only
- Approving `console.log` as a logging strategy in production paths - flag for replacement with the structured logger / RUM event
- Approving `web-vitals` reporter wired only to `console.log` - that is dev-only; production needs a real transport
- Approving `replaysSessionSampleRate: 1.0` in prod for an app handling PII without `mask` / `block` configuration on Sentry Replay
- Approving FID-only web-vitals reporting - INP replaced FID in 2024 as a Core Web Vital; missing INP signals stale config
- Approving `ErrorHandler` that swallows errors without forwarding to Sentry / structured logger
- Approving missing source-map upload to Sentry - production stack traces are then unreadable
- Approving public source-map serving in production without justification - information disclosure
- Recommending `Sentry.setUser({ email, name, ... })` when only `id` is needed - PII minimization first
- Producing one finding per missing checkbox when an entire surface is absent - collapse into one High finding per surface per Step 3's grouping rule
