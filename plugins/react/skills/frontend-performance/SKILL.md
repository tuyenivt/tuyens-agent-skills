---
name: frontend-performance
description: Optimize frontend performance: Core Web Vitals, bundle splitting, lazy loading, image optimization, render perf, memoization. Adapts to stack.
metadata:
  category: frontend
  tags: [frontend, performance, core-web-vitals, bundle, lazy-loading, memoization, multi-stack]
user-invocable: false
---

# Frontend Performance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Optimizing Core Web Vitals (LCP, INP, CLS)
- Analyzing and reducing bundle size
- Diagnosing slow loads or sluggish interactions
- Reviewing lazy loading, code splitting, image optimization

## Rules

- Measure before optimizing (Lighthouse, DevTools, RUM); do not optimize blind. With no metrics, report static findings and put instrumentation first in `Recommendations` at `[Impact: High]` - Impact rates what the change unblocks, which is every other item on the list, while Severity rates a defect's effect on a vital
- Fix issues in impact order: LCP blockers, CLS, INP, bundle size, render
- Every route is code-split; no single bundle holds the whole app
- Below-fold images lazy-load; serve modern formats (WebP/AVIF) with responsive sizing and explicit dimensions
- Memoize only after profiling proves a render is expensive
- Never sacrifice accessibility for performance (no `outline: none`, no text-less skeletons)

---

## Patterns

### Core Web Vitals Targets

| Metric | Measures                  | Good    | Poor    |
| ------ | ------------------------- | ------- | ------- |
| LCP    | Largest Contentful Paint  | < 2.5s  | > 4s    |
| INP    | Interaction to Next Paint | < 200ms | > 500ms |
| CLS    | Cumulative Layout Shift   | < 0.1   | > 0.25  |

LCP is TTFB + resource load delay + load time + render delay, so check TTFB before optimizing images: a 2.8s TTFB caps LCP above target no matter how the hero image is served. Server-side causes need server-side fixes - parallelize the sequential awaits in the data path, cache what is stable, and stream so the shell paints before data resolves (Suspense boundaries in React/Next). Vue and Angular have no equivalent streaming primitive: Nuxt awaits async setup and sends a complete document, and Angular `@defer` is a client-side deferrable view that renders its placeholder during SSR - both defer client work rather than streaming HTML, so on those stacks the fix is caching and query parallelism. Optimize the resource half only once TTFB is under roughly 800ms.

### Bundle Optimization

Route-level code splitting is mandatory:

```
// Bad: all routes in one bundle
import Dashboard from "./pages/Dashboard"
import AdminPanel from "./pages/AdminPanel"

// Good: each route is its own chunk, rendered under a boundary
import { lazy, Suspense } from "react"
const Dashboard = lazy(() => import("./pages/Dashboard"))
const AdminPanel = lazy(() => import("./pages/AdminPanel"))
<Suspense fallback={<RouteSkeleton />}><Dashboard /></Suspense>
```

Bundle analysis: run an analyzer (webpack-bundle-analyzer, rollup-plugin-visualizer, `vite-bundle-visualizer`). Investigate any dep > 50KB gzipped, check for duplicates (multiple versions of the same lib), verify tree-shaking works.

**Third-party scripts usually outweigh your own** - analytics, chat, ads, tag managers - and an analyzer never shows them because they are not in your bundle. Audit them from the network panel, not the build:

- Nothing third-party blocks parsing: `async`/`defer`, or the framework's loading strategy (`next/script` with `afterInteractive`/`lazyOnload`, Nuxt `useHead` with `defer`).
- Replace heavy embedded widgets with a facade - a static preview that loads the real chat, map, or video player on click. This is usually the single largest INP win on a marketing site.
- Audit what a tag manager actually ships; a container grows without any code change of yours.
- Consider moving tags off the main thread (Partytown) when they cannot be removed.

### Performance Budgets

