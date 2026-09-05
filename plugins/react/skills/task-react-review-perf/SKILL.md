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

Stack-specific delegate of `task-code-review-perf` for React / Next.js / Vite. It preserves the parent's invocation and diff-resolution contract; its Findings shape is this file's own.

## When to Use

- Reviewing a Next.js or Vite + React PR / branch for perf regressions
- Investigating a slow page or interaction (high INP, slow LCP, scroll jank, hydration cost)
- Pre-merge pass on changes touching bundle, data fetching, or rendering boundaries
- Quarterly Core Web Vitals / bundle sweep against RUM-flagged routes

**Not for:**

- General review (`task-react-review`)
- Security review (`task-react-review-security`)
- Pre-implementation design (`task-react-implement`)

## Severity Rubric

Steady-state user impact, not "how scary the code looks".

| Severity   | Definition                                                                                                                                                                                                                  |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High**   | LCP / INP regression visible to every cold visitor: heavy lib in initial bundle (>50KB gzip, no split), `"use client"` at layout root pulling the tree client-side, hero `<img>` blocking LCP, missing virtualization on 1k+ rows, sync work on input (>200ms INP), hydration mismatch, `force-dynamic` on cacheable route. |
| **Medium** | Degraded p95 / wasted re-renders: context value rebuilt every render with many consumers, identity-unstable props on `React.memo` child, barrel imports defeating tree-shake, `staleTime: 0` on hot query, CSS-in-JS added to a Tailwind project, missing `next/image` on non-LCP images. |
| **Low**    | Allocation / churn quick wins: inline style objects on hot rows, `useMemo` on primitives, `console.log` in render, missing `next/font`, missing `loading="lazy"` below-the-fold. |

`next/image` placement: raw `<img>` on the LCP / hero element is High (blocks LCP); raw `<img>` on non-LCP images is Medium.

Where a defect matches two rows, take the higher. On Next, a below-the-fold raw `<img>` is the Medium `next/image` row only - `next/image` lazy-loads by default, so the Low `loading="lazy"` row applies to plain `<img>` outside Next.

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

