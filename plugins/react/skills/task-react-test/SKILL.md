---
name: task-react-test
description: React / Next.js test strategy and scaffolding: Vitest, React Testing Library, user-event, MSW, Playwright, Server Components, Server Actions.
agent: react-test-engineer
metadata:
  category: frontend
  tags: [react, typescript, vitest, react-testing-library, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

# React Test

Test strategy and scaffolding for React / Next.js.

## When to Use

- Design a test strategy for a new React app, page, or feature
- Assess coverage gaps across unit / hook / component / integration / E2E layers
- Scaffold tests for under-covered components, hooks, Server Actions, or routes
- Review test pyramid balance for a React app

**Not for:** test failure debugging, general code review (`task-react-review`).

## Workflow

### Step 1 - Apply behavioral principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept a pre-confirmed stack. If neither `Framework` nor an `Additional` entry is React, stop and name the detected stack so the user can invoke that stack's test workflow.

Record `Framework` (Next.js App Router / Pages Router / hybrid App + Pages Router / Vite + React Router) and `Runner` (Vitest / Jest) for the output; the React and TypeScript versions come from `package.json` in Step 3. In a polyglot repo `stack-detect` keys the primary stack on the root manifest and may list React only under `Additional`; when the request sits inside one package (a React app under `apps/<name>`), confirm React against that package's `package.json`, scope the run to it, and name it in the deliverable's `**Stack:**` line (`(package: apps/admin)`). Greenfield (no runner installed): record the Step 3 default suffixed `(greenfield default)`; an installed runner is kept, even with no tests written yet.

### Step 3 - Read code under test and existing tests

Before producing output, read both production code and a representative sample of tests so output matches project convention. Convention wins on naming, file layout, factories and helper imports. It does not win on the practices this skill's `Avoid` list names - an existing test using `fireEvent` or a full-tree snapshot is a reason to flag it, not to copy it.

- `package.json`: which testing packages are installed, and the React / framework / runner versions
- Target module: component shape (Server vs Client), props, hooks, data fetching, event handlers
- One component test, one hook test (if any), one Playwright spec, setup files (`vitest.setup.ts`, `playwright.config.ts`)
- `vitest.config.{js,ts}` / `jest.config.{js,ts}`: `setupFiles`, `test.environment` (Vitest) or `testEnvironment` (Jest), any project/workspace split, path aliases, coverage thresholds
- `src/test/setup.ts`: MSW `setupServer`, `@testing-library/jest-dom` matchers, shared `renderWithProviders`
- Next.js: providers in `app/**/layout.tsx` (App Router) or `pages/_app.tsx` (Pages); Vite: providers in `src/main.tsx` - whichever the app mounts, the render helper must replicate

Greenfield - or any single missing piece of tooling: state choices explicitly, do not invent silently. Defaults for what is missing: Vitest + RTL + `user-event`; MSW with `onUnhandledRequest: 'error'`; Playwright for journeys; `vitest-axe` (on Vitest 1+ it needs a `declare module "vitest"` augmentation for `toHaveNoViolations`, per `react-testing-patterns`); `renderWithProviders` in `src/test/render.tsx`; factories in `src/test/factories/`. On Jest the same plan maps as: `testEnvironment: 'jest-fixed-jsdom'` (MSW 2 needs the fetch globals stock `jest-environment-jsdom` strips; both install separately); `jest.fn` / `jest.mocked` / `jest.doMock` for their `vi.` forms; a `jest.mock` factory reads outer variables only if they are `mock`-prefixed and only lazily (`fn: (...a) => mockFn(...a)`), since Jest has no `vi.hoisted`; `jest.requireActual` where Vitest uses `importOriginal`; `advanceTimers: jest.advanceTimersByTime`; `@testing-library/jest-dom` (Vitest: `/vitest`); `jest-axe`; `--maxWorkers` for concurrency.

Use skill: `react-testing-patterns` for the canonical forms it actually defines: the provider wrapper, MSW handler reset, TanStack Query isolation via a fresh `QueryClient`, the mocked-import Server Action flavor, the four-state data-component requirement, the `axe(container)` a11y assertion, and timer-driven behavior (fake timers plus the `userEvent.setup({ advanceTimers })` wiring debounce and throttle hooks need). The `next/navigation` router harness and the React 19 form primitives are **not** in that skill - Step 5 below is their only source.

When the project has a server surface (an ORM client, `src/server/**`, Server Actions, Route Handlers, or Pages Router `pages/api/**` API routes), additionally Use skill: `react-server-testing` for database-backed integration tests, per-test isolation, Route Handler and Server Action tests, and the async-Server-Component testing boundary. Stated project constraints win over that skill's defaults (e.g., team rules out Testcontainers): follow the constraint and name the coverage forfeited.

### Step 4 - React test pyramid

| Layer       | Tooling                                                                      | What belongs here                                                            |
| ----------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Unit        | Vitest + plain functions                                                     | Utilities, reducers, selectors, Zod validators                               |
| Hook        | Vitest + `renderHook` + provider wrapper                                     | Custom hooks - state transitions, effect cleanup, return shape               |
| Component   | Vitest + RTL + `user-event` + MSW                                            | Component rendering, interaction, a11y - mount, click, type, assert visible  |
| Integration | Vitest + RTL + MSW + router (`next/navigation` mock or `MemoryRouter`)       | Multi-component flows on a page - filter list, multi-step form               |
| Server integration (when a server surface exists) | Vitest + Testcontainers (real DB, per `react-server-testing`); when the project rules Testcontainers out, a disposable schema on a local instance of the project's engine, migrated with the real migrations - per-test isolation still comes from truncation or rollback; what is forfeited is a hermetic environment and engine-version parity with production | Service functions, Server Actions (authorization first), Route Handlers |
| E2E         | Playwright                                                                   | Critical journeys - signup, checkout, payment, multi-page flows              |
| Visual      | Chromatic / Percy / Playwright screenshots                                   | Visual regression on stable components (opt-in, gated to `main`)             |

**Many** unit + component, **some** integration, **few** E2E.

**Server Components.** RTL renders Client Components and synchronous Server Components without server-only imports in jsdom; an async Server Component cannot be rendered there. For async ones, two paths: (a) test the **data function** it calls (`getOrders()`) directly - database-backed when it queries one (`react-server-testing`); (b) test the **rendered route** via Playwright. Do not render an async Server Component in RTL.

### Step 5 - Apply React test patterns

**Queries and interactions:** `getByRole` / `getByLabelText` / `getByText`; `getByTestId` only as last resort. `const user = userEvent.setup(); await user.click(...)` over `fireEvent` (real focus, key, dispatch). Async: `await screen.findBy*` or `waitFor`, never `setTimeout`.

**Provider wrapping:** one shared render helper with a fresh `QueryClient` per call, built as `new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })` - both options live under `queries`, and a flat object is silently ignored so the tests keep retrying. `react-testing-patterns` defines it as a one-argument `renderWithProviders(ui)` wrapping `QueryClientProvider` only; extend that signature to `(ui, options)` and add the router, theme and auth providers the project's own layout supplies, rather than assuming they are already there.

**`vi.mock` hoisting.** `vi.mock` is hoisted above the imports, so a factory that references an outer `const` throws "Cannot access before initialization". Put anything the factory needs inside `vi.hoisted(() => ({ ... }))` and read it from there. To vary behaviour per test, keep the hoisted `vi.mock` returning `vi.fn()`s and set them per test with `vi.mocked(fn).mockResolvedValue(...)`. Reach for `vi.doMock` plus a dynamic `await import()` only when the module's shape must differ at import time.

**MSW for HTTP:**

- `setupServer(...handlers)` in `src/test/setup.ts`; `server.listen({ onUnhandledRequest: 'error' })`
- `server.resetHandlers()` in `afterEach` so per-test overrides do not leak (order-dependent failures otherwise)
- Per-test overrides: `server.use(http.get('/api/orders', () => HttpResponse.json(...)))`

**Server Action tests (Next.js).** Run both flavors when the action has validation AND a UI surface:

- _Direct unit:_ `await updateProfile(formData)` with constructed `FormData` (`await updateProfile(initialState, formData)` when the action is wired through `useActionState`). Mock the session wrapper, plus `next/cache` (and `next/headers` when the action reads cookies or headers) - both throw outside a request. When a server surface exists, the action runs against the real test database per `react-server-testing`, which overrides `react-testing-patterns`' DB mock. Assert validation error shape, authz rejection, happy-path mutation. Intentionally anonymous action: replace the authz case with its actual guard (uniqueness, rate limit, idempotency key) and say so. Action ending in `redirect()`: it throws `NEXT_REDIRECT`. Pick one strategy, not both - either leave `redirect` real and assert `await expect(action(fd)).rejects.toThrow(/NEXT_REDIRECT/)`, or mock `next/navigation` and assert the `redirect` spy was called with the expected path (a mocked `redirect` returns `undefined` and throws nothing).
- _Component wiring:_ `vi.mock('./actions', () => ({ createOrder: vi.fn() }))`. After `await user.click(submit)`, assert action called with expected args. Pair with `useFormStatus` / `useOptimistic` checks.

**React 19 form primitives:**

- `useFormStatus`: it reads the **ancestor** `<form>` submitted through `action={fn}`, so render the component inside that form (not an `onSubmit` form) or `pending` is `false` forever and the assertion passes without testing anything. Hold the mocked action on a deferred promise; assert in-flight UI (`aria-disabled`, spinner) via `findByRole`; resolve it; then assert the resolved state.
- `useOptimistic`: the optimistic value only survives while the transition is pending, so hold the mocked action on an unresolved promise, assert the row appears, then resolve. It reverts when the action settles either way, so a rejection test asserts the row disappears *and* that the component surfaced the failure - have the action return an error state rather than throw, or the rejection reaches the nearest boundary instead. The rollback branch is the most under-tested; do not skip it.
- `use()` data unwrapping: the common shape is a Server Component passing an unawaited promise to a Client Component that calls `use()`, and that **is** RTL-testable - render the client component with a promise prop inside `<Suspense>`. Only the Server Component half needs the data-function test plus Playwright.

**TanStack Query:** fresh `QueryClient` per test via the render helper; `retry: false`; assert the refetched UI after `useMutation` resolves rather than spying on `invalidateQueries` - the visible result is the contract.

**SWR:** isolate the cache per test with `<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>` in the render helper; without it one test's cache answers the next test's hook before its fetch resolves.

**React Router data routes:** a `loader` (reads) or `action` (mutates) is the SPA's data surface. Test it through `createMemoryRouter` + `RouterProvider` (plain `MemoryRouter` does not run them), or call it directly as `loader({ request: new Request('http://localhost/orders?status=open'), params: {}, context: {} })` (an absolute URL - `new Request('/orders')` throws in Node). In framework mode `createRoutesStub([{ path, Component, loader, action }])` supplies router context to a component under test; it runs only the loader / action passed in, not the route module's exports. A route with neither (a component-only route, eager or `lazy`) is tested by rendering the router at that path and asserting the page resolves.

**Router harness:** App Router - stub `next/navigation` (`useRouter` / `useSearchParams` / `usePathname`) at module level; capture `push` spy for navigation assertions. Pages Router uses `next/router` - match the project's existing pattern. React Router (Vite) - wrap in `MemoryRouter`, or `createMemoryRouter` + `RouterProvider` when routes use loaders/actions (plain `MemoryRouter` does not run them).

**Error tracker mock:** a factory replaces the whole module, so keep the rest of it:

```ts
vi.mock("@sentry/nextjs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sentry/nextjs")>()),
  captureException: vi.fn(),
}));
```

On Jest: `jest.mock("@sentry/nextjs", () => ({ ...jest.requireActual("@sentry/nextjs"), captureException: jest.fn() }))`. Assert capture on error paths; `vi.resetAllMocks()` in `beforeEach` (or `mockReset: true`) when tests set per-test implementations, `clearAllMocks` only when none do.

**E2E runner:** Playwright below. A project already standardised on Cypress keeps it - the boundaries and the journey list are the same; only the API differs, and switching runners is not this workflow's call.

**Playwright E2E:** critical journeys only; `getByRole` / `getByLabel` over `data-testid`; auth via `storageState` fixture; API stubbing via `page.route` for requests the browser makes (a Next server-side fetch never reaches it - stub the upstream behind its env-configured base URL); run against the built app via a `webServer` block, not dev mode - `next build && next start` on Next, `vite build && vite preview` on Vite.

### Step 6 - Test boundaries

**Unit:** pure utilities (formatters, parsers, currency math), reducers / state machines, Zod validators (edge cases, refinements), selectors with logic.

**Hook:** every custom hook with state transition or external integration; subscriptions / intervals / observers (assert cleanup); non-trivial effect deps.

**Component:** every interactive component (form, modal, dropdown, menu, dialog, tabs); empty / loading / error branches; conditional rendering (auth-gated, flag-gated); a11y (label association, keyboard nav, focus).

**Integration:** filter + list (filter updates list, URL syncs, deep link); multi-step wizards (see below); optimistic-update flows (mutate -> see UI -> rollback on error).

**Multi-step form / wizard.** A single integration test walks the full path; focused component tests cover each step's validation. Cover:

- Forward: valid step N advances to N+1; submit disabled until validation passes
- **Backward preserves state:** step 1 -> 2 -> back -> fields still populated (most-broken in practice)
- Cross-step validation: a step-3 field depending on a step-1 value recomputes after back-edit
- Cancel / reset clears state; "Save Draft" persists separately
- Submit calls the Server Action with merged payload from all steps

State-machine wizards (XState, Zustand, `useReducer`): unit-test the machine separately - export the reducer if private; when the project won't export it, cover transitions through the component test and say so.

**E2E:** auth / onboarding journey, checkout / payment, critical multi-page contracts, real-navigation flows (intercepting / parallel routes).

**Does NOT need a test:** framework behavior (`next/link`, `useState`, Next.js routing); typed props with no logic; trivial wrappers covered by parents; visual layout (margin, padding) - belongs to visual regression.

### Step 7 - Prioritize when coverage is low

Run this **before** scaffolding whenever coverage is thin - more than five uncovered targets (files or functions) found while reading in Step 3, or a coverage report showing under ~50%. No step here runs the coverage tool, so when no report exists judge by the target count and say which signal you used.

1. **P1 - Auth, money, mutating server calls:** every mutating Server Action, Route Handler / API route, React Router `action`, or API-client mutation that writes or grants access (validation + authz + happy); auth flows (signup, login, reset, session expiry); checkout / billing / refund.
2. **P2 - Forms and validation:** every form with validation; multi-step wizards (completion + back-preserves-state).
3. **P3 - Empty / error / loading:** every list / data view with empty + skeleton + error; error boundaries catch and surface recovery.
4. **P4 - High-churn:** files with frequent recent commits (`git log --since="3 months ago"`) or fix history (`git log --grep="fix"`); with too little history for either signal, write `no history signal` rather than guessing.
5. **P5 - Plumbing:** pure presentation, simple wrappers - lowest risk.

**Multi-band rule.** When a target qualifies for multiple bands (e.g., checkout form is both P1 money and P2 form), file under the highest band and cover both axes (assert money path AND validation + back-nav). Empty bands are skipped, not padded; when P1 is empty, list P4 fix-history targets first, keeping their `P4` label, then the rest in band order. A broken existing test on a banded target (Coverage Assessment `Broken tests`) is listed in that band too.

### Step 8 - Test infrastructure hygiene

- [ ] `vitest-axe` typed through a `declare module "vitest"` augmentation when it is used
- [ ] Runner environment key - `test.environment` on Vitest, `testEnvironment` on Jest (`jest-fixed-jsdom` with MSW) - set to a DOM environment for components / hooks and `node` for pure utilities; split them with a `// @vitest-environment node` comment per file, or `test.projects` on Vitest 3.2+ (`vitest.workspace.ts` before that)
- [ ] `@testing-library/jest-dom` matchers registered in setup
- [ ] MSW `setupServer` with `onUnhandledRequest: 'error'`; `resetHandlers()` in `afterEach`
- [ ] `userEvent.setup()` per test (not module singleton)
- [ ] Strict TypeScript in tests; no `as any` in mocks; typed `vi.mock` / `jest.mock` factory shape
- [ ] Coverage (`v8` / `istanbul`) wired to CI with documented exclusions
- [ ] Playwright: `retries: 2` on CI / `0` locally at top level; `use: { trace: 'on-first-retry' }` and `storageState` under `use` (per project), not as bare top-level keys
- [ ] No real network (MSW unhandled fails); no real filesystem in component tests
- [ ] Visual regression gated to `main`-branch builds, not every PR
- [ ] Storybook if present: stories double as tests via `play` plus `@storybook/addon-vitest` on Storybook 9+ (`@storybook/experimental-addon-test` on 8.x) - propose when stories already exist; do not impose

## Output Format

**Which output:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment (Step 5 pattern detail is reference-only; Step 7 bands drive the output)
- "write tests for X" / "scaffold tests" -> Test Scaffolds (Step 5 pattern detail is load-bearing)
- "test strategy" / "test plan", or thin coverage per Step 7 with no scaffold request -> Strategy Doc
- Multiple deliverables in one ask -> produce in order separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not silently drop one.
- Unclear -> Strategy Doc as default.

Precedence when one ask matches several rows: an explicit verb ("write/scaffold" -> Scaffolds; "strategy/plan" -> Strategy Doc) wins over the coverage-threshold heuristic. "Review coverage" combined with low coverage (no scaffold/strategy verb) is one ask matching two rows: lead with the Coverage Assessment - its Prioritization block already answers "what to write first" - and append the Strategy Doc only if a forward plan was also requested.

The formats below are the only envelope; consulted atomics' own output blocks (e.g., `react-testing-patterns`' Testing Plan) stay internal. Every deliverable ends with a `**Notes:**` line for application defects found while reading that are not test problems (a card number persisted to `localStorage`, an XSS sink), each naming the workflow that owns it; `none` when there are none. Two exceptions. When Step 3 loaded `react-server-testing` during an assessment ask, append its Server Test Assessment block after the Coverage Assessment, separated by `---`, and do not repeat under `Server Action` / `Server integration` any gap that block already lists - cite it instead. And when reviewing coverage turns up a defect in an **existing** test (a `vi.mock` factory that cannot run, a missing provider wrapper, an unhandled request), that is not a coverage gap: list it under `**Broken tests:**` in the Coverage Assessment with its `file:line` and what it fails to assert.

