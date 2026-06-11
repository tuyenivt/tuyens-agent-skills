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

- Measure before optimizing (Lighthouse, DevTools, RUM); do not optimize blind. With no metrics, report static findings and make measurement the first High-impact recommendation
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

### Bundle Optimization

Route-level code splitting is mandatory:

```
// Bad: all routes in one bundle
import Dashboard from "./pages/Dashboard"
import AdminPanel from "./pages/AdminPanel"

// Good: each route is its own chunk
const Dashboard = lazy(() => import("./pages/Dashboard"))
const AdminPanel = lazy(() => import("./pages/AdminPanel"))
```

Bundle analysis: run an analyzer (webpack-bundle-analyzer, rollup-plugin-visualizer, `vite-bundle-visualizer`). Investigate any dep > 50KB gzipped, check for duplicates (multiple versions of the same lib), verify tree-shaking works.

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
<img
  src="/photos/hero.webp"
  srcset="/photos/hero-400.webp 400w, /photos/hero-800.webp 800w, /photos/hero-1200.webp 1200w"
  sizes="(max-width: 600px) 400px, (max-width: 900px) 800px, 1200px"
  width="1200" height="630" alt="Hero banner" fetchpriority="high" />
```

### INP

Common causes:
- Long tasks (> 50ms) blocking main thread
- Forced reflows (read-write-read DOM patterns)
- Heavy event handlers without debouncing

Fixes:
- Yield to the browser with `scheduler.yield()`, `requestIdleCallback`, or `setTimeout(fn, 0)`
- Debounce search/resize (150-300ms); use `requestAnimationFrame` for scroll/resize
- Batch DOM reads before writes
- Move CPU-bound work to Web Workers

### Render Performance

Profile first (React DevTools Profiler, Vue DevTools, Angular DevTools). Common causes: parent passing new object/array refs as props, context value churn re-rendering all consumers, missing list keys. Fix at the source: stabilize references (hoist constants, memoize callbacks passed to memoized children), split contexts into focused pieces, use selectors.

Memoize only when profiling shows a slow render. Memoizing simple components adds overhead without benefit.

```
// Good: only the expensive child is memoized
const ExpensiveChart = memo(({ data }) => <D3Chart data={data} />)
const sortedData = useMemo(() => data.sort(complexSortFn), [data])
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

- Never invent numbers: when a value cannot be measured or estimated from the input (static diff, scoped component review), write `Unknown - not measured` and set Status to `Unknown`.
- Issues Found = defects in the reviewed code (each with a fix). Recommendations = proactive improvements beyond fixing defects. Do not duplicate an item across both.
- Emit `No Issues Found` only when `Issues Found` is empty; the two are mutually exclusive.

```
## Frontend Performance Assessment

**Stack:** {detected language / framework}
**Build tool:** {detected build tool}

### Core Web Vitals Estimate

| Metric | Current (estimated) | Target  | Status              |
| ------ | ------------------- | ------- | ------------------- |
| LCP    | {estimate}          | < 2.5s  | {Good | Needs Work | Unknown} |
| INP    | {estimate}          | < 200ms | {Good | Needs Work | Unknown} |
| CLS    | {estimate}          | < 0.1   | {Good | Needs Work | Unknown} |

### Bundle Analysis

- Total bundle size (gzipped): {estimate}
- Largest chunks: {list}
- Code splitting: {Yes - route-level | Partial | Missing}

### Recommendations

- [Impact: High | Medium | Low] {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if performance is adequate - do not omit this section silently}
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
