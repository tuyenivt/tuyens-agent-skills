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

Building a new React feature spanning components, state, data fetching, routing, and tests. Not for single-component edits, bug fixes, or refactors without new behavior.

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect` - it reports the framework, test framework and ORM. Read the repo directly for what it does not emit: `app/` vs `pages/` vs `vite.config.*` to tell the router, and `package.json` for the styling and state libraries and for the React and TypeScript versions. Halt and ask if the detected stack contradicts the request. Vite branch: skip Server Components / Server Actions, use client routing and client fetching.

**Step 3 - Gather.** Needed: feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints. Ask only for items the request leaves unanswered; when the brief answers everything, proceed without questions. When nobody can answer - the requester is unreachable and no one else is authorized - do not stall: record each unanswered item in `## Open Questions`, proceed to Step 4 on stated assumptions, and let Step 4's approval gate decide whether the run continues. UI-only feature: skip data and form steps. Existing components: read and compose, do not duplicate.

**Step 4 - Design.** Use skill: `react-component-patterns` + `react-routing-patterns`. If the feature embeds into a non-React host (Rails / Django / PHP page, jQuery shell) or composes with other apps (Module Federation, single-spa), additionally Use skill: `react-legacy-integration` for mount, hydration, and routing-boundary rules. Propose component tree with Server/Client boundaries (Next.js), file layout, routes. Request approval before code: an explicit OK, or a pre-authorization in the request (conditional pre-approval counts when you verify its conditions hold - record the decision as an `Approval:` line in the design). No approval and requester unavailable: stop after the design. The fence shows the Next.js convention; on Vite follow the repo's existing route / feature layout. When Step 6 loads `react-server-data-layer`, its `src/server/<module>` placement wins over `lib/<feature>/` for data and action code:

```
app/<feature>/page.tsx                           # Next.js route segment
app/<feature>/layout.tsx                         # only when the segment needs one
app/<feature>/loading.tsx + error.tsx            # required once the segment fetches or can fail
components/<feature>/<Component>.tsx + .test.tsx
hooks/use<Hook>.ts + .test.ts
lib/<feature>/queries.ts + actions.ts            # or src/server/<module>/ - see below
lib/<feature>/types.ts
```

`react-routing-patterns` makes `loading.tsx` and `error.tsx` mandatory for any segment that fetches or can fail, so a data-backed feature generates both. When Step 6 loads `react-server-data-layer`, database access moves to `src/server/<module>/` and the `Lib:` output line names that path. The `"use server"` action file stays at `app/<feature>/actions.ts` and delegates into it - that boundary is the point of the split.

**Step 5 - State.** Use skill: `react-state-patterns` (canonical for React-specific guidance) + `frontend-state-management` (framework-neutral; the React skill wins on conflict). Categorize each slice with this enum - it governs the State Map even where a loaded skill's own category list differs: **local** (one component, `useState`/`useReducer`), **shared** (small subtree, lifted state or scoped context), **global** (cross-feature, Zustand/Redux), **server** (TanStack Query/SWR), **URL** (`useSearchParams()` in Client Components; the awaited `searchParams` prop in a Server Component page), **form** (RHF + Zod). Filters and pagination belong in URL state; server data in TanStack Query; no server state in client stores.

**Step 6 - Data.** Use skill: `react-data-fetching` + `frontend-api-integration`. Define query keys, cache invalidation, loading/error/empty states. Optimistic updates: with TanStack Query use the cancel/snapshot/set/rollback/settle mutation flow; with a Server Action over a server-rendered (RSC) list, pass the server data into a Client Component, wrap it in `useOptimistic`, and let the action's `revalidatePath`/`revalidateTag` reconcile the canonical list on re-render. The optimistic setter must be called inside the action or a transition - outside one React discards the value - and the optimistic state reverts when the action settles, success included, so the revalidate has to land the real value. `react-hooks-patterns` (Step 7) owns the hook's rules; read it here if the feature is optimistic. A list rendered by a Server Component is `server` category with mechanism `RSC fetch` (not TanStack Query) in the State Map.

If the feature touches an ORM client, a schema file, or a `src/server/` module - or adds one - additionally Use skill: `react-server-data-layer` for the client singleton, the server-only boundary, service-layer placement, cache scope, and the shape every Server Action must follow: **authorize the caller, validate the input with a schema, delegate to the service layer, then revalidate**. Authorization comes first - `react-server-data-layer` comments its example `// authorize before anything` and `react-nextjs-patterns` calls `requireUser()` before `safeParse`. None of the four is optional: missing authorization is a Blocker, and a missing schema, a bypassed service layer and a missing revalidate are each High.