**Coverage Assessment:**

```markdown
## React Test Coverage Assessment

**Stack:** React <version> / TypeScript <version> _(from `package.json` in Step 3; `not detected` for either; `(package: <path>)` when scoped in Step 2)_

**Framework:** Next.js App Router <version> | Next.js Pages Router <version> | Next.js hybrid App + Pages Router <version> | Vite + React Router <version>

**Runner:** Vitest | Jest _(suffix `(greenfield default)` when none is installed)_

**Tooling present:** <the testing packages actually in `package.json`, read in Step 3; name the missing ones as gaps rather than asserting them>

**Broken tests:** [existing tests, or the setup files they share, that do not assert what they appear to (a broken test that is a layer's only coverage leaves that layer's gap open too), or that use an idiom this skill's `Avoid` list names (`fireEvent`, full-tree snapshots, `getByTestId` as the entry point), with `file:line`; `none`. On a Scaffolds or Strategy ask, report these in a short `## Broken tests` block ahead of the deliverable rather than dropping them.]

**Coverage gaps:**

- **Unit:** [utilities / reducers / validators without coverage]
- **Hook:** [custom hooks without coverage]
- **Component:** [interactive components without tests; missing empty / error / loading]
- **Integration:** [pages with multi-component flows lacking integration tests]
- **Server Action:** [actions without auth / validation / happy-path tests; omit on Vite and on a Pages-Router-only app, which have none]
- **Server integration:** [service functions / Route Handlers without DB-backed tests; omit when no server surface]
- **E2E:** [critical journeys without <E2E runner> coverage]
- **Accessibility:** [forms and dialogs without an `axe` assertion; routes without an `@axe-core/playwright` (or `cypress-axe`) scan; interactive elements without keyboard / focus tests]

