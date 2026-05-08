---
name: task-angular-review-perf
description: Angular performance review for Core Web Vitals (LCP, INP, CLS), bundle size, change detection cost, signal vs zone.js / zoneless, RxJS subscription overhead, `@defer` placement, lazy-loaded routes, `NgOptimizedImage`, SSR + `TransferState` / HTTP transfer cache, NgRx selectors. Stack-specific override of task-code-review-perf, invoked when stack-detect resolves to Angular.
agent: angular-performance-engineer
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, performance, core-web-vitals, bundle, ssr, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Angular Performance Review

## Purpose

Angular-aware performance review that names Core Web Vitals (LCP, INP, CLS), bundle splitting via `loadComponent` / `loadChildren` / `@defer`, change-detection cost (`OnPush` mandate, signal-driven updates, zoneless adoption), `computed` vs method, signal vs `BehaviorSubject` overhead, RxJS subscription discipline (`takeUntilDestroyed`, `async` pipe, `toSignal` + `requireSync`), `NgOptimizedImage`, `provideClientHydration(withHttpTransferCacheOptions(...))`, `TransferState`, NgRx selector memoization, and `@defer` placement directly instead of routing through the generic frontend adapter. Produces findings with measured or estimated impact (LCP delta, bundle delta, CD-cycle delta) and concrete fixes using TypeScript-strict Angular idioms.

This workflow is the stack-specific delegate of `task-code-review-perf` for Angular. The core workflow's contract (invocation, diff resolution, output format) is preserved.

## When to Use

- Reviewing an Angular PR or branch for performance regressions
- Investigating a slow page, route, or component (high INP, slow LCP, jank during interaction)
- Pre-merge perf pass on changes touching the bundle (new dependency, new route, new lazy component), data fetching, change-detection strategy, or rendering
- Quarterly Core Web Vitals / bundle-size sweep against RUM-flagged routes

**Not for:**

- General Angular code review (use `task-code-review` or `task-angular-review`)
- Security review (use `task-code-review-security` or `task-angular-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-angular-implement`)

## Depth Levels

| Depth      | When to Use                                                        | What Runs                                                                |
| ---------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `quick`    | Single component or route ("is this re-rendering ok?")             | Steps 4 + 5 only; change-detection hotspots + bundle deltas              |
| `standard` | Default - full Angular perf review                                 | All steps                                                                |
| `deep`     | RUM-driven review with Core Web Vitals data, profiling, or budgets | All steps + capacity guidance, route budget plan, perf-test instructions |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                           | Meaning                                                                                               |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `/task-angular-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-angular-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-angular-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If the detected stack is not Angular, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Angular 17+ and TypeScript strict mode.

Detect:

- Angular major version (17+ has `@if` / `@for` / `@defer`; 19+ has `linkedSignal`; 20+ has signal-based forms; 21+ has `resource()`)
- Change detection: `provideExperimentalZonelessChangeDetection` / `provideZonelessChangeDetection` in `app.config.ts` → **zoneless**; otherwise zone.js
- SSR: `@angular/ssr` package + `provideClientHydration` in `app.config.ts` → SSR enabled
- HTTP transfer cache: `provideClientHydration(withHttpTransferCacheOptions({...}))` present?

Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled`, `HTTP transfer cache: on | off | n/a`. The configuration drives which checklists in Steps 4-9 apply.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern rendering, change detection, bundle, and data fetching so impact estimates ground in real code:

- Every changed `*.component.ts` / `*.component.html` / `*.component.scss` - rendering surface
- Every changed `*.service.ts` - HTTP / state surface
- Every changed `*.routes.ts` / `app.routes.ts` - route configuration, lazy loading
- `app.config.ts` / `app.config.server.ts` - providers, change-detection mode, SSR config, hydration, HTTP transfer cache
- `angular.json` - build budgets, optimizer config, source maps, defer block configuration
- `package.json` for new dependencies - flag any client-side dependency > 50KB minified+gzipped
- Every changed `*.directive.ts` / `*.pipe.ts` - directives bind to template change-detection cost
- NgRx stores (`*.store.ts` / `*.reducer.ts` / `*.selectors.ts`) - selector memoization, action invalidation patterns
- Components using `@defer` blocks - placement and triggers

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new shared component imports a heavy library that becomes part of every page that uses it), read the unchanged file too - the regression lives there.

### Step 4 - Change Detection and Re-Render Hotspots

Use skill: `angular-component-patterns` for component shape; use skill: `angular-signals-patterns` for signal correctness.

Inspect every changed component / directive / service for:

