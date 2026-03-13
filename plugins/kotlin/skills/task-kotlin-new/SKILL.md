---
name: task-kotlin-new
description: End-to-end Kotlin + Spring Boot feature implementation workflow. Delivers requirements clarification, design approval, Kotlin code generation across layers, Flyway migration, and tests (unit + integration + API). Use for full feature delivery. Not for single-file changes, isolated bug fixes, or simple scaffolding tasks.
agent: kotlin-architect
metadata:
  category: backend
  tags: [kotlin, spring-boot, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - GATHER REQUIREMENTS (MANDATORY)

Collect and confirm:

- Feature/resource name and package
- Operations (CRUD + domain actions)
- Fields, constraints, validation rules
- Relationships to existing entities
- API visibility (public/internal/admin)
- Coroutine usage expectations

Do not continue until requirements are complete.

STEP 2 - DESIGN (MANDATORY APPROVAL GATE)

Propose and wait for approval:

- Endpoints (method, URI, status codes)
- Request/response DTO contracts
- Entity model + DB schema changes
- Transaction boundaries
- Error model and validation behavior

Only generate code after user approves design.

STEP 3 - ENTITY + MIGRATION

Generate:

- Entity: Kotlin class (not data class) with JPA annotations
- Flyway migration with indexes and FK constraints

Rules:

- Use skill: `kotlin-idioms` for Kotlin/JPA conventions
- Use skill: `spring-db-migration-safety` for zero-downtime migration safety
- Entity changes must always include migration

STEP 4 - REPOSITORY

Generate Spring Data repository and custom queries as needed.

Rules:

- Use JPQL/projections before native SQL
- Add pageable methods when listing/filtering is required
- Use suspend repository APIs only when project conventions require it

STEP 5 - SERVICE

Generate service with business rules and mapping.

Rules:

- Constructor injection only
- Read methods: `@Transactional(readOnly = true)`
- Mutations: explicit `@Transactional`
- Use skill: `kotlin-coroutines-spring` for coroutine boundaries and context propagation
- No `synchronized` blocks

STEP 6 - CONTROLLER + DTO

Generate:

- REST controller with proper status codes
- Kotlin request/response data classes with validation annotations

Rules:

- Use `suspend` endpoints only when service path is coroutine-based
- Never return entities directly
- Keep API contract stable and explicit

STEP 7 - ERROR HANDLING + SECURITY CHECK

- Apply consistent error mapping via Java plugin conventions
- Confirm endpoint auth requirements are explicit before finalizing

STEP 8 - TESTS

Generate all three layers:

- Unit tests (MockK; `coEvery`/`coVerify` for suspend)
- Repository integration tests (`@DataJpaTest`)
- Controller/API tests (`@WebMvcTest`)

Use skill: `kotlin-testing-patterns` and Java plugin test slice conventions.

STEP 9 - VALIDATE

Run:

`./gradlew compileKotlin compileTestKotlin test`

STEP 10 - OUTPUT SUMMARY

Provide:

- Files created (paths)
- Endpoints delivered
- Tests added by layer
- Validation result and follow-up actions (if any)

## Self-Check

- [ ] Requirements gathered and design approved before any code generated
- [ ] All layers generated: entity, Flyway migration, repository, service, controller, DTOs, tests
- [ ] Kotlin class (not data class) for JPA entities; constructor injection only; no `synchronized` blocks
- [ ] `suspend` used consistently; MockK with `coEvery`/`coVerify` for suspend functions
- [ ] `./gradlew compileKotlin compileTestKotlin test` passes
- [ ] Migration includes indexes; list endpoints paginated; files and test count presented

> Run `/task-skill-feedback` if output needed significant correction.
