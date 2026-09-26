---
name: frontend-performance
description: Optimize Next.js frontend performance: Core Web Vitals, bundle splitting, lazy loading, image and font optimization, render perf, memoization.
metadata:
  category: frontend
  tags: [frontend, performance, core-web-vitals, bundle, lazy-loading, memoization, nextjs]
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
- Routes are code-split per segment automatically; a Client Component or library that first paint does not need loads on demand with `next/dynamic`
- Below-fold images lazy-load; serve modern formats (WebP/AVIF) with responsive sizing and explicit dimensions
- Memoize by hand only after profiling proves a render is expensive; with the React Compiler on (`reactCompiler` top-level or a leftover `experimental.reactCompiler`; in `compilationMode: 'annotation'` only `"use memo"` components) the compiler memoizes, and a manual `memo`/`useMemo` is added only for a measured miss
- Never sacrifice accessibility for performance (no `outline: none`, no text-less skeletons)

---

## Patterns

### Core Web Vitals Targets

| Metric | Measures                  | Good     | Poor    |
| ------ | ------------------------- | -------- | ------- |
| LCP    | Largest Contentful Paint  | <= 2.5s  | > 4s    |
| INP    | Interaction to Next Paint | <= 200ms | > 500ms |
| CLS    | Cumulative Layout Shift   | <= 0.1   | > 0.25  |

Between Good and Poor is `Needs Improvement` (the CrUX / PageSpeed band name).

LCP is TTFB + resource load delay + load time + render delay, so check TTFB before optimizing images: a 2.8s TTFB caps LCP above target no matter how the hero image is served. Server-side causes need server-side fixes - parallelize the sequential awaits in the data path, collapse per-item queries (N+1) into one, cache what is stable, and stream so the shell paints before data resolves (`<Suspense>` boundaries, `loading.tsx`). With `cacheComponents: true` in `next.config`, the prerendered static shell is sent before any request-time data runs, so TTFB no longer waits on the data path; request-time data must sit inside `<Suspense>`. Optimize the resource half only once TTFB is under roughly 800ms.

### Bundle Optimization

The App Router splits each route segment on its own, and Server Components ship no component JS; client weight is the `"use client"` modules and everything they import. Split what first paint does not need:

```tsx
// Bad: the editor ships in the route's client bundle even when never opened
"use client"
import RichEditor from "./RichEditor"

// Good: its own chunk, fetched when rendered
"use client"
import dynamic from "next/dynamic"
const RichEditor = dynamic(() => import("./RichEditor"), { loading: () => <EditorSkeleton /> })
```

`{ ssr: false }` is valid only inside a Client Component; in a Server Component it is a build error.

Bundle analysis: `next experimental-analyze` (Turbopack, 16.1+; `--output` writes `.next/diagnostics/analyze` for before/after diffs); `@next/bundle-analyzer` covers only `--webpack` builds. `next build` no longer prints route `size` / `First Load JS`, so bytes come from the analyzer, Lighthouse or a network trace. Investigate any dep > 50KB gzipped, check for duplicates (multiple versions of the same lib), verify tree-shaking works; a package with hundreds of named exports goes in `experimental.optimizePackageImports` (`lucide-react`, `date-fns`, `lodash-es` and others are optimized by default).

**Third-party scripts usually outweigh your own** - analytics, chat, ads, tag managers - and an analyzer never shows them because they are not in your bundle. Audit them from the network panel, not the build:

- Nothing third-party blocks parsing: `next/script` with `strategy="afterInteractive"` or `"lazyOnload"`, never a raw blocking `<script>` in the root layout.
- Replace heavy embedded widgets with a facade - a static preview that loads the real chat, map, or video player on click. This is usually the single largest cut in load-time main-thread work (TBT) on a marketing site, with INP improving as a consequence. On a page that eagerly boots such a widget, the missing facade is a defect (Issues Found), not a recommendation.
- Audit what a tag manager actually ships; a container grows without any code change of yours.
- A tag that cannot be removed or facaded loads with `lazyOnload`; Next's off-main-thread `worker` strategy (Partytown) works only in `pages/`, not the App Router.

### Performance Budgets

Finding a regression after it ships is the slow path. Set budgets and enforce them in CI - `size-limit` or `bundlewatch` for bundle bytes, Lighthouse CI assertions for vitals - so a PR that crosses the line fails rather than merges. Budget the routes users actually load, not the total build, and pair the lab check with field RUM: CI catches what you built, RUM catches what your users experience on their devices and networks.

### Image Optimization

