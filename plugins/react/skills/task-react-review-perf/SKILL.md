---
name: task-react-review-perf
description: "React / Next.js perf review: Core Web Vitals, bundle, hydration, render churn, RSC boundaries, TanStack Query, Suspense, ISR."
agent: react-performance-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, performance, core-web-vitals, bundle, rsc, workflow]
  type: workflow
user-invocable: true
---

# React Performance Review

Stack-specific delegate of `task-code-review-perf` for React / Next.js / Vite. Preserves the parent contract (invocation, diff resolution, output shape).

## When to Use

- Reviewing a Next.js or Vite + React PR / branch for perf regressions
- Investigating a slow page or interaction (high INP, slow LCP, scroll jank, hydration cost)
- Pre-merge pass on changes touching bundle, data fetching, or rendering boundaries
- Quarterly Core Web Vitals / bundle sweep against RUM-flagged routes

**Not for:**

- General review (`task-react-review`)
- Security review (`task-react-review-security`)
- Production incident (`/task-oncall-start`)
- Pre-implementation design (`task-react-implement`)

## Severity Rubric

Steady-state user impact, not "how scary the code looks".

| Severity   | Definition                                                                                                                                                                                                                  |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | LCP / INP regression visible to every cold visitor: heavy lib in initial bundle (>50KB gzip, no split), `"use client"` at layout root pulling the tree client-side, hero `<img>` blocking LCP, missing virtualization on 1k+ rows, sync work on input (>200ms INP), hydration mismatch, `force-dynamic` on cacheable route. |
| **Medium** | Degraded p95 / wasted re-renders: context value rebuilt every render with many consumers, identity-unstable props on `React.memo` child, barrel imports defeating tree-shake, `staleTime: 0` on hot query, CSS-in-JS added to a Tailwind project, missing `next/image` on non-LCP images. |
| **Low**    | Allocation / churn quick wins: inline style objects on hot rows, `useMemo` on primitives, `console.log` in render, missing `next/font`, missing `loading="lazy"` below-the-fold. |

`next/image` placement: raw `<img>` on the LCP / hero element is High (blocks LCP); raw `<img>` on non-LCP images is Medium.

Tiebreaker: "would RUM flag this on a typical mobile cold visit?" yes -> High; "drag next quarter's perf budget?" yes -> Medium.

## Depth Levels

| Depth      | When                                                          | Runs                                       |
| ---------- | ------------------------------------------------------------- | ------------------------------------------ |
| `standard` | Default - full React perf review                              | Steps 1-9                                  |
| `deep`     | RUM-driven (Core Web Vitals data / profiling / route budgets) | All steps + capacity guidance + budget plan |

## Invocation

Mirrors `task-code-review-perf`:

| Invocation                         | Meaning                                                              |
| ---------------------------------- | -------------------------------------------------------------------- |
| `/task-react-review-perf`          | Review current branch vs its base; fails fast on trunk               |
| `/task-react-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                           |
| `/task-react-review-perf pr-<N>`   | Review PR head in local branch `pr-<N>` (user runs the fetch first)  |

When invoked as a subagent of `task-code-review-perf` or `task-react-review`, the parent passes the precondition handle plus already-read diff/log; skip Steps 1-3 re-detection.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. If parent already detected React, accept the handoff. If not React, stop and route to `/task-code-review-perf`. This workflow assumes React 18+ (RSC) or 19 (`use()`, `useOptimistic`, `useFormStatus`).

Record for the Summary block:

- `Framework:` Next.js (App Router) | Next.js (Pages Router) | Vite + React Router
- `Data Layer:` Server Components + `fetch` | TanStack Query | mixed
- `Styling:` Tailwind | CSS Modules | CSS-in-JS (`styled-components` / `emotion`)

Heuristics: `next.config.*` -> Next.js (App Router unless `pages/` without `app/`); `vite.config.*` without `next` -> Vite; both present -> ask the user.

### Step 3 - Resolve Diff and Read Surface

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once; reuse. Skip entirely if parent passed the handle.

Open the files that govern rendering, bundle, and data fetching so impact estimates ground in real code:

- **Next.js App Router:** changed `app/**/{page,layout,loading,error}.tsx` and `route.ts` (note `"use client"`), Server Action sites (`"use server"`), `next.config.*` (`images`, `experimental`), `package.json` deps, Suspense boundaries
- **Vite + React Router:** changed components (all client), `vite.config.*` chunks, `src/router.tsx` lazy routes / Suspense, `QueryClient` config
- Both: TanStack Query call sites, list components (rows + virtualization), image / font usage

If a small diff ripples through unchanged code (new caller of a heavy library, new Client Component importing a barrel), read the unchanged file too. Cite real `file:line` in every finding.

### Step 4 - Render and Re-Render Hotspots

Use skill: `react-hooks-patterns`. Use skill: `react-component-patterns`. Workflow-specific verifications:

- `"use client"` at the leaf, not the layout root - root placement pulls the whole subtree client-side and defeats RSC
- Identity-stable props on `React.memo` children: inline `{...}`, `[...]`, `() => ...` makes `memo` a no-op
- Context value memoized; high-fan-out contexts split into state + dispatch (`react-state-patterns`)
- No `useEffect` for derived state (compute in render) or event handling (call from handler)
- List `key` is a stable id, not `index`, for reorderable / filterable lists
- Virtualize when simple rows > 1000 or complex rows > 100 (`@tanstack/react-virtual`, `react-window`)
- Heavy sync work in render moved to `useMemo` with real deps, or precomputed; `useState` initializer lazy when expensive
- Components defined at module scope, not inside parent render body
- `useMemo` / `useCallback` only when the value gates `React.memo` / `useEffect` deps or computation >1ms - not on primitives

```tsx
// BAD: inline objects + memo no-op + Row redeclared every render
function List({ items }) {
  function Row({ item }) { return <div>{item.name}</div>; }
  return items.map(i => <Row key={i.id} item={i} config={{ dense: true }} />);
}

