---
name: kotlin-code-explain
description: Kotlin / Spring Boot code explanation: coroutines, suspend boundaries, null safety, sealed hierarchies, AOP proxy with final-by-default classes.
metadata:
  category: backend
  tags: [explanation, code-understanding, kotlin, spring, coroutines]
user-invocable: false
---

# Kotlin Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Kotlin / Spring Boot.

## When to Use

- A workflow needs Kotlin-specific signals: coroutine boundaries, null safety, data class semantics, sealed hierarchies, AOP-proxy interactions with `final`-by-default classes.
- Target code uses `suspend`, `Flow`, scope functions, `!!`, `?.`, Spring annotations on Kotlin classes.

## Rules

- Identify `suspend` first - it changes error propagation, cancellation, and threading.
- Identify scope owner (`coroutineScope`, application scope bean, `CoroutineScope(SupervisorJob())`) - the scope determines cancellation propagation.
- Identify dispatcher (`IO` / `Default` / `Main` / custom) and any `withContext` switches.
- Flag Kotlin `final`-by-default + Spring CGLIB: `@Service` / `@Component` need `open` (or `kotlin-spring` plugin) for `@Transactional` / `@Async` / `@Cacheable` to work.
- Distinguish `?.` (safe call), `?:` (Elvis), `!!` (assert), `T!` (platform type from Java).

## Patterns

### Coroutines and suspend

| Construct                     | Behavior                                                        | What to flag                                                                                          |
| ----------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `suspend fun`                 | Pausable; must be called from suspend or a builder              | Calling from non-suspend forces `runBlocking` (blocks) or `launch`/`async` (fire-and-forget)          |
| `withContext(Dispatchers.IO)` | Switches dispatcher, resumes on new pool                        | Long blocking I/O on `Default` saturates the CPU pool                                                  |
| `coroutineScope { }`          | Structured: failure cancels siblings, awaits children           | `supervisorScope { }` changes failure isolation - each child fails independently                       |
| `launch { }`                  | Fire-and-forget, returns `Job`                                  | Exceptions propagate to parent scope                                                                  |
| `async { }`                   | Returns `Deferred<T>`; exceptions deferred to `.await()`        | No `await` = swallowed exception                                                                       |
| `Flow<T>`                     | Cold stream; operators on collector's context unless `flowOn`   | Blocking inside `collect` breaks back-pressure                                                         |
| `Channel<T>`                  | Hot buffered / rendezvous                                       | Forgetting `close()` leaves consumers suspended forever                                                |
| `runBlocking { }`             | Bridges blocking / suspend                                      | Inside another coroutine context: bug (blocks thread)                                                  |

**Cancellation** is cooperative at suspend points. Long CPU-bound code without suspends cannot be cancelled - use `ensureActive()` or `yield()`.

### Proxy-backed annotations (highest-yield bug class)

Proxied annotations and what they need to fire: `@Transactional`, `@Async`, `@Cacheable` / `@CacheEvict` / `@CachePut`, `@PreAuthorize` / `@PostAuthorize`, `@Retryable`, `@Validated`.

**Three silent-failure modes** apply to every annotation above:

1. **Self-invocation** - `this.method()` from inside the same bean bypasses the proxy. In Kotlin this also fires via `companion object` calls and extension-function dispatch. Fix: extract to a separate bean, or self-inject.
2. **`private` / `final` / `protected`** - CGLIB cannot override; the annotation is silently ignored. In Kotlin, every method is `final` by default - this is the dominant failure mode here.
3. **Init-time call** (`@PostConstruct`, constructor, `@Bean` factory body calling the method on `this`) - the proxy isn't wired yet; the raw class runs.

**The `kotlin-spring` plugin** opens `@Component` / `@Service` / `@Configuration` / `@RestController` / `@Repository` and `@Transactional` automatically. It does **not** open classes annotated with `@Retryable`, custom proxy annotations, or your own meta-annotations - those still need explicit `open class` / `open fun` or a custom `allopen` rule (`kotlin("plugin.allopen")`). Without it, `@Retryable` / `@Cacheable` / custom proxy annotations silently no-op.

- `data class` cannot be opened - cannot host any of these annotations as a proxied bean.
- `object` is not a Spring bean - compiled to a static holder. `@Autowired` doesn't inject it; annotations above are ignored. Use `@Component class`.
- `internal` visibility name-mangles (`foo$module_name`). Works for constructor injection; can break reflection-based wiring.

