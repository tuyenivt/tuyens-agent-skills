---
name: task-angular-test
description: Angular test plan and scaffolding - Vitest/Jest, ATL, TestBed, HttpTestingController, CDK harnesses, Playwright.
agent: angular-test-engineer
metadata:
  category: frontend
  tags: [angular, typescript, vitest, jest, karma, angular-testing-library, testbed, http-testing-controller, msw, playwright, testing, workflow]
  type: workflow
user-invocable: true
---

# Angular Test

Stack-specific delegate of `task-code-test` for Angular.

## When to Use

- Design a test strategy for a new app, page, or feature
- Assess coverage gaps across unit / service / component / integration / guard / interceptor / E2E
- Scaffold tests for under-covered targets
- Review test pyramid balance

**Not for:** test failure debugging (`task-angular-debug`), general code review (`task-angular-review`), incident postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Apply behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. If not Angular, stop. Record `Angular: <version>`, `Runner: Vitest | Jest | Karma`, `Helper: @testing-library/angular | TestBed (ComponentFixture)`, `SSR: enabled | disabled`.

### Step 3 - Apply spec-aware mode (conditional)

If `--spec <slug>` passed or `.specs/<slug>/spec.md` exists, Use skill: `spec-aware-preamble`. Generate one test per AC (`// Satisfies: AC<N>`), cover every NFR, refuse out-of-scope. Never edit spec artifacts.

### Step 4 - Read code under test and existing tests

- Target module: component shape, service shape, guard/interceptor shape
- One existing component spec, one service spec, one Playwright spec; setup files (`test-setup.ts` / `src/test.ts`, `playwright.config.ts`)
- `tsconfig.spec.json`, `vitest.config.ts` / `jest.config.js` / `karma.conf.js`
- Setup wiring: `getTestBed().initTestEnvironment(...)`, MSW `setupServer`, harness loader, global `provide*`
- Provider/interceptor/guard/store deps that components need

Greenfield defaults (state explicitly, no silent invention): Vitest + ATL + `userEvent`; `HttpTestingController` at the boundary; MSW with `onUnhandledRequest: 'error'` for E2E only; Playwright for journeys; `vitest-axe`; shared `renderWithProviders`; factories in `test/factories/`.

Use skill: `angular-testing-patterns` for canonical forms.

### Step 5 - Runner migration decision

When legacy Karma exists alongside new test ambitions:

- **Keep Karma, add Vitest for new** when (a) Karma config is healthy, (b) component count > 50, (c) team can run both in CI. Document the boundary (e.g., new tests in `*.spec.ts` under Vitest config, legacy specs stay on Karma).
- **Full migrate to Vitest/Jest** when (a) Karma flakiness is a regular pain, (b) component count < 50, or (c) zoneless adoption is planned (Karma + zoneless is friction).

State the choice explicitly in Strategy Doc output.

### Step 6 - Angular test pyramid

| Layer       | Tooling                                                                    | What belongs here                                                          |
| ----------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Unit        | Runner + plain functions                                                   | Utilities, pipes (no DI), validators, NgRx selectors / reducers            |
| Service     | TestBed + `HttpTestingController` (HTTP); plain instantiation (pure)       | HTTP services, state services, NgRx effects (`provideMockActions`)         |
| Component   | TestBed + ATL or `ComponentFixture` + CDK harnesses (Material)             | Component rendering, interaction, a11y                                     |
| Integration | TestBed + `provideRouter([...])` + `HttpTestingController`                 | Multi-component flows on a route                                           |
| Guard       | `TestBed.runInInjectionContext(() => guardFn(...))`                        | Auth gates, role gates, can-deactivate                                     |
| Interceptor | `provideHttpClient(withInterceptors([...]))` + `HttpTestingController`     | Token attachment, error transformation, retry                              |
| E2E         | Playwright                                                                 | Critical journeys - signup, checkout, payment                              |

**Many** unit + service + component, **some** integration, **few** E2E. One test per guard / interceptor covering happy + denial paths.

### Step 7 - Apply Angular test patterns

Patterns live in `angular-testing-patterns`; workflow-level decisions:

