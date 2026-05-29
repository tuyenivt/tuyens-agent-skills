---
name: kotlin-overengineering-review
description: Kotlin/Spring necessity review: Bean Validation duplicating JPA/DB + non-null types, defensive ?.let/!!/requireNotNull on guarantees, single-impl interfaces.
metadata:
  category: backend
  tags: [kotlin, spring-boot, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Composes with `kotlin-idioms` for canonical `!!` / `Optional` / scope-function rules - this skill flags **redundant** uses; the other defines idiomatic use.

## When to Use

- Reviewing a Kotlin / Spring Boot diff adding validation, defensive guards, service interfaces, or new abstractions
- Phase D of `task-kotlin-review`: catching code that is correct but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK, `nullable = false`, unique index, Kotlin non-null type, DTO Bean Validation, framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** with measurable cost: extra SELECT on hot path, blanket catch masking real bugs, `!!` after `requireNotNull` (two checks where zero suffices), controller try/catch defeating `@RestControllerAdvice`, `data class` JPA annotation pattern fighting Hibernate. Cite cost in `Cost:`.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. Classic exceptions:
  - Entity `@field:NotNull` when a non-controller write path (Kafka consumer, scheduled job) bypasses the DTO - defense in depth.
  - `lateinit` / `requireNotNull` on a platform type (`T!`) from a Java collaborator, or on a field set by `@PostConstruct`.
  - Interface with one impl + an `@Aspect` matching the interface, a non-MockK test seam, or a second implementation in the same diff.

## Patterns

### Category 1: Redundant validation vs JPA / DB / Kotlin non-null types

Kotlin adds a fourth layer to validation: the type. A non-null Kotlin parameter is non-null at compile time, and Jackson refuses `null` for one. Full stack: **Kotlin type → DTO Bean Validation → JPA `@Column` → DB constraint.** DTO Bean Validation produces useful client errors; keep it. Entity annotations are redundant when the DTO is the sole write path.

```kotlin
// Bad - four overlapping guarantees on a non-null type
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
@field:NotNull                                     // redundant
val user: User,

// Good
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
val user: User,
```

```kotlin
// Bad - the type already forces Jackson to fail on null
data class CreateOrderRequest(
    @field:NotNull val customerId: Long,
    @field:NotNull val items: List<OrderItem>,
)

// Good - keep shape constraints, drop @NotNull on non-null types
data class CreateOrderRequest(
    val customerId: Long,
    @field:Size(max = 5) val items: List<OrderItem>,
)
```

`@field:Size`, `@field:Pattern`, `@field:Min` are still useful. Keep `@field:NotNull` only on `T?` fields where the type allows null but business rules don't.

#### Manual unique-check before save

`[High]` - races + extra SELECT per write; the unique index decides anyway.

```kotlin
// Bad
if (userRepository.existsByEmail(req.email)) throw DuplicateEmailException()

// Good
try { userRepository.save(User(req)) }
catch (e: DataIntegrityViolationException) { throw DuplicateEmailException(cause = e) }
```

### Category 2: Defensive code for impossible states

```kotlin
// Bad - order is non-null
order?.let { it.status = PROCESSING }

// Good
order.status = PROCESSING
```

```kotlin
// Bad - primitive Long is non-nullable
fun fulfill(orderId: Long) { requireNotNull(orderId); ... }
```

Legitimate on platform types (`T!` from Java) and `lateinit` fields read before injection completes.

#### `!!` after `requireNotNull` or smart-cast

`[High]` - two checks where zero suffices, the redundant `!!` throws first with a worse message.

```kotlin
// Bad
val token = requireNotNull(request.getHeader("Authorization")) { "missing auth" }
parse(token!!)
```

#### Blanket `catch (e: Exception)`

`[High]`. Swallows `IllegalStateException`, `DataAccessException`, etc. In a controller also defeats `@RestControllerAdvice` status mapping.

```kotlin
// Bad
try { service.fulfill(orderId) }
catch (e: Exception) { Result.failure("something went wrong") }

// Good
try { service.fulfill(orderId) }
catch (e: InsufficientStockException) { Result.failure(e.message) }
catch (e: PaymentDeclinedException) { Result.failure(e.message) }
```

#### `Optional<T>` in pure Kotlin

```kotlin
// Bad
fun findOrder(id: Long): Optional<OrderResponse> = repo.findById(id).map { it.toResponse() }

// Good
fun findOrder(id: Long): OrderResponse? = repo.findByIdOrNull(id)?.toResponse()
```

`Optional<List<T>>` is doubly redundant - empty list already encodes "absent". Return `List<T>` (possibly `emptyList()`).

### Category 3: Premature abstraction

#### Single-impl `@Service` interface

`[High]` - MockK mocks final classes; CGLIB proxies concrete classes; the interface earns nothing.

```kotlin
// Bad
interface OrderService { fun fulfill(orderId: Long): OrderResponse }
@Service class OrderServiceImpl(...) : OrderService

// Good
@Service class OrderService(...) { fun fulfill(orderId: Long): OrderResponse = ... }
```

#### `BaseService<T, ID>` for one or two services

Inline. Revisit when 3+ services share real cross-cutting behavior.

#### Custom `Result<T>` when a sealed class or domain exception suffices

```kotlin
// Bad
fun findOrder(id: Long): Result<Order> =
    repo.findByIdOrNull(id)?.let { Result.success(it) } ?: Result.failure("not found")

// Good - nullable for "not found"; sealed for multi-branch
fun findOrder(id: Long): Order? = repo.findByIdOrNull(id)
```

Sealed-class result is the right tool when callers programmatically branch on distinct failures.

#### Sealed class with one variant

```kotlin
// Bad
sealed class OrderEvent { data class Placed(val orderId: Long) : OrderEvent() }

// Good - skip the wrapper until a second variant lands
data class OrderPlacedEvent(val orderId: Long)
```

#### Speculative `@ConfigurationProperties` keys

Flag after a repo-wide search confirms no readers.

#### Scope-function nesting beyond 2 levels

```kotlin
// Bad
user?.let { u -> u.address?.let { addr -> addr.country?.let { c -> shipper.send(u, addr, c) } } }

// Good
val country = user?.address?.country ?: return
shipper.send(user, user.address, country)
```

## Output Format

```
### [Suggestion | High | Question] file:line
- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation}
- Redundant because: {constraints making it redundant}
- Cost: {...}   _(required for [High])_
- Recommendation: {concrete edit}
- Justified when: {...}   _([Question] or unverified cases only)_
```

For each of the three categories with no findings, emit `No <category> findings.`

## Avoid

- Flagging Bean Validation on `?`-typed DTO fields with shape constraints - only `@field:NotNull` on non-null types is redundant
- Flagging entity `@field:NotNull` without checking for non-controller write paths
- Flagging `!!` / `requireNotNull` on `lateinit`, platform types, or `@PostConstruct`-initialized fields
- Flagging a single-impl interface before checking for a second impl, `@Aspect`, non-MockK seam, or springmockk substitution
- Emitting a finding when justification is visible in the diff - skip it
