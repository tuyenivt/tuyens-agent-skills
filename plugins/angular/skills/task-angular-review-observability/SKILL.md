---
name: task-angular-review-observability
description: Angular observability review - web-vitals, Sentry, OpenTelemetry browser SDK, SSR tracing, structured logs, RUM correlation.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

# Angular Observability Review

Stack-specific delegate of `task-code-review-observability` for Angular. Focuses on Angular library + SDK wiring: `web-vitals`, `@sentry/angular` with `Sentry.createErrorHandler()` provided as `ErrorHandler` and `Sentry.TraceService` for router spans, OpenTelemetry browser SDK + SSR `@opentelemetry/sdk-node`, structured client logging, RUM correlation. Infra-level concerns (dashboards, alert rules, log forwarders) are out of scope.

## When to Use

- Reviewing an Angular PR for observability regressions or instrumentation gaps
- Pre-release observability check for a new app or major feature
- Post-incident review when client-side diagnosis was slow

**Not for:** general Angular code review (`task-angular-review`), perf with known bottleneck (`task-angular-review-perf`), active incident (`/task-oncall-start`), infra observability.

## Depth Levels

| Depth      | Runs                                              |
| ---------- | ------------------------------------------------- |
| `standard` | All steps (default)                               |
| `deep`     | All steps + SLI/SLO suggestions per critical route |

## Invocation

