---
name: kotlin-idioms
description: "Idiomatic Kotlin patterns for Spring Boot projects: data classes for DTOs, null safety over Optional, scope functions (let/apply/run/also), sealed class error hierarchies, inline value classes, Kotlin-Java interop annotations, and JPA plugin configuration."
user-invocable: false
---

# Kotlin Idioms for Spring Boot

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing DTOs, domain models, or error hierarchies in a Kotlin + Spring Boot project
- Converting Java code (Optional, Lombok @Data, streams) to idiomatic Kotlin
- Reviewing Kotlin code for Java-isms (Optional, getters/setters, streams)
- Designing type-safe wrappers for IDs and primitive value types
- Working with nullable types from Java libraries or JPA entities
- Configuring Kotlin compiler plugins for JPA/Spring compatibility

Not for coroutine patterns (see `kotlin-coroutines-spring`) or test patterns (see `kotlin-testing-patterns`).

## Rules

- Use `data class` for DTOs, value objects, and `@ConfigurationProperties` classes; use regular `class` for JPA entities (`data class` and Hibernate proxies are incompatible)
- Use `T?` instead of `Optional<T>` - Kotlin null safety is more expressive and idiomatic
- Use `!!` only when a null value is a programmer bug and you want an immediate crash - never for business logic
- Use Kotlin stdlib collection operations (`map`, `filter`, `groupBy`) instead of Java streams
- Use `@JvmStatic`, `@JvmField`, `@JvmOverloads` when Kotlin code must be called from Java or Spring frameworks
- Configure `kotlin-jpa` and `kotlin-allopen` (or `kotlin-spring`) Gradle plugins - without them JPA entities fail at runtime with cryptic errors
- Prefer `val` over `var` everywhere except JPA entity mutable fields (status, timestamps)
- Limit scope function nesting to 2 levels maximum - extract to named functions beyond that

## Patterns

### End-to-End: Java Spring Service → Idiomatic Kotlin

This pulls together the most common conversions. Use it as a reference shape when porting a Java service.

```java
// Java (before)
@Service
@RequiredArgsConstructor
public class OrderService {
    private final OrderRepository orderRepo;

    public Optional<OrderResponse> findOrder(Long id) {
        Order o = orderRepo.findById(id).orElse(null);
        if (o == null) return Optional.empty();
        return Optional.of(new OrderResponse(o.getId(), o.getStatus(), o.getTotal()));
    }

    public OrderResponse create(CreateOrderRequest req) {
        if (req.getItems() == null || req.getItems().isEmpty()) {
            throw new IllegalArgumentException("items required");
        }
        Order saved = orderRepo.save(toEntity(req));
        return toResponse(saved);
    }

    private Order toEntity(CreateOrderRequest req) { ... }
    private OrderResponse toResponse(Order o) { ... }
}
```

```kotlin
// Kotlin (after)
@Service
class OrderService(
    private val orderRepo: OrderRepository,   // constructor injection via primary constructor; no @RequiredArgsConstructor
) {
    fun findOrder(id: Long): OrderResponse? =      // T? not Optional<T>
        orderRepo.findByIdOrNull(id)?.toResponse()  // Spring Data Kotlin extension; ?. chains the null path

    fun create(req: CreateOrderRequest): OrderResponse {
        require(req.items.isNotEmpty()) { "items required" }   // require() over manual throw
        return orderRepo.save(req.toEntity()).toResponse()     // extension functions, no helper class
    }
}

// Extension functions live alongside the service or in a Mappers.kt file
private fun CreateOrderRequest.toEntity() = Order(userId = userId, status = OrderStatus.PENDING)
private fun Order.toResponse() = OrderResponse(id, status, total)
```

What changed: `Optional<T>` → `T?`, `findById().orElse(null)` → `findByIdOrNull(...)`, manual null/throw → `require`, mapper helper methods → extension functions, `@RequiredArgsConstructor` → primary constructor with `val` params. Each substitution is detailed in the sections below.

