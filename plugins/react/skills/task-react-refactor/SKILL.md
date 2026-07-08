---
name: task-react-refactor
description: Plan a React/Next.js refactor: god components, prop drilling, useEffect overuse, "use client" misuse, RSC conversion. Phased, gated.
agent: react-tech-lead
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# React Refactor

Produce a step-by-step refactor plan for a React target (component, hook, route, Server Action, page/layout, provider). Each step is independently committable with `tsc --noEmit` + Vitest gates.

Stack-specific delegate of `task-code-refactor` for React.

## When to Use

- React code-smell identification with a concrete plan
- Safe refactor of a component / hook / route / Server Action / provider
- Cleanup of god-component / prop-drilling / `"use client"` misuse before merge
- Migrating Client Component to Server Component (Next.js)

**Not for:**

- Feature changes (use `task-react-implement`)
- Cross-module architecture moves (use `task-design-architecture`)
- Bug fixes (use `task-react-debug`)

## Inputs

| Input                 | Required    | Notes                                                                                |
| --------------------- | ----------- | ------------------------------------------------------------------------------------ |
| Target                | Yes         | File or route (e.g., `app/dashboard/page.tsx`, `src/features/orders/OrderList.tsx`)  |
| Goal                  | Yes         | What the refactor should achieve                                                     |
| Test coverage status  | Recommended | Vitest / RTL / Playwright coverage for the target                                    |
| Shared/public surface | Recommended | Whether the target is used across feature / route / app boundaries                   |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not React, stop and route to `/task-code-refactor`. If invoked by a React-aware parent, accept the pre-confirmed stack.

Record `Framework` (Next.js App Router / Next.js Pages Router / Vite + React Router) and `React: <version>` for the output.

### Step 3 - Read the Target

Read the actual files; do not classify from prose alone.

1. Target file top-to-bottom: line count, hook usage, prop interface, conditional rendering depth, state/effect declarations, external collaborators (`fetch`, TanStack Query, navigation, `Sentry.captureException`)
2. Matching tests (`*.test.tsx`, `*.test.ts`, Playwright `*.spec.ts`): cases by outcome (happy, error, empty, validation, auth, accessibility)
3. Immediate callers when obvious (route page importing feature component, layout wrapping page)
4. For Server Components / Server Actions, read the parent layout/page to understand the boundary

If only a goal was given without a target, ask before proceeding.

**Sibling smells.** Real targets sit in fat files. Other smells in the same file go under `Sibling Smells (Out of Scope)` with deferral rationale and recommended follow-up skill - never silently included, never silently dropped.

**Severity inversion.** If a sibling smell is *higher severity* than the named target (XSS via `dangerouslySetInnerHTML`, Server Action without auth, IDOR), recommend pausing the refactor and routing through `task-react-review-security` first. Flag in `Sibling Smells`; the refactor PR branches off the security fix, not main.

**Bug-fix smuggled into refactor.** If the user mixes "refactor X" with "and fix that filter does not persist on refresh," stop and surface the conflict: refactoring assumes behavior preservation, so behavior changes are either a separate PR ahead, or labeled `coupled-fix` in Step 6 with their own gate.

### Step 4 - Coverage Gate (mandatory)

Refactoring without coverage is a rewrite. Identify tests covering the target, then label:

| Status       | Definition                                                            | Action                                                                       |
| ------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** >= 2 boundary outcomes per public entry point     | Proceed                                                                      |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                        | Proceed; plan includes non-optional `Step 0` adding the missing boundaries   |
| `Inadequate` | No tests, or happy-path-only                                          | Refuse Steps 1+. Output gate verdict + recommend `task-react-test`           |

Happy-path-only is `Inadequate`, not `Thin` - a single success case can't prove error handling, empty states, or accessibility preservation.

When status is `Thin` or `Inadequate`, render prerequisite tests as: `entry-point | outcome | recommended layer`. Outcomes must include validation failure, error state, empty state, loading state, and (when interactive) accessibility. Layers: component test (RTL + `user-event`), hook test (`renderHook`), Server Action test (FormData fixture), Playwright E2E.

When refusal triggers, Step 5 catalog still runs to produce a preview of Smells Identified + Sibling Smells. Refusal is on Steps 1+, not on diagnostic output.

### Step 5 - Identify Smells

Use judgment - these are signals, not rules. A 250-line component orchestrating clearly named sub-components is fine; a 100-line component doing three unrelated things is not.

**Component:**