**Pyramid balance:** Unit + Hook [n files] / Component + Integration [n files] / Server integration [n files] / E2E [n files - keep small] / Visual [n files]

_Counts are test files found by globbing the suite (`**/*.{test,spec}.*`, plus the Playwright and Cypress directories) - a cheap enumeration separate from Step 3's sample read. Write `unknown` for a tier you did not enumerate._

**Prioritization** _(on the Step 7 trigger: >5 gaps, or a report under ~50%)_

1. P1 - Auth / money / mutating server calls: [list]
2. P2 - Forms / validation / wizards: [list]
3. P3 - Empty / error / loading: [list]
4. P4 - High-churn: [files, or `no history signal`]
5. P5 - Plumbing: [list]

**Notes:** [application defects outside testing, each with `file:line` and its owning workflow; `none`]
```

**Test Scaffolds:** open with `## React Test Scaffolds` (preceded by `## Broken tests` when there are any) and one line naming `Framework` / `Runner` / `React` / `TypeScript`, then any missing setup files (render helper, MSW server, setup file) and the dev dependencies to install, then ready-to-run <Runner> / <E2E runner> files using project conventions, ordered by Step 7 band with the band on each file's heading when Step 7 ran, and end with the `**Notes:**` line. The render helper wraps the project's own data layer (a `QueryClientProvider`, an `SWRConfig`, or both). Each scaffold:

