---
name: task-kotlin-debug
description: Debug Kotlin / Spring Boot errors: null safety, coroutine stack traces, MockK, kotlin-jpa plugin, Jackson, startup failures from final classes.
agent: kotlin-architect
metadata:
  category: backend
  tags: [kotlin, spring-boot, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

# Debug Kotlin + Spring Boot Error

## When to Use

- Debugging a Kotlin / Spring Boot stack trace or error
- Fixing null-safety violations, kotlin-jpa misconfiguration, coroutine errors, MockK failures, Jackson serialization, startup failures from final Kotlin classes

Not for production incidents (use `/task-oncall-start`) or new features (use `task-kotlin-implement`).

## Edge Cases

- **No stack trace**: ask for the exact error or describe the unexpected behavior, then search likely trigger points.
- **Library-only frames**: configuration issue. Check `build.gradle.kts`, `application.yml`, `@Configuration` classes.
- **Compilation error**: skip to FIX - the compiler message is the root cause. Type mismatches, smart-cast failures, missing overrides.
- **CI-only**: environment differences. JVM version, Gradle plugin versions, Testcontainers availability, profile config.
- **Multiple errors**: focus on the first. Later errors are cascades.

## Workflow

### Step 1 - Load behavioral principles (mandatory, first)

Use skill: `behavioral-principles`.

### Step 2 - Intake

Use skill: `stack-detect`. Ask for:

- Full stack trace or error
- Source file where it originates
- Expected behavior
- Runtime / test / compile / startup

Identify the first application-code frame (skip library frames) and read that file.

### Step 3 - Classify

Match the error to one category, then load the relevant atomic skill.

**Null safety**

| Error                                              | Cause                                                              | Fix                                                                |
| -------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| `KotlinNullPointerException`                       | `!!` on null                                                       | Replace with `?.` / `?:` / `error()`. Use skill: `kotlin-idioms`  |
| `UninitializedPropertyAccessException`             | `lateinit` accessed before init                                    | Check DI wiring + `@BeforeEach`                                    |
| `IllegalStateException: ... must not be null`      | Non-null Kotlin param received null from Java                      | Make parameter nullable or `@NonNull` on Java source              |
| `IllegalStateException: Required value was null`   | `checkNotNull` / `requireNotNull` / property delegate returned null | Trace where the value should be set; don't remove the check       |

**Kotlin-JPA plugin**

| Error                                                  | Cause                          | Fix                                                                                  |
| ------------------------------------------------------ | ------------------------------ | ------------------------------------------------------------------------------------ |
| `No default constructor for entity`                    | Missing `kotlin-jpa`           | Add `kotlin("plugin.jpa")` to `build.gradle.kts`                                     |
| `Entity class is final` / `could not initialize proxy` | Missing `kotlin-allopen` setup | Add `kotlin("plugin.spring")`                                                        |
| `BeanNotOfRequiredTypeException` on @Transactional     | Class final, CGLIB can't proxy | Same fix: `kotlin("plugin.spring")` opens stereotype-annotated classes               |

```kotlin
plugins {
    kotlin("plugin.jpa")
    kotlin("plugin.spring")
}
```

**Coroutines**

| Error                                                              | Cause                                                                 | Fix                                                                                                   |
| ------------------------------------------------------------------ | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `Suspension functions can only be called within coroutine body`    | Calling `suspend` from non-suspend                                    | Add `suspend` or use `runBlocking` only at top-level entry. Use skill: `kotlin-coroutines-spring`     |
| `IllegalStateException: Flow exception transparency`               | Throwing inside `Flow.collect`                                        | Use `catch` operator before `collect`                                                                  |
| `JobCancellationException`                                         | Parent scope cancelled                                                | Check scope hierarchy. Common: `GlobalScope` or unstructured scope cancelled at shutdown               |
| `LazyInitializationException` from `suspend` controller / `withContext` block | JPA session is request-thread-bound; coroutine resumed elsewhere      | Fetch inside `@Transactional` (DTO / `JOIN FETCH`). Use skill: `kotlin-spring-jpa-performance`         |
| `IllegalStateException: No transaction is currently active`        | `@Transactional` on `suspend` but missing `kotlinx-coroutines-reactor`, or `runBlocking` bridge to suspend | Add the reactor bridge; propagate `suspend`. Use skill: `kotlin-coroutines-spring`        |

**MockK / testing**

| Error                                          | Cause                                              | Fix                                                                  |
| ---------------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------- |
| `MockKException: no answer found`              | `every` on a `suspend` function                    | Change `every` → `coEvery`, `verify` → `coVerify`                    |
| `ClassCastException` in Spring slice           | `@MockBean` used instead of `@MockkBean`           | Replace with `@MockkBean`                                            |
| `UninitializedPropertyAccessException` in test | Missing `@ExtendWith(MockKExtension::class)`       | Add the extension or use `@SpringBootTest`                           |

```kotlin
// Before: silent fail
every { repo.findById(1L) } returns order
// After
coEvery { repo.findById(1L) } returns order
```

**Jackson / serialization**

| Error                                                                          | Cause                                                                           | Fix                                                                                            |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `InvalidDefinitionException: Cannot construct instance`                        | Missing `jackson-module-kotlin` or no-arg constructor                            | Add the module dependency and register `KotlinModule`                                          |
| `MismatchedInputException` / `MissingKotlinParameterException` on data class   | Null for non-null Kotlin property                                                | Make nullable with default, or add `@JsonProperty(required = true)`                            |
| `InvalidDefinitionException` on inline value class                             | Jackson doesn't unwrap                                                           | Add `@JsonCreator` or `KotlinModule { enable(KotlinFeature.SingletonSupport) }`                |
| Bean Validation / `@JsonProperty` silently ignored on data class               | Missing use-site target - landed on constructor param                            | Add `@field:NotBlank` / `@get:JsonProperty`. See `kotlin-idioms`                                |

**Startup failures**

| Error                                                       | Cause                                                  | Fix                                                                  |
| ----------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------- |
| `BeanCurrentlyInCreationException`                          | Circular dependency                                    | Restructure; `@Lazy` on one injection as temporary fix               |
| `NoSuchBeanDefinitionException` for Kotlin class            | Wrong package or missing `@Component` / `@Service`     | Check `@ComponentScan` base packages                                  |
| `UnsatisfiedDependencyException` with Kotlin default params | Spring can't pick the constructor with defaults        | Add `@JvmOverloads` or use explicit `@Bean` factory                  |

**Java/Spring errors with Kotlin factors**

For standard Spring errors (`DataIntegrityViolationException`, `MethodArgumentNotValidException`, `UnexpectedRollbackException`, etc.), walk `Caused by:` to the root then look for Kotlin-specific factors:

- Final-class proxy failures → missing `kotlin("plugin.spring")`
- JPA no-arg failures → missing `kotlin("plugin.jpa")`
- Null parameter from Java → platform-type leak
- LIE inside `suspend` controller, `@Transactional` on suspend without reactor bridge → coroutine errors above
- Self-invocation defeating `@Transactional` / `@Async` / `@Cacheable` (companion object / extension dispatch) → see `kotlin-spring-transaction`

If no Kotlin-specific factor, fall back to `kotlin-spring-exception-handling` for the response side.

### Step 4 - Locate

Read the trace top-to-bottom for the first application-code frame. Open and read the failing function. Trace the data path upstream through constructor injection, scope functions, or coroutine chains. For coroutine errors, check "caused by" frames after `invokeSuspend`.

### Step 5 - Root cause

State **why** with confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW]
The MockKException occurs because `every` was used to stub `findById()`, which is
a suspend function. MockK needs `coEvery` for suspends - regular `every` silently
ignores the stub and reports "no answer found."
```

### Step 6 - Fix

Before/after, minimal, addressing root cause not symptom. Use skill: `kotlin-idioms` for idiom alignment.

### Step 7 - Prevention

Add one guard so the class of error cannot recur: a test, a Kotlin compiler check, a Gradle plugin config, a detekt rule, or a CI check.

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why, referencing file:line]

## Fix
[Before/after code]

## Prevention
[Test, compiler check, config, or CI step]
```

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] Error classified into a specific category before any fix
- [ ] Root cause references specific file/line; confidence stated
- [ ] Before/after fix; minimal; root cause not symptom
- [ ] Kotlin idioms preserved (no new `!!`, no Java-style workarounds, no manual `open`)
- [ ] Prevention step included
- [ ] For coroutines: scope/context addressed; for kotlin-jpa: plugin checked; for MockK: `coEvery` / `coVerify`; for Jackson: `jackson-module-kotlin` verified

## Avoid

- Introducing `!!` to fix nulls - safe calls / Elvis / restructure
- `runBlocking` in service methods to fix coroutine errors - propagate `suspend`
- Switching to Mockito to fix MockK - fix the MockK call
- Manual `open` on entities - use `kotlin-allopen` plugin
- Blanket try/catch to suppress exceptions
- Downgrading Kotlin nullable to platform types
