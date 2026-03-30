---
name: frontend-performance
description: Frontend performance - Core Web Vitals, bundle splitting, lazy loading, image optimization, render performance, memoization discipline. Adapts to detected frontend framework and build tool.
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
- Improving render performance for complex UIs
- Reviewing lazy loading, code splitting, and image optimization strategies
- Diagnosing slow initial page loads or sluggish interactions

## Rules

- Measure before optimizing - use Lighthouse, Chrome DevTools, and real user metrics (RUM) to identify actual bottlenecks
- Optimize the critical rendering path first - above-the-fold content must load without unnecessary blocking resources
- Every route must be code-split - no single bundle containing the entire application
- Images must be lazy-loaded below the fold and served in modern formats (WebP/AVIF) with responsive sizing
- Memoization is a last resort, not a default - only memoize when profiling proves a render is expensive
- Never sacrifice accessibility for performance (e.g., removing focus styles, skeleton-only without text alternatives)

---

## Patterns

**Prioritize by impact:** Address issues in this order: (1) LCP blockers (largest impact on perceived speed), (2) CLS sources (visual stability), (3) INP/interaction delays, (4) bundle size reduction, (5) render optimization. Within each category, fix the issue with the largest measured or estimated impact first.

### Core Web Vitals Targets

| Metric | What It Measures          | Good    | Needs Improvement | Poor    |
| ------ | ------------------------- | ------- | ----------------- | ------- |
| LCP    | Largest Contentful Paint  | < 2.5s  | 2.5s - 4s         | > 4s    |
| INP    | Interaction to Next Paint | < 200ms | 200ms - 500ms     | > 500ms |
| CLS    | Cumulative Layout Shift   | < 0.1   | 0.1 - 0.25        | > 0.25  |

### Bundle Optimization

**Code splitting by route** - Load only the code needed for the current page:

**Bad** - Single bundle:

```
// All routes in one bundle - users download everything upfront
import Home from "./pages/Home"
import Dashboard from "./pages/Dashboard"
import Settings from "./pages/Settings"
import AdminPanel from "./pages/AdminPanel"
```

**Good** - Lazy-loaded routes:

```
// Each route loads its own chunk on demand
const Home = lazy(() => import("./pages/Home"))
const Dashboard = lazy(() => import("./pages/Dashboard"))
const Settings = lazy(() => import("./pages/Settings"))
const AdminPanel = lazy(() => import("./pages/AdminPanel"))
```

**Bundle analysis checklist:**

- Run bundle analyzer (webpack-bundle-analyzer, rollup-plugin-visualizer, or `npx vite-bundle-visualizer`)
- Identify dependencies > 50KB gzipped - evaluate alternatives or dynamic imports
- Check for duplicate dependencies (different versions of the same library)
- Ensure tree-shaking is working (no importing entire libraries for one function)

### Image Optimization

| Technique         | Implementation                                              |
| ----------------- | ----------------------------------------------------------- |
| Modern formats    | Serve WebP/AVIF with `<picture>` fallback to JPEG/PNG       |
| Responsive sizing | `srcset` + `sizes` attributes, or framework image component |
| Lazy loading      | `loading="lazy"` for below-fold images                      |
| Priority hints    | `fetchpriority="high"` for LCP image                        |
| Dimensions        | Always set `width`/`height` to prevent CLS                  |
| CDN delivery      | Serve images from CDN with automatic format negotiation     |

**Bad** - Unoptimized images:

```html
<img src="/photos/hero.png" />
```

Problem: No lazy loading, no responsive sizing, PNG format, no dimensions (causes CLS).

**Good** - Optimized images:

```html
<img
  src="/photos/hero.webp"
  srcset="
    /photos/hero-400.webp   400w,
    /photos/hero-800.webp   800w,
    /photos/hero-1200.webp 1200w
  "
  sizes="(max-width: 600px) 400px, (max-width: 900px) 800px, 1200px"
  width="1200"
  height="630"
  alt="Hero banner"
  fetchpriority="high"
/>
```

### INP (Interaction to Next Paint)

INP measures responsiveness - the time from user interaction to the next visual update. Target: < 200ms.

**Common INP problems:**
- Long tasks (> 50ms) blocking the main thread during interaction
- Synchronous layout reads forcing reflow (`offsetHeight`, `getBoundingClientRect` inside loops)
- Expensive event handlers without debouncing

**Fixes:**
- Break up long synchronous work with `requestIdleCallback`, `scheduler.yield()`, or `setTimeout(fn, 0)` to yield to the browser
- Debounce expensive event handlers (search, resize, scroll): 150-300ms for search input, `requestAnimationFrame` for scroll/resize
- Avoid forced reflows: batch DOM reads before DOM writes, never interleave read-write-read patterns
- Move heavy computation to Web Workers for truly CPU-bound work

### Render Performance

**Expensive re-renders** - Identify and fix unnecessary renders:

1. **Profile first**: Use React DevTools Profiler, Vue DevTools performance tab, or Angular DevTools
2. **Common causes**: Parent re-rendering passes new object/array references as props, context value changes trigger all consumers, missing keys on lists
3. **Fix at the source**: Stabilize references (extract constants, useMemo for expensive computations), split context into smaller pieces, use selectors

**Memoization discipline:**

| Memoize When                                   | Do NOT Memoize When                     |
| ---------------------------------------------- | --------------------------------------- |
| Profiler shows component re-renders > 16ms     | Component renders are already fast      |
| Expensive computation in render path           | Simple prop comparisons                 |
| Stable reference needed for child optimization | No evidence of performance issue        |
| Large list items re-rendering on parent change | Small number of simple child components |

**Bad** - Memoizing everything:

```
// Every component wrapped in memo, every function in useCallback, every value in useMemo
const MemoizedButton = memo(({ label }) => <button>{label}</button>)
const handleClick = useCallback(() => setCount(c => c + 1), [])
const doubled = useMemo(() => count * 2, [count])
```

Problem: Adds memory overhead and complexity with no measurable benefit for simple components.

**Good** - Targeted memoization:

```
// Only memoize the expensive component that profiling identified as slow
const ExpensiveChart = memo(({ data }) => <D3Chart data={data} />)

// Only useMemo for actually expensive computation
const sortedData = useMemo(() => data.sort(complexSortFn), [data])
```

### Lazy Loading

Beyond route-level code splitting, lazy-load heavy components:

- Modals and dialogs (loaded on trigger)
- Charts and data visualizations (loaded when scrolled into view)
- Rich text editors (loaded on focus)
- Below-fold content sections (IntersectionObserver)

### Font Optimization

- Limit font families to 2-3 maximum; limit weights to what is actually used
- Self-host fonts for performance (eliminates third-party DNS lookup and connection). Use `@fontsource` packages or `next/font` (Next.js) for automatic self-hosting and optimization
- Combine font requests: if using Google Fonts CDN, combine families into a single URL parameter
- Preload the critical font file(s): `<link rel="preload" href="font.woff2" as="font" type="font/woff2" crossorigin>`
- Use `font-display: swap` to prevent invisible text during font loading
- Subset fonts to include only the character ranges needed for the content language

### CLS Prevention

Common CLS causes and fixes:

| Cause                         | Fix                                                    |
| ----------------------------- | ------------------------------------------------------ |
| Images without dimensions     | Always set `width` and `height` (or `aspect-ratio`)    |
| Dynamically injected content  | Reserve space with min-height or skeleton placeholder  |
| Web fonts causing text reflow | `font-display: swap` + `size-adjust` for fallback font |
| Ads or embeds loading late    | Reserve fixed dimensions for embed containers          |
| Client-side rendering flash   | Use SSR/SSG for initial content, or skeleton screens   |

## Stack-Specific Guidance

After loading stack-detect, apply performance patterns using the tools and conventions of the detected ecosystem:

- **React**: React.lazy + Suspense for code splitting, React Server Components for zero-JS server rendering, React Profiler for render analysis, Next.js Image component for automatic optimization
- **Vue**: defineAsyncComponent for lazy loading, Nuxt useHead for resource hints, Vue DevTools performance tab, Nuxt Image module for optimization
- **Angular**: loadComponent/loadChildren for lazy routes, Angular CLI budgets for bundle limits, Angular DevTools profiler, NgOptimizedImage directive

If the detected stack is unfamiliar, apply the universal patterns above and recommend the user consult their framework's performance documentation.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## Frontend Performance Assessment

**Stack:** {detected language / framework}
**Build tool:** {detected build tool}

### Core Web Vitals Estimate

| Metric | Current (estimated) | Target | Status              |
| ------ | ------------------- | ------ | ------------------- |
| LCP    | {estimate}          | < 2.5s | {Good | Needs Work} |
| INP    | {estimate}          | < 200ms| {Good | Needs Work} |
| CLS    | {estimate}          | < 0.1  | {Good | Needs Work} |

### Bundle Analysis

- Total bundle size (gzipped): {estimate}
- Largest chunks: {list}
- Code splitting: {Yes - route-level | Partial | Missing}

### Recommendations

- [Impact: High | Medium | Low] {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description of performance issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if performance is adequate - do not omit this section silently}
```

---

## Avoid

- Premature memoization without profiling evidence (adds complexity, may hurt performance)
- Loading entire third-party libraries when only one function is needed (kills tree-shaking)
- Images without explicit dimensions (causes CLS)
- Blocking the main thread with synchronous computation > 50ms (causes poor INP)
- Inlining large data in HTML (increases TTFB, blocks parser)
- Using CSS `@import` (creates request chains; use bundler imports instead)
- Lazy loading above-the-fold or LCP images (delays critical content)
- Ignoring font loading strategy (causes flash of invisible/unstyled text)