| Invocation                                    | Meaning                                  |
| --------------------------------------------- | ---------------------------------------- |
| `/task-angular-review-observability`          | Current branch vs base                   |
| `/task-angular-review-observability <branch>` | `<branch>` vs base (3-dot diff)          |
| `/task-angular-review-observability pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch) |

Subagent mode: parent passes precondition handle + read diff/log; Step 3 skipped.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Angular, stop and recommend `/task-code-review-observability`. Record `Angular: <version>`, `SSR: enabled | disabled`. Steps 7 and 9 branch on the SSR signal.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read diff + commit log once, reuse. Skip if parent passed the handle.

### Step 4 - Map the Instrumentation Surface

Produce a one-line verdict per surface (web-vitals / error tracker / OTel browser / OTel server SSR / structured logging / RUM) of the form `wired | partial | absent`.

**Grouping rules:**

- **Absent surface:** emit **one** High-Impact finding listing all missing pieces. Per-callsite findings only when the surface exists and a callsite misuses it.
- **Partial surface:** emit one finding per distinct misuse (web-vitals collected but no transport AND no `Router.events` correlation = two findings). Do not collapse partials.

Read the files that configure observability so findings cite real lines: `app.config.ts` / `app.config.server.ts` / `main.ts` / `main.server.ts` / `server.ts` / `*.interceptor.ts` / `*.service.ts` / `package.json` / `angular.json`.

### Step 5 - Web Vitals Reporting

- [ ] `web-vitals` v4+ installed; reporter wired in `main.ts` (after `bootstrapApplication`) or via `provideAppInitializer`; SSR-guarded with `isPlatformBrowser` / `afterNextRender`. Legacy `APP_INITIALIZER` is valid but flag for migration when seen.
- [ ] All Core Web Vitals: `onLCP` / `onINP` / `onCLS` (+ optional `onTTFB`, `onFCP`). INP must be present - missing INP signals legacy `getFID` config.
- [ ] Reporter posts to a real RUM/analytics endpoint via `navigator.sendBeacon` or `fetch({ keepalive: true })`. Not `console.log`.
- [ ] Sample at the reporter; metric collection ungated.
- [ ] Route correlation: subscribe to `Router.events` `NavigationEnd` so SPA navigations get distinct metrics.
- [ ] Recommend `web-vitals/attribution` when slow paths exist.

### Step 6 - Error Boundaries and Error Tracking

- [ ] `@sentry/angular` initialized in `main.ts` (before `bootstrapApplication`) via `Sentry.init({ dsn, integrations: [browserTracingIntegration(), replayIntegration()] })`
- [ ] `Sentry.createErrorHandler()` provided as `ErrorHandler` in `app.config.ts`:
  ```typescript
  providers: [{ provide: ErrorHandler, useValue: Sentry.createErrorHandler({ showDialog: false }) }]
  ```
  Without this, uncaught errors only hit Angular's default handler (console).
- [ ] Router span tracking: `@sentry/angular` v8+ - `browserTracingIntegration()` handles it automatically; v7 - provide `Sentry.TraceService` after `Router`. Flag mixing both as a finding.
- [ ] DSN from env or `environment.ts` (public token by design); `release` / `environment` from build metadata.
- [ ] PII discipline: `sendDefaultPii: false`; `beforeSend` strips sensitive keys; `replaysSessionSampleRate` / `replaysOnErrorSampleRate` chosen deliberately with `mask` / `block` selectors.
- [ ] HTTP error `HttpInterceptorFn` routes to `Sentry.captureException` or structured logger; flag `catchError(() => of(null))` that swallows.
- [ ] Sample rates explicit per env (`tracesSampleRate`, `profilesSampleRate`); not `1.0` in prod on high traffic.
- [ ] Sentry Replay vs strict CSP: Replay injects inline scripts; `script-src 'self' 'nonce-XXX'` without `'unsafe-inline'` blocks it. v8+ `replayIntegration({ nonce: '<request-nonce>' })` resolves it - flag mismatched config when both surfaces appear in the diff.
- [ ] Source maps uploaded (`@sentry/cli` / `@sentry/webpack-plugin`); `angular.json` production `sourceMap: false` or stripped after upload.
- [ ] **Retry-amplification check.** When a new HttpInterceptor adds `retry(N)` without instrumenting attempt count, one failing request becomes N captured errors. Cap or tag retries (`Sentry.captureException(err, { tags: { retry: attempt } })`).

### Step 7 - OpenTelemetry / Tracing

**Browser:**

- [ ] `WebTracerProvider` + `BatchSpanProcessor` + OTLP exporter; auto-instrumentations for `fetch`/`xhr`/`document-load`/user-interaction; wired in `main.ts` or `provideAppInitializer`
- [ ] `traceparent` propagated: backend in `propagateTraceHeaderCorsUrls`; CORS allows `traceparent`
- [ ] Sampling explicit, aligned with backend

**Server (SSR `server.ts`):**

- [ ] `@opentelemetry/sdk-node` `NodeSDK` initialized before any request handler
- [ ] Auto-instrumentations: HTTP, fetch, Express, DB clients
- [ ] Sampling: `ParentBasedSampler(TraceIdRatioBasedSampler(...))`; drop health-check noise
- [ ] Resource attributes: `service.name`, `service.version`, `deployment.environment`
- [ ] `BatchSpanProcessor` (not `SimpleSpanProcessor`); `sdk.shutdown()` on `SIGTERM`

### Step 8 - Structured Client Logging

- [ ] No `console.log` / `console.error` in production paths; replaced with a structured logger (`ngx-logger`, `pino/browser`, or a project-local `LoggerService` that fans out to Sentry breadcrumbs + a RUM custom event).
- [ ] **Replay/breadcrumb compound check.** Sentry's `consoleIntegration` ships every `console.*` as a breadcrumb; Replay records console output. When diff has `console.*` of non-trivial payload AND high Replay sampling, surface as ONE finding cross-referenced to Step 6:
  - **High** when `replaysSessionSampleRate >= 0.5` without input `mask` / `block`
  - **Critical** when the High case also has `sendDefaultPii: true`
- [ ] Sensitive fields stripped via `Sentry.beforeBreadcrumb`: no `password`, `token`, `authorization`, `Cookie`.
- [ ] No log spam in `constructor` / `ngOnInit` (fires per instantiation - RUM cost).
- [ ] Custom RUM events for business-critical actions (signup, checkout, payment).

### Step 9 - User Identity and Session Correlation

- [ ] `Sentry.setUser({ id })` on auth success; `Sentry.setUser(null)` on logout. Hook via `effect(() => Sentry.setUser(this.auth.currentUser() ? { id: ... } : null))`. `email` only with explicit consent.
- [ ] `Sentry.setTag` for tenant / role / feature-flag keys (bounded cardinality - no full names).
- [ ] `Sentry.setContext` for build version, route, sanitized query params.

### Step 10 - RUM Integration

- [ ] RUM SDK initialized at app entry, before router hooks (else first navigation pageview lost)
- [ ] SPA navigation tracked via `Router.events` `NavigationEnd` (Datadog auto-detects with `trackViewsManually: false`; custom RUM needs explicit subscription)
- [ ] Custom events for business journeys
- [ ] DNT / consent respected
- [ ] Correlation: shared `userId` / `sessionId` / `traceId` across RUM, Sentry, OTel

### Step 11 - Health and SLIs (deep depth only)

- [ ] Critical journeys have a measurable SLI (CWV thresholds or journey-specific RUM metric)
- [ ] SLOs documented in code
- [ ] Per-route error rate tracked; spike alerts wired
- [ ] Synthetic checks (Datadog Synthetics, Checkly) for critical journeys
- [ ] `angular.json` `budgets` enforced in CI

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Print confirmation line.

## Self-Check

- [ ] Principles loaded; stack confirmed; Angular version + SSR recorded
- [ ] Diff resolved once; precondition handle reused
- [ ] Surface Map produced with `wired | partial | absent` per surface; absent collapsed into one finding each, partials emit per-misuse findings
- [ ] Web Vitals (INP, transport, route correlation), Error tracker (`createErrorHandler`, `TraceService`, PII, Replay/CSP), OTel (browser + SSR `NodeSDK`), Structured logging, Identity, RUM checked; SLI/SLO at `deep`
- [ ] Findings name Angular / SDK idioms (`Sentry.createErrorHandler`, `web-vitals` `onINP`); library-scoped, infra deferred
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered High > Medium > Low
- [ ] Report written; confirmation line printed

## Output Format

```markdown
## Angular Observability Review Summary

