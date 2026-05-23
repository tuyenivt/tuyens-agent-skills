---
name: task-angular-test
description: Angular test plan and scaffolding: Vitest/Jest/Karma, Angular Testing Library, TestBed, HttpTestingController, CDK harnesses, MSW, Playwright.
agent: angular-test-engineer
metadata:
  category: frontend
  tags: [angular, typescript, vitest, jest, karma, angular-testing-library, testbed, http-testing-controller, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

# Angular Test

Stack-specific delegate of `task-code-test` for Angular. Preserves the core workflow's output contract.

## When to Use

- Design a test strategy for a new Angular app, page, or feature
- Assess coverage gaps across unit / service / component / integration / guard / interceptor / E2E layers
- Scaffold tests for under-covered components, services, guards, interceptors, or routes
- Review test pyramid balance for an Angular app

**Not for:** test failure debugging (`task-angular-debug`), general code review (`task-angular-review`), incident postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Apply behavioral principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm stack

Use skill: `stack-detect`. If invoked as a delegate of `task-code-test` (parent already detected Angular), accept the pre-confirmed stack. If stack is not Angular, stop and tell the user to invoke `/task-code-test`.

Record `Angular: <version>`, `Runner: Vitest | Jest | Karma`, `Helper: @testing-library/angular | TestBed (ComponentFixture)`, `SSR: enabled | disabled`. Angular 16+ enables signal testing; 17+ has `@if`/`@for`; 18+ has signal-form primitives.

### Step 3 - Apply spec-aware mode (conditional)

If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, Use skill: `spec-aware-preamble`. Generate one test per acceptance criterion (`// Satisfies: AC<N>` or test-name suffix), cover every NFR from `plan.md`, refuse tests for out-of-scope behavior. Never edit spec artifacts; surface gaps as proposed amendments.

### Step 4 - Read code under test and existing tests

Before producing output, read both production code and a representative sample of tests so output matches project convention.

- Target module: component shape (standalone, change detection, signals vs RxJS, inputs/outputs), service shape (HTTP, state), guard/interceptor shape (functional vs class)
- One component spec, one service spec, one Playwright spec; setup files (`test-setup.ts` / `setup-jest.ts` / `src/test.ts`, `playwright.config.ts`, `karma.conf.js` if Karma)
- `tsconfig.spec.json` for path aliases / strict; `vitest.config.ts` / `jest.config.js` / `karma.conf.js` for environment, setup files, coverage
- Setup file for `getTestBed().initTestEnvironment(...)`, MSW `setupServer` (if used), harness loader registration, global `provide*`
- Providers / interceptors / guards / NgRx store that components depend on - they must be configured in TestBed too

Greenfield (no existing tests): state choices explicitly, do not invent silently. Defaults: Vitest + ATL + `userEvent`; `HttpTestingController` at the boundary; MSW with `onUnhandledRequest: 'error'` for E2E only; Playwright for journeys; `vitest-axe`; shared `renderWithProviders`; factories in `test/factories/`.

Use skill: `angular-testing-patterns` for canonical Angular test forms (ATL render, TestBed + `HttpTestingController`, signal-based service, four-state coverage, Material harness, signal-input components, functional guard, Playwright).

### Step 5 - Angular test pyramid

| Layer       | Tooling                                                                    | What belongs here                                                          |
| ----------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Unit        | Runner + plain functions                                                   | Utilities, pipes (no DI), validators, NgRx selectors / reducers            |
| Service     | TestBed + `HttpTestingController` (HTTP); plain instantiation (pure)       | HTTP services, state services, NgRx effects (`provideMockActions`)         |
| Component   | TestBed + ATL or `ComponentFixture` + CDK harnesses (Material)             | Component rendering, interaction, a11y - mount, click, type, assert        |
| Integration | TestBed + `provideRouter([...])` + `HttpTestingController`                 | Multi-component flows on a route - filter list, multi-step form            |
| Guard       | `TestBed.runInInjectionContext(() => guardFn(...))`                        | Auth gates, role gates, can-deactivate                                     |
| Interceptor | `provideHttpClient(withInterceptors([...]))` + `HttpTestingController`     | Token attachment, error transformation, retry logic                        |
| E2E         | Playwright                                                                 | Critical user journeys - signup, checkout, payment, multi-page             |
| Visual      | Chromatic / Percy / Playwright screenshots                                 | Visual regression on stable components (opt-in, gated to `main`)           |

**Many** unit + service + component, **some** integration, **few** E2E. One test per guard / interceptor covering happy + denial paths.

### Step 6 - Apply Angular test patterns

Patterns live in `angular-testing-patterns`; this step calls out workflow-level decisions only.

**HTTP boundary.** Test services via `HttpTestingController` (`provideHttpClient()` + `provideHttpClientTesting()`); never `spyOn(service as any, 'http')`. Verify request method, URL, body, headers, then `req.flush(...)`; call `httpMock.verify()` in `afterEach`.

**Functional guards / interceptors.** Guards: `TestBed.runInInjectionContext(() => guardFn(route, state))` with stub `Router` / `AuthService` providers. Interceptors: `provideHttpClient(withInterceptors([myInterceptor]))` + `provideHttpClientTesting()`, then assert via `httpMock.expectOne(...)`. Both must cover happy + denial paths.

**Signals.** Read signals as function calls (`component.count()`). Set signal inputs via `fixture.componentRef.setInput('value', 42)` (direct assignment fails). `effect()` runs during CD - trigger via `fixture.detectChanges()` and assert the side effect, not the effect itself.

**Component test choice.** ATL for new projects (user-centric queries, `userEvent`, `render(Component, { inputs, on, providers })`); TestBed + `ComponentFixture` only when fixture-level control is required (manual CD, harness loader, OnPush input via `setInput`). Material UI: CDK harnesses (`TestbedHarnessEnvironment.loader(fixture)`), never raw `By.css('mat-button')`.

**Router stubs.** `provideRouter([...stubRoutes])` over deprecated `RouterTestingModule`; initial navigation before render when route guards depend on it.

**MSW vs `HttpTestingController`.** `HttpTestingController` for component/service tests under jsdom (faster, contract-aware). MSW only for browser-realistic flows (service worker, CORS) - typically Playwright.

**NgRx.** Reducers / selectors: pure-function tests, no TestBed. Effects: `provideMockActions(() => actions$)` from `@ngrx/effects/testing`.

**Error tracker.** `vi.mock('@sentry/angular', () => ({ captureException: vi.fn(), setUser: vi.fn() }))` (or Jest equivalent); assert capture on the error path.

**A11y.** `axe(fixture.nativeElement)` via `jest-axe` / `vitest-axe` at route-level tests; per-component tests assert accessible names.

**Snapshots sparingly.** Stable contract surfaces only, never visual layout.

### Step 7 - Test boundaries

**Unit:** utilities (formatters, parsers, currency), pipes without DI (`new MyPipe().transform(input)`), NgRx selectors/reducers, validators (edge cases).

**Service:** every HTTP service (request shape + response handling); every state service exposing a signal/observable (transitions, derived); NgRx effects (action -> side-effect -> action).

**Component:** every interactive component (form, modal, dropdown, menu, dialog, tabs); empty / loading / error branches; conditional rendering (auth-gated, flag-gated, content projection); a11y (label association, keyboard nav, focus).

**Integration:** filter + list (filter updates list, URL syncs, deep link); multi-step wizards (see below); optimistic-update flows (mutate -> see UI -> rollback on error).

**Multi-step form / wizard.** A single integration test walks the full path; focused component tests cover each step's validation. Cover:

- Forward: valid step N advances to N+1; submit disabled until validation passes
- **Backward preserves state:** step 1 -> 2 -> back -> fields still populated (most-broken in practice)
- Cross-step validation: a step-3 field depending on a step-1 value recomputes after back-edit
- Cancel / reset clears state
- Submit calls the endpoint with merged payload from all steps

NgRx / signal-store wizards: unit-test the store separately; the component test asserts wiring.

**Guard / Interceptor:** every functional guard (happy + denial / UrlTree); every functional interceptor (request transformation, retry, error mapping).

**E2E:** auth / onboarding journey, checkout / payment, critical multi-page contracts, real-navigation flows (route guards, lazy chunks, resolvers).

**Does NOT need a test:** framework behavior (`RouterLink`, NgRx Store internals, Forms primitives); typed inputs with no logic; trivial wrappers covered by parents; visual layout (margin, padding) - belongs to visual regression; pure presentation with no logic - covered via parent.

### Step 8 - Prioritize when coverage is low

When coverage is below ~50%, run this **before** scaffolding - choose what to scaffold first.

1. **P1 - Auth, money, HTTP / guards / interceptors:** every HTTP service (shape + response); every functional guard / interceptor (happy + denial); auth flows (signup, login, reset, session expiry); checkout / billing / refund.
2. **P2 - Forms and validation:** every Reactive Form with validators; multi-step wizards (completion + back-preserves-state).
3. **P3 - Empty / error / loading:** every list / data view with empty + skeleton + error; global `ErrorHandler` routes thrown errors to Sentry / structured logger.
4. **P4 - High-churn:** files with frequent recent commits (`git log --since="3 months ago"`) or fix history (`git log --grep="fix"`).
5. **P5 - Plumbing:** pure presentation, simple wrappers - lowest risk.

**Multi-band rule.** When a target qualifies for multiple bands (checkout form is both P1 money and P2 form), file under the highest band and cover both axes.

### Step 9 - Audit test infrastructure prerequisites

A prioritized list against an empty setup is a paper plan. When any of the following is missing, surface as a **Test infrastructure prerequisites** subsection of the Coverage Assessment, labelled "must land alongside P1":

- [ ] Runner config (`vitest.config.ts` / `jest.config.js` / `karma.conf.js`) with `jsdom`/`happy-dom` environment, path aliases, `setupFiles`
- [ ] Setup file wires `getTestBed().initTestEnvironment(BrowserDynamicTestingModule, ...)`, harness loader registration, MSW (`setupServer` + `listen({ onUnhandledRequest: 'error' })` + `resetHandlers` in `afterEach` + `close` in `afterAll`) when MSW is the chosen network mock
- [ ] Shared `renderWithProviders` helper (ATL) or shared TestBed factory - else every test re-derives providers
- [ ] `test/factories/<entity>.ts` for main domain types
- [ ] `playwright.config.ts` when E2E in scope
- [ ] Dev deps for chosen tooling: `@angular/cdk/testing`, `@testing-library/angular`, `jest-axe` / `vitest-axe`, `msw`, `@ngrx/effects/testing`
- [ ] CI runs the runner + Playwright; coverage tool wired

### Step 10 - Test infrastructure hygiene

- [ ] Test environment is `jsdom` / `happy-dom` (Vitest / Jest) or browser (Karma)
- [ ] `HttpTestingController.verify()` called in `afterEach` for every HTTP service test - catches unmatched / over-matched
- [ ] `userEvent.setup()` per test (not module singleton) when using ATL
- [ ] Strict TypeScript in tests; no `as any` in mocks; typed mock factories
- [ ] Coverage tool wired to CI with per-package thresholds; exclusions documented
- [ ] Playwright: `retries: 2` on CI / `0` locally; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] No real network (`HttpTestingController` unmatched fails); no real filesystem in component tests
- [ ] CI runs runner + Playwright in parallel; Playwright sharded across workers
- [ ] Visual regression gated to `main`-branch builds, not every PR

