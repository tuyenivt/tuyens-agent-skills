---
name: task-react-test
description: React test strategy and scaffolding using Vitest, React Testing Library, MSW for HTTP stubs, Playwright for E2E, and TypeScript strict-mode test typing. Detects Next.js App Router vs Vite + React Router and applies the right idioms (Server Component limitations, Server Action testing, App Router routing in tests). Use when designing a test plan, assessing coverage gaps, or scaffolding component / hook / route / E2E tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to React.
agent: react-test-engineer
metadata:
  category: frontend
  tags: [react, typescript, vitest, react-testing-library, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# React Test

## Purpose

React-aware test strategy and scaffolding using Vitest, React Testing Library (`@testing-library/react`), `@testing-library/user-event`, MSW (`msw`) for HTTP stubs, Playwright for E2E, and TypeScript strict-mode test typing. Replaces the generic frontend test patterns with React-specific guidance: user-centric queries (`getByRole`, `getByLabelText`), avoidance of implementation-detail tests (no `enzyme`-style shallow rendering), Server Component testing limitations (test via E2E or via the underlying data function, not via RTL), Server Action testing, and accessibility-as-tests.

This workflow is the stack-specific delegate of `task-code-test` for React. The core workflow's contract (output shape, prioritization rules) is preserved.

## When to Use

- Designing a test strategy for a new React app, page, or feature
- Assessing test coverage gaps across unit / component / integration / E2E layers
- Scaffolding tests for under-covered components, hooks, Server Actions, or routes
- Reviewing test pyramid balance for a React app
- Adding accessibility / boundary tests (validation, error states, empty states) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-react-debug`)
- General code review (use `task-code-review` / `task-react-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm React. If the detected stack is not React, stop and tell the user to invoke `/task-code-test` instead.

Detect framework: Next.js (App Router / Pages Router) vs Vite + React Router. Detect test runner: Vitest (preferred for Vite + modern Next.js) vs Jest (still common on older Next.js / CRA). Record `Framework: ...`, `Runner: Vitest | Jest`, `React: <version>` for the output. Each section that follows branches on this signal where the test idiom differs.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: component shape (Server vs Client), props, hooks used, data fetching, event handlers
- Glob `**/*.test.{ts,tsx}`, `**/*.spec.{ts,tsx}`, `e2e/**/*.spec.ts` and read at least: one existing component test, one existing hook test (if applicable), one existing Playwright E2E spec, test setup files (`vitest.setup.ts`, `playwright.config.ts`)
- Read `vitest.config.{js,ts}` / `jest.config.{js,ts}` for `setupFiles`, `testEnvironment` (`jsdom` for components, `node` for Node-only utilities), path aliases, coverage config
- Read `src/test/setup.ts` (or equivalent) for MSW server setup, `@testing-library/jest-dom` matchers extension, query client wrapper
- For Next.js: read `app/**/layout.tsx` and any auth provider / theme provider that components depend on - they must be wrapped in tests too

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - React Test Pyramid

The React test pyramid maps to test types:

| Layer       | Tooling                                                                  | What belongs here                                                                    |
| ----------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Unit        | Vitest + plain functions                                                 | Utility functions, reducers, selectors, formatters, validators (Zod schemas)         |
| Hook        | Vitest + `@testing-library/react` `renderHook`                           | Custom hooks in isolation - state transitions, effect side effects, return shape     |
| Component   | Vitest + RTL + `user-event` + MSW                                        | Component rendering, interaction, accessibility - mount, click, type, assert visible |
| Integration | Vitest + RTL + MSW + real router (Next.js test utilities / MemoryRouter) | Multi-component flows on a single page - filter list, submit form, see updated state |
| E2E         | Playwright                                                               | Critical user journeys - signup, checkout, payment, multi-page flows                 |
| Visual      | Playwright screenshots / Chromatic / Percy                               | Visual regression on key components (opt-in)                                         |

**Many** unit + component tests, **some** integration tests, **few** E2E tests.

> **Server Components are special.** RTL renders Client Components in jsdom; Server Components are async functions that return JSX before any client lifecycle runs. There is no canonical "render a Server Component in Vitest" path that gives you the rendered HTML the way Next.js does. Two practical strategies: (a) test the **data function** the Server Component calls (`getOrders()`) as a unit test, then trust Next.js to render JSX; (b) test the **rendered route** end-to-end via Playwright. Do not try to import a Server Component into RTL and assert on its output - that path leads to mocking React internals.

### Step 4 - Apply React Test Patterns

Use skill: `react-testing-patterns` for the canonical patterns referenced below.

**Unit tests (`*.test.ts`):**

- Vitest (`describe`, `it`, `expect`, `beforeEach`); `testEnvironment: 'node'` for pure-function tests when no DOM is involved
- Test the public function - one test per outcome (success, validation failure, edge case)
- TypeScript strict: avoid `as any`; use proper typed inputs

**Hook tests (`*.test.ts` with `renderHook`):**

- `import { renderHook, act } from '@testing-library/react'`
- `const { result, rerender } = renderHook(() => useFoo(arg), { wrapper: AllProviders })` - wrapper must include `QueryClientProvider`, theme, auth, etc. as the hook needs
- `act(() => result.current.setX(42))` for state updates; `await act(async () => ...)` for async
- Assert `result.current` shape after each transition; use `waitFor` for async settling
- Test cleanup: assert effects clean up via `unmount()` and check that intervals / subscriptions are torn down

**Component tests (`*.test.tsx`):**

- `import { render, screen } from '@testing-library/react'`; `import { userEvent } from '@testing-library/user-event'`
- **User-centric queries**: `getByRole('button', { name: /save/i })`, `getByLabelText(/email/i)`, `getByText(/welcome/i)`. Avoid `getByTestId` except as last resort - it tests implementation, not user-visible behavior
- **`userEvent` over `fireEvent`**: `await userEvent.click(button)` simulates real interaction (focus, key events, dispatching). `fireEvent.click` skips behavior real users trigger
- **Async assertions**: `await screen.findByText(...)` (built-in waitFor) for content that appears after a fetch / state transition; `expect(await screen.findByRole('alert')).toHaveTextContent(...)`
- Wrap in providers via a shared `renderWithProviders(ui, options)` helper - includes router (Next.js: mock or `next/navigation` test utilities; Vite: `MemoryRouter`), QueryClient, theme, auth context
- One test per `(component-state, user-action, assertion)` triple. Avoid testing every prop permutation - test the contract
- Accessibility: `expect(await axe(container)).toHaveNoViolations()` via `jest-axe` / `vitest-axe` for any route-level test; per-component tests at minimum assert that interactive elements have accessible names
- **Snapshot tests sparingly**: snapshots churn on every refactor; reserve for stable contract surfaces (e.g., a Markdown renderer's HTML output) - never for visual layout

**Integration tests (`*.test.tsx` with multiple components):**

- Render the page-level component with all real children; mock only the network via MSW
- Walk through the user flow: type into search, click filter, see filtered list - assertions at each user-visible step
- For Next.js App Router, mock `next/navigation` (`useRouter`, `useSearchParams`, `usePathname`) to control navigation in test; for Vite, use `MemoryRouter` with explicit initial entries

**MSW for HTTP:**

- `setupServer(...handlers)` in `src/test/setup.ts`; `server.listen({ onUnhandledRequest: 'error' })` to fail loud on missed stubs
- Handler per endpoint, not per test - tests override per-test via `server.use(http.get('...', resolver))`
- **Reset handlers in `afterEach`**: `server.resetHandlers()` removes per-test overrides so they do not leak. Without this, tests pass in isolation and fail in suite order. Goes in `vitest.setup.ts` next to `server.listen`
- Run MSW for both Vitest and Playwright (Playwright via `msw` browser worker or just point Playwright at a mocked backend)

**`renderWithProviders` helper (canonical shape):**

A shared helper avoids re-wrapping providers in every test and keeps test output comparable across the suite. Put it in `src/test/render.tsx`:

```tsx
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactElement, ReactNode } from "react";

interface ProviderOptions {
  queryClient?: QueryClient;
  // Add: theme, auth, router-state shape, etc. - based on what real layouts provide
}

export function renderWithProviders(
  ui: ReactElement,
  {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    }),
    ...renderOptions
  }: ProviderOptions & RenderOptions = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }
  return { queryClient, ...render(ui, { wrapper: Wrapper, ...renderOptions }) };
}
```

Tests then call `renderWithProviders(<OrderForm />)` and receive the standard RTL return plus the `queryClient` for assertion (e.g., `queryClient.getQueryData(['orders'])`). Each test gets a fresh client because the default factory runs per-call.

**Server Action tests (Next.js):**

There are two flavors. Run **both** when the action has both validation logic and a UI surface that calls it.

_Flavor 1 - Direct unit test of the action function:_

- Server Actions are async functions - test as a plain function: `const result = await updateProfile(formData)`
- Construct `FormData` in the test: `const fd = new FormData(); fd.set('name', 'Alice');`
- Mock the session: a wrapper around `auth()` that returns a fixture user; assert that unauthenticated calls reject before any DB / external call
- Assert validation: invalid input throws / returns the expected error shape; valid input mutates and returns the expected next state
- The DB layer is the boundary - either use a Testcontainers Postgres + real Prisma (slow, accurate) or stub the data layer per test. Match the project's existing approach

_Flavor 2 - Component test that mocks the action import:_

- The component imports the action: `import { createOrder } from './actions'`. Mock it: `vi.mock('./actions', () => ({ createOrder: vi.fn() }))`
- Assert the action was called with the expected arguments after a `userEvent.click` on the submit button - this verifies the wiring (form → action) without re-running the action's logic (which Flavor 1 already covered)
- Pair with `useFormStatus` / `useOptimistic` testing - see "React 19 form primitives" below

**React 19 form primitives in tests (`useOptimistic`, `useFormStatus`, `use()`):**

- `useFormStatus`: render the form, click submit, and during the in-flight period assert the submit button is `aria-disabled` / shows a spinner. Make the mocked action return a `Promise` that resolves after a tick so the in-flight UI is observable: `vi.mocked(createOrder).mockImplementation(() => new Promise(r => setTimeout(() => r({ ok: true }), 10)))`. Use `await screen.findByRole('button', { name: /submitting/i })` to wait for the in-flight state, then `await waitFor(() => expect(...))` for the resolved state
- `useOptimistic`: type the form, click submit, then **immediately** assert the optimistic UI shows ("Order #42 created") - before awaiting the action's resolution. After the action rejects (`vi.mocked(createOrder).mockRejectedValueOnce(new Error('boom'))`), assert the rollback (the optimistic row disappears, error toast shows). Optimistic rollback is the most under-tested branch; do not skip
- `use()` (data unwrapping): not testable through RTL when the consumer is a Server Component. Test the data function in unit; trust Next.js to feed it through the `use()` boundary; verify the rendered output via Playwright

**TanStack Query in tests:**

- Create a fresh `QueryClient` per test - shared clients leak cache across tests and produce order-dependent failures: `const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })`. Wrap the rendered component with `<QueryClientProvider client={queryClient}>` (do this in the `renderWithProviders` helper)
- Disable retries (`retry: false`) so error-state tests fail fast
- Assert `queryClient.invalidateQueries(...)` was called after a mutation - either via spying on the client or by asserting the refetched UI state after `useMutation` resolves

**`next/navigation` mock pattern (Next.js App Router component tests):**

- `next/navigation` hooks (`useRouter`, `useSearchParams`, `usePathname`) cannot run outside Next.js without a mock. Stub at module level:

  ```ts
  vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
    useSearchParams: () => new URLSearchParams(),
    usePathname: () => "/dashboard/orders",
  }));
  ```

- For tests that assert navigation, capture the spy: `const push = vi.fn(); vi.mocked(useRouter).mockReturnValue({ push, ... })`
- The Pages Router (`next/router`) has its own mock surface - check the existing `vitest.setup.ts` for the pattern the project uses

**`Sentry.captureException` mock (or any error-tracker):**

- `vi.mock('@sentry/nextjs', () => ({ captureException: vi.fn(), captureMessage: vi.fn(), setUser: vi.fn() }))`
- Assert `captureException` was called with the expected `Error` after the component's error path runs
- Reset mocks in `beforeEach` (`vi.clearAllMocks()`) to avoid cross-test bleed

**Playwright E2E (`e2e/*.spec.ts`):**

- Reserve for critical journeys: signup, checkout, multi-step forms, money flows
- One spec per journey, not per page
- Use `data-testid` only as a last-resort selector; prefer `getByRole` / `getByLabel` for resilience
- Auth setup via `storageState` fixture (login once, save state, reuse across tests) - fast and reliable
- API stubbing via `page.route('**/api/orders', route => route.fulfill({...}))` for tests asserting specific backend states without touching the real backend
- Run against a built app (`pnpm build && pnpm start` for Next.js) - dev mode has different behavior (HMR, source maps, dev-only error overlays)

### Step 5 - Test Boundaries (React-Specific)

**What deserves a unit test:**

- Pure utilities (formatters, parsers, date helpers, currency math)
- Reducers / state machines (XState, useReducer reducers)
- Validators (Zod schemas - test edge cases, custom refinements)
- Selectors (Redux / Zustand selectors with logic)

**What deserves a hook test:**

- Every custom hook with a state transition or external integration
- Hooks managing subscriptions, intervals, observers (assert cleanup)
- Hooks with non-trivial effect dependencies (verify effect re-runs on the right changes)

**What deserves a component test:**

- Every interactive component (form, modal, dropdown, menu, dialog, tabs, accordion)
- Empty / loading / error states - especially "no items" and "API failed" branches
- Conditional rendering paths (auth-gated UI, feature-flag-gated UI)
- Accessibility (label association, keyboard navigation, focus management)

**What deserves an integration test:**

- Filter + list interactions (filter changes update list, URL syncs, deep link works)
- Form flows (multi-step wizard, validation across steps)
- Optimistic-update flows (mutate → see immediate UI change → rollback on error)

**Multi-step form / wizard testing strategy:**

A single integration test that walks the full path (step 1 → 2 → 3 → submit) is the spine. Add focused component tests for each step's validation. Cover at minimum:

- **Forward navigation:** valid input on step N advances to step N+1; the submit button is disabled until each step's validation passes
- **Backward navigation preserves state:** step 1 → step 2 → back to step 1 → fields still populated. This is the most-broken behavior in practice
- **Cross-step validation:** a field on step 3 that depends on a step 1 value (e.g., shipping cost depends on item count) computes correctly when step 1 is edited via back-navigation
- **Cancel / reset:** discarding the wizard clears state; a "Save Draft" path persists state separately
- **Submit flow:** the final submit calls the Server Action with the accumulated form state from all steps; assert the action was called with the merged payload

For wizards using a state machine (XState, Zustand, `useReducer`), unit-test the machine separately - that is the lowest-overhead place to assert all the transitions. The component test then asserts the wiring, not the transitions.

**What deserves an E2E test:**

- Authentication and onboarding journey (signup, email verify, first-run)
- Checkout / payment journey
- Critical multi-page flows where contract between pages matters
- Routing flows that depend on real navigation (intercepting routes, parallel routes - Next.js)

**What does NOT need a test:**

- Framework-provided behavior: `next/link` navigation, `useState` correctness, Next.js routing - test your wiring, not the framework
- Generated boilerplate: typed props with no logic, simple wrapper components
- Trivial components: `<Button>` re-exporting a primitive with one prop change - covered by parents
- Visual layout details (margin, padding) - belongs to visual regression, not unit tests
- Pure presentation components in isolation if they have no logic - test via the parent that uses them

### Step 6 - Test Data and Fixtures

- Prefer factory utilities (`createUserFactory`, `@faker-js/faker` for primitives, or `fishery`) over hand-rolled object literals
- Co-locate factories with the schema / types they produce (`src/test/factories/user.ts`)
- For component tests: factories produce minimal valid props; tests override only the field under test
- For MSW handlers: factories produce response payloads matching the API contract
- Avoid mutating shared test fixtures - rebuild via factory in `beforeEach`
- Test data must be minimal and focused - 100-row `Array.from` setups in a component test signal the test belongs at integration / E2E

### Step 7 - Prioritization (when coverage is low)

If line / branch coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when accessibility regressions go untested while `<Button>` gets full coverage.

When starting from low test coverage, prioritize by React-specific risk:

**Priority 1 - Auth, money, and Server Actions:**

- Every Server Action mutating data: validation test + auth test + happy path
- Auth flows: signup, login, password reset, session expiry behavior
- Money / billing components: checkout, plan-change, refund

**Priority 2 - Forms and validation:**

- Every form with validation - test invalid inputs surface errors, valid inputs submit
- Multi-step wizards - completion path + back-navigation preserves state

**Priority 3 - Empty / error / loading states:**

- Every list / data view tested with empty state, loading skeleton, and error fallback
- Error boundaries test that thrown errors are caught and surface a recovery UI

**Priority 4 - High-churn components:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pure presentation, simple wrappers, plain styled components - lowest risk

### Step 8 - Test Infrastructure Hygiene

- [ ] Vitest `testEnvironment: 'jsdom'` for components / hooks; `'node'` for pure-utility tests; mixed via `// @vitest-environment node` directive when needed
- [ ] `@testing-library/jest-dom` matchers (`toBeInTheDocument`, `toBeVisible`, `toHaveAccessibleName`) registered in setup
- [ ] MSW `setupServer` with `onUnhandledRequest: 'error'` to fail loud on missed stubs
- [ ] `userEvent.setup()` per test (not module-level singleton); `await user.click(...)` consistently
- [ ] Cleanup: RTL `cleanup()` runs automatically (in modern setups); verify by checking for "leaked" elements between tests
- [ ] Strict TypeScript in tests: same `tsconfig.json`; no `as any` shortcuts; typed RTL queries via custom render helper
- [ ] Coverage tool (`v8` / `istanbul` via Vitest) wired to CI with per-package thresholds; coverage exclusions documented
- [ ] Playwright config: `retries: 2` on CI for flake tolerance, `0` locally; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] No real network calls (assert MSW unhandled fails the test); no real filesystem (`fs.writeFile` in component tests is a smell)
- [ ] CI runs Vitest + Playwright in parallel; Playwright sharded across workers for speed
- [ ] Visual regression (if used): Chromatic / Percy / Playwright screenshots gated to `main`-branch builds, not every PR (cost vs signal)
- [ ] Storybook integration (if Storybook 8+ is in repo): stories doubling as tests via `play` functions (`@storybook/test`) or the Vitest-Storybook integration (`@storybook/experimental-addon-test`) - reuses interaction logic across docs and CI without duplicating the setup. Worth proposing when stories already exist for the components the user wants to scaffold tests for; do not impose if the project does not already use Storybook

## React Review Checklist

Quick-reference checklist for reviewing existing React tests:

- [ ] Test type matches what is being tested (component → RTL, hook → renderHook, journey → Playwright)
- [ ] Queries are user-centric (`getByRole`, `getByLabel`); `getByTestId` only as last resort
- [ ] `userEvent` over `fireEvent` for user interactions
- [ ] No tests of implementation details (state internals, lifecycle method counts, render counts)
- [ ] Async assertions use `findBy*` / `waitFor` - no `setTimeout` waits
- [ ] MSW handlers cover the network surface; no real network calls
- [ ] No `as any` on mocked methods; typed `vi.mock` via factory shape
- [ ] Snapshot tests reserved for stable contracts; no UI-layout snapshots
- [ ] E2E tests cover critical journeys, not what a component test could cover
- [ ] Server Actions tested as plain async functions, not via RTL render
- [ ] Server Components tested via Playwright or via the underlying data function, not via RTL
- [ ] Test data via factories, not raw object literals

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" → Coverage Assessment
- User asks "write tests for X" or "scaffold tests" → Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested → Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests") → produce them in this order, separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## React Test Coverage Assessment

**Stack:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Runner:** Vitest | Jest
**Test framework:** Vitest, React Testing Library, MSW, Playwright (E2E)
**Coverage gaps:**

- **Unit tests:** [pure utilities / reducers / validators without test coverage]
- **Hook tests:** [custom hooks without test coverage]
- **Component tests:** [interactive components without tests; missing empty / error / loading states]
- **Integration tests:** [pages with multi-component flows lacking integration tests]
- **Server Action tests:** [Server Actions without auth / validation / happy-path tests]
- **E2E tests:** [critical journeys without Playwright coverage]
- **Accessibility:** [pages without `axe` checks; interactive components without keyboard / focus tests]

**Recommended pyramid balance:**

- Unit + hook (utilities, hooks): [count target]
- Component + integration (RTL + MSW): [count target]
- E2E (Playwright): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Auth, money, Server Actions:** [list specific Server Actions / auth flows / billing components missing tests]
2. **P2 - Forms and validation:** [forms with validation logic without tests]
3. **P3 - Empty / error / loading states:** [list views without these branches tested]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pure presentation / wrappers - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run Vitest test files using project conventions. Each scaffold must include:

- The right test type (unit / hook / component / integration / E2E)
- Factories for test data
- Component scaffolds: happy path + error / empty / loading states + a11y check
- Hook scaffolds: state transitions + effect cleanup + edge cases
- Server Action scaffolds: happy path + validation failure + unauthorized
- E2E scaffolds: full journey, with `storageState` for auth
- TypeScript strict: typed `vi.mock` factories, no `as any`

**Strategy Doc** (when designing a test strategy):

```markdown
## React Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit + Hook {x}% / Component + Integration {y}% / E2E {z}%
**Tooling:** Vitest, React Testing Library, `user-event`, MSW, Playwright, `vitest-axe` (or `jest-axe`)
**Mocking strategy:** MSW for network; provider wrappers for context (router, query, theme, auth); Vitest `vi.mock` reserved for non-network module mocks
**Server Component strategy:** [test data function in unit; trust Next.js to render | E2E via Playwright | both]
**Concurrency:** Vitest --threads / --pool=threads; Playwright sharded across workers
**Gaps to close (prioritized):**

1. [Highest risk gap - typically auth / Server Action / form]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as React; framework (Next.js / Vite) and runner (Vitest / Jest) recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `react-testing-patterns` consulted for canonical React test patterns
- [ ] Server Component testing strategy explicit (data-function unit test + Playwright E2E) - not "render Server Component in RTL"
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to React idioms (unit → Vitest; component → RTL + `user-event`; integration → RTL + MSW; E2E → Playwright)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 auth/money/Server Action, P2 forms, P3 empty/error states, P4 high-churn, P5 plumbing
- [ ] Accessibility testing presence assessed (`vitest-axe` / `jest-axe` per route-level test)

**Test Scaffolds only:**

- [ ] Test data created via factories, not raw object literals; typed factory return shapes
- [ ] Component scaffolds use user-centric queries (`getByRole` / `getByLabel`); `getByTestId` only as last resort
- [ ] Component scaffolds use `userEvent` (not `fireEvent`)
- [ ] Component scaffolds cover happy path + error + empty + loading states
- [ ] Hook scaffolds use `renderHook` with proper provider wrapper; cover state transitions and cleanup
- [ ] Server Action scaffolds: validation, authorization, happy path - both the unit-test flavor (action as function) and the component-test flavor (action mocked via `vi.mock`) when both apply
- [ ] React 19 form primitives covered: `useFormStatus` pending state observed via slow-promise mock; `useOptimistic` rollback branch tested explicitly (not just the success path)
- [ ] TanStack Query: fresh `QueryClient` per test (or via `renderWithProviders` factory); `retry: false` to fail error tests fast
- [ ] `next/navigation` mocked consistently (`useRouter` / `useSearchParams` / `usePathname`) for App Router component tests; navigation assertions capture the spy
- [ ] Error tracker (`Sentry.captureException`) mocked when the component handles errors; assertion that capture happened on the error path
- [ ] MSW handlers reset in `afterEach` (`server.resetHandlers()`) so per-test overrides do not leak
- [ ] Multi-step wizards: forward + backward + cross-step validation + submit-with-merged-payload all covered (not just the linear happy path)
- [ ] E2E scaffolds use `getByRole` selectors and `storageState` for auth setup
- [ ] No `as any` in mocks; typed `vi.mock` factory or proper module mock
- [ ] Accessibility check (`axe`) included for route-level / page-level scaffolds

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong factory, uses the wrong mocking convention, or duplicates the existing render helper
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no Server Action validation tests misses the bigger threat
- E2E tests for what a component test could cover - context cost compounds across the suite
- Testing implementation details: render counts, internal state shape, lifecycle method calls - tests break on every refactor and provide no signal
- `getByTestId` everywhere - test IDs are an escape hatch, not a default; user-centric queries reflect what users actually see
- `fireEvent` instead of `userEvent` - skips focus, key dispatch, and other behaviors real users trigger
- Mocking React internals (`vi.mock('react', ...)`) - signals the test is asserting framework behavior; rewrite to assert user-visible behavior
- Snapshot tests for visual layout - they churn on every restyle and provide no signal; reserve for stable contracts (a Markdown renderer's HTML output)
- Trying to render a Server Component in RTL - that path leads to mocking React internals; test the data function or use Playwright
- Skipping Server Action tests because they "are just functions" - validation, auth, and side-effect logic must be exercised
- Real network calls in component tests - flaky and slow; MSW with `onUnhandledRequest: 'error'` enforces the boundary
- Sharing mutable fixtures across tests - leaks state and produces order-dependent failures
- Asserting CSS class names (`expect(el).toHaveClass('text-red-500')`) - couples tests to styling implementation; assert visible behavior or accessibility properties instead
- `as any` to silence TypeScript in mocks - defeats strict mode; use typed `vi.mock` factories
