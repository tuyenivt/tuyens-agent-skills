---
name: task-kotlin-new
description: "Create a new Kotlin + Spring Boot resource. Generates Kotlin entity, repository, service with coroutines, controller, data class DTOs, Flyway migration, and tests with MockK. Delegates Spring patterns to Java plugin skills."
agent: kotlin-architect
---

STEP 1 — GATHER: resource name, fields, associations, operations, coroutines needed?

STEP 2 — MIGRATION: reference Java plugin's db-migration-safety (same Flyway, same rules)

STEP 3 — ENTITY: Kotlin class (NOT data class) with mapped annotations

- kotlin-jpa plugin handles no-arg constructor
- Load skill: kotlin-idioms for Kotlin-specific patterns

STEP 4 — DTO: Kotlin data classes for request/response

- Use Kotlin null safety (String? for optional fields)

STEP 5 — REPOSITORY: Spring Data JPA interface (same as Java)

- suspend fun for coroutine-aware queries if needed

STEP 6 — SERVICE: Kotlin class with constructor injection

- suspend fun for async operations (load kotlin-coroutines-spring)
- Sealed class for result types

STEP 7 — CONTROLLER: @RestController with Kotlin syntax

- suspend fun endpoints if coroutines used

STEP 8 — TESTS: load kotlin-testing-patterns

- MockK for mocking, coEvery for suspend functions
- Same test slices as Java (@DataJpaTest, @WebMvcTest)

STEP 9 — VALIDATE: ./gradlew compileKotlin compileTestKotlin test

OUTPUT: file checklist (all .kt files)