| Smell                                      | Signal                                                                                                     | Risk   |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | ------ |
| God component                              | > 300 lines mixing fetching, state, logic, multiple rendering paths                                        | High   |
| Inline business logic in JSX               | Calculations, > 3-level branching, formatting inside the `return` block                                    | Medium |
| Conditional rendering ladder               | > 3 nested ternaries / `&&` chains                                                                         | Medium |
| Inline anonymous components                | `function Inner() {...}` declared inside parent body - re-created every render, breaks `memo` and hooks    | High   |
| `"use client"` at root of layout/page      | Top-level `"use client"` for one interactive piece - pulls descendants into client bundle                  | High   |
| Untyped props (`any`)                      | Prop interface uses `any` / missing; `as any` silences errors                                              | High   |
| Anonymous default export                   | `export default function() {...}` - bad stack traces, unfriendly DevTools                                  | Low    |
| Mass-imported barrel                       | `import { X } from '@/components'` defeats tree-shake                                                      | Medium |

**Hooks:**

| Smell                                  | Signal                                                                                          | Risk   |
| -------------------------------------- | ----------------------------------------------------------------------------------------------- | ------ |
| Fat hook                               | 8+ params and 12+ return fields - extract or split                                              | High   |
| `useEffect` for derived state          | `useEffect(() => setX(a + b), [a, b])` - compute during render                                  | High   |
| `useEffect` for event handling         | Effect triggered by `setClicked` in `onClick` - call the handler directly                       | High   |
| Missing `useEffect` cleanup            | Subscriptions / observers / intervals without return cleanup                                    | High   |
| Stale closure / wrong deps             | `[]` while reading props/state; eslint-disabled `exhaustive-deps` without comment               | High   |
| `useState` for derived value           | State always computed from other state/props - compute during render                            | Medium |
| `useState` for lifetime constant       | `const [x] = useState({...})` never set - module constant, `useMemo`, or `useRef`               | Low    |
| `useMemo`/`useCallback` on cheap values | Memoization on primitives - costs more than it saves                                           | Low    |
| `useState` for URL-synced state        | Filters/page/sort in `useState` instead of search params - breaks deep links, back button       | Medium |
| Hooks called conditionally             | Hooks after early returns / inside `if` - Rules of Hooks violation                              | High   |

**Data fetching:**

| Smell                                       | Signal                                                                                          | Risk   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------ |
| `useEffect(() => fetch(...))` for init data | Loses cache, dedup, refetch-on-focus - use TanStack Query, SWR, or Server Component fetch       | High   |
| Server-fetchable data fetched on client     | Client `useEffect(() => fetch(...))` where parent Server Component could fetch - waterfall      | High   |
| Sequential `await` for independent fetches  | Use `Promise.all` - serial doubles latency                                                      | Medium |
| Unstable query keys                         | `['orders-' + JSON.stringify(filters)]` - use structured `['orders', filters]`                  | Medium |
| Missing cache invalidation after mutation   | `useMutation` succeeds without `queryClient.invalidateQueries(...)` - UI shows stale data       | High   |

**State / configuration:**

| Smell                              | Signal                                                                                              | Risk   |
| ---------------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| Prop drilling > 4 layers           | Same prop threaded through 4+ layers - hoist, context, or co-locate                                 | Medium |
| Context re-renders every consumer  | `<Provider value={{ a, b }}>` rebuilt every render - `useMemo` or split state/dispatch              | High   |
| Single-consumer context            | Context read by exactly one component - lift / pass directly                                        | Low    |
| Mutable module-level state         | `let cache = {}` mutated by render/events - leaks across HMR, tests, SSR requests                   | High   |
| `process.env.X` sprinkled          | Belongs in typed config / Zod-validated env loader                                                  | Medium |
| Provider sandwich at root          | > 5 providers nested in root layout - consolidate                                                   | Low    |

**Server Action / Route Handler (Next.js):**

| Smell                                       | Signal                                                                                            | Risk |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------- | ---- |
| Server Action without Zod                   | `'use server'` accepting `formData`/args without validation - mass-assignment risk                | High |
| Server Action without auth                  | Mutation without `await auth()` / session check at top                                            | High |
| `'use server'` file re-exports utility      | A `'use server'` file may only export Server Actions - utilities become network-callable          | High |
| Server Component returns entire ORM row     | `prisma.user.findUnique(...)` rendered into Client Component - leaks `passwordHash` into HTML     | High |
| `dangerouslySetInnerHTML` without sanitizer | User HTML rendered raw - XSS                                                                      | High |

**Accessibility:**

