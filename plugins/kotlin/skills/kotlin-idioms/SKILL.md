---
name: kotlin-idioms
description: "Idiomatic Kotlin for Spring Boot: data class DTOs, null safety over Optional, scope functions, sealed errors, value classes, JPA plugin."
user-invocable: false
---

# Kotlin Idioms for Spring Boot

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing DTOs, domain models, mappers, or error hierarchies in Kotlin / Spring Boot
- Converting Java code (`Optional`, Lombok, streams, getters) to idiomatic Kotlin
- Working with nullable types from Java libraries or JPA entities

Not for coroutines (see `kotlin-coroutines-spring`) or testing (see `kotlin-testing-patterns`).

## Rules

- `T?` instead of `Optional<T>`. `Optional` only for Java-interop boundaries.
- `data class` for DTOs, value objects, `@ConfigurationProperties`. Regular `class` for JPA entities (canonical pattern in `kotlin-spring-jpa-performance`).
- `!!` only as fail-fast assertion. Use `?:`, `?.`, `requireNotNull`, or `error()` otherwise.
- `require` / `check` / `checkNotNull` over manual `if (x) throw`. `require` for arguments (`IllegalArgumentException`), `check` for invariants (`IllegalStateException`).
- Kotlin stdlib (`map`, `filter`, `groupBy`, `sumOf`) over Java streams.
- `@Jvm*` annotations only when Java callers or Spring reflection need them.
- `kotlin("plugin.spring")` + `kotlin("plugin.jpa")` Gradle plugins. Without them: `No default constructor for entity` (JPA), `BeanNotOfRequiredTypeException` / `could not initialize proxy` (Spring AOP).
- `val` over `var` except mutable framework fields (entity `status`, audit timestamps).
- Scope-function nesting max 2 levels; deeper - extract to a named function.

## Patterns

### Java to Kotlin reference shape

```kotlin
@Service
class OrderService(private val orderRepo: OrderRepository) {       // primary-constructor injection

    fun findOrder(id: Long): OrderResponse? =                      // T? not Optional<T>
        orderRepo.findByIdOrNull(id)?.toResponse()                 // Spring Data Kotlin ext

    fun create(req: CreateOrderRequest): OrderResponse {
        require(req.items.isNotEmpty()) { "items required" }       // require, not if/throw
        return orderRepo.save(req.toEntity()).toResponse()         // extension functions
    }
}

private fun CreateOrderRequest.toEntity() = Order(userId, OrderStatus.PENDING)
private fun Order.toResponse() = OrderResponse(id, status, total)
```

### Gradle plugins for JPA / Spring

```kotlin
plugins {
    kotlin("plugin.spring")   // opens @Component / @Service / @Configuration / @Transactional
    kotlin("plugin.jpa")      // no-arg constructors for @Entity / @Embeddable / @MappedSuperclass
}
```

### Null safety

```kotlin
fun findUser(id: Long): User?                      // not Optional<User>
val name = user?.profile?.displayName              // safe call chain
val name = user?.name ?: "Anonymous"               // Elvis default
val email = user?.email?.let { it.lowercase() }    // transform when present
val url = System.getenv("URL") ?: error("URL required")   // fail-fast over !!
```

**Platform types from Java** (`String!`): treat as nullable at the call site. Assigning `T!` to a non-null `T` compiles but throws on null.

### `require` / `check` / `error`

```kotlin
require(items.isNotEmpty()) { "items required" }      // IllegalArgumentException
val uid = checkNotNull(userId) { "userId set here" }   // IllegalStateException; smart-cast non-null
check(total > BigDecimal.ZERO) { "positive total" }    // invariant
error("unreachable")                                   // unreachable state
```

Lazy `{ "..." }` lambdas - interpolation only runs on failure.

### Named arguments replace builders

```kotlin
val req = CreateOrderRequest(
    userId = currentUser.id,
    items = listOf(item),
    expressShipping = true,
)

data class PageRequest(val page: Int = 0, val size: Int = 20, val sort: String = "id,desc")
PageRequest(size = 5)              // override one default
```

No Lombok `@Builder`; no telescoping constructors.

### `data class` and use-site annotation targets

Kotlin property expansion (field + getter + setter + constructor param) means framework annotations often need an explicit target:

```kotlin
data class CreateUserRequest(
    @field:NotBlank                  // Bean Validation on backing field
    @field:Size(min = 3, max = 50)
    val username: String,

    @get:JsonProperty("created_at")  // Jackson on getter
    val createdAt: Instant,
)
```

Targets: `@field:`, `@get:` / `@set:`, `@param:`, `@property:`. Missing target = annotation silently lands on the wrong element and frameworks ignore it.

