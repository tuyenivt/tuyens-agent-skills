---
name: task-spring-implement
description: "End-to-end Spring Boot feature: entity, Flyway migration, repository, service, controller, DTO records, tests across all layers."
agent: java-engineer
metadata:
  category: backend
  tags: [spring-boot, java, feature, implementation, workflow, jpa, rest-api, testing]
  type: workflow
user-invocable: true
---

# Implement Feature

## When to Use

- New Spring Boot feature end-to-end (entity, migration, repository, service, controller, DTOs, tests)
- Adding a domain aggregate with REST API and persistence
- Skip for: pure refactors, bug fixes, single-layer additions

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect` for the build tool and the production database engine - Steps 5 and 9 branch on the engine.

Read the Spring Boot version from the build file (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` does not report either. Every construct the generated code uses must exist and bind on that version, composed-atomic forms included. Below Boot 4.0, write this workflow's or the atomic's Boot 3 form; when neither has one, say `Boot 3 form not given` rather than emitting the Boot 4 one.

From the same build file read Lombok (every Lombok annotation below applies only when present), the mapper library (MapStruct vs hand-written), and the web starter. Not Spring Boot, or WebFlux with no servlet starter (with both, servlet wins at runtime): stop and say so. Below the Boot 4.0 / Java 21 floor, do not stop: generate for the detected version and record each downgraded construct under `## Warnings`. Version-gated constructs: web starter (Boot 4 `spring-boot-starter-webmvc`; Boot 3 `spring-boot-starter-web`), Jackson 3 `tools.jackson.*` (Boot 3: `com.fasterxml.jackson.databind`; annotations stay `com.fasterxml.jackson.annotation` on both), auto-configuration classes and customizers (Boot 4 `org.springframework.boot.<tech>.autoconfigure`, e.g. `org.springframework.boot.kafka.autoconfigure.DefaultKafkaProducerFactoryCustomizer`; Boot 3 `org.springframework.boot.autoconfigure.<tech>`), the Step 9 test dependencies, `@MockitoBean` (`org.springframework.test.context.bean.override.mockito.MockitoBean` on both lines, Boot 3.4+; below that Boot's `@MockBean`), `@ServiceConnection` (Boot 3.1+), `@SQLRestriction` (Boot 3.2+; Boot 3.0-3.1 `@Where`), virtual threads (Java 21+).

The generated code needs two modules; add each when absent and list it under `Modified`: `spring-boot-starter-validation` (no web starter brings it, and without it `@Valid` validates nothing), and the project's migration tool (Flyway only when none exists) - Boot 4 `spring-boot-starter-flyway` / `spring-boot-starter-liquibase` (a bare `flyway-core` / `liquibase-core` migrates nothing on Boot 4), Boot 3 `flyway-core` / `liquibase-core` - plus, on Flyway 10+, `org.flywaydb:flyway-database-postgresql` or `flyway-mysql`.

### Step 3 - Gather Requirements

Ask and lock down before any design:

1. Feature name, package base, primary use case
2. Operations (CRUD plus custom verbs such as approve, cancel, transition)
3. Entity fields, types, validation constraints, relationships (and fetch type expectations)
4. Derived or aggregate reads (counts, averages, rollups) - each one is either computed per request or denormalized onto a column, and that choice decides whether an existing table needs a migration
5. Status field and allowed transitions, if any
6. Money: each amount's unit (minor units or decimal scale), currency, rounding and sign, and every money movement the feature makes (charge, refund, payout, scheduled charge)
7. Idempotency / deduplication needs (payments, external callbacks), and the scope the key is unique within (per caller / per tenant / global)
8. Access rule per operation: public, authenticated, role-restricted, owner-restricted, or machine-to-machine (webhook, partner callback) - plus, for owner-restricted, how the authenticated principal maps to the owning domain id, and for role-restricted, how the role reaches Spring Security as a `GrantedAuthority`
9. Side effects after commit, each durable (must happen when the row commits) or best-effort

**Degraded input.** Feature name only -> ask for fields and operations. Existing entity referenced -> read it and follow its conventions; the feature still gets a migration unless it adds no columns and no table. Referenced entity missing -> search for it under other names, then ask; unanswered, store a plain `<x>_id` column (no FK, no `@ManyToOne`), never generate the missing aggregate, and record it under `## Assumptions` and `## Warnings`. **Answers incomplete for any reason** - no interactive user, or a user who stops answering - proceed on your own defaults for the unanswered items and record each one under `## Assumptions`. Defaults when unstated: package base from the existing source root (empty project: root package plus feature name), page size 20, `Long` surrogate PK, aggregate reads computed per request rather than denormalized, only the transitions the request names with every other state terminal, money in the existing schema's representation (else `BIGINT NOT NULL CHECK (amount >= 0)` minor units plus a `CHAR(3)` currency), side effects durable when they move money or notify a partner and best-effort otherwise, idempotency keys unique **per calling principal** rather than globally, and the most restrictive access rule the operation can plausibly carry - role-restricted for an administrative verb, owner-restricted when the entity carries an owner column, authenticated otherwise. Stop only when fields or operations cannot reasonably be inferred.

### Step 4 - Design (Approval Gate)

Load the atomics Steps 5-8 name first - the design commits to what they constrain. Present and wait for explicit approval:

- Endpoint table (method, URI, access rule, request/response DTO records, status codes)
- Entity model + migration DDL outline (indexes, FK, CHECK constraints for status enums and money, unique index for idempotency keys)
- Service method signatures + transaction boundaries (read-only default, write boundaries, each money call's state machine)
- Domain exception hierarchy + HTTP status mapping
- Post-commit side effects, each on the outbox or a best-effort listener

**When approval cannot be obtained** - no interactive user, or the user does not answer - state the design, record the assumptions, and set `Design gate` in the output to `skipped (<reason>)`. Generate only the reversible parts; hold (Proportionality, `behavioral-principles`) every part whose defect would move money, expose data, or cannot be undone - any money movement (charge, refund, payout, or a job that triggers one), adding `spring-boot-starter-security` to a project without it (it locks every existing endpoint; with the starter held, every non-public endpoint is held too), and an owner that must be an existing domain id, with no principal mapping (Step 8), together with every operation it guards. A held part is not generated, not even as a stub; each gets a `Held:` warning naming the answer it waits on. When the held parts are the feature's purpose, stop at the design. Rejection loops back to Step 3 for the disputed answers, then re-presents this step.

### Step 5 - Entity + Migration

Use skill: `spring-jpa-performance`, `spring-db-migration-safety`.

Entity is a class (records cannot be JPA entities); Lombok on it is `@Getter` / `@Setter` only, even when existing entities carry `@Data`, whose `equals` / `hashCode` / `toString` walk LAZY associations and break across proxies. Audit fields via the project's existing `@MappedSuperclass` base, else `@EntityListeners(AuditingEntityListener.class)` on the entity; auditing no-ops unless `@EnableJpaAuditing` is on a configuration class, so add it if absent. Validation constraints live on request DTOs (Step 8); the entity mirrors them as DB constraints (`@Column` attributes matching the migration DDL exactly - `precision`/`scale` only for `BigDecimal`; money held as minor units is a `Long`/`BIGINT`), not duplicate Bean Validation annotations. LAZY on all associations; a foreign key that is never navigated is a plain id field, not a `@ManyToOne`. Status enums get a CHECK constraint; value invariants (non-negative amount or balance, date ordering) get CHECKs too - write them so a NULL column cannot pass, since `NULL OR FALSE` is NULL. FK and frequently-filtered columns get indexes. A migration that alters an existing table, or introduces the migration tool to a schema that already has tables, gets `spring-db-migration-safety`'s blocks in `## Migration Safety`. An introduction also ships the existing schema as a baseline that production skips and the Step 9 container builds: Flyway, a script at or below `spring.flyway.baseline-version` under `baseline-on-migrate`; Liquibase, changesets with `<preConditions onFail="MARK_RAN">` on the table's absence.

Idempotency keys get a unique index **scoped the way Step 3 answered** - a globally unique key lets one caller's key collide with another's, and replay then returns the wrong caller's resource. Idempotent creates put the key on the aggregate; an idempotent operation verb (redeem, capture) instead gets a child operation record owning the key and storing the response fields replayed on duplicates.

Soft delete (when required): `deleted_at` column plus `@SQLDelete` + `@SQLRestriction` on the entity, which filters every JPQL and derived query automatically - repository-level filtering instead means every read, **including the aggregate queries of Step 6**, must remember the predicate, and native queries bypass both. A uniqueness rule that must allow re-creation after delete needs a partial unique index (`... WHERE deleted_at IS NULL`). MySQL has no partial indexes: add `active TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL))` to the unique index (NULLs never collide), and leave it out of the entity or map it `insertable = false, updatable = false` - mapped plainly, it breaks every insert.

### Step 6 - Repository

Extend `JpaRepository<{Name}, {PK type}>`. Derived methods for simple filters; `@Query` only when names become unwieldy; `Specification` when an endpoint has 2+ optional filters. `Page<>` for all list endpoints. Aggregate reads (Step 3 item 4) computed per request are an aggregate `@Query` returning a projection interface or record, never a full-collection load. Idempotent writes need a lookup **scoped exactly like the unique index** (`findByMerchantIdAndIdempotencyKey`, not `findByIdempotencyKey`). Call a `@Modifying` query only from a read-write service transaction.

### Step 7 - Service

Use skill: `spring-transaction`, `spring-exception-handling`. When the feature publishes or has a durable side effect, also Use skill: `spring-messaging-patterns`.

`@Service @Transactional(readOnly = true)` plus constructor injection (Lombok `@RequiredArgsConstructor @Slf4j`). Read-write `@Transactional` only on mutating methods. Entity-to-DTO via record static factory (`XxxResponse.from(entity)`) unless Step 2 found a mapper library the project standardizes on; never return entities. Status transitions validated against an allowed-transitions map before persistence; invalid transitions throw a domain exception - except a re-delivered external callback re-asserting the state a row already holds, which is a replay and returns the current resource, not a 409 the partner will retry forever.

**Contended mutations** (balances, counters, stock, and any status transition two callers can race) need `@Version` on the entity when the read-modify-write spans multiple fields or must fail loudly - map `OptimisticLockingFailureException` to 409; use one atomic conditional `UPDATE ... WHERE status = :expected` instead when the change is a single-column transition and a silent no-op row count is the signal you want.

**Money.** An amount charged or refunded is computed server-side from stored data, never taken from the request. A money call whose result is saved follows `spring-transaction`'s state machine (Remote call whose result must be persisted), and the contended write it depends on is confirmed in the PENDING transaction, before the call - flushed `@Version`, a row lock, or a conditional `UPDATE` whose row count is checked; a `@Version` checked at commit settles the race after the charge. The decline transaction, and the reconciler when it resolves a row as not charged, release the reserved write. When the feature changes a money value an existing path reads (an order total, a balance), find every reader of that field and column and state what each now gets (`Money reader:`); fix a refund or payout that would use the wrong amount in this change, or hold the money feature.

**Idempotent creates need the race handled, not just the lookup.** Lookup then insert is check-then-act: concurrent callers both miss and one dies on the unique index. Catch the violation outside any transaction: an orchestrator with no transaction (`propagation = NOT_SUPPORTED` under the class-level default) calls a `@Transactional` insert on another bean, catches the violation, and re-reads the winner with Step 6's scoped lookup - or insert-or-ignore then read (`spring-transaction`, Idempotent writes, with the conflict target scoped like Step 5's index). Branch on the violated constraint's name (Hibernate `ConstraintViolationException.getConstraintName()` in the cause chain, matched by suffix - MySQL/Oracle qualify it): the idempotency index is a replay (409 when the payload fingerprint stored with the key differs from this request's), a business-dedup index is a 409 with no replay, anything else is rethrown.

