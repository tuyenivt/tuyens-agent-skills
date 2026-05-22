---
name: spring-overengineering-review
description: "Spring necessity review: Bean Validation duplicating JPA/DB, defensive guards on framework guarantees, single-impl interfaces."
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

- Every finding cites the constraint that makes the code redundant: FK, `nullable = false`, unique index, `@Column` attribute, DTO Bean Validation, or framework guarantee
- Severity:
  - **`[Suggestion]`** default - cite the constraint, recommend the edit
  - **`[High]`** when a measurable cost is present: extra SELECT in a hot path, blanket catch masking real bugs, `@Service` interface forcing every refactor to touch two files, controller try/catch defeating `@RestControllerAdvice` status mapping, defensive `equals`/`hashCode` breaking Hibernate proxies. Cite cost in `Cost:` field.
  - **`[Question]`** when justification is plausible but not visible (e.g., "is this `@NotNull` needed because a Kafka consumer bypasses the DTO?")
- Skip findings when justification is visible in the diff (non-controller write path bypassing the DTO is defense-in-depth, not duplication)

## Patterns

### Category 1 - Redundant validation vs JPA / DB

DTO validation owns user-facing errors; entity-level annotations fire only on flush. Flag entity validations when the DTO is the sole write path AND the JPA/DB constraint already enforces the rule.

```java
// Bad - three layers checking the same rule
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
@NotNull   // redundant
private User user;

// Good - constraint at the layer that owns it
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
private User user;
```

```java
// Bad - DTO already validates email shape
@Email @Size(max = 255) @Column(length = 255, nullable = false)
private String email;

// Good
@Column(length = 255, nullable = false)
private String email;
```

**Manual unique-check before save** - `[High]`. Races (concurrent SELECTs both pass) and the unique index rejects anyway. Extra SELECT per write.

```java
// Bad
if (userRepository.existsByEmail(req.email())) throw new DuplicateEmailException();
userRepository.save(new User(req));

// Good - unique index "uk_users_email" is authoritative
try { return userRepository.save(new User(req)); }
catch (DataIntegrityViolationException e) { throw new DuplicateEmailException(e); }
```

Justified only when no unique index exists - in which case recommend adding the index.

### Category 2 - Defensive code for impossible states

Spring guarantees non-null for `@Autowired` beans, `@Valid @NotNull` fields, and the principal inside `@PreAuthorize`'d methods. Re-checking those guarantees adds noise and hides regressions that should crash loudly.

```java
// Bad - @Valid + @NotNull already returned 400
@PostMapping
ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest req) {
    Objects.requireNonNull(req.customerId());
    ...
}
```

```java
// Bad - imperative shape hides the failure path
if (maybe.isPresent()) return toResponse(maybe.get());
throw new EntityNotFoundException("order " + id);

// Good
return orderRepository.findById(id)
    .map(this::toResponse)
    .orElseThrow(() -> new EntityNotFoundException("order " + id));
```

**Blanket `catch (Exception)`** - `[High]`. Swallows real bugs (`NPE`, `DataIntegrityViolationException`); in controllers, erases status-code mapping (`EntityNotFoundException` → 404 becomes opaque 500).

```java
// Bad
try { return service.fulfill(orderId); }
catch (Exception e) { log.error("fulfillment failed", e); return Result.failure("something went wrong"); }

// Good - name the failures the call can actually raise
try { return service.fulfill(orderId); }
catch (InsufficientStockException | PaymentDeclinedException e) { return Result.failure(e.getMessage()); }
```

**Catch-and-rethrow with no transformation** - if the intent is HTTP status mapping, that belongs in `@RestControllerAdvice`.

### Category 3 - Premature abstraction

**`@Service` interface with one implementation** - `[High]`. Every refactor touches two files. Mockito mocks classes via CGLIB; Spring proxies concrete classes by default.

```java
// Bad
public interface OrderService { OrderResponse fulfill(Long orderId); }
@Service public class OrderServiceImpl implements OrderService { ... }

// Good
@Service public class OrderService { ... }
```

Justified when a second implementation, an `@Aspect` with a JDK-proxy pointcut, or a non-Mockito test seam requires the interface.

**`BaseService<T>` with one or two subclasses** - generics propagation for 3 saved lines.

```java
// Bad
public abstract class BaseService<T, ID> {
    protected abstract JpaRepository<T, ID> repo();
    public T findOne(ID id) { return repo().findById(id).orElseThrow(); }
}
```

Abstract only when 3+ services share real cross-cutting behavior (audit, metrics).

**`Result<T>` wrapping a trivial read** - keep `Optional` unless callers branch on multiple distinct failure modes.

```java
// Bad
public Result<Order> findOrder(Long id) {
    return orderRepository.findById(id).map(Result::success).orElseGet(() -> Result.failure("not found"));
}

// Good
public Optional<Order> findOrder(Long id) { return orderRepository.findById(id); }
```

**Speculative `@ConfigurationProperties` keys** - flag fields declared and validated but never read anywhere in the repo (confirm with a repo-wide search).

**Custom mapper layer when one transformation would do** - prefer a MapStruct interface or `OrderResponse.from(Order)` static factory over three mapper classes.

## Output Format

One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `@NotNull` on `Order.user`}
- Redundant because: {constraints: FK, `nullable = false`, unique index, DTO `@NotNull`, framework guarantee}
- Cost: {extra SELECT | masked exception | speculative surface | proxy mismatch} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if `[Question]` or plausible reason; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the workflow sees the check ran.

## Avoid

- Flagging Bean Validation on a DTO consumed by `@Valid` - that layer owns user-facing errors
- Flagging an entity `@NotNull` without checking for a non-controller write path (Kafka consumer, scheduled job, admin tool)
- Recommending removal of a unique pre-check without confirming a unique index exists
- Flagging a `@Service` interface before checking for a second impl, `@Aspect`, or test seam
- Emitting a finding when justification is visible in the diff
