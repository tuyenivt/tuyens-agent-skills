---
name: task-angular-review-perf
description: Angular perf review - Core Web Vitals, bundle size, change detection, signals/zoneless, @defer, NgOptimizedImage, SSR, selectors.
agent: angular-performance-engineer
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, performance, core-web-vitals, bundle, ssr, workflow]
  type: workflow
user-invocable: true
---

# Angular Performance Review

Stack-specific delegate of `task-code-review-perf` for Angular. Names Angular idioms directly (`OnPush`, signals, `@defer`, `NgOptimizedImage`, `loadComponent`, HTTP transfer cache, `takeUntilDestroyed`, selector memoization). Findings carry measured or estimated impact (LCP delta, bundle delta, CD-cycle delta) and concrete fixes.

## When to Use

- Angular PR / branch perf review
- Slow page, route, or component (high INP, slow LCP, jank)
- Pre-merge perf pass on bundle / data / CD / rendering changes
- Quarterly CWV / bundle sweep against RUM-flagged routes

**Not for:** general code review (`task-angular-review`), security review (`task-angular-review-security`), incident response (`/task-oncall-start`), feature design (`task-angular-implement`).

## Depth Levels

| Depth      | Runs                                                                     |
| ---------- | ------------------------------------------------------------------------ |
| `standard` | All steps (default)                                                      |
| `deep`     | All steps + capacity guidance, route budget plan, perf-test instructions |

## Invocation

| Invocation                           | Meaning                                  |
| ------------------------------------ | ---------------------------------------- |
| `/task-angular-review-perf`          | Current branch vs base                   |
| `/task-angular-review-perf <branch>` | `<branch>` vs base (3-dot diff)          |
| `/task-angular-review-perf pr-<N>`   | PR head fetched into `pr-<N>`            |

Subagent mode: parent passes precondition handle + read diff/log; Step 3 skipped.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Angular, stop and recommend `/task-code-review-perf`. Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled`, `HTTP transfer cache: on | off | n/a`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read diff + commit log once. Skip if parent passed the handle.

### Step 4 - Read the Performance Surface

Before applying checklists, open the files governing rendering, CD, bundle, and data so impact estimates ground in real code:

- Changed `*.component.ts/.html/.scss` (rendering)
- Changed `*.service.ts` (HTTP / state)
- Changed `*.routes.ts` / `app.routes.ts` (routes, lazy loading)
- `app.config.ts` / `app.config.server.ts` (providers, CD mode, SSR, transfer cache)
- `angular.json` (budgets, optimizer, source maps)
- `package.json` for new deps - flag any > 50KB minified+gzipped
- NgRx stores (selector memoization, action patterns)
- Components using `@defer`

For diffs that ripple through unchanged files (new shared component importing a heavy library), read those too.

**Grouping rule.** When one root cause trips multiple checkboxes (eager `chart.js` import fires Step 5 OnPush, Step 6 bundle, Step 8 LCP), emit **one** finding citing the root cause and listing the symptoms. Per-symptom findings only when each is independently actionable.

### Step 5 - Change Detection and Re-Render Hotspots

Canonical CD/signal/RxJS discipline lives in `angular-component-patterns`, `angular-signals-patterns`, `angular-rxjs-patterns`. Review-scoped scan:

- [ ] **OnPush mandate** on new `@Component` ([Recommend] when diff touches the decorator).
- [ ] **Signal-first new state** - prefer `signal()` / `computed()` over `BehaviorSubject` + `async`.
- [ ] **`@for track`** - missing or `track $index` on reorderable list is [Recommend].
- [ ] **`@for` × 1000+ items without `cdk-virtual-scroll-viewport`** (threshold scales with row complexity).
- [ ] **`@defer` placement/triggers** - heavy below-fold components (charts, editors, maps) wrapped with explicit `on viewport` / `on interaction`. Missing `@placeholder` -> CLS.
- [ ] **Bare `.subscribe()` in component / directive** - [Recommend] memory leak.
- [ ] **`effect` misuse** - `effect(() => mySignal.set(...))` is [Recommend] - use `computed` / `linkedSignal`. NgRx selectors returning fresh literals defeat memoization.

### Step 6 - Bundle Size and Code Splitting

- [ ] **Lazy-loaded routes** - feature routes use `loadComponent` / `loadChildren`. Eager `component:` for non-trivial routes is [Recommend] bundle finding.
- [ ] **`@defer` for heavy below-the-fold components** - charting (`chart.js`, `apexcharts`), rich text (`tiptap`, `quill`), date pickers, maps. Eager imports are [Recommend].
- [ ] **New dependencies measured** - flag > 50KB minified+gzipped not lazy-loaded. Prefer tree-shake-friendly imports (`import { format } from 'date-fns'`, not `import * as df`).
- [ ] **`angular.json` budgets** - `{ type: "initial", maximumWarning: "500kb", maximumError: "1mb" }`; flag absence in projects > 1MB initial.

> **Impact heuristic.** A 50KB gzip dependency on the home route adds ~50KB on every cold visit. Phrase impact as "+<N>KB on every cold visitor of every route that imports this," not "the bundle got bigger."

### Step 7 - Data Fetching and Caching

Canonical patterns in `angular-data-fetching`. Review-scoped scan:

- [ ] **SSR HTTP transfer cache** - `provideClientHydration(withHttpTransferCacheOptions({...}))` reuses server-fetched data. Flag SSR projects without it - double-fetch on every page.
- [ ] **`TransferState`** for non-HTTP server-computed data.
- [ ] **Shared HTTP cache** - `shareReplay({ bufferSize: 1, refCount: true })` on `getCurrentUser` / config endpoints.
- [ ] **N+1 fan-out** - `forkJoin(items.map(i => http.get(...)))` is N round-trips; recommend batched endpoint.
- [ ] **Mutation invalidation** - post-mutation, dependent caches must be invalidated.
- [ ] **`HttpClient.get()` in template binding** re-fires every CD cycle.

### Step 8 - Core Web Vitals and Page Load

**LCP:**

- [ ] **`NgOptimizedImage`** for images: `<img ngSrc="..." width="..." height="..." priority>` for hero. Raw `<img>` for non-decorative is [Recommend].
- [ ] **`width` / `height` attributes** on every image (prevents CLS); `NgOptimizedImage` enforces.
- [ ] **Hero image not deferred**, gated by `*ngIf` for slow data, or `loading="lazy"`.
- [ ] **`font-display: swap`** for self-hosted webfonts.

**INP:**

- [ ] **No long synchronous tasks on user input** (form submit doing 50ms blocks paint).
- [ ] **Heavy filter/search uses signals + debounce** (`debounceTime(...)` via RxJS bridge).

**CLS:**

- [ ] **`@placeholder` with same dimensions** as deferred content (`h-64 w-full` for image slots).
- [ ] **No late-injecting content at top** (A/B test snippets, banners, cookie modals).

### Step 9 - SSR and Hydration

_Skipped on SPA-only projects. Transfer-cache wiring is owned by Step 7 - do not double-flag._

- [ ] **`provideClientHydration()`** enabled (else CD passes immediately re-render the entire tree).
- [ ] **`provideHttpClient(withFetch())`** present - prerequisite for the transfer cache to intercept `HttpClient`.
- [ ] **Browser-only APIs guarded** - `window`/`document`/`localStorage`/`IntersectionObserver` wrapped with `isPlatformBrowser` or `afterNextRender` (the modern idiom).
- [ ] **`provideEventReplay()`** for INP under SSR (Angular 18+).
- [ ] **NG0500 hydration mismatch** in console - DOM diff drift between server and client render; usually a browser-only API in render path.

### Zoneless

_Only if `provideZonelessChangeDetection` is in the diff or already enabled._

- [ ] **Third-party libs assuming Zone.js** (chart libraries, jQuery plugins) require manual CD trigger via `ApplicationRef.tick()` or migration.
- [ ] **Async tasks not signal-tracked** (raw `setTimeout`, `setInterval`, `addEventListener`) won't trigger CD - wrap state mutations in signals.
- [ ] **Tests** - `provideZonelessChangeDetection` in `TestBed.configureTestingModule`; `fixture.detectChanges()` still required.

### Step 10 - Observability for Perf (delegation)

Presence check only - depth belongs to `task-angular-review-observability`. Confirm: critical journeys have some instrumentation (web-vitals reporter, RUM SDK, Sentry `BrowserTracing`, or server OTel). Note gap; do not duplicate the audit.

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`. Print confirmation line.

