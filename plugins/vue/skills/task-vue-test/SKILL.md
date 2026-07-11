---
name: task-vue-test
description: Vue / Nuxt test plan and scaffolding - Vitest, Vue Test Utils, @nuxt/test-utils, MSW, Playwright E2E, composable and SFC tests.
agent: vue-test-engineer
metadata:
  category: frontend
  tags: [vue, typescript, vitest, vue-test-utils, nuxt-test-utils, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

# Vue Test

Stack-specific delegate of `task-code-test` for Vue. Preserves the core workflow's output shape and prioritization rules; substitutes Vue idioms (Vitest, VTU / Testing Library Vue, `@nuxt/test-utils`, MSW, Playwright) and Vue-specific risks (composables, Nitro endpoints, Pinia, Suspense).

## When to Use

- Designing a test strategy for a new Vue app, page, or feature
- Assessing coverage gaps across unit / composable / component / integration / Nitro / E2E layers
- Scaffolding tests for under-covered components, composables, Nitro endpoints, or routes
- Reviewing test pyramid balance or adding accessibility / boundary tests

**Not for:** test failure debugging (`task-vue-debug`), general code review (`task-vue-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If invoked as a delegate of `task-code-test` with Vue already confirmed, skip re-detection. If the stack is not Vue, stop and direct the user to `/task-code-test`.

Record for the output: `Framework: Nuxt 3 | Vite + Vue Router`, `Vue: <version>`, `Runner: Vitest` (flag Jest as legacy; recommend migration), `Helper: @vue/test-utils | @testing-library/vue`, `E2E: Playwright | Cypress | none`. Subsequent steps branch on these signals.

If the project runs Jest and migration is declined, produce scaffolds in Jest idiom (`jest.mock`, `jest.fn`, Jest config) so they run as-is; list Vitest migration under Test infrastructure prerequisites as a recommendation, not a blocker. Pyramid, boundaries, and prioritization are runner-independent.

### Step 3 - Read Code Under Test and Existing Tests

Ground output in real project conventions before producing assessment, strategy, or scaffolds.

- Read each target module top-to-bottom: component shape (`<script setup>` vs Options API), props, composables, data fetching, events
- Glob `**/*.{test,spec}.{ts,tsx}`, `e2e/**/*.spec.ts`. Read at least one existing component test, one composable test (if any), one Playwright spec
- Read `vitest.config.*` (environment, setupFiles, aliases, coverage) and the setup file (MSW wiring, jest-dom matchers)
- Nuxt: read `nuxt.config.ts` and check for `environment: 'nuxt'` in vitest config
- Read providers / plugins / Pinia stores that targets depend on - they must be wrapped or stubbed in tests

If no existing tests exist, state so and propose conventions explicitly in the output instead of inventing them silently.

### Step 4 - Map the Vue Test Pyramid

| Layer       | Tooling                                              | What belongs here                                                       |
| ----------- | ---------------------------------------------------- | ----------------------------------------------------------------------- |
| Unit        | Vitest                                               | Pure functions, Pinia state/getters/actions, validators, formatters     |
| Composable  | Vitest + `withSetup` or probe component              | Custom composables - reactivity transitions, lifecycle, cleanup         |
| Component   | Vitest + VTU / TLV + `userEvent` + MSW               | Render, interaction, accessibility - mount, act, assert                 |
| Integration | Vitest + VTU + MSW + real router / `mountSuspended`  | Multi-component flows on a page - filter, submit, navigate              |
| Nitro       | Vitest + `@nuxt/test-utils` `setup` + `$fetch`       | Nuxt server endpoint - validation, auth, response shape                 |
| E2E         | Playwright (+ `@nuxt/test-utils/playwright` on Nuxt) | Critical journeys - signup, checkout, multi-page flows                  |
| Visual      | Chromatic / Percy / Histoire / Playwright shots      | Visual regression on key components (opt-in)                            |

**Many** unit/composable/component, **some** integration, **few** E2E. One Nitro test per endpoint covering happy + auth + validation paths minimum.

### Step 5 - Apply Vue Test Patterns

Use skill: `vue-testing-patterns` for canonical patterns: `withSetup` host-component composable testing, `renderWithProviders` + `createTestingPinia`, real-router mounting (`createMemoryHistory`), MSW lifecycle, `mountSuspended` (Nuxt), Nitro endpoint testing via the `@nuxt/test-utils/e2e` `$fetch` harness, Playwright E2E.

Selection rules (this workflow decides; the atomic skill provides the pattern):

- Composable → `withSetup`; when it depends on `inject` / router / Pinia, register those plugins or provides on the host component
- Component test → user-centric queries (`getByRole` / `getByLabel`); `getByTestId` only as last resort
- Pinia state/getter/action test → no component mount; `setActivePinia(createPinia())` in `beforeEach`
- Nitro endpoint with both server logic and UI caller → cover both sides: e2e-harness `$fetch` for the endpoint, `mountSuspended` + MSW for the component
- Page-level integration test → MSW for network; real router (Vite: `createMemoryHistory`; Nuxt: `mountSuspended`)
- TanStack Query → fresh `QueryClient` per test with `retry: false`; Playwright auth seeded via `storageState`
- TypeScript strict in tests; no `as any` in mocks

### Step 6 - Define Test Boundaries

**Deserves a test:**

| Category    | Coverage target                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------ |
| Unit        | Pure utilities, Pinia stores (isolated), Zod schemas, selectors                                  |
| Composable  | Every custom composable with state transitions, subscriptions, watchers - including cleanup     |
| Component   | Every interactive component; empty / loading / error states; conditional rendering; a11y         |
| Nitro       | Every input-accepting endpoint - validation + auth + happy path; error-shape consistency        |
| Integration | Filter+list, multi-step forms, optimistic-update flows                                           |
| E2E         | Auth journey, checkout, multi-page flows where contract between pages matters                    |

**Multi-step wizard** test spine: one integration test walking the full path; component tests per step's validation. Cover forward navigation, backward navigation preserves state (most-broken in practice), cross-step validation, cancel/reset, submit with merged payload. For wizards backed by Pinia or composable, unit-test the store/composable separately; the component test asserts wiring, not transitions.

**Does NOT need a test:** framework-provided behavior (`<NuxtLink>`, Pinia internals, Vue Router guards), generated boilerplate, trivial wrappers covered by parents, visual layout (belongs to visual regression), pure presentation components with no logic.

### Step 7 - Test Data and Fixtures

- Factories (`createUserFactory`, `@faker-js/faker`, `fishery`) over hand-rolled literals
- Co-locate with types: `test/factories/<entity>.ts`
- Component tests: factories produce minimal valid props; override only the field under test
- MSW handlers: factories produce response payloads matching API contracts
- Rebuild fixtures in `beforeEach`; never mutate shared fixtures
- Test data must be minimal - 100-row `Array.from` setups in a component test signal it belongs at integration / E2E

### Step 8 - Prioritize (when coverage is low)

Run before scaffolding when line/branch coverage is below ~50% or there are >5 gaps. Order determines *which* tests to scaffold first; alphabetical or by-file is wrong.

1. **P1 - Auth, money, Nitro endpoints:** every mutating Nitro endpoint (validation + auth + happy); auth flows; billing/checkout
2. **P2 - Forms and validation:** every validated form; multi-step wizards (back-navigation preserves state)
3. **P3 - Empty / error / loading:** every list/data view with all three branches; error boundaries (`errorCaptured` / `error.vue`)
4. **P4 - High-churn:** files with frequent recent commits (`git log --since="3 months ago"`) or bug-fix history (`git log --grep="fix"`)
5. **P5 - Plumbing:** pure presentation, simple wrappers - lowest risk

### Step 9 - Audit Test Infrastructure Prerequisites

A prioritized list against an empty `vitest.config.ts` is a paper plan. Audit the harness needed to *run* tests; surface every missing piece as a prerequisite that must land **alongside P1**, not after it.

- [ ] `vitest.config.{ts,js,mjs}` - correct `environment` (`jsdom` / `happy-dom` / `nuxt`), path aliases match `tsconfig.json`, `setupFiles` entry
- [ ] Setup file (`test/setup.ts`) - MSW (`setupServer`, `server.listen({ onUnhandledRequest: 'error' })`, `resetHandlers` in `afterEach`, `close` in `afterAll`); jest-dom matchers if using TLV
- [ ] `test/render.ts` shared `renderWithProviders` (Pinia + router + theme + auth) - else every test re-derives the chain and they drift
- [ ] `test/factories/<entity>.ts` for main domain types
- [ ] `playwright.config.{ts,js}` when E2E is in scope
- [ ] Dev deps for chosen tooling: `msw`, `vitest-axe`, `@testing-library/jest-dom` or VTU matchers, `@nuxt/test-utils` (Nuxt)
- [ ] CI runs Vitest + Playwright (when in scope); coverage tool (`v8` / `istanbul`) wired

Missing items render as a **Test infrastructure prerequisites** subsection of the Coverage Assessment; label "must land alongside P1."

### Step 10 - Verify Hygiene of Existing Setup

Audit ongoing-maintenance items distinct from Step 9's first-time prerequisites:

- [ ] `userEvent.setup()` per test (not module-level)
- [ ] Strict TS in tests; typed `mount<typeof Component>`
- [ ] No real network (MSW `onUnhandledRequest: 'error'` enforces); no real filesystem
- [ ] Coverage thresholds per package; exclusions documented
- [ ] Playwright: `retries: 2` on CI / `0` local; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] CI runs Vitest + Playwright in parallel; Playwright sharded
- [ ] Visual regression (if used) gated to `main` builds, not every PR
- [ ] Histoire / Storybook stories doubling as tests via `play` functions (if a story catalog exists)

## Output Format

**Which output to produce:**

- "What tests are missing?" / "review coverage" → Coverage Assessment
- "Write/scaffold tests for X" → Test Scaffolds
- "Test strategy/plan" or coverage <50% with no scaffolds requested → Strategy Doc (optionally include Coverage Assessment)
- Two or more deliverables in one invocation → produce in order, separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not silently drop one
- If unclear → Strategy Doc

**Coverage Assessment:**

```markdown
## Vue Test Coverage Assessment

**Stack:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Runner:** Vitest | Jest
**Helper:** @vue/test-utils | @testing-library/vue
**Test framework:** Vitest, [helper], MSW, Playwright (E2E), @nuxt/test-utils (Nuxt)

**Coverage gaps:**

- **Unit:** [pure utilities / Pinia logic / validators without tests]
- **Composable:** [custom composables without tests]
- **Component:** [interactive components without tests; missing empty/error/loading]
- **Integration:** [pages with multi-component flows lacking tests]
- **Nitro:** [endpoints without auth/validation/happy-path tests]
- **E2E:** [critical journeys without Playwright coverage]
- **Accessibility:** [pages without `axe`; interactive components without keyboard/focus tests]

**Recommended pyramid balance** *(rough targets - adjust to risk):*

- Unit + composable: ~50-60%
- Component + integration: ~30-40%
- Nitro: >=1 per endpoint (happy + auth + validation)
- E2E: ~5-10% - critical journeys only

**Prioritization** *(when coverage <50% or >5 gaps)*

1. **P1 - Auth, money, Nitro:** [list]
2. **P2 - Forms and validation:** [list]
3. **P3 - Empty/error/loading:** [list]
4. **P4 - High-churn:** [list]
5. **P5 - Plumbing:** [list]

**Test infrastructure prerequisites** *(when any Step 9 item is missing - must land alongside P1)*

- [missing item, e.g., "no `vitest.config.ts` - components cannot mount under `environment: 'nuxt'`"]
- [...]
```

**Test Scaffolds:** ready-to-run test files in the project's runner idiom (Vitest; Jest only per the Step 2 carve-out), matching project conventions. Each must include:

- Correct test type (unit / composable / component / integration / Nitro / E2E)
- Factories for test data
- Component: happy path + error/empty/loading + a11y check
- Composable: state transitions + cleanup + edge cases
- Nitro: happy + validation failure + unauthorized
- E2E: full journey with auth state seeded via the project's E2E tool (Playwright `storageState`, Cypress session)
- Strict TS; typed `vi.mock` factories; no `as any`

**Strategy Doc:**

```markdown
## Vue Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit+Composable {x}% / Component+Integration {y}% / Nitro {z}% / E2E {w}%
**Tooling:** Vitest, [VTU | TLV], `userEvent`, MSW, Playwright, `vitest-axe`, @nuxt/test-utils (Nuxt)
**Mocking strategy:** MSW for network; provider wrappers for context (router, Pinia, theme, auth); `vi.mock` reserved for non-network module mocks
**Composable strategy:** [`withSetup` for pure | probe component for context-bound | both]
**Nitro strategy:** [direct `$fetch` via @nuxt/test-utils + DB stubbing approach]
**Concurrency:** Vitest `--pool=threads`; Playwright sharded
**Gaps to close (prioritized):**

1. [Highest risk - typically auth / Nitro / form]
2. [...]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed; framework, runner, helper, Vue version recorded
- [ ] Step 3 - target modules and a representative sample of existing tests + setup files read
- [ ] Step 4 - test pyramid mapped to Vue idioms
- [ ] Step 5 - `vue-testing-patterns` consulted; composable strategy explicit (`withSetup`; plugins/provides on the host when context-bound); user-centric queries used; no `wrapper.vm.<internal>` assertions
- [ ] Step 6 - boundaries defined; no duplicated assertions across layers; wizard coverage includes back-navigation + cross-step + submit
- [ ] Step 7 - factories (not raw literals); minimal data per test
- [ ] Step 8 - risk-based prioritization applied when coverage <50% (P1 auth/money/Nitro, P2 forms, P3 empty/error, P4 high-churn, P5 plumbing)
- [ ] Step 9 - infrastructure prerequisites audited; missing pieces surfaced as "must land alongside P1," not buried in Step 10
- [ ] Step 10 - hygiene items checked when assessing or reviewing existing tests
- [ ] Scaffolds only: MSW handlers reset in `afterEach`; TanStack Query uses fresh `QueryClient` with `retry: false`; Sentry mock asserted on error paths; a11y (`axe`) on route-level scaffolds

## Avoid

- Scaffolding without reading existing tests + setup - drifts from project conventions.
- Chasing coverage percentage instead of risk.
- E2E for what a component test could cover.
- Testing implementation details (`wrapper.vm`, render counts, lifecycle calls).
- `getByTestId` as default (TLV); `fireEvent` over `userEvent` (TLV). In VTU, `wrapper.trigger()` is canonical - prefer `userEvent` only for high-fidelity input simulation.
- Calling a composable outside a setup context.
- Mounting a component to test Pinia state - test the store directly.
- Sharing mutable fixtures or asserting CSS class names.
- `as any` in mocks.
