---
name: task-react-review-perf
description: "React / Next.js perf review: Core Web Vitals, bundle, hydration, render churn, RSC boundaries, TanStack Query, Suspense, ISR."
agent: react-performance-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, performance, core-web-vitals, bundle, rsc, workflow]
  type: workflow
user-invocable: true
---

# React Performance Review

Stack-specific delegate of `task-code-review-perf` for React / Next.js. It preserves the parent's invocation and diff-resolution contract; its Findings shape is this file's own.

## When to Use

- Reviewing a PR / branch in a Next.js 16 App Router project for perf regressions
- A branch that changes a slow page or interaction (high INP, slow LCP, scroll jank, hydration cost)
- Pre-merge pass on changes touching bundle, data fetching, or rendering boundaries

**Not for:**

- General review (`task-react-review`)
- Security review (`task-react-review-security`)
- Pre-implementation design (`task-react-implement`)

## Severity Rubric

Steady-state user impact, not "how scary the code looks".

| Severity   | Definition                                                                                                                                                                                                                  |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | LCP / INP regression visible to every cold visitor: heavy lib in initial bundle (>50KB gzip, no split), `"use client"` at layout root pulling the tree client-side, hero `<img>` blocking LCP, missing virtualization on 1k+ rows, sync work on input (>200ms INP), hydration mismatch, `force-dynamic` on a cacheable route (without `cacheComponents`; with it, per-request data read outside `<Suspense>`), a nonce CSP added to an app with static routes (Step 8). |
| **Medium** | Degraded p95 / wasted re-renders: context value rebuilt every render with many consumers, identity-unstable props on `React.memo` child, barrel imports defeating tree-shake, `staleTime: 0` on hot query, CSS-in-JS added to a Tailwind project, missing `next/image` on non-LCP images. |
| **Low**    | Allocation / churn quick wins: inline style objects on hot rows, `useMemo` on primitives, `console.log` in render, missing `next/font`, below-the-fold `<iframe>` without `loading="lazy"`. |

`next/image` placement: raw `<img>` on the LCP / hero element is High (blocks LCP); raw `<img>` on non-LCP images, below the fold included (`next/image` lazy-loads by default), is Medium.

Where a defect matches two rows, take the higher. A loaded atomic's `Critical` or `Blocker` files as High.

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
| `--base <branch>` / `deep`         | Forwarded from the parent or typed directly; `--base` goes to `review-precondition-check`, `deep` sets the Depth level |
| `/task-react-review-perf <branch>` | Review `<branch>` vs its base (3-dot diff)                           |
| `/task-react-review-perf pr-<N>`   | Review PR head in local branch `pr-<N>` (user runs the fetch first)  |

`task-react-review` spawns this workflow as a subagent and passes the pre-confirmed stack and framework (`Next.js <version>` with its router suffix), the React version and the below-floor line or `none`, `base_ref` / `head_ref`, the pre-read diff, name-status list and commit log, and the depth level; Steps 2-3 consume those instead of re-running, and Step 9 returns findings instead of writing. `task-code-review-perf` does **not** spawn a subagent - it forwards the invocation arguments and stops, so that path is a normal standalone run that owns its own report. Step 1 always runs.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. In subagent mode skip it: accept the parent's framework (router suffix included), React version and below-floor line or `none`, and skip the scope stop and floor check below - the other records below still run. `stack-detect` keys the primary stack on the root manifest, so in a polyglot repo (a Next.js app under `apps/<name>` beside a Rails root) it may appear only under `Additional`; that counts when the diff or request sits inside that package - confirm against the package's own `package.json`, scope the run to it, and name the package in the Summary's `Notes`.