### Gradle Plugin Configuration (Required for JPA)

Kotlin classes are `final` by default and have no no-arg constructors. JPA and Spring require both. These plugins fix it at compile time:

```kotlin
// build.gradle.kts
plugins {
    kotlin("plugin.spring") version "..."   // opens @Component, @Service, @Configuration, etc.
    kotlin("plugin.jpa") version "..."      // generates no-arg constructors for @Entity, @Embeddable, @MappedSuperclass
}

// Optional: extend allopen for custom annotations
allOpen {
    annotation("jakarta.persistence.Entity")
    annotation("jakarta.persistence.MappedSuperclass")
    annotation("jakarta.persistence.Embeddable")
}
```

Without `kotlin-jpa`: `org.hibernate.InstantiationException: No default constructor for entity`
Without `kotlin-spring`: `BeanNotOfRequiredTypeException` or `could not initialize proxy` on `@Transactional` classes

### Data Class for DTOs (not JPA entities)

```kotlin
// Good: data class for request/response DTOs
data class CreateOrderRequest(
    val userId: Long,
    val items: List<OrderItemRequest>,
    val shippingAddress: String,
)

data class OrderResponse(
    val id: Long,
    val status: OrderStatus,
    val total: BigDecimal,
    val createdAt: Instant,
)

// Bad: data class for JPA entity - Hibernate proxies don't work with equals/hashCode on all fields
@Entity
data class Order( // avoid - use regular class
    @Id @GeneratedValue val id: Long = 0,
    val userId: Long,
    var status: OrderStatus,
)

// Good: regular class for JPA entity with ID-based equals/hashCode
@Entity
class Order(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,
    val userId: Long,
    var status: OrderStatus = OrderStatus.PENDING,
    @Column(updatable = false)
    val createdAt: Instant = Instant.now(),
) {
    override fun equals(other: Any?) = other is Order && id != 0L && id == other.id
    override fun hashCode() = id.hashCode()
}
```

### ConfigurationProperties with Data Class

```kotlin
// Good: type-safe configuration binding
@ConfigurationProperties(prefix = "app.orders")
data class OrderProperties(
    val maxItemsPerOrder: Int = 50,
    val defaultCurrency: String = "USD",
    val expirationHours: Long = 24,
    val retry: RetryProperties = RetryProperties(),
) {
    data class RetryProperties(
        val maxAttempts: Int = 3,
        val delayMs: Long = 1000,
    )
}

// Bad: Java-style mutable config class
@ConfigurationProperties(prefix = "app.orders")
class OrderProperties {
    var maxItemsPerOrder: Int = 50  // unnecessary mutability
    var defaultCurrency: String = "USD"
}
```

### Null Safety

```kotlin
// Use T? instead of Optional<T>
fun findUser(id: Long): User?  // clear, idiomatic Kotlin
fun findUser(id: Long): Optional<User>  // Java-ism, avoid in Kotlin

// Safe call (?.) - returns null if receiver is null
val name = user?.profile?.displayName

// Elvis operator (?:) - provide a default when null
val name = user?.name ?: "Anonymous"

// Let for transforming nullable values
val email = user?.email?.let { it.lowercase().trim() }

// !! only when null is a bug (crashes with NullPointerException)
val config = System.getenv("DATABASE_URL")
    ?: error("DATABASE_URL must be set") // prefer error() over !!
```

### Preconditions: require / check / error

Replace Java `if (x == null) throw new IllegalArgumentException(...)` boilerplate with stdlib precondition functions. They convey intent and produce smart-cast non-null types after the check.

```kotlin
fun createOrder(req: CreateOrderRequest, userId: Long?): Order {
    require(req.items.isNotEmpty()) { "Order must have at least one item" }   // IllegalArgumentException
    require(req.items.size <= 50)   { "Too many items: ${req.items.size}" }
    val uid = checkNotNull(userId)  { "userId must be set on this code path" } // IllegalStateException; uid is Long
    check(req.total > BigDecimal.ZERO) { "Total must be positive" }            // IllegalStateException for invariants
    ...
}
```