**Side effects.** A publish or remote call that must happen when the row commits needs the transactional outbox. AFTER_COMMIT fits only best-effort side effects: it loses the send on a crash or a listener exception (swallowed in afterCompletion). A money call whose result must be saved follows **Money** above. Best-effort effects use `ApplicationEventPublisher` + `@TransactionalEventListener(AFTER_COMMIT)`. Publish the event or write the outbox row inside the `@Transactional` writer, never in a `NOT_SUPPORTED` orchestrator, where no transaction exists and the listener never fires.

### Step 8 - Controller

Use skill: `spring-exception-handling`. When any Step 3 access rule is not `public`, also Use skill: `spring-security-patterns`.

`@RestController @RequestMapping` + constructor injection (Lombok `@RequiredArgsConstructor`). `@Valid @RequestBody` records on writes - a raw-body HMAC webhook instead takes `@RequestBody byte[]` and parses after verifying - and `@Valid` validates nothing unless the request record's components carry the Step 3 constraints (`@NotBlank`, `@Size`, `@Pattern`, ...), so put them there now. `Pageable` on list. `@RequestParam(required = false)` for filters. `201 CREATED` on POST that creates, `200 OK` when an idempotent POST replays an existing resource, `204 NO_CONTENT` on DELETE, custom verbs as `POST /{id}/{verb}` returning `200 OK` with the resource. Request and Response DTOs are records.