With no `next` dependency, print `task-react-review-perf covers Next.js App Router projects only; <project framework> is out of scope - use core's /task-code-review-perf for a generic review.` and stop. Record the React and `next` versions and the TypeScript and TanStack Query majors from `package.json` - `stack-detect` emits no versions; on an SWR project the TanStack major is `n/a (SWR)`. When the declared `next` is below 16.3 or `react` below 19, put `<package> <declared> is below the plugin floor (Next.js 16.3, React 19); output targets Next.js 16.3 and React 19 - upgrade first.` in the Summary's `Notes` (`<package>` is `Next.js` or `React`; both below is one line, `Next.js 15.5 and React 18.3 are below the plugin floor ...`) and continue. `<declared>` is the version the lockfile resolves for `next` / `react`, else the lower bound of the `package.json` range (`^16.1.0` -> `16.1.0`). Record the full version, not the major. Step 6's option names are TanStack v5 (`gcTime`, not v4's `cacheTime`), so on v4 read them as their v4 equivalents rather than filing a finding. Record from `next.config.*` whether `reactCompiler` is set (`true` or an object) and whether `cacheComponents: true` is, top-level or as a leftover `experimental.*` key (Next still applies it, with a moved-key warning): with the compiler on, Step 4's identity and memoization checks apply only to components that opt out (`"use no memo"`) or that the compiler skips, and under `compilationMode: 'annotation'` only `"use memo"` components are compiled, so the checks apply to every other component; Steps 6 and 8 branch on `cacheComponents`.

Record for the Summary block:

- `Framework:` `Next.js <version>`, suffixed ` (Pages Router)` when routes exist only under `pages/` or ` (App + Pages Router)` when both `app/` and `pages/` hold routes (detection only - guidance stays App Router)
- `Data Layer:` Server Components + `fetch` | TanStack Query | SWR | mixed | not detected
- `Styling:` Tailwind | CSS Modules | CSS-in-JS (`styled-components` / `emotion`) | mixed | not detected

### Step 3 - Resolve Diff and Read Surface

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-perf`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). Surface a fail-fast verbatim, write no report, and stop.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits on <head_short_name> since prior perf review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the report write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse.

**Subagent mode** = a parent passed `base_ref` / `head_ref` plus the pre-read diff, name-status list and log (also when the parent runs this lens inline): skip the precondition, the round gate and the diff reads; the surface read still runs.

Open the files that govern rendering, bundle, and data fetching so impact estimates ground in real code:

- Changed `app/**/{page,layout,loading,error}.tsx` and `route.ts` (note `"use client"`), Server Action sites (`"use server"`), `proxy.ts` (or a retained `middleware.ts`), `next.config.*` (`images`, `cacheComponents`, `reactCompiler`, `experimental`), `package.json` deps, Suspense boundaries
- TanStack Query / SWR call sites, list components (rows + virtualization), image / font usage, and client-side fan-out (`Promise.all(items.map(fetch))` per row)

If a small diff ripples through unchanged code (new caller of a heavy library, new Client Component importing a barrel), read the unchanged file too. Cite real `file:line` in every finding.

### Step 4 - Render and Re-Render Hotspots

Use skill: `react-hooks-patterns` - it owns `useMemo` / `useCallback` discipline and dependency identity (`UnstableDepIdentity`, `CallbackIdentityChurn`). Use skill: `react-component-patterns` for component boundaries. `React.memo` effectiveness and missing list keys are `frontend-performance`'s Render Performance rules (loaded in Step 5); the stable-id-over-`index` check and the React checks below are this step's. Use skill: `react-state-patterns` for the context-splitting rule below (it qualifies the advice: splitting helps only when the setters are stable). Workflow-specific verifications:

- `"use client"` at the leaf, not the layout root - root placement pulls the whole subtree client-side and defeats RSC
- Identity-stable props on `React.memo` children: inline `{...}`, `[...]`, `() => ...` makes `memo` a no-op
- Context value memoized; high-fan-out contexts split into state + dispatch
- No `useEffect` for derived state (compute in render) or event handling (call from handler)
- List `key` is a stable id, not `index`, for reorderable / filterable lists
- Virtualize when simple rows > 1000 or complex rows > 100 (`@tanstack/react-virtual`, `react-window`)
- Heavy sync work in render moved to `useMemo` with real deps, or precomputed; `useState` initializer lazy when expensive
- Components defined at module scope, not inside parent render body
- `useMemo` / `useCallback` only when the value gates `React.memo` / `useEffect` deps, or profiling showed the computation slow - not on primitives, and not on an unmeasured guess

```tsx
import { memo } from "react";

type Item = { id: string; name: string };
type RowProps = { item: Item; config: { dense: boolean } };

// BAD: Row is a new component type every render, so every row unmounts and
// remounts (DOM rebuilt, row state lost); memo cannot help, and the fresh
// `config` object would defeat it anyway.
function BadList({ items }: { items: Item[] }) {
  const Row = memo(({ item, config }: RowProps) => (
    <div className={config.dense ? "py-0.5" : "py-2"}>{item.name}</div>
  ));
  return items.map((i) => <Row key={i.id} item={i} config={{ dense: true }} />);
}

// GOOD: Row hoisted to module scope and the config object stable, so memo skips
// re-rendering every unchanged row.
const ROW_CONFIG = { dense: true };
const Row = memo(({ item, config }: RowProps) => (
  <div className={config.dense ? "py-0.5" : "py-2"}>{item.name}</div>
));
function GoodList({ items }: { items: Item[] }) {
  return items.map((i) => <Row key={i.id} item={i} config={ROW_CONFIG} />);
}
```

### Step 5 - Bundle Size and Code Splitting

Use skill: `frontend-performance` - it owns bundle budgets, tree-shaking and Core Web Vitals, and is the only loaded skill that does. Use skill: `react-nextjs-patterns` for `next/image` conventions. `next/dynamic` and `next/font` are not in that skill - `frontend-performance` owns fonts, and the dynamic-import form is given below.

- Every new `dependencies` entry sized - `next build` no longer prints route sizes, so measure with `next experimental-analyze` (Turbopack, the default) or `@next/bundle-analyzer` (`--webpack` builds only); flag >50KB gzip not lazy-loaded
- Charting (`recharts`, `chart.js`), rich text (`tiptap`, `slate`, `quill`), maps (`mapbox-gl`, `leaflet`), date pickers rendered only on interaction, or mounted when scrolled into view, go behind `dynamic(() => import('./Chart'))` called from a Client Component (in a Server Component it does not code-split), so their chunk loads when first rendered; a component rendered on the initial pass, above or below the fold, stays in the cold load even when split, so size it as initial bundle. `ssr: false` removes the component from the server HTML - reserve it for components that cannot render on the server, with the slot's size reserved
- `dynamic(..., { ssr: false })` in a Server Component file (no `"use client"`) fails `next build`: High, whatever the chart weighs, with a Client Component wrapper as the fix. A round-2 "fix" that moves a heavy import behind it is this finding, not an addressed one
- Tree-shake-friendly imports: `import { format } from 'date-fns'`, `import isEqual from 'lodash/isEqual'`. A CommonJS package (`lodash`, `moment`) does not tree-shake at all, so any import of its root pulls the whole library. In an ESM package flag a namespace import (`import * as X`) only when `X` is used dynamically (`X[name]`, spread, passed as a value) - static `X.member` access tree-shakes like a named import
- Barrel `index.ts` imports on the hot path replaced with direct paths
- `moment` -> `date-fns` / `dayjs` / `Intl`; CSS-in-JS flagged when added to a zero-runtime project

Impact phrasing: "+<N>KB gzip on every cold visit to <route>", not "the bundle got bigger".

### Step 6 - Data Fetching and Caching

Use skill: `react-data-fetching`. Workflow-specific verifications:

**Next.js Server Components:**

- With `cacheComponents` set: cacheable data sits in a `"use cache"` scope with an explicit `cacheLife` (and `cacheTag` when a write invalidates it), runtime data inside `<Suspense>`; a segment `dynamic` / `revalidate` / `fetchCache` / `dynamicParams` export errors, and a new `unstable_cache` is legacy (`"use cache"` replaces it). Without it: every `fetch` declares intent - `cache: 'force-cache'` / `next: { revalidate, tags }` for cacheable data, `cache: 'no-store'` (or a Request-time API) for per-request data on a route that would otherwise prerender at build, and non-fetch IO goes in `unstable_cache`
- Independent fetches via `Promise.all`, in Server Components and Route Handlers alike; N+1 `Promise.all(items.map(...))` flagged on any stack - recommend a batched query or endpoint
- Outbound HTTP awaited on the request path (a Server Action or page waiting on a third-party API) is TTFB / INP cost the user waits on. `after()` from `next/server` is for work whose result the response does not show and whose failure the caller need not see: logging, analytics, cache warming, non-critical notifications. A call whose result the user sees (a label shown on the page) or whose failure must reach the caller so it retries (a payment, refund, or any webhook side effect - the sender redelivers only on a non-2xx) stays on the request path; `after()` failures are never reported back. Medium unless a measurement shows it on the LCP or INP path
- LCP element rendered eagerly, not behind `<Suspense fallback>`
- Tag invalidation over full-route `revalidatePath`: `updateTag(tag)` in a Server Action that must show the user their own write, `revalidateTag(tag, 'max')` for stale-while-revalidate, `revalidateTag(tag, { expire: 0 })` from a Route Handler or webhook needing immediate expiry - never the one-argument form
- No `useEffect`-fetch in a Client Component when a Server Component parent could fetch and pass props

**TanStack Query:**

- `staleTime` / `gcTime` set; query keys are stable structured arrays, not JSON strings
- Mutation invalidation explicit (`onSuccess: () => queryClient.invalidateQueries(...)`); high-latency mutations use TanStack's `onMutate` + snapshot + `onError` rollback flow, not `useOptimistic` (which only holds its value inside an action or transition)
- `useQueries` for parallel fan-out; `prefetchQuery` on hover for likely-next routes

**SWR:** SWR has no `staleTime` - freshness is `revalidateIfStale` / `revalidateOnFocus` / `revalidateOnReconnect` (or `useSWRImmutable`), and `dedupingInterval` only collapses requests inside its window; keys are deterministic (a string, an array, or a function returning `null` to pause), and a write revalidates the affected key - `useSWRMutation` does by default, otherwise an explicit `mutate(key)`.

### Step 7 - Core Web Vitals

Use skill: `frontend-performance` for the metric thresholds and the shared rating table; this step adds only the React/Next bindings. TTFB and LCP resource load delay dominate LCP on most routes, and third-party script weight dominates main-thread time (INP) - size both before micro-optimising render.

**LCP:**

- `next/image` on the hero with `loading="eager"` (optionally plus `fetchPriority="high"`, which alone still renders `loading="lazy"`) or `preload` (only when one image is the LCP element at every viewport; `priority` is deprecated); raw `<img>` for above-the-fold flagged. `images` config: `qualities` defaults to `[75]` (a `quality` prop outside the list is coerced) and `minimumCacheTTL` to 4h - lowering it multiplies optimizer work
- `next/font` for fonts; flag `<link href="fonts.googleapis.com">` (DNS lookup + render-blocking CSS)
- Hero not gated by Suspense, lazy mount, or `loading="lazy"`

**INP:**

- `useTransition` for expensive state updates triggered by input; `useDeferredValue` for filter / search re-renders
- Heavy click handlers broken up with `scheduler.yield()` (or `setTimeout(fn, 0)`), or moved to a worker - `requestIdleCallback` only queues work for idle time and cannot break up a task already running

**CLS:**

- Reserved dimensions on async slots (skeleton with same `h-`/`w-`); `font-display: swap` (default in `next/font`)
- A/B / banner / modal scripts don't push content; load below the fold or reserve space

### Step 8 - Hydration, Streaming, ISR

- No hydration mismatch sources in render: `Date.now()`, `Math.random()`, `window` / `localStorage` access; browser APIs go inside `useEffect`
- Slow data isolated in `<Suspense fallback>` so the route shell streams first; `loading.tsx` per segment with non-trivial fetches
- Rendering mode chosen deliberately: with `cacheComponents`, stable content in a `"use cache"` scope with `cacheLife` and per-request data inside `<Suspense>`; without it, stable content on a dynamic route needs `cache: 'force-cache'` or `next: { revalidate: N }`, and `force-dynamic` only when truly per-request
- `proxy.ts` (or a retained `middleware.ts`) kept thin - no uncached DB / HTTP on the request path (`fetch` cache options do nothing there), and a `matcher` so it skips static assets (with none it runs on every request, `_next/static` included). Flag a new `runtime = 'edge'` export for removal: the Edge runtime is deprecated and `cacheComponents` requires Node
- A nonce CSP requires every page to render dynamically: a page that still prerenders carries no nonce and the CSP blocks its scripts - a broken page, not only a slower one, filed High here. Without `cacheComponents`, opt each page in with `await connection()`; with it, a nonce CSP cannot work (the prerendered shell's scripts carry no nonce) - move to hash-based `experimental.sri` or drop nonces. The cost of nonces: static optimization and ISR off, CDN caching off; `experimental.sri` keeps pages static

### Step 9 - Observability Hand-off and Report

Confirm presence only (depth belongs to `task-react-review-observability`):

- `web-vitals` reporter wired, RUM SDK active, or Sentry browser SDK with performance enabled on the changed routes
- `instrumentation.ts` exporting OTel when server work is non-trivial
- No `console.log` left in render path of a hot route (if visible in diff)

Gaps are not findings: they become a `[Delegate] -> task-react-review-observability` Next Step. When no RUM or web-vitals reporter exists, or the one present omits the metric the complaint is about (INP for an interaction complaint), that Next Step goes **first**: the impact estimates it would measure are unmeasured until it lands.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, and fill the Summary's `Findings verified` line from its tally. Findings carried from a prior round are not re-verified. Subagent runs skip this - the parent verifies the merged set once.

**Subagent mode** (see Step 3): return this workflow's Output Format document - Summary, Findings, Recommendations, Next Steps, and at `deep` the Capacity and Budget Plan - and write nothing; the parent owns the report and merges the Findings and Next Steps, carrying the non-finding sections into its own `## Scope Sections`. Each finding must already carry its `Label`; the parent does not re-derive labels.

**Reconcile (standalone, round 2+).** Re-project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: one `## High-Impact Findings` section and, per prior finding in every tier, a `### [<Label>] <file:line>` heading - the label from its `Label` slot, the bare `file:line` prefix of its `Location` slot (the first when it lists several), then each annotation as its own `_(...)_` group: `_(pre-existing)_` kept, verify's combined `_(pre-existing; newly reachable via <path>)_` written as two groups `_(pre-existing)_ _(newly reachable via <path>)_` (reconcile matches `_(pre-existing)_` exactly), a prior `_(carried from round <N>)_` re-emitted, and an `_(unverified: <reason>)_` finding on a file the diff does not touch also projected with `_(pre-existing)_` (reconcile would otherwise mark it `Addressed`) - followed by `- Issue: <its Issue text>`. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status list and `head_sha`, and render its table and tally under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows carry into the tier the prior report filed them under, at their prior label, with the prior annotation kept and `_(carried from round <N>)_` on the `Location` line (`<N>` = the round the finding first appeared: the prior's own carried marker when present, else the prior report's `round`); a carried finding this round's own pass re-derives publishes once, at the higher of the two labels, keeping the fresh verify annotation plus `_(carried from round <N>)_`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

Then Use skill: `review-report-writer` with `report_type: review-perf` and every field it requires: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` and `round` / `prior_head_sha` from the Step 3 round gate, `scope: +perf`, `depth` as resolved, `stack: typescript-nextjs`, `mode: full`, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present. Print the confirmation line after the report body.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## React Performance Review Summary

- **Stack Detected:** React <version> / TypeScript <version>
- **Framework:** Next.js <version>{ <Step 2 router suffix>}
- **Data Layer:** Server Components + `fetch` | TanStack Query | SWR | mixed | not detected
- **Styling:** Tailwind | CSS Modules | CSS-in-JS | mixed | not detected
- **Scope:** Frontend (React)
- **Depth:** standard | deep
- **Round:** <N> _(include from round 2 onward)_
- **Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]
- **Notes:** <any note a step required - the Step 2 below-floor line, the package the run was scoped to, React Compiler on (annotation mode when set), Cache Components on, a React or TanStack major that changed how a check was read; omit when none>
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_. _In subagent mode write exactly `not run (subagent; parent verifies the merged set)`._

## Findings

Labels: High -> `[Must]`; Medium / Low -> `[Recommend]` (the verify pass's `Label` column overrides when it ran). Repeat the block per finding, numbered sequentially across tiers - number the `Location` line, and indent every other field's `- ` bullet to the width of that number's marker (three spaces for `1. `, four for `10. `) so the block renders as one list item.

### High Impact

1. **Location:** [file:line, comma-separated when one root cause spans several; carry the verify pass's `Annotation` when it is not `-`: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`; a carried finding appends `_(carried from round <N>)_`]
   - **Label:** [Must | Recommend]
   - **Issue:** [name the React idiom: `"use client"` at layout root, hero `<img>` blocking LCP, missing virtualization on 1k+ rows, context value rebuilt every render, `recharts` eager-imported, hydration mismatch from `Date.now()`, etc.]
   - **Impact:** [measured (`LCP 2.8s -> 1.4s`) or estimated (`+120KB gzip on every cold visit to /dashboard`, `~40 re-renders per scroll frame`)]
   - **Fix:** [specific React change with code - leaf `"use client"`, `dynamic(() => import(...))` for an interaction-only component (`{ ssr: false }` only when it cannot render on the server), `useMemo` context value, `@tanstack/react-virtual`, etc.] Tag it `(quick win)` or `(structural)`.

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty impact sections. When every section is empty, `## Findings` still appears and contains `No performance issues found.`, followed by any `out of lens:` lines._

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Recommendations