**Step 7 - Components.** Use skill: `react-hooks-patterns` + `react-styling-patterns`. Next.js: Use skill: `react-nextjs-patterns`. Generate with named exports for components. App Router special files take a **default** export - `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `template.tsx`, `default.tsx`, `global-error.tsx` - with one exception: `route.ts` takes named exports per HTTP method (`export async function GET`), and Next errors on a default export there. Follow `react-component-patterns` on prop typing (inline for one or two props, an `interface` past that). `"use client"` only where required.

**Step 8 - Forms.** Use skill: `frontend-form-handling` (skip if no forms). Validation, error display, submission protection, dirty tracking.

**Step 9 - A11y.** Use skill: `frontend-accessibility`. Audit to WCAG 2.1 AA: semantic HTML, keyboard nav, ARIA, focus management.

**Step 10 - Tests.** Use skill: `react-testing-patterns` + `frontend-testing-patterns`. Component tests (RTL), hook tests, integration with MSW. Assert behavior, not internals. List e2e candidates. When Step 6 loaded `react-server-data-layer`, additionally Use skill: `react-server-testing` for database-backed tests of the service functions and the authorization cases on every Server Action added.

**Step 11 - Validate.** Run `npx tsc --noEmit`, lint, test. Fix failures before reporting. When the environment cannot run them, never claim a pass: say so, list the exact commands for the user to run, and report the feature as unvalidated.

## Output Format

**Two deliverables, by how far the run got.** When Step 4's approval gate stops the run (no approval and the requester is unavailable), the deliverable is the design alone: run Steps 5 and 6 as design work, then emit `Approval: withheld - <who was asked, why they could not answer>`, a `## Open Questions` list of what Step 3 could not resolve, the proposed file layout under `## Files Planned` (same shape as `## Files Generated`), and the `## Component Tree`, `## State Map` and `## Endpoints / Queries` blocks as *proposed*. Emit no code and no `## Tests`, and stop there.

Otherwise the deliverable is the code plus this block. Output blocks defined by the loaded atomic skills are working material - do not emit them. A section with no entries keeps its heading with a single `none` line. Server Actions appear in the Endpoints / Queries table as Method `action`, Path the module path, the revalidation target (`revalidatePath /orders`) in the Query Key column, the pending UI under Loading, the returned error state under Error, and `n/a` under Empty.

```markdown
Approval: <"explicit OK from <who>", or "pre-authorized by <source>; conditions verified: <which>">

## Files Generated

Routes:      app/orders/page.tsx, app/orders/[id]/page.tsx, app/orders/loading.tsx, app/orders/error.tsx

Components:  components/orders/OrderList.tsx (+ .test.tsx), OrderRow.tsx

Hooks:       hooks/useOrderFilters.ts (+ .test.ts)

Lib:         lib/orders/queries.ts, lib/orders/actions.ts

Types:       lib/orders/types.ts

Tests:       (covered above) + e2e/orders.spec.ts (candidate)

Other:       <every touched file outside the categories above - middleware.ts, a nav link, an existing component's prop surface, a schema migration; `none` when there are none>

## Component Tree

```text
{Root} ({Server | Client})
|- {ChildA} ({Server | Client})
`- {ChildB} ({Server | Client})
```

## State Map

| State | Category | Owner | Mechanism |
| ----- | -------- | ----- | --------- |
| ...   | local \| shared \| global \| server \| URL \| form | ... | useState \| useReducer \| lifted state or scoped context \| Zustand \| Redux Toolkit \| TanStack Query \| SWR \| RSC fetch \| useSearchParams \| awaited searchParams prop \| RHF |

## Endpoints / Queries

| Method | Path | Query Key | Loading | Error | Empty |
| ------ | ---- | --------- | ------- | ----- | ----- |

## Validation

- <the result of Step 11's `tsc --noEmit`, lint and test run; when the environment cannot run them, say so and list the exact commands, and mark the feature unvalidated>

## Open Questions

- <items Step 3 could not resolve that the build proceeded past on stated assumptions; `none`>

## Notes

- <anything the behavioral principles require surfacing that is not a generated file: a contradiction between the request and the code, a pre-existing defect encountered, a convention the repo states but does not follow. `none` when there is nothing.>

## Tests

- Component: {count} (RTL; single-component, even when MSW stubs HTTP)
- Hook: {count}
- Integration: {count} (MSW; multi-component flows)
- Server (DB-backed): {count} _(`n/a` when Step 10 did not load `react-server-testing`)_
- Accessibility: {count} _(the `axe` assertions `react-testing-patterns` requires on every form and dialog, written in Step 10)_
- E2E candidates: {list}
```

## Self-Check

- [ ] Step 1-2: behavioral principles loaded; stack confirmed (Next.js or Vite branch chosen)
- [ ] Step 3-4: requirements gathered (asked only for unanswered items; unanswerable ones recorded as Open Questions); when the feature embeds into a non-React host or composes with another app, `react-legacy-integration` was loaded; design approved before code, recorded on the `Approval:` line - or the run stopped after the design and emitted the design-only deliverable
- [ ] Step 5: state categorized; URL state for filters/pagination; no server state in client stores
- [ ] Step 6: queries have keys, cache invalidation, and loading/error/empty states; when the feature touched an ORM client, a schema, or `src/server/`, `react-server-data-layer` was loaded and every Server Action validates, authorizes, delegates, then revalidates
- [ ] Step 7: `"use client"` only where needed; components named-exported and App Router special files default-exported; props typed per `react-component-patterns`
- [ ] Step 8: forms have validation, error display, submit protection, dirty tracking (if applicable)
- [ ] Step 9: WCAG 2.1 AA - semantic HTML, keyboard, ARIA, focus
- [ ] Step 10: tests assert behavior (RTL + MSW); critical paths flagged for e2e; when Step 6 loaded `react-server-data-layer`, `react-server-testing` was loaded and every added Server Action has an authorization test
- [ ] Step 11: `tsc --noEmit`, lint, tests pass - or reported unvalidated with the exact commands when the environment cannot run them; recorded under `## Validation`

## Avoid

- `any` or suppressed TS errors; class components anywhere except an error boundary, which React still has no function equivalent for
- `"use client"` blanket-applied across a Next.js tree
- Fetching in `useEffect` without a data library
- Server state in Zustand/Redux - use TanStack Query
- Missing loading/error/empty states on data-fetching components
- Tests asserting internal state or method calls
- Generating code before design approval