Finding a regression after it ships is the slow path. Set budgets and enforce them in CI - `size-limit` or `bundlewatch` for bundle bytes, Lighthouse CI assertions for vitals, Angular CLI `budgets` where the framework supplies them - so a PR that crosses the line fails rather than merges. Budget the routes users actually load, not the total build, and pair the lab check with field RUM: CI catches what you built, RUM catches what your users experience on their devices and networks.

### Image Optimization

| Technique         | How                                                         |
| ----------------- | ----------------------------------------------------------- |
| Modern formats    | WebP/AVIF with `<picture>` fallback                         |
| Responsive sizing | `srcset` + `sizes`, or framework image component            |
| Lazy loading      | `loading="lazy"` for below-fold                             |
| LCP image hint    | `fetchpriority="high"`                                      |
| Dimensions        | Always set `width`/`height` (or `aspect-ratio`) to avoid CLS |
| CDN               | Auto format negotiation                                     |

```html
<picture>
  <source type="image/avif" sizes="100vw"
          srcset="/photos/hero-400.avif 400w, /photos/hero-800.avif 800w, /photos/hero-1200.avif 1200w" />
  <source type="image/webp" sizes="100vw"
          srcset="/photos/hero-400.webp 400w, /photos/hero-800.webp 800w, /photos/hero-1200.webp 1200w" />
  <img
    src="/photos/hero-1200.jpg" sizes="100vw"
    srcset="/photos/hero-400.jpg 400w, /photos/hero-800.jpg 800w, /photos/hero-1200.jpg 1200w"
    width="1200" height="630" style="width:100%;height:auto"
    alt="Hero banner" fetchpriority="high" />
</picture>
<!-- Format negotiation happens across <source type=...>; srcset alone picks by width only,
     so every candidate in one srcset must be a format the browser already supports.
     `sizes` describes the rendered slot: a full-bleed image is 100vw, and a fixed 400px
     hint on a fluid layout downloads the small file and upscales it. -->
```

### INP

Common causes:
- Long tasks (> 50ms) blocking main thread
- Forced reflows (read-write-read DOM patterns)
- Heavy event handlers without debouncing

Fixes:
- Yield to the browser with `scheduler.yield()` or `setTimeout(fn, 0)`; `requestIdleCallback` only queues work for idle time and cannot break up a task already running
- Debounce search/resize (150-300ms); use `requestAnimationFrame` for scroll/resize
- Batch DOM reads before writes
- Move CPU-bound work to Web Workers

### Render Performance

Profile first (React DevTools Profiler, Vue DevTools, Angular DevTools). Common causes: parent passing new object/array refs as props, context value churn re-rendering all consumers, missing list keys. Fix at the source: stabilize references (hoist constants, memoize callbacks passed to memoized children), split contexts into focused pieces, use selectors.

Memoize only when profiling shows a slow render. Memoizing simple components adds overhead without benefit.

```
// Good: only the expensive child is memoized
const ExpensiveChart = memo(({ data }) => <D3Chart data={data} />)

function Report({ data }) {
  // Copy before sorting: Array.sort mutates in place and returns the same reference,
  // which both mutates a prop during render and defeats the memo below.
  const sortedData = useMemo(() => [...data].sort(complexSortFn), [data])
  return <ExpensiveChart data={sortedData} />
}
```

### Lazy Loading Beyond Routes

Lazy-load modals (on trigger), charts (on visible via IntersectionObserver), rich text editors (on focus), and below-fold sections.

### Font Optimization

- Limit to 2-3 families and the weights actually used
- Self-host (eliminates third-party DNS lookup); `@fontsource` or `next/font`
- Preload critical files: `<link rel="preload" href="font.woff2" as="font" type="font/woff2" crossorigin>`
- `font-display: swap` to avoid invisible text
- Subset to the character ranges needed

### CLS Prevention