## Output Format

**Which output:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / "test plan" / coverage < 50% without scaffold request -> Strategy Doc
- Multiple deliverables in one ask -> produce in order separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds. Do not silently drop one.
- Unclear -> Strategy Doc as default.

**Coverage Assessment:**

```markdown
## Angular Test Coverage Assessment

**Stack:** Angular <version> / TypeScript <version>
**Runner:** Vitest | Jest | Karma
**Helper:** @testing-library/angular | TestBed (ComponentFixture)
**SSR:** enabled | disabled
**Test framework:** [runner], [helper], `HttpTestingController`, CDK harnesses, Playwright, `vitest-axe` / `jest-axe`, MSW (where applicable)

**Coverage gaps:**

- **Unit:** [utilities / pipes / NgRx selectors without coverage]
- **Service:** [HTTP services without `HttpTestingController` tests; state services without coverage]
- **Component:** [interactive components without tests; missing empty / error / loading]
- **Integration:** [route-level pages with multi-component flows lacking integration tests]
- **Guard / Interceptor:** [functional guards / interceptors without happy + denial coverage]
- **E2E:** [critical journeys without Playwright]
- **Accessibility:** [routes without `axe`; interactive elements without keyboard / focus tests]

**Pyramid balance:** Unit + Service [n] / Component + Integration [n] / Guard + Interceptor [n] / E2E [n - keep small]

**Prioritization** _(when coverage < ~50% or > 5 gaps)_

1. P1 - Auth / money / HTTP / guards / interceptors: [list]
2. P2 - Forms / validation / wizards: [list]
3. P3 - Empty / error / loading: [list]
4. P4 - High-churn: [files]
5. P5 - Plumbing: [list]

**Test infrastructure prerequisites** _(when any Step 9 item is missing - must land alongside P1)_

- [missing item, e.g., "no `vitest.config.ts` - components cannot mount under jsdom"]
- [...]
```

