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

- Debugging a Kotlin + Spring Boot stack trace or error message
- Fixing null safety violations (`KotlinNullPointerException`, `UninitializedPropertyAccessException`)
- Resolving Kotlin-JPA plugin misconfiguration (`No default constructor`, entity is final)
- Diagnosing coroutine errors (suspension outside coroutine body, Flow exception transparency)
- Fixing MockK test failures (`no answer found`, wrong mock bean annotation)
- Resolving Jackson serialization errors with Kotlin data classes or inline value classes
- Fixing Spring Boot startup failures caused by final Kotlin classes

Not for production incident analysis with blast radius assessment (use `/task-oncall-start`). Not for implementing new features (use `task-kotlin-implement`).

## Edge Cases

- **No stack trace provided**: Ask the user for the exact error message or describe the unexpected behavior, then search the codebase for likely trigger points
- **Library-only stack trace**: If the stack trace contains only library frames (no application code), the issue is configuration. Check `build.gradle.kts`, `application.yml`, or Spring `@Configuration` classes
- **Compilation error (not runtime)**: Skip to STEP 4 - the root cause is in the compiler message itself. Focus on type mismatches, smart cast failures, or missing overrides
- **Error occurs in CI but not locally**: Check for environment differences: JVM version, Gradle plugin versions, test container availability, profile-specific config
- **Multiple errors**: Focus on the first error in the output - later errors are often cascading failures. Fix the root cause first and revalidate

## Implementation

### STEP 1 - LOAD BEHAVIORAL PRINCIPLES (MANDATORY, FIRST)

Use skill: `behavioral-principles`. Load these rules first so they govern classification, root-cause framing, and the fix.

### STEP 2 - INTAKE

Use skill: `stack-detect` to confirm the project stack and identify relevant Kotlin/Spring versions.

Ask for:

- Full stack trace or error message
- The source file where the error originates
- What the user expected to happen
- Whether this is a runtime error, test failure, compilation error, or startup failure

If a stack trace is provided, identify the first application-code frame (skip library frames) and read that file.

### STEP 3 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

#### Kotlin Null Safety Errors

| Error                                         | Cause                                                  | Fix                                                                           |
| --------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `KotlinNullPointerException`                  | `!!` used on a null value                              | Replace `!!` with `?.`, `?:`, or `error()`. Use skill: `kotlin-idioms`        |
| `UninitializedPropertyAccessException`        | `lateinit` property accessed before initialization     | Check DI wiring (constructor injection) and test setup (`@BeforeEach`)        |
| `IllegalStateException: ... must not be null` | Kotlin non-null parameter received null from Java code | Add `?` to the parameter type or add `@NonNull` annotation at the Java source |
| `IllegalStateException: Required value was null` | `checkNotNull(x)` / `requireNotNull(x)` / property delegate (`by lazy`, `Delegates.notNull()`) returned null | Trace where the value should have been set; do not "fix" by removing the `checkNotNull` - it is asserting an invariant. If the value is legitimately optional, change the type to `T?` and handle both branches |

#### Kotlin-JPA Plugin Errors

| Error                                                      | Cause                              | Fix                                                                                        |
| ---------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------ |
| `No default constructor for entity`                        | Missing `kotlin-jpa` Gradle plugin | Add `kotlin("plugin.jpa")` to `build.gradle.kts`                                           |
| `Entity class is final` / `could not initialize proxy`     | Missing `kotlin-allopen` config    | Add `kotlin("plugin.spring")` to `build.gradle.kts`                                        |
| `BeanNotOfRequiredTypeException` on @Transactional service | Class is final, CGLIB cannot proxy | Same fix: `kotlin("plugin.spring")` opens `@Component`/`@Service`/`@Transactional` classes |

```kotlin
// build.gradle.kts fix for JPA plugin issues
plugins {
    kotlin("plugin.jpa") version "..."     // generates no-arg constructors
    kotlin("plugin.spring") version "..."  // opens @Component, @Service, etc.
}
```