## Output Format

```markdown
## Angular Performance Review Summary

**Stack:** Angular <version> / <CD mode> / SSR: <enabled|disabled> / HTTP transfer cache: <on|off|n/a>
**Scope:** Frontend (Angular)
**Overall:** Clean | Issues Found [counts]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [name the Angular idiom: Default CD on list component, bare `.subscribe()` leaking on nav, missing `track`, eager chart.js, missing `NgOptimizedImage priority` on hero, SSR re-fetch without transfer cache, NgRx selector returning fresh object literal, etc.]
- **Impact:** [measured `LCP 2.8s -> 1.4s` when RUM data exists; estimated `+120KB gzip on every cold visit to /dashboard` otherwise. Never "this is slow"]
- **Fix:** [specific Angular change with code]

### Medium Impact / Low Impact
[Same structure]

_Omit empty buckets._

## Recommendations

[Structural improvements not tied to a finding - e.g., "Adopt zoneless CD for high-frequency routes", "Convert long lists to `cdk-virtual-scroll-viewport`"]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [e.g., "Add `changeDetection: OnPush` and convert `BehaviorSubject` to signal in src/app/orders/order-list.component.ts:12"]
2. **[Delegate]** [Recommend] [scope: build] - [e.g., "Add bundle budget for /dashboard route"]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Principles loaded; stack confirmed; CD mode, SSR, transfer cache recorded
- [ ] Diff resolved once; precondition handle reused
- [ ] Performance surface read directly before checklists
- [ ] Steps 5-10 applied per depth; every finding states measured or estimated impact
- [ ] Findings ordered by impact; Next Steps tagged `[Implement]`/`[Delegate]`
- [ ] Report written; confirmation line printed

## Avoid

- State-changing git commands - user runs these
- "This is slow" without naming the Angular idiom or stating impact (KB gzip, LCP delta, CD-cycle cost)
- Generic frontend advice when an Angular pattern applies ("wrap in `@defer (on viewport)`", not "lazy load")
- Treating high re-render counts as inherently bad - signals + OnPush make CD cheap; investigate only when a profile implicates re-renders
- Conflating perf review with general review, security, or observability - delegate
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
