---
name: task-angular-test
description: Angular test strategy and scaffolding using Vitest / Jest / Karma + Angular Testing Library, TestBed, `HttpTestingController`, Angular CDK harnesses, MSW for HTTP stubs, Playwright for E2E, and TypeScript strict-mode test typing. Use when designing a test plan, assessing coverage gaps, or scaffolding component / service / guard / interceptor / E2E tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to Angular.
agent: angular-test-engineer
metadata:
  category: frontend
  tags: [angular, typescript, vitest, jest, karma, angular-testing-library, testbed, http-testing-controller, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `// Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Angular Test

## Purpose

Angular-aware test strategy and scaffolding using Vitest (modern projects), Jest (common via `jest-preset-angular`), or Karma + Jasmine (legacy default), Angular Testing Library (`@testing-library/angular`) for user-centric queries, TestBed for DI-aware mounting, `HttpTestingController` for HTTP mocking at the boundary, Angular CDK component harnesses for Material UI, MSW (`msw`) for browser-realistic HTTP stubs in E2E, Playwright for E2E, and TypeScript strict-mode test typing. Replaces the generic frontend test patterns with Angular-specific guidance: signal-aware test patterns (read signal as function call, `runInInjectionContext` for testing functions that use `inject()`), functional guard / interceptor testing via `TestBed.runInInjectionContext`, HTTP testing via `HttpTestingController` (preferred over service-method mocks), and accessibility-as-tests.

This workflow is the stack-specific delegate of `task-code-test` for Angular. The core workflow's contract (output shape, prioritization rules) is preserved.

## When to Use

- Designing a test strategy for a new Angular app, page, or feature
- Assessing test coverage gaps across unit / component / integration / E2E layers
- Scaffolding tests for under-covered components, services, guards, interceptors, or routes
- Reviewing test pyramid balance for an Angular app
- Adding accessibility / boundary tests (validation, error states, empty states) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-angular-debug`)
- General code review (use `task-code-review` / `task-angular-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If the detected stack is not Angular, stop and tell the user to invoke `/task-code-test` instead.

Detect: Angular major version (Angular 16+ supports signal testing patterns; Angular 17+ has `@if` / `@for` testable; Angular 18+ has signal-form testing primitives). Detect test runner: Vitest (modern), Jest (`jest-preset-angular`), or Karma + Jasmine (CLI default). Detect helper: `@testing-library/angular` vs raw TestBed + `ComponentFixture`. Detect SSR (affects what surfaces have tests). Record `Runner: Vitest | Jest | Karma`, `Helper: @testing-library/angular | TestBed (ComponentFixture)`, `Angular: <version>`, `SSR: enabled | disabled`. Each section that follows branches on these signals where the test idiom differs.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: component shape (standalone, change detection, signals vs RxJS, inputs/outputs), service shape (HTTP calls, state), guard / interceptor shape (functional vs class)
- Glob `**/*.spec.ts`, `**/*.test.ts`, `e2e/**/*.spec.ts` and read at least: one existing component test, one existing service test, one existing Playwright E2E spec, test setup files (`test-setup.ts`, `playwright.config.ts`, `karma.conf.js` if Karma)
- Read `tsconfig.spec.json` for path aliases, strict mode in tests; `vitest.config.ts` / `jest.config.js` / `karma.conf.js` for environment, setup files, coverage config
- Read `test-setup.ts` (or `setup-jest.ts`, `src/test.ts`) for `getTestBed().initTestEnvironment(...)`, MSW server setup if used, global `provide*` calls for testing, harness loader registration
- Read any provider / interceptor / guard / NgRx store that components depend on - they must be configured in TestBed too

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - Angular Test Pyramid

The Angular test pyramid maps to test types:

| Layer       | Tooling                                                                                | What belongs here                                                                                              |
| ----------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Unit        | Vitest / Jest / Karma + plain functions                                                | Utility functions, pipes, NgRx selectors / reducers in isolation, formatters, validators                       |
| Service     | TestBed + `HttpTestingController` for HTTP services; plain instantiation for pure svcs | HTTP services, state services, NgRx effects (with `provideMockActions`)                                        |
| Component   | TestBed + ATL / `ComponentFixture` + harness loader                                    | Component rendering, interaction, accessibility - mount, click, type, assert                                   |
| Integration | TestBed + `RouterTestingModule` (or real `provideRouter` with stub routes) + MSW       | Multi-component flows on a route - filter list, submit form, see updated UI                                    |
| Guard       | `TestBed.runInInjectionContext(() => guardFn(...))` for functional guards              | Auth gates, role gates, can-deactivate logic                                                                   |
| Interceptor | `provideHttpClient(withInterceptors([...]))` + `HttpTestingController`                 | Token attachment, error transformation, retry logic                                                            |
| E2E         | Playwright                                                                             | Critical user journeys - signup, checkout, payment, multi-page flows                                           |
| Visual      | Playwright screenshots / Chromatic / Percy                                             | Visual regression on key components (opt-in)                                                                   |

**Many** unit + service + component tests, **some** integration tests, **few** E2E tests. Guard / interceptor tests sit between unit and integration in cost; aim for one per guard / interceptor covering happy + denial paths.

### Step 4 - Apply Angular Test Patterns

Use skill: `angular-testing-patterns` for the canonical patterns referenced below.

**Unit tests (`*.spec.ts`):**

- Vitest / Jest / Jasmine (`describe`, `it`, `expect`, `beforeEach`); plain instantiation for pure functions and pipes (no TestBed needed)
- Test the public function - one test per outcome (success, validation failure, edge case)
- TypeScript strict: avoid `as any`; use proper typed inputs
- Pipe tests: `new MyPipe().transform(input)` directly - no TestBed needed for stateless pipes; TestBed only when the pipe injects dependencies
- NgRx selector tests: pure functions over state - call directly with a state fixture; assert returned shape

**Service tests with `HttpTestingController` (preferred for HTTP services):**

- `HttpTestingController` is the canonical Angular HTTP mock - it intercepts at the `HttpClient` boundary, not the service method. This means tests verify request shape (method, URL, body, headers) and the service's response handling - both contract layers
- Setup: `TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] })` (Angular 17+) or older `imports: [HttpClientTestingModule]`
- Pattern: instantiate service via `TestBed.inject(MyService)`, call method, then `httpMock.expectOne(...)` to verify and respond, then `httpMock.verify()` in `afterEach` to ensure no unmatched requests
- Flag service tests that mock the service's HTTP method (`spyOn(service as any, 'http')`); that bypasses the contract verification `HttpTestingController` provides

```ts
// Canonical HttpClient service test
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { OrderService } from './order.service';