[Structural items not tied to a single finding - route-level `next/dynamic` for editor pages, split filters context into state + dispatch, add bundle budget to CI, adopt `@tanstack/react-virtual` across list views.]

## Capacity and Budget Plan _(`deep` only - omit at `standard`)_

Capacity guidance (virtualization, batched endpoints, pagination for large datasets) and a per-route budget plan (LCP / INP / bundle thresholds wired to CI). This is its own section, not a Recommendations bullet, so the parent preserves it when merging. A defect in the changed code files as a Finding even when its fix is capacity work (an unpaginated new endpoint); this section plans what no single finding carries.

## Next Steps

Each item `[Implement]` (localized) or `[Delegate]` (cross-cutting / build config / load test). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: build] - [one-line action]
3. **[Delegate]** -> <workflow> - [the out-of-lens defects or observability gaps, named]
4. **[Implement]** [Recommend] file:line - [one-line action]

_Omit only when there are no findings and no delegate lines._
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - Next.js confirmed, or the out-of-scope line printed and the run stopped (subagent: parent's decision accepted); below-floor line in `Notes` when applicable; `Framework` (router suffix included), `Data Layer`, `Styling`, React and `next` versions, TanStack Query major, React Compiler (annotation mode and a leftover `experimental.*` key included) and `cacheComponents` recorded (write `not detected` for any the project does not reveal)
- [ ] Step 3 - `review-precondition-check` ran with `report_type: review-perf` (or subagent mode); round decided from the handle before the diff was read, or the no-op line printed; diff, name-status and log read once; performance surface opened (changed routes, components, config, data-fetching sites)
- [ ] Step 4 - `react-hooks-patterns`, `react-component-patterns` and `react-state-patterns` consulted; `"use client"` placement, identity-stable props, context memo, list keys / virtualization, inline-component hazard audited
- [ ] Step 5 - `frontend-performance` and `react-nextjs-patterns` consulted; bundle deltas sized per new dep; tree-shake-hostile imports flagged; heavy libs gated by `next/dynamic`
- [ ] Step 6 - `react-data-fetching` consulted; caching read against `cacheComponents` (`"use cache"` scopes, or `fetch` cache intent), tag invalidation form, `after()` kept to work the response neither shows nor must report failing, Server-vs-Client fetch placement, TanStack `staleTime` / keys / invalidation audited
- [ ] Step 7 - `frontend-performance` consulted; LCP image / fonts, third-party script weight and TTFB, INP `useTransition` / `useDeferredValue`, CLS reservations checked
- [ ] Step 8 - hydration sources, Suspense streaming, rendering-mode decisions, `proxy.ts` (or retained `middleware.ts`) weight and `matcher`, and the nonce CSP's dynamic-rendering requirement (per `cacheComponents`) and cost reviewed
- [ ] Step 9 - observability presence checked or `[Delegate]` added; standalone: findings verified with `Label` and `Annotation` carried, tally in Summary, prior round reconciled through the projection when round > 1, report written via `review-report-writer` with `branch` = `head_short_name`, confirmation printed; subagent: Output Format document returned, nothing written
- [ ] Every finding states impact (measured or estimated - never just "this is slow") and cites `file:line`
- [ ] Depth honored: `standard` ran 1-9; `deep` additionally produced the Capacity and Budget Plan section
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend (omit when no actionable findings)

## Avoid

- State-changing git (`fetch`, `checkout`, `reset`) - the user runs these to protect uncommitted work
- "This is slow" without naming the React idiom (`"use client"` at root, context value churn, eager chart import, missing virtualization)
- Generic frontend advice when a React pattern applies ("use `next/dynamic`", not "lazy load")
- `useMemo` / `useCallback` / `React.memo` as defaults - no-op when props are unstable, costlier than the recompute on primitives
- Approving `"use client"` at the root of a layout with no client-only need
- Approving `dynamic = 'force-dynamic'` on a cacheable route
- Approving raw `<img>` for hero / above-the-fold (`next/image` with `loading="eager"` or `preload`)
- Approving CSS-in-JS in a Tailwind / CSS Modules project for "DX" reasons
- Treating high re-render counts as inherently bad - investigate only when a profile or interaction lag implicates them
- `useEffect(() => fetch(...), [])` in a Client Component when a Server Component parent could fetch
- Conflating perf with general / security review - delegate
- **Out-of-lens defects** (security: untrusted `dangerouslySetInnerHTML`, `eval`; correctness: a crash or logic bug spotted en route): one `[Delegate] -> <workflow>` line per target workflow, not per defect - name the defects on that one line. Put it in Next Steps, and when the defect would break the build or expose data add a single `out of lens: <one line>` at the end of `## Findings` so a reader of the findings alone still sees it. If the issue also has a real perf cost, file that cost as its own Finding and still delegate the other half once. A schema or migration defect (a `NOT NULL` column on a large table) delegates to `task-react-review`. The one in-lens build break is Step 5's `ssr: false` in a Server Component, filed High because it is the perf fix that cannot ship
- Estimating an impact the diff cannot support - say what would measure it instead
