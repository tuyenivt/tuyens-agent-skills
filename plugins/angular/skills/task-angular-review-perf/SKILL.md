---
name: task-angular-review-perf
description: Angular perf review: Core Web Vitals (LCP/INP/CLS), bundle size, change detection, signals/zoneless, @defer, NgOptimizedImage, SSR, NgRx selectors.
agent: angular-performance-engineer
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, performance, core-web-vitals, bundle, ssr, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Angular Performance Review

Stack-specific delegate of `task-code-review-perf` for Angular. Names Angular idioms directly (`OnPush`, signals, `@defer`, `NgOptimizedImage`, `loadComponent`, `provideClientHydration`, HTTP transfer cache, `takeUntilDestroyed`, NgRx selector memoization) rather than routing through the generic frontend adapter. Produces findings with measured or estimated impact (LCP delta, bundle delta, CD-cycle delta) and concrete fixes.

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

Use skill: `stack-detect` to confirm Angular. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-angular-review` (parent already detected Angular), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Angular, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Angular 17+ and TypeScript strict mode.

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

Canonical CD / signal / RxJS discipline lives in `angular-component-patterns`, `angular-signals-patterns`, `angular-rxjs-patterns`. This step is a review-scoped scan for the diff:

- [ ] **OnPush mandate**: new `@Component` without `changeDetection: ChangeDetectionStrategy.OnPush` is [High] - dirties on every Zone event (zone.js) or every signal write (zoneless). Flag only when the diff touches the decorator
- [ ] **Signal-first new state**: new local state uses `signal()` / `computed()` not `BehaviorSubject` + `async` (manual subscription, Zone bridge, more dirty-checking)
- [ ] **`computed` over template getter calls**: `{{ expensiveCalc() }}` re-runs every CD cycle - wrap with `computed` for derived signal state
- [ ] **`effect` misuse**: side effects only (DOM, library sync, logging). `effect(() => mySignal.set(...))` is [High] - use `computed` / `linkedSignal`. Long-lived effects holding subscriptions / intervals / observers need `onCleanup`; use `untracked` to break dep tracking
- [ ] **`toSignal` initial value**: missing `initialValue` returns `Signal<T | undefined>` (template handles poorly); use `{ requireSync: true }` when source is `BehaviorSubject` / `ReplaySubject(1)`
- [ ] **Bare `.subscribe()` in component / directive**: [High] memory leak - use `takeUntilDestroyed()` (injection context required), `async` pipe, or `toSignal`
- [ ] **`@for` `track`**: `track $index` on a reorderable / filterable / removable list breaks DOM reuse and re-creates child components ([High]); missing `track` is [High]
- [ ] **`@for` × 1000+ items without `cdk-virtual-scroll-viewport`** (`@angular/cdk/scrolling`); threshold scales with row complexity (simple × 1000+ or complex × 100+)
- [ ] **`@defer` placement / triggers**: heavy below-fold components (charts, editors, maps) wrapped with explicit `on viewport` / `on interaction` / `when cond()` (default `on idle` rarely intended). Missing `@placeholder` → CLS
- [ ] **Identity instability in templates**: `[config]="{ a: 1 }"` or `(click)="() => doThing(item)"` allocates per CD cycle; in `@for × 1000` this compounds. Lift to `computed` or method reference
- [ ] **`@HostListener('window:scroll' / 'window:mousemove')`** triggers app-tick on every event (zone.js); use `fromEvent` + `throttleTime` + `runOutsideAngular`, or signal-based listeners
- [ ] **Heavy sync work in `ngOnInit` / constructor**: parse / sort / filter / serialize large arrays - move to cached service, worker, or `requestIdleCallback`
- [ ] **NgRx selector instability**: `createSelector(..., state => ({ ...state }))` defeats memoization - downstream re-emits on every action. Stable returns; NgRx Signal Store `withMethods` / `computed`

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

Canonical HTTP / RxJS idioms live in `angular-service-patterns` and `angular-rxjs-patterns`. Review-scoped scan:

- [ ] **SSR HTTP transfer cache**: `provideClientHydration(withHttpTransferCacheOptions({...}))` reuses server-fetched data on hydration. Flag SSR projects without it - double-fetch on every page
- [ ] **`TransferState` for non-HTTP server-computed data** to avoid re-computation on hydration
- [ ] **Shared HTTP cache**: `shareReplay({ bufferSize: 1, refCount: true })` on `getCurrentUser` / config endpoints; flag unmemoized `HttpClient.get` fanned across components
- [ ] **N+1 fan-out**: `forkJoin(items.map(i => http.get(...)))` is N round-trips - recommend a batched endpoint
- [ ] **Sequential `switchMap` for independent fetches** blocks end-to-end - use `forkJoin([a$, b$])` for parallel
- [ ] **Mutation invalidation missing**: post-mutation, dependent caches must be invalidated (NgRx dispatch / signal cache `set()` / re-trigger `shareReplay` source)
- [ ] **`HttpClient.get()` in render path / template binding** re-fires every CD cycle - move to a service + `signal()` / `shareReplay`

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

Use skill: `review-report-writer` with `report_type: review-perf`. Write the assembled output to the report file and print the confirmation line.

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
- **Issue:** [what the problem is - name the Angular idiom: Default CD on a list component, bare `.subscribe()` leaking on navigation, missing `track` on `@for`, eager Material Datepicker, missing `NgOptimizedImage priority` on hero, SSR re-fetch without HTTP transfer cache, `effect` writing back to a signal, NgRx selector returning a fresh object literal, etc.]
- **Impact:** [measured `LCP 2.8s -> 1.4s` when RUM data exists, estimated `+120KB gzip on every cold visit to /dashboard` otherwise - never "this is slow"]
- **Fix:** [specific Angular change with code - `changeDetection: OnPush`, `takeUntilDestroyed()`, `loadComponent`, `@defer (on viewport)`, `provideClientHydration(withHttpTransferCacheOptions({}))`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Adopt zoneless CD for high-frequency interaction routes", "Convert long lists to `cdk-virtual-scroll-viewport`", "Add bundle budget to angular.json"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, build config, or perf-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `changeDetection: OnPush` to src/app/orders/order-list.component.ts:12 and convert state from BehaviorSubject to signal"]
2. **[Delegate]** [High] [scope: build] - [one-line action, e.g., "Add bundle budget for /dashboard route - spawn build-config subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Self-Check

- [ ] Step 1: Angular stack confirmed; version, CD mode, SSR, HTTP transfer cache recorded
- [ ] Step 2: `review-precondition-check` ran (or handle received); diff + commit log read once and reused; pr-ref fetch surfaced to user, not executed; `head_matches_current=false` was user-approved (or parent gated)
- [ ] Step 3: Performance surface read directly (components, services, route configs, `app.config.ts`, NgRx stores, `@defer` blocks, `angular.json`)
- [ ] Step 4: OnPush + signal-first audit applied; `effect` vs `computed` / `linkedSignal`; RxJS subscription hygiene; `@for track`; NgRx selector stability
- [ ] Step 5: Bundle deltas for new `dependencies` measured; tree-shake imports verified; lazy-load discipline for new routes
- [ ] Step 6: SSR HTTP transfer cache + `TransferState` reviewed; `shareReplay` / signal cache for shared observables; in-template HTTP calls flagged; N+1 fan-out flagged
- [ ] Step 7: Core Web Vitals (LCP image / fonts / CLS reservations / INP debounce / `NgOptimizedImage priority`) checked when route or asset code changed (skipped at `quick` unless touched)
- [ ] Step 8: SSR + hydration / `afterNextRender` / browser-API guards reviewed for SSR projects; section skipped on SPA-only
- [ ] Step 9: Observability presence/absence noted; depth delegated to `task-angular-review-observability` (skipped at `quick`)
- [ ] Step 10: Every finding states measured or estimated impact; findings ordered by impact; depth honored (`quick`=Steps 4+5; `standard`=4-9; `deep`+capacity & budget plan); Next Steps tagged `[Implement]`/`[Delegate]`; report written via `review-report-writer` and confirmation printed

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command - the user must run these
- Reporting "this is slow" without naming the Angular idiom or stating impact (KB gzip, LCP delta, CD-cycle cost)
- Recommending generic frontend advice when an Angular pattern applies ("wrap in `@defer (on viewport)`", not "lazy load")
- Suggesting `computed` as a default - only when the value is reused or genuinely derived
- Treating high re-render counts as inherently bad - signals + OnPush make CD cheap; investigate only when a profile or interaction lag implicates re-renders
- Conflating perf review with general code review, security review, or observability audit - delegate those to their workflows
