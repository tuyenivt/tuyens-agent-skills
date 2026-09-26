---
name: task-react-implement
description: Implement Next.js 16 App Router / React 19 feature end-to-end - components, state, data, routing, forms, a11y, tests.
metadata:
  category: frontend
  tags: [react, typescript, nextjs, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## When to Use

Building a new feature in a Next.js 16 App Router project, spanning components, state, data fetching, routing, and tests. Not for single-component edits, bug fixes, or refactors without new behavior.

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect` - it reports the framework, test framework and ORM. Read the repo for the rest: `app/` or `src/app/` with a root layout is the App Router; `package.json` gives the `next`, React and TypeScript versions and the styling and state libraries. In a polyglot repo `stack-detect` keys the primary stack on the root manifest and may list React only under `Additional`; when the request sits inside one package (a React app under `apps/<name>`), confirm React against that package's `package.json` and build in its layout - a request spanning two packages follows each one's. Any other framework - a Next.js project with `pages/` alone, or a non-Next React build - prints `task-react-implement covers Next.js App Router projects only; <project framework> is out of scope.` and stops here, before any other branch. A declared `next` < 16.3 or `react` < 19 puts `<package> <declared> is below the plugin floor (Next.js 16.3, React 19); output targets Next.js 16.3 and React 19 - upgrade first.` under `## Notes` (`<package>` is `Next.js` or `React`; both below is one line, `Next.js 15.5 and React 18.3 are below the plugin floor ...`), and the run continues. `<declared>` is the version the lockfile resolves for `next` / `react`, else the lower bound of the `package.json` range (`^16.1.0` -> `16.1.0`). Record the full version, not the major. Halt and ask if the detected stack contradicts the request; when nobody can answer, record the contradiction under `## Open Questions` and stop at the design-only deliverable.

**Step 3 - Gather.** Needed: feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints. Ask only for items the request leaves unanswered; when the brief answers everything, proceed without questions. When nobody can answer - the requester is unreachable and no one else is authorized - do not stall: record each unanswered item in `## Open Questions`, proceed to Step 4 on stated assumptions, and let Step 4's approval gate decide whether the run continues. UI-only feature: skip data and form steps. Existing components: read and compose, do not duplicate.

**Step 4 - Design.** Use skill: `react-component-patterns` + `react-nextjs-patterns` (routing, special files, Server Actions, validation; loaded once here for every later step). Propose component tree with Server/Client boundaries, file layout, routes. Request approval before code: an explicit OK, or a pre-authorization in the request (conditional pre-approval counts when you verify its conditions hold - record the decision as an `Approval:` line in the design). No approval and requester unavailable: run Steps 5-6 as design only, emit the design-only deliverable (Output Format), and stop. A missing test runner or test library the feature needs is part of the design (named, with what it adds), not installed unasked in Step 10. The fence shows the Next.js convention; wherever the repo already has a layout for the same kind of file (flat `src/server/*.ts` modules, say), follow the repo. When Step 6 loads `react-server-data-layer`, its `src/server/` placement wins over `lib/<feature>/` for data-access code:

```
app/<feature>/page.tsx                           # Next.js route segment
app/<feature>/layout.tsx                         # only when the segment needs one
app/<feature>/loading.tsx + error.tsx            # error.tsx where it can fail, loading.tsx where it fetches
app/<feature>/@<slot>/default.tsx                # every parallel-route slot - a missing one fails the build
components/<feature>/<Component>.tsx + .test.tsx
hooks/use<Hook>.ts + .test.ts
app/<feature>/actions.ts                         # "use server" actions
lib/<feature>/queries.ts                         # or src/server/ - see below
lib/<feature>/types.ts
```

`react-nextjs-patterns` puts an error boundary where a segment can fail and a loading UI where it fetches; a segment's own `error.tsx` does not catch its own `layout.tsx`, so a fetching layout needs the parent's. When Step 6 loads `react-server-data-layer`, database access moves to `src/server/` and the `Lib:` output line names that path. The `"use server"` action file stays at `app/<feature>/actions.ts` and delegates into it - that boundary is the point of the split.

**Step 5 - State.** Use skill: `react-state-patterns` (canonical for React-specific guidance) + `frontend-state-management` (framework-neutral; the React skill wins on conflict). Categorize each slice with this enum - it governs the State Map even where a loaded skill's own category list differs: **local** (one component, `useState`/`useReducer`), **shared** (small subtree, lifted state or scoped context), **global** (cross-feature, Zustand / Jotai / Redux Toolkit, or app-wide Context for identity), **server** (TanStack Query / SWR / RTK Query, or an RSC fetch), **URL** (`useSearchParams()` in Client Components; the awaited `searchParams` prop in a Server Component page), **form** (RHF + Zod, or `useActionState` + a shared Zod schema for a Server Action form). Filters and pagination belong in URL state; server data in its server mechanism (RSC fetch or a server-cache library); never hand-copied into Zustand, Redux slices or Context.

**Step 6 - Data.** Use skill: `react-data-fetching` + `frontend-api-integration`. Define query keys, cache invalidation, loading/error/empty states. Name the caching model on the Output Format's `Caching model:` line: with `cacheComponents` set in `next.config`, cached reads are `"use cache"` functions with `cacheLife` / `cacheTag`, and uncached request data outside `<Suspense>` fails the build; without it, a route using no Request-time API is prerendered at build with the data fetched then, so per-request data needs `await connection()` or a Request-time API, and caching is opt-in (`cache: 'force-cache'`, `next: { revalidate, tags }`). Optimistic updates: with TanStack Query use the cancel/snapshot/set/rollback/settle mutation flow; with a Server Action over server-rendered (RSC) data, pass the server data into a Client Component, wrap it in `useOptimistic`, and let the action reconcile it - `updateTag(tag)` or `revalidatePath`, never `revalidateTag(tag, 'max')`, which serves stale data so the optimistic value reverts to it; `refresh()` (`next/cache`) re-renders the client router without expiring any cache, so it lands the real value only for uncached data. Revalidate every route that renders the changed value, not only the list page. The optimistic setter must be called inside the action or a transition - outside one React discards the value - and the optimistic state reverts when the action settles, success included, so the revalidate has to land the real value. `react-hooks-patterns` (Step 7) owns the hook's rules; read it here if the feature is optimistic. A list rendered by a Server Component is `server` category with mechanism `RSC fetch` (not TanStack Query) in the State Map.

If the feature touches an ORM client, a schema file, or a `src/server/` module - or adds one - additionally Use skill: `react-server-data-layer` for the client singleton, the server-only boundary, service-layer placement and cache scope. Every Server Action or Route Handler the feature adds, ORM or not, follows one order: **authorize the caller, validate the input with a schema** (`react-nextjs-patterns`, loaded at Step 4), **delegate to the service layer** (`react-server-data-layer`, loaded for any added entry point that writes), **then revalidate** whatever cached or rendered surface the write changed. Missing authorization on a mutating entry point is a Blocker and missing validation High; a bypassed service layer is High.

**Step 7 - Components.** Use skill: `react-hooks-patterns` + `react-styling-patterns` + `frontend-performance` (images, lists, client bundle weight). Generate with named exports for components. App Router special files take a **default** export - `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `template.tsx`, `default.tsx`, `global-error.tsx`; a generated `error.tsx` / `global-error.tsx` takes `{ error, retry }` and calls `retry()` even when the repo's existing boundaries use `reset` - repo precedent does not override a floor API; `route.ts` takes named exports per HTTP method (`export async function GET`) - a default export there is not a handler (dev logs an error) and every method but the auto-answered `OPTIONS` returns 405. Type route props with the generated globals - `PageProps<'/orders/[id]'>` / `LayoutProps<'/orders'>` (`const { id } = await props.params`), a handler's context as `RouteContext<'/api/orders/[id]'>` - not hand-written `params` types. Follow `react-component-patterns` on prop typing (inline for one or two props; a named `interface` or `type` past that or once the shape is reused). `"use client"` only where required.

**Step 8 - Forms.** Use skill: `frontend-form-handling` (skip if no forms). Validation, error display, submission protection, dirty tracking.

**Step 9 - A11y.** Use skill: `frontend-accessibility`. Audit to WCAG 2.1 AA: semantic HTML, keyboard nav, ARIA, focus management.

**Step 10 - Tests.** Use skill: `react-testing-patterns` + `frontend-testing-patterns`. Component tests (RTL), hook tests, integration with MSW. Assert behavior, not internals. Test an async Server Component through its data function (Vitest and Jest cannot render one), mock Server Actions at their import in component tests (MSW cannot intercept them), and write the Playwright journey for an RSC + action flow when Playwright is installed or approved in the design - otherwise list it under E2E candidates. When the feature adds a server entry point (Step 6) or a `src/server/` module, additionally Use skill: `react-server-testing` for the authorization case on each and database-backed tests of the service functions.

**Step 11 - Validate.** Run `next typegen` (route types, the `PageProps` / `LayoutProps` / `RouteContext` globals, `next-env.d.ts`), then type-check with the repo's own script when one exists, else `tsc --noEmit` (with no `tsconfig.json` at all, say the type-check does not apply); then lint through the ESLint CLI (flat config, `eslint-config-next`) or Biome, and test, all through the detected package manager. `next lint` is removed and `next build` no longer lints: a `lint` script still calling `next lint` fails - run `eslint .` instead and name the `next-lint-to-eslint-cli` codemod under `## Notes`. Fix failures before reporting. When the environment cannot run them, never claim a pass: say so, list the exact commands for the user to run, and report the feature as unvalidated.

## Output Format

**Two deliverables, by how far the run got.** When Step 4's approval gate stops the run (no approval and the requester is unavailable), the deliverable is the design alone: run Steps 5 and 6 as design work, then emit `Approval: withheld - <who was asked, why they could not answer>`, a `## Open Questions` list of what Step 3 could not resolve, the proposed file layout under `## Files Planned` (same shape as `## Files Generated`, planned test files included), the `## Component Tree`, `## State Map` and `## Endpoints / Queries` blocks (its `Caching model:` line included) as *proposed*, and `## Notes` (an atomic's risk class carried with its severity word, `High: ActionBypassesService`), in that order. Emit no code and no `## Tests` count block, and stop there.

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

