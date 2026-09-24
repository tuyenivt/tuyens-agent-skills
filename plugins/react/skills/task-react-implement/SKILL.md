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

**Step 2 - Detect stack.** Use skill: `stack-detect` - it reports the framework, test framework and ORM. Read the repo for the rest: on Next.js, `app/` or `src/app/` with a root layout is the App Router and `pages/` or `src/pages/` alone the Pages Router; otherwise `@react-router/dev` in `package.json`, `reactRouter()` in `vite.config.*` or `app/routes.ts` is React Router framework mode, else a Vite SPA; `package.json` gives the styling and state libraries and the React and TypeScript versions. In a polyglot repo `stack-detect` keys the primary stack on the root manifest and may list React only under `Additional`; when the request sits inside one package (a React app under `apps/<name>`), confirm React against that package's `package.json` and build in its layout - a request spanning two packages follows each one's. Halt and ask if the detected stack contradicts the request; when nobody can answer, record the contradiction under `## Open Questions` and stop at the design-only deliverable. Branches: **Next.js App Router** - the default below; **Next.js Pages Router** - no Server Components or Server Actions, data through `getServerSideProps` / `getStaticProps` and `pages/api/**` routes; **React Router framework mode / Remix** - route-module `loader` / `action` for data and writes, each `action` an endpoint under the Step 6 authorization rule; **Vite SPA** - client routing and client fetching.

**Step 3 - Gather.** Needed: feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints. Ask only for items the request leaves unanswered; when the brief answers everything, proceed without questions. When nobody can answer - the requester is unreachable and no one else is authorized - do not stall: record each unanswered item in `## Open Questions`, proceed to Step 4 on stated assumptions, and let Step 4's approval gate decide whether the run continues. UI-only feature: skip data and form steps. Existing components: read and compose, do not duplicate.

**Step 4 - Design.** Use skill: `react-component-patterns` + `react-routing-patterns`. If the feature embeds into a non-React host (Rails / Django / PHP page, jQuery shell) or composes with other apps (Module Federation, single-spa), additionally Use skill: `react-legacy-integration` for mount, hydration, and routing-boundary rules. Propose component tree with Server/Client boundaries (Next.js), file layout, routes. Request approval before code: an explicit OK, or a pre-authorization in the request (conditional pre-approval counts when you verify its conditions hold - record the decision as an `Approval:` line in the design). No approval and requester unavailable: run Steps 5-6 as design only, emit the design-only deliverable (Output Format), and stop. A missing test runner or test library the feature needs is part of the design (named, with what it adds), not installed unasked in Step 10. The fence shows the Next.js convention; on Vite, and wherever the repo already has a layout for the same kind of file (flat `src/server/*.ts` modules, say), follow the repo. When Step 6 loads `react-server-data-layer`, its `src/server/` placement wins over `lib/<feature>/` for data-access code:

```
app/<feature>/page.tsx                           # Next.js route segment
app/<feature>/layout.tsx                         # only when the segment needs one
app/<feature>/loading.tsx + error.tsx            # error.tsx where it can fail, loading.tsx where it fetches
components/<feature>/<Component>.tsx + .test.tsx
hooks/use<Hook>.ts + .test.ts
app/<feature>/actions.ts                         # "use server" actions
lib/<feature>/queries.ts                         # or src/server/ - see below
lib/<feature>/types.ts
```

`react-routing-patterns` puts an error boundary where a segment can fail and a loading UI where it fetches; a segment's own `error.tsx` does not catch its own `layout.tsx`, so a fetching layout needs the parent's. When Step 6 loads `react-server-data-layer`, database access moves to `src/server/` and the `Lib:` output line names that path. The `"use server"` action file stays at `app/<feature>/actions.ts` and delegates into it - that boundary is the point of the split.

**Step 5 - State.** Use skill: `react-state-patterns` (canonical for React-specific guidance) + `frontend-state-management` (framework-neutral; the React skill wins on conflict). Categorize each slice with this enum - it governs the State Map even where a loaded skill's own category list differs: **local** (one component, `useState`/`useReducer`), **shared** (small subtree, lifted state or scoped context), **global** (cross-feature, Zustand / Jotai / Redux Toolkit, or app-wide Context for identity), **server** (TanStack Query / SWR / RTK Query, an RSC fetch, or a React Router loader), **URL** (`useSearchParams()` in Client Components; the awaited `searchParams` prop in a Server Component page), **form** (RHF + Zod, or `useActionState` + a shared Zod schema for a Server Action form). Filters and pagination belong in URL state; server data in its server mechanism (RSC fetch, loader, or a server-cache library); never hand-copied into Zustand, Redux slices or Context.

