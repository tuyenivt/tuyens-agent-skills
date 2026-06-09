---
name: task-vue-review-perf
description: "Vue / Nuxt perf review: Core Web Vitals, bundle, hydration, reactivity hotspots, Pinia, useFetch cache, routeRules, images."
agent: vue-performance-engineer
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, performance, core-web-vitals, bundle, ssr, workflow]
  type: workflow
user-invocable: true
---

# Vue Performance Review

Stack-specific delegate of `task-code-review-perf` for Vue 3 / Nuxt 3 / Vite. Preserves the parent contract (invocation, diff resolution, output shape).

## When to Use

- Reviewing a Nuxt or Vite + Vue PR / branch for perf regressions
- Investigating a slow page or interaction (high INP, slow LCP, jank, hydration cost)
- Pre-merge pass on changes touching bundle, data fetching, or rendering boundaries
- Quarterly Core Web Vitals / bundle sweep against RUM-flagged routes

**Not for:**

- General review (`task-vue-review`)
- Security review (`task-vue-review-security`)
- Production incident (`/task-oncall-start`)
- Pre-implementation design (`task-vue-implement`)

## Severity Rubric

Steady-state user impact, not "how scary the code looks".

| Severity   | Definition                                                                                                                                                                                                                                                                            |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | LCP / INP regression visible to every cold visitor: heavy lib in initial bundle (>50KB gzip, no split), full UI library import (Vuetify / PrimeVue / Element Plus), hero `<img>` blocking LCP, missing virtualization on 1k+ rows, sync work on input (>200ms INP), hydration mismatch, `useFetch` without key on hot navigation, `ssr: false` on a cacheable route. |
| **Medium** | Degraded p95 / wasted re-renders: deep `reactive` over a large dataset, watcher cascade, identity-unstable inline objects/handlers in hot lists, barrel imports defeating tree-shake, `staleTime: 0` on hot query, missing `<NuxtImg>`, `$fetch` in `<script setup>` for initial-render data. |
| **Low**    | Allocation / churn quick wins: missing `v-memo` on read-heavy lists, `computed` on primitives, `console.log` in render, missing `@nuxt/fonts`, missing `loading="lazy"` below-the-fold.                                                                                                |

Tiebreaker: "would RUM flag this on a typical mobile cold visit?" yes -> High; "drag next quarter's perf budget?" yes -> Medium.

## Depth Levels

