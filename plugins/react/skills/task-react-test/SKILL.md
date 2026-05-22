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

Stack-specific delegate of `task-code-test` for React / Next.js. Preserves the core workflow's output contract.

## When to Use

- Design a test strategy for a new React app, page, or feature
- Assess coverage gaps across unit / hook / component / integration / E2E layers
- Scaffold tests for under-covered components, hooks, Server Actions, or routes
- Review test pyramid balance for a React app

**Not for:** test failure debugging (`task-react-debug`), general code review (`task-react-review`), incident postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Apply behavioral principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm stack

Use skill: `stack-detect`. If invoked as a delegate of `task-code-test` (parent already detected React), accept the pre-confirmed stack. If stack is not React, stop and tell the user to invoke `/task-code-test`.

Record `Framework` (Next.js App Router / Pages Router / Vite + React Router), `Runner` (Vitest / Jest), `React: <version>` for the output.

### Step 3 - Apply spec-aware mode (conditional)

If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, Use skill: `spec-aware-preamble`. Generate one test per acceptance criterion (`// Satisfies: AC<N>` or test-name suffix), cover every NFR from `plan.md`, refuse tests for out-of-scope behavior. Never edit spec artifacts; surface gaps as proposed amendments.

### Step 4 - Read code under test and existing tests

Before producing output, read both production code and a representative sample of tests so output matches project convention.

- Target module: component shape (Server vs Client), props, hooks, data fetching, event handlers
- One component test, one hook test (if any), one Playwright spec, setup files (`vitest.setup.ts`, `playwright.config.ts`)
- `vitest.config.{js,ts}` / `jest.config.{js,ts}`: `setupFiles`, `testEnvironment`, path aliases, coverage thresholds
- `src/test/setup.ts`: MSW `setupServer`, `@testing-library/jest-dom` matchers, shared `renderWithProviders`
- Next.js: providers in `app/**/layout.tsx` (auth, theme, query client) that tests must replicate

Greenfield (no existing tests): state choices explicitly, do not invent silently. Defaults: Vitest + RTL + `user-event`; MSW with `onUnhandledRequest: 'error'`; Playwright for journeys; `vitest-axe`; `renderWithProviders` in `src/test/render.tsx`; factories in `src/test/factories/`.

Use skill: `react-testing-patterns` for canonical React test forms (`renderWithProviders`, MSW handler reset, `next/navigation` mock, Server Action flavors, React 19 form primitives, TanStack Query isolation).

### Step 5 - React test pyramid

| Layer       | Tooling                                                                      | What belongs here                                                            |
| ----------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Unit        | Vitest + plain functions                                                     | Utilities, reducers, selectors, Zod validators                               |
| Hook        | Vitest + `renderHook` + provider wrapper                                     | Custom hooks - state transitions, effect cleanup, return shape               |
| Component   | Vitest + RTL + `user-event` + MSW                                            | Component rendering, interaction, a11y - mount, click, type, assert visible  |
| Integration | Vitest + RTL + MSW + router (`next/navigation` mock or `MemoryRouter`)       | Multi-component flows on a page - filter list, multi-step form               |
| E2E         | Playwright                                                                   | Critical journeys - signup, checkout, payment, multi-page flows              |
| Visual      | Chromatic / Percy / Playwright screenshots                                   | Visual regression on stable components (opt-in, gated to `main`)             |

**Many** unit + component, **some** integration, **few** E2E.

**Server Components.** RTL renders Client Components in jsdom; Server Components are async functions that return JSX before client lifecycle. Two paths: (a) test the **data function** the Server Component calls (`getOrders()`) as a unit test; (b) test the **rendered route** via Playwright. Do not import a Server Component into RTL.

### Step 6 - Apply React test patterns

**Queries and interactions:** `getByRole` / `getByLabelText` / `getByText`; `getByTestId` only as last resort. `await userEvent.click(...)` over `fireEvent` (real focus, key, dispatch). Async: `await screen.findBy*` or `waitFor`, never `setTimeout`.

