---
name: kotlin-code-explain
description: Kotlin / Spring Boot framework signals for code explanation - coroutines and structured concurrency, suspend boundaries, null safety, data class equality, sealed hierarchies, and Spring AOP proxy interactions with Kotlin's `final`-by-default. Used by task-code-explain to explain Kotlin code with stack-aware gotchas.
metadata:
  category: backend
  tags: [explanation, code-understanding, kotlin, spring, coroutines]
user-invocable: false
---

# Kotlin Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Kotlin / Spring Boot.

## When to Use

- A workflow needs Kotlin-specific signals: coroutine boundaries, null safety, data class semantics, sealed hierarchies, AOP-proxy interactions with `final`-by-default classes.
- The target code uses `suspend` functions, `Flow`, `Channel`, coroutine scopes, Kotlin idioms (`?.`, `!!`, `let`, `also`, `apply`, scope functions), or Spring annotations on Kotlin classes.

## Rules

- Identify whether the function is `suspend` first - suspend boundaries change error propagation, cancellation, and threading semantics.
- Distinguish coroutine scope owners (`viewModelScope`, `applicationScope`, `CoroutineScope(SupervisorJob())`, structured `coroutineScope { }`) - the scope determines cancellation propagation.
- Identify the dispatcher (`Dispatchers.IO`, `Dispatchers.Default`, `Dispatchers.Main`, custom) and whether dispatcher switches happen via `withContext`.
- Surface Kotlin's `final`-by-default interaction with Spring CGLIB proxies: classes annotated with `@Service`, `@Component`, `@RestController` need `open` (or the `kotlin-spring` Gradle plugin) for `@Transactional`/`@Async`/`@Cacheable` to work.
- Distinguish `null`-safety signals - safe calls (`?.`), Elvis (`?:`), and platform types from Java interop (`Type!` shown in IDE) - because platform types bypass nullability checks.

## Patterns

### Coroutines and Suspend Boundaries

| Construct                        | Behavior                                                                                          | What to flag                                                                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `suspend fun`                    | Can be paused; must be called from another suspend or a coroutine builder                         | Calling a suspend from a non-suspend context requires `runBlocking` (blocks thread) or `launch`/`async` (fire and forget without await)     |
| `withContext(Dispatchers.IO)`    | Switches dispatcher; resumes on the new pool                                                      | Long blocking I/O on `Dispatchers.Default` saturates the limited CPU pool; use `IO`                                                         |
| `coroutineScope { }`             | Structured concurrency: child coroutines must finish before scope returns; failure cancels siblings | Wrapping with `supervisorScope { }` changes failure isolation - one child failure does not cancel siblings                                  |
| `launch { }`                     | Fire-and-forget; returns `Job`; exceptions propagate to parent                                    | Uncaught exceptions in `launch` propagate to the parent scope and may cancel sibling coroutines                                             |
| `async { }`                      | Returns `Deferred<T>`; exceptions deferred until `.await()`                                       | Failing to `await` swallows the exception silently                                                                                           |
| `Flow<T>`                        | Cold stream; collected via `collect`; back-pressure built in                                      | Operators run on the collector's context unless `flowOn` switches it; `collect` is a suspend - blocking inside breaks the back-pressure     |
| `Channel<T>`                     | Hot communication primitive; buffered or rendezvous                                               | Forgetting to `close()` leaves consumers suspended forever; unhandled `ClosedChannelException` on send after close                          |
| `runBlocking { }`                | Bridges blocking and suspend worlds                                                               | Using inside another coroutine context blocks the current thread - usually a bug; only OK at the top of `main` or in tests                  |

**Cancellation:** coroutines cooperatively check for cancellation at suspend points. Long CPU-bound code without suspend points cannot be cancelled. Use `ensureActive()` or `yield()` in tight loops.

### Spring + Kotlin AOP Gotcha (highest-yield class)

Kotlin classes and methods are `final` by default. Spring CGLIB proxies require `open` to subclass.

- Without `kotlin-spring` plugin: `@Service` classes need `open` and methods that use `@Transactional`/`@Async`/`@Cacheable`/`@PreAuthorize` need `open` too. Otherwise the annotations silently do nothing.
- With `kotlin-spring` plugin: classes annotated with Spring stereotypes are automatically `open`. Verify the plugin is in `build.gradle.kts` (`plugins { kotlin("plugin.spring") }`).
- `data class` cannot be opened - cannot be a Spring bean if you need proxying. Use a regular class or `@Service` on a wrapper.

Self-invocation gotcha is the same as Java/Spring - calling `this.method()` bypasses the proxy regardless.

### Null Safety and Platform Types