describe('OrderService', () => {
  let service: OrderService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), OrderService],
    });
    service = TestBed.inject(OrderService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('fetches orders', () => {
    let result: Order[] | undefined;
    service.getOrders().subscribe(r => result = r);

    const req = httpMock.expectOne('/api/orders');
    expect(req.request.method).toBe('GET');
    req.flush([{ id: 1, status: 'open' }]);

    expect(result).toEqual([{ id: 1, status: 'open' }]);
  });
});
```

**Functional guard tests (`CanActivateFn` / `CanMatchFn`):**

- Functional guards are bare functions; they must be called inside an injection context. Use `TestBed.runInInjectionContext(() => authGuard(route, state))` for tests
- Provide stub `Router` / `AuthService` via `TestBed.configureTestingModule({ providers: [...] })` so the guard's `inject()` calls resolve

```ts
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { authGuard } from './auth.guard';

describe('authGuard', () => {
  let router: jasmine.SpyObj<Router>;

  beforeEach(() => {
    router = jasmine.createSpyObj('Router', ['parseUrl']);
    TestBed.configureTestingModule({
      providers: [
        { provide: Router, useValue: router },
        { provide: AuthService, useValue: { isAuthenticated: () => false } },
      ],
    });
  });

  it('redirects unauthenticated user to /login', () => {
    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as any, { url: '/protected' } as any)
    );
    expect(router.parseUrl).toHaveBeenCalledWith('/login');
  });
});
```

**Functional interceptor tests (`HttpInterceptorFn`):**

- Configure TestBed with `provideHttpClient(withInterceptors([myInterceptor]))` and `provideHttpClientTesting`. Make an HTTP call, then `httpMock.expectOne(...)` to verify the interceptor's effect on the request

```ts
beforeEach(() => {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { token: () => 'abc123' } },
    ],
  });
});