**Provider wrapping:** one shared `renderWithProviders(ui, options)` helper wraps router, QueryClient, theme, auth. Fresh `QueryClient` per call (`retry: false`, `gcTime: 0`) so cache does not leak. See `react-testing-patterns` for canonical shape.

**MSW for HTTP:**

- `setupServer(...handlers)` in `src/test/setup.ts`; `server.listen({ onUnhandledRequest: 'error' })`
- `server.resetHandlers()` in `afterEach` so per-test overrides do not leak (order-dependent failures otherwise)
- Per-test overrides: `server.use(http.get('/api/orders', () => HttpResponse.json(...)))`

**Server Action tests (Next.js).** Run both flavors when the action has validation AND a UI surface:

- _Direct unit:_ `await updateProfile(formData)` with constructed `FormData`. Mock session wrapper. Assert validation error shape, authz rejection, happy-path mutation.
- _Component wiring:_ `vi.mock('./actions', () => ({ createOrder: vi.fn() }))`. After `userEvent.click(submit)`, assert action called with expected args. Pair with `useFormStatus` / `useOptimistic` checks.

**React 19 form primitives:**

- `useFormStatus`: mock the action to resolve after a tick; assert in-flight UI (`aria-disabled`, spinner) via `findByRole`, then resolved state via `waitFor`.
- `useOptimistic`: assert the optimistic row appears **before** awaiting the action; mock a rejection; assert rollback (row disappears, error toast). Rollback branch is the most under-tested - do not skip.
- `use()` data unwrapping: not testable through RTL when consumed by a Server Component - test the data function in unit, verify via Playwright.

**TanStack Query:** fresh `QueryClient` per test via `renderWithProviders`; `retry: false`; assert refetched UI after `useMutation` resolves (or spy on `invalidateQueries`).

**`next/navigation` mock (App Router):** stub `useRouter` / `useSearchParams` / `usePathname` at module level; capture `push` spy for navigation assertions. Pages Router uses `next/router` - match the project's existing pattern.

**Error tracker mock:** `vi.mock('@sentry/nextjs', () => ({ captureException: vi.fn(), ... }))`; assert capture on error paths; `vi.clearAllMocks()` in `beforeEach`.

**Playwright E2E:** critical journeys only; `getByRole` / `getByLabel` over `data-testid`; auth via `storageState` fixture; API stubbing via `page.route`; run against built app (`pnpm build && pnpm start`), not dev mode.

### Step 7 - Test boundaries

**Unit:** pure utilities (formatters, parsers, currency math), reducers / state machines, Zod validators (edge cases, refinements), selectors with logic.

**Hook:** every custom hook with state transition or external integration; subscriptions / intervals / observers (assert cleanup); non-trivial effect deps.

**Component:** every interactive component (form, modal, dropdown, menu, dialog, tabs); empty / loading / error branches; conditional rendering (auth-gated, flag-gated); a11y (label association, keyboard nav, focus).

**Integration:** filter + list (filter updates list, URL syncs, deep link); multi-step wizards (see below); optimistic-update flows (mutate → see UI → rollback on error).

**Multi-step form / wizard.** A single integration test walks the full path; focused component tests cover each step's validation. Cover:

- Forward: valid step N advances to N+1; submit disabled until validation passes
- **Backward preserves state:** step 1 → 2 → back → fields still populated (most-broken in practice)
- Cross-step validation: a step-3 field depending on a step-1 value recomputes after back-edit
- Cancel / reset clears state; "Save Draft" persists separately
- Submit calls the Server Action with merged payload from all steps

State-machine wizards (XState, Zustand, `useReducer`): unit-test the machine separately; the component test asserts wiring, not transitions.

**E2E:** auth / onboarding journey, checkout / payment, critical multi-page contracts, real-navigation flows (intercepting / parallel routes).