- [ ] **OnPush mandate**: every `@Component` declares `changeDetection: ChangeDetectionStrategy.OnPush`. Default change detection in a new component is a [High] - it dirties on every event in the entire `NgZone` (zone.js) or every signal write (zoneless). Existing Default-CD components are out of scope; flag only when the diff touches the `@Component` decorator
- [ ] **Signal-driven state in new code**: new local state uses `signal()` / `computed()` rather than `BehaviorSubject` + `async`. `BehaviorSubject` requires manual subscription, schedules CD via `markForCheck()` after `async` pipe emission, and bridges through the Zone for change detection. Signals integrate with the new local change detection (Angular 17+) and minimize the dirty-checking surface
- [ ] **`computed` over getter functions in templates**: `{{ expensiveCalc() }}` in a template re-runs every change detection cycle. Wrap with `computed`, store in a field, and read `expensiveCalc()` (now a signal call - cached). For pure functions called once per render this is fine; for derived state from signals, `computed` is the idiom
- [ ] **`effect` discipline**: `effect()` is for side effects only - DOM imperative work, third-party library sync, logging. NOT for deriving state. `effect(() => mySignal.set(otherSignal() + 1))` is a [High] - use `computed` or `linkedSignal`
- [ ] **`effect` cleanup**: `effect((onCleanup) => { const sub = obs.subscribe(); onCleanup(() => sub.unsubscribe()) })` - flag missing cleanup on long-lived effects subscribing to observables, intervals, or DOM listeners
- [ ] **`untracked` for cutting deps**: `effect(() => { logSomething(currentSignal()); untracked(() => trackingSignal()) })` - flag effects re-firing on irrelevant signal reads when `untracked` would prevent it
- [ ] **`toSignal` `initialValue` / `requireSync`**: `toSignal(obs$)` returns `Signal<T | undefined>`; templates handle `undefined` poorly. Provide `initialValue` for the synchronous case, or `{ requireSync: true }` when the source is a `BehaviorSubject` / `ReplaySubject(1)` and the synchronous read is guaranteed
- [ ] **Subscription leak via bare `.subscribe()`**: every `.subscribe()` in a component / directive must use `takeUntilDestroyed()` (in injection context) or `async` pipe / `toSignal()` in template. Bare `.subscribe()` is a [High] memory-leak finding - the subscription survives navigation and accumulates
- [ ] **`async` pipe over manual subscribe**: template binding `{{ user$ | async }}` over `ngOnInit` `.subscribe()` + field assignment. The pipe handles unsubscription on view destroy and triggers CD via `markForCheck()` automatically
- [ ] **`@for` `track` correctness**: `track $index` on a reorderable / filterable / removable list breaks DOM reuse and re-creates child components on every reorder - blows away component state and triggers full re-render. `track item.id` is right. Flag both missing track and `track $index` on dynamic lists
- [ ] **`@for` over thousands of items without virtualization**: rendering 1000+ items without `cdk-virtual-scroll-viewport` (`@angular/cdk/scrolling`) causes long initial render and laggy scroll. Threshold scales with row complexity: simple row × 1000+ or complex row × 100+
- [ ] **`@defer` placement**: heavy below-the-fold components (charts, editors, maps) wrapped in `@defer (on viewport) { <app-chart /> } @placeholder { ... }`. Flag eager `<app-chart />` for components used only on user interaction or below the fold
- [ ] **`@defer` missing trigger**: `@defer { ... }` defaults to `on idle`; explicit triggers (`on viewport`, `on interaction`, `on hover`, `when cond()`) are clearer and often match intent better. Missing `@placeholder` causes content shift when the deferred block loads - flag for CLS impact
- [ ] **Inline arrow / template function reference instability**: `[config]="{ a: 1 }"` or `(click)="() => doThing(item)"` in a template creates a new object/function on every CD cycle. Under OnPush this still re-evaluates the binding; in a `@for` over 1000 items this compounds. Lift to a `computed` or method reference
- [ ] **`@HostListener` on noisy events**: `@HostListener('window:scroll')` / `'window:mousemove'` triggers a full app-tick CD pass on zone.js (every event). Use `fromEvent(window, 'scroll').pipe(throttleTime(...))` outside the zone (`runOutsideAngular`), or signal-based DOM listeners
- [ ] **Heavy synchronous work in `ngOnInit` / `constructor`**: parsing, sorting, filtering large arrays, JSON serialization in component init blocks rendering. Move to a service with caching, a worker, or `requestIdleCallback`
- [ ] **`NgRx` selector instability**: selectors returning a fresh object literal each call (`createSelector(..., state => ({ ...state }))`) defeat memoization - downstream `select()` re-emits on every action. Use `createSelector` with stable returns; `withMethods` / `computed` in NgRx Signal Store

