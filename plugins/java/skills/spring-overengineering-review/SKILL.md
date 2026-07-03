---
name: spring-overengineering-review
description: "Spring necessity review - flag Bean Validation duplicating JPA/DB, defensive guards on framework guarantees, single-impl interfaces."
metadata:
  category: backend
  tags: [java, spring-boot, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Spring Boot diff that adds validation annotations, defensive null checks, service interfaces, or new abstractions
- Phase D of `task-spring-review` - catching code that is correct, performant, and safe but does not need to exist

## Rules

- Cite the constraint that makes the code redundant: FK, `nullable = false`, unique index, DTO `@Valid` + `@NotNull`, `@RestControllerAdvice`, or framework guarantee. No citation, no finding.
- Intent:
  - `[Recommend]` - default; cite the constraint and recommend the edit. Escalate to `[Must]` when measurable cost is present (extra SELECT, masked exception, forced two-file refactor, broken proxy semantics) - record cost in `Cost:` field
  - `[Question]` - plausible justification not visible in the diff; ask before recommending removal
- Code matching multiple patterns (e.g., a blanket catch that also rethrows) gets one finding under the higher-intent pattern
- Skip when the diff shows justification (non-controller write path, second implementation, async consumer bypassing the DTO)

## Patterns

### Category 1 - Redundant validation vs JPA / DB

DTO validation owns user-facing errors; entity-level validation fires only on flush. Flag entity validations when the DTO is the sole write path AND a JPA/DB constraint already enforces the rule.

```java
// Bad - FK + nullable + @NotNull all assert the same thing
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
@NotNull
private User user;

// Good
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
private User user;
```

```java
// Bad - DTO already validates email shape and length
@Email @Size(max = 255) @Column(length = 255, nullable = false)
private String email;

// Good
@Column(length = 255, nullable = false)
private String email;
```

**Manual unique-check before save** - `[Must]`. Race-prone (two concurrent SELECTs both pass), and the unique index rejects anyway. Costs one extra SELECT per write.

```java
// Bad
if (userRepository.existsByEmail(req.email())) throw new DuplicateEmailException();
userRepository.save(new User(req));

// Good - unique index "uk_users_email" is authoritative
try { return userRepository.save(new User(req)); }
catch (DataIntegrityViolationException e) { throw new DuplicateEmailException(e); }
```

Justified only when no unique index exists - then recommend adding the index instead.

### Category 2 - Defensive Impossibility (guards on framework guarantees)

Spring guarantees non-null for injected dependencies (constructor or `@Autowired`), `@Valid @NotNull` request fields, and the principal inside `@PreAuthorize`'d methods. Re-checking them hides regressions that should crash loudly.

```java
// Bad - @Valid + @NotNull already returned 400 before this runs
ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest req) {
    Objects.requireNonNull(req.customerId());
    return ResponseEntity.ok(orderService.create(req.customerId()));
}

// Good - trust the validation layer
ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest req) {
    return ResponseEntity.ok(orderService.create(req.customerId()));
}
```

```java
// Bad - Optional.ofNullable on a field already constrained by @NotNull
Long id = Optional.ofNullable(req.customerId())
    .orElseThrow(() -> new IllegalArgumentException("required"));

// Good
Long id = req.customerId();
```

**Blanket `catch (Exception)` in a controller or service** - `[Must]`. Swallows `DataIntegrityViolationException`, `NullPointerException`, and domain exceptions; in controllers it erases `@RestControllerAdvice` status mapping (404/409 collapse to 500).

```java
// Bad
try { return service.fulfill(orderId); }
catch (Exception e) { log.error("failed", e); return ResponseEntity.status(500).build(); }

// Good - let advice map status; catch only what this layer handles
return ResponseEntity.ok(service.fulfill(orderId));
```

**Catch-and-rethrow with no transformation** - `[Recommend]`. If the goal is HTTP status mapping, that belongs in `@RestControllerAdvice`. If the goal is logging, the advice logs once at the boundary.

### Category 3 - Premature abstraction

**`@Service` interface with one implementation** - `[Must]`. Every refactor touches two files; Mockito mocks concrete classes directly (ByteBuddy); Spring proxies concrete classes by default.

```java
// Bad
public interface OrderService { OrderResponse fulfill(Long id); }
@Service public class OrderServiceImpl implements OrderService { ... }

// Good
@Service public class OrderService { ... }
```

Justified when a second implementation exists, an `@Aspect` needs a JDK-proxy pointcut, or a non-Mockito test seam requires the interface.

**`BaseService<T, ID>` with one or two subclasses** - `[Recommend]`. Generics propagation buys ~3 saved lines per child. Abstract only when 3+ services share real cross-cutting behavior (audit, metrics, tenant scoping).

**Custom `Result<T>` wrapping a single failure mode** - `[Recommend]`. `Optional` already expresses "found or not"; exceptions express domain failures. Use `Result<T>` only when callers branch on 2+ distinct failure variants and exceptions would be overkill.

```java
// Bad
public Result<Order> findOrder(Long id) {
    return orderRepository.findById(id)
        .map(Result::success)
        .orElseGet(() -> Result.failure("not found"));
}

// Good
public Optional<Order> findOrder(Long id) { return orderRepository.findById(id); }
```

**Speculative `@ConfigurationProperties` keys** - `[Recommend]`. Flag fields declared and validated but never read in the repo (confirm with a repo-wide search for the property name).

**Mapper proliferation** - `[Recommend]`. Three mapper classes for one transformation; prefer a MapStruct interface or `OrderResponse.from(Order)` static factory.

## Output Format

One block per finding:

```
### [Must | Recommend | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `@NotNull` on `Order.user`}
- Unnecessary because: {FK | `nullable = false` | unique index | DTO `@NotNull` | `@RestControllerAdvice` | framework guarantee | single impl | `Optional` already expresses this | unread/speculative}
- Cost: {extra SELECT | masked exception | proxy mismatch | forced two-file refactor | speculative surface} _(required for `[Must]`)_
- Recommendation: {concrete edit}
- Justified when: {one-line note - on `[Question]` always; on `[Must]`/`[Recommend]` when a known exception exists, e.g., "no unique index present"}
```

For each of the three categories with no findings, state `No <category> findings.` so the workflow sees the check ran.

When the request asks what should stay (or reviewed code was contested but is justified), close with a keep-list - one line per element:

```
Keep: {code element} - {constraint or reason it is necessary}
```

## Avoid

- Flagging Bean Validation on a DTO consumed by `@Valid` - that layer owns user-facing errors
- Flagging an entity `@NotNull` without checking for non-controller write paths (Kafka consumer, scheduled job, admin tool)
- Recommending removal of a unique pre-check without confirming the unique index exists
- Flagging a `@Service` interface before checking for a second impl, `@Aspect`, or test seam
- Treating Optional/stream style preferences as overengineering - this skill judges necessity, not idiom
