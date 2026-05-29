---
name: task-angular-debug
description: Debug Angular - change detection, signals, RxJS leaks, DI errors, routing, build/TS errors, zone/SSR, test failures.
metadata:
  category: frontend
  tags: [angular, debug, change-detection, signals, rxjs, dependency-injection, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug - Angular Debugging Workflow

## When to Use

- Angular error, warning, or stack trace you need to interpret
- Change detection issue (`ExpressionChangedAfterItHasBeenChecked`, stale view, infinite CD)
- Signal/computed/effect not updating, or updating too often
- RxJS subscription leak, wrong operator, cold-observable double-fire
- DI failure (`NullInjectorError`, `NG0203`, circular dependency)
- Routing error (no route match, guard rejection, lazy load failure)
- Build/TypeScript error or test failure
- Zone.js / SSR / hydration mismatch
- Wrong behavior with no exception (silent staleness, missing data)

**Not for:** production incident with containment - use `/task-oncall-start`.

## Inputs

| Input                       | Required | Description                       |
| --------------------------- | -------- | --------------------------------- |
| Error message / console log | Yes      | Primary failure signal            |
| Source file                 | No       | Component/service where it fires  |
| Steps to reproduce          | No       | What triggers the error           |
| Expected vs actual          | No       | For silent / wrong-behavior bugs  |
| Angular version             | No       | For version-specific issues       |

## Workflow

**STEP 1 - PRINCIPLES:** `Use skill: behavioral-principles`.

**STEP 2 - STACK:** `Use skill: stack-detect` to confirm Angular version, zoneless vs zone.js, SSR usage, state library.

**STEP 3 - INTAKE:** Capture error text, file, repro steps. If ambiguous, ask one clarifying question before proceeding.

**STEP 4 - CLASSIFY:** Match the symptom to a row and load the relevant atomic skill.

**Routing rule for no-exception bugs:** When the symptom is "wrong value, no exception" (stale view, missing data, wrong route), use the No-error / wrong-behavior table. When an exception or framework warning fires, use the Errored category table. If both apply, prefer the No-error row - it isolates the silent failure mode.

### Errored category table

| Category          | Error pattern                                                        | Likely cause                              | Load skill                       |
| ----------------- | -------------------------------------------------------------------- | ----------------------------------------- | -------------------------------- |
| Change detection  | `ExpressionChangedAfterItHasBeenChecked` / NG0100                    | State mutation during CD or in lifecycle  | `angular-component-patterns`     |
| Change detection  | "Change detection cycle exceeded"                                    | Infinite effect/computed/CD loop          | `angular-signals-patterns`       |
| DI                | `NullInjectorError: No provider for X`                               | Missing provider or wrong scope           | `angular-service-patterns`       |
| DI                | `NG0203 inject() must be called in context`                          | `inject()` outside constructor/factory    | `angular-service-patterns`       |
| DI                | Circular / cyclic dependency                                         | Services injecting each other             | `angular-service-patterns`       |
| RxJS              | Growing subscription count / leak                                    | Missing `takeUntilDestroyed`              | `angular-rxjs-patterns`          |
| RxJS              | `ObjectUnsubscribedError`, `EmptyError`                              | Subject reused after complete / empty     | `angular-rxjs-patterns`          |
| RxJS              | Duplicate HTTP / cancelled requests                                  | Wrong flattening op or cold re-subscribe  | `angular-rxjs-patterns`          |
| Routing           | `Cannot match any routes`, NG04002, lazy load fails                  | Bad path, guard returning false, wrong `loadComponent` | `angular-routing-patterns` |
| Build / TS        | `Cannot find module`, type-not-assignable                            | Path alias / signal-input type mismatch   | `angular-signals-patterns` (signal-typed) |
| Runtime           | `Maximum call stack size exceeded`                                   | Infinite effect/computed cycle            | `angular-signals-patterns`       |
| Test              | "No provider for HttpClient", "is not a known element"               | Missing `provideHttpClient` / import      | `angular-testing-patterns`       |
| Test              | `fixture.detectChanges()` not updating                               | OnPush needs signal write / input change  | `angular-testing-patterns`       |
| Performance       | Slow render, bundle bloat                                            | Hot path / change-detection scope         | `task-angular-review-perf`       |

### No-error / wrong-behavior table

| Surface                                       | Symptom                                          | Fix direction                                                                  |
| --------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| OnPush + in-place mutation                    | Child never re-renders after `items.push(x)`     | Replace mutation: `items = [...items, x]` or `signal.update(s => [...s, x])`  |
| Signal nested mutation                        | `state().nested.field = x` does not re-render    | `state.update(s => ({ ...s, nested: { ...s.nested, field: x } }))`             |
| Pure pipe stale                               | Pipe never re-runs after array mutation          | Pure pipes track input reference; replace, do not mutate                       |
| Cold HTTP re-subscribed                       | Duplicate requests via `async` pipe + manual sub | `shareReplay({ bufferSize: 1, refCount: true })` or sink into one signal       |
| `@ViewChild` undefined in `ngOnInit`          | Populated after view init                        | Move to `ngAfterViewInit` or use reactive `viewChild()` (17+)                  |
| `inject()` in callback                        | `NG0203` or wrong instance                       | Run in constructor/factory, or `EnvironmentInjector.runInContext(...)`         |
| `takeUntilDestroyed` outside injection ctx    | Subscription leaks                               | Use at field init, or pass captured `DestroyRef`                               |
| Guard reads async signal too early            | Wrong route / false negative                     | Resolver, or return `firstValueFrom(state$.pipe(filter(Boolean)))`             |
| NgRx selector returns fresh literal           | Re-renders on every action                       | Return primitive/stable ref, or downstream `distinctUntilChanged`              |
| SSR `localStorage` / `window` access          | Null on server, flicker on client                | Guard `isPlatformBrowser`, use `afterNextRender`, or `TransferState`           |
| HTTP transfer cache miss                      | Client re-fetches SSR-fetched URL                | Align headers/URL; configure `withHttpTransferCacheOptions` deliberately       |
| Signal input read in constructor              | Value is `undefined` early                       | Read in `computed` / `effect`, set default, or use `input.required`            |
| `toSignal` returns undefined                  | Type widened, template breaks                    | Add `initialValue` or `requireSync: true`                                      |

**STEP 5 - LOCATE:** Open the failing file plus ~50 lines of context. Trace route -> parent -> failing component -> service. Name the layer: Component | Service | State | Routing | RxJS | Build | Test.

**STEP 6 - ROOT CAUSE:** Explain WHY the error fires, citing the specific line. Rate confidence:

- HIGH: error and code point to one cause unambiguously
- MEDIUM: cause is likely but alternatives exist
- LOW: need more input - state what (file, repro, version)

**STEP 7 - FIX:** Show before/after for the exact change. If alternatives exist, rank by (1) correctness, (2) minimal surface, (3) project pattern alignment.

**STEP 8 - PREVENT:** Suggest a test that would have caught this. If the pattern likely repeats, grep for similar usage (e.g., `\(\)\.[a-z]+\s*=` for nested signal mutation).

## Output Format

**Bug Analysis** - category, confidence {HIGH | MEDIUM | LOW}, layer {Component | Service | State | Routing | RxJS | Build | Test}

**Root Cause** - why this fires, with `file:line` reference

**Fix** - before/after diff with one-line explanation

**Prevention** (omit if fix is trivial) - test to add, atomic skill reference, other occurrences

**Needs Clarification** (only if confidence is LOW) - exact info required to confirm

### Output Constraints

- One bug, one fix. No unrelated style or refactor suggestions.
- No `any`, `setTimeout`, or disabled strict mode as a fix.

## Self-Check

- [ ] Loaded principles + stack-detect; Angular version, zone mode, SSR known
- [ ] Error captured; clarification asked if ambiguous
- [ ] Routing rule applied (no-exception -> No-error table; otherwise Errored table); atomic skill loaded
- [ ] Source file opened; layer named
- [ ] Root cause explains WHY with `file:line`; confidence rated
- [ ] Before/after fix is minimal and addresses root cause
- [ ] Test suggested; repeat occurrences identified if pattern is widespread

## Avoid

- Generic advice ("add console.log", "clear cache", "restart dev server")
- Symptom fixes (`setTimeout` wraps, disabling OnPush) instead of root cause
- Suggesting `.mutate()` (removed in Angular 17+) or `markForCheck()` as a substitute for an immutable signal update
- Refactoring beyond the bug
- Proposing a fix without reading the failing code
- Mixing incident-response (containment, blast radius) into developer debugging
