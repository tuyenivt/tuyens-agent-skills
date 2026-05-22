---
name: task-spring-implement
description: "End-to-end Spring Boot feature: entity + Flyway migration + repository + service + controller + DTO records + tests across layers."
metadata:
  category: backend
  tags: [spring-boot, java, feature, implementation, workflow, jpa, rest-api, testing]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` after `behavioral-principles` and `stack-detect`. The preamble decides between `no-spec` / `spec-only` / `spec+plan` / `full-spec` modes; follow its contract and skip GATHER (and DESIGN when `plan.md` exists). Never edit `spec.md` / `plan.md` / `tasks.md`; surface conflicts as proposed amendments.

# Implement Feature

## When to Use

- New Spring Boot feature end-to-end (entity → controller → tests → migration)
- Scaffolding a complete CRUD or domain-specific resource
- Adding a new domain aggregate with REST API, persistence, and tests

## Edge Cases

- **Partial input** (feature name only) - ask for entity fields, relationships, operations before design
- **No persistence** (proxy/aggregation endpoint) - skip entity/repository/migration; generate controller + service + DTOs + tests
- **Existing entity referenced** - read it and extend; skip migration if no schema change
- **Referenced entity missing** - ask whether to generate or assume it exists
- **Maven project** - substitute `./mvnw` for `./gradlew` in Step 9
- **Webhook receiver** - skip CRUD scaffold; raw-body controller + signature validation
- **Status transitions** - validate in service layer + CHECK constraint in migration
- **Idempotency** - unique key column + find-or-create + duplicate-request test
- **Bulk operations** - `@Transactional` `saveAll` + size limit + dedicated endpoint

## Rules

- Constructor injection only (`@RequiredArgsConstructor`); never `@Autowired` fields
- Records for DTOs; classes for JPA entities
- `@Transactional(readOnly = true)` default on service classes
- Never expose JPA entities in API responses - always map to DTO records
- No `synchronized` blocks (breaks Virtual Threads) - use `ReentrantLock` if needed
- `@MockitoBean` not `@MockBean` (deprecated since Boot 3.4)
- HikariCP `maximumPoolSize` 10-40 (Virtual Threads tuning)
- Design approved by user before code generation
- Compilation check after generation

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack and Gather Requirements

Use skill: `stack-detect`. Ask the user:

1. Feature name and primary use case
2. Package base and operations (CRUD / custom search / filter)
3. Entity fields, relationships, validation constraints
4. External integrations (third-party APIs, webhooks)
5. Async messaging needs (notifications, syncing, event-driven workflows)
6. API visibility (public / authenticated / role-restricted)
7. Status transitions (e.g., order: pending → confirmed → shipped)
8. Idempotency requirements (deduplication keys, exactly-once)
9. Webhook / callback endpoints (signature validation, raw body parsing)

Do not continue until requirements are complete.

### Step 3 - Design (approval gate)

Present for user approval:

- Endpoints (method, URI, query params, request/response DTOs, status codes)
- Entity model + DB schema (indexes, constraints, CHECK constraints for status)
- Service methods + transaction boundaries
- Error model (domain exception hierarchy, HTTP status mapping)
- Idempotency strategy (if applicable)
- Webhook handler design (if applicable)
- Background dispatch points (which transaction commits, what fires after)

Only generate code after approval.

### Step 4 - Entity + Migration

Use skill: `spring-jpa-performance`, `spring-db-migration-safety`.

- Audit fields via `@MappedSuperclass` base + `@EntityListeners(AuditingEntityListener.class)` + `@EnableJpaAuditing`
- Bean Validation from gathered constraints (`@NotBlank`, `@NotNull`, `@Positive`, `@Size`)
- JPA `@Column`: `nullable = false`, `unique = true`, `precision`/`scale` for `BigDecimal`
- LAZY fetch on all associations
- Flyway migration matches JPA: `NUMERIC(19,4)` for monetary `BigDecimal`, indexes on FK / unique / frequently-filtered columns

Status field with known transitions:

```sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'));
```

Idempotency key:

```sql
CREATE UNIQUE INDEX idx_payments_idempotency_key ON payments(idempotency_key);
```

### Step 5 - Repository

Use skill: `spring-jpa-performance`. Extend `JpaRepository<{Name}, Long>`. Derived methods for simple filters; `@Query` only when names become unwieldy; `Specification` only when an endpoint has 2+ optional filters. `Page<>` for all list endpoints.

```java
Optional<Payment> findByIdempotencyKey(String idempotencyKey);  // for idempotent writes
```

### Step 6 - Service

Use skill: `spring-transaction`, `spring-exception-handling`. If async/messaging: `spring-messaging-patterns`.

`@Service @Transactional(readOnly=true) @RequiredArgsConstructor @Slf4j`. Read-write `@Transactional` on mutating methods only. Entity-to-DTO via record static factory `XxxResponse.from(Xxx)`. Business exceptions extend a common base.

Status transitions validated in the service before persistence:

```java
private static final Map<OrderStatus, Set<OrderStatus>> VALID_TRANSITIONS = Map.of(
    PENDING, Set.of(CONFIRMED, CANCELLED),
    CONFIRMED, Set.of(SHIPPED, CANCELLED),
    SHIPPED, Set.of(DELIVERED));