### Scope functions

| Function | Receiver | Returns       | Use for                              |
| -------- | -------- | ------------- | ------------------------------------ |
| `let`    | `it`     | lambda result | Null-safe transform, local scope     |
| `apply`  | `this`   | object        | Builder-style configuration          |
| `run`    | `this`   | lambda result | Compute value from object's context  |
| `also`   | `it`     | object        | Side effects (logging, events)       |
| `with`   | `this`   | lambda result | Multiple ops on same object          |

```kotlin
val request = HttpEntity(body).apply { headers.setBearerAuth(token) }       // configure
val order = repo.save(newOrder).also { log.info("created id={}", it.id) }   // side effect + pass-through
```

### Sealed hierarchies

```kotlin
sealed class OrderError {
    data class NotFound(val id: Long) : OrderError()
    data class InsufficientStock(val itemId: Long, val available: Int) : OrderError()
    data object Unauthorized : OrderError()
}

fun render(error: OrderError): ResponseEntity<*> = when (error) {   // exhaustive when expression
    is OrderError.NotFound -> ResponseEntity.status(404).body("not found: ${error.id}")
    is OrderError.InsufficientStock -> ResponseEntity.status(409).body(error)
    OrderError.Unauthorized -> ResponseEntity.status(403).build<Unit>()
}
```

Exhaustiveness check only applies when `when` is used as an expression (assigned, returned, or last expression). `when` as a statement does not check.

### Inline value classes for type-safe IDs

```kotlin
@JvmInline value class OrderId(val value: Long)
@JvmInline value class UserId(val value: Long)

fun getOrder(id: OrderId): Order   // compiler prevents passing UserId here
```

Boxing reappears at API boundaries (`List<OrderId>`, `OrderId?`, generic params). Jackson needs `jackson-module-kotlin` or `@JsonCreator` to round-trip them.

### Extension functions over utility classes

```kotlin
fun Order.toResponse() = OrderResponse(id, status, total)
fun List<Order>.totalRevenue(): BigDecimal = sumOf { it.total }
```

Skip `class OrderUtils { companion object { @JvmStatic ... } }`.

### `companion object` and `object`

```kotlin
class Order(val id: Long) {
    companion object {
        const val MAX_ITEMS = 50               // compile-time constant
        fun empty() = Order(id = 0)            // factory
    }
}

object OrderIdGenerator { fun next(): Long = ... }   // singleton; no .INSTANCE
```

`object` is not a Spring bean - `@Autowired` won't inject it; `@Transactional` / `@Async` on its methods are ignored. Use `@Component class` for DI / proxying.

### `@ConfigurationProperties` data class

```kotlin
@ConfigurationProperties(prefix = "app.orders")
data class OrderProperties(
    val maxItemsPerOrder: Int = 50,
    val retry: RetryProperties = RetryProperties(),
) {
    data class RetryProperties(val maxAttempts: Int = 3, val delayMs: Long = 1000)
}
```

`@Value("\${...}")` only for one-off values. Escape `$` in Kotlin: `\${prop.name}`.

### Java interop annotations

`@JvmStatic` (Java calls `Companion.method()` as `Class.method()`), `@JvmField` (exposes property as public field), `@JvmOverloads` (generates overloads for default-parameter functions).

## Output Format

```
## Kotlin Idiom Review

Gradle plugins: kotlin-spring {yes|no|n/a}, kotlin-jpa {yes|no|n/a}
!! count: {count, each justified}
Platform types treated nullable: {yes | no}

### Conversions
| Java pattern              | Kotlin idiom                       | Files |
| ------------------------- | ---------------------------------- | ----- |
| Optional<T>               | T?                                 |       |
| @Data DTO                 | data class                         |       |
| @Data Entity              | class + ID-based equals/hashCode   |       |
| Java streams              | Kotlin stdlib                      |       |
| Lombok @Builder           | named args + defaults              |       |
| Utility class             | extension functions                |       |
| if/throw guard            | require / check / checkNotNull     |       |
| Bean Validation on entity | @field: target on val parameters   |       |
```

## Avoid

- `Optional<T>` in Kotlin code
- `data class` for JPA entities
- `!!` for expected-null cases - use `?: error(...)` or handle the null
- Java streams over Kotlin stdlib
- Manual `open` on entities or `@Service` classes - use the Gradle plugins
- Lombok `@Builder` ports - named arguments cover the same ground
- Manual `if (x == null) throw ...` - use `require` / `check` / `checkNotNull`
- Bean Validation / Jackson annotations on `data class` properties without a use-site target
- Scope-function nesting beyond 2 levels
