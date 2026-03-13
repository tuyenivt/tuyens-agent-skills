---
name: task-spring-new
description: End-to-end Spring Boot feature implementation workflow. Generates entity, repository, service, controller, DTO records, Flyway migration, and tests (unit + integration). Use for new features requiring multiple coordinated layers. Not for single-file changes, isolated bug fixes, or simple scaffolding tasks.
metadata:
  category: backend
  tags: [spring-boot, java, feature, implementation, workflow, jpa, rest-api, testing]
  type: workflow
user-invocable: true
---

# Implement Feature

## When to Use

- Implementing a new Spring Boot feature end-to-end (entity → controller → tests → migration)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate with REST API, persistence, and test coverage
- Any daily coding task that requires coordinated generation of multiple Spring Boot layers

## Rules

- Constructor injection only - use `@RequiredArgsConstructor` (Lombok); never `@Autowired` fields
- Records for all DTOs (Java 21+); classes for JPA entities
- `@Transactional(readOnly = true)` as default on service classes
- Never expose JPA entities in API responses - always map to DTO records
- No `synchronized` blocks - breaks Virtual Threads; use `ReentrantLock` if needed
- Connection pool sizing: 10–40 (optimized for Virtual Threads)
- Use `var` for local variables when type is obvious
- Use `@MockitoBean` not `@MockBean` (deprecated since Spring Boot 3.4.0)
- Jakarta EE 10 for Spring Boot 3.x; Jakarta EE 11 for Spring Boot 4
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run compilation check after all files are generated

## Implementation

STEP 1 - GATHER: feature name, package base, operations (CRUD/custom), async messaging needs, entity relationships, validation constraints, API visibility

STEP 2 - DESIGN: propose endpoints (method + URI + DTOs + status), entity fields, service methods, transaction boundaries. Present for user approval before generating code.

STEP 3 - ENTITY + MIGRATION: Use skill: `spring-jpa-performance`, `spring-db-migration-safety`. Generate entity class with audit fields; Flyway migration with indexes for FK and filter columns. LAZY fetch by default.

STEP 4 - REPOSITORY: Use skill: `spring-jpa-performance`. Extend `JpaRepository<{Name}, Long>`. JPQL `@Query` for custom methods; `Specification` for dynamic filters; `Page<>` for pagination.

STEP 5 - SERVICE: Use skill: `spring-transaction`, `spring-exception-handling`. If async/messaging: Use skill: `spring-messaging-patterns`. `@Service @Transactional(readOnly=true) @RequiredArgsConstructor @Slf4j`. `@Transactional` (read-write) on mutating methods only. Entity-DTO mapping in-class. Business exceptions from common base.

STEP 6 - CONTROLLER: Use skill: `api-guidelines`, `spring-exception-handling`. `@RestController @RequestMapping("/api/v1/{resources}") @RequiredArgsConstructor`. `@Valid @RequestBody` on writes. `Pageable` on list. `201 CREATED` for POST, `204 NO_CONTENT` for DELETE. Request and Response DTO records.

STEP 7 - TESTS: Use skill: `spring-test-integration`. Unit: `@ExtendWith(MockitoExtension.class)`, `@MockitoBean` (not `@MockBean`). Integration: `@DataJpaTest` + Testcontainers. API: `@WebMvcTest` + MockMvc. Cover happy path, not-found, validation, error responses.

STEP 8 - VALIDATE: `./gradlew compileJava compileTestJava`. Present file list, endpoints, test count, any warnings.

## Self-Check

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
