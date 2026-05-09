---
name: task-react-review-perf
description: React / Next.js performance review: Core Web Vitals, bundle, hydration, re-render storms, TanStack Query, Suspense, RSC boundaries, ISR/revalidate.
agent: react-performance-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, performance, core-web-vitals, bundle, rsc, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# React Performance Review

## Purpose

React-aware performance review that names Core Web Vitals (LCP, INP, CLS), bundle splitting via `next/dynamic` / `React.lazy`, Server vs Client Component boundaries, RSC streaming via Suspense, TanStack Query cache keys / `staleTime` / `gcTime`, `useMemo` / `useCallback` discipline, hydration cost, `next/image` and `next/font` directly instead of routing through the generic frontend adapter. Produces findings with measured or estimated impact (LCP delta, bundle delta, render count, hydration time) and concrete fixes using TypeScript-strict React idioms.

This workflow is the stack-specific delegate of `task-code-review-perf` for React. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Next.js or Vite + React PR or branch for performance regressions
- Investigating a slow page, route, or component (high INP, slow LCP, jank during interaction)
- Pre-merge perf pass on changes touching the bundle (new dependency, new route, new client component), data fetching, or rendering boundaries
- Quarterly Core Web Vitals / bundle-size sweep against RUM-flagged routes

**Not for:**

- General React code review (use `task-code-review` or `task-react-review`)
- Security review (use `task-code-review-security` or `task-react-review-security`)
- Production incident response (use `/task-oncall-start`)
- Pre-implementation feature design (use `task-react-implement`)

## Depth Levels

| Depth      | When to Use                                                        | What Runs                                                                |
| ---------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `quick`    | Single component or route ("is this re-rendering ok?")             | Steps 4 + 5 only; render hotspots + bundle deltas                        |
| `standard` | Default - full React perf review                                   | All steps                                                                |
| `deep`     | RUM-driven review with Core Web Vitals data, profiling, or budgets | All steps + capacity guidance, route budget plan, perf-test instructions |

Default: `standard`.

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                         | Meaning                                                                                               |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-react-review-perf`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-react-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-react-review-perf pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-perf` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm React. If invoked as a delegate of `task-code-review-perf` or as a subagent of `task-react-review` (parent already detected React), accept the pre-confirmed stack and skip re-detection. If the detected stack is not React, stop and tell the user to invoke `/task-code-review-perf` instead - this workflow assumes React 19+ and TypeScript strict mode.

Then detect the framework:

- `next.config.{js,ts,mjs}` present / `next` in `package.json` deps → **Next.js App Router** (assume App Router unless `pages/` directory present without `app/` - then Pages Router)
- `vite.config.{js,ts}` present / `vite` in deps without `next` → **Vite + React Router**
- Both present → ask the user which surface this PR targets; do not guess

