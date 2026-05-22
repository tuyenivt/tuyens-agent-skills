---
name: task-vue-review-observability
description: Vue / Nuxt observability review - web-vitals, Sentry Vue/Nuxt SDK, errorCaptured, OpenTelemetry browser + Nitro, RUM, structured logs.
agent: vue-tech-lead
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, observability, web-vitals, sentry, opentelemetry, rum, workflow]
  type: workflow
user-invocable: true
---

Stack-specific delegate of `task-code-review-observability` for Vue. Library/SDK-level only - infra config (Datadog dashboards, Sentry org settings, log forwarders, alert rules) is out of scope.

## When to Use

- Vue PR observability review or regression check (Nuxt 3, Vite + Vue Router)
- Pre-release or post-incident audit of client-side instrumentation
- Adopting `web-vitals` / Sentry / OpenTelemetry / RUM in a Vue app
- Auditing error-boundary placement and crash-reporting paths

**Not for:** general review (`task-vue-review`), perf (`task-vue-review-perf`), active incidents (`/task-oncall-start`), infra dashboards/alerts.

## Depth

| Depth      | When                                       | What Runs                             |
| ---------- | ------------------------------------------ | ------------------------------------- |
| `quick`    | Single component or route                  | Steps 1-6, 12                         |
| `standard` | Default                                    | All steps except 11                   |
| `deep`     | Pre-release of critical app, post-incident | All steps including SLI/SLO (Step 11) |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Confirm Vue. Record framework: Nuxt 3 | Vite + Vue Router. If not Vue, stop and redirect to `/task-code-review-observability`.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip if a parent workflow passed the handle plus pre-read artifacts.

### Step 4 - Surface Map

Read instrumentation wiring in the framework-appropriate files below, plus every changed file calling `Sentry.*`, `web-vitals` APIs, OTel APIs, or a logger. Produce one verdict per surface: `wired | partial | absent` with file:line evidence. A missing wire is the finding, not a precondition.

| Framework           | Files to open                                                                                                                                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nuxt 3              | `nuxt.config.{js,ts,mjs}`, `app.vue`, `error.vue`, `plugins/sentry.{client,server}.{ts,config.ts}`, `plugins/web-vitals.client.ts`, `plugins/otel.client.ts`, `server/plugins/*.ts`, `composables/*`, `package.json` |
| Vite + Vue Router   | `src/main.ts`, `src/router/*.ts`, `src/components/ErrorBoundary.vue`, `vite.config.{js,ts}`, `package.json`                                                                                                          |

| Surface                  | Look for                                                                                                                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Web Vitals               | `import { onLCP, onINP, onCLS } from 'web-vitals'` + transport; Nuxt `plugins/web-vitals.client.ts`                                       |
| Error tracker + boundary | `@sentry/nuxt` module or `@sentry/vue` `Sentry.init({ app, ... })`; `error.vue` calling `Sentry.captureException`; `app.config.errorHandler`; `errorCaptured` hook |
| OpenTelemetry (browser)  | `WebTracerProvider`, `@opentelemetry/sdk-trace-web`, `@opentelemetry/auto-instrumentations-web`, OTLP exporter                            |
| OpenTelemetry (server)   | Nitro `server/plugins/otel.ts` registering `@opentelemetry/sdk-node` `NodeSDK` (Nuxt only; `n/a` for Vite)                                |
| Structured logging       | Logger module posting to RUM/Sentry; absence shown by `console.log`/`console.error` in prod paths                                         |
| RUM                      | Datadog RUM / Vercel Analytics / Cloudflare Web Analytics / custom SDK init at app entry                                                  |

**Grouping rule.** If a whole surface is `absent`, produce one High finding listing the missing pieces grouped by target file/symbol - not one finding per sub-check.

**Greenfield exception.** If 3+ surfaces are `absent`, run Steps 5-10 at every depth; skip the per-step diff-touch gate.

### Step 5 - Web Vitals