| Cause                         | Fix                                              |
| ----------------------------- | ------------------------------------------------ |
| Images without dimensions     | Set `width`/`height` or `aspect-ratio`           |
| Dynamically injected content  | Reserve space (min-height or skeleton)           |
| Web font reflow               | `font-display: swap` + `size-adjust` on fallback |
| Late ads/embeds               | Reserve fixed dimensions for the container       |
| Client-render flash           | SSR/SSG initial content, or skeleton             |

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: `React.lazy` + Suspense; React Server Components; React Profiler; Next.js `Image`
- **Vue**: `defineAsyncComponent`; Nuxt `useHead` for resource hints; Nuxt Image
- **Angular**: `loadComponent`/`loadChildren`; CLI budgets; `NgOptimizedImage`

For unknown stacks, apply universal patterns and point the user to the framework's perf docs.

---

## Output Format

Consuming workflow skills depend on this structure.

- Never invent numbers: when a value cannot be measured or estimated from the input (static diff, scoped component review), write `Unknown - not measured` and set Status to `Unknown`. When real measurements are supplied, use them and label the column value `(measured)`.
- Add a `Not assessed:` line after the last issue naming anything the input never showed or that could not be verified from it - a file in scope that no route imports, a handler whose reachability the given files do not establish. Rate what you can see; a defect whose execution path is unconfirmed stays Medium and says so.
- Issues Found = defects in the reviewed code (each with a fix). Recommendations = proactive improvements beyond fixing defects. Do not duplicate an item across both.
- Emit `No Issues Found` only when `Issues Found` is empty; the two are mutually exclusive. A clean run still emits every header field, the vitals table, the bundle block and `Recommendations`; only the `Issues Found` blocks are omitted.
- Order Issues Found by severity, highest first; within a band, file order.
- Severity and Impact share one anchor: High = directly degrades a Core Web Vital on a primary route (LCP blocker, CLS source, long task on interaction path); Medium = bundle or render waste with no direct vitals breach; Low = polish.
- In implement or design mode (planning or building, not reviewing), the vitals table holds targets with Status `Unknown`, Recommendations carries the plan, and Issues Found carries only residual risks knowingly accepted.

```
## Frontend Performance Assessment

**Stack:** {detected language / framework, or "unknown - universal patterns applied"}

**Bundler:** {the bundler in use - Vite, webpack, Turbopack, Rollup; `unknown` when no build config was in scope. Named separately from `stack-detect`'s `Build tool`, which reports the package manager for JS/TS}

### Core Web Vitals Estimate

| Metric | Current ({estimated} or {measured}) | Target  | Status              |
| ------ | ------------------- | ------- | ------------------- |
| LCP    | {estimate}          | < 2.5s  | {Good \| Needs Work \| Poor \| Unknown} |
| INP    | {estimate}          | < 200ms | {Good \| Needs Work \| Poor \| Unknown} |
| CLS    | {estimate}          | < 0.1   | {Good \| Needs Work \| Poor \| Unknown} |

### Bundle Analysis

- Total bundle size (gzipped): {estimate}
- Largest chunks: {list}
- Third-party weight: {scripts loaded outside the bundle - analytics, chat, tag managers - with sizes when observed, `none observed` when the input shows no tags. An analyzer never sees these}
- Code splitting: {Yes - route-level | Partial | Missing | Unknown - no routing entry in scope}

### Recommendations

- [Impact: High | Medium | Low] {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### Not assessed

- {anything the input never showed or that could not be verified from it - a value needing a measurement, a file in scope that no route imports, a handler whose reachability the given files do not establish. Omit this section when nothing applies}

### No Issues Found

{Emit this section only when Issues Found is empty, and state explicitly that performance is adequate. When issues were found, omit it entirely}
```

---

## Avoid

- Premature memoization without profiling
- Importing whole libraries for one function (kills tree-shaking)
- Images without explicit dimensions
- Synchronous main-thread work > 50ms
- Inlining large data in HTML (blocks parser, hurts TTFB)
- CSS `@import` (request chains; use bundler imports)
- Lazy loading above-the-fold or LCP images
- Ignoring font loading strategy (FOIT/FOUT)
