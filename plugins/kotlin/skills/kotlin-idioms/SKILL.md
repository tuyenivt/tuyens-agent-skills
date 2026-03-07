---
name: kotlin-idioms
description: "Kotlin idioms for Spring Boot: data classes, null safety, extension functions, scope functions (let/apply/run/also), sealed classes, inline value classes, and Kotlin-Java interop patterns."
user-invocable: false
---

# Kotlin Idioms for Spring Boot

## When to Use

- Writing DTOs, domain models, or error hierarchies in a Kotlin + Spring Boot project
- Reviewing Kotlin code for Java-isms (Optional, getters/setters, streams)
- Designing type-safe wrappers for IDs and primitive value types
- Working with nullable types from Java libraries or JPA entities

## Rules

- Use `data class` for DTOs and value objects; use regular `class` for JPA entities (`data class` and JPA proxies are incompatible)
- Use `T?` instead of `Optional<T>` - Kotlin null safety is more expressive and idiomatic
- Use `!!` only when a null value is a programmer bug and you want an immediate crash - never for business logic
- Use Kotlin stdlib collection operations (`map`, `filter`, `groupBy`) instead of Java streams
- Use `@JvmStatic`, `@JvmField`, `@JvmOverloads` when Kotlin code must be called from Java or Spring frameworks

## Patterns

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

// Bad: data class for JPA entity - Hibernate proxies don't work well with equals/hashCode based on all fields
@Entity
data class Order( // avoid - use regular class
    @Id @GeneratedValue val id: Long = 0,
    val userId: Long,
    var status: OrderStatus,
)

// Good: regular class for JPA entity
@Entity
class Order(
    @Id @GeneratedValue val id: Long = 0,
    val userId: Long,
    var status: OrderStatus = OrderStatus.PENDING,
) {
    override fun equals(other: Any?) = other is Order && id == other.id
    override fun hashCode() = id.hashCode()
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

### Scope Functions

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
```

### Sealed Classes for Error Hierarchies

```kotlin
sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class NotFound(val message: String) : ApiResult<Nothing>()
    data class ValidationError(val errors: List<String>) : ApiResult<Nothing>()
    data class InternalError(val cause: Throwable) : ApiResult<Nothing>()
}

// Exhaustive when - compiler enforces all cases are handled
fun handleResult(result: ApiResult<Order>): ResponseEntity<*> = when (result) {
    is ApiResult.Success -> ResponseEntity.ok(result.data)
    is ApiResult.NotFound -> ResponseEntity.notFound().build<Unit>()
    is ApiResult.ValidationError -> ResponseEntity.badRequest().body(result.errors)
    is ApiResult.InternalError -> ResponseEntity.internalServerError().build<Unit>()
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

### Kotlin-Java Interop Annotations

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

## Avoid

- `Optional<T>` - use Kotlin nullable types
- `data class` for JPA entities
- `!!` for expected null cases - use `?: error(...)` or handle the null path
- Java streams - use Kotlin stdlib collection operations
- Java-style getters/setters - use Kotlin properties
- Nested scope functions without a clear reason for each level
