---
name: task-spring-implement
description: "End-to-end Spring Boot feature: entity, Flyway migration, repository, service, controller, DTO records, tests across all layers."
metadata:
  category: backend
  tags: [spring-boot, java, feature, implementation, workflow, jpa, rest-api, testing]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Steps 1-2. Follow its mode (`no-spec` / `spec-only` / `spec+plan` / `full-spec`); skip GATHER (and DESIGN when `plan.md` exists). Never edit `spec.md` / `plan.md` / `tasks.md`; surface conflicts as proposed amendments.

# Implement Feature

## When to Use

- New Spring Boot feature end-to-end (entity, migration, repository, service, controller, DTOs, tests)
- Adding a domain aggregate with REST API and persistence
- Skip for: pure refactors, bug fixes, single-layer additions, or stack-detect output that is not Spring Boot

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`. Confirm Java 21+, Spring Boot 3.5+, build tool (Gradle vs Maven), and persistence stack. If not Spring Boot, stop.

### Step 3 - Gather Requirements

Ask and lock down before any design:

1. Feature name, package base, primary use case
2. Operations (CRUD plus custom verbs such as approve, cancel, transition)
3. Entity fields, types, validation constraints, relationships (and fetch type expectations)
4. Status field and allowed transitions, if any
5. Idempotency / deduplication needs (payments, external callbacks)
6. API visibility (public / authenticated / role-restricted)
7. Async dispatch points (events fired after commit)

Edge inputs: feature name only -> ask for fields and operations. Existing entity referenced -> read it, skip migration if no schema change. Referenced entity missing -> ask before assuming.

### Step 4 - Design (Approval Gate)

Present and wait for explicit approval:

- Endpoint table (method, URI, params, request/response DTO records, status codes)
- Entity model + Flyway DDL outline (indexes, FK, CHECK constraints for status enums, unique index for idempotency keys)
- Service method signatures + transaction boundaries (read-only default, write boundaries)
- Domain exception hierarchy + HTTP status mapping
- Post-commit dispatch points (which transaction commits, what fires after)

Generate code only after approval.

### Step 5 - Entity + Migration

Use skill: `spring-jpa-performance`, `spring-db-migration-safety`.

Entity is a class (records cannot be JPA entities). Audit fields via `@MappedSuperclass` base + `AuditingEntityListener`. Bean Validation from gathered constraints. LAZY on all associations. `@Column(nullable, unique, precision, scale)` matches the Flyway DDL exactly. Status enums get a CHECK constraint; idempotency keys get a unique index. FK and frequently-filtered columns get indexes.

### Step 6 - Repository

Use skill: `spring-jpa-performance`.

Extend `JpaRepository<{Name}, Long>`. Derived methods for simple filters; `@Query` only when names become unwieldy; `Specification` when an endpoint has 2+ optional filters. `Page<>` for all list endpoints. Idempotent writes need a `findBy{key}` lookup.

### Step 7 - Service

Use skill: `spring-transaction`, `spring-exception-handling`.

`@Service @Transactional(readOnly = true) @RequiredArgsConstructor @Slf4j`. Read-write `@Transactional` only on mutating methods. Entity-to-DTO via record static factory (`XxxResponse.from(entity)`); never return entities. Status transitions validated against an allowed-transitions map before persistence; invalid transitions throw a domain exception. Post-commit side effects via `ApplicationEventPublisher` + `@TransactionalEventListener(AFTER_COMMIT)`.

### Step 8 - Controller

Use skill: `spring-exception-handling`.

`@RestController @RequestMapping("/api/v1/{resources}") @RequiredArgsConstructor`. `@Valid @RequestBody` on writes. `Pageable` on list. `@RequestParam(required = false)` for filters. `201 CREATED` on POST, `204 NO_CONTENT` on DELETE, custom verbs as `POST /{id}/{verb}`. Request and Response DTOs are records.

### Step 9 - Tests

Use skill: `spring-test-integration`.

- Service unit: plain Mockito, `@ExtendWith(MockitoExtension.class)`
- Repository: `@DataJpaTest` + Testcontainers (matching production DB), no H2
- Controller: `@WebMvcTest` + MockMvc, `@MockitoBean` (not `@MockBean`)

Cover: happy path, not-found, validation errors, unique-constraint conflict (409), filter/search, idempotent replay returns same response, invalid state transition (409 or 422).

### Step 10 - Validate

Run `./gradlew compileJava compileTestJava` (Maven: `./mvnw compile test-compile`). Report file list, endpoint table, test count, warnings.

## Output Format

```markdown
## Generated Files

- Entity: `src/main/java/.../entity/{Name}.java`
- DTOs: `src/main/java/.../dto/{Name}Request.java`, `{Name}Response.java`
- Repository: `src/main/java/.../repository/{Name}Repository.java`
- Service: `src/main/java/.../service/{Name}Service.java`
- Controller: `src/main/java/.../controller/{Name}Controller.java`
- Migration: `src/main/resources/db/migration/V{timestamp}__create_{table}.sql`
- Tests: service unit, `@DataJpaTest` repository, `@WebMvcTest` controller

## Endpoints

| Method | URI                                  | Status | Description       |
| ------ | ------------------------------------ | ------ | ----------------- |
| GET    | /api/v1/{resources}                  | 200    | List (paginated)  |
| GET    | /api/v1/{resources}/{id}             | 200    | Get by ID         |
| POST   | /api/v1/{resources}                  | 201    | Create            |
| PUT    | /api/v1/{resources}/{id}             | 200    | Update            |
| DELETE | /api/v1/{resources}/{id}             | 204    | Delete            |
| POST   | /api/v1/{resources}/{id}/{verb}      | 200    | Custom transition |

## Tests

- Unit: {count}
- Repository: {count}
- Controller: {count}
```

## Self-Check

- [ ] Step 1 - behavioral-principles loaded
- [ ] Step 2 - stack-detect ran; Spring Boot 3.5+ / Java 21+ confirmed
- [ ] Step 3 - requirements gathered; status transitions and idempotency clarified
- [ ] Step 4 - design approved by user before any code
- [ ] Step 5 - entity + migration match (columns, constraints, indexes); CHECK constraints on status enums
- [ ] Step 6 - repository uses `Page<>` on lists; idempotency lookup present when needed
- [ ] Step 7 - `@Transactional(readOnly = true)` default; write boundaries only on mutations; DTO mapping via records; transition map enforced
- [ ] Step 8 - controller returns DTOs (never entities); correct status codes; `@Valid` on writes
- [ ] Step 9 - Testcontainers (no H2); `@MockitoBean`; conflict, replay, invalid-transition covered
- [ ] Step 10 - compilation passes; file list, endpoint table, test count reported

## Avoid

- Generating code before requirements and design approval
- Exposing JPA entities in API responses (always DTO records)
- `@Autowired` field injection (constructor only via `@RequiredArgsConstructor`)
- `synchronized` blocks (pins Virtual Threads; use `ReentrantLock`)
- `@MockBean` (deprecated since Boot 3.4; use `@MockitoBean`)
- H2 for integration tests (use Testcontainers matching production)
- Unbounded `findAll()` without pagination
- Missing CHECK constraint for known status enums
- Missing unique index for idempotency keys
- Editing `.specs/<slug>/spec.md` / `plan.md` / `tasks.md` in spec-aware mode
