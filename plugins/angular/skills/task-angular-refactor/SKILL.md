---
name: task-angular-refactor
description: Angular refactor plan - god components, RxJS leaks, BehaviorSubject->signal, OnPush migration, fat services; phased commit-sized steps.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# Angular Refactor

Produce a safe, step-by-step refactoring plan for a specific Angular target (component, service, guard, interceptor, route config, store). Identifies Angular-specific smells and proposes independently-committable steps with `ng build` + test-suite gates between each.

Stack-specific delegate of `task-code-refactor` for Angular.

## When to Use

- Angular code-smell identification and resolution
- Safe refactoring of a component / service / guard / interceptor / route configuration
- Pre-merge "this PR grew the god-component / subscription-leak problem - what's the cleanup?"
- Migrating BehaviorSubject to signals, NgModule to standalone, Default CD to OnPush, class-based to functional guards/interceptors

**Not for:** debt prioritization (`task-debt-prioritize`), feature changes (`task-angular-implement`), architecture restructuring (`task-design-architecture`), bug fixes (`task-angular-debug`).

## Inputs

| Input                 | Required    | Description                                                                 |
| --------------------- | ----------- | --------------------------------------------------------------------------- |
| Target scope          | Yes         | File or module to refactor                                                  |
| Goal                  | Yes         | What this refactor achieves                                                 |
| Test coverage status  | Recommended | Existing coverage for the target area                                       |
| Shared/public surface | Recommended | Whether target is used across feature / route / app boundaries              |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Angular, stop and recommend `/task-code-refactor`. Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled`.

### Step 3 - Read the Target

Refactor plans grounded in prose hallucinate smells that aren't there.

**Single-target mode (default).** A specific file or component is named.

1. Read the target file top-to-bottom; note line count, CD mode, signal vs RxJS state, input/output declarations, subscriptions, lifecycle hooks, external collaborators.
2. Read matching test file(s); count cases by outcome (happy, error, empty, validation, auth, a11y).
3. For widely-used services or shared components, read at least one caller.

**Sweep mode.** Goal is "convert all X to Y" (every class-based guard → functional, every `BehaviorSubject` in `libs/data-access` → signal). Inventory targets via grep before planning: list every file matched, group by shape (small / medium / mixed), and emit a multi-PR plan where each PR is one shape group. Coverage Gate runs per group, not per file.

If the user named only a goal without a target or a sweep scope, ask which before proceeding.

**Sibling-smell disposition.** If the target file contains smells outside the named goal (e.g., `bypassSecurityTrustHtml` co-located), list under `Sibling Smells (Out of Scope)` with a one-phrase deferral and follow-up skill - do not action.

### Step 4 - Coverage Gate

"Public entry point" = a component's user-driven interaction (click, type, submit, key), a service's exported method, a guard/interceptor/resolver function, or an exported pipe. Private helpers don't count.

| Status       | Definition                                                                                  | Action                                                              |
| ------------ | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `Adequate`   | Happy path + ≥2 boundary outcomes (error, empty, validation, auth) per public entry point   | Proceed                                                             |
| `Thin`       | Happy path + exactly 1 boundary outcome per public entry point                              | Proceed; plan includes mandatory `Step 0 - Coverage prerequisite`   |
| `Inadequate` | No tests, or happy-path-only across the public surface                                      | **Refuse later steps.** Output Coverage Gate verdict and recommend `task-angular-test`. Smell catalog (Step 5) still runs as preview. |

**Internal-coupled tests count negatively.** Tests asserting `fixture.componentInstance.<internal>` or stream names the refactor will rename are surfaced as `internal-coupled: <test:line>` and require DOM/event rewrite in `Step 0` before that refactor step runs.

### Step 5 - Identify Angular Smells

Use judgment - these are signals, not hard rules.

**Component / template:**

| Smell                                | Risk   |
| ------------------------------------ | ------ |
| God Component (>300 lines, mixed concerns) | High |
| Default Change Detection on new code | High   |
| Inline business logic in template (deep ternaries) | Medium |
| Untyped Inputs (`@Input() x` or `input<any>()`) | High |
| `@for` `track $index` on dynamic list | High   |
| `*ngIf`/`*ngFor` in new code         | Medium |
| `[innerHTML]` without sanitizer      | High   |

**State / signal / RxJS:**

| Smell                                | Risk   |
| ------------------------------------ | ------ |
| `BehaviorSubject` for component-local state | Medium |
| Bare `.subscribe()` without cleanup  | High   |
| `effect()` for derived state (should be `computed`) | High |
| `effect()` for event handler         | High   |
| Manual `markForCheck`/`detectChanges` to bypass OnPush | Medium |
| Mixed signal / `BehaviorSubject` in one component | Medium |

**Service / DI / routing:**

| Smell                                | Risk   |
| ------------------------------------ | ------ |
| Fat Service (8+ methods, unrelated concerns) | High |
| `providedIn: 'root'` for per-user state without reset | High |
| Direct `HttpClient` in component     | High   |
| Class-based guard/resolver/interceptor in new code | Medium |
| Eager `component:` for non-trivial route | Medium |
| `CanActivate` guarding lazy route (use `CanMatch`) | Medium |
| NgModule for new code                | Medium |

For accessibility, security, and SSR-specific smells, defer to `task-angular-review-security` / `task-angular-review-perf` and surface as sibling smells.

Use skill: `complexity-review` when the target shows over-engineering signals (single-impl generic, content-projection abstraction for one consumer).

### Step 6 - Cross-Module Risk

Use skill: `review-blast-radius`. Angular-specific signals:

- Public design-system component in shared lib
- Top-level `app.component` / root layout / `app.config.ts`
- Service injected by 10+ components
- HTTP interceptor (affects every HTTP call)
- Auth guard (affects every protected route)
- Cross-feature NgRx store

State blast radius before proposing steps: **Narrow** | **Moderate** | **Wide** | **Critical**.

### Step 7 - Propose the Step Sequence

Each step must be (1) independently committable, (2) behaviorally invariant unless labeled `coupled-fix`, (3) reversible in one revert, (4) tested.

**Recipe interleaving.** Pick one primary recipe as the spine; fold supporting recipes as sub-steps where dependencies require. If the spine grows past ~8 steps, split into two PRs. Worked example: when splitting a god component is the spine and a `@for track $index` fix is needed, insert the track fix inside the list-extract sub-step rather than running it as a separate top-level step.

**Coupled-fix.** When a refactor structurally depends on a behavior change (e.g., extracting an HTTP method that adds an auth-context lookup), label the step `coupled-fix` with its own test gate.

### Common Angular refactor recipes

**Split god component**

1. Identify orthogonal concerns (filters, list, summary, actions).
2. Extract one concern at a time into a standalone component with explicit `input<T>()` / `output<T>()`; god component renders it.
3. Update tests if the new component has its own surface.
4. Repeat until the god component is a thin layout coordinator.
5. Verify route-level / Playwright E2E still pass.

**Migrate `BehaviorSubject` to `signal()`**

1. Replace `private state$ = new BehaviorSubject(v)` with `state = signal(v)`; mutators (`state$.next(v)`) become `state.set(v)`.
2. Update template: `{{ state$ | async }}` -> `{{ state() }}`.
3. Update external consumers: `toObservable(state)` to keep RxJS interop, or migrate them too.
4. Run tests; assert behavior unchanged.

**Add `takeUntilDestroyed()`**

1. Bare `.subscribe()` in field init / constructor: `obs$.pipe(takeUntilDestroyed()).subscribe(...)`.
2. Outside injection context: `private destroyRef = inject(DestroyRef)` then `takeUntilDestroyed(this.destroyRef)`.
3. Cleaner alternative: `async` pipe in template or `toSignal(obs$, { initialValue })`.

**Default CD -> OnPush**

1. Audit for imperative state mutation (`this.x = x + 1` and template re-renders). Migrate to signals first if found.
2. Add `changeDetection: ChangeDetectionStrategy.OnPush`.
3. Run tests; audit any `cdr.markForCheck()` / `cdr.detectChanges()` calls - they indicate a missed signal.

**`@for track $index` -> `track item.id`**

1. Verify `item` has a stable id; if not, add one via `crypto.randomUUID()` at fetch time (coupled-fix).
2. Replace; run tests for reorder/filter/remove preservation.

**Class-based guard → functional**

1. Convert: `export const authGuard: CanActivateFn = (route, state) => { const router = inject(Router); ... }`.
2. Update route config; remove the class registration from providers.
3. Rewrite tests using `TestBed.runInInjectionContext(() => authGuard(routeStub, stateStub))`.

**Class-based interceptor → functional**

1. Convert: `export const authInterceptor: HttpInterceptorFn = (req, next) => { ... return next(req); }`.
2. Replace `provideHttpClient(withInterceptorsFromDi(), HTTP_INTERCEPTORS provider)` with `provideHttpClient(withInterceptors([authInterceptor]))`.
3. Rewrite tests using `provideHttpClient(withInterceptors([authInterceptor]))` + `HttpTestingController` to assert the transformed request.

**NgModule component -> standalone**

1. Set `standalone: true` (implicit on 19+); move imports from module to component `imports`.
2. Remove from module `declarations`; update consumers to import the component directly.
3. If the module had no other declarations, delete it.

**Extract service from fat component**

1. Identify cohesive state + logic + HTTP trio inside the component.
2. Create `XxxService` with the same shape; copy logic; write a service test (`HttpTestingController`).
3. Replace inlined logic with `private svc = inject(XxxService)`; verify component tests still pass.

**Change-detection-boundary watch.** When converting `BehaviorSubject` + `async` to `signal()`, OnPush consumers dirty-check differently. Audit consumers reading the value across CD boundaries.

**Subscription-boundary watch.** When introducing `takeUntilDestroyed()`, ensure the call site is in an injection context.

### Step 8 - Validate Plan Against Goal

- [ ] Goal achieved at the end of the sequence
- [ ] Each step ≤30 min to review
- [ ] Test coverage runs between every step
- [ ] Low-risk steps before high-risk (extracts/additions before deletions/conversions)
- [ ] Rollback path is one revert per step
- [ ] No bundled unrelated cleanup

## Output Format

```markdown
## Angular Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Angular refactor recipes"]
**Stack:** Angular <version> / <CD mode> / SSR: <enabled|disabled>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[Adequate: one sentence on boundary cases that exist.]
[Thin: list missing boundary tests; Step 0 covers them.]
[Inadequate: state what coverage must exist; recommend `task-angular-test`. **Stop here** - omit Blast Radius, Step Sequence, Verification. Step 5 catalog still produces Smells Identified + Sibling Smells as preview.]