**Test Scaffolds:** ready-to-run files using project conventions. Each scaffold:

- Right test type (unit / service / component / integration / guard / interceptor / E2E)
- Factories for data (no raw object literals)
- User-centric queries (`getByRole` / `getByLabel`); `userEvent`, not `fireEvent`
- Component: happy + error + empty + loading + a11y (`axe` at route level); signal inputs via `setInput`, signals read as function calls
- Service: `HttpTestingController` setup + happy + error + `verify()` in `afterEach`
- Guard: `TestBed.runInInjectionContext` + happy + denial paths
- Interceptor: `provideHttpClient(withInterceptors([...]))` + `HttpTestingController` + request-transformation assertion
- Material UI via CDK harnesses
- NgRx effects via `provideMockActions`; selectors / reducers as pure-function tests
- E2E: full journey, `storageState` for auth, `page.route` for API stubs
- Strict TS; typed mock factories; no `as any`

**Strategy Doc:**

```markdown
## Angular Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit + Service {x}% / Component + Integration {y}% / Guard + Interceptor {z}% / E2E {w}%
**Tooling:** [runner], [helper], `HttpTestingController`, CDK harnesses, Playwright, `vitest-axe` / `jest-axe`, MSW (E2E only), `@ngrx/effects/testing` (when NgRx in use)
**Mocking:** `HttpTestingController` at the HTTP boundary; provider stubs (`useValue`) for non-HTTP services; MSW only for browser-realistic E2E
**Signal strategy:** signals as function calls; inputs via `setInput`; effects via `detectChanges`
**Concurrency:** Vitest `--pool=threads` (or Jest `--maxWorkers`); Playwright sharded across workers
**Gaps to close (prioritized):**

1. [Highest-risk gap, typically auth / HTTP service / guard / interceptor]
2. [...]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded before any other step
- [ ] Step 2 - Stack confirmed as Angular; `Angular`, `Runner`, `Helper`, `SSR` recorded
- [ ] Step 3 - Spec-aware mode honored when `--spec` passed (one test per AC, NFR coverage, no out-of-scope tests)
- [ ] Step 4 - Code under test, sample existing tests, and setup files read directly; `angular-testing-patterns` consulted
- [ ] Step 5 - Pyramid mapped to Angular idioms (unit -> runner; service -> `HttpTestingController`; component -> TestBed/ATL + harnesses; guard -> `runInInjectionContext`; interceptor -> `withInterceptors` + `HttpTestingController`; E2E -> Playwright)
- [ ] Step 6 - Patterns applied: `HttpTestingController` not service-method mocks; functional guards via `runInInjectionContext`; signals read as function calls and set via `setInput`; Material via CDK harnesses; `provideRouter` over `RouterTestingModule`; NgRx effects via `provideMockActions`; a11y via `axe`
- [ ] Step 7 - Boundaries respected (no E2E for what a component test covers; framework internals not tested); multi-step wizard covers forward + backward-preserves-state + cross-step + submit
- [ ] Step 8 - Risk bands applied when coverage is low; multi-band targets covered on both axes
- [ ] Step 9 - Infrastructure prerequisites audited; missing items surfaced as "must land alongside P1," not buried in hygiene
- [ ] Step 10 - Hygiene checks pass (`HttpTestingController.verify()` in `afterEach`, fresh `userEvent.setup()`, no real network, strict TS)

## Avoid

- Scaffolding without reading existing tests + setup files - imports wrong factory, duplicates the TestBed factory
- Chasing coverage % over risk - 100% lines with no `HttpTestingController` tests on services misses the bigger threat
- E2E for what a component test covers - context cost compounds across the suite
- Testing implementation details (`fixture.componentInstance.<internal>`, render counts, lifecycle calls) - breaks on every refactor
- `getByTestId` as default - escape hatch, not entry point; user-centric queries reflect real users
- Mocking HTTP at the service method instead of `HttpTestingController` - bypasses request-shape verification
- Calling a functional guard / interceptor outside an injection context - throws or no-ops; use `runInInjectionContext`
- Raw `By.css('mat-...')` selectors when CDK harnesses exist - tests break on every Material upgrade
- Skipping `HttpTestingController.verify()` in `afterEach` - unmatched requests pass silently and tests rot
- Mounting a full component to test NgRx selector / reducer logic - test pure functions directly
- Snapshot tests for visual layout - churn on every restyle; reserve for stable contracts
- Real network in component tests - flaky and slow; `HttpTestingController` enforces the boundary
- Sharing mutable fixtures across tests - leaks state, order-dependent failures
- Asserting CSS class names (`toHaveClass('text-red-500')`) - couples tests to styling; assert visible behavior or a11y
- `as any` to silence TypeScript in mocks - defeats strict mode; use typed mock factories
- `setTimeout` waits for async work - use `findBy*` / `waitFor` / `fixture.whenStable()`