### Step 5 - Bundle Size and Code Splitting

- [ ] **Lazy-loaded routes**: feature routes use `loadComponent: () => import('./feature.component').then(m => m.FeatureComponent)` (component-level) or `loadChildren: () => import('./feature.routes').then(m => m.routes)` (route-tree). Eager `component:` for non-trivial routes is a [High] bundle finding - the component lands in the initial bundle
- [ ] **`@defer` for heavy below-the-fold components**: charting (`chart.js`, `apexcharts`, `echarts`), rich text (`tiptap`, `quill`), date pickers, maps - wrap in `@defer` with `on viewport` / `on interaction`. Eager imports are a [High] even when the page genuinely uses the chart - LCP impact is the same
- [ ] **New dependencies measured**: any new entry in `dependencies` (not `devDependencies`) gets a size note. Flag anything > 50KB minified+gzipped that is not lazy-loaded
- [ ] **Heavy libraries pulled into the client bundle eagerly**: `moment` (use `date-fns` / `dayjs` / native `Intl`), `lodash` (use `lodash-es` and tree-shake; better, native or `radash`), full Angular Material module imports
- [ ] **Tree-shake friendly imports**: `import isEqual from 'lodash/isEqual'` (or `lodash-es`); never `import _ from 'lodash'`. `import { format } from 'date-fns'` not `import * as df from 'date-fns'`. Named imports also matter for `chart.js`, `rxjs` (`import { map, filter } from 'rxjs'` not `import * as rx from 'rxjs'`)
- [ ] **Angular Material per-component imports**: `import { MatButton } from '@angular/material/button'` (standalone import) - the per-module imports `@angular/material/button` tree-shake correctly. Flag eager full-library imports if any appear
- [ ] **`angular.json` budgets**: `"budgets": [{ "type": "initial", "maximumWarning": "500kb", "maximumError": "1mb" }]` should be set; flag absence in projects with > 1MB initial bundles
- [ ] **Source maps in production**: `"sourceMap": false` for production builds (or upload-then-strip via Sentry plugin); public source maps leak source code structure
- [ ] **Build optimizer / vendor chunks**: Angular 17+ esbuild-based builder is the default for new projects; flag old `webpack` builder unless project pinned

> **Impact heuristic - bundle blast radius.** A 50KB gzip dependency on the home route adds ~50KB transferred on every cold visit (every visitor, every device). On 3G that is ~1.3s longer download; on cable ~50ms; the worst case dominates LCP for budget-constrained users. Phrase the impact as "+<N>KB on every cold visitor of every route that imports this," not "the bundle got bigger."

### Step 6 - Data Fetching and Caching

Use skill: `angular-service-patterns` for HTTP service patterns; use skill: `angular-rxjs-patterns` for operator selection.

- [ ] **HTTP cache via `provideClientHydration(withHttpTransferCacheOptions({...}))`**: under SSR, server-fetched data is automatically cached and reused on hydration - no double-fetch. Flag SSR projects without `provideClientHydration` or with HTTP transfer cache disabled
- [ ] **`TransferState` for non-HTTP server-computed data**: `makeStateKey<T>('foo')` + `transferState.set/get` to avoid re-computing on hydration. Flag manual `HttpClient` wrappers that re-fetch the same URL on hydration
- [ ] **`shareReplay({ bufferSize: 1, refCount: true })` for shared HTTP observables**: a service exposing `getCurrentUser()` should cache the result; flag unmemoized `HttpClient.get` calls fanned out across components
- [ ] **N+1 fan-out over a list**: `forkJoin(items.map(i => http.get(`/api/detail/${i.id}`)))` parallelizes N requests but is still N round-trips. Flag and recommend a batched server endpoint (`/api/details?ids=...`)
- [ ] **Sequential awaits / chained switchMap for independent fetches**: `switchMap` chains for two independent HTTP calls block end-to-end. Use `forkJoin([a$, b$])` for parallel
- [ ] **HTTP cache headers respected**: server-set `Cache-Control` headers honored by the browser; service-side caching layered on top (not in lieu of). Flag client-side cache implementations that ignore server cache directives
- [ ] **Mutation invalidation explicit**: after a `POST` / `PUT` / `DELETE`, dependent caches invalidated (NgRx action dispatched, signal-based cache `set()` updated, or `shareReplay` source re-triggered). Flag mutations that succeed but UI shows stale data
- [ ] **No `HttpClient.get()` in render path**: a component template binding to a method that calls `HttpClient.get` re-fires on every CD cycle - fetches a stream of duplicate requests. Move to a service + `signal()` / `BehaviorSubject` / `shareReplay`