Class-level `@RequestMapping` is the longest prefix every method in the class shares. A sub-resource split across two URI spaces (`/products/{id}/reviews`, `/reviews/{id}`) shares none: write full paths on each method, or split into two controllers.

**Enforce each access rule where it can actually be enforced:**

| Access rule        | Where it goes                                                                                                                      |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Public             | `permitAll` matcher placed **above** the chain's `anyRequest()` rule - after it, the chain fails at startup (`Can't configure requestMatchers after anyRequest`) |
| Authenticated      | Covered by the chain's `anyRequest().authenticated()`; no annotation needed                                                        |
| Role-restricted    | `@PreAuthorize("hasRole('X')")` on the handler, where `X` omits the `ROLE_` prefix that `hasRole` adds. The annotation is inert unless `@EnableMethodSecurity` is on a configuration class - add it if absent |
| Owner-restricted   | Not expressible at method entry - the row is not loaded yet. `@PreAuthorize("isAuthenticated()")` on the handler; the service loads scoped (`findByIdAndOwnerId`: 404 on another's row) or loads then compares principal to owner (403) - the choice decides Step 9's denied-case assertion |
| Machine-to-machine | Its own `@Order`ed, path-scoped `SecurityFilterChain` (shared credential, mTLS, or signature check with a constant-time compare) - a webhook cannot authenticate against the app's user chain |

Every hasRole / hasAuthority check is only as real as the JWT converter feeding it: a top-level claim needs authorities-claim-name plus an authority prefix; a nested claim (Keycloak realm_access.roles) yields no authorities through setAuthoritiesClaimName - Boot 4.1 `authorities-claim-expressions` plus `authority-prefix: ROLE_` (default prefix is `SCOPE_`), else a custom converter. The prefix is `authority-prefix: ROLE_` when the claim values are bare role names, and an empty prefix when they already carry `ROLE_`. Trace each role checked to what grants it (JWT converter, `UserDetailsService`, a roles table). When nothing grants it or the mapping yields nothing, every role gate denies everyone: say so, and never propose a role-based bypass.

**The owner id comes from the principal, never from the request body or path.** When the codebase has no principal-to-owner mapping (custom principal, owner claim, or principal-to-account lookup), ask. Unanswered: a new aggregate stores `Authentication.getName()` as its owner and scopes every access by it; an owner that must be an existing domain id is held (Step 4). Never generate a principal interface nothing implements. Record the choice under `## Assumptions`.

