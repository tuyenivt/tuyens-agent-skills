---
name: task-kotlin-debug
description: Diagnose and fix Kotlin + Spring Boot errors including null safety violations, coroutine stack traces, MockK setup errors, and Kotlin-JPA plugin issues. Not for production incident analysis with blast radius assessment (use task-incident-root-cause).
agent: kotlin-architect
metadata:
  category: backend
  tags: [kotlin, spring-boot, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

## When to Use

- Debugging a Kotlin + Spring Boot stack trace or error message
- Fixing null safety violations (`KotlinNullPointerException`, `UninitializedPropertyAccessException`)
- Resolving Kotlin-JPA plugin misconfiguration (`No default constructor`, entity is final)
- Diagnosing coroutine errors (suspension outside coroutine body, Flow exception transparency)
- Fixing MockK test failures (`no answer found`, wrong mock bean annotation)

## STEP 1 - INTAKE

Ask for: full stack trace or error message, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip library frames) and read that file.

**Edge cases**:
- If no stack trace is provided, ask the user for the exact error message or describe the unexpected behavior, then search the codebase for likely trigger points
- If the stack trace contains only library frames (no application code), look for configuration errors in `build.gradle.kts`, `application.yml`, or Spring `@Configuration` classes
- If the error is a compilation error (not runtime), skip to STEP 4 - the root cause is in the compiler message itself

## STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

### Kotlin Null Safety Errors
- `KotlinNullPointerException` -> `!!` used on a null value. Trace where the null originates. Fix: replace `!!` with safe call (`?.`), elvis (`?:`) or `error()`. Use skill: `kotlin-idioms` (null safety section).
- `UninitializedPropertyAccessException` -> `lateinit` property accessed before initialization. Check DI wiring (`@Autowired`, constructor injection) and test setup (`@BeforeEach`).

### Kotlin-JPA Plugin Errors
- `No default constructor for entity` -> missing `kotlin-jpa` Gradle plugin. The plugin generates no-arg constructors for `@Entity` classes.
- `Entity class is final` -> missing `kotlin-allopen` plugin config. Spring/JPA needs open classes for proxying.

```kotlin
// build.gradle.kts fix for both issues
plugins {
    kotlin("plugin.jpa") version "..."     // generates no-arg constructors
    kotlin("plugin.spring") version "..."  // opens @Component, @Service, etc.
}
```

### Coroutine Errors
- `Suspension functions can only be called within coroutine body` -> calling a `suspend` function from non-suspend context. Fix: add `suspend` modifier or wrap in `runBlocking` (only at top-level entry points, not in services). Use skill: `kotlin-coroutines-spring`.
- `IllegalStateException: Flow exception transparency` -> throwing inside `Flow.collect`. Use `catch` operator before `collect`.
- `JobCancellationException` -> parent scope was cancelled. Check scope hierarchy and structured concurrency.

### MockK / Testing Errors
- `MockKException: no answer found` -> missing stub. Common cause: using `every` instead of `coEvery` for `suspend` functions. Use skill: `kotlin-testing-patterns`.

```kotlin
// BEFORE (fails silently - every doesn't work with suspend)
every { repo.findById(1L) } returns order

// AFTER (coEvery for suspend functions)
coEvery { repo.findById(1L) } returns order
```

- `ClassCastException` in Spring test slice -> using `@MockBean` instead of `@MockkBean` for Kotlin classes.

### Java/Spring Errors
- For all standard Java/Spring errors (`DataIntegrityViolationException`, `HttpMessageNotReadableException`, `MethodArgumentNotValidException`, etc.) -> same classification as Java plugin's `task-spring-debug`. Check the Java-layer cause first, then look for Kotlin-specific factors (null safety, final classes, coroutines).

## STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (not library code)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it upstream through constructor injection, scope functions, or coroutine chains
4. For coroutine errors: check the full coroutine stack trace (look for "caused by" frames after the initial `invokeSuspend` frame)

## STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The MockKException occurs because `every` was used to stub `findById()`, which is
a suspend function. MockK requires `coEvery` for suspend functions - regular
`every` silently ignores the stub and MockK reports "no answer found."
```

## STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms. Use skill: `kotlin-idioms` to ensure fixes follow Kotlin conventions.

## STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:
- **Test** that exercises the exact code path
- **Kotlin compiler check** (e.g., make nullable types explicit)
- **Gradle plugin config** for JPA/Spring issues
- **Linting rule** (detekt) if applicable

## Avoid

- Do not introduce `!!` to fix null errors - use safe calls, elvis, or restructure the code
- Do not use `runBlocking` inside service methods to fix coroutine errors - propagate `suspend` through the call chain
- Do not switch to Mockito to fix MockK errors - fix the MockK usage (usually `coEvery`/`coVerify`)
- Do not make JPA entities `open` manually - use the `kotlin-allopen` plugin
- Do not add blanket `try/catch` blocks to suppress exceptions

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why the error occurs, referencing specific file:line]

## Fix
[Before/after code blocks]

## Prevention
[Test, compiler check, or config change to prevent recurrence]
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Kotlin idioms preserved - no `!!` introduced, no Java-style synchronized blocks
- [ ] Prevention step included
- [ ] For coroutines: scope/context addressed; for kotlin-jpa: Gradle plugin config checked; for MockK: `coEvery`/`coVerify` used correctly