it('attaches Authorization header', () => {
  const http = TestBed.inject(HttpClient);
  http.get('/api/data').subscribe();

  const req = TestBed.inject(HttpTestingController).expectOne('/api/data');
  expect(req.request.headers.get('Authorization')).toBe('Bearer abc123');
});
```

**Component tests:**

**With `@testing-library/angular` (preferred for new projects):**

- **User-centric queries**: `getByRole('button', { name: /save/i })`, `getByLabelText(/email/i)`, `getByText(/welcome/i)`. Avoid `getByTestId` except as last resort
- **`userEvent` over `fireEvent`**: `await userEvent.click(button)` simulates real interaction
- **Async assertions**: `await screen.findByText(...)` (built-in waitFor)
- Wrap providers via the `render(Component, { providers: [...], imports: [...], componentInputs: {...} })` API - or build a `renderWithProviders` helper

**With raw TestBed + ComponentFixture (existing projects):**

- `TestBed.configureTestingModule({ imports: [MyComponent], providers: [...] })` (standalone components are imported, not declared)
- `const fixture = TestBed.createComponent(MyComponent)`; `fixture.componentRef.setInput('orderId', 'abc')` for signal inputs (Angular 16+); `fixture.detectChanges()` to trigger initial CD
- Find via `fixture.debugElement.query(By.css('[data-testid="..."]'))` - lower-level than ATL's `getByRole`
- For OnPush components, mutate signals or call `fixture.componentRef.setInput(...)` then `fixture.detectChanges()` - directly modifying `componentInstance` properties may not trigger CD
- **Avoid** asserting on `fixture.componentInstance.<internal>` for component state - test through the rendered DOM and emitted events

**Angular CDK component harnesses (for Material UI):**

- `import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed'`; `const loader = TestbedHarnessEnvironment.loader(fixture)`; `const button = await loader.getHarness(MatButtonHarness.with({ text: 'Save' }))`; `await button.click()`
- Harnesses abstract over Material's DOM structure changes - tests against the public API survive Material upgrades
- Strongly preferred over raw `By.css('mat-button')` selectors

**Signal-aware testing:**