- [ ] `web-vitals` v4+ in `package.json` (v2.x exports `getFID` - stale)
- [ ] All four core metrics reported: LCP, INP, CLS, TTFB (FCP optional); INP must replace FID
- [ ] Wiring: Nuxt `plugins/web-vitals.client.ts` registering reporters; Vite in `src/main.ts` after `app.mount(...)`
- [ ] Transport is real: `navigator.sendBeacon` or `fetch` with `keepalive: true` to RUM/analytics endpoint; `console.log` reporter is dev-only
- [ ] Each metric carries route/pathname (`useRoute().path`); SPA navigation tracked via `router.afterEach`
- [ ] Sample at the reporter, not at metric collection (`onLCP` itself must not be gated)
- [ ] `web-vitals/attribution` build recommended when LCP/INP/CLS values exist but root causes are opaque

### Step 6 - Error Tracker + Error Boundaries

- [ ] Sentry SDK initialized outside component bodies: Nuxt `@sentry/nuxt` module via `nuxt.config.ts` + `sentry.{client,server}.config.ts`, or `plugins/sentry.client.ts` calling `Sentry.init({ app, dsn, ... })`; Vite in `src/main.ts`
- [ ] `Sentry.init` receives the `app` argument (auto-wires `app.config.errorHandler`) and `router` for `browserTracingIntegration({ router })`
- [ ] DSN from env (`NUXT_PUBLIC_SENTRY_DSN` / `VITE_SENTRY_DSN` acceptable - DSN is a public token); `release` and `environment` from build metadata
- [ ] `tracesSampleRate`, `replaysSessionSampleRate`, `replaysOnErrorSampleRate` set per env; not `1.0` in prod for high-traffic apps
- [ ] PII scrubbing: `sendDefaultPii: false`; `beforeSend` strips sensitive keys; Replay uses `mask`/`block` selectors on PII inputs
- [ ] `ignoreErrors` entries each commented (ResizeObserver loop, browser-extension noise, navigation network errors)
- [ ] Error boundary tree:
  - Nuxt: root `error.vue` (and `pages/**/error.vue` if used) explicitly calling `Sentry.captureException(error)` - rendering a fallback without capture loses the diagnostic (flag High); `clearError({ redirect: '/' })` for recovery
  - Vite: root `<Sentry.ErrorBoundary>` or a wrapper component using `errorCaptured`; component-level `errorCaptured` on routes with non-trivial render / external data
- [ ] User-facing fallback with retry/reset action, not a blank screen
- [ ] Source maps uploaded via `@sentry/nuxt` module or `@sentry/vite-plugin`; not served publicly (`sourcemap.client: false` in Nuxt; Vite default unless `--sourcemap`)
- [ ] Sentry Replay vs strict CSP: if `script-src 'self' 'nonce-XXX'` without `'unsafe-inline'`, Replay inline scripts are blocked - flag conflict

### Step 7 - OpenTelemetry / Tracing

_Skip at `quick` unless diff touches OTel config or Nitro plugins (or greenfield applies)._

**Browser:**

- [ ] `WebTracerProvider` + `BatchSpanProcessor` + OTLP exporter; `@opentelemetry/auto-instrumentations-web` enables `fetch`, `xhr`, `document-load`, `user-interaction`; wire in Nuxt `plugins/otel.client.ts` or Vite `src/main.ts` before mount
- [ ] `traceparent` propagated on outbound fetch to own backend (including Nitro endpoints); backend host in `propagateTraceHeaderCorsUrls`; CORS allows `traceparent`
- [ ] Sampling explicit and aggressive on client (`TraceIdRatioBasedSampler`); aligned with backend ratio

**Server (Nuxt Nitro):**

- [ ] `server/plugins/otel.ts` registers `@opentelemetry/sdk-node` `NodeSDK` before any endpoint runs; edge runtime support limited - document the gap
- [ ] `BatchSpanProcessor` (not `SimpleSpanProcessor`), `SIGTERM` -> `sdk.shutdown()`
- [ ] Resource attributes: `service.name`, `service.version`, `deployment.environment` from build metadata / `runtimeConfig`
- [ ] Sampler aware of high-volume noise (health checks, prefetches) - custom `Sampler` dropping them beats flat ratio
- [ ] Trace context propagated into Nitro endpoints via auto-instrumentation (no manual wrapping)

