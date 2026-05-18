---
name: kotlin-overengineering-review
description: Kotlin/Spring necessity review: Bean Validation duplicating JPA/DB + non-null types, defensive ?.let/!!/requireNotNull on guarantees, single-impl interfaces.
metadata:
  category: backend
  tags: [kotlin, spring-boot, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Composes with `kotlin-idioms` for canonical `!!` / `Optional` / scope-function rules - this skill flags **redundant** uses, the other defines idiomatic use.

## When to Use

- Reviewing a Kotlin + Spring Boot diff that adds validation annotations, defensive null guards, service interfaces, or new abstractions
- Phase D of `task-kotlin-review`: catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK, `nullable = false`, unique index, Kotlin non-null type, DTO Bean Validation, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** with a measurable cost: extra SELECT in a hot path, blanket catch masking real bugs, `!!` after `requireNotNull` (two checks where zero suffices), controller try/catch defeating `@RestControllerAdvice` status mapping, or a `data class` JPA annotation pattern fighting Hibernate. Cite the cost in the `Cost:` field.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. Skip it. Classic cases:
  - Entity `@field:NotNull` when a non-controller write path (Kafka consumer, scheduled job) bypasses the DTO - defense in depth.
  - `lateinit` / `requireNotNull` on a platform type (`T!`) from a Java collaborator, or on a field set by `@PostConstruct` - legitimate fail-fast.
  - Interface with one impl + an `@Aspect` matching the interface, a non-MockK test seam, or a second implementation already in the same diff.

## Patterns

### Category 1: Redundant validation vs JPA / DB / Kotlin non-null types

Kotlin adds a fourth layer to validation: the type. A non-null Kotlin parameter is non-null at compile time, and Jackson refuses to deserialize `null` into one. The full stack: **Kotlin type → DTO Bean Validation → JPA `@Column` → DB constraint.** DTO Bean Validation is the layer that produces useful client error messages; keep it. Entity annotations are redundant when the DTO is the sole write path.

#### `@field:NotNull` on a non-null entity field

```kotlin
// Bad - four overlapping guarantees
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
@field:NotNull                                       // redundant on a non-null type
val user: User,

// Good
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
val user: User,
```

#### `@field:NotNull` on a non-null DTO field

```kotlin
// Bad - the type forces Jackson to fail on null; @NotNull is dead
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

Keep Bean Validation for constraints **beyond** nullability (`@field:Size`, `@field:Pattern`, `@field:Min`), and on `?`-typed fields where the type allows null but a business rule does not.

#### Manual unique-check before save

`[High]` - races and runs an extra SELECT per write; the unique index decides anyway.

```kotlin
// Bad
if (userRepository.existsByEmail(req.email)) throw DuplicateEmailException()

// Good
try { userRepository.save(User(req)) }
catch (e: DataIntegrityViolationException) { throw DuplicateEmailException(cause = e) }
```

### Category 2: Defensive code for impossible states

Kotlin's null-safety, `@Valid`, and Spring's framework contracts overlap. Re-checking what one already proved is dead code at best and masks regressions at worst.

#### `?.let` on a non-null receiver

```kotlin
// Bad - order is non-null; ?. never short-circuits
order?.let { it.status = Status.PROCESSING }

// Good
order.status = Status.PROCESSING
```

#### `requireNotNull` on an already-non-null parameter

```kotlin
// Bad - primitive Long is non-nullable
fun fulfill(orderId: Long) { requireNotNull(orderId); ... }
```

Legitimate on platform types (`T!` from a Java collaborator) and on `lateinit` fields read before injection completes.

#### `!!` after `requireNotNull` or smart-cast

`[High]` - two checks where zero suffices, and the redundant `!!` will be the one that throws first (with a less useful message).

```kotlin
// Bad - requireNotNull already guarantees non-null for the rest of the block
val token = requireNotNull(request.getHeader("Authorization")) { "missing auth header" }
parse(token!!)
```

#### Blanket `catch (e: Exception)` - masks bugs and defeats `@RestControllerAdvice`

`[High]`. In a service, swallows `IllegalStateException`, `DataAccessException`, etc. In a controller, additionally erases status mapping (`EntityNotFoundException` -> 404 becomes opaque 500).

```kotlin
// Bad
try { service.fulfill(orderId) }
catch (e: Exception) { logger.error("failed", e); Result.failure("something went wrong") }

// Good - name the failures the call can raise; let the rest reach @RestControllerAdvice
try { service.fulfill(orderId) }
catch (e: InsufficientStockException) { Result.failure(e.message) }
catch (e: PaymentDeclinedException) { Result.failure(e.message) }
```

#### `Optional<T>` in pure Kotlin code

```kotlin
// Bad
fun findOrder(id: Long): Optional<OrderResponse> =
    orderRepository.findById(id).map { it.toResponse() }

// Good
fun findOrder(id: Long): OrderResponse? = orderRepository.findByIdOrNull(id)?.toResponse()
```

`Optional<List<T>>` is doubly redundant - the empty list already encodes "absent". Return `List<T>` (possibly `emptyList()`), not `Optional<List<T>>`. `Optional` is appropriate only at a Java-interop boundary where the caller is Java.

### Category 3: Premature abstraction

#### `@Service` interface with one Kotlin implementation

`[High]` - MockK mocks final classes; CGLIB proxies concrete classes; the interface earns nothing.

```kotlin
// Bad
interface OrderService { fun fulfill(orderId: Long): OrderResponse }
@Service class OrderServiceImpl(...) : OrderService { override fun fulfill(...) = ... }

// Good
@Service class OrderService(...) { fun fulfill(orderId: Long): OrderResponse = ... }
```

#### `BaseService<T, ID>` for one or two services

```kotlin
// Bad - template-method scaffold
abstract class BaseService<T, ID> {
    protected abstract fun repo(): JpaRepository<T, ID>
    fun findOne(id: ID): T = repo().findById(id).orElseThrow()
}

// Good - inline; revisit when 3+ services share real cross-cutting behavior (audit, metrics)
@Service
class OrderService(private val repo: OrderRepository) {
    fun findOne(id: Long): Order = repo.findByIdOrNull(id) ?: throw OrderNotFoundException(id)
}
```

#### Custom `Result<T>` where a sealed class or domain exception suffices

```kotlin
// Bad
fun findOrder(id: Long): Result<Order> =
    orderRepository.findByIdOrNull(id)?.let { Result.success(it) } ?: Result.failure("not found")

// Good - nullable for "not found"; sealed hierarchy when callers branch on multiple failure modes
fun findOrder(id: Long): Order? = orderRepository.findByIdOrNull(id)
```

A sealed-class result is the right tool when callers programmatically branch on distinct failure types (validation vs payment vs inventory). For a single "not found", the type system already encodes it.

#### Sealed class with one variant

```kotlin
// Bad
sealed class OrderEvent { data class Placed(val orderId: Long) : OrderEvent() }

// Good - skip the wrapper until a second variant lands in the same release
data class OrderPlacedEvent(val orderId: Long)
```

#### Speculative `@ConfigurationProperties` keys

```kotlin
// Bad - auditTopic / tracingEnabled declared, zero read sites repo-wide
data class TenantConfig(val name: String, val timeout: Duration, val auditTopic: String, val tracingEnabled: Boolean)
```

Flag only after a repo-wide search confirms no readers.

#### Scope-function nesting beyond 2 levels

```kotlin
// Bad
user?.let { u -> u.address?.let { addr -> addr.country?.let { c -> shipper.send(u, addr, c) } } }

// Good - fail fast on the precondition
val country = user?.address?.country ?: return
shipper.send(user, user.address, country)
```

See `kotlin-idioms` for the "max 2 levels" rule.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `@field:NotNull` on non-null `customerId`}
- Redundant because: {one or more constraints: FK, `nullable = false`, unique index, Kotlin non-null type, DTO `@NotNull`, framework guarantee}
- Cost: {extra SELECT | masked exception | speculative surface area | scope-nesting cognitive load} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a `[Question]` or when a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging Bean Validation on `?`-typed DTO fields with shape constraints (`@Size`, `@Pattern`) - only `@field:NotNull` on non-null types is redundant
- Flagging an entity `@field:NotNull` without checking for non-controller write paths
- Flagging `!!` / `requireNotNull` on `lateinit` reads, platform types, or `@PostConstruct`-initialized fields
- Flagging a single-impl interface before checking for a second impl, an `@Aspect`, a non-MockK test seam, or springmockk substitution
- Emitting a finding when justification is visible in the diff - skip it; `Justified when:` is for plausible-but-unverified cases