- Right test type (unit / hook / component / integration / E2E)
- Factories for data (no raw object literals)
- User-centric queries - `getByRole` / `getByLabelText` in RTL, `getByRole` / `getByLabel` in Playwright; `userEvent`, not `fireEvent`
- Data-fetching component or hook: the four states `react-testing-patterns` requires (loading, success, empty, error); a form or dialog: an `axe` assertion (`vitest-axe` / `jest-axe` against the render container; route-level scans need `@axe-core/playwright` in E2E)
- Hook: state transitions + effect cleanup + edge cases
- Server Action: unit flavor (validation + authz + happy) AND component flavor (`vi.mock` wiring) when both apply
- React 19 forms: `useFormStatus` in-flight assertion via slow-promise mock; `useOptimistic` rollback branch
- E2E: full journey, `storageState` / `cy.session` for auth, `page.route` / `cy.intercept` for browser-side API stubs
- Strict TS; typed `vi.mock` / `jest.mock` factories; no `as any`

**Strategy Doc:**

```markdown
## React Test Strategy

**Stack:** React <version> / TypeScript <version> / <Framework> / Runner: <Runner> _(Step 2 record; greenfield defaults suffixed)_

**Objective:** [what this strategy achieves]

**Pyramid balance:** the same five tiers as the Coverage Assessment, in test-file counts - target shape is many unit + component, some integration, few E2E

**Tooling:** <Runner>, React Testing Library, `user-event`, MSW, <E2E runner>, `vitest-axe` or `jest-axe` _(installed tools, greenfield defaults suffixed `(greenfield default)`)_

**Setup:** [missing infra to install and wire - runner config, setup file, render helper, CI step; `in place` when none]

**Mocking:** MSW for network; provider wrappers for context; `vi.mock` / `jest.mock` reserved for non-network module mocks

**Server Component strategy:** [data function in unit; Playwright for rendered route | n/a - no server surface]

**Concurrency:** Vitest parallelises by file already (`forks` pool by default; tune `maxWorkers` / `fileParallelism`, `fileParallelism: false` on a DB-backed project); Jest uses `--maxWorkers` (`--runInBand` on a DB-backed project). Playwright uses `workers` within a machine and `--shard` across machines

**Gaps to close (prioritized):** _(Step 7's bands, so the two deliverables rank the same way)_

1. P1 - Auth / money / mutating server calls: [list]
2. P2 - Forms / validation / wizards: [list]
3. P3 - Empty / error / loading: [list]
4. P4 - High-churn: [files, or `no history signal`]
5. P5 - Plumbing: [list]

_Empty bands are skipped, not padded._

**Skip (does not need tests):** [Step 6 exclusions applied to this repo]

**Rollout:** [phase order for incremental adoption; omit when adopting all at once]

**Notes:** [application defects outside testing, each with `file:line` and its owning workflow; `none`]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded before any other step
- [ ] Step 2 - Stack confirmed as React (against the package's own manifest in a monorepo); `Framework` and `Runner` recorded
- [ ] Step 3 - Code under test, a sample of existing tests, and setup files read directly; React / TypeScript versions recorded from `package.json` (`not detected` where absent); `react-testing-patterns` consulted; `react-server-testing` consulted when the project has an ORM client, `src/server/**`, Server Actions, Route Handlers or `pages/api/**` routes
- [ ] Step 4 - Pyramid mapped to React idioms; async Server Component strategy explicit (data function + Playwright, not RTL)
- [ ] Step 5 - Patterns applied: user-centric queries; `userEvent` over `fireEvent`; `findBy*` / `waitFor` for async; MSW `resetHandlers` in `afterEach`; `renderWithProviders` with fresh `QueryClient`; Server Action both flavors when both apply; `useFormStatus` pending + `useOptimistic` rollback covered; `next/navigation` mocked for App Router
- [ ] Step 6 - Boundaries respected (no E2E for what a component test covers; framework internals not tested); multi-step wizard covers forward + backward-preserves-state + cross-step + submit
- [ ] Step 7 - Risk bands applied when coverage is low; multi-band targets covered on both axes
- [ ] Step 8 - Infra hygiene checks pass (MSW `onUnhandledRequest: 'error'` + `resetHandlers`, fresh `userEvent.setup()`, no real network, strict TS, runner environment key, coverage wired, Playwright keys under `use`)
- [ ] Output Format - the router selected the deliverable(s) the ask calls for, in the stated order, with the precedence rule applied to a multi-row ask; the `react-server-testing` block appended when its exception fired; `**Notes:**` line present

## Avoid

- Scaffolding without reading existing tests + setup files - imports wrong factory, duplicates the render helper
- Chasing coverage % over risk - 100% lines with no Server Action validation misses the bigger threat
- E2E for what a component test covers - context cost compounds across the suite
- Testing implementation details (render counts, internal state shape, lifecycle calls) - breaks on every refactor
- `getByTestId` as default - escape hatch, not the entry point; user-centric queries reflect real users
- `fireEvent` over `userEvent` - skips focus, key dispatch, real interaction behavior
- Mocking React internals (`vi.mock('react', ...)`) - signals the test asserts framework behavior
- Snapshot tests for visual layout - churn on every restyle; reserve for stable contracts (HTML renderer output)
- Rendering an async Server Component in RTL - leads to mocking React internals; test the data function or use Playwright. `react-testing-patterns` shows an `await Component({...})` call; this workflow and `react-server-testing` both override it - do not scaffold that shape
- Skipping Server Action tests because "they're just functions" - validation, authz, side effects must be exercised
- Real network in component tests - flaky and slow; MSW with `onUnhandledRequest: 'error'` enforces the boundary
- Sharing mutable fixtures across tests - leaks state, order-dependent failures
- Asserting CSS class names (`toHaveClass('text-red-500')`) - couples tests to styling; assert visible behavior or a11y properties
- `as any` to silence TypeScript in mocks - defeats strict mode; use typed `vi.mock` factories
- `setTimeout` / arbitrary sleep waits for async work - use `findBy*` / `waitFor`