- **HTTP boundary.** `HttpTestingController` (`provideHttpClient()` + `provideHttpClientTesting()`); never `spyOn(service, 'http' as any)`. Verify method/URL/body/headers; `req.flush(...)`; `httpMock.verify()` in `afterEach`.
- **Functional guards.** `TestBed.runInInjectionContext(() => guardFn(route, state))` with stub providers. Happy + denial.
- **Functional interceptors.** `provideHttpClient(withInterceptors([myInterceptor]))` + `provideHttpClientTesting()`; assert via `httpMock.expectOne(...)` request transformation. Happy + denial.
- **Signals.** Read as function calls. Set signal inputs via `fixture.componentRef.setInput('value', 42)`. `effect()` runs during CD - trigger via `fixture.detectChanges()`, assert the side effect.
- **Reactive Forms.** Cover valid + invalid + cross-field + async-validator pending paths; for server-validation, simulate `HttpErrorResponse` 422 and assert `control.errors['server']` is set. See `angular-forms-patterns`.
- **Component test choice.** ATL by default (user-centric, `userEvent`, `render(Component, { inputs, on, providers })`). TestBed + `ComponentFixture` only for fixture-level control (manual CD, harness loader, `setInput` on OnPush).
- **Router stubs.** `provideRouter([...stubRoutes])` over deprecated `RouterTestingModule`.
- **MSW vs `HttpTestingController`.** `HttpTestingController` for component/service tests (faster, contract-aware). MSW only for browser-realistic flows (service worker, CORS) - typically Playwright.
- **NgRx.** Reducers/selectors as pure-function tests, no TestBed. Effects: `provideMockActions(() => actions$)` from `@ngrx/effects/testing`.
- **Third-party auth SDK (Auth0, Okta, Firebase).** Mock the SDK's `AuthService` via `useValue: stubAuth`. For `@auth0/auth0-angular`:

  ```typescript
  const auth0 = {
    isAuthenticated$: of(true),
    user$: of({ sub: "auth0|123", email: "u@x.com" }),
    loginWithRedirect: vi.fn(),
    logout: vi.fn(),
    getAccessTokenSilently: vi.fn(() => of("token")),
  };
  TestBed.configureTestingModule({ providers: [{ provide: AuthService, useValue: auth0 }] });
  ```
- **Error tracker.** `vi.mock('@sentry/angular', () => ({ captureException: vi.fn(), setUser: vi.fn() }))`; assert capture on the error path.
- **A11y.** `axe(fixture.nativeElement)` via `jest-axe` / `vitest-axe` at route-level tests.

### Step 8 - Test boundaries

**Unit:** utilities, pipes without DI, NgRx selectors/reducers, validators (edge cases).

**Service:** every HTTP service (request shape + response); every state service exposing a signal/observable (transitions, derived); NgRx effects.

**Component:** every interactive component (form, modal, dropdown, menu, dialog, tabs); empty / loading / error branches; conditional rendering; a11y (label association, keyboard nav, focus).

**Integration:** filter + list (filter updates list, URL syncs, deep link); multi-step wizards; optimistic-update flows.

**Multi-step wizard.** One integration test walks the full path; focused tests cover each step's validation. Cover:

- Forward: valid step N advances to N+1; submit disabled until validation passes
- **Backward preserves state** (most-broken in practice)
- Cross-step validation: step-3 field depending on step-1 value recomputes after back-edit
- Cancel / reset clears state
- Submit calls endpoint with merged payload

**Guard / Interceptor:** every functional guard/interceptor with happy + denial paths.

**E2E:** auth / onboarding journey, checkout / payment, critical multi-page contracts.

**Does NOT need a test:** framework behavior (`RouterLink`, NgRx internals, Forms primitives); typed inputs with no logic; trivial wrappers covered by parents; visual layout - belongs to visual regression; pure presentation - covered via parent.

### Step 9 - Prioritize when coverage is low

When coverage < ~50%, run before scaffolding:

1. **P1 - Auth, money, HTTP / guards / interceptors:** every HTTP service, every functional guard / interceptor, auth flows, checkout / billing.
2. **P2 - Forms and validation:** every Reactive Form with validators; multi-step wizards.
3. **P3 - Empty / error / loading:** every list / data view with empty + skeleton + error; global `ErrorHandler` routes to Sentry.
4. **P4 - High-churn:** files with frequent commits or fix history.
5. **P5 - Plumbing:** pure presentation, simple wrappers.

**Multi-band rule.** Multi-band targets (checkout = P1 + P2) file under highest band, cover both axes.

### Step 10 - Audit test infrastructure prerequisites

When any is missing, surface as **Test infrastructure prerequisites** subsection - "must land alongside P1":

- [ ] Runner config (`vitest.config.ts` / `jest.config.js` / `karma.conf.js`) with `jsdom`/`happy-dom`, path aliases, `setupFiles`
- [ ] Setup file wires `getTestBed().initTestEnvironment(...)`, harness loader, MSW if used
- [ ] Shared `renderWithProviders` helper or TestBed factory
- [ ] `test/factories/<entity>.ts` for main domain types
- [ ] `playwright.config.ts` when E2E in scope
- [ ] Dev deps: `@angular/cdk/testing`, `@testing-library/angular`, `jest-axe`/`vitest-axe`, `msw`, `@ngrx/effects/testing`
- [ ] CI runs runner + Playwright; coverage tool wired with thresholds
- [ ] Playwright `retries: 2` on CI / `0` locally; `trace: 'on-first-retry'`; isolated `storageState` per project
- [ ] `HttpTestingController.verify()` called in `afterEach` for every HTTP test