@Transactional
public OrderResponse transition(Long id, OrderStatus newStatus) {
    Order order = orderRepository.findById(id).orElseThrow(() -> new OrderNotFoundException(id));
    if (!VALID_TRANSITIONS.getOrDefault(order.getStatus(), Set.of()).contains(newStatus))
        throw new InvalidStateTransitionException(order.getStatus(), newStatus);
    order.setStatus(newStatus);
    return OrderResponse.from(orderRepository.save(order));
}
```

Idempotent writes:

```java
@Transactional
public PaymentResponse processPayment(PaymentRequest req) {
    return paymentRepository.findByIdempotencyKey(req.idempotencyKey())
        .map(PaymentResponse::from)
        .orElseGet(() -> PaymentResponse.from(paymentRepository.save(Payment.from(req))));
}
```

### Step 7 - Controller

Use skill: `backend-api-guidelines`, `spring-exception-handling`. If authorization is needed: `spring-security-patterns`.

`@RestController @RequestMapping("/api/v1/{resources}") @RequiredArgsConstructor`. `@Valid @RequestBody` on writes. `Pageable` on list. `@RequestParam(required = false)` for filters. `201 CREATED` on POST, `204 NO_CONTENT` on DELETE. Request and Response DTO records.

Webhook with raw body for signature validation:

```java
@PostMapping("/webhooks/stripe")
public ResponseEntity<Void> handleStripeWebhook(
        @RequestBody String rawBody,
        @RequestHeader("Stripe-Signature") String signature) {
    stripeWebhookService.verify(rawBody, signature);
    stripeWebhookService.process(rawBody);
    return ResponseEntity.ok().build();
}
```

### Step 8 - Tests

Use skill: `spring-test-integration`.

- Unit: `@ExtendWith(MockitoExtension.class)` or plain Mockito
- Repository: `@DataJpaTest` + Testcontainers
- Controller: `@WebMvcTest` + MockMvc, `@MockitoBean` services

Cover: happy path, not-found, validation errors, unique-constraint conflict (409), filter/search, idempotency (duplicate returns same response), invalid state transition (409 / 422).

### Step 9 - Validate

`./gradlew compileJava compileTestJava`. Present file list, endpoint table, test count, any warnings.

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Requirements gathered and design approved before code
- [ ] All layers generated: migration, entity, repository, service, controller, DTOs, tests
- [ ] Constructor injection; no field `@Autowired`; no `synchronized`
- [ ] Records for DTOs; entities never exposed in API responses
- [ ] `@Transactional(readOnly = true)` on service class; read-write only on mutations
- [ ] `@MockitoBean` used; Testcontainers for integration tests
- [ ] Compilation passes; file list, endpoint table, test count presented

## Output

```markdown
## Generated Files

- [ ] Entity: `src/main/java/.../entity/{Name}.java`
- [ ] DTO: `src/main/java/.../dto/{Name}Request.java`
- [ ] DTO: `src/main/java/.../dto/{Name}Response.java`
- [ ] Repository: `src/main/java/.../repository/{Name}Repository.java`
- [ ] Service: `src/main/java/.../service/{Name}Service.java`
- [ ] Controller: `src/main/java/.../controller/{Name}Controller.java`
- [ ] Migration: `src/main/resources/db/migration/V{timestamp}__create_{table}.sql`
- [ ] Unit test: `src/test/java/.../service/{Name}ServiceTest.java`
- [ ] Integration test: `src/test/java/.../repository/{Name}RepositoryTest.java`
- [ ] API test: `src/test/java/.../controller/{Name}ControllerTest.java`

## Endpoints

| Method | URI                                  | Status | Description            |
| ------ | ------------------------------------ | ------ | ---------------------- |
| GET    | /api/v1/{resources}                  | 200    | List (paginated)       |
| GET    | /api/v1/{resources}?{filter}={value} | 200    | Filter (if applicable) |
| GET    | /api/v1/{resources}/{id}             | 200    | Get by ID              |
| POST   | /api/v1/{resources}                  | 201    | Create                 |
| PUT    | /api/v1/{resources}/{id}             | 200    | Update                 |
| DELETE | /api/v1/{resources}/{id}             | 204    | Delete                 |

## Tests

- Unit: {count}
- Integration: {count}
- API: {count}
```

## Avoid

- Generating code before requirements + design approval
- Exposing JPA entities in API responses
- `@Autowired` field injection
- `synchronized` blocks (breaks Virtual Threads)
- `@MockBean` (deprecated since Boot 3.4)
- H2 for integration tests
- Skipping idempotency for payment / external callback flows
- Missing CHECK constraints for known status transitions
- Unbounded `findAll()` without pagination