- `require` - argument validation (caller's fault) → `IllegalArgumentException`
- `check` / `checkNotNull` - internal invariants (our fault) → `IllegalStateException`
- `error(msg)` - unreachable / unrecoverable state → `IllegalStateException`

Use lazy message lambdas (`{ "..." }`) so string interpolation only runs on failure.

### Named Arguments (Replace Builders)

Kotlin's named + default arguments replace Lombok `@Builder` and Java telescoping constructors. No builder class needed.

```kotlin
// Good: named args at call site - readable, refactor-safe, no builder boilerplate
val req = CreateOrderRequest(
    userId = currentUser.id,
    items = listOf(item),
    shippingAddress = "123 Main St",
    couponCode = null,
    expressShipping = true,
)

// Constructor with defaults supports partial specification at call site
data class PageRequest(
    val page: Int = 0,
    val size: Int = 20,
    val sort: String = "createdAt,desc",
)
val firstPage = PageRequest()                 // all defaults
val small = PageRequest(size = 5)             // override one
val sorted = PageRequest(sort = "id,asc")     // skip middle args by name

// Bad: Java-style builder ported to Kotlin - unnecessary in Kotlin
CreateOrderRequest.builder()
    .userId(currentUser.id)
    .items(listOf(item))
    .build()
```

### Scope Functions

| Function | Receiver | Return        | Use For                               |
| -------- | -------- | ------------- | ------------------------------------- |
| `let`    | `it`     | Lambda result | Null-safe transforms, local scope     |
| `apply`  | `this`   | Object itself | Object configuration (builder-style)  |
| `run`    | `this`   | Lambda result | Computing a value from object context |
| `also`   | `it`     | Object itself | Side effects (logging, events)        |
| `with`   | `this`   | Lambda result | Multiple operations on same object    |

```kotlin
// let - transform a nullable value or create a local scope
val result = order?.let { o ->
    processOrder(o)
    o.toResponse()
}

// apply - configure an object and return it (builder-style)
val request = HttpEntity<CreateOrderRequest>(body).apply {
    headers.setBearerAuth(token)
    headers.contentType = MediaType.APPLICATION_JSON
}

// run - compute a value using an object's context
val isValid = order.run {
    status != OrderStatus.CANCELLED && total > BigDecimal.ZERO
}

// also - perform a side effect and return the original object
val order = repo.save(newOrder)
    .also { log.info("Order created: id={}", it.id) }
    .also { eventPublisher.publish(OrderCreatedEvent(it.id)) }

// with - multiple operations on the same object, returns the lambda result
val summary = with(order) {
    "Order #$id by user $userId for $total"
}
```

### Sealed Classes for Error Hierarchies

```kotlin
sealed class OrderError {
    data class NotFound(val orderId: Long) : OrderError()
    data class ValidationFailed(val errors: List<String>) : OrderError()
    data class InsufficientStock(val itemId: Long, val available: Int) : OrderError()
    data object Unauthorized : OrderError()
}

// Exhaustive when - compiler enforces all cases are handled
fun handleError(error: OrderError): ResponseEntity<*> = when (error) {
    is OrderError.NotFound -> ResponseEntity.status(404).body(mapOf("error" to "Order ${error.orderId} not found"))
    is OrderError.ValidationFailed -> ResponseEntity.badRequest().body(error.errors)
    is OrderError.InsufficientStock -> ResponseEntity.status(409).body("Item ${error.itemId}: only ${error.available} available")
    is OrderError.Unauthorized -> ResponseEntity.status(403).build<Unit>()
}

// Sealed interface for result types (Kotlin 1.5+)
sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Failure(val error: OrderError) : ApiResult<Nothing>
}
```

### Inline Value Classes for Type Safety

Prevent passing the wrong ID or primitive to a function:

```kotlin
@JvmInline
value class OrderId(val value: Long)

@JvmInline
value class UserId(val value: Long)

// Now these are type-safe - compiler prevents mixing them up
fun getOrder(orderId: OrderId): Order
fun getUser(userId: UserId): User

// Bad: both are Long - easy to swap by accident
fun getOrder(orderId: Long): Order
fun getUser(userId: Long): User
```

### Extension Functions for Domain Operations

```kotlin
// Good: extension functions for entity mapping and domain logic
fun Order.toResponse() = OrderResponse(
    id = id,
    status = status,
    total = total,
    createdAt = createdAt,
)

fun CreateOrderRequest.toEntity() = Order(
    userId = userId,
    status = OrderStatus.PENDING,
)

// Good: extension functions on collections for domain-specific operations
fun List<Order>.totalRevenue(): BigDecimal = sumOf { it.total }
fun List<Order>.activeOnly(): List<Order> = filter { it.status == OrderStatus.ACTIVE }

// Bad: utility class with static methods (Java-ism)
class OrderUtils {
    companion object {
        @JvmStatic
        fun toResponse(order: Order) = OrderResponse(...)  // use extension function instead
    }
}
```

### `companion object` and `object` (Replace Java `static` and Singletons)

Kotlin has no `static` keyword. Java `static` members go in a `companion object`; Java singletons (private constructor + `INSTANCE`) become a top-level `object`.

```kotlin
// Java static -> Kotlin companion object
class Order(val id: Long, val total: BigDecimal) {
    companion object {
        const val MAX_ITEMS = 50                      // compile-time constant (like Java public static final)
        fun empty(userId: Long) = Order(id = 0, ...)  // factory function - call as Order.empty(uid)
    }
}

// Java singleton -> Kotlin object
object OrderIdGenerator {
    private val seq = AtomicLong()
    fun next(): Long = seq.incrementAndGet()
}
// Call as OrderIdGenerator.next() - no .INSTANCE, no getInstance()
```

Use `const val` for compile-time constants; use plain `val` inside `companion object` for anything computed.

### Use-Site Annotation Targets (`@field:`, `@get:`, `@param:`)

Kotlin properties expand to a backing field, getter, setter, and constructor parameter. Annotations like `@NotBlank`, `@Column`, `@JsonProperty` may need an explicit target so they land on the right element. Without a target Kotlin picks a default that often isn't what frameworks expect.

```kotlin
data class CreateUserRequest(
    @field:NotBlank                          // target the backing field for Bean Validation
    @field:Size(min = 3, max = 50)
    val username: String,

    @field:Email
    val email: String,

    @get:JsonProperty("created_at")          // target the getter for Jackson
    val createdAt: Instant,
)

@Entity
class User(
    @Id @GeneratedValue
    val id: Long = 0,

    @Column(name = "user_name", nullable = false, length = 50)  // JPA annotations on val parameter target the field by default
    val username: String,
)
```

Common targets: `@field:` (backing field), `@get:` / `@set:` (accessors), `@param:` (constructor param), `@property:` (the property itself). When validation or JSON annotations seem to be ignored at runtime, the missing use-site target is almost always why.

### Kotlin-Java Interop Annotations

Use these when Kotlin code must be consumed by Java code or Spring framework internals:

```kotlin
// @JvmStatic: allows Java to call companion object functions without .Companion
class OrderStatus {
    companion object {
        @JvmStatic
        fun fromCode(code: String): OrderStatus = ...
    }
}

// @JvmField: exposes a property as a public field (no getter/setter) - useful for constants
class ApiConstants {
    companion object {
        @JvmField val DEFAULT_PAGE_SIZE = 20
        @JvmField val MAX_PAGE_SIZE = 100
    }
}

// @JvmOverloads: generates Java-compatible overloads for functions with default params
class PaginationRequest @JvmOverloads constructor(
    val page: Int = 1,
    val size: Int = 20,
    val sort: String = "createdAt",
)
```

### Collection Operations

```kotlin
val orders: List<Order> = repo.findAll()

// Prefer Kotlin stdlib over Java streams
val activeOrders = orders.filter { it.status == OrderStatus.ACTIVE }
val totals = orders.map { it.total }
val byUser = orders.groupBy { it.userId }
val total = orders.sumOf { it.total }
val topOrder = orders.maxByOrNull { it.total }

// Sequence for lazy evaluation of large collections
val result = orders.asSequence()
    .filter { it.total > BigDecimal("100") }
    .map { it.toSummary() }
    .take(10)
    .toList()
```

## Edge Cases

**Kotlin JPA plugin missing**: If you see `No default constructor for entity` or `Entity class is final`, the fix is Gradle plugin configuration (see Patterns above), not manual `open` modifiers or empty constructors.

**Data class copy() with JPA**: Even for DTOs, `copy()` is a shallow copy. The new instance shares the same list reference as the original. Deep-copy mutable collections explicitly when needed.

**Inline value classes with Jackson**: Jackson requires the `jackson-module-kotlin` module and may need `@JsonCreator` or `@JvmInline` to serialize/deserialize inline value classes correctly. Test serialization round-trips when introducing value classes to API boundaries.

**Kotlin nullable types from Java code**: Java methods without nullability annotations (`@Nullable`, `@NonNull`) return platform types (`T!`). Treat these as nullable at call sites to avoid runtime `NullPointerException`:

```kotlin
// Java library returns String! (platform type)
val name: String = javaService.getName() // compiles but crashes if null
val name: String? = javaService.getName() // safe - forces null handling
```

**Sealed class exhaustiveness with `when`**: If you use `when` as a statement (not expression), the compiler does NOT enforce exhaustiveness. Always assign the `when` result to a variable or use it as a return value to get compile-time safety.

**Spring `@Value` injection**: Use `@Value("\${property.name}")` (escaped dollar sign in Kotlin) or prefer `@ConfigurationProperties` data classes for type-safe, refactoring-friendly configuration.

## Output Format

```
## Kotlin Idiom Review

### Gradle Plugins
- [ ] `kotlin-jpa` configured: {yes | no | not applicable}
- [ ] `kotlin-spring` (allopen) configured: {yes | no | not applicable}

### Conversions Applied
| Java Pattern | Kotlin Idiom | Files Changed |
|--------------|--------------|---------------|
| Optional<T> | T? | {list} |
| @Data DTO | data class | {list} |
| @Data Entity | class + equals/hashCode | {list} |
| Java streams | Kotlin stdlib | {list} |
| Lombok builder | named arguments + defaults | {list} |
| Utility class | Extension functions | {list} |
| static field/method | companion object / const val | {list} |
| Singleton | object | {list} |
| if/throw guard | require / check / checkNotNull | {list} |
| Bean Validation on entity | @field: targets on val params | {list} |

### Null Safety
- Platform types (T!) treated as nullable at call sites: {yes | no}
- !! usage: {count, each justified}

### Warnings
- {any edge cases encountered}
```

## Avoid

- `Optional<T>` - use Kotlin nullable types
- `data class` for JPA entities
- `!!` for expected null cases - use `?: error(...)` or handle the null path
- Java streams - use Kotlin stdlib collection operations
- Java-style getters/setters - use Kotlin properties
- Nested scope functions beyond 2 levels deep - extract to named functions instead
- Manual `open` on JPA entities or Spring beans - use `kotlin-spring` and `kotlin-jpa` plugins
- Utility classes with static methods - use extension functions; for static-like state use `companion object` or `object`
- Lombok `@Builder` ports - use named arguments and default parameter values
- Manual `if (x == null) throw ...` - use `require` / `check` / `checkNotNull`
- `@Value` for complex configuration - use `@ConfigurationProperties` data classes
- Bean Validation / Jackson annotations without a use-site target on `data class` properties when the framework appears to ignore them - add `@field:` or `@get:`