Other:       <every touched file outside the categories above - proxy.ts, a nav link, an existing component's prop surface, a schema migration; `none` when there are none>

## Component Tree

```text
{Root} ({Server | Client})
|- {ChildA} ({Server | Client})
`- {ChildB} ({Server | Client})
```

## State Map

| State | Category | Owner | Mechanism |
| ----- | -------- | ----- | --------- |
| ...   | local \| shared \| global \| server \| URL \| form | ... | useState \| useReducer \| useOptimistic \| lifted state or scoped context \| app-wide Context \| Zustand \| Jotai \| Redux Toolkit \| TanStack Query \| SWR \| RTK Query \| manual fetch + AbortController \| RSC fetch \| useSearchParams \| awaited searchParams prop \| RHF \| useActionState |

## Endpoints / Queries

| Method | Path | Query Key | Loading | Error | Empty |
| ------ | ---- | --------- | ------- | ----- | ----- |

Caching model: cacheComponents ("use cache" + cacheLife / cacheTag) | no cacheComponents (opt-in fetch caching)

## Validation

- <the result of Step 11's type-check (the command actually run), lint and test run, plus any migration or codegen the environment could not run; when the environment cannot run them, say so and list the exact commands, and mark the feature unvalidated>

## Open Questions

- <items Step 3 could not resolve that the build proceeded past on stated assumptions; `none`>

## Notes

- <anything the behavioral principles require surfacing that is not a generated file: the Step 2 below-floor line, a contradiction between the request and the code, a pre-existing defect encountered, a convention the repo states but does not follow. `none` when there is nothing.>

## Tests

- Component: {count} (RTL; single-component, even when MSW stubs HTTP)
- Hook: {count}
- Integration: {count} (MSW; multi-component flows)
- Server (DB-backed or action authorization): {count} _(`n/a` when Step 10 did not load `react-server-testing`)_
- Accessibility: {count} _(the `axe` assertions `react-testing-patterns` requires on every form and dialog, written in Step 10)_
- E2E: {count} written; candidates: {list}
````

## Self-Check

- [ ] Step 1-2: behavioral principles loaded; Next.js App Router confirmed (any other framework: the out-of-scope line printed and the run stopped before the contradiction check); a below-floor `next` / `react` recorded under `## Notes`
- [ ] Step 3-4: requirements gathered (asked only for unanswered items; unanswerable ones recorded as Open Questions); `react-component-patterns` + `react-nextjs-patterns` loaded; every parallel-route slot in the design has a `default.tsx`; design approved before code, recorded on the `Approval:` line - or Steps 5-6 ran as design only and the design-only deliverable was emitted
- [ ] Step 5: state categorized; URL state for filters/pagination; no server data hand-copied into client stores
- [ ] Step 6: caching model named on the `Caching model:` line; queries have keys, cache invalidation, and loading/error/empty states; `react-server-data-layer` loaded when the feature touched an ORM client, a schema, or `src/server/`; every added server entry point authorizes, validates, delegates, then revalidates whatever cached or rendered surface it changed
- [ ] Step 7: `"use client"` only where needed; components named-exported, App Router special files default-exported; generated `error.tsx` / `global-error.tsx` take `{ error, retry }` and call `retry()`, whatever the repo's existing boundaries use; route props typed with `PageProps` / `LayoutProps` / `RouteContext`; props typed per `react-component-patterns`; `frontend-performance` applied
- [ ] Step 8: forms have validation, error display, submit protection, dirty tracking (if applicable)
- [ ] Step 9: WCAG 2.1 AA - semantic HTML, keyboard, ARIA, focus
- [ ] Step 10: tests assert behavior (RTL + MSW); async Server Components tested through their data function; RSC + action journeys written in Playwright where it is installed or approved; when a server entry point or `src/server/` module was added, `react-server-testing` loaded and an authorization test on each
- [ ] Step 11: `next typegen`, then type-check, lint (ESLint CLI or Biome, not `next lint`), tests pass - or reported unvalidated with the exact commands when the environment cannot run them; recorded under `## Validation`
- [ ] Design-only run: Steps 5-6 checked against the proposed State Map and Endpoints; Steps 7-11 skipped

## Avoid

- `any` or suppressed TS errors; class components, error boundaries included - a component-level boundary is `catchError` from `next/error` (any other boundary - hand-rolled or `react-error-boundary` - swallows `redirect()` / `notFound()` unless it rethrows them)
- `"use client"` blanket-applied across a Next.js tree
- Fetching in `useEffect` without a data library
- Server data hand-copied into Zustand, Redux slices or Context - use a server-cache library
- Missing loading/error/empty states on data-fetching components
- Tests asserting internal state or method calls
- Generating code before design approval