### Step 9 - Tests

Use skill: `spring-test-integration`.

- Dependencies: add the missing ones for the declared version and list each under `Modified`. Boot 4: one `spring-boot-starter-<tech>-test` per technology used (`-data-jpa-test`, `-webmvc-test`, `-security-test`), `spring-boot-testcontainers`, `org.testcontainers:testcontainers-<engine>` and `testcontainers-junit-jupiter` (2.x). Boot 3: `spring-boot-starter-test`, `spring-security-test`, `spring-boot-testcontainers`, `org.testcontainers:<engine>` and `junit-jupiter` (1.x). Versions come from the Boot BOM (Boot 3.0: pin Testcontainers).
- Service unit: plain Mockito, `@ExtendWith(MockitoExtension.class)`
- Repository: `@DataJpaTest` + Testcontainers matching production, never H2, wired with `@ServiceConnection` or `@DynamicPropertySource` (Boot 3.0-3.3: plus `@AutoConfigureTestDatabase(replace = NONE)`). Let the migrations build the schema, not `ddl-auto`, or the CHECK constraints and unique indexes from Step 5 are absent from the tested schema. An existing migration chain that fails on an empty container, or entities the tests persist that do not match it, is a `Pre-existing:` warning and a failing test named in `Suite result`. **When the existing suite runs on H2**, adopt Testcontainers for this feature's tests only and record the split convention and the new Docker requirement under `## Warnings` - do not migrate the existing suite
- Controller: `@WebMvcTest` + MockMvc, `@MockitoBean` collaborators. `@Import` the configuration classes declaring the `SecurityFilterChain` and `@EnableMethodSecurity`, and on a resource server add `@MockitoBean JwtDecoder` - without them the tests pass against Boot's default chain. On a JWT resource server, role tests send the production claim shape through the production converter (`spring-test-integration`, Security tests); bare `jwt()` skips the mapping. An owner check reading a custom principal needs `.with(user(<principal>))` / `@WithUserDetails` - `@WithMockUser` carries no domain id. State-changing requests need `.with(csrf())` when the production chain has CSRF; a session-based chain also needs a client token source (`spring-security-patterns`, CSRF), or the endpoints pass their tests and 403 in the browser
- Integration, when the feature has an idempotency race, a contended write, a money state machine, an outbox or an AFTER_COMMIT listener: `@SpringBootTest` + Testcontainers with no `@Transactional` on the test - a test transaction never commits, so none of those run (Boot 4: `@AutoConfigureMockMvc`, or `@AutoConfigureRestTestClient` with `RANDOM_PORT` or `@AutoConfigureMockMvc`; Boot 3: `TestRestTemplate` under `RANDOM_PORT`). Races run two callers behind a latch (`spring-test-integration`, Concurrency)