- Read signals as function calls in tests: `expect(component.count()).toBe(0)`; `component.increment(); expect(component.count()).toBe(1)`
- For `computed` signals, set the input dependency, then read: `component.input1.set(5); expect(component.derived()).toBe(10)`
- For `effect()`, trigger CD via `fixture.detectChanges()` (effects run during change detection); assert on the effect's side effect (mock service called, DOM mutated)
- Signal inputs: `fixture.componentRef.setInput('value', 42)` (signal input must be set this way - direct assignment to `component.value` doesn't work because signals are read-only externally)

**Stubs and mocks:**

- For services with HTTP, prefer `provideHttpClientTesting` + `HttpTestingController` over manually mocking the service
- For services without HTTP (state, business logic), `useValue: { method: vi.fn() }` or `useClass: StubMyService` - keep stubs minimal and typed
- For Router: `provideRouter([...stubRoutes])` with stub components (avoids `RouterTestingModule` deprecation in newer Angular)

**One test per `(component-state, user-action, assertion)` triple.** Avoid testing every input permutation - test the contract.

**Accessibility:** `expect(await axe(fixture.nativeElement)).toHaveNoViolations()` via `jest-axe` / `vitest-axe` for any route-level test; per-component tests at minimum assert that interactive elements have accessible names.

**Snapshot tests sparingly**: snapshots churn on every refactor; reserve for stable contract surfaces - never for visual layout.

**Integration tests:**

- Render the route-level component with all real children; mock only the network via `HttpTestingController` (or MSW for browser-realistic E2E)
- Walk through the user flow: type into search, click filter, see filtered list - assertions at each user-visible step
- Use `provideRouter([...])` with explicit initial navigation (`router.navigateByUrl('/initial')`) before the component renders

**MSW for HTTP (E2E and browser-realistic component tests):**

- `setupServer(...handlers)` in test setup; `server.listen({ onUnhandledRequest: 'error' })` to fail loud on missed stubs
- For Angular component tests inside Karma / Jest / Vitest with jsdom, `HttpTestingController` is usually preferred (faster, contract-aware). MSW shines when you want network-level realism (e.g., integration with a service worker, CORS testing) - typically Playwright tests
- Reset handlers in `afterEach`: `server.resetHandlers()` removes per-test overrides

**NgRx tests:**

- **Reducers**: pure functions; call `myReducer(state, action)` with state fixture; assert returned shape
- **Selectors**: pure functions; call selector with state fixture; assert derived value
- **Effects**: use `provideMockActions(() => actions$)` from `@ngrx/effects/testing`; provide stub services; subscribe to effect output, dispatch action, assert outputs

**Sentry / error tracker mock:**

- `vi.mock('@sentry/angular', () => ({ captureException: vi.fn(), setUser: vi.fn() }))` (Vitest); equivalent in Jest
- Assert `captureException` was called with the expected `Error` after the component's error path runs

**Playwright E2E (`e2e/*.spec.ts`):**

- Reserve for critical journeys: signup, checkout, multi-step forms, money flows
- One spec per journey, not per page
- Use `data-testid` only as a last-resort selector; prefer `getByRole` / `getByLabel` for resilience
- Auth setup via `storageState` fixture (login once, save state, reuse across tests) - fast and reliable
- API stubbing via `page.route('**/api/orders', route => route.fulfill({...}))` for tests asserting specific backend states
- Run against a built app (`ng build && ng serve --configuration=production`) - dev mode has different behavior (HMR, source maps, dev-only error overlays)

### Step 5 - Test Boundaries (Angular-Specific)

**What deserves a unit test:**

- Pure utilities (formatters, parsers, date helpers, currency math)
- Pipes without DI - call `.transform()` directly
- NgRx selectors / reducers (pure functions over state)
- Validators (custom validators - test edge cases)
- Selectors / derived data functions

**What deserves a service test:**

- Every HTTP service: shape verification via `HttpTestingController` + response handling
- Every state service exposing a signal / observable: state transitions, derived computations
- NgRx effects: action → side-effect → action mapping

**What deserves a component test:**

- Every interactive component (form, modal, dropdown, menu, dialog, tabs, accordion)
- Empty / loading / error states - especially "no items" and "API failed" branches
- Conditional rendering paths (auth-gated UI, feature-flag-gated UI, content-projection composition)
- Accessibility (label association, keyboard navigation, focus management)

**What deserves a guard / interceptor test:**

- Every functional guard - happy path + denial path (return UrlTree / false)
- Every functional interceptor - request transformation (token added, retry logic, error mapping)

**What deserves an integration test:**

- Filter + list interactions (filter changes update list, URL syncs, deep link works)
- Form flows (multi-step wizard, validation across steps)
- Optimistic-update flows (mutate → see immediate UI change → rollback on error)

**Multi-step form / wizard testing strategy:**

Cover at minimum:

- **Forward navigation:** valid input on step N advances to step N+1; the submit button is disabled until each step's validation passes
- **Backward navigation preserves state:** step 1 → step 2 → back to step 1 → fields still populated
- **Cross-step validation:** a field on step 3 that depends on a step 1 value
- **Cancel / reset:** discarding the wizard clears state
- **Submit flow:** the final submit calls the endpoint with the accumulated form state from all steps

For wizards using NgRx or signal-based stores, unit-test the store separately - that is the lowest-overhead place to assert all the transitions. The component test then asserts the wiring.

**What deserves an E2E test:**

- Authentication and onboarding journey (signup, email verify, first-run)
- Checkout / payment journey
- Critical multi-page flows where contract between pages matters
- Routing flows that depend on real navigation (route guards, lazy-loaded chunks, route data resolvers)

**What does NOT need a test:**

- Framework-provided behavior: `RouterLink` navigation, NgRx Store internals, Angular Forms primitives - test your wiring, not the framework
- Generated boilerplate: typed inputs with no logic, simple wrapper components
- Trivial components: a `<Button>` re-exporting a primitive with one input - covered by parents
- Visual layout details (margin, padding) - belongs to visual regression, not unit tests
- Pure presentation components in isolation if they have no logic - test via the parent that uses them

### Step 6 - Test Data and Fixtures

- Prefer factory utilities (`createUserFactory`, `@faker-js/faker` for primitives, or `fishery`) over hand-rolled object literals
- Co-locate factories with the schema / types they produce (`test/factories/user.ts`)
- For component tests: factories produce minimal valid props; tests override only the field under test
- Avoid mutating shared test fixtures - rebuild via factory in `beforeEach`
- Test data must be minimal and focused

### Step 7 - Prioritization (when coverage is low)

If line / branch coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first.

When starting from low test coverage, prioritize by Angular-specific risk:

**Priority 1 - Auth, money, and HTTP services:**

- Every HTTP service: shape verification + response handling tests
- Every functional guard / interceptor: auth path + denial path
- Auth flows: signup, login, password reset, session expiry behavior
- Money / billing components: checkout, plan-change, refund

**Priority 2 - Forms and validation:**

- Every Reactive Form with validators - test invalid inputs surface errors, valid inputs submit
- Multi-step wizards - completion path + back-navigation preserves state

**Priority 3 - Empty / error / loading states:**

- Every list / data view tested with empty state, loading skeleton, and error fallback
- Global `ErrorHandler` test that thrown errors are routed to Sentry / structured logger

**Priority 4 - High-churn components:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pure presentation, simple wrappers, plain styled components - lowest risk

### Step 7.5 - Test Infrastructure Prerequisites

Before scaffolding or recommending tests, audit whether the harness needed to _run_ them exists. A prioritized test list against an empty `test-setup.ts` is a paper plan. Read the project for these markers and surface every missing piece as a prerequisite that must land **alongside** P1 work, not after it:

- [ ] Test runner config present (`vitest.config.ts` / `jest.config.js` / `karma.conf.js`) with the right environment (`jsdom` / `happy-dom` for components), path aliases matching `tsconfig.json`, and a `setupFiles` entry
- [ ] `test-setup.ts` (or `setup-jest.ts` / `src/test.ts`) wires `getTestBed().initTestEnvironment(...)` (often via `BrowserDynamicTestingModule`); registers harness loader; sets up MSW (`setupServer`, `server.listen({ onUnhandledRequest: 'error' })`, `server.resetHandlers()` in `afterEach`, `server.close()` in `afterAll`) when MSW is the chosen network mock
- [ ] Shared `renderWithProviders` helper (when using ATL) or shared `TestBed.configureTestingModule({ imports, providers })` factory - else every test re-derives the provider chain
- [ ] `test/factories/<entity>.ts` for the project's main domain types
- [ ] `playwright.config.ts` present when E2E is in scope (otherwise note "E2E not yet wired" and require the config as a prerequisite to any P1 E2E item)
- [ ] Dev dependencies present for the chosen tooling: `@angular/cdk/testing` (harnesses), `@testing-library/angular` (when chosen), `jest-axe` / `vitest-axe` (a11y), `msw` (when chosen), `@ngrx/effects/testing` (for NgRx effects)
- [ ] CI is configured to run the test runner + Playwright (when E2E in scope) and the coverage tool wired

When any of these are missing, render them as a separate **Test infrastructure prerequisites** subsection of the Coverage Assessment (template below) and label them "must land alongside P1." Do not bury them in Step 8's hygiene checks - those are for ongoing maintenance, not first-test prerequisites.

### Step 8 - Test Infrastructure Hygiene

- [ ] Test environment is `jsdom` / `happy-dom` (Vitest / Jest) or browser (Karma); Angular requires DOM for component tests
- [ ] `getTestBed().initTestEnvironment(BrowserDynamicTestingModule, ...)` called once in setup file
- [ ] `HttpTestingController.verify()` called in `afterEach` for every service test using HTTP - catches unmatched / over-matched requests
- [ ] `userEvent.setup()` per test (not module-level singleton) when using ATL
- [ ] Cleanup: TestBed automatically resets between tests when `resetTestingModule: true` (default); verify by checking for "leaked" elements between tests
- [ ] Strict TypeScript in tests: same `tsconfig.spec.json` extending `tsconfig.json`; no `as any` shortcuts
- [ ] Coverage tool wired to CI with per-package thresholds; coverage exclusions documented
- [ ] Playwright config: `retries: 2` on CI for flake tolerance, `0` locally; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] No real network calls (assert `HttpTestingController` unmatched fails the test); no real filesystem in component tests
- [ ] CI runs Vitest / Jest / Karma + Playwright in parallel; Playwright sharded across workers for speed
- [ ] Visual regression (if used): Chromatic / Percy / Playwright screenshots gated to `main`-branch builds, not every PR