// GOOD: stable identity, Row hoisted, memo effective
const Row = memo(({ item, config }) => <div>{item.name}</div>);
const ROW_CONFIG = { dense: true };
function List({ items }) {
  return items.map(i => <Row key={i.id} item={i} config={ROW_CONFIG} />);
}
```

### Step 5 - Bundle Size and Code Splitting

Use skill: `react-component-patterns`. Use skill: `react-nextjs-patterns` (Next.js).

- Every new `dependencies` entry sized; flag >50KB gzip not lazy-loaded
- Charting (`recharts`, `chart.js`), rich text (`tiptap`, `slate`, `quill`), maps (`mapbox-gl`, `leaflet`), date pickers behind `next/dynamic({ ssr: false })` (Next) or `lazy()` + `<Suspense>` (Vite) - even when the page uses the chart, the LCP impact is the same
- Tree-shake-friendly imports: `import { format } from 'date-fns'`, `import isEqual from 'lodash/isEqual'`, never `import * as X from 'recharts'`
- Barrel `index.ts` imports on the hot path replaced with direct paths
- `moment` -> `date-fns` / `dayjs` / `Intl`; CSS-in-JS flagged when added to a zero-runtime project

Impact phrasing: "+<N>KB gzip on every cold visit to <route>", not "the bundle got bigger".

### Step 6 - Data Fetching and Caching

Use skill: `react-data-fetching`. Workflow-specific verifications:

**Next.js Server Components:**

- Every `fetch(url, { cache, next: { revalidate, tags } })` declares intent (Next 15+ default is `no-store`); non-fetch IO wrapped in `unstable_cache`
- Independent fetches via `Promise.all`; N+1 `Promise.all(items.map(...))` flagged - recommend a batched endpoint
- LCP element rendered eagerly, not behind `<Suspense fallback>`
- `revalidateTag` over full-route `revalidatePath`
- No `useEffect`-fetch in a Client Component when a Server Component parent could fetch and pass props

**TanStack Query:**

- `staleTime` / `gcTime` set; query keys are stable structured arrays, not JSON strings
- Mutation invalidation explicit (`onSuccess: () => queryClient.invalidateQueries(...)`); `useOptimistic` for high-latency mutations
- `useQueries` for parallel fan-out; `prefetchQuery` on hover for likely-next routes

### Step 7 - Core Web Vitals

**LCP:**

- `next/image` with `priority` on the hero; raw `<img>` for above-the-fold flagged; Vite uses `vite-imagetools` or explicit `srcset`/`sizes`/`width`/`height`
- `next/font` for fonts; flag `<link href="fonts.googleapis.com">` (DNS lookup + render-blocking CSS)
- Hero not gated by Suspense, lazy mount, or `loading="lazy"`

**INP:**

- `useTransition` for expensive state updates triggered by input; `useDeferredValue` for filter / search re-renders
- Heavy click handlers offloaded to a worker, network request, or `requestIdleCallback`

**CLS:**

- Reserved dimensions on async slots (skeleton with same `h-`/`w-`); `font-display: swap` (default in `next/font`)
- A/B / banner / modal scripts don't push content; load below the fold or reserve space

### Step 8 - Hydration, Streaming, ISR (Next.js)

_Skipped on Vite-only projects._

- No hydration mismatch sources in render: `Date.now()`, `Math.random()`, `window` / `localStorage` access; browser APIs go inside `useEffect`
- Slow data isolated in `<Suspense fallback>` so the route shell streams first; `loading.tsx` per segment with non-trivial fetches
- ISR / SSG / SSR chosen deliberately: cached `fetch` (default) for stable content, `next.revalidate: N` for periodic refresh, `cache: 'no-store'` / `force-dynamic` only when truly per-request
- `runtime = 'edge'` for low-TTFB handlers without Node APIs; middleware kept thin (no uncached DB / HTTP)

### Step 9 - Observability Hand-off and Report

Confirm presence only (depth belongs to `task-react-review-observability`):

- `web-vitals` reporter wired, RUM SDK active, or Sentry browser SDK with performance enabled on the changed routes
- `instrumentation.ts` exporting OTel (Next.js) when server work is non-trivial
- No `console.log` left in render path of a hot route (if visible in diff)

Gaps -> Low / Recommendation with `[Delegate] -> task-react-review-observability`.

Then use skill: `review-report-writer` with `report_type: review-perf`. Write the report to file; print the confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## React Performance Review Summary

**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Data Layer:** Server Components + `fetch` | TanStack Query | mixed
**Styling:** Tailwind | CSS Modules | CSS-in-JS
**Scope:** Frontend (React)
**Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line]
- **Issue:** [name the React idiom: `"use client"` at layout root, hero `<img>` blocking LCP, missing virtualization on 1k+ rows, context value rebuilt every render, `recharts` eager-imported, hydration mismatch from `Date.now()`, etc.]
- **Impact:** [measured (`LCP 2.8s -> 1.4s`) or estimated (`+120KB gzip on every cold visit to /dashboard`, `~40 re-renders per scroll frame`)]
- **Fix:** [specific React change with code - leaf `"use client"`, `next/dynamic({ ssr: false })`, `useMemo` context value, `@tanstack/react-virtual`, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty sections._

## Recommendations

[Structural items not tied to a single finding - route-level `next/dynamic` for editor pages, split filters context into state + dispatch, add bundle budget to CI, adopt `react-virtual` across list views.]

[**`deep` only:** capacity guidance (virtualization / batched endpoints for large datasets) and a per-route budget plan (LCP / INP / bundle thresholds wired to CI) go here, each prefixed `[deep]`.]

## Next Steps

Each item `[Implement]` (localized) or `[Delegate]` (cross-cutting / build config / load test). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: build] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed React; `Framework`, `Data Layer`, `Styling` recorded
- [ ] Step 3 - `review-precondition-check` ran or parent handle accepted; diff + log read once; performance surface opened (changed routes, components, config, data-fetching sites)
- [ ] Step 4 - `react-hooks-patterns` + `react-component-patterns` consulted; `"use client"` placement, identity-stable props, context memo, list keys / virtualization, inline-component hazard audited
- [ ] Step 5 - bundle deltas sized per new dep; tree-shake-hostile imports flagged; heavy libs gated by `next/dynamic` / `React.lazy`
- [ ] Step 6 - `react-data-fetching` consulted; `fetch` cache intent, Server-vs-Client fetch placement, TanStack `staleTime` / keys / invalidation audited
- [ ] Step 7 - LCP image / fonts, INP `useTransition` / `useDeferredValue`, CLS reservations checked when routes or assets changed
- [ ] Step 8 - hydration sources, Suspense streaming, ISR / SSG / SSR / runtime decisions reviewed (Next.js only; skipped on Vite)
- [ ] Step 9 - observability presence checked or `[Delegate]` added; report written via `review-report-writer`; confirmation line printed
- [ ] Every finding states impact (measured or estimated - never just "this is slow") and cites `file:line`
- [ ] Depth honored: `standard` ran 1-9; `deep` adds capacity + budget plan
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend (omit when no actionable findings)

## Avoid

- State-changing git (`fetch`, `checkout`, `reset`) - the user runs these to protect uncommitted work
- "This is slow" without naming the React idiom (`"use client"` at root, context value churn, eager chart import, missing virtualization)
- Generic frontend advice when a React pattern applies ("use `next/dynamic`", not "lazy load")
- `useMemo` / `useCallback` / `React.memo` as defaults - no-op when props are unstable, costlier than the recompute on primitives
- Approving `"use client"` at the root of a layout with no client-only need
- Approving `dynamic = 'force-dynamic'` on a cacheable route
- Approving raw `<img>` for hero / above-the-fold on Next.js (`next/image` + `priority`)
- Approving CSS-in-JS in a Tailwind / CSS Modules project for "DX" reasons
- Treating high re-render counts as inherently bad - investigate only when a profile or interaction lag implicates them
- `useEffect(() => fetch(...), [])` in a Client Component when a Server Component parent could fetch
- Conflating perf with general / security review - delegate
- **Dual perf+security findings** (untrusted `dangerouslySetInnerHTML`, `eval`, prototype pollution via spread): emit a single `[Delegate] -> task-react-review-security` line in Next Steps only - no Findings-section entry and no parallel security commentary. If the issue has no independent perf cost, it is Next Steps only; if it also has a real perf cost, file that perf cost as its own Finding and still delegate the security half once
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
