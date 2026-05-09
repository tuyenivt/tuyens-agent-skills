---
name: task-vue-review-perf
description: Vue / Nuxt perf review: Core Web Vitals, bundle size, hydration, reactivity hotspots, Pinia, useFetch cache, routeRules, prerender, images.
agent: vue-performance-engineer
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, performance, core-web-vitals, bundle, ssr, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Vue Performance Review

## Purpose

Vue-aware performance review that names Core Web Vitals (LCP, INP, CLS), bundle splitting via `defineAsyncComponent` / Nuxt `<LazyXxx />` auto-imports, Nuxt `useFetch` / `useAsyncData` cache keys / `transform` / `getCachedData`, Pinia store granularity, `computed` vs method, `shallowRef` / `shallowReactive` for large structures, watcher discipline (`watchEffect` vs `watch` + flushing), `<NuxtImg>` / `<NuxtPicture>` and `@nuxt/fonts`, hydration cost, and `routeRules` (`prerender` / `swr` / `isr`) directly instead of routing through the generic frontend adapter. Produces findings with measured or estimated impact (LCP delta, bundle delta, hydration time) and concrete fixes using TypeScript-strict Vue 3 idioms.

This workflow is the stack-specific delegate of `task-code-review-perf` for Vue. The core workflow's contract (invocation, diff resolution, output format) is preserved.

## When to Use

- Reviewing a Nuxt or Vite + Vue PR or branch for performance regressions
- Investigating a slow page, route, or component (high INP, slow LCP, jank during interaction)
- Pre-merge perf pass on changes touching the bundle (new dependency, new route, new lazy component), data fetching, or rendering boundaries
- Quarterly Core Web Vitals / bundle-size sweep against RUM-flagged routes

**Not for:**

- General Vue code review (use `task-code-review` or `task-vue-review`)
- Security review (use `task-code-review-security` or `task-vue-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-vue-implement`)

## Depth Levels