**Does NOT need a test:** framework behavior (`next/link`, `useState`, Next.js routing); typed props with no logic; trivial wrappers covered by parents; visual layout (margin, padding) - belongs to visual regression.

### Step 8 - Prioritize when coverage is low

When coverage is below ~50%, run this **before** scaffolding - choose what to scaffold first.

1. **P1 - Auth, money, Server Actions:** every mutating Server Action (validation + authz + happy); auth flows (signup, login, reset, session expiry); checkout / billing / refund.
2. **P2 - Forms and validation:** every form with validation; multi-step wizards (completion + back-preserves-state).
3. **P3 - Empty / error / loading:** every list / data view with empty + skeleton + error; error boundaries catch and surface recovery.
4. **P4 - High-churn:** files with frequent recent commits (`git log --since="3 months ago"`) or fix history (`git log --grep="fix"`).
5. **P5 - Plumbing:** pure presentation, simple wrappers - lowest risk.

**Multi-band rule.** When a target qualifies for multiple bands (e.g., checkout form is both P1 money and P2 form), file under the highest band and cover both axes (assert money path AND validation + back-nav).

### Step 9 - Test infrastructure hygiene

- [ ] Vitest `testEnvironment: 'jsdom'` for components / hooks; `'node'` for pure utilities
- [ ] `@testing-library/jest-dom` matchers registered in setup
- [ ] MSW `setupServer` with `onUnhandledRequest: 'error'`; `resetHandlers()` in `afterEach`
- [ ] `userEvent.setup()` per test (not module singleton)
- [ ] Strict TypeScript in tests; no `as any` in mocks; typed `vi.mock` factory shape
- [ ] Coverage (`v8` / `istanbul`) wired to CI with documented exclusions
- [ ] Playwright: `retries: 2` on CI / `0` locally; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] No real network (MSW unhandled fails); no real filesystem in component tests
- [ ] Visual regression gated to `main`-branch builds, not every PR
- [ ] Storybook 8+ if present: stories double as tests via `play` / `@storybook/experimental-addon-test` - propose when stories already exist; do not impose

## Output Format

**Which output:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / "test plan" / coverage < 50% without scaffold request -> Strategy Doc
- Multiple deliverables in one ask -> produce in order separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not silently drop one.
- Unclear -> Strategy Doc as default.

**Coverage Assessment:**

```markdown
## React Test Coverage Assessment

**Stack:** React <version> / TypeScript <version>
**Framework:** Next.js App Router <version> | Next.js Pages Router <version> | Vite + React Router <version>
**Runner:** Vitest | Jest
**Test framework:** Vitest, React Testing Library, `user-event`, MSW, Playwright

**Coverage gaps:**

- **Unit:** [utilities / reducers / validators without coverage]
- **Hook:** [custom hooks without coverage]
- **Component:** [interactive components without tests; missing empty / error / loading]
- **Integration:** [pages with multi-component flows lacking integration tests]
- **Server Action:** [actions without auth / validation / happy-path tests]
- **E2E:** [critical journeys without Playwright coverage]
- **Accessibility:** [routes without `axe` checks; interactive elements without keyboard / focus tests]

**Pyramid balance:** Unit + Hook [n] / Component + Integration [n] / E2E [n - keep small]

**Prioritization** _(when coverage < ~50% or > 5 gaps)_

1. P1 - Auth / money / Server Actions: [list]
2. P2 - Forms / validation / wizards: [list]
3. P3 - Empty / error / loading: [list]
4. P4 - High-churn: [files]
5. P5 - Plumbing: [list]
```

**Test Scaffolds:** ready-to-run Vitest / Playwright files using project conventions. Each scaffold:

- Right test type (unit / hook / component / integration / E2E)
- Factories for data (no raw object literals)
- User-centric queries (`getByRole` / `getByLabel`); `userEvent`, not `fireEvent`
- Component: happy + error + empty + loading + a11y (`axe` at route level)
- Hook: state transitions + effect cleanup + edge cases
- Server Action: unit flavor (validation + authz + happy) AND component flavor (`vi.mock` wiring) when both apply
- React 19 forms: `useFormStatus` in-flight assertion via slow-promise mock; `useOptimistic` rollback branch
- E2E: full journey, `storageState` for auth, `page.route` for API stubs
- Strict TS; typed `vi.mock` factories; no `as any`

**Strategy Doc:**

```markdown
## React Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit + Hook {x}% / Component + Integration {y}% / E2E {z}%
**Tooling:** Vitest, React Testing Library, `user-event`, MSW, Playwright, `vitest-axe`
**Mocking:** MSW for network; provider wrappers for context; `vi.mock` reserved for non-network module mocks
**Server Component strategy:** [data function in unit; Playwright for rendered route]
**Concurrency:** Vitest `--pool=threads`; Playwright sharded across workers
**Gaps to close (prioritized):**

1. [Highest-risk gap, typically auth / Server Action / money path]
2. [...]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded before any other step
- [ ] Step 2 - Stack confirmed as React; `Framework`, `Runner`, `React` recorded
- [ ] Step 3 - Spec-aware mode honored when `--spec` passed (one test per AC, NFR coverage, no out-of-scope tests)
- [ ] Step 4 - Code under test, a sample of existing tests, and setup files read directly; `react-testing-patterns` consulted
- [ ] Step 5 - Pyramid mapped to React idioms; Server Component strategy explicit (data function + Playwright, not RTL)
- [ ] Step 6 - Patterns applied: user-centric queries; `userEvent` over `fireEvent`; `findBy*` / `waitFor` for async; MSW `resetHandlers` in `afterEach`; `renderWithProviders` with fresh `QueryClient`; Server Action both flavors when both apply; `useFormStatus` pending + `useOptimistic` rollback covered; `next/navigation` mocked for App Router
- [ ] Step 7 - Boundaries respected (no E2E for what a component test covers; framework internals not tested); multi-step wizard covers forward + backward-preserves-state + cross-step + submit
- [ ] Step 8 - Risk bands applied when coverage is low; multi-band targets covered on both axes
- [ ] Step 9 - Infra hygiene checks pass (MSW `onUnhandledRequest: 'error'` + `resetHandlers`, fresh `userEvent.setup()`, no real network, strict TS)

## Avoid

- Scaffolding without reading existing tests + setup files - imports wrong factory, duplicates the render helper
- Chasing coverage % over risk - 100% lines with no Server Action validation misses the bigger threat
- E2E for what a component test covers - context cost compounds across the suite
- Testing implementation details (render counts, internal state shape, lifecycle calls) - breaks on every refactor
- `getByTestId` as default - escape hatch, not the entry point; user-centric queries reflect real users
- `fireEvent` over `userEvent` - skips focus, key dispatch, real interaction behavior
- Mocking React internals (`vi.mock('react', ...)`) - signals the test asserts framework behavior
- Snapshot tests for visual layout - churn on every restyle; reserve for stable contracts (HTML renderer output)
- Rendering a Server Component in RTL - leads to mocking React internals; test the data function or use Playwright
- Skipping Server Action tests because "they're just functions" - validation, authz, side effects must be exercised
- Real network in component tests - flaky and slow; MSW with `onUnhandledRequest: 'error'` enforces the boundary
- Sharing mutable fixtures across tests - leaks state, order-dependent failures
- Asserting CSS class names (`toHaveClass('text-red-500')`) - couples tests to styling; assert visible behavior or a11y properties
- `as any` to silence TypeScript in mocks - defeats strict mode; use typed `vi.mock` factories
- `setTimeout` / arbitrary sleep waits for async work - use `findBy*` / `waitFor`
