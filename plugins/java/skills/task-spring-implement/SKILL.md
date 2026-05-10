---
name: task-spring-implement
description: "End-to-end Spring Boot feature implementation: entity, repository, service, controller, DTO records, Flyway migration, tests across layers."
metadata:
  category: backend
  tags: [spring-boot, java, feature, implementation, workflow, jpa, rest-api, testing]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. The preamble decides between modes (`no-spec`, `spec-only`, `spec+plan`, `full-spec`); follow its contract - skip GATHER (and DESIGN, when `plan.md` is present) and treat the spec as the source of truth. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

# Implement Feature

## When to Use

- Implementing a new Spring Boot feature end-to-end (entity → controller → tests → migration)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate with REST API, persistence, and test coverage
- Any daily coding task that requires coordinated generation of multiple Spring Boot layers

## Edge Cases

- **Partial input** (feature name only): ask for entity fields, relationships, and operations before design
- **No persistence** (proxy/aggregation endpoint): skip entity/repository/migration; generate controller + service + DTOs + tests only
- **Existing entity referenced**: read it and extend; skip migration if no schema change
- **Referenced entity missing**: ask whether to generate it or assume it exists
- **Maven project**: substitute `./mvnw` for `./gradlew` in Step 9
- **Webhook receiver**: skip CRUD scaffold; generate raw-body controller + signature validation
- **Status transitions**: validate in service layer, add CHECK constraint in migration (Step 6, Step 4)
- **Idempotency**: unique key column + find-or-create + duplicate-request test (Step 6, Step 8)
- **Bulk operations**: `@Transactional` `saveAll` + size limit + dedicated endpoint

## Rules

- Constructor injection only - use `@RequiredArgsConstructor` (Lombok); never `@Autowired` fields
- Records for all DTOs (Java 21+); classes for JPA entities
- `@Transactional(readOnly = true)` as default on service classes
- Never expose JPA entities in API responses - always map to DTO records
- No `synchronized` blocks - breaks Virtual Threads; use `ReentrantLock` if needed
- Connection pool sizing: 10-40 (optimized for Virtual Threads)
- Use `var` for local variables when type is obvious
- Use `@MockitoBean` not `@MockBean` (deprecated since Spring Boot 3.4.0)
- Jakarta EE 10 for Spring Boot 3.x; Jakarta EE 11 for Spring Boot 4
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run compilation check after all files are generated

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Load these rules first - they govern every step including stack detection, scope decisions, and finding generation.

### STEP 2 - DETECT STACK AND GATHER REQUIREMENTS (MANDATORY)

Use skill: `stack-detect` to confirm the project is Spring Boot and identify framework versions, database, and project layout conventions.

Ask the user these questions before writing any code:

1. Feature name and primary use case
2. Package base and operations (CRUD/custom search/filter)
3. Entity fields, relationships, and validation constraints (required, unique, range, format)
4. Are there external integrations? (third-party APIs, webhooks, callbacks)
5. Async messaging needs? (notifications, syncing, event-driven workflows)
6. API visibility (public/authenticated/role-restricted)
7. Are there status transitions? (e.g., order: pending -> confirmed -> shipped)
8. Idempotency requirements? (deduplication keys, exactly-once processing)
9. Are there webhook or callback endpoints from external services? (signature validation, raw body parsing)

Do not continue until requirements are complete. If the user provides incomplete input, ask targeted clarifying questions.

### STEP 3 - DESIGN (MANDATORY APPROVAL GATE)

Propose endpoints (method + URI + query params + DTOs + status), entity fields with types and constraints, service methods, transaction boundaries. Include custom filter/search endpoints (e.g., `GET /api/v1/products?categoryId=5`). Present for user approval before generating code.

Design decisions to present:

- Endpoints (method, URI, status codes, request/response DTOs)
- Entity model + DB schema changes (indexes, constraints, CHECK constraints for status fields)
- Service methods and transaction boundaries
- Error model (domain exception hierarchy, HTTP status mapping)
- Idempotency strategy (if applicable)
- Webhook handler design (if applicable): raw body reading, signature validation, event type routing
- Background job dispatch points (after which transaction commits)

Only generate code after user approves design.

### STEP 4 - ENTITY + MIGRATION

Use skill: `spring-jpa-performance`, `spring-db-migration-safety`. Generate entity class with:

- Audit fields via `@MappedSuperclass` base entity: `createdAt` (`@CreatedDate`), `updatedAt` (`@LastModifiedDate`) with `@EntityListeners(AuditingEntityListener.class)` and `@EnableJpaAuditing` on a config class
- Bean Validation annotations mapping from gathered constraints: `@NotBlank`, `@NotNull`, `@Positive`, `@Size`, etc.
- JPA `@Column` constraints: `nullable = false` for required fields, `unique = true` for unique fields, `precision`/`scale` for `BigDecimal` (e.g., `@Column(precision = 19, scale = 4)` for monetary values)
- LAZY fetch by default on all associations
- Flyway migration with column types matching JPA annotations (e.g., `NUMERIC(19,4)` for `BigDecimal`), indexes on FK columns, unique constraint columns, and frequently filtered columns

For status fields with known transitions, add a CHECK constraint:

```sql
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'));
```

For idempotency keys, add a unique index:

```sql
CREATE UNIQUE INDEX idx_payments_idempotency_key ON payments(idempotency_key);
```

### STEP 5 - REPOSITORY