#### Coroutine Errors

| Error                                                           | Cause                                      | Fix                                                                                                               |
| --------------------------------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `Suspension functions can only be called within coroutine body` | Calling `suspend` from non-suspend context | Add `suspend` modifier or use `runBlocking` only at top-level entry points. Use skill: `kotlin-coroutines-spring` |
| `IllegalStateException: Flow exception transparency`            | Throwing inside `Flow.collect`             | Use `catch` operator before `collect`                                                                             |
| `JobCancellationException`                                      | Parent scope was cancelled                 | Check scope hierarchy and structured concurrency. Common cause: `GlobalScope.launch` or unstructured `CoroutineScope(...)` in a Spring bean - the parent has no link to the request lifecycle and gets cancelled at shutdown. Use skill: `kotlin-coroutines-spring` |
| `TimeoutCancellationException` outside `withTimeout`            | Coroutine scope timed out upstream         | Trace the scope chain to find which parent set the timeout                                                        |
| `LazyInitializationException` from a `suspend` controller / `withContext` block | JPA Session is bound to the request thread; the coroutine resumed on a different dispatcher worker thread, so OSIV cannot reach it | Do not enable OSIV. Fetch the data inside the `@Transactional` boundary (DTO projection or `JOIN FETCH`); never return a managed entity across the suspension. Use skill: `kotlin-spring-jpa-performance` |
| `IllegalStateException: No transaction is currently active` (R2DBC / coroutine-aware TX) | `@Transactional` was applied to a `suspend` method but the kotlinx-coroutines-reactor bridge is missing, OR a non-suspend bean called the suspend method via `runBlocking` | Add `org.jetbrains.kotlinx:kotlinx-coroutines-reactor`; remove `runBlocking` and propagate `suspend`. Use skill: `kotlin-coroutines-spring` |

#### MockK / Testing Errors

| Error                                          | Cause                                                     | Fix                                                                                       |
| ---------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `MockKException: no answer found`              | Missing stub. Usually `every` used for `suspend` function | Change `every` to `coEvery`, `verify` to `coVerify`. Use skill: `kotlin-testing-patterns` |
| `ClassCastException` in Spring test slice      | `@MockBean` used instead of `@MockkBean`                  | Replace with `@MockkBean`                                                                 |
| `UninitializedPropertyAccessException` in test | Missing `@ExtendWith(MockKExtension::class)`              | Add extension or use `@SpringBootTest`                                                    |

```kotlin
// BEFORE (fails silently - every doesn't work with suspend)
every { repo.findById(1L) } returns order

// AFTER (coEvery for suspend functions)
coEvery { repo.findById(1L) } returns order
```

#### Jackson / Serialization Errors

| Error                                                      | Cause                                                                     | Fix                                                                                                    |
| ---------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `InvalidDefinitionException: Cannot construct instance of` | Missing `jackson-module-kotlin` or no-arg constructor for deserialization | Add `com.fasterxml.jackson.module:jackson-module-kotlin` dependency and register `KotlinModule`        |
| `MismatchedInputException` on data class                   | Null value for non-null Kotlin property                                   | Make the property nullable (`T?`) with a default, or add `@JsonProperty(required = true)`              |
| `InvalidDefinitionException` on inline value class         | Jackson doesn't know how to unwrap inline class                           | Add `@JsonCreator` or configure Jackson with `KotlinModule { enable(KotlinFeature.SingletonSupport) }` |
| `MissingKotlinParameterException` (older `MismatchedInputException`) | Required non-null Kotlin property got null in JSON               | Make the property nullable with a default, or fix the JSON; do not weaken to `T?` if business logic requires non-null |
| Bean Validation / `@JsonProperty` annotations silently ignored on a `data class` | Annotation lacks a use-site target so Kotlin put it on the constructor parameter, not the field/getter | Add `@field:NotBlank` (or `@get:JsonProperty`); see `kotlin-idioms` use-site targets section |