## Angular Review Checklist

Quick-reference checklist for reviewing existing Angular tests:

- [ ] Test type matches what is being tested (component → ATL/TestBed, HTTP service → `HttpTestingController`, guard → `runInInjectionContext`, interceptor → `provideHttpClient(withInterceptors([...]))` + `HttpTestingController`, journey → Playwright)
- [ ] HTTP services tested via `HttpTestingController`, not by mocking service methods
- [ ] Functional guards tested via `TestBed.runInInjectionContext(() => guardFn(...))`, not by stubbing the guard's internals
- [ ] Material UI tested via CDK harnesses, not raw `By.css('mat-button')` selectors
- [ ] Signal inputs set via `fixture.componentRef.setInput(...)`, signals read as function calls
- [ ] Queries are user-centric (`getByRole`, `getByLabel`); `getByTestId` only as last resort
- [ ] `userEvent` over `fireEvent` for user interactions when using ATL
- [ ] No tests of implementation details (asserting `fixture.componentInstance.<internal>`, render counts, lifecycle method calls)
- [ ] Async assertions use `findBy*` / `waitFor` / `fixture.whenStable()` - no `setTimeout` waits
- [ ] `HttpTestingController.verify()` called in `afterEach`
- [ ] No `as any` on mocked methods; typed `vi.mock` / `jest.mock` factories
- [ ] Snapshot tests reserved for stable contracts; no UI-layout snapshots
- [ ] E2E tests cover critical journeys, not what a component test could cover
- [ ] NgRx effects tested with `provideMockActions`, not by manually triggering
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
## Angular Test Coverage Assessment

