---
name: task-angular-debug
description: Debug Angular - change detection, signals, RxJS leaks, DI errors, routing, build/TS errors, zone/SSR, test failures.
agent: angular-engineer
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

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Confirm Angular version, zoneless vs zone.js, SSR usage, state library.

### Step 3 - Intake

Capture error text, file, repro steps. If ambiguous, ask one clarifying question before proceeding.

### Step 4 - Classify

Match the symptom to a row and load the relevant atomic skill.

**Routing rule for no-exception bugs:** When the symptom is "wrong value, no exception" (stale view, missing data, wrong route), use the No-error / wrong-behavior table. When an exception or framework warning fires, use the Errored category table. If both apply, prefer the No-error row - it isolates the silent failure mode.

### Errored category table

Match on the user-pasted message *first*; the `NG####` codes are listed but secondary. **Test errors take precedence over any other category** - if the stack trace contains a test runner path (`.spec.ts`, `karma`, `vitest`, `jest`), route to `angular-testing-patterns` even when the underlying error pattern matches another row.

| Category          | Error pattern                                                        | Likely cause                                          | Load skill                       |
| ----------------- | -------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------- |
| Test              | Any error originating from a `.spec.ts` / runner stack trace         | Missing `provideHttpClient` / standalone import / `setInput` / `detectChanges` | `angular-testing-patterns` |
| Change detection  | "Expression has changed after it was checked" (NG0100)               | State mutation during CD or in lifecycle              | `angular-component-patterns`     |
| Change detection  | "Change detection cycle exceeded", "Maximum call stack" in CD path   | Infinite effect/computed/CD loop                      | `angular-signals-patterns`       |
| DI                | "NullInjectorError: No provider for X"                               | Missing provider or wrong scope                       | `angular-service-patterns`       |
| DI                | "NG0203", "inject() must be called from an injection context"        | `inject()` outside constructor/factory                | `angular-service-patterns`       |
| DI                | "Circular dependency in DI detected"                                 | Services injecting each other                         | `angular-service-patterns`       |
| RxJS              | Growing subscription count, memory growth on nav                     | Missing `takeUntilDestroyed`                          | `angular-rxjs-patterns`          |
| RxJS              | `ObjectUnsubscribedError`, `EmptyError`, duplicate HTTP              | Subject misuse / cold re-subscribe / wrong flattening | `angular-rxjs-patterns`          |
| Routing           | "Cannot match any routes" (NG04002), lazy load fails                 | Bad path, guard returning false, wrong `loadComponent` | `angular-routing-patterns`      |
| SSR / Hydration   | NG0500-series "hydration node mismatch"                              | Browser-only API in render path; DOM diff drift       | `angular-routing-patterns` (SSR section) |
| Build / TS        | TS "Cannot find module" / "Type X is not assignable to Y"            | Path alias misconfigured / signal-input typing        | `angular-component-patterns` (or `angular-signals-patterns` if signal-typed) |

### No-error / wrong-behavior table

| Surface                                       | Symptom                                          | Fix direction                                                                  | Load skill                       |
| --------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ | -------------------------------- |
| OnPush + in-place mutation                    | Child never re-renders after `items.push(x)`     | Replace mutation: `items = [...items, x]` or `signal.update(s => [...s, x])`  | `angular-signals-patterns`       |
| Signal nested mutation                        | `state().nested.field = x` does not re-render    | `state.update(s => ({ ...s, nested: { ...s.nested, field: x } }))`             | `angular-signals-patterns`       |
| Pure pipe stale                               | Pipe never re-runs after array mutation          | Pure pipes track input reference; replace, do not mutate                       | `angular-component-patterns`     |
| Cold HTTP re-subscribed                       | Duplicate requests via `async` pipe + manual sub | `shareReplay({ bufferSize: 1, refCount: true })` or sink into one signal       | `angular-rxjs-patterns`          |
| `@ViewChild` undefined in `ngOnInit`          | Populated after view init                        | Move to `ngAfterViewInit` or use reactive `viewChild()` (17.2+)                | `angular-component-patterns`     |
| `inject()` in callback                        | `NG0203` or wrong instance                       | Run in constructor/factory, or `EnvironmentInjector.runInContext(...)`         | `angular-service-patterns`       |
| `takeUntilDestroyed` outside injection ctx    | Subscription leaks                               | Use at field init, or pass captured `DestroyRef`                               | `angular-rxjs-patterns`          |
| Guard reads async signal too early            | Wrong route / false negative                     | Resolver, or return `firstValueFrom(state$.pipe(filter(Boolean)))`             | `angular-routing-patterns`       |
| NgRx selector returns fresh literal           | Re-renders on every action                       | Return primitive/stable ref, or downstream `distinctUntilChanged`              | `angular-state-patterns`         |
| SSR `localStorage` / `window` access          | Null on server, flicker on client                | Guard `isPlatformBrowser`, use `afterNextRender`, or `TransferState`           | `angular-routing-patterns` (SSR) |
| HTTP transfer cache miss                      | Client re-fetches SSR-fetched URL                | Align headers/URL; configure `withHttpTransferCacheOptions` deliberately       | `angular-data-fetching`          |
| Signal input read in constructor              | Value is `undefined` early                       | Read in `computed` / `effect`, set default, or use `input.required`            | `angular-signals-patterns`       |
| `toSignal` returns undefined                  | Type widened, template breaks                    | Add `initialValue` or `requireSync: true`                                      | `angular-rxjs-patterns`          |

### Step 5 - Locate

Open the failing file plus ~50 lines of context. Trace route -> parent -> failing component -> service. Name the layer: Component | Service | State | Routing | RxJS | Build | Test.

### Step 6 - Root Cause

Explain WHY the error fires, citing the specific line. Rate confidence:

- HIGH: error and code point to one cause unambiguously
- MEDIUM: cause is likely but alternatives exist
- LOW: need more input - state what (file, repro, version)

### Step 7 - Fix

Show before/after for the exact change. If alternatives exist, rank by (1) correctness, (2) minimal surface, (3) project pattern alignment.

### Step 8 - Prevent

Suggest a test that would have caught this. If the pattern likely repeats, grep for similar usage (e.g., `\(\)\.[a-z]+\s*=` for nested signal mutation).

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
