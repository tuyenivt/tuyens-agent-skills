---
name: task-react-implement
description: Implement React 19 / Next.js / Vite feature end-to-end - components, state, data, routing, forms, a11y, tests.
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## When to Use

Building a new React feature spanning components, state, data fetching, routing, and tests. Not for single-component edits, bug fixes (use `task-react-debug`), or refactors without new behavior.

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 2 and follow its mode contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit spec artifacts from this workflow.

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect`. Confirm React + (Next.js App Router | Vite + React Router); identify styling, state lib, test framework. Halt and ask if mismatched. Vite branch: skip Server Components / Server Actions, use client routing and client fetching.

**Step 3 - Gather.** Ask: feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints. UI-only feature: skip data and form steps. Existing components: read and compose, do not duplicate.

**Step 4 - Design.** Use skill: `react-component-patterns` + `react-routing-patterns`. If the feature embeds into a non-React host (Rails / Django / PHP page, jQuery shell) or composes with other apps (Module Federation, single-spa), additionally Use skill: `react-legacy-integration` for mount, hydration, and routing-boundary rules. Propose component tree with Server/Client boundaries (Next.js), file layout, routes. Request approval before code:

```
app/<feature>/(page.tsx | layout.tsx)            # Next.js route
components/<feature>/<Component>.tsx + .test.tsx
hooks/use<Hook>.ts + .test.ts
lib/<feature>/queries.ts | actions.ts
types.ts
```

**Step 5 - State.** Use skill: `react-state-patterns` (canonical for React-specific guidance) + `frontend-state-management` (framework-neutral; the React skill wins on conflict). Categorize each slice: **local** (one component, `useState`/`useReducer`), **shared** (small subtree, lifted state or scoped context), **global** (cross-feature, Zustand/Redux), **server** (TanStack Query/SWR), **URL** (`searchParams`), **form** (RHF + Zod). Filters and pagination belong in URL state; server data in TanStack Query; no server state in client stores.

**Step 6 - Data.** Use skill: `react-data-fetching` + `frontend-api-integration`. Define query keys, cache invalidation, loading/error/empty states, optimistic updates if needed.

**Step 7 - Components.** Use skill: `react-hooks-patterns` + `react-styling-patterns`. Next.js: Use skill: `react-nextjs-patterns`. Generate with named exports (default only for route pages), typed props (declare an `interface` once props >= 2; inline a single-prop type is fine), `"use client"` only where required.

**Step 8 - Forms.** Use skill: `frontend-form-handling` (skip if no forms). Validation, error display, submission protection, dirty tracking.

**Step 9 - A11y.** Use skill: `frontend-accessibility`. Audit to WCAG 2.1 AA: semantic HTML, keyboard nav, ARIA, focus management.

**Step 10 - Tests.** Use skill: `react-testing-patterns` + `frontend-testing-patterns`. Component tests (RTL), hook tests, integration with MSW. Assert behavior, not internals. List e2e candidates.

**Step 11 - Validate.** Run `npx tsc --noEmit`, lint, test. Fix failures before reporting.

## Output Format

```markdown
## Files Generated

Routes:      app/orders/page.tsx, app/orders/[id]/page.tsx
Components:  components/orders/OrderList.tsx (+ .test.tsx), OrderRow.tsx
Hooks:       hooks/useOrderFilters.ts (+ .test.ts)
Lib:         lib/orders/queries.ts, lib/orders/actions.ts
Types:       lib/orders/types.ts
Tests:       (covered above) + e2e/orders.spec.ts (candidate)

## Component Tree

<Root> (Server | Client)
├── <ChildA> (Server | Client)
└── <ChildB> (Client)

## State Map

| State | Category | Owner | Mechanism |
| ----- | -------- | ----- | --------- |
| ...   | local/shared/global/server/URL/form | ... | useState / Zustand / TanStack Query / searchParams / RHF |

## Endpoints / Queries

| Method | Path | Query Key | Loading | Error | Empty |
| ------ | ---- | --------- | ------- | ----- | ----- |

## Tests

- Component: {count} (RTL)
- Hook: {count}
- Integration: {count} (MSW)
- E2E candidates: {list}
```

## Self-Check

- [ ] Step 1-2: behavioral principles loaded; stack confirmed (Next.js or Vite branch chosen)
- [ ] Step 3-4: requirements gathered; component tree and file layout approved before code
- [ ] Step 5: state categorized; URL state for filters/pagination; no server state in client stores
- [ ] Step 6: queries have keys, cache invalidation, and loading/error/empty states
- [ ] Step 7: TS strict, function components, `"use client"` only where needed, typed props interfaces
- [ ] Step 8: forms have validation, error display, submit protection, dirty tracking (if applicable)
- [ ] Step 9: WCAG 2.1 AA - semantic HTML, keyboard, ARIA, focus
- [ ] Step 10: tests assert behavior (RTL + MSW); critical paths flagged for e2e
- [ ] Step 11: `tsc --noEmit`, lint, tests pass

## Avoid

- `any` or suppressed TS errors; class components
- `"use client"` blanket-applied across a Next.js tree
- Fetching in `useEffect` without a data library
- Server state in Zustand/Redux - use TanStack Query
- Missing loading/error/empty states on data-fetching components
- Tests asserting internal state or method calls
- Generating code before design approval