Cover: happy path, not-found, validation errors, filter/search, each access rule (allowed and denied), invalid state transition (409 or 422), plus the duplicate-POST case the feature actually has - business-dedup uniqueness (one X per Y) -> 409 conflict; idempotency-key replay -> original response returned; same key, different payload -> 409. Test only the cases the feature has.

### Step 10 - Validate

Resolve every import and referenced type in the generated files against a file in the repo or a named package on the declared version - a class that lives in another package, or only on the other Boot line, is a compile error. Then compile with the build tool Step 2 detected (`./gradlew compileJava compileTestJava` or `./mvnw test-compile`) and run the tests. Fix what fails and re-run; report a suite still red with the failing test names. If no build wrapper is runnable, the import resolution is the whole check: record under `## Warnings` that nothing was compiled.

## Output Format

```markdown
**Stack:** Java <version> / Spring Boot <version>{ - below the floor (<Boot 3.x | Java < 21 | both>)}

## Generated Files

- Entity: `src/main/java/.../entity/{Name}.java`
- DTOs: `src/main/java/.../dto/{Name}Request.java`, `{Name}Response.java`
- Repository: `src/main/java/.../repository/{Name}Repository.java`
- Service: `src/main/java/.../service/{Name}Service.java`
- Controller: `src/main/java/.../controller/{Name}Controller.java`
- Migration: `src/main/resources/db/migration/...` (Liquibase: `db/changelog/...`, included from the master changelog) - version prefix and naming follow the project's existing migration files, or `V{yyyyMMdd}_{HHmm}__create_{table}.sql` when the project has none; omit this entry entirely when the feature adds no schema
- Tests: service unit, `@DataJpaTest` repository, `@WebMvcTest` controller, and the `@SpringBootTest` integration class when Step 9 requires one
- Supporting: domain exceptions, config beans, extra DTOs/projections, test fixtures - whatever Steps 4-9 produced
- Modified: existing files this feature edits - build file (each dependency added), `SecurityFilterChain`, `@RestControllerAdvice`, enabling configuration - each with what changed

## Endpoints

| Method | URI | Access | Status | Description |
| ------ | --- | ------ | ------ | ----------- |
| ... | one row per endpoint this feature actually has | ... | ... | ... |

## Migration Safety {only when a migration alters an existing table or introduces the migration tool}

<`spring-db-migration-safety`'s `**Engine:**` line, `Plan:` line, then one block per file or step>

## Tests

- Unit: {count}
- Repository: {count}
- Controller: {count}
- Integration: {count}
- Suite result: {passed | failed - <failing test names> | not run - <reason>}

## Assumptions

One bullet per requirement answered by default rather than by the user, per referenced model stored as a plain `<x>_id`, per owner mapping chosen, and per unobservable stack fact. `None` when every answer came from the user.

## Warnings

Design gate: approved | skipped (<reason>)

- Held: <part not generated> - waits on <the answer it needs>
- Missing model: <name> - {stored as plain `<x>_id`, no FK | found under another name - represented as <column>}
- Downgraded: <construct> - {<form used on the detected version> | Boot 3 form not given}
- Money reader: <file:line> - <what it now gets>
- Pre-existing: <defect on this feature's path> - surfaced, not fixed
- Deviation: <convention the feature or the request departs from> - <why>
- Unverified: <what Step 10 could not check>
```

Warnings bullets appear only for the kinds that occurred, one per item. A stop emits `**Stack:**`, the design if one was reached, `## Assumptions` and `## Warnings`; the other sections are omitted, never emitted empty.

## Self-Check

Tick, or mark `N/A` with the reason the workflow authorized it.

- [ ] Step 1 - behavioral-principles loaded
- [ ] Step 2 - every generated construct binds on the build file's Boot and Java versions
- [ ] Step 3 - every requirement answered or defaulted into `## Assumptions`
- [ ] Step 4 - design approved, or gate skipped with every risky part held
- [ ] Step 5 - entity and migration match, constraints and indexes included
- [ ] Step 6 - lookups scoped like their indexes, lists paged
- [ ] Step 7 - money and idempotent writes race-safe, side effects durable where required
- [ ] Step 8 - every access rule enforced where it can be
- [ ] Step 9 - each case the feature has tested on the production engine
- [ ] Step 10 - imports resolved; compiled and tests run, or the gap recorded
- [ ] Every mandated output section present (a stop: its four)

## Avoid

- Generating code before requirements and design are settled or explicitly defaulted
- `@Autowired` field injection (constructor injection only)