| Depth      | When to Use                                                        | What Runs                                                                |
| ---------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `quick`    | Single component or route ("is this re-rendering ok?")             | Steps 4 + 5 only; reactivity hotspots + bundle deltas                    |
| `standard` | Default - full Vue perf review                                     | All steps                                                                |
| `deep`     | RUM-driven review with Core Web Vitals data, profiling, or budgets | All steps + capacity guidance, route budget plan, perf-test instructions |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                       | Meaning                                                                                               |
| -------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-vue-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-vue-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-vue-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Vue. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-vue-review` (parent already detected Vue), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Vue, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes Vue 3.5+ and TypeScript strict mode.

Then detect the framework:

- `nuxt.config.{js,ts,mjs}` present / `nuxt` in `package.json` deps → **Nuxt 3**
- `vite.config.{js,ts}` present / `vite` in deps + `vue` without `nuxt` → **Vite + Vue Router**
- Both present → ask the user which surface this PR targets; do not guess

The framework decision drives which checklists in Steps 4-7 apply. Record `Framework: Nuxt 3 | Vite + Vue Router` for the Summary block. Also record `Vue: <version>` (Vue 3.5 unlocks reactive props destructure, `useId`, `useTemplateRef`, stable Suspense; Vue 3.4 unlocks `defineModel`).

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern rendering, hydration, bundle, and data fetching so impact estimates ground in real code:

**Nuxt 3 surface:**

- Every changed `pages/**/*.vue`, `layouts/**/*.vue`, `components/**/*.vue`, `app.vue`, `error.vue`
- Every changed `server/api/**/*.ts`, `server/routes/**/*.ts`, `server/middleware/**/*.ts` - Nitro server endpoints affect LCP via SSR data flow
- `nuxt.config.{js,ts,mjs}` - `routeRules` (prerender / swr / isr / cache), `experimental` (`payloadExtraction`, `viewTransition`, `componentIslands`), `nitro` config, `image` module, `vite` overrides
- Every changed `composables/**/*.ts` - `useFetch` / `useAsyncData` callsites, custom composable reactivity surface
- Pinia stores (`stores/**/*.ts`) - state shape, getters, action invalidation patterns
- Lazy components (`<LazyXxx />` auto-import or `defineAsyncComponent`) and `<Suspense>` boundaries
- `package.json` for new dependencies - flag any client-side dependency > 50KB minified+gzipped

**Vite + Vue Router surface:**

- Every changed `src/**/*.vue` component and composable - all components run client-side; SSR is opt-in (Vite SSR template) and uncommon
- `vite.config.{js,ts}` - plugins (`vue`, `vue-jsx`), `build.rollupOptions`, manual chunks, code-split config
- `src/router/*.ts` / `src/main.ts` - route definitions, dynamic `import()` route components, `<Suspense>` boundaries
- Pinia stores
- `package.json` for new client dependencies

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new shared component imports a heavy library that becomes part of every page that uses it), read the unchanged file too - the regression lives there.

### Step 4 - Reactivity and Re-Render Hotspots

Use skill: `vue-composables-patterns` for canonical composable / reactivity discipline; use skill: `vue-component-patterns` for component shape.

Inspect every changed component / composable for:

- [ ] **Deep `reactive(largeObject)` for read-only data**: `reactive()` recursively wraps every nested property in a proxy - on a 500-row dataset the cost compounds. Use `shallowReactive` / `shallowRef` for large immutable structures (API responses, lookup tables) and only deep-reactive the slice that actually mutates
- [ ] **`reactive` for primitive values**: `reactive({ count: 0 })` works but `ref(0)` is the idiom; flag when the only reason for `reactive` is to share a primitive
- [ ] **Destructuring a `reactive` loses reactivity**: `const { a, b } = reactive({ a, b })` - `a` and `b` are now plain values. Use `toRefs` / `toRef`, or in Vue 3.5+ destructure props directly (which compiles to reactive accessors)
- [ ] **Spreading a `reactive` loses reactivity**: `{ ...state }` makes a plain object copy; pass `state` directly or use `toRefs(state)` when sharing fields with a child via `defineProps`
- [ ] **`computed` that does heavy work without dep filtering**: a `computed` reading `largeArray.value` re-runs whenever any item shape changes (because `largeArray` itself is reactive). For derivations that only depend on a slice, isolate the slice via a smaller `computed` first or use `shallowRef` on the source
- [ ] **`computed` used as a method**: `const x = computed(() => fn())` invoked as `x.value` repeatedly inside a template / handler - a method call would be cheaper if the result is not cached across renders. Conversely: a method called inside the template that doesn't depend on render state should be a `computed` so its result memoizes
- [ ] **`watchEffect` with hidden side effects**: `watchEffect(() => { fetch(state.url) })` re-fires whenever any reactive read inside changes - including reads you didn't intend to track. Prefer explicit `watch(() => state.url, fn)` for known sources; reach for `watchEffect` only when the dep set is genuinely "everything I touch in this block"
- [ ] **`watch` deep / immediate misuse**: `watch(state, fn, { deep: true })` on a 500-key object scans on every change - costly and rarely what you want. Prefer specifying `() => state.specificField`. `immediate: true` is correct for "run once now and on every future change" but smell when used to compensate for a missing initial fetch
- [ ] **`watch` flush timing**: default `flush: 'pre'` runs before the DOM updates; `'post'` after; `'sync'` immediately. Default is right for most cases. Flag explicit `'sync'` (blocks the reactivity batch) outside DevTools / debugging
- [ ] **Watcher cascade**: `watch(a, () => state.b = ...)` then `watch(b, () => state.c = ...)` - chained watchers re-batch through tick boundaries and produce intermediate renders. Collapse into a single `computed` or a single watcher that updates multiple targets
- [ ] **`v-for` without `:key` / `:key="index"`**: missing key breaks reconciliation; key by stable ID. `:key="index"` on a reorderable / filterable list breaks DOM reuse and component state. Flag both
- [ ] **`v-for` with `v-if` on the same element**: `<li v-for v-if>` - in Vue 3 `v-if` has higher precedence and the iteration variable is not in scope inside `v-if`. Filter the source array via a `computed` first (`<li v-for="item in visibleItems">`) - cleaner and faster
- [ ] **Inline functions in template event handlers**: `<button @click="() => doSomething(item)">` allocates a new function per render per row - over a list of 1000 items that compounds. Lift to a method / `useFn` factory when measurable
- [ ] **Inline objects / arrays in template props**: `<Child :config="{ ... }" :items="[...]">` rebuilt every parent render → cascades into deep watchers / computeds in the child. Lift to `computed` or a stable `ref`
- [ ] **`defineProps` with deep object types accepted as plain object**: child receives a deep object and uses each field independently - prefer flat props or `toRefs(props)` to avoid subscribing to the entire object on every change
- [ ] **List virtualization absent for long lists**: rendering 1000+ items (or 100+ rows of complex content - charts, sub-tables, rich slots) without `vue-virtual-scroller` / `@tanstack/vue-virtual` causes long initial render and laggy scroll. Threshold scales with row complexity: simple row × 1000+ or complex row × 100+. Flag steady-state lists
- [ ] **`v-memo` opportunity missed**: `<div v-memo="[item.id, item.updatedAt]">` skips re-render when the dep array is unchanged - useful for read-heavy lists where parent re-renders but row content rarely changes. Flag when a hot list re-renders entirely on parent state updates
- [ ] **`v-once` for static content**: marketing copy / config legends rendered inside dynamic parents but never changing - `v-once` caches the render
- [ ] **Heavy synchronous work in render / setup body**: parsing, sorting, filtering large arrays, JSON serialization in `setup()` body or template expression. Move to a `computed` (with real dep set) or precompute outside the component
- [ ] **`provide` / `inject` re-renders every consumer**: providing a non-stable reactive object propagates change to every injection consumer; if only one field changes, every consumer re-runs. Prefer providing fine-grained refs or splitting into multiple provides

### Step 5 - Bundle Size and Code Splitting

Use skill: `vue-component-patterns` for split boundaries; use skill: `vue-nuxt-patterns` for Nuxt-specific lazy components.

- [ ] **New dependencies measured**: any new entry in `dependencies` (not `devDependencies`) gets a size note. Flag anything > 50KB minified+gzipped that is not lazy-loaded
- [ ] **Heavy libraries pulled into the client bundle eagerly**: charting (`chart.js`, `apexcharts`, `echarts`), rich text (`tiptap`, `quill`), date pickers (with moment), `moment` (use `date-fns` / `dayjs` / native `Intl`), `lodash` (use `lodash-es` and tree-shake; better, native or `radash`)
- [ ] **Nuxt `<LazyXxx />` auto-import for heavy components**: prefixing a component name with `Lazy` (e.g., `<LazyEditor />`) auto-creates a dynamic import boundary. Flag eager `<Editor />` for components used on a single route, gated by user interaction, or only rendered conditionally
- [ ] **`defineAsyncComponent` for non-Nuxt projects (Vite)**: `const Editor = defineAsyncComponent(() => import('./Editor.vue'))` wrapped in `<Suspense>`; route-level lazy via Vue Router `component: () => import('./EditorPage.vue')`
- [ ] **Barrel-file imports defeating tree-shake**: `import { X } from '@/components'` where `index.ts` re-exports 50 things drags the whole barrel in if not configured for tree-shaking. Prefer direct path imports (`@/components/X.vue`) on the hot path. Nuxt auto-imports avoid this when used as components in templates - but flag explicit barrel imports of components in `<script setup>`
- [ ] **`unplugin-vue-components` / `unplugin-auto-import` config**: when used, ensure `dts` is enabled (TS support) and the resolvers don't pull global UI libraries (`Vuetify`, `PrimeVue`) into every component. Component-level auto-import is fine; library-level can balloon the bundle
- [ ] **CSS-in-JS / runtime CSS cost**: rare in Vue (scoped CSS, CSS Modules, Tailwind, UnoCSS are zero-runtime), but flag any `vue-styled-components` / `emotion` adoption as Medium - Vue's scoped styles already solve the problem zero-runtime
- [ ] **Tree-shake friendly imports**: `import isEqual from 'lodash/isEqual'` (or `lodash-es`); never `import _ from 'lodash'`. `import { format } from 'date-fns'` not `import * as df from 'date-fns'`. Named imports also matter for large libs like `chart.js`, `@vueuse/core` (auto-imports only the composables you use, but explicit `import * as VueUse from '@vueuse/core'` defeats it)
- [ ] **Charting / rich-editor / map libraries dynamically imported**: rarely belong in the initial bundle - they belong below the fold or behind interaction. Wrap with `<LazyChart />` (Nuxt) or `defineAsyncComponent` (Vite) + `<Suspense>`. Flag eager imports as a Medium even when the page genuinely uses the chart - the LCP impact is the same
- [ ] **Vuetify / PrimeVue / Element Plus full-import**: importing the entire UI library (`import Vuetify from 'vuetify'`) instead of per-component (`import { VBtn, VCard } from 'vuetify/components'`) ships the whole library. Flag full-import as High

> **Impact heuristic - bundle blast radius.** A 50KB gzip dependency on the home route adds ~50KB transferred on every cold visit (every visitor, every device). On 3G that is ~1.3s longer download; on cable ~50ms; the worst case dominates LCP for budget-constrained users. Phrase the impact as "+<N>KB on every cold visitor of every route that imports this," not "the bundle got bigger."

### Step 6 - Data Fetching and Caching

Use skill: `vue-data-fetching` for canonical patterns.

**Nuxt 3 (`useFetch` / `useAsyncData` / `$fetch`):**

- [ ] **`useFetch` over manual `$fetch` for SSR data**: `useFetch(url)` integrates with the SSR payload (server fetch reused on client hydration); raw `$fetch` in `<script setup>` runs twice (once on server, once on client) unless explicitly guarded. Flag `$fetch` for initial-render data
- [ ] **Stable `key` for cacheable data**: `useFetch(url, { key: 'orders-' + status })` enables payload reuse across navigations; missing keys make Nuxt synthesize one from the call site (works but not portable). Flag dynamic keys built via `JSON.stringify` (cache miss every time)
- [ ] **`getCachedData` for client-side cache reuse**: `useAsyncData(key, fn, { getCachedData: (key) => nuxtApp.payload.data[key] ?? nuxtApp.static.data[key] })` returns cached payload instead of re-fetching on client navigation; flag callsites that always re-fetch when data is rarely changing
- [ ] **`transform` to project response down**: `useFetch(url, { transform: (data) => ({ id: data.id, name: data.name }) })` keeps the SSR payload small - the entire fetched object lands in the HTML otherwise. Flag full ORM rows surfaced in `useFetch` payload
- [ ] **`pick` for response field selection**: `useFetch(url, { pick: ['id', 'name'] })` - lighter than `transform` for shallow projection
- [ ] **`server: false` for client-only fetch**: `useFetch(url, { server: false })` skips SSR and runs only on client (e.g., user-specific data not eligible for SSR cache); flag missing when the call returns user-specific data being SSR'd into shared HTML
- [ ] **`lazy: true` for non-blocking fetch**: a `useFetch` in `<script setup>` blocks SSR until it resolves - good for above-the-fold data, bad for below-fold. Flag a slow non-critical fetch blocking SSR; recommend `lazy: true` + `<Suspense>` boundary
- [ ] **`watch` option for refetch on dep change**: `useFetch(url, { watch: [filter] })` refetches when `filter` changes; flag manual `watch(() => filter.value, () => refresh())` patterns - the option is cleaner
- [ ] **`refresh()` / `refreshNuxtData` after mutations**: after a Nitro server-side mutation, refresh affected `useAsyncData` keys. `refreshNuxtData('orders')` re-runs the fetch; `clearNuxtData('orders')` evicts. Flag mutations without invalidation
- [ ] **N+1 fan-out over a list**: `await Promise.all(items.map(i => $fetch(`/api/detail/${i.id}`)))` parallelizes N requests but is still N round-trips. Flag and recommend a batched server endpoint (`/api/details?ids=...`) or a Nitro-level batched query. Pure parallelism does not save the database
- [ ] **Sequential awaits for independent fetches in `<script setup>`**: `const a = await useFetch(...); const b = await useFetch(...);` blocks SSR end-to-end. Use `Promise.all([useFetch(...), useFetch(...)])` or two parallel `useAsyncData` calls
- [ ] **`<Suspense>` for async setup**: components with async `<script setup>` or `await useFetch` inside need a `<Suspense>` boundary in the parent for graceful fallback; flag missing
- [ ] **LCP element not behind `<Suspense fallback>`**: hero image / above-the-fold content must not be deferred behind a Suspense fallback - that defers the LCP element itself. Suspense belongs around below-the-fold content

**Both frameworks (TanStack Query Vue / VueQuery, when used):**

- [ ] **`staleTime` / `gcTime` set**: default `staleTime: 0` refetches on every mount - flag for endpoints whose data does not change per-mount. `staleTime: 60_000` for typical reads
- [ ] **Query keys are stable, structured arrays**: `['orders', { ownerId, status }]` not `'orders-' + JSON.stringify(filters)` - structured keys enable scoped invalidation
- [ ] **Cache invalidation explicit after mutations**: `useMutation({ onSuccess: () => queryClient.invalidateQueries({ queryKey: ['orders'] }) })`
- [ ] **No fetching in render body / template expression**: a `$fetch()` call in the template re-fires on every render

### Step 7 - Core Web Vitals and Page Load

_Skipped at `quick` depth unless the diff touches a route, layout, or assets._

**LCP (Largest Contentful Paint):**

- [ ] **`<NuxtImg>` / `<NuxtPicture>` for images (Nuxt)**: `@nuxt/image` provides automatic responsive sizing, modern format conversion (AVIF/WebP), provider integration (Cloudinary / IPX). Flag raw `<img>` for hero / above-the-fold images. Use `:preload="true"` on the LCP image to mark it for high-priority preload
- [ ] **Vite equivalent**: `vite-imagetools` or manual `<img loading="lazy" srcset="..." sizes="...">` with explicit `width` / `height`. Hero image should not be lazy
- [ ] **`width` / `height` attributes** on every image (prevents CLS even when async-decoded); `<NuxtImg>` enforces this
- [ ] **Hero image not deferred**: above-the-fold image must not be inside a lazy component, gated by `<Suspense>` for slow data, or set to `loading="lazy"`
- [ ] **`@nuxt/fonts` for self-hosted fonts (Nuxt)**: auto-detects fonts in CSS and self-hosts with `font-display: swap`; flag `<link href="https://fonts.googleapis.com/...">` (extra DNS lookup + render-blocking CSS)
- [ ] **`font-display: swap`**: webfonts use swap; flag `font-display: block` for above-the-fold text

**INP (Interaction to Next Paint):**

- [ ] **No long synchronous tasks on user input**: form submit handler doing 50ms of synchronous work blocks paint. Defer via `nextTick` (defer to next tick) or break into `requestIdleCallback` chunks
- [ ] **Heavy filtering / search uses `computed` with debounce**: typing into a search box that filters a 10K-row list synchronously on every keystroke janks; debounce input via `useDebounceFn` (`@vueuse/core`) and apply via a separate ref
- [ ] **No long-running effects on click**: heavy computation in a click handler should be moved to a worker (`comlink` / native `Worker`), a network request, or `requestIdleCallback`

**CLS (Cumulative Layout Shift):**

- [ ] **Reserved space for async content**: skeletons / placeholders with the same dimensions as the final content (`h-64 w-full` for an image slot, fixed-height containers for ads / embeds)
- [ ] **No layout thrash from late-loading fonts**: `@nuxt/fonts` solves; for raw fonts use `font-display: swap` + `size-adjust` / `ascent-override` font metrics overrides
- [ ] **Late-injecting elements at the top of the page**: A/B test snippets, banners, cookie modals that push content down trigger CLS - reserve space or load below the fold

### Step 8 - Hydration and Streaming (Nuxt)

_Skipped on Vite + Vue Router projects (no SSR / hydration unless explicit Vite SSR template)._

- [ ] **No hydration mismatch sources**: `Date.now()` / `Math.random()` / `new Date().toString()` rendered server-side without `<ClientOnly>` wrap or stable seed; access to `window` / `document` / `localStorage` / `navigator` in `<script setup>` body without `import.meta.client` / `process.client` guard
- [ ] **`<ClientOnly>` for inherently client-only components**: components depending on `window`, `IntersectionObserver`, third-party widgets that don't SSR. Wrap with `<ClientOnly>` and provide a `<template #fallback>` to reserve space (else CLS)
- [ ] **`onMounted` for browser-only APIs**: `window.matchMedia`, `localStorage`, `IntersectionObserver` accessed inside `onMounted` (which only runs on the client); never in `<script setup>` top-level
- [ ] **`useState` for shared SSR state**: cross-component state preserved across SSR → client hydration uses Nuxt's `useState(key, init)`; flag `ref()` at module scope (cross-request leak in SSR) or in a composable that loses its value on hydration
- [ ] **Component Islands (experimental)**: `<NuxtIsland name="Foo" />` for selectively-hydrated regions; mention only when the diff explicitly enables `experimental.componentIslands`
- [ ] **Nuxt `payloadExtraction`**: enabled by default - keeps the SSR payload separate from HTML for prerender. Flag `experimental.payloadExtraction: false` without rationale
- [ ] **`<Suspense>` for async setup**: long-running async setup in a child component blocks hydration of the entire subtree; isolate slow components in their own `<Suspense fallback>`

### Step 9 - Caching, ISR, and Edge (Nuxt `routeRules`)

_Skipped at `quick` depth and on Vite projects._

- [ ] **`routeRules` for per-route caching strategy (Nuxt 3)**: `nuxt.config.ts` `routeRules: { '/blog/**': { swr: 3600 }, '/admin/**': { ssr: false }, '/marketing/**': { prerender: true } }`. Flag a route that should be prerendered but is rendered SSR per-request, or a per-user route accidentally cached via `swr`
- [ ] **`prerender` for static content**: marketing pages, blog index, docs - prerender at build time
- [ ] **`swr` (Stale-While-Revalidate)** for content that changes occasionally: serves cached HTML, revalidates in background. `swr: 3600` = serve cached for 1h
- [ ] **`isr` (Incremental Static Regeneration)** on platforms that support it (Vercel / Netlify) - prerender on first request, cache for N seconds
- [ ] **`ssr: false` per-route** for client-only dashboards (e.g., admin) where SSR provides no value and the auth context only exists client-side
- [ ] **`headers` route rule** for cache-control / CDN hints: `headers: { 'cache-control': 's-maxage=300, stale-while-revalidate=3600' }`
- [ ] **Nitro storage cache (`useStorage`)**: server-side cache for expensive Nitro endpoint results; `defineCachedEventHandler` / `cachedFunction` for TTL'd memoization. Flag uncached repeat queries hit on every SSR
- [ ] **Edge runtime where appropriate**: Nuxt 3 supports edge providers (Vercel Edge, Cloudflare Workers); `routeRules` `experimental: { wasm: true }` and provider-specific config. Use for low-TTFB globally; Node runtime for everything else

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-vue-review-observability`. From a perf perspective, confirm only:

- [ ] Critical user journeys reachable from this PR have **some** instrumentation (`web-vitals` reporter wired, RUM SDK active, Sentry Vue SDK with performance enabled, or Nitro server-side tracing); if not, raise as a Low/Recommendation finding and delegate to `task-vue-review-observability` rather than dictating the design here
- [ ] No `console.log` left in render path / `<script setup>` body of a hot route - if visible in the diff. If not in the diff, skip

Anything beyond presence/absence (sample rates, attribution, route segmentation) → `task-vue-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Vue; framework (Nuxt 3 / Vite + Vue Router) and Vue version recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface read directly (changed components, layouts, route handlers, config, data-fetching composables, Pinia stores)
- [ ] `vue-composables-patterns` and `vue-component-patterns` consulted for reactivity hotspots
- [ ] Reactivity audit (deep `reactive` cost, watcher cascades, `computed` over-tracking, destructure de-reactivity) applied
- [ ] Bundle deltas assessed for any new `dependencies` entry; tree-shake-friendly imports verified; UI library full-imports flagged
- [ ] `vue-data-fetching` consulted for `useFetch` / `useAsyncData` cache options, transform / pick / key, mutation invalidation
- [ ] N+1 fan-out (`Promise.all(items.map(...))`) flagged when present; batched-query alternative recommended
- [ ] Inline objects / arrays in template props and inline event-handler functions flagged as identity-instability hazards
- [ ] Tree-shake hostile imports (`import * as X from 'chart.js' / 'date-fns' / 'lodash'`) flagged
- [ ] Heavy chart / editor / map libraries gated by `<LazyXxx />` / `defineAsyncComponent`; eager imports flagged
- [ ] Core Web Vitals (LCP image / fonts / CLS reservations / INP debounce) checked when route or asset code changed
- [ ] LCP element verified not deferred behind `<Suspense fallback>` / `<ClientOnly>` without rationale
- [ ] Hydration / streaming checks applied for Nuxt; Vite section skipped on Vite-only projects
- [ ] `routeRules` (`prerender` / `swr` / `isr` / `ssr: false` / `headers`) decisions reviewed for changed routes (Nuxt)
- [ ] Every finding states impact - measured (`LCP: 2.8s -> 1.4s`) when RUM data exists, estimated otherwise (`+45KB gzip on every cold visit to /dashboard`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and budget plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Vue Performance Review Summary

**Stack Detected:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Scope:** Frontend (Vue)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the Vue idiom: deep `reactive` over a 5K-row dataset, watcher cascade rebuilding state through three ticks, eager `<Editor />` for a route-only component, missing `<NuxtImg>` on hero, `useFetch` without `key` causing cache miss, etc.]
- **Impact:** [estimated effect - e.g., "+120KB gzip on every cold visit to /dashboard" or measured "LCP 2.8s -> 1.4s after fix"]
- **Fix:** [specific Vue change with code example - `shallowRef` for the dataset, `<LazyEditor>`, `useFetch(url, { key, transform })`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Adopt `<LazyXxx />` for editor pages", "Convert long lists to `vue-virtual-scroller`", "Add bundle budget to CI"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, build config change, or perf-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Replace `reactive(orders)` with `shallowRef(orders)` in stores/orders.ts:42; mutate via `.value = next`"]
2. **[Delegate]** [High] [scope: build] - [one-line action, e.g., "Add bundle budget for /dashboard route - spawn build-config subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the Vue idiom ("this is slow" vs "deep `reactive` over a 5K-row dataset; switch to `shallowRef` so only top-level mutation is tracked")
- Recommending generic frontend advice when a Vue pattern applies (say "use `<LazyXxx />` auto-import", not "lazy load")
- Suggesting `computed` everywhere as a default - the cost is cheap but cache invalidation still costs; only use when the value is reused or genuinely derived
- Approving raw `<img>` for hero / above-the-fold images on Nuxt - `<NuxtImg :preload="true">` is the right tool
- Approving `ssr: false` on a route without a per-route reason - it disables every server-rendering benefit
- Approving `useFetch` without a `key` for keyable data - cache reuse across navigation is lost
- Approving full-import of Vuetify / PrimeVue / Element Plus when per-component import works - bundle balloons
- Conflating perf review with general code review or security review - delegate those to their workflows
- Treating high re-render counts as inherently bad - Vue's reactivity is fast; only investigate when a profile or interaction lag implicates re-renders
- Recommending `useEffect`-style patterns (`watchEffect(() => fetch(...))`) when `useFetch` (Nuxt) would do