**Step 6 - Data.** Use skill: `react-data-fetching` + `frontend-api-integration`. Define query keys, cache invalidation, loading/error/empty states. Optimistic updates: with TanStack Query use the cancel/snapshot/set/rollback/settle mutation flow; with a Server Action over server-rendered (RSC) data, pass the server data into a Client Component, wrap it in `useOptimistic`, and let the action reconcile it - `revalidatePath`, or `revalidateTag(tag)` on 15; on 16 `updateTag(tag)`, since `revalidateTag(tag, 'max')` serves stale data and the optimistic value reverts to it. Revalidate every route that renders the changed value, not only the list page. The optimistic setter must be called inside the action or a transition - outside one React discards the value - and the optimistic state reverts when the action settles, success included, so the revalidate has to land the real value. `react-hooks-patterns` (Step 7) owns the hook's rules; read it here if the feature is optimistic. A list rendered by a Server Component is `server` category with mechanism `RSC fetch` (not TanStack Query) in the State Map.

If the feature touches an ORM client, a schema file, or a `src/server/` module - or adds one - additionally Use skill: `react-server-data-layer` for the client singleton, the server-only boundary, service-layer placement and cache scope. Every server entry point the feature adds - Server Action, Route Handler, `pages/api` route, React Router `action` / `loader` - ORM or not, follows one order: **authorize the caller, validate the input with a schema** (`react-nextjs-patterns`, Use skill: on the Next.js branch, here rather than at Step 7), **delegate to the service layer** (`react-server-data-layer`, loaded for any added entry point that writes), **then revalidate** whatever cached or rendered surface the write changed. Missing authorization on a mutating entry point is a Blocker and missing validation High on every branch; a bypassed service layer is High.

**Step 7 - Components.** Use skill: `react-hooks-patterns` + `react-styling-patterns` + `frontend-performance` (images, lists, client bundle weight). Next.js: Use skill: `react-nextjs-patterns` if Step 6 did not load it. Generate with named exports for components. App Router special files take a **default** export - `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `template.tsx`, `default.tsx`, `global-error.tsx` - as does any module a route config loads as a route element (React Router route modules); `route.ts` takes named exports per HTTP method (`export async function GET`) - a default export there is not a handler (dev logs an error) and every method but the auto-answered `OPTIONS` returns 405. Follow `react-component-patterns` on prop typing (inline for one or two props; a named `interface` or `type` past that or once the shape is reused). `"use client"` only where required.

**Step 8 - Forms.** Use skill: `frontend-form-handling` (skip if no forms). Validation, error display, submission protection, dirty tracking.

**Step 9 - A11y.** Use skill: `frontend-accessibility`. Audit to WCAG 2.1 AA: semantic HTML, keyboard nav, ARIA, focus management.

**Step 10 - Tests.** Use skill: `react-testing-patterns` + `frontend-testing-patterns`. Component tests (RTL), hook tests, integration with MSW. Assert behavior, not internals. On the Next.js branch, test an async Server Component through its data function (`task-react-test` and `react-server-testing` override `react-testing-patterns`' await-the-component form), mock Server Actions at their import in component tests (MSW cannot intercept them), and write the Playwright journey for an RSC + action flow when Playwright is installed or approved in the design - otherwise list it under E2E candidates. When the feature adds a server entry point (Step 6) or a `src/server/` module, additionally Use skill: `react-server-testing` for the authorization case on each and database-backed tests of the service functions.

**Step 11 - Validate.** Type-check with the repo's own script when one exists, else `tsc -b` when the root `tsconfig.json` has `references` (the Vite template) or `tsc --noEmit` otherwise (with no `tsconfig.json` at all, say the type-check does not apply), after `next typegen` on Next 15.5+; then lint and test, all through the detected package manager. Fix failures before reporting. When the environment cannot run them, never claim a pass: say so, list the exact commands for the user to run, and report the feature as unvalidated.

## Output Format

**Two deliverables, by how far the run got.** When Step 4's approval gate stops the run (no approval and the requester is unavailable), the deliverable is the design alone: run Steps 5 and 6 as design work, then emit `Approval: withheld - <who was asked, why they could not answer>`, a `## Open Questions` list of what Step 3 could not resolve, the proposed file layout under `## Files Planned` (same shape as `## Files Generated`, planned test files included), the `## Component Tree`, `## State Map` and `## Endpoints / Queries` blocks as *proposed*, and `## Notes` (an atomic's risk class carried with its severity word, `High: ActionBypassesService`), in that order. Emit no code and no `## Tests` count block, and stop there.

Otherwise the deliverable is the code plus this block. In either deliverable, output blocks defined by the loaded atomic skills are working material - do not emit them. A section with no entries keeps its heading with a single `none` line. Server Actions appear in the Endpoints / Queries table as Method `action`, Path the module path, the revalidation target (`revalidatePath /orders`) in the Query Key column, the pending UI under Loading, the returned error state under Error, and `n/a` under Empty.

