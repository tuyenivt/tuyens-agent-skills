---
name: task-kotlin-implement
description: End-to-end Kotlin / Spring Boot feature implementation: clarification, design, layered code generation, Flyway migration, unit + integration tests.
agent: kotlin-architect
metadata:
  category: backend
  tags: [kotlin, spring-boot, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` is passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after STEP 1 and STEP 2. The preamble chooses mode and dictates which gather/design steps to skip. Treat the spec as source of truth; surface conflicts as proposed amendments. Never edit `spec.md`, `plan.md`, or `tasks.md`.

# Implement Kotlin Feature

## When to Use

- End-to-end Kotlin + Spring Boot feature (entity, controller, tests, migration)
- New domain aggregate with REST API, persistence, coroutines, tests

Not for single-file changes (edit directly) or bug fixes (use `task-kotlin-debug`).

## Rules

- Constructor injection only; no `@Autowired` fields.
- `data class` for DTOs; regular `class` for JPA entities; never expose entities in API responses.
- `@Transactional(readOnly = true)` default on service classes; `@Transactional` on mutating methods only.
- No `synchronized` (pins Virtual Threads) - `ReentrantLock` if needed.
- `suspend` endpoints only when the service path is coroutine-based.
- `@MockkBean` + `coEvery` / `coVerify` for suspend mocks.
- Verify `kotlin("plugin.jpa")` and `kotlin("plugin.spring")` in `build.gradle.kts`.
- Present design and wait for approval before generating code.

## Edge Cases

- **Vague input**: ask targeted questions; never guess field names, types, relationships.
- **No persistence**: skip STEP 4 + 5; generate service and controller only.
- **Existing entity**: read and extend; check existing DTOs / repositories.
- **Referenced entity missing**: ask whether to create or use a plain ID reference.
- **Maven project**: detect `pom.xml` and use `./mvnw` instead of `./gradlew`.
- **Bulk operations**: `@Transactional` + `saveAll()`, dedicated bulk endpoint, collection size limits.
- **Soft-delete**: `deletedAt: Instant?` + Hibernate `@SQLDelete` + `@SQLRestriction`; partial index `WHERE deleted_at IS NULL`.

## Workflow

### STEP 1 - Load behavioral principles (mandatory, first)

Use skill: `behavioral-principles`.

### STEP 2 - Detect stack + gather requirements

Use skill: `stack-detect`.

Collect and confirm:

- Feature / resource name and package
- Operations (CRUD + domain actions)
- Fields, constraints, validation
- Relationships
- API visibility (public / internal / admin)
- Coroutine usage (suspend services? Flow streaming?)
- Async / messaging needs

Don't continue until requirements are complete.

### STEP 3 - Design (mandatory approval gate)

Propose and wait for approval:

- Endpoints (method, URI, status, request/response DTOs)
- Entity model + DB schema
- Service methods + transaction boundaries
- Coroutine scope decisions (suspend vs blocking, Flow vs List)
- Error model + validation
- Kotlin enums for status / category

Generate code only after approval.

### STEP 4 - Entity + migration

Use skill: `kotlin-idioms` for entity conventions.
Use skill: `kotlin-spring-db-migration-safety` for zero-downtime migration safety.

Generate:

- Entity: regular Kotlin class, JPA annotations, audit fields, ID-based equals/hashCode
- Kotlin enum for status / type
- Flyway migration with indexes on FK + filter columns
- Verify `kotlin-jpa` + `kotlin-spring` plugins

Entity changes always include a migration.

### STEP 5 - Repository

Use skill: `kotlin-spring-jpa-performance`.

- `JpaRepository<{Name}, Long>` (or `CoroutineCrudRepository` for R2DBC)
- JPQL `@Query` before native SQL; `Specification` for dynamic filters
- `Pageable` on list / filter methods

### STEP 6 - Service

Use skill: `kotlin-coroutines-spring` for coroutine boundaries.
Use skill: `kotlin-spring-transaction` for transaction patterns.

- Constructor injection
- `@Service @Transactional(readOnly = true)` default
- `@Transactional` on mutating methods
- Entity-to-DTO via extension functions
- Business exceptions from common base
- `suspend` only when the path is coroutine-based

### STEP 7 - Controller + DTO

Use skill: `backend-api-guidelines` for REST conventions.

- `@RestController @RequestMapping("/api/v1/{resources}")`
- Kotlin request / response data classes with Jakarta validation
- `@Valid @RequestBody`; `Pageable` for list endpoints
- `201 CREATED` for POST, `204 NO_CONTENT` for DELETE
- `suspend` endpoints only when service path is coroutine-based
- Never return entities directly

### STEP 8 - Error handling + security check

Use skill: `kotlin-spring-exception-handling`.

- Apply consistent error mapping via existing or new `@ControllerAdvice`
- Map domain exceptions:

| Domain Error          | HTTP Status |
| --------------------- | ----------- |
| NotFound              | 404         |
| ValidationFailed      | 400         |
| Conflict / Duplicate  | 409         |
| Unauthorized          | 403         |
| BusinessRuleViolation | 422         |

- Endpoint auth requirements explicit before finalizing

### STEP 9 - Tests

Use skill: `kotlin-testing-patterns`.

- Unit: MockK + `coEvery` / `coVerify`; kotest matchers; fixture factories
- Repository: `@DataJpaTest` + Testcontainers
- Controller: `@WebMvcTest` + `@MockkBean` + MockMvc Kotlin DSL

Cover: happy path, not-found, validation, error responses, edge cases.

### STEP 10 - Validate

- Gradle: `./gradlew compileKotlin compileTestKotlin test`
- Maven: `./mvnw compile test-compile test`

Verify: tests pass, no unsafe-cast warnings, detekt / ktlint clean (if configured).

## Output Format

```markdown
## Generated Files

- [ ] Entity: `src/main/kotlin/.../entity/{Name}.kt`
- [ ] Enum: `src/main/kotlin/.../entity/{StatusEnum}.kt` (if applicable)
- [ ] DTO: `src/main/kotlin/.../dto/{Name}Request.kt`
- [ ] DTO: `src/main/kotlin/.../dto/{Name}Response.kt`
- [ ] Repository: `src/main/kotlin/.../repository/{Name}Repository.kt`
- [ ] Service: `src/main/kotlin/.../service/{Name}Service.kt`
- [ ] Controller: `src/main/kotlin/.../controller/{Name}Controller.kt`
- [ ] Migration: `src/main/resources/db/migration/V{timestamp}__create_{table}.sql`
- [ ] Unit test, integration test, API test

## Endpoints

| Method | URI                      | Status | Description      |
| ------ | ------------------------ | ------ | ---------------- |
| GET    | /api/v1/{resources}      | 200    | List (paginated) |
| GET    | /api/v1/{resources}/{id} | 200    | Get by ID        |
| POST   | /api/v1/{resources}      | 201    | Create           |
| PUT    | /api/v1/{resources}/{id} | 200    | Update           |
| DELETE | /api/v1/{resources}/{id} | 204    | Delete           |

## Tests
- Unit / Integration / API counts
```

## Self-Check

- [ ] `behavioral-principles` loaded as STEP 1
- [ ] Stack detected; design approved before code
- [ ] All layers generated: entity, migration, repository, service, controller, DTOs, tests
- [ ] `kotlin-jpa` and `kotlin-spring` plugins verified; entity is regular class
- [ ] `data class` for DTOs; constructor injection only; no `synchronized`
- [ ] `suspend` used consistently; MockK with `coEvery` / `coVerify` for suspend functions
- [ ] `@MockkBean` not `@MockBean`; Testcontainers for integration tests
- [ ] Build + tests pass
- [ ] Migration includes indexes; list endpoints paginated

## Avoid

- Generating code before design approval
- `data class` for JPA entities
- `@Autowired` field injection
- `synchronized` blocks
- Returning entities from controllers
- `@MockBean` instead of `@MockkBean`
- `every` / `verify` for suspend functions
- Skipping the migration when an entity changes
- Manual `open` on entities or services