```kotlin
// Ensure jackson-module-kotlin is configured
@Configuration
class JacksonConfig {
    @Bean
    fun kotlinModule() = KotlinModule.Builder()
        .enable(KotlinFeature.StrictNullChecks)
        .build()
}
```

#### Spring Boot Startup Errors

| Error                                                       | Cause                                                        | Fix                                                                             |
| ----------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `BeanCurrentlyInCreationException`                          | Circular dependency between Kotlin beans                     | Restructure to break cycle; use `@Lazy` on one injection point as temporary fix |
| `NoSuchBeanDefinitionException` for Kotlin class            | Class is in wrong package or missing `@Component`/`@Service` | Check `@ComponentScan` base packages; verify annotation is present              |
| `UnsatisfiedDependencyException` with Kotlin default params | Spring can't resolve constructor with default params         | Add `@JvmOverloads` or use explicit `@Bean` factory method                      |

#### Java/Spring Errors

For standard Spring errors (`DataIntegrityViolationException`, `HttpMessageNotReadableException`, `MethodArgumentNotValidException`, `LazyInitializationException`, `UnexpectedRollbackException`, etc.), walk the `Caused by:` chain to the deepest root cause first, then look for Kotlin-specific factors:

- **Final-class proxy failures**: `BeanNotOfRequiredTypeException`, `could not initialize proxy` → missing `kotlin("plugin.spring")` (above)
- **JPA no-arg failures**: `InstantiationException`, `No default constructor` → missing `kotlin("plugin.jpa")` (above)
- **Null parameter from Java caller**: `IllegalStateException: ... must not be null` → platform-type leak (above)
- **Coroutine boundary issues**: LIE inside `suspend` controller, `@Transactional` on suspend method without the reactor bridge → see Coroutine Errors above
- **Self-invocation defeating `@Transactional` / `@Async` / `@Cacheable`**: in Kotlin this most often happens via `companion object` calls or extension-function dispatch. Move the call to a different bean or self-inject. Use skill: `kotlin-spring-transaction`

If the root cause is plain Spring with no Kotlin-specific factor, fall through to the standard Spring exception mapping (use skill: `kotlin-spring-exception-handling` for the response side).

### STEP 4 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (not library code)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it upstream through constructor injection, scope functions, or coroutine chains
4. For coroutine errors: check the full coroutine stack trace (look for "caused by" frames after the initial `invokeSuspend` frame)

### STEP 5 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The MockKException occurs because `every` was used to stub `findById()`, which is
a suspend function. MockK requires `coEvery` for suspend functions - regular
`every` silently ignores the stub and MockK reports "no answer found."
```

### STEP 6 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms. Use skill: `kotlin-idioms` to ensure fixes follow Kotlin conventions.

### STEP 7 - PREVENTION

Add a guard so this class of error cannot recur:

- **Test** that exercises the exact code path
- **Kotlin compiler check** (e.g., make nullable types explicit)
- **Gradle plugin config** for JPA/Spring issues
- **Linting rule** (detekt) if applicable
- **CI check** to catch the issue before merge

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

- [ ] Error classified into a specific category before any fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Kotlin idioms preserved - no `!!` introduced, no Java-style workarounds, no manual `open` modifiers
- [ ] Prevention step included (test, config change, linting rule, or CI check)
- [ ] For coroutines: scope/context addressed; for kotlin-jpa: Gradle plugin config checked; for MockK: `coEvery`/`coVerify` used correctly; for Jackson: `jackson-module-kotlin` verified

## Avoid

- Do not introduce `!!` to fix null errors - use safe calls, elvis, or restructure the code
- Do not use `runBlocking` inside service methods to fix coroutine errors - propagate `suspend` through the call chain
- Do not switch to Mockito to fix MockK errors - fix the MockK usage (usually `coEvery`/`coVerify`)
- Do not make JPA entities `open` manually - use the `kotlin-allopen` plugin
- Do not add blanket `try/catch` blocks to suppress exceptions
- Do not downgrade Kotlin nullable types to platform types (`T!`) to avoid null handling
