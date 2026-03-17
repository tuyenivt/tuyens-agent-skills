---
name: task-angular-debug
description: Debug Angular errors - change detection issues, RxJS subscription leaks, DI errors, build failures, zone.js issues, and runtime errors for Angular 21+ projects.
metadata:
  category: frontend
  tags: [angular, debug, change-detection, rxjs, dependency-injection, error, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug - Angular Debugging Workflow

## When to Use

- Angular error or warning you need help understanding
- Change detection issues (component not updating, ExpressionChangedAfterItHasBeenChecked)
- RxJS subscription leak or operator error
- Dependency injection error (NullInjectorError, circular dependency)
- Build or TypeScript compilation error
- Zone.js or SSR-related issue
- Test failure you can't figure out
- Behavior that doesn't match expectations (no error, but wrong result)

**Not for**: Production incident response with containment and blast radius assessment - use `task-incident-root-cause` instead.

**Approach**: Classify before fixing. Understand the error, trace through the codebase, explain why (not just what), and apply the smallest correct change aligned with project patterns.

**Edge cases**:

- **Vague description, no error message**: Ask for the exact console output, the component where it occurs, and steps to reproduce before classifying.
- **Multiple errors**: Identify the root error (usually the first in the console) and focus on that. Mention secondary errors only if they are independent.
- **No source code available**: If the error points to framework internals only, explain the framework behavior and ask the user for the application code that triggered it.
- **Intermittent/non-deterministic bug**: Note that the issue may be race-condition or timing-related; ask for reproduction steps and whether it occurs in development, production, or both.

## Inputs

| Input                           | Required | Description                             |
| ------------------------------- | -------- | --------------------------------------- |
| Error message or console output | Yes      | The primary failure signal              |
| Relevant source file            | No       | Component or service where error occurs |
| Steps to reproduce              | No       | What triggers the error                 |
| Expected vs actual behavior     | No       | For logic bugs without exceptions       |
| Angular version                 | No       | For version-specific issues             |

## Rules

- Always classify the error before reading code
- Show the exact code change needed - no vague suggestions
- Explain WHY the error happened, not just how to fix it
- Prefer minimal fixes over refactors - fix the bug, don't redesign
- If confidence is LOW, say so and state what additional info would help
- Do not suggest unrelated improvements or style changes
- Reference atomic skills only when the fix involves a pattern they cover

## Workflow

STEP 1 - INTAKE: Accept one or more of: Angular error message, build error, browser console output, TypeScript compilation error, test failure output, or description of unexpected behavior. If the input is ambiguous, ask one clarifying question before proceeding.

STEP 2 - CLASSIFY: Identify the error category to guide investigation:

**Change detection error** -> Component not updating or expression changed after check:

| Error Pattern                            | Likely Cause                            | Load Skill                              |
| ---------------------------------------- | --------------------------------------- | --------------------------------------- |
| "ExpressionChangedAfterItHasBeenChecked" | Modifying state during change detection | Use skill: `angular-component-patterns` |
| Component not updating on data change    | Missing OnPush trigger or signal update | Use skill: `angular-signals-patterns`   |
| "Change detection cycle exceeded"        | Infinite change detection loop          | Use skill: `angular-component-patterns` |

**DI error** -> Dependency injection failure:

| Error Pattern                          | Likely Cause                        | Load Skill                            |
| -------------------------------------- | ----------------------------------- | ------------------------------------- |
| "NullInjectorError: No provider for X" | Missing provider or incorrect scope | Use skill: `angular-service-patterns` |
| "Circular dependency detected"         | Services depending on each other    | Use skill: `angular-service-patterns` |
| "Cannot instantiate cyclic dependency" | Constructor injection cycle         | Use skill: `angular-service-patterns` |

**RxJS error** -> Observable/subscription issue:

| Error Pattern                             | Likely Cause                              | Load Skill                         |
| ----------------------------------------- | ----------------------------------------- | ---------------------------------- |
| Memory leak / growing subscription count  | Missing unsubscribe or takeUntilDestroyed | Use skill: `angular-rxjs-patterns` |
| "ObjectUnsubscribedError"                 | Using subject after unsubscribe           | Use skill: `angular-rxjs-patterns` |
| "EmptyError" or unexpected empty emission | Observable completing before emitting     | Use skill: `angular-rxjs-patterns` |
| switchMap cancelling requests             | Wrong flattening operator                 | Use skill: `angular-rxjs-patterns` |

**Routing error** -> Navigation or route configuration:

| Error Pattern                      | Likely Cause                           | Load Skill                            |
| ---------------------------------- | -------------------------------------- | ------------------------------------- |
| "Cannot match any routes"          | Missing route definition or wrong path | Use skill: `angular-routing-patterns` |
| "Error: NG04002" (guard rejection) | Route guard returning false/UrlTree    | Use skill: `angular-routing-patterns` |
| Lazy loaded module not loading     | Wrong loadComponent/loadChildren path  | Use skill: `angular-routing-patterns` |

**Build / TypeScript error** -> compilation or bundling issue:

| Error Pattern                                  | Likely Cause                               | Load Skill                              |
| ---------------------------------------------- | ------------------------------------------ | --------------------------------------- |
| "Cannot find module" in component file         | Missing import or path alias misconfigured | -                                       |
| "Type X is not assignable to type Y"           | Signal/input type mismatch                 | Use skill: `angular-signals-patterns`   |
| "NG0100: Expression has changed after checked" | State mutation in lifecycle hook           | Use skill: `angular-component-patterns` |

**Runtime error** -> JavaScript exception during rendering or event handling:

| Error Pattern                                | Likely Cause                                | Load Skill                            |
| -------------------------------------------- | ------------------------------------------- | ------------------------------------- |
| "Cannot read properties of undefined"        | Accessing signal value before data loads    | Use skill: `angular-signals-patterns` |
| "Maximum call stack size exceeded"           | Infinite computed or effect cycle           | Use skill: `angular-signals-patterns` |
| "NG0203: inject() must be called in context" | inject() called outside constructor/factory | Use skill: `angular-service-patterns` |

**Test failure** -> assertion mismatch, async timing, TestBed setup:

| Error Pattern                             | Likely Cause                                         | Load Skill                            |
| ----------------------------------------- | ---------------------------------------------------- | ------------------------------------- |
| "No provider for HttpClient"              | Missing provideHttpClient in TestBed                 | Use skill: `angular-testing-patterns` |
| fixture.detectChanges() not updating view | OnPush component needs signal update or input change | Use skill: `angular-testing-patterns` |
| "Component X is not a known element"      | Missing import in TestBed configuration              | Use skill: `angular-testing-patterns` |

**Performance issue** -> slow renders, memory leak, bundle size -> Use skill: `frontend-performance`

STEP 3 - LOCATE: Read the error to identify the source file and component/service name. Open the file and surrounding context (~50 lines above and below). Trace the component tree: route -> parent component -> failing component -> service. Identify which layer the bug is in (Component | Service | State | Routing | RxJS | Build).

STEP 4 - ROOT CAUSE: Explain WHY this error occurred, not just what happened. Reference the specific code that causes the issue. If it's a pattern violation (not just a one-off bug), name the pattern. Rate confidence: HIGH (certain, evidence is clear), MEDIUM (likely, but alternative causes exist), or LOW (need more info to confirm).

STEP 5 - FIX: Show the exact code change needed (before / after). If multiple fixes are possible, rank by: (1) Correctness, (2) Minimal change surface, (3) Alignment with project patterns. Explain any trade-offs between alternatives.

STEP 6 - PREVENT: Suggest a test that would have caught this bug. If it's a pattern violation, reference the relevant atomic skill. If the same bug could exist elsewhere, identify other occurrences (grep for similar patterns).

## Output Format

Present the analysis in this structure:

**Bug Analysis** - error type, confidence (HIGH/MEDIUM/LOW), layer (Component/Service/State/Routing/RxJS/Build)

**Root Cause** - explanation of why this happened, referencing specific code

**Fix** - before/after code diff showing the exact change, with explanation

**Prevention** (omit if fix is trivial) - test that would catch this bug, pattern reference, other occurrences found via grep

### Output Constraints

- Keep the analysis focused - one bug, one fix
- Omit Prevention section if the fix is trivial (e.g., typo, missing import)
- If confidence is LOW, add a **Needs Clarification** section listing what info would help
- No code style commentary unrelated to the bug
- No suggestions for unrelated improvements

## Self-Check

- [ ] Error input accepted and clarified if ambiguous (STEP 1)
- [ ] Error classified into category before any code is read or fix proposed (STEP 2)
- [ ] Source file and component/service located; layer identified (STEP 3)
- [ ] Root cause explains WHY with specific code reference; confidence level stated (STEP 4)
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom (STEP 5)
- [ ] Test suggested that would catch this bug; other occurrences identified if pattern is widespread (STEP 6)

## Avoid

- Generic debugging advice ("add console.log", "clear cache")
- Fixing symptoms instead of root causes
- Suggesting refactors when a targeted fix suffices
- Analysis without reading the actual source code
- Proposing fixes that introduce new anti-patterns (adding `any`, disabling strict mode, wrapping in setTimeout for change detection)
- Mixing incident response concerns into developer debugging