**Stack:** Angular <version> / TypeScript <version>
**Runner:** Vitest | Jest | Karma
**Helper:** @testing-library/angular | TestBed (ComponentFixture)
**SSR:** enabled | disabled
**Test framework:** [runner], [helper], `HttpTestingController`, CDK harnesses, Playwright (E2E), MSW (where applicable)
**Coverage gaps:**

- **Unit tests:** [pure utilities / pipes / NgRx selectors without test coverage]
- **Service tests:** [HTTP services without `HttpTestingController` tests; state services without test coverage]
- **Component tests:** [interactive components without tests; missing empty / error / loading states]
- **Integration tests:** [route-level pages with multi-component flows lacking integration tests]
- **Guard / Interceptor tests:** [functional guards / interceptors without tests for happy + denial paths]
- **E2E tests:** [critical journeys without Playwright coverage]
- **Accessibility:** [pages without `axe` checks; interactive components without keyboard / focus tests]

**Recommended pyramid balance:**

- Unit + service (utilities, pipes, services): [count target]
- Component + integration (TestBed/ATL + `HttpTestingController`): [count target]
- Guard / Interceptor: [count target - one per guard / interceptor minimum]
- E2E (Playwright): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Auth, money, HTTP services / guards / interceptors:** [list specific services / guards / interceptors / billing components missing tests]
2. **P2 - Forms and validation:** [forms with validation logic without tests]
3. **P3 - Empty / error / loading states:** [list views without these branches tested]
4. **P4 - High-churn:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pure presentation / wrappers - lowest risk]