| Technique         | How                                                         |
| ----------------- | ----------------------------------------------------------- |
| Modern formats    | `next/image` negotiates by `Accept` header; WebP by default, AVIF via `images.formats` |
| Responsive sizing | `next/image` with `sizes` (without it, only a 1x/2x `srcset`) |
| Lazy loading      | `next/image` lazy-loads by default                          |
| LCP image hint    | `loading="eager"` plus `fetchPriority="high"` (`fetchPriority` alone still lazy-loads), or `preload` for a single LCP candidate; `priority` is deprecated |
| Dimensions        | `width`/`height`, a static import, or `fill` in a sized parent, to avoid CLS |

```tsx
import Image from "next/image"
import hero from "./hero.jpg" // static import: width and height inferred

<Image src={hero} alt="Hero banner" sizes="100vw" loading="eager" fetchPriority="high"
  style={{ width: "100%", height: "auto" }} />
// `sizes` describes the rendered slot: a full-bleed image is 100vw, and a fixed 400px
// hint on a fluid layout downloads the small file and upscales it.
```

### INP

Common causes:
- Long tasks (> 50ms) blocking main thread
- Forced reflows (read-write-read DOM patterns)
- Heavy event handlers without debouncing

Fixes:
- Yield to the browser with `scheduler.yield()` where it exists (`globalThis.scheduler?.yield` - no Safari support), falling back to `await new Promise(r => setTimeout(r, 0))`; `requestIdleCallback` only queues work for idle time and cannot break up a task already running
- Debounce search input (150-300ms); throttle scroll and resize handlers to `requestAnimationFrame`
- Batch DOM reads before writes
- Move CPU-bound work to Web Workers

### Render Performance

Profile first (React DevTools Profiler). Common causes: parent passing new object/array refs as props, context value churn re-rendering all consumers, missing list keys. Fix at the source: stabilize references (hoist constants, memoize callbacks passed to memoized children), split contexts into focused pieces, use selectors.

Memoize only when profiling shows a slow render. Memoizing simple components adds overhead without benefit. With the React Compiler on, compiled components and values are memoized at build time; hand-written `memo`/`useMemo` stays only where the profiler shows the compiler missed a case.

```
// Good: only the expensive child is memoized
const ExpensiveChart = memo(({ data }) => <D3Chart data={data} />)

function Report({ data }) {
  // Copy before sorting: Array.sort mutates in place, which mutates a prop during render -
  // every other consumer of `data` sees it reordered. (`data.toSorted(fn)` copies too, ES2023.)
  const sortedData = useMemo(() => [...data].sort(complexSortFn), [data])
  return <ExpensiveChart data={sortedData} />
}
```

### Lazy Loading Beyond Routes

Lazy-load with `next/dynamic`: modals (on trigger), charts (on visible via IntersectionObserver), rich text editors (on focus), and below-fold client sections.

### Font Optimization

- Limit to 2-3 families and the weights actually used
- Load through `next/font` (`next/font/google` or `next/font/local`): self-hosted with no third-party request, `display: 'swap'` and preload on by default, and a size-adjusted fallback that limits reflow
- Declare `subsets` to the character ranges needed; only declared subsets are preloaded

### CLS Prevention

| Cause                         | Fix                                              |
| ----------------------------- | ------------------------------------------------ |
| Images without dimensions     | Set `width`/`height` or `aspect-ratio`           |
| Dynamically injected content  | Reserve space (min-height or skeleton)           |
| Web font reflow               | `font-display: swap` + `size-adjust` on fallback |
| Late ads/embeds               | Reserve fixed dimensions for the container       |
| Client-render flash           | Initial content from a Server Component, or a sized `loading.tsx` / Suspense fallback |

## Next.js Bindings

- Server Components by default; `"use client"` at the leaves, since everything a client module imports ships to the browser
- `next/dynamic` for Client Components and libraries; `next/image`, `next/font`, `next/script` for assets
- `cacheComponents: true`: static shell first, request-time data streamed inside `<Suspense>`
- React Compiler on: automatic memoization of compiled components; React DevTools Profiler to confirm

---

## Output Format

Consuming workflow skills depend on this structure.