Use skill: `spring-jpa-performance`. Extend `JpaRepository<{Name}, Long>`. Use derived query methods for simple filters (e.g., `Page<Product> findByCategoryId(Long categoryId, Pageable pageable)`). Use JPQL `@Query` only when derived method names become unwieldy. Use `Specification` only when the endpoint supports multiple optional filter parameters. `Page<>` for all list endpoints.

For idempotency, implement upsert-style lookup:

```java
Optional<Payment> findByIdempotencyKey(String idempotencyKey);
```

### STEP 6 - SERVICE

Use skill: `spring-transaction`, `spring-exception-handling`. If async/messaging: Use skill: `spring-messaging-patterns`. `@Service @Transactional(readOnly=true) @RequiredArgsConstructor @Slf4j`. `@Transactional` (read-write) on mutating methods only. Entity-to-DTO mapping via static factory method on the response DTO record: `public static XxxResponse from(Xxx entity)`. Business exceptions from common base.

For status transitions, validate transitions in the service layer before persisting:

```java
private static final Map<OrderStatus, Set<OrderStatus>> VALID_TRANSITIONS = Map.of(
    OrderStatus.PENDING, Set.of(OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
    OrderStatus.CONFIRMED, Set.of(OrderStatus.SHIPPED, OrderStatus.CANCELLED),
    OrderStatus.SHIPPED, Set.of(OrderStatus.DELIVERED)
);

@Transactional
public OrderResponse transition(Long id, OrderStatus newStatus) {
    Order order = orderRepository.findById(id)
        .orElseThrow(() -> new OrderNotFoundException(id));
    Set<OrderStatus> allowed = VALID_TRANSITIONS.getOrDefault(order.getStatus(), Set.of());
    if (!allowed.contains(newStatus)) {
        throw new InvalidStateTransitionException(order.getStatus(), newStatus);
    }
    order.setStatus(newStatus);
    return OrderResponse.from(orderRepository.save(order));
}
```

For idempotent operations (e.g., payment processing), check by idempotency key first:

```java
@Transactional
public PaymentResponse processPayment(PaymentRequest req) {
    return paymentRepository.findByIdempotencyKey(req.idempotencyKey())
        .map(PaymentResponse::from) // already processed - return existing
        .orElseGet(() -> {
            Payment payment = Payment.from(req);
            return PaymentResponse.from(paymentRepository.save(payment));
        });
}
```

### STEP 7 - CONTROLLER

Use skill: `backend-api-guidelines`, `spring-exception-handling`. If endpoints need authorization: Use skill: `spring-security-patterns`. `@RestController @RequestMapping("/api/v1/{resources}") @RequiredArgsConstructor`. `@Valid @RequestBody` on writes. `Pageable` on list. `@RequestParam` for filter/search parameters (e.g., `@RequestParam(required = false) Long categoryId`). `201 CREATED` for POST, `204 NO_CONTENT` for DELETE. Request and Response DTO records.

For webhook endpoints from external services (e.g., Stripe), read the raw body for signature validation:

```java
@PostMapping("/webhooks/stripe")
public ResponseEntity<Void> handleStripeWebhook(
        @RequestBody String rawBody,
        @RequestHeader("Stripe-Signature") String signature) {
    stripeWebhookService.verify(rawBody, signature); // throws if invalid
    stripeWebhookService.process(rawBody);
    return ResponseEntity.ok().build();
}
```

### STEP 8 - TESTS

Use skill: `spring-test-integration`. Unit: `@ExtendWith(MockitoExtension.class)`, `@MockitoBean` (not `@MockBean`). Integration: `@DataJpaTest` + Testcontainers. API: `@WebMvcTest` + MockMvc. Cover: happy path, not-found, validation errors (missing required fields, invalid values), unique constraint violations (409 Conflict), filter/search endpoints, error responses, idempotency (duplicate request returns same response), invalid state transitions (returns 409/422).

### STEP 9 - VALIDATE

`./gradlew compileJava compileTestJava`. Present file list, endpoints, test count, any warnings.

## Avoid

- Generating code before requirements are gathered and design is approved
- Exposing JPA entities directly in API responses (always map to DTO records)
- `@Autowired` field injection (use constructor injection via `@RequiredArgsConstructor`)
- `synchronized` blocks (breaks Virtual Threads - use `ReentrantLock` if needed)
- `@MockBean` (deprecated since Spring Boot 3.4.0 - use `@MockitoBean`)
- H2 for integration tests (use Testcontainers with real database)
- Skipping idempotency handling when the feature involves payment or external service callbacks
- Missing CHECK constraints for status fields with known transitions
- Unbounded `findAll()` without pagination

## Self-Check

- [ ] Behavioral principles loaded as Step 1 before any other delegation
- [ ] Requirements gathered and design approved before any code generated
- [ ] All layers generated: Flyway migration, entity, repository, service, controller, DTOs, tests
- [ ] `@RequiredArgsConstructor` used; no `@Autowired` fields; no `synchronized` blocks
- [ ] Records used for all DTOs; JPA entities never exposed directly in API responses
- [ ] `@Transactional(readOnly = true)` on service class; `@Transactional` on mutating methods only
- [ ] `@MockitoBean` used (not `@MockBean`); Testcontainers for integration tests
- [ ] `./gradlew compileJava compileTestJava` passes; file list, endpoint table, and test count presented

## Output

Present a checklist of generated files:

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

- Unit tests: {count} (service layer)
- Integration tests: {count} (repository layer)
- API tests: {count} (controller layer)
```