### Step 7 - Core Web Vitals and Page Load

_Skipped at `quick` depth unless the diff touches a route, layout, or assets._

**LCP (Largest Contentful Paint):**

- [ ] **`NgOptimizedImage` for images**: `<img ngSrc="..." width="..." height="..." priority>` for hero / above-the-fold images. The `priority` attribute marks for `<link rel="preload">` and high-priority fetch. Raw `<img>` is a [Medium] for non-decorative images
- [ ] **`width` / `height` attributes** on every image (prevents CLS even when async-decoded); `NgOptimizedImage` enforces this
- [ ] **Hero image not deferred**: above-the-fold image must not be inside a `@defer` block, gated by `*ngIf` for slow data, or set to `loading="lazy"`
- [ ] **`font-display: swap`** for self-hosted webfonts; flag `font-display: block` for above-the-fold text
- [ ] **Critical CSS inlined**: Angular SSR with hydration inlines critical CSS by default (`provideClientHydration`); flag SSR projects rendering above-the-fold content with all CSS in external stylesheets

**INP (Interaction to Next Paint):**

- [ ] **No long synchronous tasks on user input**: form submit handler doing 50ms of synchronous work blocks paint. Defer via microtask / `setTimeout(0)` or break into chunks
- [ ] **Heavy filtering / search uses signals + debounce**: typing into a search box that filters a 10K-row list on every keystroke janks. Debounce via `debounceTime(...)` on an RxJS source converted to signal, or `effect()` with explicit debouncing
- [ ] **Zone.js patch overhead**: zone.js patches DOM events; deeply nested event handlers + change detection passes can spike INP. Zoneless mode (Angular 18+) eliminates this overhead - flag projects with high INP that have not evaluated zoneless

**CLS (Cumulative Layout Shift):**

- [ ] **Reserved space for `@defer` blocks**: `@placeholder { <skeleton-card /> }` with the same dimensions as the deferred content
- [ ] **Skeletons / placeholders with same dimensions** as the final content (`h-64 w-full` for an image slot, fixed-height containers for ads / embeds)
- [ ] **No layout thrash from late-loading fonts**: `font-display: swap` + `size-adjust` / `ascent-override` font metrics overrides
- [ ] **Late-injecting elements at the top of the page**: A/B test snippets, banners, cookie modals that push content down trigger CLS - reserve space or load below the fold

### Step 8 - Server-Side Rendering and Hydration

_Skipped on Angular projects without SSR (`@angular/ssr` not in deps)._

- [ ] **`provideClientHydration()` enabled**: hydration reuses server-rendered DOM on the client (vs full re-render); flag SSR projects without it - first paint is fine but CD passes immediately re-render the entire tree, defeating SSR
- [ ] **`withHttpTransferCacheOptions({})`**: HTTP transfer cache reuses server-fetched responses on hydration; flag absence
- [ ] **Browser-only APIs guarded under SSR**: `window`, `document`, `localStorage`, `IntersectionObserver` accessed in component code that runs server-side crashes. Wrap with `if (isPlatformBrowser(this.platformId))` or move into `afterNextRender(() => ...)` / `ngAfterViewInit` (client-only) hooks. `afterNextRender` is the modern idiom (Angular 16+)
- [ ] **`afterNextRender` / `afterRender` for DOM-dependent work**: bridge browser-only APIs to a hook that only runs on the client - avoids SSR crashes and waits for the DOM to be ready
- [ ] **`ngOnInit` does HTTP work that runs twice**: in SSR, `ngOnInit` runs once on server, once on client (without transfer cache). With HTTP transfer cache on, the second call returns cached. Flag SSR projects where critical-path HTTP calls re-fire on hydration
- [ ] **`@defer` under SSR**: `@defer` blocks are server-rendered as their `@placeholder` content (Angular 17+); they only "defer" the bundle download on the client. Flag `@defer` wrapping above-the-fold content - the placeholder is what users see, which may not be what was intended
- [ ] **No mutable module-level state**: `let cache = {}` mutated by render or events leaks across SSR requests. Flag for service-scoped or signal-based state

### Step 9 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-angular-review-observability`. From a perf perspective, confirm only:

- [ ] Critical user journeys reachable from this PR have **some** instrumentation (`web-vitals` reporter wired, RUM SDK active, Sentry Angular SDK with `BrowserTracing`, or server-side tracing via Node OTel); if not, raise as a Low/Recommendation finding and delegate to `task-angular-review-observability` rather than dictating the design here
- [ ] No `console.log` left in render path / template / `ngOnInit` of a hot route - if visible in the diff. If not in the diff, skip