## Output Format

**Which output:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / coverage < 50% without scaffold request -> Strategy Doc
- Multiple deliverables -> produce in order separated by `---`: Coverage Assessment, Strategy Doc, Test Scaffolds
- Unclear -> Strategy Doc as default

**Coverage Assessment:**

```markdown
## Angular Test Coverage Assessment

**Stack:** Angular <version>
**Runner:** Vitest | Jest | Karma
**Helper:** @testing-library/angular | TestBed
**SSR:** enabled | disabled

**Coverage gaps:**

- **Unit:** [utilities / pipes / NgRx selectors without coverage]
- **Service:** [HTTP services without `HttpTestingController`; state services without coverage]
- **Component:** [interactive components without tests; missing empty / error / loading]
- **Integration:** [route-level pages with multi-component flows lacking tests]
- **Guard / Interceptor:** [functional guards/interceptors without happy + denial]
- **E2E:** [critical journeys without Playwright]
- **Accessibility:** [routes without `axe`; interactive without keyboard / focus]

**Pyramid balance:** Unit + Service [n] / Component + Integration [n] / Guard + Interceptor [n] / E2E [n]

**Prioritization** _(when coverage < ~50% or > 5 gaps)_

1. P1 - Auth / money / HTTP / guards / interceptors: [list]
2. P2 - Forms / validation / wizards: [list]
3. P3 - Empty / error / loading: [list]
4. P4 - High-churn: [files]
5. P5 - Plumbing: [list]

**Test infrastructure prerequisites** _(when any Step 10 item missing - must land alongside P1)_

- [missing item]
```

**Test Scaffolds:** ready-to-run files following project conventions. Each:

- Right test type
- Factories for data (no raw object literals)
- User-centric queries; `userEvent`, not `fireEvent`
- Component: happy + error + empty + loading + a11y; signal inputs via `setInput`
- Service: `HttpTestingController` + happy + error + `verify()` in `afterEach`
- Guard: `runInInjectionContext` + happy + denial
- Interceptor: `withInterceptors` + `HttpTestingController` + transformation assertion
- NgRx: effects via `provideMockActions`; selectors/reducers pure-function
- E2E: full journey, `storageState` for auth, `page.route` for API stubs
- Strict TS; typed mock factories

**Strategy Doc:**

```markdown
## Angular Test Strategy

**Objective:** [what this strategy achieves]
**Runner choice:** [Vitest greenfield | Karma kept for legacy + Vitest for new | full Karma->Vitest migrate]
**Pyramid balance:** Unit + Service {x}% / Component + Integration {y}% / Guard + Interceptor {z}% / E2E {w}%
**Tooling:** [runner], [helper], `HttpTestingController`, CDK harnesses, Playwright, `vitest-axe`/`jest-axe`, MSW (E2E only), `@ngrx/effects/testing`
**Mocking:** `HttpTestingController` at HTTP boundary; provider stubs (`useValue`) for non-HTTP; third-party auth SDK stubbed (`AuthService` `useValue: stubAuth`); MSW only for browser-realistic E2E
**Signal strategy:** signals as function calls; inputs via `setInput`; effects via `detectChanges`
**Critical journeys to E2E:** [signup / checkout / etc.]
**Gaps to close (prioritized):**

1. [Highest-risk gap]
2. [...]
```

## Self-Check

- [ ] Principles loaded; stack confirmed
- [ ] Spec-aware mode honored when `--spec` passed
- [ ] Code under test, sample tests, setup files read; `angular-testing-patterns` consulted
- [ ] Runner migration decision stated when Karma exists
- [ ] Pyramid mapped to Angular idioms; patterns applied (HTTP boundary, `runInInjectionContext`, harness, `setInput`)
- [ ] Boundaries respected; multi-step wizard covers forward + backward-preserves-state + cross-step + submit
- [ ] Risk bands applied when coverage low; infrastructure prerequisites surfaced if missing
- [ ] Third-party auth SDK stubbing pattern applied when in scope
- [ ] `HttpTestingController.verify()` in `afterEach` enforced; user-centric queries default

## Avoid

- Scaffolding without reading existing tests + setup files
- Chasing coverage % over risk - 100% lines with no `HttpTestingController` on services misses the bigger threat
- E2E for what a component test covers
- Testing implementation details (`fixture.componentInstance.<internal>`, render counts, lifecycle calls)
- `getByTestId` as default - escape hatch, not entry point
- Mounting a full component to test NgRx selector/reducer
- Sharing mutable fixtures across tests
- Asserting CSS class names (`toHaveClass('text-red-500')`) - assert visible behavior or a11y
- `setTimeout` waits for async - use `findBy*` / `waitFor` / `fixture.whenStable()`