| Smell                                 | Signal                                                                                            | Risk   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------- | ------ |
| `<input>` without `<label>`           | Screen readers miss them                                                                          | High   |
| Custom dialog without focus trap      | `<div>` modal without `role="dialog"`, focus trap, keyboard close                                 | High   |
| `<div onClick>` for a button          | Not focusable, not announced as button                                                            | High   |
| Image without `alt`                   | `<img>` / `next/image` without `alt` (or `alt=""` for decorative)                                 | Medium |

**Tests (when in scope):**

| Smell                           | Signal                                                                                         | Risk   |
| ------------------------------- | ---------------------------------------------------------------------------------------------- | ------ |
| `getByTestId` everywhere        | Couples to implementation - prefer user-centric queries                                        | Medium |
| `fireEvent` instead of `userEvent` | Skips focus/key events real users trigger                                                   | Medium |
| Snapshot tests on visual layout | Churn on every styling change; no signal                                                       | Medium |
| Render counts asserted          | `expect(renderSpy).toHaveBeenCalledTimes(2)` tests implementation                              | High   |

**Over-engineering signals** (single-impl HoC, generic abstractions for one consumer, premature compound components, single-consumer Context, premature memoization, store-for-two-slices): Use skill: `complexity-review` + `react-overengineering-review` - these are simplifications, not new abstractions. Run before proposing the recipe so a refactor toward less structure isn't masked by a recipe toward more.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. State `Narrow | Moderate | Wide | Critical` before proposing steps.

React signals: design-system primitive used cross-feature, root layout / global provider, hook imported by > 10 components, prop interface change cascading to all parents, Server Action consumed by multiple forms, shared store, route segment under many pages.

### Step 7 - Propose the Sequence

Each step must be: independently committable (`tsc --noEmit` + Vitest pass), behaviorally invariant (unless labeled `coupled-fix`), reversible in one revert, tested.

**Primary recipe.** Pick one recipe matching the user's goal as the spine. Fold supporting recipes as additive sub-steps where dependencies require. Never concatenate. State `Primary recipe:` in the output. If the spine exceeds ~8 steps, split into two PRs.

**Coupled-fix.** When a refactor requires a behavior change (e.g., extracting a Server Action that derives `ownerId` from session requires adding a session check, changing failure mode for unauthenticated callers), label `coupled-fix` with its own gate and rationale.

**Per-step stances (recorded in Output Format).** Every step states:

- **Hydration stance** - Server Component | Client Component | unchanged | converting X -> Y. Adding `"use client"` pulls descendants client-side; removing it requires no descendant uses hooks/events/browser APIs.
- **Async stance** - sync | async (Server Component) | unchanged. Client Components cannot be `async`; flag any such attempt.

**Common recipes** (any one can be the spine; supporting recipes fold as sub-steps where dependencies require. Gaps in numbering align with cross-stack recipe IDs and are intentional.):

**R1 - Move `"use client"` to the leaf.**
1. Identify the smallest interactive subtree (the actual hook / handler / browser-API surface)
2. Extract that subtree into a new `"use client"` file
3. Remove `"use client"` from the original layout/page; render `<NewClientComponent />` in its place
4. Verify parent compiles as Server Component (no hooks, no handlers, no `window`); hoist any leakage
5. Run tests; assert observable behavior unchanged

*Mixed-interactivity case:* when interactivity is scattered (filters top, rows middle, pagination bottom), extract each island as its own `"use client"` component; the Server Component parent composes them and passes server-fetched data as props. If two islands share state, hoist into a Client `<Provider>` wrapping only those islands.

**R2 - Extract custom hook from fat component.**
1. Identify the cohesive state + effect + handler trio (e.g., filters state + URL sync effect + `setFilter`)
2. Create `use<Concern>.ts`; copy logic; add `renderHook` test for state transitions, effect cleanup, edges
3. Replace inlined logic with `const api = useFilters(...)`
4. Component tests pass unchanged
5. Surface "audit other components for this pattern" as a follow-up, not a bundled step

**R3 - Split god component into focused components.**
1. Identify orthogonal concerns (e.g., `Dashboard` doing filters + list + summary + actions)
2. Extract one concern per commit into a new file with explicit prop interface; god component renders `<Filters />` etc.
3. Add tests for the new component if it has its own surface
4. Repeat until the original is a thin layout coordinator
5. Route-level / Playwright tests still pass