## Smells Identified

_Only smells this plan addresses. Others go under `Sibling Smells (Out of Scope)`. A 12-row table on a single-recipe plan is a bundling smell - re-scope or split._

| Smell | Location | Risk | Notes |
| ----- | -------- | ---- | ----- |
| [name] | file:line | High | [one sentence] |

## Sibling Smells (Out of Scope)

_Omit if none._

| Smell | Location | Why deferred | Recommended follow-up |
| ----- | -------- | ------------ | --------------------- |
| [name] | file:line | [separate target / belongs to security review] | [`task-angular-review-security` / etc.] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [rationale citing callers/tests/public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add missing boundary tests
- **Test gate:** new tests pass; existing suite green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added/extracted/moved]
- **Risk:** Low | Medium | High
- **Step kind:** refactor | coupled-fix
- **Test gate:** [which tests must pass after this step]
- **Rollback:** [one git revert]

_Include `CD stance` and `Subscription stance` only for steps that touch them._

### Step 2 - ...

[Continue numbering. `coupled-fix` for steps where refactor structurally depends on a behavior change.]

## Verification

- [ ] Goal achieved
- [ ] `ng build` clean and tests pass between every step
- [ ] No silent CD-mode or subscription-management changes

## Out of Scope

[Adjacent improvements explicitly NOT in this plan.]
```

## Self-Check

- [ ] Steps 1-2: principles loaded; stack confirmed; CD mode and SSR recorded
- [ ] Step 3: target + tests read directly; sweep vs single-target routed; sibling smells captured
- [ ] Step 4: coverage gate evaluated (Adequate / Thin / Inadequate); happy-path-only = Inadequate; internal-coupled tests pinned to Step 0; preview catalog runs if Inadequate
- [ ] Step 5: smells classified using the catalog (component, state/RxJS, service/DI/routing)
- [ ] Step 6: blast radius stated (Narrow / Moderate / Wide / Critical)
- [ ] Step 7: primary recipe named; plan <=~8 steps or split; Step 0 included if Thin; CD/subscription stance stated only when steps touch them; steps ordered low-risk first; no bundled unrelated cleanup
- [ ] Step 8: goal explicitly maps to end state

## Avoid

- Producing a refactor plan without a coverage gate
- Bundling behavior changes or "while we're here" cleanups
- Renaming during a refactor (separate PR)
- Removing `.subscribe()` without verifying behavior preserved
- Migrating `BehaviorSubject` to `signal` without auditing external subscribers (may need `toObservable`)
- Migrating Default CD to OnPush without auditing imperative `this.x = ...` mutations
- `track $index` -> `track item.id` without verifying every item has a stable id
- Defaulting to NgRx for input drilling - service is often correct
- Refactoring a design-system component without a back-compat plan