**Stack:** Angular <version> / SSR: <enabled|disabled>
**Web Vitals:** wired | partial | absent
**Error Tracker:** Sentry (@sentry/angular) | Honeybadger | Rollbar | absent
**Tracing (browser):** OpenTelemetry web SDK | absent
**Tracing (server, SSR):** server.ts + @opentelemetry/sdk-node | absent | n/a (SPA only)
**RUM:** Datadog RUM | New Relic | Cloudflare Web Analytics | custom | absent
**Overall:** Adequate | Gaps Found [counts] | Greenfield - no observability surface wired [counts]

## Surface Map

| Surface                     | Verdict                        | Evidence                                      |
| --------------------------- | ------------------------------ | --------------------------------------------- |
| Web Vitals                  | wired / partial / absent       | [file:line or "no reporter found"]           |
| ErrorHandler + Sentry SDK   | wired / partial / absent       | [...]                                         |
| OpenTelemetry (browser)     | wired / partial / absent       | [...]                                         |
| OpenTelemetry (server, SSR) | wired / partial / absent / n/a | [...]                                         |
| Structured logging          | wired / partial / absent       | [...]                                         |
| RUM                         | wired / partial / absent       | [...]                                         |

> Use **Greenfield** in the headline when 3+ rows are `absent`.

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the idiom: missing INP reporter, `Sentry.createErrorHandler` not provided, no `TraceService` for router spans, `traceparent` not propagated, source maps public, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Angular / SDK change with code]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit empty buckets. Group by surface when 3+ findings share one._

## Recommendations

[Structural improvements not tied to a single finding]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [e.g., "Provide `Sentry.createErrorHandler()` as `ErrorHandler` in app.config.ts:24"]
2. **[Delegate]** [Recommend] [scope: ops] - [...]

_Omit if no actionable findings._
```

## Avoid

- State-changing git commands - user runs these
- Generic phrasing ("add observability") instead of naming the SDK idiom
- Infra review (dashboards, alert rules, log forwarders, on-call rotation)
- `Sentry.init` inside a component constructor (re-initializes per mount)
- One finding per missing checkbox when an entire surface is absent - collapse per Step 3
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