The framework decision drives which checklists in Steps 4-7 apply. Record `Framework: Next.js (App Router) | Next.js (Pages Router) | Vite + React Router` for the Summary block. Also record `React: <version>` (RSC requires 18+; React 19 unlocks `useOptimistic`, `useFormStatus`, the `use()` hook for Suspense data, and Server Action improvements).

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-perf` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Performance Surface

Before applying the checklists, open the files that govern rendering, hydration, bundle, and data fetching so impact estimates ground in real code:

**Next.js App Router surface:**

- Every changed `app/**/page.tsx`, `app/**/layout.tsx`, `app/**/loading.tsx`, `app/**/error.tsx`, `app/**/route.ts` - note Server vs Client (`"use client"`) directive at the top
- Every changed component file - check for `"use client"`; trace the Client Component subtree (every import down from a Client Component is also Client)
- `next.config.{js,ts,mjs}` - `images`, `experimental`, `serverExternalPackages`, `webpack` overrides, `reactStrictMode`, output mode (`standalone` / `export`)
- Server Actions (functions marked `"use server"`) and their callers - note `revalidatePath` / `revalidateTag` calls
- Data fetching: `fetch` calls in Server Components (note `cache` / `next.revalidate` / `next.tags` options), TanStack Query usage in Client Components, `unstable_cache` wrappers
- `app/**/*.tsx` Suspense boundaries (`<Suspense fallback={...}>`) and streaming intent
- `package.json` for new dependencies - flag any client-side dependency > 50KB minified+gzipped

**Vite + React Router surface:**

- Every changed component file - all components run client-side; no Server Component boundary to track
- `vite.config.{js,ts}` - plugins, `build.rollupOptions`, manual chunks, code-split config
- `src/router.tsx` / `src/main.tsx` - route definitions, `lazy()` route loaders, `<Suspense>` boundaries
- TanStack Query setup (`QueryClient` config, default `staleTime` / `gcTime`)
- `package.json` for new client dependencies

For each finding produced later, cite a real `file:line`. If the diff is small but ripples through code that is not in the diff (a new Client Component imports a heavy library that becomes part of every page that uses it), read the unchanged file too - the regression lives there.

### Step 4 - Render and Re-Render Hotspots

Use skill: `react-hooks-patterns` for canonical hook discipline; use skill: `react-component-patterns` for component shape.

Inspect every changed component for:

- [ ] **`"use client"` placement (Next.js)**: Client directive is at the **leaf** of the tree, not the root. A `"use client"` on a layout pulls all descendants client-side, defeating RSC. Move state-holding fragments into small Client Components and keep the surrounding tree on the server
- [ ] **Unnecessary client-side conversion**: a component marked `"use client"` that has no hook, no event handler, no browser API call, no `useState` / `useEffect` / `useRef` - revert to Server Component for free bundle savings
- [ ] **Ref / state in Server Component**: any `useState` / `useRef` / `useEffect` in a file without `"use client"` is a build error; flagged as a code smell that signals confused RSC mental model
- [ ] **Object / array / function props rebuilt every render**: `<Child config={{...}} onClick={() => ...} items={[...]}>` triggers re-render of memoized children every parent render; lift to module scope, `useMemo`, or `useCallback` when the child is `React.memo`-wrapped or expensive
- [ ] **`useMemo` / `useCallback` on cheap values**: memoizing primitives (`useMemo(() => count + 1, [count])`) costs more than the recomputation; flag as noise. Only memo when (a) the value is a stable reference for `React.memo` children, (b) the computation is genuinely expensive (>1ms in dev), or (c) it gates an expensive `useEffect` dependency
- [ ] **`React.memo` on always-changing props**: `React.memo(Component)` is useless if the parent passes a new object / array / function each render. Pair with stable references at the call site, or skip
- [ ] **Context value rebuilt every render**: `<Provider value={{ a, b }}>` recreates the object every render → every consumer re-renders. Memoize via `useMemo(() => ({ a, b }), [a, b])` or split into multiple contexts (state vs dispatch) for finer-grained re-rendering
- [ ] **`useEffect` for derived state**: `useEffect(() => setX(a + b), [a, b])` re-renders twice. Compute during render: `const x = a + b`. Reserve `useEffect` for synchronization with external systems (subscriptions, DOM, intervals), not "things that depend on state"
- [ ] **`useEffect` for event handlers**: handling user actions inside `useEffect(() => { if (clicked) ... }, [clicked])` is the wrong primitive; call the handler from the event directly. The React docs' "you might not need an effect" applies
- [ ] **`useEffect` without cleanup**: subscriptions, intervals, observers without a return cleanup leak across re-renders; flag explicitly
- [ ] **Missing `key` on lists / wrong `key`**: `key={index}` on a reorderable list breaks reconciliation; key by stable ID. Flag missing `key` (React warns but it is still a perf bug) and `key={index}` on lists that mutate
- [ ] **Inline style objects**: `style={{ color: 'red' }}` allocates per render; for hot paths prefer Tailwind / CSS Modules / cva variants - constant class strings, no per-render allocation
- [ ] **Heavy synchronous work in render**: parsing, sorting, filtering large arrays, JSON serialization in render body. Move to `useMemo` (with real cost) or precompute outside the component
- [ ] **`useState` initializer not lazy when expensive**: `useState(expensiveCompute())` runs on every render; use `useState(() => expensiveCompute())` for one-shot init
- [ ] **Inline anonymous components inside parent body**: `function Row({ data }) {...}` declared inside the parent's render function (`function Table() { function Row(...) {} return <ul>{rows.map(d => <Row data={d} />)}</ul> }`) is recreated every parent render - new function identity each time, which (a) makes `React.memo(Row)` a no-op, (b) destroys any `useState` inside `Row` between renders, (c) breaks reconciliation. Move the inner component to module scope (or a sibling file) so its identity is stable
- [ ] **List virtualization absent for long lists**: rendering 1000+ items (or 100+ rows of complex content - charts, sub-tables, rich JSX) without `@tanstack/react-virtual` / `react-window` causes long initial render and laggy scroll. Threshold scales with row complexity: simple row × 1000+ or complex row × 100+. Flag steady-state lists, not transient ones (e.g., a search-result dropdown showing 50 items is fine without virtualization)

### Step 5 - Bundle Size and Code Splitting

Use skill: `react-component-patterns` for split boundaries; use skill: `react-nextjs-patterns` for Next.js-specific dynamic imports.

- [ ] **New dependencies measured**: any new entry in `dependencies` (not `devDependencies`) gets a size note. Use `bundle-phobia` mentally / `pnpm why <pkg>` for transitive cost. Flag anything > 50KB minified+gzipped that is not lazy-loaded
- [ ] **Heavy libraries pulled into the client bundle eagerly**: charting (`recharts`, `chart.js`, `apexcharts`), rich text (`tiptap`, `slate`, `quill`), date pickers (`react-datepicker` w/ moment), `moment` (use `date-fns` / `dayjs` / native `Intl`), `lodash` (use `lodash-es` and tree-shake; better, native or `radash`)
- [ ] **`next/dynamic` for route-level heavy components**: `const Editor = dynamic(() => import('./Editor'), { ssr: false, loading: () => <Skeleton /> })` for any component used on a single route, gated by user interaction, or only rendered conditionally
- [ ] **`React.lazy` + `Suspense` for Vite**: `const Editor = lazy(() => import('./Editor'))` wrapped in `<Suspense fallback={...}>`; route-level lazy via React Router `lazy:` route option
- [ ] **Barrel-file imports defeating tree-shake**: `import { X } from '@/components'` where `@/components/index.ts` re-exports 50 things drags the whole barrel in if not configured for tree-shaking. Prefer direct path imports (`@/components/X`) on the hot path
- [ ] **Polyfills / shims duplicated**: `core-js`, regenerator-runtime, `whatwg-fetch` duplicated across deps; check `package.json` `browserslist` is sane
- [ ] **CSS-in-JS runtime cost**: `styled-components` / `emotion` add runtime cost for styles + an extra render pass on hydration; flag as a Medium finding when added to a project that was Tailwind / CSS Modules. Tailwind / CSS Modules are zero-runtime; cva is build-time class concat
- [ ] **Tree-shake friendly imports**: `import isEqual from 'lodash/isEqual'` (or `lodash-es`); never `import _ from 'lodash'`. `import { format } from 'date-fns'` not `import * as df from 'date-fns'`. Named imports also matter for large libs like `recharts`, `framer-motion`, `@radix-ui/*` - `import * as recharts from 'recharts'` pulls every chart variant even if the diff uses one
- [ ] **Charting / rich-editor / map libraries dynamically imported**: `recharts`, `chart.js`, `apexcharts`, `tiptap`, `slate`, `quill`, `mapbox-gl`, `leaflet` rarely belong in the initial bundle - they belong below the fold or behind interaction. Wrap with `next/dynamic(() => import('./ReportChart'), { ssr: false })` (Next.js) or `lazy()` + `<Suspense>` (Vite). Flag eager imports as a Medium even when the page genuinely uses the chart - the LCP impact is the same

> **Impact heuristic - bundle blast radius.** A 50KB gzip dependency on the home route adds ~50KB transferred on every cold visit (every visitor, every device). On 3G that is ~1.3s longer download; on cable ~50ms; the worst case dominates LCP for budget-constrained users. Phrase the impact as "+<N>KB on every cold visitor of every route that imports this," not "the bundle got bigger."

### Step 6 - Data Fetching and Caching

Use skill: `react-data-fetching` for canonical patterns.

**Next.js (Server Components and `fetch`):**

- [ ] **`fetch` cache options explicit**: every Server Component `fetch(url, { cache: 'force-cache' | 'no-store', next: { revalidate: N, tags: [...] } })` declares its caching intent. Default in Next.js 15+ is `cache: 'no-store'` (uncached) - flag missing `cache` / `revalidate` on data that could be cached
- [ ] **Tag-based revalidation**: long-cached data revalidated via `revalidateTag('orders')` after Server Action mutations; not relying on full-route `revalidatePath` for fine-grained updates
- [ ] **`unstable_cache` for non-fetch IO**: ORM queries / file reads / Redis lookups in Server Components wrapped in `unstable_cache(fn, key, { revalidate, tags })` - else they hit the DB on every render
- [ ] **Parallel data fetching**: Server Component awaits `await Promise.all([getA(), getB()])` for independent fetches, not sequential `const a = await getA(); const b = await getB();` - waterfall doubles latency
- [ ] **N+1 fan-out over a list**: `await Promise.all(items.map(item => getDetail(item.id)))` parallelizes N requests but is still N round-trips. Flag and recommend a batched query (`getDetailsByIds(items.map(i => i.id))`) or DataLoader-style batching. Pure parallelism does not save the database
- [ ] **Suspense streaming used**: long-running fetches in Server Components wrapped in `<Suspense fallback={<Skeleton />}>` so the rest of the page streams immediately; not blocking the entire route on the slowest query
- [ ] **LCP element not inside Suspense fallback**: the hero image / above-the-fold content must not be deferred behind `<Suspense fallback={<Skeleton />}>` - that defers the LCP element itself. Suspense belongs around below-the-fold or non-critical content; the LCP element renders eagerly with `priority` (Next.js `<Image priority>`) so it is in the initial paint
- [ ] **`use()` for promise unwrapping (React 19)**: deeper components consume promises via `use(promise)` instead of waterfalling `await` calls; fall back to `<Suspense>` boundaries
- [ ] **No client-side fetch when server fetch would do**: a Client Component `useEffect(() => { fetch(...) }, [])` is a request waterfall (server renders, client hydrates, then client requests) - move the fetch to the parent Server Component and pass data down

**Both frameworks (TanStack Query):**

- [ ] **`staleTime` / `gcTime` set**: default `staleTime: 0` refetches on every mount - flag for endpoints whose data does not change per-mount. `staleTime: 60_000` for typical reads; longer for catalog / config data
- [ ] **Query keys are stable, structured arrays**: `['orders', { ownerId, status }]` not `'orders-' + JSON.stringify(filters)` - structured keys enable `queryClient.invalidateQueries({ queryKey: ['orders'] })` to invalidate per resource
- [ ] **Cache invalidation explicit after mutations**: `useMutation({ onSuccess: () => queryClient.invalidateQueries({ queryKey: ['orders'] }) })` - never rely on time-based revalidation for write paths
- [ ] **Optimistic updates for high-perceived-latency mutations**: `onMutate` snapshots state, sets optimistic value, `onError` rolls back. React 19 `useOptimistic` for component-local optimism
- [ ] **`useQueries` / `parallel queries` for fan-out**: independent reads run in parallel, not sequentially via dependent `useQuery` chains
- [ ] **Prefetch on intent**: `queryClient.prefetchQuery` on hover / focus for likely-next routes
- [ ] **No fetching in render body**: `fetch()` directly in component render (not via `useQuery` / Server Component) is a bug - re-fires on every render

### Step 7 - Core Web Vitals and Page Load

_Skipped at `quick` depth unless the diff touches a route, layout, or assets._

**LCP (Largest Contentful Paint):**

- [ ] **`next/image` for all images**: `<Image src={...} alt={...} priority={isHero} />` - automatic responsive sizing, modern format conversion (AVIF/WebP), lazy-load by default. Flag raw `<img>` for hero / above-the-fold images. `priority` on the LCP image marks it for high-priority preload
- [ ] **Vite equivalent**: `vite-imagetools` or manual `<img loading="lazy" srcset="..." sizes="...">` with explicit width / height. Hero image should not be lazy
- [ ] **`width` / `height` attributes** on every image (prevents CLS even when async-decoded); `next/image` enforces this
- [ ] **Hero image not deferred**: above-the-fold image must not be inside a Client Component that lazy-mounts, gated by Suspense for slow data, or set to `loading="lazy"`
- [ ] **`next/font` for fonts**: `import { Inter } from 'next/font/google'` self-hosts and preloads; flag `<link href="https://fonts.googleapis.com/...">` in `<head>` for new code (extra DNS lookup + render-blocking CSS)
- [ ] **`font-display: swap`**: webfonts use swap (default in `next/font`); flag `font-display: block` for above-the-fold text

**INP (Interaction to Next Paint):**

- [ ] **No long synchronous tasks on user input**: form submit handler doing 50ms of synchronous work blocks paint. Defer via `startTransition` (React 18+) for state updates that can be interrupted
- [ ] **`useTransition` for expensive state updates**: `const [isPending, startTransition] = useTransition(); startTransition(() => setFilters(next))` lets React keep the previous UI responsive
- [ ] **`useDeferredValue` for filtering / search**: render a stale UI on the new input value until the heavy re-render finishes
- [ ] **No long-running effects on click**: heavy computation in a click handler should be moved to a worker (`comlink` / native `Worker`), a network request, or `requestIdleCallback`

**CLS (Cumulative Layout Shift):**

- [ ] **Reserved space for async content**: skeletons / placeholders with the same dimensions as the final content (`h-64 w-full` for an image slot, fixed-height containers for ads / embeds)
- [ ] **No layout thrash from late-loading fonts**: `next/font` solves; for raw fonts use `font-display: swap` + `size-adjust` / `ascent-override` font metrics overrides
- [ ] **Late-injecting elements at the top of the page**: A/B test snippets, banners, cookie modals that push content down trigger CLS - reserve space or load below the fold

### Step 8 - Hydration and Streaming (Next.js)

_Skipped on Vite + React Router projects (no SSR / hydration)._

- [ ] **No hydration mismatch sources**: `Date.now()` / `Math.random()` / `new Date().toString()` rendered server-side without `suppressHydrationWarning` (use only for timestamps, not as a fix-all); access to `window` / `document` / `localStorage` in render body of a Server Component or unguarded Client Component
- [ ] **`useEffect` for browser-only APIs**: `window.matchMedia`, `localStorage`, `IntersectionObserver` accessed inside `useEffect` (or guarded by `typeof window !== 'undefined'`), never in render
- [ ] **Streaming via `<Suspense>`**: long-running data fetches isolated in their own `<Suspense fallback>` so the route shell streams first; not gating the whole page on the slowest query
- [ ] **Loading UI per route segment**: `app/**/loading.tsx` defined for routes with non-trivial data fetching - the file becomes the implicit Suspense fallback
- [ ] **No `dynamic = 'force-dynamic'` unless required**: opting a route out of static generation makes every request render server-side; only use when the data is genuinely per-request and not cacheable

### Step 9 - Caching, ISR, and Edge

_Skipped at `quick` depth and on Vite projects._

- [ ] **ISR vs SSG vs SSR chosen deliberately**: static (default in App Router with cached `fetch`) for content that changes occasionally; ISR via `next.revalidate: N` for periodic refresh; SSR (`cache: 'no-store'` or `dynamic = 'force-dynamic'`) only when truly per-request
- [ ] **Edge runtime when appropriate**: `export const runtime = 'edge'` for Route Handlers / Middleware that need low TTFB globally and do not need Node APIs (no `fs`, no native modules); Node runtime for everything else
- [ ] **`revalidateTag` over `revalidatePath`** for fine-grained invalidation; avoids invalidating an entire route's cache when only one entity changed
- [ ] **Middleware kept thin**: `middleware.ts` runs on every matched request; heavy work in middleware blocks every navigation. Avoid DB / external HTTP in middleware unless cached aggressively

### Step 10 - Observability for Perf (delegation hand-off)

_Skipped at `quick` depth._

This step is intentionally narrow - depth on observability belongs to `task-react-review-observability`. From a perf perspective, confirm only:

- [ ] Critical user journeys reachable from this PR have **some** instrumentation (`web-vitals` reporter wired, RUM SDK active, Sentry browser SDK with performance enabled, or Next.js `instrumentation.ts` exporting OTel); if not, raise as a Low/Recommendation finding and delegate to `task-react-review-observability` rather than dictating the design here
- [ ] No `console.log` left in render path of a hot route - if visible in the diff. If neither is in the diff, skip

Anything beyond presence/absence (sample rates, attribution, route segmentation) → `task-react-review-observability` owns it. Note the gap, do not duplicate the audit here.


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-perf`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as React; framework (Next.js App Router / Pages Router / Vite) and React version recorded before any framework-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Performance surface read directly (changed components, layouts, route handlers, config, data-fetching modules)
- [ ] `react-hooks-patterns` and `react-component-patterns` consulted for render hotspots
- [ ] `"use client"` boundary placement audited (Next.js); leaf-level placement preferred
- [ ] Bundle deltas assessed for any new `dependencies` entry; tree-shake-friendly imports verified
- [ ] `react-data-fetching` consulted for cache options, query keys, mutation invalidation
- [ ] N+1 fan-out (`Promise.all(items.map(...))`) flagged when present; batched-query alternative recommended
- [ ] Inline anonymous components in render bodies flagged as identity-instability hazards
- [ ] Tree-shake hostile imports (`import * as X from 'recharts' / 'date-fns' / 'lodash'`) flagged
- [ ] Heavy chart / editor / map libraries gated by `next/dynamic` or `React.lazy`; eager imports flagged
- [ ] Core Web Vitals (LCP image / fonts / CLS reservations / INP `useTransition`) checked when route or asset code changed
- [ ] LCP element verified not deferred behind `<Suspense fallback>`
- [ ] Hydration / streaming checks applied for Next.js; Vite section skipped on Vite-only projects
- [ ] ISR / SSG / SSR / Edge runtime decisions reviewed for changed routes (Next.js)
- [ ] Every finding states impact - measured (`LCP: 2.8s -> 1.4s`) when RUM data exists, estimated otherwise (`+45KB gzip on every cold visit to /dashboard`) - never just "this is slow"
- [ ] Findings ordered by impact; quick wins separated from structural changes
- [ ] Depth honored: `quick` ran only Steps 4 + 5; `standard` ran 4-10; `deep` adds capacity guidance and budget plan
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## React Performance Review Summary