### Step 8 - Structured Client Logging

_Skip at `quick` unless diff modifies logging utilities or adds `console.*` in prod paths (or greenfield applies)._

- [ ] No `console.log` / `console.error` in prod paths - routes to `Sentry.captureMessage` / `captureException` or a structured logger that hits RUM
- [ ] No log calls in `<script setup>` body (fires on every component setup)
- [ ] Sensitive-field hygiene: payloads exclude `password`, `token`, `authorization`, `Cookie`, raw responses with PII; `beforeBreadcrumb` strips known keys
- [ ] Business actions (signup, checkout step, payment) emit structured RUM events - not page views alone

### Step 9 - Identity, Session, Trace Correlation

_Skip at `quick` unless diff touches auth, RUM SDK init, or Sentry context wiring (or greenfield applies)._

- [ ] `Sentry.setUser({ id })` after auth; `Sentry.setUser(null)` on logout; `email` only with consent. Nuxt + `nuxt-auth-utils`: hook in a plugin via `watch(() => useUserSession().user, ...)`
- [ ] `Sentry.setTag` for low-cardinality dimensions (tenant, role, flag); no PII or unbounded values (no `userId` as tag)
- [ ] `Sentry.setContext` for build version, sanitized route/query
- [ ] **`extra` / `setContext` payloads project user to `{ id }` (or `{ id, role }`)** - never pass `session.user` whole
- [ ] Same `userId` / `sessionId` / `traceId` flow into RUM, Sentry, and OTel so a slow user cross-references to errors and traces

### Step 10 - RUM Integration

_Skip at `quick` and on apps without a chosen RUM provider (or greenfield applies)._

- [ ] SDK initialized once at app entry, before any router hook fires (first navigation otherwise unrecorded)
- [ ] SPA navigation tracked via `router.afterEach` (Nuxt and Vite); vendor auto-detect verified
- [ ] Custom events for business-critical interactions (checkout step completed, plan upgraded)
- [ ] DNT respected: `navigator.doNotTrack === '1'` short-circuits init where jurisdiction requires
- [ ] Privacy posture documented when Session Replay / session recording is on

### Step 11 - Health and SLIs (deep only)

- [ ] Critical journeys have at least one SLI (LCP < 2.5s, INP < 200ms, CLS < 0.1, or custom RUM metric)
- [ ] SLOs documented in code (route config / module README) - not free-floating in Confluence
- [ ] Error rate per route alerted via Sentry/RUM
- [ ] Synthetic checks (Datadog Synthetics, Checkly) complement RUM for critical journeys
- [ ] Bundle-size budget per route enforced in CI - LCP regressions correlate with bundle growth

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write the report to file and print the confirmation line.

## Output Format

