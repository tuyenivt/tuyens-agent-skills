---
name: task-react-refactor
description: React refactor planning for god components, prop drilling, `useEffect` overuse for derived state / events, fat hooks, `"use client"` placement at root of layouts, missing Server Component conversion, scattered state, missing Zod on Server Actions, untyped props, accessibility gaps, inline business logic in JSX. Produces a step-by-step sequence of independently-committable refactoring steps with a Vitest coverage gate. Stack-specific override of task-code-refactor for React.
agent: react-tech-lead
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# React Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific React target (component, hook, route, Server Action, page / layout, provider). Identifies React-specific smells (god component, prop drilling, `useEffect` for derived state, `"use client"` at root of layout, fat hook, conditional rendering ladder, scattered state, missing Zod on Server Action, inline business logic in JSX, untyped props) and proposes independently-committable refactoring steps with Vitest gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for React.

## When to Use

- React code-smell identification and resolution
- React technical-debt reduction with a concrete plan
- Safe refactoring of a component / hook / route / Server Action / provider
- Pre-merge "this PR grew the god-component / prop-drilling problem - what's the cleanup?"
- Migrating a Client Component to Server Component (Next.js)

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-react-new`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-react-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                    |
| --------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, module, or route to refactor (e.g., `app/dashboard/page.tsx`, `src/features/orders/OrderList.tsx`, `app/account/actions.ts`)                             |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `useOrderFilters` hook, move `"use client"` to a leaf, split `Dashboard` god component, kill prop drilling) |
| Test coverage status  | Recommended | Whether Vitest / RTL / Playwright coverage exists for the target area                                                                                          |
| Shared/public surface | Recommended | Whether the target is used across feature / route / app boundaries                                                                                             |

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm React. If invoked as a subagent of a React-aware parent, accept the pre-confirmed stack. If not React, stop and tell the user to invoke `/task-code-refactor` instead.

Detect framework: Next.js (App Router / Pages Router) vs Vite + React Router. Record `Framework: ...`, `React: <version>` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target component / hook / module top-to-bottom; note line count, hook usage, prop interface, conditional rendering depth, state declarations, effect declarations, external collaborators (`fetch`, TanStack Query, `Sentry.captureException`, navigation calls)
2. Read the matching test file(s) (`*.test.tsx`, `*.test.ts`, Playwright `*.spec.ts`); count cases by outcome (happy path, error state, empty state, validation failure, auth denial, accessibility check)
3. If callers / parents are obvious (a route page importing a feature component, a layout wrapping a page), read the immediate caller too - removing or reshaping props without seeing call sites is how silent breakage happens
4. For Next.js Server Components / Server Actions, read the parent layout / page to understand the boundary the target lives behind

If the user named only the goal without a target file / module, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat modules. If the file containing the target also contains other smells (e.g., the user names `OrderList` but the same file has IDOR risk in `OrderActions` and `dangerouslySetInnerHTML` in `OrderDescription`), do **not** action them in this plan and do **not** ignore them silently. List under a `Sibling Smells (Out of Scope)` heading, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-react-review-security`), and recommend follow-up invocations.

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`*.test.tsx`, `*.test.ts`, integration tests, Playwright specs), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                | What the workflow does                                                                                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., empty state, error state, validation failure, auth denial) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                            | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                     | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-react-test` first              |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves error handling, empty states, or accessibility - you would be flying blind.

**Output of this step:** explicit coverage status using one of the three labels. Do not proceed past Step 4 if status is `Inadequate`.

**Preview rules when Inadequate.** Step 4's smell catalog still runs to populate the Smells Identified and Sibling Smells (Out of Scope) preview - that is what the catalog is for. The refusal is on producing Steps 1+, not on diagnostic output. The preview helps the author scope the follow-up `task-react-test` invocation (e.g., "we know we'll need filter-validation tests because there's a god component with filter logic").

**Bug-fix smuggled into a refactor request.** If the user's prose mixes "refactor X" with "and also fix that the filter does not persist on refresh," stop and surface the conflict: refactoring assumes behavior preservation, so a behavior change must either (a) be a separate PR ahead of the refactor, or (b) be explicitly labeled `coupled-fix` in Step 6 with its own test gate. Do not silently fold it into an extraction step.

### Step 4 - Identify React Smells

Inspect the target for these React-specific smells. Use judgment - these are signals, not hard rules.

**Component smells:**

| Smell                                      | Signal                                                                                                                                                    | Risk   |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Component                              | Component file > 300 lines; mixes data fetching, state, business logic, multiple sub-rendering paths                                                      | High   |
| Inline Business Logic in JSX               | Calculations, branching > 3 levels, formatting inside the JSX `return` block - extract to functions or sub-components                                     | Medium |
| Conditional Rendering Ladder               | > 3 nested ternaries / `&&` chains in the return; readability degrades fast                                                                               | Medium |
| Inline Anonymous Components                | `function InnerThing() {...}` declared inside the parent's body - re-created every render, breaks `React.memo`, breaks state of any state hooks inside it | High   |
| `"use client"` at Root of Layout (Next.js) | A layout / page-level component marked `"use client"` for one small interactive piece - pulls the entire descendant tree into client bundle               | High   |
| Untyped Props (`props: any`)               | Component prop interface uses `any` or is missing entirely; type errors silenced via `as any`                                                             | High   |
| Anonymous Default Export                   | `export default function() {...}` - bad stack traces and unfriendly DevTools display                                                                      | Low    |
| Mass-Imported Barrel                       | `import { X } from '@/components'` defeats tree-shake and pulls unrelated components into the bundle                                                      | Medium |

**Hook smells:**

| Smell                                     | Signal                                                                                                                                            | Risk   |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Hook                                  | Custom hook with 8+ params and 12+ return fields - extract or split                                                                               | High   |
| `useEffect` for Derived State             | `useEffect(() => setX(a + b), [a, b])` - compute during render: `const x = a + b`                                                                 | High   |
| `useEffect` for Event Handling            | `useEffect(() => { if (clicked) doThing() }, [clicked])` triggered by `setClicked` in `onClick` - just call `doThing()` from the handler          | High   |
| Missing `useEffect` Cleanup               | Subscriptions / observers / intervals without a return cleanup function - memory leak across re-renders                                           | High   |
| Stale Closure / Wrong Deps                | `useEffect(..., [])` while reading props / state - eslint-disabled `react-hooks/exhaustive-deps` without comment                                  | High   |
| `useState` for Derived Value              | State that is always computed from other state / props - eliminate; compute during render                                                         | Medium |
| `useState` for Lifetime Constant          | `const [config] = useState({...})` initialized once and never set - move to a module-level constant, `useMemo`, or a `useRef` if identity matters | Low    |
| `useMemo` / `useCallback` on Cheap Values | Memoization on primitives / cheap operations - costs more than it saves                                                                           | Low    |
| `useState` for URL-Synced State           | Filters, page, sort kept in `useState` instead of search params - breaks deep-linking, breaks back-button, doesn't survive reload                 | Medium |
| Hooks Called Conditionally                | `if (x) { useState(...) }` or hooks after early returns - violates Rules of Hooks (eslint catches this; flag any disable)                         | High   |

**Data fetching smells:**

| Smell                                          | Signal                                                                                                                                        | Risk   |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `useEffect(() => fetch(...))` for Initial Data | Pattern works but loses cache, dedup, refetch-on-focus, error handling - prefer TanStack Query, SWR, or (Next.js) Server Component fetch      | High   |
| Server-Fetchable Data Fetched on Client        | Next.js Client Component `useEffect(() => fetch(...))` for data the parent Server Component could fetch and pass as props - request waterfall | High   |
| Sequential `await` for Independent Fetches     | `const a = await getA(); const b = await getB();` instead of `Promise.all` - waterfall doubles latency                                        | Medium |
| Unstable Query Keys                            | `useQuery({ queryKey: ['orders-' + JSON.stringify(filters)] })` - structured arrays (`['orders', filters]`) enable scoped invalidation        | Medium |
| Missing Cache Invalidation After Mutation      | `useMutation` succeeds but no `queryClient.invalidateQueries(...)` - UI shows stale data                                                      | High   |

**State / configuration smells:**

| Smell                                       | Signal                                                                                                         | Risk   |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------ |
| Prop Drilling > 4 Layers                    | Same prop threaded through 4+ component layers - hoist to context, state lib, or co-locate                     | Medium |
| Context Re-Renders Every Consumer           | Provider value rebuilt every render (`<Provider value={{ a, b }}>`); split into state vs dispatch or `useMemo` | High   |
| Single-Consumer Context                     | Context for state read by exactly one component - remove context, lift / pass directly                         | Low    |
| Mutable Module-Level State                  | `let cache = {}` / `const handlers = []` mutated by render or events - leaks across HMR, tests, requests (SSR) | High   |
| `process.env.X` Sprinkled Across Components | Should be a typed config module / Zod-validated env loader                                                     | Medium |
| Provider Sandwich at Root                   | > 5 providers nested in `app/layout.tsx` / `App.tsx`; consolidate into `<Providers>` for readability           | Low    |

**Server Action / Route Handler smells (Next.js):**

| Smell                                       | Signal                                                                                                                           | Risk |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---- |
| Server Action Without Zod                   | `'use server'` function accepting `formData` / args without validation - mass-assignment risk if data flows into ORM             | High |
| Server Action Without Auth                  | Mutation Server Action without `await auth()` (or session check) at the top                                                      | High |
| `'use server'` File Re-exports Utility      | A file with `'use server'` directive must export only Server Actions - utilities exported here become network-callable           | High |
| Server Component Returns Entire ORM Row     | `prisma.user.findUnique({ where })` rendered into Client Component props - serializes `passwordHash` / internal fields into HTML | High |
| `dangerouslySetInnerHTML` Without Sanitizer | User-controlled HTML rendered raw - XSS                                                                                          | High |

**Accessibility smells:**

| Smell                                 | Signal                                                                                                                   | Risk   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------ |
| `<input>` Without `<label>`           | Inputs without associated labels - screen readers miss them                                                              | High   |
| Custom Dialog Without Focus Trap      | Modal built from `<div>` without `role="dialog"`, focus trap, or keyboard close - keyboard / screen-reader users blocked | High   |
| `<div onClick>` Instead of `<button>` | Clickable `<div>` without `role="button"`, `tabIndex`, key handling - not focusable, not announced as button             | High   |
| Image Without `alt`                   | `<img>` / `next/image` without `alt` (or `alt=""` for decorative)                                                        | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                              | Signal                                                                                                  | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ------ |
| `getByTestId` Everywhere           | Tests rely on `data-testid` instead of user-centric queries - couples to implementation                 | Medium |
| `fireEvent` Instead of `userEvent` | Skips focus / key events real users trigger                                                             | Medium |
| Snapshot Tests on Visual Layout    | Churns on every styling change; no signal                                                               | Medium |
| Render Counts Asserted             | `expect(renderSpy).toHaveBeenCalledTimes(2)` - tests implementation; rewrite to assert visible behavior | High   |

**General smells (apply with TypeScript / React judgment):**

Use skill: `complexity-review` when the target shows over-engineering signals (single-impl HoC, generic abstractions for one consumer, premature compound components) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply React judgment - a 250-line component that orchestrates clearly named sub-components is fine; a 100-line component doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and routes are affected.

React-specific blast-radius signals:

- [ ] **Public design-system component**: target is a primitive in a shared component library used across many features
- [ ] **Top-level layout / provider**: refactoring `app/layout.tsx`, root `App.tsx`, or a global provider affects every page
- [ ] **Hook used widely**: target hook is imported by > 10 components; signature changes cascade
- [ ] **Route segment used in many places**: refactoring `app/(marketing)/layout.tsx` affects every marketing page
- [ ] **Component prop interface**: prop rename / removal cascades into every parent that renders the component
- [ ] **Server Action consumed by multiple forms**: refactoring an action breaks every `<form action={...}>` pointing at it
- [ ] **State / context used cross-feature**: refactoring a shared store affects every feature that reads it

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single feature, multiple callers) / **Wide** (cross-feature, public component, root layout) / **Critical** (design-system primitive, root provider).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `tsc --noEmit` cleanly and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing Vitest / Playwright suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a god component with `useEffect` for derived state, `"use client"` at root, and prop drilling), do **not** concatenate the recipes - that produces a 25-step plan. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a Server Action that derives `ownerId` from the session _requires_ a session check be added to the action, which changes the failure mode for unauthenticated callers). Label such steps `coupled-fix` with their own test gate and rationale. This is **not** a bundling violation - it is an explicit prerequisite. Do not silently fold it into an extraction step.

**Hydration-boundary watch.** When converting a component between Server and Client (Next.js), state which boundary the result lives on. Adding `"use client"` pulls the descendant tree client-side - audit imports for server-only modules (`fs`, ORM clients) that must be hoisted to a Server Component parent. Removing `"use client"` requires that no descendant uses hooks / events / browser APIs - audit before changing.

**Async-boundary watch.** Adding `async` to a component function (Server Components only) or removing it crosses a rendering boundary. Client Components cannot be `async`; flag any attempt to make a Client Component async.

**Common React refactor recipes:**

**Recipe: Move `"use client"` to the leaf**

1. Identify the smallest interactive subtree in the current Client Component (the actual hook / event handler / browser-API surface)
2. Extract that subtree into a new component file marked `"use client"`; the new file is a Client Component, importable from anywhere
3. Remove `"use client"` from the original layout / page; replace the inlined interactivity with `<NewClientComponent />`
4. Verify the parent now compiles as a Server Component (no hooks, no event handlers, no `window`); fix or hoist any leakage
5. Run tests; assert observable behavior unchanged (RTL component tests for the leaf, Playwright E2E for route-level)

> **Mixed-interactivity case.** When the original Client Component has interactivity scattered across the tree (filters at the top, table rows in the middle, pagination at the bottom - each holding state) you cannot pull it down to a single leaf. Instead, identify each interactive island, extract each one as its own `"use client"` component, and have the Server Component parent compose them. The parent stays a Server Component; it passes server-fetched data into each Client island as props. If two islands must share state, hoist that shared state into a Client `<Provider>` that wraps only the islands that need it - not the whole route.

**Recipe: Move filter / pagination / sort state to URL search params (Next.js + React Router)**

This is a behavior-aware refactor: moving filter state to the URL means refresh, deep links, and back-button now preserve filter state. That is a UX contract change. Treat it as `coupled-fix` Step 1 in the plan and tell the user explicitly so the change is not surprising.

1. Define the URL contract: which params, types, defaults (e.g., `status: 'open' | 'closed' | 'all' = 'all'`, `page: number = 1`, `q: string = ''`). Validate via Zod / a small parser; reject malformed values to defaults rather than crashing on bad input
2. Replace each `useState` filter with a read from search params via `useSearchParams()` (Next.js) / `useSearchParams` from React Router
3. Replace each `setFilter(...)` call with a `router.push(\`?\${params.toString()}\`)`(Next.js) /`setSearchParams(params)`(React Router); on Next.js, prefer`router.replace` for filters that should not pollute history
4. Update the data fetcher: query keys / Server Component fetches now derive from search params (`['orders', { status, page }]`); the URL is the source of truth
5. Run tests: deep-linking (`/orders?status=open` renders filtered list immediately), back-button restores prior filter, refresh preserves filter, validation fallback for malformed params
6. (Coupled-fix) Note that this changes back-button behavior - document in PR description; check that no analytics depend on the old in-memory state

**Recipe: Replace fan-out `useEffect` fetches with Server Component fetch + `Promise.all` (Next.js) or parallel TanStack queries**

The smell: a Client Component with three `useEffect(() => fetch(...), [])` blocks for `/api/orders`, `/api/users`, `/api/billing` - serial waterfall (component renders, hydrates, fires three requests, each blocking its render path on its own).

1. **If the parent could be a Server Component** (and would do so once the consuming subtree is moved to a Client leaf - see the `"use client"` recipe): hoist the three fetches to the Server Component. Use `await Promise.all([getOrders(), getUsers(), getBilling()])` so they run in parallel server-side. Pass the resolved data as props to the (now smaller) Client Component
2. **Otherwise** (real client-only fetch): replace each `useEffect` with `useQuery({ queryKey, queryFn })` - `useQueries([...])` for explicit fan-out. Set `staleTime` (default 0 = refetch on every mount) and `gcTime` deliberately based on data volatility (e.g., `staleTime: 60_000` for typical reads; longer for catalog / config)
3. Add cache invalidation on writes that mutate the fetched data: `useMutation({ onSuccess: () => queryClient.invalidateQueries({ queryKey: ['orders'] }) })`
4. Add Suspense boundaries (`<Suspense fallback={<Skeleton />}>`) so the slow fetch streams while the fast ones render - especially valuable in Next.js Server Components
5. Run tests: empty / loading / error states (the `useEffect` version probably under-tested these); concurrent fan-out asserted via mock latency

**Recipe: Virtualize a long list**

When the target renders > 500 rows in steady state and the diff under refactor is touching the rendering path, virtualization belongs in the plan. Treat as a separate refactor target if the user did not name it - do not bundle silently.

1. Choose the primitive: `@tanstack/react-virtual` (modern, framework-agnostic, supports horizontal + grid) or `react-window` (lighter, simpler API). Match what the project already uses if any
2. Replace the rendered list with the virtualizer's render path; reserve container height (`h-screen`, fixed `--vh`, or measured) - virtualization does not work without a known viewport
3. Verify keyboard navigation, screen-reader announcement, and scroll-restoration still work - virtualization can break all three; use the library's accessibility mode (`@tanstack/react-virtual` `aria-rowcount` / `aria-rowindex` semantics)
4. Run tests: `userEvent` keyboard navigation, screen-reader announcement (`vitest-axe` for accessibility tree), scroll restoration on back-navigation
5. Measure the LCP / INP impact (RUM if available, else Lighthouse run before / after)

**Recipe: Extract custom hook from fat component**

1. Identify the cohesive state + effect + handler trio inside the component (e.g., filters state + URL sync effect + `setFilter` callback)
2. Create `use<Concern>.ts` with the same shape; copy logic; write a hook test (`renderHook` + boundary cases - state transitions, effect cleanup, edge cases)
3. Replace the inlined logic in the component with `const filterApi = useFilters(...)`; component still does the original work via the hook
4. Verify component tests pass unchanged
5. Audit other components for the same pattern - opportunity to reuse the hook (do not bundle this audit; surface it as a follow-up)

**Recipe: Replace `useEffect` for derived state with computed value**

1. Identify the effect: `useEffect(() => setX(a + b), [a, b])` (or similar)
2. Replace with: `const x = a + b` (compute during render); delete `useState` for `x`; delete the effect
3. Run tests; assert observable behavior unchanged (the prior version had a transient render with stale `x` between `a` change and effect run; now `x` is always consistent)
4. Audit other components for the same pattern

**Recipe: Replace `useEffect` for fetching with TanStack Query / Server Component fetch**

1. **If on Next.js and the parent could be a Server Component**: hoist the fetch to the parent Server Component; pass data as a prop; remove the `useEffect`
2. **Else**: replace with `useQuery({ queryKey: ['x', filters], queryFn: () => fetchX(filters) })`; handle `isLoading` / `error` from the hook return
3. Add cache invalidation on relevant mutations (`onSuccess: () => queryClient.invalidateQueries(['x'])`)
4. Run tests; add tests for empty / error / loading states (boundary outcomes the `useEffect` version probably didn't cover)

**Recipe: Untangle prop drilling**

1. Identify the prop chain (which prop, which layers it passes through)
2. Decide on the right primitive: (a) **co-locate state** with the consumer (move the `useState` to the leaf if no other consumer needs it), (b) **context** for cross-cutting state (theme, auth), (c) **state library** (Zustand / Jotai) for app-state shared by multiple features. Choosing the primitive is the first decision; not every prop drill is a context candidate
3. Implement: extract the state into the chosen primitive; remove the prop from intermediate layers; consumers read directly
4. Verify intermediate layers are simpler (fewer props); run tests
5. If using context, ensure value is memoized (`useMemo(() => ({ ... }), [deps])`) so consumers don't re-render unnecessarily

**Recipe: Split god component into focused components**

1. Identify the orthogonal concerns inside the component (e.g., `Dashboard.tsx` doing filters + list + summary + actions panel)
2. Extract one concern at a time into a new component file with explicit prop interface; original god component renders the new one via `<Filters />` etc.
3. Update tests if the new component has its own test surface
4. Repeat until the god component is a thin layout coordinator
5. Verify route-level tests / Playwright E2E still pass

**Recipe: Migrate Client Component → Server Component (Next.js)**

1. Audit the component for client-only hooks (`useState`, `useEffect`, `useRef`, event handlers, `window` access). If any are present, this recipe doesn't apply directly - first move them into a small Client Component leaf
2. Remove `"use client"` directive
3. Convert any client-side `useEffect(() => fetch(...))` into a top-of-component `await fetch(...)` (Server Components are async)
4. Update any imports that were only-client (e.g., `react-icons` is fine; `@tanstack/react-query` is client-only - replace with Server Component data fetching)
5. Run build (`tsc --noEmit` + `next build` if available locally); fix any boundary leakage errors
6. Verify Playwright E2E tests pass; the data flow now happens server-side and the client receives rendered HTML

**Recipe: Add Zod validation to Server Action**

1. Define a Zod schema for the action's input (`zod-form-data` for FormData; plain Zod for typed args)
2. Add `const parsed = Schema.parse(formData)` (or `.safeParse` + early return) at the top of the action; followed by the existing logic using `parsed.<field>`
3. Audit the action for any `formData.get('x')` / `args.x` references that should now use `parsed.<field>`
4. Add a test: invalid input rejected with the expected error shape; valid input proceeds
5. Audit other Server Actions in the file for the same gap - surface as follow-up if not in this plan's scope

**Recipe: Stabilize context value to prevent re-render storm**

1. Identify the provider: `<MyContext.Provider value={{ a, b, fn }}>`
2. Memoize the value: `const value = useMemo(() => ({ a, b, fn }), [a, b, fn]);` - use referentially stable function (declare `fn` via `useCallback` or hoist)
3. **Or split** into two contexts: state (`MyStateContext`) and dispatch (`MyDispatchContext`) - dispatch is referentially stable, state changes per action; consumers subscribe to only what they need
4. Run tests; profile if available (re-render counts in React DevTools Profiler should drop)

**Recipe: Replace mutable module-level state**

1. Identify the mutable state (`let cache = {}`, `const handlers = []`)
2. Move into a hook + context, a state library (Zustand store), or per-component state if appropriate
3. Update consumers to read via the new primitive
4. Run tests; assert cross-test isolation (Vitest test order should not matter)

**Recipe: Add accessibility for custom interactive component**

1. Identify the violation (e.g., `<div onClick>` for a button)
2. Replace with the right semantic element (`<button>`, `<a>`, `<input>`) or add proper ARIA + key handlers (`role`, `tabIndex`, keydown handler dispatching click on Enter / Space)
3. Add label / `aria-label` / `aria-describedby` as needed
4. Run `vitest-axe` / `jest-axe` test asserting no violations

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps ordered low-risk first (extracts, additions) before high-risk (deletions, prop removals, boundary changes)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## React Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common React refactor recipes" - this is the spine]
**Stack:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-react-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce **Smells Identified** and **Sibling Smells (Out of Scope)** as a *preview*; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure / invalid input, error state, empty state, loading state, accessibility (when interactive). Layer options: component test (RTL + `user-event`), hook test (`renderHook`), Server Action test (function call with FormData fixture), Playwright E2E. Example: `OrderList | empty-state visible when 0 orders | component test`.

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/module that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                               |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-react-review-security` / `task-react-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - component / hook / E2E / Server Action]
- **Hydration stance:** [Server Component | Client Component | unchanged | converting from X to Y]
- **Async stance:** [sync | async (Server Component) | unchanged]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it (e.g., adding `await auth()` so the extracted Server Action can derive `ownerId`). Always state why the coupling is structural.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `tsc --noEmit` clean and Vitest suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No silent Server Component ↔ Client Component boundary changes; descendants audited
- [ ] No silent sync ↔ async signature changes (Server Component conversions only)

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderList` to `OrdersTable` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as React (or accepted from parent dispatcher); framework recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin` (Step 3)
- [ ] When refusal triggered (Inadequate), Step 4 catalog still ran to produce the Smells preview; not skipped (Step 3)
- [ ] Bug-fix smuggled into a refactor request was surfaced and split into a separate PR or labeled `coupled-fix` - never silently folded (Step 3)
- [ ] React-specific smells identified using Step 4 catalog (component, hook, data fetching, state, Server Action, accessibility, test) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate` (Output Format)
- [ ] Hydration stance (Server / Client / unchanged) stated per step on Next.js targets (Step 6)
- [ ] Async stance stated per step (no silent sync ↔ async changes, e.g., making a Client Component async) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, boundary changes, prop removals) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `tsc --noEmit` clean and Vitest suite passes between every step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing a `useEffect` without verifying the surrounding logic preserves the original observable behavior - some effects compensate for genuinely external state and removal regresses
- Converting a Client Component to Server Component without auditing every descendant for hooks / events / browser APIs - silent build break or runtime crash
- Moving `"use client"` toward the leaf without verifying the new root has no client-only imports
- Making a Client Component `async` - not supported; it must be a Server Component or use `useEffect` / TanStack Query for async data
- Replacing `useEffect` for fetching with TanStack Query when a Server Component parent could fetch instead (Next.js) - deeper improvement available
- Replacing prop drilling with context as a default - co-located state is often the right answer; context for cross-cutting state, state library for app-shared
- Replacing context with a state library (Zustand / Jotai) without checking that the additional dep is justified - sometimes a memoized context is enough
- Refactoring a design-system primitive without a backward-compatibility plan - that is a public API
- Replacing `getByTestId` queries with `getByRole` queries during a refactor - that is a test improvement, deserves its own PR
