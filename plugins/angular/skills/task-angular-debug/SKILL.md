---
name: task-angular-debug
description: Debug Angular: change detection, signals, RxJS leaks, DI errors, routing, build/TS errors, zone/SSR, test failures.
metadata:
  category: frontend
  tags: [angular, debug, change-detection, signals, rxjs, dependency-injection, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug - Angular Debugging Workflow

## When to Use

- Angular error, warning, or stack trace you need to interpret
- Change detection issue (stale view, `ExpressionChangedAfterItHasBeenChecked`, infinite CD)
- Signal/computed/effect not updating, or updating too often
- RxJS subscription leak, wrong operator, cold-observable double-fire
- DI failure (`NullInjectorError`, `NG0203`, circular dependency)
- Routing error (no route match, guard rejection, lazy load failure)
- Build/TypeScript error or test failure (TestBed, async timing)
- Zone.js / SSR / hydration mismatch
- Wrong behavior with no exception (silent staleness, missing data)

**Not for**: Production incident with containment - use `/task-oncall-start`.

**Edge cases**:

- No error message or vague description: ask for exact console output, file location, and reproduction steps before classifying.
- Multiple errors: focus on the first/root error; mention secondary only if independent.
- Intermittent bug: flag as race-condition or hydration-timing; ask if it reproduces in dev, prod, or both.

## Inputs

| Input                       | Required | Description                       |
| --------------------------- | -------- | --------------------------------- |
| Error message / console log | Yes      | Primary failure signal            |
| Source file                 | No       | Component/service where it fires  |
| Steps to reproduce          | No       | What triggers the error           |
| Expected vs actual          | No       | For silent / wrong-behavior bugs  |
| Angular version             | No       | For version-specific issues       |

## Workflow

**STEP 1 - PRINCIPLES**: `Use skill: behavioral-principles`.

**STEP 2 - STACK**: `Use skill: stack-detect` to confirm Angular version, zoneless vs zone.js, SSR usage, state library (NgRx / signals). Use this to pick framework-specific guidance.

**STEP 3 - INTAKE**: Capture the error text, file, repro steps. If input is ambiguous, ask one clarifying question before proceeding.

**STEP 4 - CLASSIFY**: Match the error to a category and load the relevant atomic skill. Pick the most specific row. If multiple match, classify by the failing layer (signals beats generic CD).

| Category          | Error pattern                                                        | Likely cause                              | Load skill                       |
| ----------------- | -------------------------------------------------------------------- | ----------------------------------------- | -------------------------------- |
| Change detection  | `ExpressionChangedAfterItHasBeenChecked` / NG0100                    | State mutation during CD or in lifecycle  | `angular-component-patterns`     |
| Change detection  | View stale on data change                                            | OnPush + missing reference change / signal write | `angular-signals-patterns` |
| Change detection  | "Change detection cycle exceeded"                                    | Infinite effect/computed/CD loop          | `angular-signals-patterns`       |
| DI                | `NullInjectorError: No provider for X`                               | Missing provider or wrong scope           | `angular-service-patterns`       |
| DI                | `NG0203 inject() must be called in context`                          | `inject()` outside constructor/factory    | `angular-service-patterns`       |
| DI                | Circular / cyclic dependency                                         | Services injecting each other             | `angular-service-patterns`       |
| RxJS              | Growing subscription count / leak                                    | Missing `takeUntilDestroyed` / unsubscribe | `angular-rxjs-patterns`         |
| RxJS              | `ObjectUnsubscribedError`, `EmptyError`                              | Subject reused after complete / empty source | `angular-rxjs-patterns`        |
| RxJS              | Duplicate HTTP / cancelled requests                                  | Wrong flattening op or cold re-subscribe  | `angular-rxjs-patterns`          |
| Routing           | `Cannot match any routes`, NG04002, lazy load fails                  | Bad path, guard returning false, wrong `loadComponent` | `angular-routing-patterns` |
| Build / TS        | `Cannot find module`, type-not-assignable                            | Path alias / signal-input type mismatch   | `angular-signals-patterns` (if signal-typed) |
| Runtime           | `Cannot read properties of undefined`                                | Access before signal/data settles         | `angular-signals-patterns`       |
| Runtime           | `Maximum call stack size exceeded`                                   | Infinite effect/computed cycle            | `angular-signals-patterns`       |
| Test              | "No provider for HttpClient", "is not a known element"               | Missing `provideHttpClient` / import in TestBed | `angular-testing-patterns` |
| Test              | `fixture.detectChanges()` not updating                               | OnPush needs signal write / input change  | `angular-testing-patterns`       |
| Performance       | Slow render, bundle bloat, leak                                      | Hot path / change-detection scope         | `frontend-performance`           |

**No-error / wrong-behavior intake**: when there is no stack trace, work the seams where data crosses change detection, an injection context, or SSR hydration. Common Angular surfaces:

| Surface                                       | Symptom                                          | Fix direction                                                                  |
| --------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| OnPush + in-place mutation                    | Child never re-renders after `items.push(x)`     | Replace mutation: `items = [...items, x]` or `signal.update(s => [...s, x])`  |
| Pure pipe stale                               | `arr ` + pipe never re-runs after mutation       | Pure pipes track input reference; replace, do not mutate                       |
| Signal nested mutation                        | `state().nested.field = x` does not re-render    | `state.update(s => ({ ...s, nested: { ...s.nested, field: x } }))`             |
| Cold HTTP re-subscribed                       | Duplicate requests via `async` pipe + manual sub | `shareReplay({ bufferSize: 1, refCount: true })` or sink into one signal       |
| `@ViewChild` undefined in `ngOnInit`          | Populated after view init                        | Move to `ngAfterViewInit` or use reactive `viewChild()` (v17+)                 |
| `inject()` in callback                        | `NG0203` or wrong instance                       | Run in constructor/factory, or capture `EnvironmentInjector.runInContext(...)` |
| `takeUntilDestroyed` outside injection ctx    | Subscription leaks                               | Use at field init, or pass captured `DestroyRef`                               |
| Guard reads async signal too early            | Wrong route / false negative                     | Resolver, or return `firstValueFrom(state$.pipe(filter(Boolean)))`             |
| NgRx selector returns fresh literal           | Re-renders on every action                       | Return primitive/stable ref, or downstream `distinctUntilChanged`              |
| SSR `localStorage` / `window` access          | Null on server, flicker on client                | Guard `isPlatformBrowser`, use `afterNextRender`, or `TransferState`           |
| HTTP transfer cache miss                      | Client re-fetches SSR-fetched URL                | Align headers/URL; configure `withHttpTransferCacheOptions` deliberately       |
| Signal input read in constructor              | Value is `undefined` early                       | Read in `computed` / `effect`, set default, or use `input.required`            |

**STEP 5 - LOCATE**: Open the failing file plus ~50 lines of context. Trace route -> parent -> failing component -> service. Name the layer: Component | Service | State | Routing | RxJS | Build | Test.

**STEP 6 - ROOT CAUSE**: Explain WHY the error fires, citing the specific line. If it is a pattern violation, name the pattern. Rate confidence:

- HIGH: error and code point to one cause unambiguously
- MEDIUM: cause is likely but alternatives exist
- LOW: need more input - state what (file, repro, version)

**STEP 7 - FIX**: Show before/after for the exact change. If alternatives exist, rank by (1) correctness, (2) minimal surface, (3) alignment with project patterns; note the tradeoff.

**STEP 8 - PREVENT**: Suggest a test that would have caught this (TestBed, `HttpTestingController`, SSR component test). If the pattern likely repeats, grep for similar usage and list occurrences.

## Output Format

**Bug Analysis** - category, confidence {HIGH | MEDIUM | LOW}, layer {Component | Service | State | Routing | RxJS | Build | Test}

**Root Cause** - why this fires, with file:line reference

**Fix** - before/after diff with one-line explanation

**Prevention** (omit if fix is trivial) - test to add, atomic skill reference, other occurrences

**Needs Clarification** (only if confidence is LOW) - exact info required to confirm

### Output Constraints

- One bug, one fix. No unrelated style or refactor suggestions.
- Omit Prevention if the fix is trivial (typo, missing import).
- No `any`, `setTimeout`, or disabled strict mode as a fix.

## Self-Check

- [ ] STEP 1: Loaded `behavioral-principles`
- [ ] STEP 2: Loaded `stack-detect`; Angular version, zone mode, SSR, state library known
- [ ] STEP 3: Error text and context captured; clarification asked if ambiguous
- [ ] STEP 4: Classified to a category; relevant atomic skill loaded
- [ ] STEP 5: Source file opened; layer named
- [ ] STEP 6: Root cause explains WHY with code reference; confidence rated
- [ ] STEP 7: Before/after fix is minimal and addresses root cause
- [ ] STEP 8: Test suggested; repeat occurrences identified if pattern is widespread

## Avoid

- Generic advice ("add console.log", "clear cache", "restart dev server")
- Fixing symptoms (wrapping in `setTimeout`, disabling OnPush) instead of root cause
- Refactoring beyond the bug
- Proposing a fix without reading the failing code
- Mixing incident-response (containment, blast radius) into developer debugging