```markdown
## Vue Observability Review Summary

**Stack:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**RUM:** Datadog RUM | Vercel Analytics | Cloudflare Web Analytics | custom | absent
**Overall:** Adequate | Gaps Found [High/Medium/Low counts] | Greenfield - 3+ surfaces absent

## Surface Map

| Surface                  | Verdict                        | Evidence                                      |
| ------------------------ | ------------------------------ | --------------------------------------------- |
| Web Vitals               | wired / partial / absent       | [file:line or "no web-vitals reporter found"] |
| Error tracker + boundary | wired / partial / absent       | [file:line]                                   |
| OpenTelemetry (browser)  | wired / partial / absent       | [file:line]                                   |
| OpenTelemetry (server)   | wired / partial / absent / n/a | [file:line; n/a for Vite]                     |
| Structured logging       | wired / partial / absent       | [file:line]                                   |
| RUM                      | wired / partial / absent       | [file:line]                                   |

_Use `absent` consistently (not `none`/`missing`/`not wired`). Set Overall to `Greenfield` when 3+ rows are `absent`._

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Gap Class:** [missing-wire | misconfigured | unsafe-default | pii-leak | noise]
- **Surface:** [Web Vitals | Error Tracker | Tracing | Logging | Identity | RUM]
- **Issue:** [name the Vue/SDK idiom: missing INP reporter, no `error.vue`, `Sentry.init` without `app` argument (skips `errorHandler` wiring), web-vitals reporter missing route correlation, OTel `traceparent` not propagated, source maps served publicly, `extra: { user: session.user }` shipping PII]
- **Impact:** [diagnosability | alertability | cost | privacy]
- **Suggested Instrumentation:** [specific code/config: API call, file to add, exact SDK option]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty buckets. Group by Surface within a bucket when >2 findings share one; otherwise list flat. Greenfield collapses a whole surface into one finding per the Step 4 grouping rule._

## Recommendations

[Structural improvements not tied to a single finding - e.g., swap `web-vitals` for `web-vitals/attribution`; adopt `@sentry/nuxt` module over bespoke `plugins/sentry.client.ts`; add a Nitro OTel plugin]

## Next Steps

Prioritized list. Each item tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting / ops). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [action]
2. **[Delegate]** [High] [scope: ops] - [action]
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Vue; framework recorded (Nuxt 3 / Vite + Vue Router)
- [ ] Step 3: diff and commit log read once and reused (or handle accepted from parent)
- [ ] Step 4: surface map produced with 6 verdicts and evidence; grouping/greenfield rules applied
- [ ] Step 5: web-vitals v4+, all four core metrics with INP, real transport, route correlation, sampling at reporter
- [ ] Step 6: Sentry init outside component bodies with `app` argument, env-driven release/env, sample rates per env, PII scrub, error-boundary tree with explicit `captureException` in `error.vue`, source maps uploaded but not public, Replay vs CSP conflict checked
- [ ] Step 7: OTel browser SDK + traceparent propagation; Nuxt Nitro plugin with shutdown, BatchSpanProcessor, edge gap documented (skipped per gate when applicable)
- [ ] Step 8: no `console.*` in prod paths, no log in `<script setup>` body, sensitive-field hygiene, RUM events for business actions (skipped per gate)
- [ ] Step 9: `setUser({ id })`, low-cardinality tags, `extra` projects user to `{ id }`, cross-tool correlation (skipped per gate)
- [ ] Step 10: RUM SDK init order, SPA nav tracking via `router.afterEach`, custom events, DNT respected (skipped per gate)
- [ ] Step 11: SLIs, SLOs in code, per-route error alerts, synthetics, bundle budgets (deep only)
- [ ] Step 12: report written via `review-report-writer`; confirmation printed

## Avoid

- Generic advice when a Vue/SDK idiom exists ("add metrics" vs "register `onINP` reporter in `plugins/web-vitals.client.ts` posting via `sendBeacon`")
- Per-checkbox findings when a whole surface is absent - collapse per the Step 4 grouping rule
- Approving Sentry init inside a component body - re-runs every mount, double-reports
- Approving `Sentry.init({ dsn })` without the `app` argument - skips `app.config.errorHandler` auto-wiring
- Approving `error.vue` that renders a fallback without calling `Sentry.captureException` (when `@sentry/nuxt` auto-capture is not installed)
- Approving FID-only web-vitals reporting (INP replaced FID in 2024)
- Approving `web-vitals` reporter wired only to `console.log`
- Approving `replaysSessionSampleRate: 1.0` in prod without `mask`/`block` on PII inputs
- Approving `extra: { user: session.user }` or `setContext` payloads carrying email/phone/address - project to `{ id }`
- Approving public source-map serving in production
- Approving missing source-map upload to Sentry - production stack traces unreadable
- Approving `userId`/`orderId` as Sentry tags (unbounded cardinality)
- Approving Sentry Replay on a strict CSP without addressing the inline-script conflict
- Approving error boundaries with a blank-screen fallback
- Infra scope (Datadog dashboards, Sentry org settings, log forwarders, alert rules) - delegate to ops review
- State-changing git commands