| Depth      | When                                                          | Runs                                        |
| ---------- | ------------------------------------------------------------- | ------------------------------------------- |
| `standard` | Default - full Vue perf review                                | Steps 1-9                                   |
| `deep`     | RUM-driven (Core Web Vitals data / profiling / route budgets) | All steps + capacity guidance + budget plan |

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                       | Meaning                                                              |
| -------------------------------- | -------------------------------------------------------------------- |
| `/task-vue-review-perf`          | Review current branch vs its base; fails fast on trunk               |
| `/task-vue-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                           |
| `/task-vue-review-perf pr-<N>`   | Review PR head in local branch `pr-<N>` (user runs the fetch first)  |

When invoked as a subagent of `task-code-review-perf` or `task-vue-review`, the parent passes the precondition handle plus already-read diff/log; skip Steps 1-3 re-detection.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. If parent already detected Vue, accept the handoff. If not Vue, stop and route to `/task-code-review-perf`. Assumes Vue 3.5+ (`useId`, `useTemplateRef`, reactive props destructure) or 3.4+ (`defineModel`); TypeScript strict.

Record for the Summary block:

- `Framework:` Nuxt 3 | Vite + Vue Router
- `Data Layer:` `useFetch` / `useAsyncData` | TanStack Query Vue | mixed
- `Styling:` Tailwind / UnoCSS | scoped CSS / CSS Modules | CSS-in-JS (`vue-styled-components` / `emotion`)

Heuristics: `nuxt.config.*` or `nuxt` in deps -> Nuxt 3; `vite.config.*` + `vue` without `nuxt` -> Vite + Vue Router; both present -> ask the user.

### Step 3 - Resolve Diff and Read Surface

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once; reuse. Skip entirely if parent passed the handle.

Open the files that govern rendering, bundle, and data fetching so impact estimates ground in real code:

- **Nuxt 3:** changed `pages/`, `layouts/`, `components/`, `app.vue`, `composables/`, `server/api/`, `stores/`; `nuxt.config.*` (`routeRules`, `image`, `experimental`, `nitro`, `vite`); Suspense / `<LazyXxx />` boundaries
- **Vite + Vue Router:** changed `src/**/*.vue` and composables (all client), `vite.config.*` chunks, `src/router/*.ts` lazy routes / Suspense, Pinia stores
- Both: TanStack Query call sites, list components (rows + virtualization), image / font usage, `package.json` for new deps

If a small diff ripples through unchanged code (new caller of a heavy library, shared component pulling a barrel), read the unchanged file too. Cite real `file:line` in every finding.

### Step 4 - Reactivity and Re-Render Hotspots

Use skill: `vue-composables-patterns`. Use skill: `vue-component-patterns`. Workflow-specific verifications:

- Deep `reactive` over large read-only data (API rows, lookup tables) -> `shallowRef` / `shallowReactive`
- Reactivity loss via destructure / spread (`const { a } = reactive(...)`, `{ ...state }`) -> `toRefs` or Vue 3.5+ props destructure
- Watcher discipline: no wide `{ deep: true }`, no `flush: 'sync'` outside debugging, no `a -> b -> c` cascades; collapse to one `computed` or multi-target watcher
- `v-for` `:key` is a stable id, not `index`, for reorderable / filterable lists
- `v-for` + `v-if` on the same element -> filter via `computed` first (`v-if` has higher precedence in Vue 3)
- Identity-unstable inline `{...}` / `[...]` props and inline `() => ...` handlers in hot lists -> lift to `computed` or stable `ref`
- Heavy sync work in `setup()` / template expression -> `computed` with real deps, or precompute
- Virtualize when simple rows > 1000 or complex rows > 100 (`vue-virtual-scroller`, `@tanstack/vue-virtual`)
- `v-memo` / `v-once` on read-heavy lists where row content rarely changes
- `provide` / `inject` re-render storm from a non-stable reactive object -> fine-grained refs or split provides (`vue-state-patterns`)

```vue
<!-- BAD: inline object recreated each render, deep reactive over 5K rows -->
<script setup lang="ts">
const orders = reactive(await $fetch('/api/orders')) // 5K rows, all proxied
</script>
<template>
  <OrderRow v-for="o in orders" :key="o.id" :item="o" :config="{ dense: true }" />
</template>

<!-- GOOD: shallowRef, stable config, $fetch swapped to useFetch -->
<script setup lang="ts">
const { data: orders } = await useFetch('/api/orders', { key: 'orders' })
const rows = shallowRef(orders.value ?? [])
const ROW_CONFIG = { dense: true }
</script>
<template>
  <OrderRow v-for="o in rows" :key="o.id" :item="o" :config="ROW_CONFIG" />
</template>
```

### Step 5 - Bundle Size and Code Splitting

Use skill: `vue-component-patterns`. Use skill: `vue-nuxt-patterns` (Nuxt).

- Every new `dependencies` entry sized; flag >50KB gzip not lazy-loaded
- Charting (`chart.js`, `apexcharts`, `echarts`), rich text (`tiptap`, `quill`), maps, date pickers behind `<LazyXxx />` (Nuxt auto-import) or `defineAsyncComponent(() => import(...))` + `<Suspense>` (Vite) - even when the page uses the chart, the LCP impact is the same
- Tree-shake-friendly imports: `import { format } from 'date-fns'`, `import isEqual from 'lodash/isEqual'`, never `import * as X from 'apexcharts' / 'lodash'`
- Full UI library imports (`import Vuetify from 'vuetify'`) -> per-component (`import { VBtn } from 'vuetify/components'`) - flag as High
- Barrel `index.ts` imports on the hot path -> direct paths; Nuxt component auto-imports are fine, explicit barrel imports in `<script setup>` are not
- `moment` -> `date-fns` / `dayjs` / `Intl`; CSS-in-JS flagged when added to a scoped-CSS / Tailwind project
- `unplugin-vue-components` resolvers don't pull a global UI library into every component

Impact phrasing: "+<N>KB gzip on every cold visit to <route>", not "the bundle got bigger".

### Step 6 - Data Fetching and Caching

Use skill: `vue-data-fetching`. Workflow-specific verifications:

**Nuxt 3 (`useFetch` / `useAsyncData` / `$fetch`):**

- `$fetch` in `<script setup>` for initial-render data runs twice (server + client) -> `useFetch` so SSR payload hydrates
- Stable `key` for parameterized fetches (no JSON-stringified keys); `transform` / `pick` to project payload down; `getCachedData` for cross-navigation reuse
- `server: false` for user-specific data not eligible for shared SSR cache; `lazy: true` + `<Suspense>` for below-fold fetches that would block SSR
- Mutations call `refreshNuxtData(key)` / `clearNuxtData(key)`; missing invalidation -> stale UI
- N+1 / waterfall: `Promise.all(items.map(i => $fetch(...)))` -> batched endpoint; sequential `await useFetch` for independent fetches -> parallelize
- LCP element not gated by `<Suspense fallback>` waiting on slow data

**TanStack Query Vue:**

- `staleTime` / `gcTime` set; query keys are stable structured arrays, not JSON strings
- Mutation invalidation explicit (`onSuccess: () => queryClient.invalidateQueries(...)`)
- No `$fetch()` directly in a template expression (fires every render)

### Step 7 - Core Web Vitals

**LCP:**

- Nuxt: `<NuxtImg :preload="true">` / `<NuxtPicture>` for hero / above-the-fold; flag raw `<img>`. Vite: `vite-imagetools` or explicit `srcset`/`sizes`/`width`/`height`
- `width` / `height` on every image (CLS); `<NuxtImg>` enforces
- Hero not gated by `<Suspense>`, lazy mount, `<ClientOnly>`, or `loading="lazy"`
- Nuxt: `@nuxt/fonts` self-hosts webfonts; flag `<link href="fonts.googleapis.com">`. `font-display: swap` everywhere

**INP:**

- Debounce wide filter / search input via `useDebounceFn` (`@vueuse/core`); apply via a separate ref
- Heavy click handlers offloaded to a worker, network request, or `requestIdleCallback`
- Long synchronous work in submit handlers broken up via `nextTick` or chunking

**CLS:**

- Reserved dimensions on async slots (skeleton with same `h-`/`w-`)
- Late-injecting A/B / banner / modal scripts reserve space or load below the fold

### Step 8 - Hydration, Streaming, `routeRules` (Nuxt)

_Skipped on Vite-only projects._

- No hydration mismatch sources: `Date.now()`, `Math.random()`, `window` / `document` / `localStorage` / `navigator` access in `<script setup>` body -> `onMounted`, `<ClientOnly>` (with `<template #fallback>` to reserve space), or `import.meta.client` guard
- Cross-component SSR state via `useState(key, init)`; flag module-scope `ref()` (cross-request leak) or composable-local state that loses value on hydration
- Slow child `async setup` isolated in its own `<Suspense fallback>` so the parent shell hydrates first
- `routeRules` per-route caching deliberate: `prerender` for marketing / docs, `swr: N` for occasionally-changing content, `isr` on Vercel / Netlify, `ssr: false` only for client-only dashboards, `headers` for CDN cache-control
- `defineCachedEventHandler` / `cachedFunction` / `useStorage` for repeat-hit Nitro endpoints; uncached repeats on every SSR flagged
- `experimental.payloadExtraction: false` flagged without rationale
- Edge runtime (`nitro.preset: 'vercel-edge' / 'cloudflare'`) for low-TTFB handlers without Node APIs

### Step 9 - Observability Hand-off and Report

Confirm presence only (depth belongs to `task-vue-review-observability`):

- `web-vitals` reporter wired, RUM SDK active, or Sentry Vue SDK with performance enabled on changed routes
- Nitro server-side tracing when server work is non-trivial
- No `console.log` left in render path of a hot route (if visible in diff)

Gaps -> Low / Recommendation with `[Delegate] -> task-vue-review-observability`.

Then use skill: `review-report-writer` with `report_type: review-perf`. Write the report to file; print the confirmation line.

## Output Format

```markdown
## Vue Performance Review Summary

**Stack Detected:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Data Layer:** `useFetch` / `useAsyncData` | TanStack Query Vue | mixed
**Styling:** Tailwind / UnoCSS | scoped CSS / CSS Modules | CSS-in-JS
**Scope:** Frontend (Vue)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [name the Vue idiom: deep `reactive` over a 5K-row dataset, watcher cascade, eager `<Editor />` for a route-only component, missing `<NuxtImg>` on hero, `useFetch` without `key`, full `vuetify` import, hydration mismatch from `Date.now()`, etc.]
- **Impact:** [measured (`LCP 2.8s -> 1.4s`) or estimated (`+120KB gzip on every cold visit to /dashboard`, `~40 re-renders per scroll frame`)]
- **Fix:** [specific Vue change with code - `shallowRef`, `<LazyEditor>`, `useFetch(url, { key, transform })`, `<NuxtImg :preload="true">`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty sections._

## Recommendations

[Structural items not tied to a single finding - route-level `<LazyXxx />` for editor pages, convert long lists to `vue-virtual-scroller`, add bundle budget to CI, adopt `routeRules` `swr` on marketing pages.]

## Next Steps

Each item `[Implement]` (localized) or `[Delegate]` (cross-cutting / build config / load test). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: build] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Steps 1-3: behavioral principles loaded; Vue stack + Framework/Data Layer/Styling recorded; diff/log read once; perf surface opened
- [ ] Step 4: reactivity hotspots audited (deep `reactive`, watcher cascades, de-reactivity, `v-for` keys, virtualization, `v-memo`)
- [ ] Step 5: bundle deltas sized; tree-shake-hostile and full UI-library imports flagged; heavy libs gated by `<LazyXxx />` / `defineAsyncComponent`
- [ ] Step 6: `useFetch` key/transform/`getCachedData`/mutation invalidation audited; `$fetch` in `<script setup>` for initial data flagged
- [ ] Step 7: LCP image/fonts, INP debounce, CLS reservations checked
- [ ] Step 8: hydration sources, `<Suspense>` streaming, `useState`, `routeRules`, Nitro caching reviewed (Nuxt only)
- [ ] Step 9: observability presence checked or `[Delegate]` added; report written; confirmation printed
- [ ] Every finding cites `file:line` and states measured or estimated impact
- [ ] Depth honored: `standard` runs 1-9; `deep` adds capacity + budget plan
- [ ] Next Steps tagged `[Implement]`/`[Delegate]`, ordered Must > Recommend > Question

## Avoid

- State-changing git - user runs `fetch`/`checkout`.
- "This is slow" without naming the Vue idiom (deep `reactive`, watcher cascade, missing virtualization, `useFetch` without `key`).
- Generic frontend advice when a Vue pattern applies.
- `computed` / `watch` as defaults - only when reused or genuinely derived.
- Treating high re-render counts as inherently bad without profile evidence.
- Conflating perf with general/security review - delegate.
- **Dual perf+security findings** (`v-html`, `eval`, prototype-pollution spread): report perf half once with `[Delegate] -> task-vue-review-security` in Next Steps.
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