**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Scope:** Frontend (React)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [what the problem is - name the React idiom: `"use client"` at root of layout pulls 800KB into bundle, missing `next/image` on hero, context value rebuilt every render, `useEffect` for derived state, etc.]
- **Impact:** [estimated effect - e.g., "+120KB gzip on every cold visit to /dashboard" or measured "LCP 2.8s -> 1.4s after fix"]
- **Fix:** [specific React change with code example - leaf `"use client"`, `next/dynamic`, `useMemo` context value, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Adopt route-level `next/dynamic` for editor pages", "Split filters context into state + dispatch contexts", "Add bundle budget to CI"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting refactor, build config change, or perf-test work worth spawning a subagent for). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Move `\"use client\"` from app/dashboard/layout.tsx to app/dashboard/_components/Filters.tsx"]
2. **[Delegate]** [High] [scope: build] - [one-line action, e.g., "Add bundle budget for /dashboard route - spawn build-config subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting issues without naming the React idiom ("this is slow" vs "context value rebuilt every render; wrap with `useMemo` or split into two contexts")
- Recommending generic frontend advice when a React pattern applies (say "use `next/dynamic`", not "lazy load")
- Suggesting `useMemo` / `useCallback` everywhere as a default - they cost more than they save on cheap values; only use when measurable
- Suggesting `React.memo` without checking that the props are stable - it is a no-op when the parent passes new objects/arrays/functions
- Recommending CSS-in-JS for "developer experience" when zero-runtime alternatives (Tailwind / CSS Modules / cva) match the project's conventions
- Approving `"use client"` at the root of a layout that has no client-only need - it pulls the whole tree into the client bundle and defeats RSC
- Approving `dynamic = 'force-dynamic'` on a route without a per-request reason - it disables every cache layer
- Approving raw `<img>` for hero / above-the-fold images on Next.js - `next/image` with `priority` is the right tool
- Conflating perf review with general code review or security review - delegate those to their workflows
- Treating high re-render counts as inherently bad - React is fast; only investigate when a profile or interaction lag implicates re-renders
- Recommending `useEffect(() => fetch(...), [])` in a Client Component when a parent Server Component (Next.js) could fetch and pass props down