`task-react-review` spawns this workflow as a subagent and passes the pre-confirmed stack and framework, `base_ref` / `head_ref`, the pre-read diff and commit log, and the depth level; Steps 2-3 consume those instead of re-running, and Step 9 returns findings instead of writing. `task-code-review-perf` does **not** spawn a subagent - it forwards the invocation arguments and stops, so that path is a normal standalone run that owns its own report. Step 1 always runs.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. If the parent already detected React, accept the handoff. If not React, stop and name the detected stack so the user can invoke that stack's perf workflow - do not route back to `/task-code-review-perf`, which is what dispatched here. Record the React major and the TanStack Query major by reading `package.json` - `stack-detect` emits no versions. `useTransition` and `useDeferredValue` (Step 7) exist from React 18; Step 6's option names are TanStack v5 (`gcTime`, not v4's `cacheTime`), so on v4 read them as their v4 equivalents rather than filing a finding. Record the TanStack Query major too - Step 6's option names are v5 (`gcTime`, not v4's `cacheTime`).

Record for the Summary block:

- `Framework:` Next.js (App Router) | Next.js (Pages Router) | Vite + React Router
- `Data Layer:` Server Components + `fetch` | TanStack Query | SWR | mixed
- `Styling:` Tailwind | CSS Modules | CSS-in-JS (`styled-components` / `emotion`)

Heuristics: `next.config.*` -> Next.js (App Router unless `pages/` without `app/`); `vite.config.*` without `next` -> Vite; both present -> ask the user.

### Step 3 - Resolve Diff and Read Surface

Use skill: `review-precondition-check`. If it fails fast (dirty tree, trunk head, missing ref, declined approval gate) surface the message verbatim, write no report, and stop. On approval, read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once; reuse. Capture `head_sha = git rev-parse <head_ref>` and `base_sha = git rev-parse <base_ref>` for the report checkpoint. Subagent mode skips the precondition and diff re-read only - the surface read below is never skipped.

Open the files that govern rendering, bundle, and data fetching so impact estimates ground in real code:

- **Next.js App Router:** changed `app/**/{page,layout,loading,error}.tsx` and `route.ts` (note `"use client"`), Server Action sites (`"use server"`), `next.config.*` (`images`, `experimental`), `package.json` deps, Suspense boundaries
- **Vite + React Router:** changed components (all client), `vite.config.*` chunks, `src/router.tsx` lazy routes / Suspense, `QueryClient` config
- Both: TanStack Query call sites, list components (rows + virtualization), image / font usage

If a small diff ripples through unchanged code (new caller of a heavy library, new Client Component importing a barrel), read the unchanged file too. Cite real `file:line` in every finding.

### Step 4 - Render and Re-Render Hotspots

Use skill: `react-hooks-patterns` - it owns `useMemo` / `useCallback` discipline and dependency identity (`UnstableDepIdentity`, `CallbackIdentityChurn`). Use skill: `react-component-patterns` for component boundaries. `React.memo` effectiveness and list `key` stability are scored in this step - no loaded atomic owns either, so state the rule in the finding rather than citing one. Use skill: `react-state-patterns` for the context-splitting rule below (it qualifies the advice: splitting helps only when the setters are stable). Workflow-specific verifications:

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

// BAD: Row is redeclared every render, so memo could never help even if applied,
// and the fresh `config` object would defeat it anyway.
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

Use skill: `frontend-performance` - it owns bundle budgets, tree-shaking and Core Web Vitals, and is the only loaded skill that does. Use skill: `react-nextjs-patterns` (Next.js) for `next/image` conventions. `next/dynamic` and `next/font` are not in that skill - `frontend-performance` owns fonts, and the dynamic-import form is given below.

- Every new `dependencies` entry sized; flag >50KB gzip not lazy-loaded
- Charting (`recharts`, `chart.js`), rich text (`tiptap`, `slate`, `quill`), maps (`mapbox-gl`, `leaflet`), date pickers behind `dynamic(() => import('./Chart'), { ssr: false })` from `next/dynamic` (Next) or `lazy()` + `<Suspense>` (Vite) - even when the page uses the chart, the LCP impact is the same. `ssr: false` is rejected inside a Server Component, so the `dynamic()` call must sit in a Client Component
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
- Mutation invalidation explicit (`onSuccess: () => queryClient.invalidateQueries(...)`); high-latency mutations use TanStack's `onMutate` + snapshot + `onError` rollback flow, not `useOptimistic` (which only holds its value inside an action or transition)
- `useQueries` for parallel fan-out; `prefetchQuery` on hover for likely-next routes

**SWR:** the same three checks map onto `dedupingInterval` (for `staleTime`), a stable key array or function, and an explicit `mutate` after a write; see `react-data-fetching` for the mapping.

### Step 7 - Core Web Vitals

Use skill: `frontend-performance` for the metric thresholds and the shared rating table; this step adds only the React/Next bindings. Third-party script weight and TTFB are the dominant LCP contributors on most routes - size them before micro-optimising render.

**LCP:**

- `next/image` with `priority` on the hero; raw `<img>` for above-the-fold flagged; Vite uses `vite-imagetools` or explicit `srcset`/`sizes`/`width`/`height`
- `next/font` for fonts; flag `<link href="fonts.googleapis.com">` (DNS lookup + render-blocking CSS)
- Hero not gated by Suspense, lazy mount, or `loading="lazy"`

**INP:**

- `useTransition` for expensive state updates triggered by input; `useDeferredValue` for filter / search re-renders
- Heavy click handlers broken up with `scheduler.yield()` (or `setTimeout(fn, 0)`), or moved to a worker - `requestIdleCallback` only queues work for idle time and cannot break up a task already running

**CLS:**

- Reserved dimensions on async slots (skeleton with same `h-`/`w-`); `font-display: swap` (default in `next/font`)
- A/B / banner / modal scripts don't push content; load below the fold or reserve space

### Step 8 - Hydration, Streaming, ISR (Next.js)

_Skipped on Vite. On the Pages Router run the hydration-mismatch and rendering-mode checks (they apply to `getServerSideProps` / `getStaticProps` + `revalidate` and to Edge API routes via `export const config = { runtime: 'edge' }`), and skip only the App Router segment mechanics - `loading.tsx` and segment Suspense._

- No hydration mismatch sources in render: `Date.now()`, `Math.random()`, `window` / `localStorage` access; browser APIs go inside `useEffect`
- Slow data isolated in `<Suspense fallback>` so the route shell streams first; `loading.tsx` per segment with non-trivial fetches
- ISR / SSG / SSR chosen deliberately: on Next 15 `fetch` is **uncached by default**, so stable content needs an explicit `cache: 'force-cache'` or `next: { revalidate: N }`; `force-dynamic` only when truly per-request
- `runtime = 'edge'` for low-TTFB handlers without Node APIs; middleware kept thin (no uncached DB / HTTP)

### Step 9 - Observability Hand-off and Report

Confirm presence only (depth belongs to `task-react-review-observability`):

- `web-vitals` reporter wired, RUM SDK active, or Sentry browser SDK with performance enabled on the changed routes
- `instrumentation.ts` exporting OTel (Next.js) when server work is non-trivial
- No `console.log` left in render path of a hot route (if visible in diff)

Gaps -> a `## Recommendations` entry with `[Delegate] -> task-react-review-observability`. When no RUM or web-vitals reporter exists at all, that recommendation goes **first**: every impact estimate in this report is unmeasured until it lands.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary's `Findings verified` slot. Subagent runs skip this - the parent verifies the merged set once.

**Subagent mode:** return this workflow's Output Format document - Summary, Findings, Recommendations, Next Steps, and at `deep` the Capacity and Budget Plan - and write nothing; the parent owns the report and merges the Findings and Next Steps, carrying the non-finding sections into its own `## Scope Sections`. Each finding must already carry its `Label`; the parent does not re-derive labels.

**Round gate (standalone only).** Run this immediately after Step 3 resolves the refs, before reading any surface - a no-op exit should cost one `git rev-parse`, not a whole review. Resolve `<branch>` first, exactly as the writer call below does: the head's short name, or the handle's `current_branch` when `head_ref` is the literal `HEAD`. The prior-report key is `review-perf-<branch>.md` with the writer's filename sanitization applied (`/` and any character outside `[A-Za-z0-9_-]` replaced, runs collapsed, ends stripped), so a `feature/x` branch looks up `review-perf-feature-x.md`. The `prior_checkpoint` in the precondition handle names the **core** `review-<branch>.md` and is a different report - ignore it. If that file exists with valid frontmatter and its `head_sha` equals the current head, and this run adds no depth, print `No new commits on <branch> since prior perf review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Treat missing or invalid frontmatter as round 1 and overwrite.

**Reconcile (standalone, round 2+).** When a valid prior report exists and this is a diff-based run, Use skill: `review-prior-findings-reconcile`. It parses a `## High-Impact Findings` section containing one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, which is not this workflow's report shape, so **re-project the prior report first**: emit that exact section heading, then per prior finding a `### [<Label>] <file:line>` heading taking the label from its `Label` slot and the location from its `Location` slot, followed by `- Issue: <its Issue text>` (reconcile reads that line as the finding's summary and cannot match without it). Pass the projection as `prior_report` along with the diff, the `git diff --name-status <base>...<head>` list from Step 3, and `head_sha`. Put the returned table under `## Prior Round Reconciliation`. Carry its `Still open` and `Needs re-check` rows into this round's Findings, in the section the prior report filed them under (the table returns a label, not a bucket - re-read the prior report for the bucket), with `(open since round <N>)` appended to the `Location` line and any `_(pre-existing)_` annotation preserved, since next round's reconcile keys on it. Map any legacy label the table preserved (`[Blocker]`, `[High]`, `[Suggestion]`, `[Question]`, `[Nitpick]`) into `[Must]` or `[Recommend]` before publishing anything outside the reconciliation table itself, which keeps them verbatim. Skip reconciliation entirely when there is no diff (audit mode or a whole-app sweep) and say so in the Summary.

Then Use skill: `review-report-writer` with `report_type: review-perf` and every required field: `report_body`, `branch`, `base_ref` / `head_ref` from the precondition handle - when the handle's `head_ref` is the literal `HEAD` (no-argument mode), pass its `current_branch` instead, or the writer produces a `-HEAD.md` file the next round's lookup never finds, `base_sha` / `head_sha` from Step 3, `scope: +perf`, `depth` as resolved, `stack: typescript-nextjs` (Vite: `typescript-react`), and `mode: full`, `round: 1` - unless `review-perf-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself). Write the report; print the confirmation line after the report body.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## React Performance Review Summary

- **Stack Detected:** React <version> / TypeScript <version>
- **Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
- **Data Layer:** Server Components + `fetch` | TanStack Query | SWR | mixed
- **Styling:** Tailwind | CSS Modules | CSS-in-JS | not detected
- **Scope:** Frontend (React)
- **Depth:** standard | deep
- **Round:** <N> _(include from round 2 onward)_
- **Overall:** Clean | Issues Found - [count by impact: High/Medium/Low]
- **Notes:** <any note a step required - a React or TanStack major that changed how a check was read, a reconciliation skipped for want of a diff; omit when none>
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_; <U> of these unverified _(that clause only when a surviving row is unverified)_. _In subagent mode write exactly `not run (subagent; parent verifies the merged set)`._

## Findings

Labels: High -> `[Must]`; Medium / Low -> `[Recommend]` (the verify pass's `Label` column overrides when it ran). Repeat the block per finding, numbered sequentially across tiers - number the `Location` line, and indent every other field's `- ` bullet to the width of that number's marker (three spaces for `1. `, four for `10. `) so the block renders as one list item.

### High Impact

1. **Location:** [file:line] [carry the verify pass's annotation when it set one: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `(unverified: <reason>)`]
   - **Label:** [Must | Recommend]
   - **Issue:** [name the React idiom: `"use client"` at layout root, hero `<img>` blocking LCP, missing virtualization on 1k+ rows, context value rebuilt every render, `recharts` eager-imported, hydration mismatch from `Date.now()`, etc.]
   - **Impact:** [measured (`LCP 2.8s -> 1.4s`) or estimated (`+120KB gzip on every cold visit to /dashboard`, `~40 re-renders per scroll frame`)]
   - **Fix:** [specific React change with code - leaf `"use client"`, `dynamic(() => import(...), { ssr: false })` from a Client Component, `useMemo` context value, `@tanstack/react-virtual`, etc.] Tag it `(quick win)` or `(structural)`.

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit empty impact sections. When every section is empty, `## Findings` still appears and contains exactly `No performance issues found.`_

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Recommendations

[Structural items not tied to a single finding - route-level `next/dynamic` for editor pages, split filters context into state + dispatch, add bundle budget to CI, adopt `@tanstack/react-virtual` across list views.]

## Capacity and Budget Plan _(`deep` only - omit at `standard`)_

Capacity guidance (virtualization, batched endpoints, pagination for large datasets) and a per-route budget plan (LCP / INP / bundle thresholds wired to CI). This is its own section, not a Recommendations bullet, so the parent preserves it when merging. A structural fix motivated by a specific finding belongs in Recommendations at any depth.

## Next Steps

Each item `[Implement]` (localized) or `[Delegate]` (cross-cutting / build config / load test). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: build] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed React; `Framework`, `Data Layer`, `Styling`, React major and TanStack Query major recorded (write `not detected` for any the project does not reveal)
- [ ] Step 3 - `review-precondition-check` ran or parent handle accepted; diff + log read once; performance surface opened (changed routes, components, config, data-fetching sites)
- [ ] Step 4 - `react-hooks-patterns`, `react-component-patterns` and `react-state-patterns` consulted; `"use client"` placement, identity-stable props, context memo, list keys / virtualization, inline-component hazard audited
- [ ] Step 5 - `frontend-performance` and `react-nextjs-patterns` consulted; bundle deltas sized per new dep; tree-shake-hostile imports flagged; heavy libs gated by `dynamic()` / `React.lazy`
- [ ] Step 6 - `react-data-fetching` consulted; `fetch` cache intent, Server-vs-Client fetch placement, TanStack `staleTime` / keys / invalidation audited
- [ ] Step 7 - `frontend-performance` consulted; LCP image / fonts, third-party script weight and TTFB, INP `useTransition` / `useDeferredValue`, CLS reservations checked
- [ ] Step 8 - hydration sources, Suspense streaming, ISR / SSG / SSR / runtime decisions reviewed (skipped on Vite; on Pages Router only the App Router segment mechanics were skipped)
- [ ] Step 9 - observability presence checked or `[Delegate]` added; standalone: same-SHA no-op gate applied, prior round reconciled when a valid prior report existed, findings verified, tally in Summary, report written via `review-report-writer` with full checkpoint fields and a real branch name, confirmation printed; subagent: Output Format document returned, nothing written
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
- Approving raw `<img>` for hero / above-the-fold on Next.js (`next/image` + `priority`)
- Approving CSS-in-JS in a Tailwind / CSS Modules project for "DX" reasons
- Treating high re-render counts as inherently bad - investigate only when a profile or interaction lag implicates them
- `useEffect(() => fetch(...), [])` in a Client Component when a Server Component parent could fetch
- Conflating perf with general / security review - delegate
- **Out-of-lens defects** (security: untrusted `dangerouslySetInnerHTML`, `eval`; correctness: a crash or logic bug spotted en route): one `[Delegate] -> <workflow>` line per target workflow, not per defect - name the defects on that one line. Put it in Next Steps, and when the defect would break the build or expose data add a single `out of lens: <one line>` at the end of `## Findings` so a reader of the findings alone still sees it. If the issue also has a real perf cost, file that cost as its own Finding and still delegate the other half once
- Estimating an impact the diff cannot support - say what would measure it instead
