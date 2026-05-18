---
name: spring-overengineering-review
description: Spring Boot necessity review: Bean Validation duplicating JPA/DB constraints, defensive Optional/null checks on @NotNull, single-impl interfaces, BaseService bloat.
metadata:
  category: backend
  tags: [java, spring-boot, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Spring Boot diff that adds validation annotations, defensive null checks, service interfaces, or new abstractions
- Phase D of `task-spring-review`: catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint that makes the code redundant: FK name, `nullable = false` column, unique index, `@Column` attribute, Bean Validation on the DTO, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present: extra SELECT in a hot path, blanket catch masking real bugs, `@Service` interface forcing every refactor to touch two files, controller try/catch that defeats `@RestControllerAdvice` status-code mapping, or defensive `equals`/`hashCode` breaking Hibernate proxies. Cite the cost in the `Cost:` field.
  - **`[Question]`** when justification is plausible but not visible in the diff (e.g., "is this `@NotNull` needed because a Kafka consumer bypasses the DTO?").
- A redundancy with **visible** justification is not a finding. Skip it. The classic case: DTO + entity + DB validation when a non-controller write path (Kafka consumer, scheduled job, admin tool) bypasses the DTO - that is defense in depth, not duplication.

## Patterns

### Category 1: Redundant validation vs JPA / DB constraints

Bean Validation runs in three places: the controller `@RequestBody @Valid DTO`, JPA `@Column`/`@JoinColumn`, and the DB schema. Entity-level annotations only fire on flush; if the DTO is the sole write path, they add nothing.

- **DTO validations** - keep; they produce `MethodArgumentNotValidException` with field errors for the client.
- **Entity validations** - flag when the DTO is the sole write path AND the JPA/DB constraint already enforces the rule.

#### `@NotNull` on an entity field already covered by JPA + DB

```java
// Bad - three layers checking the same rule; entity validation only fires at flush
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
@NotNull                                              // redundant
private User user;

// Good - constraint at the layer that owns it
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
private User user;
```

The DTO keeps its `@NotNull` so the controller returns 400 before the entity is constructed.

#### `@Size` / `@Pattern` on an entity duplicating the validated DTO

```java
// Bad
@Email @Size(max = 255) @Column(length = 255, nullable = false)
private String email;

// Good - DTO owns shape; entity column declares storage
@Column(length = 255, nullable = false)
private String email;
```

#### Manual unique-check before save

Races (two concurrent requests both pass the SELECT), and the unique index rejects the duplicate anyway. `[High]` - extra SELECT in a hot write path, and the pre-check does not actually guarantee uniqueness.

```java
// Bad
if (userRepository.existsByEmail(req.email())) throw new DuplicateEmailException();
userRepository.save(new User(req));

// Good - let the unique index decide
try {
    return userRepository.save(new User(req));
} catch (DataIntegrityViolationException e) {
    throw new DuplicateEmailException(e);  // unique index "uk_users_email" is authoritative
}
```

Justified only when no unique index exists - in which case the validation is the only barrier (still racy, but the only one); recommend adding the index.

### Category 2: Defensive code for impossible states

Spring guarantees non-null for `@Autowired` beans, `@Valid @NotNull` fields, and the authenticated principal inside a `@PreAuthorize`'d method. Re-checking those guarantees adds noise and can hide the regression that should crash loudly.

#### `Objects.requireNonNull` on an already-validated `@NotNull` field

```java
// Bad
@PostMapping
ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest req) {
    Objects.requireNonNull(req.customerId());      // @Valid + @NotNull already rejected null with 400
    ...
}
```

#### `Optional.isPresent()` + `.get()` instead of `.map` / `.orElseThrow`

```java
// Bad - imperative shape hides the failure path
if (maybe.isPresent()) return toResponse(maybe.get());
throw new EntityNotFoundException("order " + id);

// Good
return orderRepository.findById(id)
    .map(this::toResponse)
    .orElseThrow(() -> new EntityNotFoundException("order " + id));
```

#### Blanket `catch (Exception)` - masks real bugs and defeats `@RestControllerAdvice`

`[High]`. In a service, swallows `NullPointerException`, `DataIntegrityViolationException`, etc. In a controller, additionally erases status-code mapping that `@RestControllerAdvice` would apply (`EntityNotFoundException` -> 404, `DuplicateEmailException` -> 409 become opaque 500s).

```java
// Bad
try {
    return service.fulfill(orderId);
} catch (Exception e) {
    log.error("fulfillment failed", e);
    return Result.failure("something went wrong");
}

// Good - name the failures the call can actually raise; let the rest crash to @RestControllerAdvice
try {
    return service.fulfill(orderId);
} catch (InsufficientStockException | PaymentDeclinedException e) {
    return Result.failure(e.getMessage());
}
```

#### Catch-and-rethrow with no transformation

If the intent is HTTP status mapping, that belongs in `@RestControllerAdvice`, not every controller method.

```java
// Bad
try { return service.charge(orderId); } catch (PaymentDeclinedException e) { throw e; }
```

### Category 3: Premature abstraction

#### `@Service` interface with one implementation

`[High]` - every refactor touches two files for no behavioral reason. Mockito mocks classes via CGLIB; Spring Boot's default proxy mode also proxies concrete classes.

```java
// Bad
public interface OrderService { OrderResponse fulfill(Long orderId); }
@Service public class OrderServiceImpl implements OrderService { ... }

// Good
@Service public class OrderService { ... }
```

Justified when a second implementation, an `@Aspect` with a JDK-proxy pointcut (e.g., `execution(* OrderService+.fulfill(..))`), or a non-Mockito test seam requires the interface.

#### `BaseService<T>` with one or two subclasses

```java
// Bad - template-method scaffold; saves 3 lines at the cost of generics propagation
public abstract class BaseService<T, ID> {
    protected abstract JpaRepository<T, ID> repo();
    public T findOne(ID id) { return repo().findById(id).orElseThrow(); }
}

// Good - inline; abstract once 3+ services share real cross-cutting behavior (audit, metrics)
@Service
public class OrderService {
    private final OrderRepository repo;
    public Order findOne(Long id) { return repo.findById(id).orElseThrow(); }
}
```

#### Custom `Result<T>` wrapping a trivial read

```java
// Bad
public Result<Order> findOrder(Long id) {
    return orderRepository.findById(id).map(Result::success).orElseGet(() -> Result.failure("not found"));
}

// Good
public Optional<Order> findOrder(Long id) { return orderRepository.findById(id); }
```

Keep `Result<T>` when callers programmatically branch on multiple distinct failure modes (e.g., `InsufficientFunds` vs `Declined` vs `GatewayTimeout`), or when success and failure carry different payloads.

#### Speculative `@ConfigurationProperties` keys

```java
// Bad - audit and tracingTag are declared and validated, never read anywhere in the repo
@ConfigurationProperties("payments")
public record PaymentsConfig(String gatewayUrl, Duration timeout, boolean audit, String tracingTag) {}
```

Flag only after a repo-wide search confirms zero read sites.

#### Custom mapper layer when one transformation would do

```java
// Bad - three classes for one transformation
class OrderEntityToDomain { Order map(OrderEntity e) { ... } }
class OrderDomainToResponse { OrderResponse map(Order o) { ... } }
class OrderMapperConfig { ... }

// Good - one MapStruct interface OR one record static factory
@Mapper(componentModel = "spring")
public interface OrderMapper { OrderResponse toResponse(Order o); }
```

When MapStruct is not a dependency, prefer `OrderResponse.from(Order)` static factories over hand-written `@Component` mapper beans.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `@NotNull` on `Order.user`}
- Redundant because: {one or more constraints: FK, `nullable = false`, unique index, DTO `@NotNull`, framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | proxy mismatch} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a `[Question]` or when a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging Bean Validation on a DTO consumed by `@Valid` - that layer owns user-facing error messages
- Flagging an entity `@NotNull` without checking for a non-controller write path (Kafka consumer, scheduled job)
- Recommending removal of a unique-check without confirming a unique index exists
- Flagging a `@Service` interface before checking for a second impl, an `@Aspect`, or a non-Mockito test seam
- Emitting a finding when justification is visible in the diff - skip it; `Justified when:` is for plausible-but-unverified cases