**R4 - Untangle prop drilling.**
1. Identify the prop chain (which prop, which layers)
2. Choose primitive: (a) **co-locate state** with the consumer if no other consumer needs it, (b) **context** for cross-cutting state (theme, auth), (c) **state library** (Zustand / Jotai) for app-shared state. This choice is the first decision; not every drill is a context candidate
3. Extract state into the chosen primitive; remove from intermediate layers
4. If using context, memoize the value (`useMemo(() => ({...}), [deps])`)
5. Run tests; intermediate layers are simpler

**R6 - Replace `useEffect` for fetching with TanStack Query / Server Component fetch.**
1. **If on Next.js and parent could be a Server Component:** hoist fetch to parent; pass data as prop; remove the `useEffect`
2. **Else:** replace with `useQuery({ queryKey, queryFn })`; handle `isLoading` / `error` from the return; set `staleTime` deliberately
3. Add `invalidateQueries` on relevant mutations
4. Run tests; add boundary tests (empty / error / loading) the `useEffect` version probably missed

**R7 - Replace fan-out `useEffect` fetches with parallel queries / Server Component fetch.**
1. **If parent could be Server Component:** hoist three fetches; `await Promise.all([getA(), getB(), getC()])`; pass data as props
2. **Else:** `useQueries([...])`; set `staleTime` / `gcTime` per data volatility; add `<Suspense fallback={...}>` so slow fetch streams while fast ones render
3. Add cache invalidation on writes
4. Run tests: empty / loading / error / concurrent fan-out (mock latency)

**R8 - Move filter/pagination/sort state to URL search params.**

This is `coupled-fix` (refresh, deep links, back button now preserve state - UX contract change). Tell the user explicitly.

1. Define the URL contract: params, types, defaults (e.g., `status: 'open' | 'closed' | 'all' = 'all'`); validate with Zod; reject malformed to defaults
2. Replace each `useState` filter with `useSearchParams()` read
3. Replace each `setFilter` with `router.push(...)` (Next.js) / `setSearchParams(...)` (React Router); `router.replace` for filters that shouldn't pollute history
4. Update fetcher: query keys / Server Component fetches derive from URL
5. Tests: deep link, back-button restore, refresh preserves, malformed param fallback

**R9 - Migrate Client Component -> Server Component (Next.js).**
1. Audit for client-only surfaces (`useState`, `useEffect`, `useRef`, handlers, `window`); if present, first extract them to a Client leaf (R1)
2. Remove `"use client"`; convert any `useEffect(() => fetch(...))` into top-of-component `await fetch(...)` (Server Components are async)
3. Replace client-only imports (TanStack Query etc.) with Server Component fetching
4. `tsc --noEmit` + `next build`; fix any boundary leakage
5. Playwright E2E passes; client receives rendered HTML

**R10 - Add Zod validation to Server Action.**
1. Define a Zod schema (`zod-form-data` for FormData; plain Zod for typed args)
2. `const parsed = Schema.parse(formData)` (or `.safeParse` + early return) at the top; rewrite refs to `parsed.<field>`
3. Test: invalid input rejected with expected error shape; valid input proceeds
4. Audit other Server Actions in the file - surface as follow-up if not in scope

**R13 - Add accessibility for custom interactive component.**
1. Identify the violation (`<div onClick>` for a button)
2. Use the semantic element (`<button>`, `<a>`, `<input>`) or add `role`, `tabIndex`, keydown handler dispatching click on Enter/Space
3. Add `label` / `aria-label` / `aria-describedby` as needed
4. `vitest-axe` / `jest-axe` test asserts no violations

**Minor recipes** (one-line fixes; cite by name, do not number as spine steps):

- **Derived state in effect**: `useEffect(() => setX(a+b), [a,b])` → `const x = a + b`. Delete the state and the effect.
- **Stabilize context value**: wrap in `useMemo(() => ({...}), deps)`, or split into state / dispatch contexts.
- **Module-level mutable state**: move `let cache = {}` into a hook + context, store, or per-component state; assert cross-test isolation.
- **Virtualize a long list**: separate target if not named. `@tanstack/react-virtual` or `react-window`; reserve container height; verify keyboard nav + scroll restoration.

### Step 8 - Validate Plan Against Goal

- [ ] Goal achieved at end of sequence
- [ ] Each step reviewable in < 30 min
- [ ] `tsc --noEmit` + Vitest between every step
- [ ] Low-risk first (additions, extractions) before high-risk (deletions, prop removals, boundary changes)
- [ ] Rollback is one revert per step
- [ ] No "while we're here" cleanup bundled

## Output Format