**`@Transactional` on `suspend`**: needs `kotlinx-coroutines-reactor` on the classpath so Spring 6 binds the TX across suspension. Even wired correctly, blocking JPA inside a suspend on `Dispatchers.IO` does not become non-blocking - the TX is held across suspension and any `withContext` switch detaches from it. Prefer non-suspend `@Transactional` services called from a suspend orchestrator that handles dispatcher switching.

**External I/O inside `@Transactional`**: holds the DB connection through the round-trip. Move out, or publish `@TransactionalEventListener(AFTER_COMMIT)`.

### Null safety and platform types

- `String` (non-null), `String?` (nullable), `String!` (platform type from Java - unknown).
- `!!` crashes with `NullPointerException`. Smell unless the contract guarantees non-null.
- `?.let { ... }` runs the block only when non-null.
- `lateinit var` defers initialization; access before init throws `UninitializedPropertyAccessException`.
- `by lazy { }` initializes on first access, thread-safe.

### Data class equality

- Auto-generated `equals` / `hashCode` / `toString` / `copy` / component functions.
- Equality based on **constructor properties only**. Body properties are ignored.
- `copy()` is shallow - mutable collections share references with the original.

### Inline value classes (`@JvmInline value class`)

- Erased to the underlying type at bytecode level - zero allocation for type-safe IDs.
- Equality is value-equality (two `UserId(1L)` are equal because they erase to the same `Long`).
- Jackson does not unwrap by default - needs `KotlinModule` or `@JsonCreator`.
- Boxing reappears as a generic param, nullable, or assigned to `Any`.

### Sealed hierarchies

- Subclasses in the same module (Kotlin 1.5+) or file.
- `when` checks exhaustiveness **only as an expression** (assigned / returned). As a statement, no check.
- Adding a subclass: silent in statement form, compile error in expression form. Prefer expression form.

### Scope functions

Definitive table in `kotlin-idioms`. When explaining code, name the one used and the confusion pair: `apply` vs `also` (both return receiver; `this` vs `it`), `let` vs `run` (both return block result; `it` vs `this`).

### `@TransactionalEventListener` phases

- `BEFORE_COMMIT` (rare): inside the TX; listener exception rolls everything back.
- `AFTER_COMMIT` (default, most common): runs only on commit; **listener exception is swallowed/logged** (TX already committed) - use outbox for durability.
- `AFTER_ROLLBACK`: compensating actions.
- `AFTER_COMPLETION`: always runs.

Listener starting a new `@Transactional` in `AFTER_COMMIT` / `AFTER_ROLLBACK` needs `propagation = REQUIRES_NEW` - the original is gone. `@Async` listener runs on the executor pool; SecurityContext / MDC don't propagate without setup.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Flow Context:**

- Suspend boundary - is this `suspend`? Scope / dispatcher?
- Coroutine scope owner and cancellation propagation
- Spring stereotype + whether `kotlin-spring` plugin is present

**Non-Obvious Behavior:**

- AOP proxy gotchas tied to `final`-by-default
- Platform types from Java bypassing null checks
- `runBlocking` inside coroutine context
- `async` without `await` swallowing exceptions
- `Flow` collector vs upstream context
- `data class` equality based on constructor properties only
- `lateinit` / `by lazy` timing
- `@Transactional` on `suspend` (reactor bridge, TX held across suspension)
- External I/O inside `@Transactional` (connection held)
- `@TransactionalEventListener` phase semantics (especially `AFTER_COMMIT` swallowing)
- Inline value classes at API boundaries (Jackson unwrap; forced boxing)
- `object` declarations needing Spring DI or proxying

**Key Invariants:**

- Suspend functions must be called from a coroutine context
- Spring beans must be `open` (or use plugin) for proxy-backed annotations
- Sealed exhaustiveness only checked as expression

**Change Impact Preview:**

- Adding `@Transactional` to a `final` method: silent no-op without `open` / plugin
- Changing a `data class` constructor breaks `equals` / `hashCode` for collection keys
- Removing `suspend`: callers must adapt; cancellation semantics change
- Moving external I/O out of `@Transactional`: shortens connection hold
- Switching listener from `BEFORE_COMMIT` to `AFTER_COMMIT`: listener failures no longer roll back
- Replacing `data class` with `@JvmInline value class`: Jackson breaks without `KotlinModule`

## Avoid

- Treating `final`-by-default as a Java idiom - it's the source of most "annotation no-op" bugs
- Conflating `?.` and `!!` - different failure modes
- Recommending `runBlocking` when the caller is already a coroutine
- Confusing `launch` and `async`
- Listing all scope functions when only one applies - pick the one used and explain it
