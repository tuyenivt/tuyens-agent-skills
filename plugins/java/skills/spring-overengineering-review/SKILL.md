---
name: spring-overengineering-review
description: "Spring necessity review - flag Bean Validation duplicating JPA/DB, defensive guards on framework guarantees, single-impl interfaces."
metadata:
  category: backend
  tags: [java, spring-boot, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Category 1 applies when the project uses JPA/Hibernate - `ORM` says so, or, when `ORM` is absent, the build file declares `spring-boot-starter-data-jpa` / `hibernate-core`. Otherwise it reports `No Redundant Validation findings (no JPA provider).`

## When to Use

- Reviewing a Spring Boot diff or codebase that adds validation annotations, defensive null checks, service interfaces, or new abstractions
- Phase D of `task-spring-review` - catching code that is correct, performant, and safe but does not need to exist
- Answering "which of these should stay?" for a list of contested elements

## Rules

- Cite the evidence that makes the code unnecessary - one value from the `Unnecessary because` list in the Output Format, confirmed by a repo search. No evidence, no finding.
- A database constraint counts only when a hand-written migration (Flyway/Liquibase) has it: a `NOT NULL` column, unique index or FK. `@Column(nullable = false)` and `@ManyToOne(optional = false)` are DDL hints - Hibernate does not check them at runtime when Bean Validation is on the classpath - so they never stand in for the database. When the schema is generated (`ddl-auto`, exported DDL), entity `@NotNull`/`@Size` are where the constraint comes from and stay.
- Which layer owns which assertion:
  - **Presence and uniqueness** (`@NotNull`, unique) duplicated by a database constraint are redundant whatever the write paths.
  - **Shape** (`@NotBlank`, `@Size`, `@Email`, `@Pattern`, `@Positive`) on an entity is redundant only when a validated DTO is the sole write path. A second writer that bypasses the DTO (Kafka consumer, scheduled job, admin tool) rescues it. A `NOT NULL` column enforces non-null, not non-blank.
- Label: a pattern below that states its own label keeps it; otherwise `[Recommend]`, escalated to `[Must]` when keeping the code has a measurable runtime cost (an extra query per call, a masked exception). Then, overriding both: a justification check that could not be run (no repo access, unresolvable search) downgrades the label to `[Recommend]`, with the open assumption stated in `Justified when`.
- Code matching several patterns gets one finding under the higher label. Several redundant annotations on one field are one finding (its `Unnecessary because` joins the values with `+`); separate fields are separate findings. Callers and write paths mean production code - tests do not rescue anything.
- Justification checks (constraint in a migration, sole write path, second impl, `final` class, test seam, `@EnableMethodSecurity`) are repo searches, not diff guesses.
- Defects outside the three categories (a wrong mapping, a bug, a missing unique index) are not findings here - name each on one `Out of scope:` line, anchored like a finding, so the caller routes it.

## Patterns

### Category 1 - Redundant validation vs JPA / DB

DTO validation owns user-facing errors; entity validation fires when Hibernate executes the INSERT/UPDATE - at flush, or immediately on `persist()` with IDENTITY ids.

```java
// Bad - optional=false, nullable=false and @NotNull all assert non-null
@ManyToOne(optional = false)
@JoinColumn(name = "user_id", nullable = false)
@NotNull
private User user;

// Good - given `user_id ... NOT NULL` in the migration; optional=false kept for inner-join fetching
@ManyToOne(optional = false)
@JoinColumn(name = "user_id")
private User user;
```

```java
// Bad - the validated DTO is the only writer and already checks shape and length
@Email @Size(max = 255) @Column(length = 255, nullable = false)
private String email;

// Good
@Column(length = 255, nullable = false)
private String email;
```

**Manual unique-check before save** - `[Must]` when the unique index exists. Race-prone (two concurrent SELECTs both pass), the index rejects anyway, and it costs one SELECT per write.

```java
// Bad
if (userRepository.existsByEmail(req.email())) throw new DuplicateEmailException();
userRepository.save(new User(req));

// Good - the unique index uk_users_email is authoritative. saveAndFlush, not save: with
// SEQUENCE ids the INSERT defers to flush, so a catch around save() would miss it.
// Map only this constraint (suffix match: MySQL and Oracle qualify the name); any other violation
// is not a duplicate email.
try { return userRepository.saveAndFlush(new User(req)); }
catch (DataIntegrityViolationException e) {
    if (e.getCause() instanceof org.hibernate.exception.ConstraintViolationException c && c.getConstraintName() != null
            && c.getConstraintName().toLowerCase(Locale.ROOT).endsWith("uk_users_email")) throw new DuplicateEmailException(e);
    throw e;
}
```

The catch must not continue work in the same transaction: it is marked rollback-only and the Hibernate session is unusable after the exception (PostgreSQL has also aborted it). No unique index: the pre-check is not flagged; emit `Out of scope: missing unique index on <table.column> at <file:line> - data integrity`.

### Category 2 - Defensive impossibility (guards on framework guarantees)

The framework guarantees: required injection points on container-managed beans (constructor parameters and `@Autowired` members not declared `required = false`, `@Nullable`, `Optional` or `ObjectProvider`); fields of a `@Valid` request body under `@NotNull`; an authenticated principal inside a method reached through the proxy whose `@PreAuthorize` expression requires authentication (`isAuthenticated()`, `hasRole`, `hasAuthority`), with `@EnableMethodSecurity` present. A guard that re-checks a guarantee is dead code that implies the guarantee is unreliable; a guard that silently returns or defaults (`if (x == null) return;`) also hides the regression that should fail loudly.

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

A guard is justified when a caller exists that the guarantee does not cover - the security principal read on a `@Scheduled` thread, or an `@Async` one without context propagation (`getAuthentication()` is null there; Boot 4.1 `spring.task.execution.propagate-context=true` or a `ContextPropagatingTaskDecorator` carries it), a method also called outside the proxy. A request-scoped bean read outside a request throws `ScopeNotActiveException` rather than returning null - a null guard there is dead code, and the scheduled path is broken (`Out of scope:`).

**Blanket `catch (Exception)` in a controller, service, or message listener** - `[Must]`. Swallows `DataIntegrityViolationException`, `NullPointerException` and domain exceptions: in controllers it erases `@RestControllerAdvice` status mapping (404/409 collapse to 500); in listeners it defeats retry and the DLT. A `@Scheduled` method is already logged-and-continued by the scheduler's error handler - flag its catch only when it swallows without logging (`Unnecessary because: scheduler error handler`).

```java
// Bad
try { return ResponseEntity.ok(service.fulfill(orderId)); }
catch (Exception e) { log.error("failed", e); return ResponseEntity.status(500).build(); }

// Good - let the advice map status; catch only what this layer handles
return ResponseEntity.ok(service.fulfill(orderId));
```

**Catch-and-rethrow with no transformation** - `[Recommend]`. Rethrowing as-is, or wrapped in a bare `RuntimeException`, adds nothing: HTTP mapping belongs in `@RestControllerAdvice`; logging happens once at the boundary.

### Category 3 - Premature abstraction

**`@Service` interface with one implementation** - `[Recommend]`. Every refactor touches two files; Mockito mocks concrete classes; without the interface Spring proxies the class itself (CGLIB).

```java
// Bad
public interface OrderService { OrderResponse fulfill(Long id); }
@Service public class OrderServiceImpl implements OrderService { ... }

// Good
@Service public class OrderService { ... }
```

Justified when: a second implementation exists (a `@Profile` or test-only one counts); the class or its advised methods are `final` (CGLIB cannot proxy them); a pointcut or `@DeclareParents` targets the interface type (`execution(* com.acme.InvoiceGateway+.*(..))`); the interface is a module or port boundary - the implementation lives in a different module from the interface.

**`BaseService<T, ID>` with one or two subclasses** - `[Recommend]`. Abstract only when 3+ services share real cross-cutting behavior (audit, metrics, tenant scoping).

**Custom `Result<T>` wrapping a single failure mode** - `[Recommend]`. `Optional` expresses "found or not"; exceptions express domain failures. `Result<T>` earns its place when callers branch on 2+ distinct failure variants.

```java
// Bad
public Result<Order> findOrder(Long id) {
    return orderRepository.findById(id).map(Result::success).orElseGet(() -> Result.failure("not found"));
}

// Good
public Optional<Order> findOrder(Long id) { return orderRepository.findById(id); }
```

**Speculative `@ConfigurationProperties` keys** - `[Recommend]`. A field is unread when no code calls its accessor (`props.retryLimit()` / `getRetryLimit()`) and no `@Value("${...}")`, `${key}` placeholder (annotation attributes, other property values), `@ConditionalOnProperty` or `Environment.getProperty` reads the key; the key's presence in `application*.yml` is a declaration, not a read.

**Mapper proliferation** - `[Recommend]`. Several mapper classes for one transformation; prefer one MapStruct interface or an `OrderResponse.from(Order)` factory.

## Output Format

Order: findings grouped by category (Redundant Validation, Defensive Impossibility, Premature Abstraction), by `file:line` within a category. Anchor at `file:line`; when the input carries no line numbers, anchor at `file:symbol` and say so once at the top; pasted input without files anchors at `Class.member`. A finding spanning several classes (a mapper chain) anchors at the entry class and names the rest in `Code`; two findings on one anchor add `(2)`.

```
### [Must | Recommend] {file:line}

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `@NotNull` on `Order.user`}
- Unnecessary because: {DB NOT NULL column | DB unique index | DB foreign key | DTO validation | `@RestControllerAdvice` | retry/DLT machinery | scheduler error handler | no-op rethrow | framework guarantee | single impl | thin base, <3 subclasses | `Optional` already expresses this | duplicate mapper | unread/speculative}
- Cost: {extra query | masked exception | forced two-file refactor | speculative surface} {required on [Must]; on [Recommend] only when a cost applies}
- Recommendation: {concrete edit}
- Justified when: {one-line note} {when a known exception exists, or the justification is assumed but unverified}
```

For each category with no findings, state `No <category> findings.` so the caller sees the check ran.

Close with a keep-list whenever the request asks what should stay or reviewed code was contested but is justified - one line per element:

```
Keep: {code element} - {constraint or reason it is necessary}
```

Then, when any, `Out of scope: {defect} at {file:line} - {owning concern}` lines - e.g. `Out of scope: Order.legacyRef maps a column V20260915_1050 drops at Order.java:47 - schema/entity drift`.

## Avoid

- Flagging Bean Validation on a DTO consumed by `@Valid` - that layer owns user-facing errors
- Citing `nullable = false` or `optional = false` as the enforcing constraint without the schema constraint behind it
- Flagging an entity shape annotation without checking for non-DTO write paths
- Recommending removal of a unique pre-check without confirming the unique index exists
- Flagging a `@Service` interface before checking for a second impl, a `final` class, an interface-typed pointcut, or a module boundary
- Treating Optional/stream style preferences as overengineering - this skill judges necessity, not idiom