```markdown
## React Refactor Plan

**Target:** [file:line or path]
**Goal:** [what the refactor achieves]
**Primary recipe:** [R# from Step 7 - the spine]
**Stack:** React <version> / TypeScript <version>
**Framework:** Next.js App Router <version> | Next.js Pages Router <version> | Vite + React Router <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[Adequate: one sentence on boundary cases that exist.]
[Thin: list missing boundary tests; Step 0 covers them.]
[Inadequate: state required coverage; recommend `task-react-test` first. Stop here - omit Blast Radius, Step Sequence, Verification. You may still produce **Smells Identified** and **Sibling Smells** as preview-only.]

**Prerequisite tests** (when Thin or Inadequate):

| Entry point  | Outcome                            | Recommended layer                       |
| ------------ | ---------------------------------- | --------------------------------------- |
| `OrderList`  | empty-state visible when 0 orders  | component test (RTL + `user-event`)     |
| `useFilters` | resets on route change             | hook test (`renderHook`)                |

## Smells Identified

| Smell    | Location  | Risk | Notes          |
| -------- | --------- | ---- | -------------- |
| [Smell]  | file:line | High | [one-line why] |

## Sibling Smells (Out of Scope)

_Other smells in the target file; listed for hand-off, not action. Omit if none._

| Smell    | Location  | Why deferred                                | Recommended follow-up                          |
| -------- | --------- | ------------------------------------------- | ---------------------------------------------- |
| [Smell]  | file:line | separate target / separate severity / etc. | `task-react-review-security` / other          |

[If a sibling smell is higher severity than the named target, state prominently: "Severity inversion: pause this refactor; route through `task-react-review-security` first; branch the refactor PR off the security fix, not main."]

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_
- **Change:** add missing boundary tests from Prerequisite Tests
- **Risk:** Low (tests only)
- **Test gate:** new tests pass; suite green
- **Rollback:** revert added test files

### Step 1 - [Verb + noun]
- **Change:** [what is added / extracted / moved]
- **Risk:** Low | Medium | High
- **Step kind:** refactor | coupled-fix
- **Test gate:** [component / hook / E2E / Server Action]
- **Hydration stance:** [Server Component | Client Component | unchanged | converting X -> Y]
- **Async stance:** [sync | async (Server Component) | unchanged]
- **Rollback:** [one git revert]

### Step 2 - [Verb + noun]
[Same structure. `coupled-fix` requires rationale for the coupling.]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `tsc --noEmit` + Vitest between every step
- [ ] No bundled unrelated cleanup
- [ ] One revert per step
- [ ] No silent Server <-> Client boundary changes; descendants audited
- [ ] No Client Component made `async`

## Out of Scope

[Adjacent improvements explicitly NOT in this plan.]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed React (or accepted from parent); framework + version recorded
- [ ] Step 3 - target file(s) + tests read directly; sibling smells listed or section omitted; severity inversion flagged if applicable; smuggled bug-fix split or labeled `coupled-fix`
- [ ] Step 4 - Coverage Gate verdict using sharp boundaries; `Inadequate` refuses Steps 1+; happy-path-only -> `Inadequate`; prerequisite table rendered when Thin/Inadequate; Step 5 preview still produced under refusal
- [ ] Step 5 - smells classified using the catalog (component, hook, data fetching, state, Server Action, accessibility, test)
- [ ] Step 6 - blast radius stated
- [ ] Step 7 - `Primary recipe:` named; supporting recipes folded as sub-steps; spine <= ~8 steps or split into PRs; every step states Hydration + Async stance; behavior changes labeled `coupled-fix`; ordered low-risk first
- [ ] Step 8 - goal mapped to end state; no bundled cleanup

## Avoid

- Producing Steps 1+ when Coverage Gate is `Inadequate`
- Bundling behavior changes with refactor steps (use `coupled-fix` with rationale, or split the PR)
- "While we're here" unrelated cleanup; renames during a refactor
- Removing a `useEffect` without verifying surrounding logic preserves observable behavior - some effects compensate for genuinely external state
- Converting Client -> Server Component without auditing every descendant for hooks / events / browser APIs
- Moving `"use client"` toward the leaf without verifying the new root has no client-only imports
- Making a Client Component `async` - not supported
- Replacing `useEffect` fetching with TanStack Query when a Server Component parent could fetch instead (Next.js)
- Replacing prop drilling with context as a default - co-located state is often the right answer
- Replacing context with a state library without checking the dep is justified - a memoized context is often enough
- Refactoring a design-system primitive without a back-compat plan
- Replacing `getByTestId` with `getByRole` during a refactor - that's a test improvement, its own PR
