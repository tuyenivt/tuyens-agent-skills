---
name: task-vue-test
description: Vue test strategy and scaffolding using Vitest, Vue Test Utils, @nuxt/test-utils, MSW for HTTP stubs, Playwright for E2E, and TypeScript strict-mode test typing. Detects Nuxt 3 vs Vite + Vue Router and applies the right idioms (Nuxt server route testing, composable testing, `<script setup>` mounting). Use when designing a test plan, assessing coverage gaps, or scaffolding component / composable / route / E2E tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to Vue.
agent: vue-test-engineer
metadata:
  category: frontend
  tags: [vue, typescript, vitest, vue-test-utils, nuxt-test-utils, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Vue Test

## Purpose

Vue-aware test strategy and scaffolding using Vitest, Vue Test Utils (`@vue/test-utils`), `@nuxt/test-utils` (Nuxt-aware mounting + Nitro endpoint testing), MSW (`msw`) for HTTP stubs, Playwright for E2E, and TypeScript strict-mode test typing. Replaces the generic frontend test patterns with Vue-specific guidance: user-centric queries via `@testing-library/vue` (or VTU `findByText` semantics), avoidance of implementation-detail tests (no asserting `wrapper.vm` internals), Nuxt server route testing via `@nuxt/test-utils`, composable testing via `withSetup` helpers, and accessibility-as-tests.

This workflow is the stack-specific delegate of `task-code-test` for Vue. The core workflow's contract (output shape, prioritization rules) is preserved.

## When to Use

- Designing a test strategy for a new Vue app, page, or feature
- Assessing test coverage gaps across unit / component / integration / E2E layers
- Scaffolding tests for under-covered components, composables, Nitro endpoints, or routes
- Reviewing test pyramid balance for a Vue app
- Adding accessibility / boundary tests (validation, error states, empty states) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-vue-debug`)
- General code review (use `task-code-review` / `task-vue-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Vue. If the detected stack is not Vue, stop and tell the user to invoke `/task-code-test` instead.

Detect framework: Nuxt 3 vs Vite + Vue Router. Detect test runner: Vitest is the standard for both; Jest still appears in older Vue 2 projects (rare on Vue 3). Detect helper library: `@vue/test-utils` (VTU - the official Vue test library) vs `@testing-library/vue` (Testing Library variant - more user-centric query API). Record `Framework: ...`, `Runner: Vitest | Jest`, `Helper: @vue/test-utils | @testing-library/vue`, `Vue: <version>` for the output. Each section that follows branches on this signal where the test idiom differs.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: component shape (script setup vs Options API), props, composables used, data fetching, event handlers
- Glob `**/*.test.{ts,tsx}`, `**/*.spec.{ts,tsx}`, `e2e/**/*.spec.ts` and read at least: one existing component test, one existing composable test (if applicable), one existing Playwright E2E spec, test setup files (`vitest.setup.ts`, `playwright.config.ts`)
- Read `vitest.config.{js,ts}` for `setupFiles`, `environment` (`jsdom` / `happy-dom` for components, `node` for Node-only utilities), path aliases, coverage config
- Read `vitest.setup.ts` (or equivalent) for MSW server setup, global stubs, `@testing-library/jest-dom` matcher extension
- For Nuxt: read `nuxt.config.ts` for any modules affecting test setup; check for `@nuxt/test-utils` config (`vitest.config` `test.environment: 'nuxt'`)
- For both: read any provider / plugin / Pinia store that components depend on - they must be wrapped or stubbed in tests too

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - Vue Test Pyramid

The Vue test pyramid maps to test types:

| Layer       | Tooling                                                                       | What belongs here                                                                 |
| ----------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Unit        | Vitest + plain functions                                                      | Utility functions, Pinia getters / actions in isolation, formatters, validators   |
| Composable  | Vitest + `withSetup` helper or `@vue/test-utils` `mount` of a probe component | Custom composables in isolation - state transitions, lifecycle, return shape      |
| Component   | Vitest + VTU / `@testing-library/vue` + `user-event` + MSW                    | Component rendering, interaction, accessibility - mount, click, type, assert      |
| Integration | Vitest + VTU + MSW + real router (Vue Router) / `@nuxt/test-utils` (Nuxt)     | Multi-component flows on a single page - filter list, submit form, see updated UI |
| Nitro       | Vitest + `@nuxt/test-utils` `setup` + `$fetch`                                | Nuxt server endpoint contract - input validation, auth, response shape            |
| E2E         | Playwright + `@nuxt/test-utils` (Nuxt) / Playwright standalone (Vite)         | Critical user journeys - signup, checkout, payment, multi-page flows              |
| Visual      | Playwright screenshots / Chromatic / Percy / Histoire                         | Visual regression on key components (opt-in)                                      |

**Many** unit + composable + component tests, **some** integration tests, **few** E2E tests. Nitro endpoint tests sit between unit and integration in cost; aim for one per endpoint covering happy + auth + validation paths.

### Step 4 - Apply Vue Test Patterns

Use skill: `vue-testing-patterns` for the canonical patterns referenced below.

**Unit tests (`*.test.ts`):**

- Vitest (`describe`, `it`, `expect`, `beforeEach`); `environment: 'node'` for pure-function tests when no DOM is involved
- Test the public function - one test per outcome (success, validation failure, edge case)
- TypeScript strict: avoid `as any`; use proper typed inputs
- Pinia store tests: `setActivePinia(createPinia())` in `beforeEach`; instantiate the store via `useFooStore()`; assert state, getters, action effects directly. No component mount needed for pure store logic

**Composable tests:**

Composables containing reactivity (`ref`, `computed`, `watch`, lifecycle hooks) cannot be called directly outside a component context - lifecycle hooks throw, `inject` returns undefined. Two patterns:

_Pattern 1 - `withSetup` helper (preferred for pure composables):_

```ts
// test/utils.ts
import { createApp, type App } from "vue";

export function withSetup<T>(setup: () => T): [T, App] {
  let result!: T;
  const app = createApp({
    setup() {
      result = setup();
      return () => {};
    },
  });
  app.mount(document.createElement("div"));
  return [result, app];
}

// composable.test.ts
const [api, app] = withSetup(() => useFilters({ status: "open" }));
expect(api.filters.value.status).toBe("open");
api.setStatus("closed");
expect(api.filters.value.status).toBe("closed");
app.unmount();
```

_Pattern 2 - probe component (when the composable depends on `inject`, router, Pinia, or other context):_

```ts
const TestComponent = defineComponent({
  setup() {
    return { api: useOrderFilters() };
  },
  render() {
    return h("div");
  },
});
const wrapper = mount(TestComponent, {
  global: { plugins: [createPinia(), router] },
});
expect(wrapper.vm.api.status).toBe("open");
await wrapper.vm.api.setStatus("closed");
expect(wrapper.vm.api.status).toBe("closed");
```

- Assert the composable's reactive return shape after each transition; use `nextTick()` between mutations and assertions when the composable batches updates via watchers
- Test cleanup: assert effects clean up via `app.unmount()` / `wrapper.unmount()` and check that watchers / intervals / subscriptions are torn down (e.g., `vi.useFakeTimers()` to assert intervals stop firing)

**Component tests (`*.test.ts`):**

- VTU: `import { mount } from '@vue/test-utils'`; `const wrapper = mount(Component, { props, global: { plugins, stubs } })`
- Testing Library Vue: `import { render, screen } from '@testing-library/vue'`; user-centric queries align with React Testing Library conventions

**With `@testing-library/vue` (preferred for new projects):**

- **User-centric queries**: `getByRole('button', { name: /save/i })`, `getByLabelText(/email/i)`, `getByText(/welcome/i)`. Avoid `getByTestId` except as last resort
- **`userEvent` over `fireEvent`**: `await userEvent.click(button)` simulates real interaction (focus, key events). `fireEvent.click` skips behavior real users trigger
- **Async assertions**: `await screen.findByText(...)` (built-in waitFor); `expect(await screen.findByRole('alert')).toHaveTextContent(...)`
- Wrap in providers via a shared `renderWithProviders(ui, options)` helper - includes router (Vite: real `createRouter` with memory history; Nuxt: `@nuxt/test-utils` provides router context), Pinia, theme, auth context

**With Vue Test Utils (existing projects, lower-level API):**

- `mount()` for full render with children; `shallowMount()` only for cases where deep mount has cross-cutting noise (e.g., layout + provider chain unrelated to the test) - prefer `mount()` for behavior tests
- Find via `wrapper.find('[role="button"]')`, `wrapper.findAll('li')`, `wrapper.findComponent(ChildComponent)`. Prefer DOM selectors / accessible roles over component selectors when possible
- Trigger events via `await wrapper.find('button').trigger('click')`; use `await wrapper.setProps({ status: 'closed' })` for prop changes; use `nextTick()` after reactive mutations
- Assert emitted events: `expect(wrapper.emitted('save')).toBeTruthy()`, `expect(wrapper.emitted('save')?.[0]).toEqual([{ id: 1 }])`
- **Avoid** asserting on `wrapper.vm.<internal>` for component state - that's an implementation detail. Test through the rendered DOM and emitted events

**Stubs and mocks (`global.stubs`):**

- `global.stubs: { NuxtLink: true }` to stub framework components when their behavior is not under test (avoids needing the full Nuxt context)
- `global.plugins: [createPinia(), router]` to install plugins
- `global.provide: { someKey: stubValue }` to satisfy `inject` calls

**One test per `(component-state, user-action, assertion)` triple.** Avoid testing every prop permutation - test the contract.

**Accessibility:** `expect(await axe(container)).toHaveNoViolations()` via `vitest-axe` for any route-level test; per-component tests at minimum assert that interactive elements have accessible names.

**Snapshot tests sparingly**: snapshots churn on every refactor; reserve for stable contract surfaces (e.g., a Markdown renderer's HTML output) - never for visual layout.

**Integration tests (`*.test.ts` with multiple components):**

- Render the page-level component with all real children; mock only the network via MSW
- Walk through the user flow: type into search, click filter, see filtered list - assertions at each user-visible step
- For Vite + Vue Router, use `createRouter({ history: createMemoryHistory(), routes })` with explicit initial entries via `router.push('/initial')` before mount
- For Nuxt App Router, prefer `@nuxt/test-utils` integration mode (`mountSuspended`) which provides the full Nuxt context (auto-imports, server routes, Nitro mocks)

**MSW for HTTP:**

- `setupServer(...handlers)` in `vitest.setup.ts`; `server.listen({ onUnhandledRequest: 'error' })` to fail loud on missed stubs
- Handler per endpoint, not per test - tests override per-test via `server.use(http.get('...', resolver))`
- **Reset handlers in `afterEach`**: `server.resetHandlers()` removes per-test overrides so they do not leak. Without this, tests pass in isolation and fail in suite order
- For Nuxt `useFetch` / `$fetch` - both go through the global `$fetch` ofetch instance and MSW intercepts them transparently
- Run MSW for both Vitest and Playwright (Playwright via `msw` browser worker or just point Playwright at a mocked backend)

**`renderWithProviders` helper (canonical shape, Testing Library Vue):**

A shared helper avoids re-wrapping providers in every test and keeps test output comparable. Put it in `test/render.ts`:

```ts
import { render, type RenderOptions } from "@testing-library/vue";
import { createRouter, createMemoryHistory } from "vue-router";
import { createPinia } from "pinia";
import type { Component } from "vue";

export function renderWithProviders(
  component: Component,
  options: RenderOptions & { initialRoute?: string } = {},
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      /* test routes */
    ],
  });
  if (options.initialRoute) router.push(options.initialRoute);

  return render(component, {
    global: {
      plugins: [createPinia(), router],
      stubs: { NuxtLink: false /* render real anchor */ },
      ...options.global,
    },
    ...options,
  });
}
```

**Nitro endpoint tests (Nuxt, via `@nuxt/test-utils`):**

There are two flavors. Run **both** when the endpoint has both validation logic and a UI surface that calls it.

_Flavor 1 - Direct test of the endpoint via `@nuxt/test-utils`:_

```ts
import { setup, $fetch } from "@nuxt/test-utils";

describe("PUT /api/account", async () => {
  await setup({
    /* nuxt project root */
  });

  it("rejects invalid body", async () => {
    await expect(
      $fetch("/api/account", { method: "PUT", body: { role: "admin" } }),
    ).rejects.toThrow(/400/);
  });

  it("updates own account", async () => {
    const result = await $fetch("/api/account", {
      method: "PUT",
      body: { name: "Alice" },
      headers: { cookie: "session=..." /* or use a session-fixture helper */ },
    });
    expect(result).toEqual({ ok: true });
  });
});
```

- Mock the session via cookie / header injection; assert that unauthenticated calls reject before any DB / external call
- Assert validation: invalid input rejected with the expected status; valid input mutates and returns the expected payload
- The DB layer is the boundary - either use a Testcontainers Postgres + real Prisma (slow, accurate) or stub the data layer per test. Match the project's existing approach

_Flavor 2 - Component test that mocks `useFetch` / `$fetch`:_

```ts
// Mock the fetch composable - the component's wiring is what's under test
vi.mock("#app", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useFetch: vi.fn(() => ({
    data: ref({ ok: true }),
    error: ref(null),
    pending: ref(false),
    refresh: vi.fn(),
  })),
}));
```

- Pair with form-state testing - assert the action was called with the expected body after `userEvent.click` on submit, without re-running the endpoint logic (Flavor 1 already covered)

**Pinia store tests (no component mount required):**

```ts
import { setActivePinia, createPinia } from "pinia";
import { useOrdersStore } from "@/stores/orders";

describe("orders store", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("addOrder appends to state", () => {
    const store = useOrdersStore();
    store.addOrder({ id: 1, status: "open" });
    expect(store.orders).toHaveLength(1);
  });
});
```

- Test getters as derived state; test actions as state transitions; test `$patch` if used for batch updates
- For stores that fetch via `$fetch`, mock the fetch function (`vi.mock('ofetch')` or via MSW)

**TanStack Query Vue (when used) in tests:**

- Create a fresh `QueryClient` per test - shared clients leak cache: `const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })`
- Wrap the rendered component with `<QueryClientProvider :client="queryClient">` (do this in the `renderWithProviders` helper)
- Disable retries (`retry: false`) so error-state tests fail fast

**Vue Router mock pattern (Vite component tests):**

- Use a real `createRouter({ history: createMemoryHistory(), routes })` with stub route components - avoids over-mocking. Push initial location: `router.push('/orders/123')` before mount
- For tests that assert navigation, spy on `router.push`: `const push = vi.spyOn(router, 'push'); ...; expect(push).toHaveBeenCalledWith('/success')`

**Nuxt-specific (`@nuxt/test-utils`):**

- `mountSuspended(Component)` from `@nuxt/test-utils/runtime` - mounts a component inside a Suspense boundary with full Nuxt context (auto-imports, plugins, modules)
- `mockNuxtImport('useFetch', () => ...)` to override auto-imported composables in a test
- Router and Pinia available as auto-imports in the test environment

**`Sentry.captureException` mock (or any error-tracker):**

- `vi.mock('@sentry/vue', () => ({ captureException: vi.fn(), captureMessage: vi.fn(), setUser: vi.fn() }))`
- Assert `captureException` was called with the expected `Error` after the component's error path runs
- Reset mocks in `beforeEach` (`vi.clearAllMocks()`) to avoid cross-test bleed

**Playwright E2E (`e2e/*.spec.ts`):**

- Reserve for critical journeys: signup, checkout, multi-step forms, money flows
- One spec per journey, not per page
- Use `data-testid` only as a last-resort selector; prefer `getByRole` / `getByLabel` for resilience
- Auth setup via `storageState` fixture (login once, save state, reuse across tests) - fast and reliable
- API stubbing via `page.route('**/api/orders', route => route.fulfill({...}))` for tests asserting specific backend states without touching the real backend
- Run against a built app (Nuxt: `pnpm build && pnpm preview`; Vite: `pnpm build && pnpm preview`) - dev mode has different behavior (HMR, source maps, dev-only error overlays)
- For Nuxt: `@nuxt/test-utils/playwright` provides `useTestContext` for auto-launching the Nuxt dev server / preview server with test fixtures

### Step 5 - Test Boundaries (Vue-Specific)

**What deserves a unit test:**

- Pure utilities (formatters, parsers, date helpers, currency math)
- Pinia stores in isolation (state, getters, actions - without mounting components)
- Validators (Zod schemas - test edge cases, custom refinements)
- Selectors / derived data functions

**What deserves a composable test:**

- Every custom composable with a state transition or external integration
- Composables managing subscriptions, intervals, observers (assert cleanup)
- Composables with non-trivial watcher dependencies (verify watcher re-runs on the right changes)

**What deserves a component test:**

- Every interactive component (form, modal, dropdown, menu, dialog, tabs, accordion)
- Empty / loading / error states - especially "no items" and "API failed" branches
- Conditional rendering paths (auth-gated UI, feature-flag-gated UI, slot-based composition)
- Accessibility (label association, keyboard navigation, focus management)

**What deserves a Nitro endpoint test (Nuxt):**

- Every endpoint that accepts user input - validation test + auth test + happy path
- Error-shape consistency (error responses match a typed contract)
- Authentication / authorization rejection paths

**What deserves an integration test:**

- Filter + list interactions (filter changes update list, URL syncs, deep link works)
- Form flows (multi-step wizard, validation across steps)
- Optimistic-update flows (mutate → see immediate UI change → rollback on error)

**Multi-step form / wizard testing strategy:**

A single integration test that walks the full path is the spine. Add focused component tests for each step's validation. Cover at minimum:

- **Forward navigation:** valid input on step N advances to step N+1; the submit button is disabled until each step's validation passes
- **Backward navigation preserves state:** step 1 → step 2 → back to step 1 → fields still populated. The most-broken behavior in practice
- **Cross-step validation:** a field on step 3 that depends on a step 1 value
- **Cancel / reset:** discarding the wizard clears state; a "Save Draft" path persists state separately
- **Submit flow:** the final submit calls the endpoint with the accumulated form state from all steps

For wizards using Pinia or `useReducer`-style composables, unit-test the store / composable separately - that is the lowest-overhead place to assert all the transitions. The component test then asserts the wiring, not the transitions.

**What deserves an E2E test:**

- Authentication and onboarding journey (signup, email verify, first-run)
- Checkout / payment journey
- Critical multi-page flows where contract between pages matters
- Routing flows that depend on real navigation (Nuxt page transitions, route middleware)

**What does NOT need a test:**

- Framework-provided behavior: `<NuxtLink>` navigation, Pinia plugin internals, Vue Router built-in guards - test your wiring, not the framework
- Generated boilerplate: typed props with no logic, simple wrapper components
- Trivial components: `<Button>` re-exporting a primitive with one prop change - covered by parents
- Visual layout details (margin, padding) - belongs to visual regression, not unit tests
- Pure presentation components in isolation if they have no logic - test via the parent that uses them

### Step 6 - Test Data and Fixtures

- Prefer factory utilities (`createUserFactory`, `@faker-js/faker` for primitives, or `fishery`) over hand-rolled object literals
- Co-locate factories with the schema / types they produce (`test/factories/user.ts`)
- For component tests: factories produce minimal valid props; tests override only the field under test
- For MSW handlers: factories produce response payloads matching the API contract
- Avoid mutating shared test fixtures - rebuild via factory in `beforeEach`
- Test data must be minimal and focused - 100-row `Array.from` setups in a component test signal the test belongs at integration / E2E

### Step 7 - Prioritization (when coverage is low)

If line / branch coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when accessibility regressions go untested while `<Button>` gets full coverage.

When starting from low test coverage, prioritize by Vue-specific risk:

**Priority 1 - Auth, money, and Nitro endpoints:**

- Every Nitro endpoint mutating data: validation test + auth test + happy path
- Auth flows: signup, login, password reset, session expiry behavior
- Money / billing components: checkout, plan-change, refund

**Priority 2 - Forms and validation:**

- Every form with validation - test invalid inputs surface errors, valid inputs submit
- Multi-step wizards - completion path + back-navigation preserves state

**Priority 3 - Empty / error / loading states:**

- Every list / data view tested with empty state, loading skeleton, and error fallback
- Error boundaries (Vue 3 `errorCaptured` / Nuxt `error.vue`) test that thrown errors are caught and surface a recovery UI

**Priority 4 - High-churn components:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pure presentation, simple wrappers, plain styled components - lowest risk

### Step 8 - Test Infrastructure Hygiene

- [ ] Vitest `environment: 'jsdom'` (or `'happy-dom'` - faster) for components / composables; `'node'` for pure-utility tests; mixed via `// @vitest-environment node` directive when needed
- [ ] Nuxt: `environment: 'nuxt'` (provided by `@nuxt/test-utils`) for tests that need auto-imports / Nitro mocking
- [ ] `@testing-library/jest-dom` matchers (`toBeInTheDocument`, `toBeVisible`, `toHaveAccessibleName`) registered in setup (when using Testing Library Vue)
- [ ] MSW `setupServer` with `onUnhandledRequest: 'error'` to fail loud on missed stubs
- [ ] `userEvent.setup()` per test (not module-level singleton) when using `@testing-library/vue`
- [ ] Cleanup: VTU / Testing Library cleanup runs automatically; verify by checking for "leaked" elements between tests
- [ ] Strict TypeScript in tests: same `tsconfig.json`; no `as any` shortcuts; typed VTU mount via `mount<typeof Component>`
- [ ] Coverage tool (`v8` / `istanbul` via Vitest) wired to CI with per-package thresholds; coverage exclusions documented
- [ ] Playwright config: `retries: 2` on CI for flake tolerance, `0` locally; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] No real network calls (assert MSW unhandled fails the test); no real filesystem (`fs.writeFile` in component tests is a smell)
- [ ] CI runs Vitest + Playwright in parallel; Playwright sharded across workers for speed
- [ ] Visual regression (if used): Chromatic / Percy / Histoire / Playwright screenshots gated to `main`-branch builds, not every PR (cost vs signal)
- [ ] Histoire / Storybook integration (if a story catalog exists in repo): stories doubling as tests via `play` functions or `@histoire/plugin-vue3` test runner - reuses interaction logic across docs and CI without duplicating the setup

## Vue Review Checklist

Quick-reference checklist for reviewing existing Vue tests:

- [ ] Test type matches what is being tested (component → VTU/TLV, composable → `withSetup` / probe, journey → Playwright, endpoint → `@nuxt/test-utils`)
- [ ] Queries are user-centric (`getByRole`, `getByLabel`); `getByTestId` only as last resort
- [ ] `userEvent` over `fireEvent` / direct `trigger()` for user interactions when meaningful
- [ ] No tests of implementation details (asserting `wrapper.vm.<internal>`, render counts, lifecycle method calls)
- [ ] Async assertions use `findBy*` / `waitFor` / `nextTick()` - no `setTimeout` waits
- [ ] MSW handlers cover the network surface; no real network calls
- [ ] No `as any` on mocked methods; typed `vi.mock` via factory shape
- [ ] Snapshot tests reserved for stable contracts; no UI-layout snapshots
- [ ] E2E tests cover critical journeys, not what a component test could cover
- [ ] Nitro endpoints tested as direct `$fetch` calls via `@nuxt/test-utils`, not through component mounting
- [ ] Composables tested via `withSetup` or probe component, not by calling outside a setup context
- [ ] Pinia stores tested without mounting components when the test is about state logic
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
## Vue Test Coverage Assessment

**Stack:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Runner:** Vitest | Jest
**Helper:** @vue/test-utils | @testing-library/vue
**Test framework:** Vitest, [helper], MSW, Playwright (E2E), @nuxt/test-utils (Nuxt)
**Coverage gaps:**

- **Unit tests:** [pure utilities / Pinia store logic / validators without test coverage]
- **Composable tests:** [custom composables without test coverage]
- **Component tests:** [interactive components without tests; missing empty / error / loading states]
- **Integration tests:** [pages with multi-component flows lacking integration tests]
- **Nitro endpoint tests:** [Nuxt server endpoints without auth / validation / happy-path tests]
- **E2E tests:** [critical journeys without Playwright coverage]
- **Accessibility:** [pages without `axe` checks; interactive components without keyboard / focus tests]

**Recommended pyramid balance:**

- Unit + composable (utilities, composables, stores): [count target]
- Component + integration (VTU/TLV + MSW): [count target]
- Nitro endpoint: [count target - one per server route minimum]
- E2E (Playwright): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Auth, money, Nitro endpoints:** [list specific endpoints / auth flows / billing components missing tests]
2. **P2 - Forms and validation:** [forms with validation logic without tests]
3. **P3 - Empty / error / loading states:** [list views without these branches tested]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pure presentation / wrappers - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run Vitest test files using project conventions. Each scaffold must include:

- The right test type (unit / composable / component / integration / Nitro / E2E)
- Factories for test data
- Component scaffolds: happy path + error / empty / loading states + a11y check
- Composable scaffolds: state transitions + watcher cleanup + edge cases
- Nitro endpoint scaffolds: happy path + validation failure + unauthorized
- E2E scaffolds: full journey, with `storageState` for auth
- TypeScript strict: typed `vi.mock` factories, no `as any`

**Strategy Doc** (when designing a test strategy):

```markdown
## Vue Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit + Composable {x}% / Component + Integration {y}% / Nitro {z}% / E2E {w}%
**Tooling:** Vitest, [VTU | Testing Library Vue], `user-event`, MSW, Playwright, `vitest-axe`, @nuxt/test-utils (Nuxt)
**Mocking strategy:** MSW for network; provider wrappers for context (router, Pinia, theme, auth); Vitest `vi.mock` reserved for non-network module mocks
**Composable strategy:** [`withSetup` for pure | probe component for context-bound | both]
**Nitro strategy:** [direct `$fetch` via @nuxt/test-utils + DB stubbing approach]
**Concurrency:** Vitest --threads / --pool=threads; Playwright sharded across workers
**Gaps to close (prioritized):**

1. [Highest risk gap - typically auth / Nitro endpoint / form]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as Vue; framework (Nuxt / Vite) and runner (Vitest / Jest) and helper (VTU / TLV) recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `vue-testing-patterns` consulted for canonical Vue test patterns
- [ ] Composable testing strategy explicit (`withSetup` for pure; probe component when context-bound) - not "call composable directly outside setup"
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Vue idioms (unit → Vitest; component → VTU/TLV + `user-event`; integration → VTU + MSW; Nitro → `@nuxt/test-utils`; E2E → Playwright)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 auth/money/Nitro, P2 forms, P3 empty/error states, P4 high-churn, P5 plumbing
- [ ] Accessibility testing presence assessed (`vitest-axe` per route-level test)

**Test Scaffolds only:**

- [ ] Test data created via factories, not raw object literals; typed factory return shapes
- [ ] Component scaffolds use user-centric queries (`getByRole` / `getByLabel`); `getByTestId` only as last resort
- [ ] Component scaffolds use `userEvent` (not `fireEvent` / direct `trigger`) when meaningful
- [ ] Component scaffolds cover happy path + error + empty + loading states
- [ ] Composable scaffolds use `withSetup` or probe component pattern; cover state transitions and cleanup
- [ ] Nitro endpoint scaffolds: validation, authorization, happy path - both the direct `$fetch` flavor (endpoint as endpoint) and the component-test flavor (`useFetch` mocked) when both apply
- [ ] Pinia store scaffolds: no component mount when only state logic is under test
- [ ] TanStack Query (when used): fresh `QueryClient` per test (or via `renderWithProviders` factory); `retry: false` to fail error tests fast
- [ ] Vue Router: real `createMemoryHistory` router with stub routes; navigation assertions spy on `router.push`
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
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no Nitro endpoint validation tests misses the bigger threat
- E2E tests for what a component test could cover - context cost compounds across the suite
- Testing implementation details: `wrapper.vm.<internal>`, render counts, lifecycle method calls - tests break on every refactor
- `getByTestId` everywhere - test IDs are an escape hatch, not a default; user-centric queries reflect what users actually see
- `fireEvent` instead of `userEvent` - skips focus, key dispatch, and other behaviors real users trigger (when using Testing Library Vue; VTU's `trigger` is acceptable for simple cases)
- Calling a composable directly outside a setup context - lifecycle hooks throw, `inject` returns undefined; use `withSetup` or a probe component
- Snapshot tests for visual layout - they churn on every restyle and provide no signal; reserve for stable contracts
- Skipping Nitro endpoint tests because they "are just functions" - validation, auth, and side-effect logic must be exercised
- Mounting a component to test Pinia store state - mount adds noise; test the store directly with `setActivePinia`
- Real network calls in component tests - flaky and slow; MSW with `onUnhandledRequest: 'error'` enforces the boundary
- Sharing mutable fixtures across tests - leaks state and produces order-dependent failures
- Asserting CSS class names (`expect(el).toHaveClass('text-red-500')`) - couples tests to styling implementation; assert visible behavior or accessibility properties instead
- `as any` to silence TypeScript in mocks - defeats strict mode; use typed `vi.mock` factories