- Never invent numbers: a value is `(estimated)` only when derived from supplied data (a lab proxy such as TBT for INP, a sibling route's RUM) - a lab run's own reading of the reviewed route is `(measured)`; from static review alone write `Unknown - not measured` and set Status to `Unknown`. Supplied measurements are written `{value} (measured)`; label each cell, since one table may mix all three. The bundle sizes follow the same rule, and `next build` output carries no route sizes, so a bundle value comes from analyzer, Lighthouse or network-trace data in the input.
- Emit the `### Not assessed` section naming anything the input never showed or that could not be verified from it - a file in scope that no route imports, a handler whose reachability the given files do not establish. Rate what you can see; a defect whose execution path is unconfirmed is capped at Medium (a Low stays Low) and says so.
- Issues Found = defects in the reviewed code (each with a fix). Recommendations = proactive improvements beyond fixing defects. Do not duplicate an item across both.
- Emit `No Issues Found` only when `Issues Found` is empty; the two are mutually exclusive. A clean run still emits every header field, the vitals table, the bundle block and `Recommendations`; only the `Issues Found` blocks are omitted.
- Order Issues Found by severity, highest first; within a band, file order (the order the input lists the files; ascending line within a file). `Location` may list several `file:line` entries (or several lines of one file), comma-separated, when one root cause spans them; lead with the file the fix changes, and sort the finding by that lead file.
- Severity anchor: High = directly degrades a Core Web Vital on a primary route (LCP blocker, CLS source, long task on interaction path); Medium = bundle or render waste with no direct vitals breach (waste on a primary route's initial bundle is High only when the input shows it on the LCP or interaction path); Low = polish. Impact uses the same bands, with one addition: a change that unblocks or measures the High items (instrumentation when no metrics exist) is also `[Impact: High]`.
- In implement or design mode (planning or building, not reviewing), the vitals table holds targets with Status `Unknown`, Recommendations carries the plan, and Issues Found carries residual risks knowingly accepted. When the build or design touches existing code, defects already in it are ordinary Issues Found entries marked `(pre-existing)` at their own severity; the residual-risk reading covers only the new work. `No Issues Found` is then emitted only when neither exists, stating the plan carries no residual risk.

```
## Frontend Performance Assessment

**Stack:** {Framework and Language as a display name (`Next.js 16.3 / TypeScript` for stack-detect's `React (Next.js)`) - the major.minor from the owning app's `package.json` (`^16.3.0` -> 16.3); with no `tsconfig.json`, the extensions of the files in scope decide JS vs TS, overriding stack-detect's Language; in a monorepo, the app owning the reviewed code; `unknown` for a part that is inconclusive}

**Bundler:** {the production build's bundler - Turbopack (the `next build` default), or webpack when the build script passes `--webpack` - with the dev server's in parentheses when it differs (`webpack (dev: Turbopack)`); in a monorepo, the owning app's; `unknown` when no build config was in scope. Named separately from `stack-detect`'s `Build tool`, which reports the package manager for JS/TS}

### Core Web Vitals Estimate

| Metric | Current             | Target   | Status              |
| ------ | ------------------- | -------- | ------------------- |
| LCP    | {value} {(measured) \| (estimated)}, or `Unknown - not measured` | <= 2.5s  | {Good \| Needs Improvement \| Poor \| Unknown} |
| INP    | {value} {(measured) \| (estimated)}, or `Unknown - not measured` | <= 200ms | {Good \| Needs Improvement \| Poor \| Unknown} |
| CLS    | {value} {(measured) \| (estimated)}, or `Unknown - not measured` | <= 0.1   | {Good \| Needs Improvement \| Poor \| Unknown} |

### Bundle Analysis

- Total bundle size (gzipped): {value} {(measured) \| (estimated)}, or `Unknown - not measured`
- Largest chunks: {list with sizes as above}, or `Unknown - not measured`
- Third-party weight: {scripts loaded outside the bundle - analytics, chat, tag managers - with sizes when observed, `none observed` when the input shows no tags. An analyzer never sees these}
- Code splitting: {Yes - route-level | Partial | Missing | Unknown - no routing entry in scope}

### Recommendations

- [Impact: High | Medium | Low] {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}{ (pre-existing)}
  - Location: {file}:{line}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### Not assessed

- {anything the input never showed or that could not be verified from it - a value needing a measurement, a file in scope that no route imports, a handler whose reachability the given files do not establish. Omit this section when nothing applies}

Notes: {observations outside this skill's concern, each naming the owning concern; omit when none}

### No Issues Found

{Emit this section only when Issues Found is empty, and state explicitly that performance is adequate. When issues were found, omit it entirely}
```

---

## Avoid

- Premature memoization without profiling
- Importing whole libraries for one function (kills tree-shaking)
- Images without explicit dimensions
- Synchronous main-thread work > 50ms
- Inlining large data in HTML (a larger document delays FCP/LCP; serializing it before the first flush delays TTFB)
- CSS `@import` (request chains; use bundler imports)
- Lazy loading above-the-fold or LCP images
- Ignoring font loading strategy (FOIT/FOUT)