````markdown
Approval: <"explicit OK from <who>", or "pre-authorized by <source>; conditions verified: <which>">

## Files Generated

Routes:      app/orders/page.tsx, app/orders/[id]/page.tsx, app/orders/loading.tsx, app/orders/error.tsx

Components:  components/orders/OrderList.tsx (+ .test.tsx), OrderRow.tsx

Hooks:       hooks/useOrderFilters.ts (+ .test.ts)

Lib:         lib/orders/queries.ts, app/orders/actions.ts

Types:       lib/orders/types.ts

Tests:       (covered above) + e2e/orders.spec.ts

Other:       <every touched file outside the categories above - middleware.ts (proxy.ts on 16), a nav link, an existing component's prop surface, a schema migration; `none` when there are none>

## Component Tree

```text
{Root} ({Server | Client})
|- {ChildA} ({Server | Client})
`- {ChildB} ({Server | Client})
```

## State Map

| State | Category | Owner | Mechanism |
| ----- | -------- | ----- | --------- |
| ...   | local \| shared \| global \| server \| URL \| form | ... | useState \| useReducer \| useOptimistic \| lifted state or scoped context \| app-wide Context \| Zustand \| Jotai \| Redux Toolkit \| TanStack Query \| SWR \| RTK Query \| manual fetch + AbortController \| RSC fetch \| getServerSideProps / getStaticProps props \| React Router loader \| useSearchParams \| awaited searchParams prop \| RHF \| useActionState \| React Router action (useFetcher / useActionData) |

## Endpoints / Queries

| Method | Path | Query Key | Loading | Error | Empty |
| ------ | ---- | --------- | ------- | ----- | ----- |

## Validation

- <the result of Step 11's type-check (the command actually run), lint and test run, plus any migration or codegen the environment could not run; when the environment cannot run them, say so and list the exact commands, and mark the feature unvalidated>

## Open Questions

- <items Step 3 could not resolve that the build proceeded past on stated assumptions; `none`>

## Notes

- <anything the behavioral principles require surfacing that is not a generated file: a contradiction between the request and the code, a pre-existing defect encountered, a convention the repo states but does not follow. `none` when there is nothing.>

## Tests

- Component: {count} (RTL; single-component, even when MSW stubs HTTP)
- Hook: {count}
- Integration: {count} (MSW; multi-component flows)
- Server (DB-backed or action authorization): {count} _(`n/a` when Step 10 did not load `react-server-testing`)_
- Accessibility: {count} _(the `axe` assertions `react-testing-patterns` requires on every form and dialog, written in Step 10)_
- E2E: {count} written; candidates: {list}
````

## Self-Check

- [ ] Step 1-2: behavioral principles loaded; stack confirmed and one branch chosen (App Router, Pages Router, React Router framework mode, Vite SPA)
- [ ] Step 3-4: requirements gathered (asked only for unanswered items; unanswerable ones recorded as Open Questions); when the feature embeds into a non-React host or composes with another app, `react-legacy-integration` was loaded; design approved before code, recorded on the `Approval:` line - or Steps 5-6 ran as design only and the design-only deliverable was emitted
- [ ] Step 5: state categorized; URL state for filters/pagination; no server data hand-copied into client stores
- [ ] Step 6: queries have keys, cache invalidation, and loading/error/empty states; `react-server-data-layer` loaded when the feature touched an ORM client, a schema, or `src/server/`; every added server entry point authorizes, validates, delegates, then revalidates whatever cached or rendered surface it changed
- [ ] Step 7: `"use client"` only where needed; components named-exported, App Router special files and route modules default-exported; props typed per `react-component-patterns`; `frontend-performance` applied
- [ ] Step 8: forms have validation, error display, submit protection, dirty tracking (if applicable)
- [ ] Step 9: WCAG 2.1 AA - semantic HTML, keyboard, ARIA, focus
- [ ] Step 10: tests assert behavior (RTL + MSW); async Server Components tested through their data function; RSC + action journeys written in Playwright where it is installed or approved; when a server entry point or `src/server/` module was added, `react-server-testing` loaded and an authorization test on each
- [ ] Step 11: type-check, lint, tests pass - or reported unvalidated with the exact commands when the environment cannot run them; recorded under `## Validation`
- [ ] Design-only run: Steps 5-6 checked against the proposed State Map and Endpoints; Steps 7-11 skipped

## Avoid

- `any` or suppressed TS errors; class components anywhere except an error boundary, which React still has no function equivalent for
- `"use client"` blanket-applied across a Next.js tree
- Fetching in `useEffect` without a data library
- Server data hand-copied into Zustand, Redux slices or Context - use a server-cache library
- Missing loading/error/empty states on data-fetching components
- Tests asserting internal state or method calls
- Generating code before design approval