- `String` (non-null), `String?` (nullable), `String!` (platform type from Java interop - nullability unknown).
- `!!` (assert non-null) crashes with `NullPointerException` if the value is null. Treat as a smell unless the surrounding contract guarantees non-null.
- `?.let { ... }` runs the block only when non-null; common pattern for optional handling.
- `lateinit var` defers initialization; accessing before init throws `UninitializedPropertyAccessException` - common in DI fields and test fixtures.
- `by lazy { }` initializes on first access; thread-safe by default (`SYNCHRONIZED` mode).

### Data Classes and Equality

- `data class` auto-generates `equals`, `hashCode`, `toString`, `copy`, and component functions for destructuring.
- Equality is based on **constructor properties only**. Properties declared in the body are ignored by `equals`/`hashCode`.
- `copy()` returns a new instance with selected properties overridden. Mutating the original after copy does not affect the copy.
- Used as Set/Map keys: ensure the underlying values are themselves stable (no mutable collections in the constructor).

### Sealed Hierarchies and Pattern Matching

- `sealed class` / `sealed interface`: subclasses must be in the same module (Kotlin 1.5+) or same file.
- `when` expression on sealed types: compiler checks exhaustiveness only when used as expression (assigned or returned). `when` as statement does not enforce exhaustiveness.
- Adding a new subclass without updating call sites: silent in statement form, compile error in expression form. Prefer expression form.

### Scope Functions (`let`, `run`, `also`, `apply`, `with`)

| Function | Receiver | Returns         | Common use                                                            |
| -------- | -------- | --------------- | --------------------------------------------------------------------- |
| `let`    | `it`     | block result    | Null-safe transformation; mapping a value                             |
| `run`    | `this`   | block result    | Configuration + computation in one block                              |
| `also`   | `it`     | original object | Side effects (logging, debugging); returns the receiver               |
| `apply`  | `this`   | original object | Builder-style configuration; returns the receiver                     |
| `with`   | `this`   | block result    | Multiple operations on a single object without a method chain         |

Common confusion: `apply` vs `also` (both return receiver - `apply` uses `this`, `also` uses `it`). `let` vs `run` (both return block result - `let` uses `it`, `run` uses `this`).

### Spring Idioms in Kotlin

- Constructor injection is idiomatic - no field injection.
- `@ConstructorBinding` for `@ConfigurationProperties` (in Spring Boot 2.x; not needed in 3.x with Kotlin).
- Spring Data interfaces: same as Java; runtime proxy implements the interface.
- `@RequestBody` with `data class`: auto-deserialized via Jackson; `@JsonCreator` is rarely needed in Kotlin since Jackson auto-detects the primary constructor.

### Testing Specifics

- `kotest` and `JUnit 5` (`kotlin.test`) are common; coroutine tests use `runTest` (replaces `runBlocking` for virtual time).
- `MockK` over Mockito for Kotlin (Mockito cannot mock `final` classes by default; MockK handles this natively).
- `@MockBean` on `final` classes requires `open` or the `kotlin-allopen` plugin.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Suspend boundary: is this a `suspend fun`? What scope/dispatcher does it run on?
- Coroutine scope owner and cancellation propagation
- Spring stereotype if applicable; whether `kotlin-spring` plugin is enabled

**Into "Non-Obvious Behavior":**

- AOP proxy gotchas tied to `final`-by-default
- Platform types from Java interop bypassing null checks
- `runBlocking` inside a coroutine context (thread blocking)
- `async` without `await` swallowing exceptions
- `Flow` collector context vs upstream context
- `data class` equality based only on constructor properties
- `lateinit` and `by lazy` initialization timing

**Into "Key Invariants":**

- Suspend functions must be called from a coroutine context
- Spring beans must be `open` (or use plugin) for proxy-backed annotations
- Sealed type exhaustiveness only checked when `when` is an expression

**Into "Change Impact Preview":**

- Adding `@Transactional` to a `final` method: silent no-op without `open` or plugin
- Changing a `data class` constructor breaks `equals`/`hashCode` semantics for any collection using it as key
- Adding a sealed subclass without updating `when` expressions: compile errors at every expression call site (good); statement call sites silently skip (bad)
- Removing `suspend` modifier: callers must adapt; cancellation semantics change

## Avoid

- Treating `final`-by-default as a Java idiom - it is the source of most "annotation does nothing" bugs in Spring + Kotlin
- Describing `?.` and `!!` interchangeably - they have different failure modes
- Recommending `runBlocking` as a fix when the surrounding code is already in a coroutine
- Confusing `launch` and `async` - one fire-and-forgets, the other defers
- Listing all scope functions when only one applies; pick the one used and explain it