**Test infrastructure prerequisites** _(include when any Step 7.5 item is missing - these must land alongside P1 because no test can be authored without them)_

- [missing item 1, e.g., "no `vitest.config.ts` - components cannot mount under jsdom"]
- [missing item 2, e.g., "no `getTestBed().initTestEnvironment(...)` call - first TestBed test will fail with `Test environment not initialized`"]
- [missing item 3, e.g., "MSW not installed - browser-realistic E2E network mocks unavailable; for component tests `HttpTestingController` covers it"]
- [...]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run test files using project conventions. Each scaffold must include:

- The right test type (unit / service / component / integration / guard / interceptor / E2E)
- Factories for test data
- Component scaffolds: happy path + error / empty / loading states + a11y check
- Service scaffolds: `HttpTestingController` setup + happy path + error response + `verify()` in `afterEach`
- Guard scaffolds: `TestBed.runInInjectionContext` + happy + denial paths
- Interceptor scaffolds: `provideHttpClient(withInterceptors([...]))` + `HttpTestingController` + assertion on transformed request / response
- E2E scaffolds: full journey, with `storageState` for auth
- TypeScript strict: typed mocks, no `as any`

**Strategy Doc** (when designing a test strategy):

```markdown
## Angular Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit + Service {x}% / Component + Integration {y}% / Guard / Interceptor {z}% / E2E {w}%
**Tooling:** [runner], [helper], `HttpTestingController`, CDK harnesses, Playwright, `jest-axe` / `vitest-axe`, MSW (where applicable), `@ngrx/effects/testing` (when NgRx in use)
**Mocking strategy:** `HttpTestingController` for HTTP boundary; provider stubs (`useValue`) for non-HTTP services; MSW for browser-realistic E2E
**Signal strategy:** [test signals as function calls; signal inputs via `setInput`; effects via `detectChanges`]
**HTTP strategy:** [`HttpTestingController` for service tests; `provideHttpClient(withInterceptors([...]))` for interceptor tests]
**Concurrency:** Vitest --threads / --pool=threads (or Jest --maxWorkers); Playwright sharded across workers
**Gaps to close (prioritized):**

1. [Highest risk gap - typically auth / HTTP service / guard / interceptor]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as Angular; runner (Vitest / Jest / Karma) and helper (ATL / TestBed) recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + setup files read directly so output matches project conventions (Step 2)
- [ ] `angular-testing-patterns` consulted for canonical Angular test patterns
- [ ] HTTP service testing strategy explicit (`HttpTestingController` at the boundary, not service method mocks)
- [ ] Functional guard / interceptor strategy explicit (`runInInjectionContext` for guards; `withInterceptors` + `HttpTestingController` for interceptors)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Angular idioms (unit → runner; service → `HttpTestingController`; component → TestBed/ATL + harnesses; integration → TestBed + MSW or `HttpTestingController`; guard → `runInInjectionContext`; interceptor → `withInterceptors` + `HttpTestingController`; E2E → Playwright)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 auth/money/HTTP/guards, P2 forms, P3 empty/error states, P4 high-churn, P5 plumbing
- [ ] Accessibility testing presence assessed (`jest-axe` / `vitest-axe` per route-level test)
- [ ] Test infrastructure prerequisites audited (Step 7.5): missing test runner config / `getTestBed().initTestEnvironment` / shared `configureTestingModule` factory / factories / `playwright.config.ts` / dev deps surfaced as "must land alongside P1," not buried in Step 8 hygiene

**Test Scaffolds only:**

- [ ] Test data created via factories, not raw object literals; typed factory return shapes
- [ ] Component scaffolds use user-centric queries (`getByRole` / `getByLabel`); `getByTestId` only as last resort
- [ ] Component scaffolds use `userEvent` (not `fireEvent`) when meaningful (ATL) or `triggerEventHandler` (TestBed)
- [ ] Component scaffolds cover happy path + error + empty + loading states
- [ ] Signal inputs set via `fixture.componentRef.setInput(...)`; signals read as function calls
- [ ] Service scaffolds use `HttpTestingController` with `verify()` in `afterEach`; happy + error response paths
- [ ] Guard scaffolds use `TestBed.runInInjectionContext`; cover happy + denial paths
- [ ] Interceptor scaffolds use `provideHttpClient(withInterceptors([...]))` + `HttpTestingController`; assertion on request transformation
- [ ] Material UI tested via CDK harnesses, not raw `By.css('mat-...')` selectors
- [ ] NgRx effects: `provideMockActions(() => actions$)` from `@ngrx/effects/testing`
- [ ] NgRx selectors / reducers: pure-function tests, no TestBed
- [ ] Error tracker (`Sentry.captureException`) mocked when the component handles errors; assertion that capture happened on the error path
- [ ] E2E scaffolds use `getByRole` selectors and `storageState` for auth setup
- [ ] No `as any` in mocks; typed mock factories
- [ ] Accessibility check (`axe`) included for route-level / page-level scaffolds

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + setup files - the result imports the wrong factory, uses the wrong mocking convention, or duplicates the existing TestBed factory
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no `HttpTestingController` tests on services misses the bigger threat
- E2E tests for what a component test could cover - context cost compounds across the suite
- Testing implementation details: `fixture.componentInstance.<internal>`, render counts, lifecycle method calls - tests break on every refactor
- `getByTestId` everywhere - test IDs are an escape hatch, not a default; user-centric queries reflect what users actually see
- Mocking HTTP at the service-method level instead of `HttpTestingController` - bypasses the request-shape verification the controller provides
- Calling a functional guard / interceptor outside an injection context - throws or no-ops; use `TestBed.runInInjectionContext`
- Snapshot tests for visual layout - they churn on every restyle and provide no signal; reserve for stable contracts
- Skipping `HttpTestingController.verify()` in `afterEach` - unmatched requests pass silently and tests rot
- Mounting a full component to test NgRx selector / reducer logic - test pure functions directly without TestBed
- Real network calls in component tests - flaky and slow; `HttpTestingController` enforces the boundary
- Sharing mutable fixtures across tests - leaks state and produces order-dependent failures
- Asserting CSS class names (`expect(el).toHaveClass('text-red-500')`) - couples tests to styling implementation; assert visible behavior or accessibility properties instead
- `as any` to silence TypeScript in mocks - defeats strict mode; use typed mock factories
- Using raw `By.css('mat-...')` selectors for Material components when CDK harnesses exist - tests break on every Material upgrade
