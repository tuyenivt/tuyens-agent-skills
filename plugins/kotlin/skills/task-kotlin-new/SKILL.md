---
name: task-kotlin-new
description: End-to-end Kotlin + Spring Boot feature implementation workflow. Delivers requirements clarification, design approval, Kotlin code generation across layers, Flyway migration, and tests (unit + integration + API). Not for single-file changes, isolated bug fixes, or simple scaffolding tasks.
agent: kotlin-architect
metadata:
  category: backend
  tags: [kotlin, spring-boot, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Kotlin Feature

## When to Use

- Implementing a new Kotlin + Spring Boot feature end-to-end (entity, controller, tests, migration)
- Scaffolding a complete CRUD or domain-specific resource with Kotlin idioms
- Adding a new domain aggregate with REST API, persistence, coroutines, and test coverage
- Any daily coding task that requires coordinated generation of multiple Spring Boot layers in Kotlin

## Rules

- Constructor injection only - never `@Autowired` fields
- `data class` for DTOs; regular `class` for JPA entities (Hibernate proxies are incompatible with data classes)
- `@Transactional(readOnly = true)` as default on service classes; `@Transactional` on mutating methods only
- Never expose JPA entities in API responses - always map to DTO data classes
- No `synchronized` blocks - breaks Virtual Threads; use `ReentrantLock` if needed
- Use `suspend` endpoints only when the service path is coroutine-based
- Use `@MockkBean` not `@MockBean`; `coEvery`/`coVerify` for `suspend` function mocks
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

### STEP 1 - GATHER REQUIREMENTS (MANDATORY)

Collect and confirm:

- Feature/resource name and package
- Operations (CRUD + domain actions)
- Fields, constraints, validation rules
- Relationships to existing entities
- API visibility (public/internal/admin)
- Coroutine usage expectations (suspend services? Flow streaming?)
- Async/messaging needs

Do not continue until requirements are complete. If the user provides incomplete input, ask targeted clarifying questions.

### STEP 2 - DESIGN (MANDATORY APPROVAL GATE)

Propose and wait for approval:

- Endpoints (method, URI, status codes, request/response DTOs)
- Entity model + DB schema changes
- Service methods and transaction boundaries
- Coroutine scope decisions (suspend vs blocking, Flow vs List)
- Error model and validation behavior

Only generate code after user approves design.

### STEP 3 - ENTITY + MIGRATION

Use skill: `kotlin-idioms` for Kotlin/JPA entity conventions (regular class, not data class, with `equals`/`hashCode` on ID).

Use skill: `spring-db-migration-safety` for zero-downtime migration safety.

Generate:

- Entity: Kotlin class (not data class) with JPA annotations, audit fields
- Flyway migration with indexes for FK and filter columns

Entity changes must always include a migration.

### STEP 4 - REPOSITORY

Use skill: `spring-jpa-performance` for query patterns.

Generate Spring Data repository and custom queries as needed:

- Extend `JpaRepository<{Name}, Long>` (or `CoroutineCrudRepository` if project uses R2DBC)
- JPQL `@Query` before native SQL; `Specification` for dynamic filters
- Add `Pageable` methods when listing/filtering is required

### STEP 5 - SERVICE

Use skill: `kotlin-coroutines-spring` for coroutine boundaries and context propagation.

Use skill: `spring-transaction` for transaction patterns.

Generate service with business rules and mapping:

- Constructor injection only
- `@Service @Transactional(readOnly = true)`
- `@Transactional` on mutating methods only
- Entity-DTO mapping in-class
- Business exceptions from common base

### STEP 6 - CONTROLLER + DTO

Use skill: `backend-api-guidelines` for REST conventions.

Generate:

- REST controller with `@RestController @RequestMapping("/api/v1/{resources}")`
- Kotlin request/response data classes with Jakarta validation annotations
- `@Valid @RequestBody` on writes; `Pageable` on list endpoints
- `201 CREATED` for POST, `204 NO_CONTENT` for DELETE

Rules:

- Use `suspend` endpoints only when service path is coroutine-based
- Never return entities directly

### STEP 7 - ERROR HANDLING + SECURITY CHECK

Use skill: `spring-exception-handling` for error mapping patterns.

- Apply consistent error mapping (use existing `@ControllerAdvice` or create if absent)
- Confirm endpoint auth requirements are explicit before finalizing

### STEP 8 - TESTS

Use skill: `kotlin-testing-patterns` for MockK, kotest, and coroutine test patterns.

Generate all three layers:

- Unit tests: MockK with `coEvery`/`coVerify` for suspend functions; kotest matchers
- Repository integration tests: `@DataJpaTest` + Testcontainers
- Controller/API tests: `@WebMvcTest` + `@MockkBean` + MockMvc Kotlin DSL

Cover happy path, not-found, validation errors, and error responses.

### STEP 9 - VALIDATE

Run: `./gradlew compileKotlin compileTestKotlin test`

### STEP 10 - OUTPUT SUMMARY

Present the output format below.

## Output

```markdown
## Generated Files

- [ ] Entity: `src/main/kotlin/.../entity/{Name}.kt`
- [ ] DTO: `src/main/kotlin/.../dto/{Name}Request.kt`
- [ ] DTO: `src/main/kotlin/.../dto/{Name}Response.kt`
- [ ] Repository: `src/main/kotlin/.../repository/{Name}Repository.kt`
- [ ] Service: `src/main/kotlin/.../service/{Name}Service.kt`
- [ ] Controller: `src/main/kotlin/.../controller/{Name}Controller.kt`
- [ ] Migration: `src/main/resources/db/migration/V{timestamp}__create_{table}.sql`
- [ ] Unit test: `src/test/kotlin/.../service/{Name}ServiceTest.kt`
- [ ] Integration test: `src/test/kotlin/.../repository/{Name}RepositoryTest.kt`
- [ ] API test: `src/test/kotlin/.../controller/{Name}ControllerTest.kt`

## Endpoints

| Method | URI                      | Status | Description      |
| ------ | ------------------------ | ------ | ---------------- |
| GET    | /api/v1/{resources}      | 200    | List (paginated) |
| GET    | /api/v1/{resources}/{id} | 200    | Get by ID        |
| POST   | /api/v1/{resources}      | 201    | Create           |
| PUT    | /api/v1/{resources}/{id} | 200    | Update           |
| DELETE | /api/v1/{resources}/{id} | 204    | Delete           |

## Tests

- Unit tests: {count} (service layer)
- Integration tests: {count} (repository layer)
- API tests: {count} (controller layer)
```

## Self-Check

- [ ] Requirements gathered and design approved before any code generated
- [ ] All layers generated: entity, Flyway migration, repository, service, controller, DTOs, tests
- [ ] Kotlin class (not data class) for JPA entities; `data class` for DTOs; constructor injection only; no `synchronized` blocks
- [ ] `suspend` used consistently where needed; MockK with `coEvery`/`coVerify` for suspend functions
- [ ] `@MockkBean` used (not `@MockBean`); Testcontainers for integration tests
- [ ] `./gradlew compileKotlin compileTestKotlin test` passes
- [ ] Migration includes indexes; list endpoints paginated; file list, endpoint table, and test count presented