Anything beyond presence/absence (sample rates, attribution, route segmentation) → `task-angular-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Angular; version, change-detection mode (zone.js / zoneless), SSR enabled / disabled, HTTP transfer cache on / off recorded before any configuration-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface read directly (changed components, services, route configs, `app.config.ts`, NgRx stores, `@defer` blocks, `angular.json`)
- [ ] `angular-component-patterns` and `angular-signals-patterns` consulted for change-detection hotspots; `angular-rxjs-patterns` consulted for subscription overhead
- [ ] OnPush + signal-first audit applied; Default change detection in new components flagged
- [ ] `effect` vs `computed` vs `linkedSignal` audited; `effect` writing back to signals flagged
- [ ] RxJS subscription hygiene checked (`takeUntilDestroyed`, `async` pipe, `toSignal`); bare `.subscribe()` in components flagged
- [ ] `@for` `track`, `@defer` placement / triggers / placeholder reviewed
- [ ] Bundle deltas assessed for any new `dependencies` entry; tree-shake-friendly imports verified; lazy-loaded route discipline verified for new routes
- [ ] N+1 fan-out (`forkJoin(items.map(...))`) flagged when present; batched-query alternative recommended
- [ ] HTTP transfer cache + `TransferState` reviewed for SSR projects; double-fetch on hydration flagged
- [ ] `shareReplay` / signal cache reviewed for shared HTTP observables; in-template HTTP calls flagged
- [ ] Core Web Vitals (LCP image / fonts / CLS reservations / INP debounce / `NgOptimizedImage` priority) checked when route or asset code changed
- [ ] SSR + hydration / `afterNextRender` / browser-API guards reviewed for SSR projects; Vite / non-SSR section skipped on SPA-only projects
- [ ] Every finding states impact - measured (`LCP: 2.8s -> 1.4s`) when RUM data exists, estimated otherwise (`+45KB gzip on every cold visit to /dashboard`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-9; `deep` adds capacity guidance and budget plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Angular Performance Review Summary

**Stack Detected:** Angular <version> / TypeScript <version>
**Change detection:** zone.js | zoneless
**SSR:** enabled | disabled
**HTTP transfer cache:** on | off | n/a
**Scope:** Frontend (Angular)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Angular idiom: Default change detection on a list component, bare `.subscribe()` leaking on navigation, missing `track` on `@for`, eager Material Datepicker on a route that uses it once, missing `NgOptimizedImage priority` on hero, SSR re-fetch without HTTP transfer cache, `effect` writing back to a signal, NgRx selector returning fresh object literal each call, etc.]
- **Impact:** [estimated effect - e.g., "+120KB gzip on every cold visit to /dashboard" or measured "LCP 2.8s -> 1.4s after fix"]
- **Fix:** [specific Angular change with code example - `changeDetection: OnPush`, `takeUntilDestroyed()`, `loadComponent`, `@defer (on viewport)`, `provideClientHydration(withHttpTransferCacheOptions({}))`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Adopt zoneless change detection for the high-frequency interaction routes", "Convert long lists to `cdk-virtual-scroll-viewport`", "Add bundle budget to angular.json"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, build config change, or perf-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `changeDetection: OnPush` to src/app/orders/order-list.component.ts:12 and convert state from BehaviorSubject to signal"]
2. **[Delegate]** [High] [scope: build] - [one-line action, e.g., "Add bundle budget for /dashboard route - spawn build-config subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Angular idiom ("this is slow" vs "Default change detection on a 1000-row `@for` list re-renders every row on every event in the zone")
- Recommending generic frontend advice when an Angular pattern applies (say "wrap in `@defer (on viewport)`", not "lazy load")
- Suggesting `computed` everywhere as a default - the cost is cheap but cache invalidation still costs; only use when the value is reused or genuinely derived
- Approving raw `<img>` for hero / above-the-fold images - `<img ngSrc priority>` via `NgOptimizedImage` is the right tool
- Approving Default change detection on new components - OnPush + signals is the canonical shape
- Approving bare `.subscribe()` in components - leak guaranteed
- Approving `effect` for state derivation - use `computed` / `linkedSignal`
- Approving `@for` without `track` or with `track $index` on dynamic lists
- Approving SSR projects without `provideClientHydration` + HTTP transfer cache - first-paint benefit, double-fetch cost
- Approving full-library Angular Material imports - per-component imports tree-shake
- Conflating perf review with general code review or security review - delegate those to their workflows
- Treating high re-render counts as inherently bad - signals + OnPush make CD cheap; only investigate when a profile or interaction lag implicates re-renders
