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

Use skill: `stack-detect`. Establish Java version, Spring Boot version, build tool (Gradle vs Maven), Lombok presence, mapper library (MapStruct vs hand-written), web stack (servlet vs reactive - when both starters are present, servlet wins at runtime), **and the production database engine** - Steps 5 and 9 branch on it. If not Spring Boot, stop.

Below the 3.5+ / Java 21+ floor this skill targets: do not stop. Generate for the detected version, and record every construct you had to downgrade as a warning. Version-gated constructs to check: `@MockitoBean` (Boot 3.4+; below that `@MockBean`), `@ServiceConnection` (Boot 3.1+), records and pattern matching (Java 17+), virtual threads (Java 21+). Anything you cannot observe (engine, Java toolchain) becomes a stated assumption, not a silent guess.

### Step 3 - Gather Requirements

Ask and lock down before any design:

1. Feature name, package base, primary use case
2. Operations (CRUD plus custom verbs such as approve, cancel, transition)
3. Entity fields, types, validation constraints, relationships (and fetch type expectations)
4. Derived or aggregate reads (counts, averages, rollups) - each one is either computed per request or denormalized onto a column, and that choice decides whether an existing table needs a migration
5. Status field and allowed transitions, if any
6. Idempotency / deduplication needs (payments, external callbacks), and the scope the key is unique within (per caller / per tenant / global)
7. Access rule per operation: public, authenticated, role-restricted, owner-restricted, or machine-to-machine (webhook, partner callback) - plus, for owner-restricted, how the authenticated principal maps to the owning domain id, and for role-restricted, how the role reaches Spring Security as a `GrantedAuthority`
8. Async dispatch points (events fired after commit)

**Degraded input.** Feature name only -> ask for fields and operations. Existing entity referenced -> read it and follow its conventions; the feature still gets a migration unless it adds no columns and no table. Referenced entity missing -> ask before assuming. **Answers incomplete for any reason** - no interactive user, or a user who stops answering - proceed on your own defaults for the unanswered items and record each one under `## Assumptions`. Defaults when unstated: package base from the existing source root (or the feature name under the root package when the project is empty), page size 20, `Long` surrogate PK, aggregate reads computed per request rather than denormalized, only the transitions the request names with every other state terminal, idempotency keys unique **per calling principal** rather than globally, and the most restrictive access rule the operation can plausibly carry - role-restricted for an administrative verb, owner-restricted when the entity carries an owner column, authenticated otherwise. Stop only when fields or operations cannot reasonably be inferred.

### Step 4 - Design (Approval Gate)

Present and wait for explicit approval:

- Endpoint table (method, URI, access rule, request/response DTO records, status codes)
- Entity model + Flyway DDL outline (indexes, FK, CHECK constraints for status enums, unique index for idempotency keys)
- Service method signatures + transaction boundaries (read-only default, write boundaries)
- Domain exception hierarchy + HTTP status mapping
- Post-commit dispatch points (which transaction commits, what fires after)

**When approval cannot be obtained** - no interactive user, or the user does not answer - state the design, record the assumptions, set `Design gate` in the output to `skipped (<reason>)`, and generate. Do not stall. Rejection loops back to Step 3 for the disputed answers, then re-presents this step.

### Step 5 - Entity + Migration

Use skill: `spring-jpa-performance`, `spring-db-migration-safety`.

Entity is a class (records cannot be JPA entities). Audit fields via `@MappedSuperclass` base + `AuditingEntityListener` **when the project already has that base** - otherwise `@EntityListeners` on the entity rather than introducing a base class for one aggregate; either way auditing no-ops unless `@EnableJpaAuditing` is on a configuration class, so add it if absent. Validation constraints live on request DTOs (Step 8); the entity mirrors them as DB constraints (`@Column` attributes matching the Flyway DDL exactly - `precision`/`scale` only for `BigDecimal`; money held as minor units is a `Long`/`BIGINT`), not duplicate Bean Validation annotations. LAZY on all associations; a foreign key that is never navigated is a plain id field, not a `@ManyToOne`. Status enums get a CHECK constraint; value invariants (non-negative balance, date ordering) get CHECKs too - write them so a NULL column cannot pass, since `NULL OR FALSE` is NULL. FK and frequently-filtered columns get indexes.

Idempotency keys get a unique index **scoped the way Step 3 answered** - a globally unique key lets one caller's key collide with another's, and replay then returns the wrong caller's resource. Idempotent creates put the key on the aggregate; an idempotent operation verb (redeem, capture) instead gets a child operation record owning the key and storing the response fields replayed on duplicates.

Soft delete (when required): `deleted_at` column plus `@SQLDelete` + `@SQLRestriction` on the entity, which filters every JPQL and derived query automatically - repository-level filtering instead means every read, **including the aggregate queries of Step 6**, must remember the predicate, and native queries bypass both. A uniqueness rule that must allow re-creation after delete needs a partial unique index (`... WHERE deleted_at IS NULL`) - a plain unique constraint blocks the re-create. MySQL has no partial indexes: add `active TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL))` and include it in the unique index (NULLs never collide); write `STORED` when you want the value materialized, though InnoDB indexes a VIRTUAL generated column too. A generated column is either left out of the entity or mapped `insertable = false, updatable = false`; mapping it plainly breaks every insert.

### Step 6 - Repository

Extend `JpaRepository<{Name}, {PK type}>`. Derived methods for simple filters; `@Query` only when names become unwieldy; `Specification` when an endpoint has 2+ optional filters. `Page<>` for all list endpoints. Aggregate reads (Step 3 item 4) computed per request are an aggregate `@Query` returning a projection interface or record, never a full-collection load; a soft-deleted row must not reach an aggregate. Idempotent writes need a lookup **scoped exactly like the unique index** (`findByMerchantIdAndIdempotencyKey`, not `findByIdempotencyKey`) - an unscoped lookup returns another caller's resource before the index is ever consulted.

### Step 7 - Service

Use skill: `spring-transaction`, `spring-exception-handling`.

`@Service @Transactional(readOnly = true) @RequiredArgsConstructor @Slf4j` (Lombok annotations only if the project already uses Lombok; otherwise explicit constructor + logger). Read-write `@Transactional` only on mutating methods. Entity-to-DTO via record static factory (`XxxResponse.from(entity)`) unless Step 2 found a mapper library the project standardizes on; never return entities. Status transitions validated against an allowed-transitions map before persistence; invalid transitions throw a domain exception - except a re-delivered external callback re-asserting the state a row already holds, which is a replay and returns the current resource, not a 409 the partner will retry forever.

**Contended mutations** (balances, counters, stock, and any status transition two callers can race) need `@Version` on the entity when the read-modify-write spans multiple fields or must fail loudly - map `OptimisticLockingFailureException` to 409; use one atomic conditional `UPDATE ... WHERE status = :expected` instead when the change is a single-column transition and a silent no-op row count is the signal you want.

**Idempotent creates need the race handled, not just the lookup.** Lookup then insert is check-then-act: concurrent callers both miss and one dies on the unique index. Force the insert with `saveAndFlush` so the violation surfaces inside your own `try` - a plain `save` defers it to commit, after the method has returned, and the catch never runs. Catch `DataIntegrityViolationException` and re-read the winner's row, but the failed insert marks the current transaction rollback-only, so that re-read must run in a separate transaction (a collaborator bean with `@Transactional(propagation = REQUIRES_NEW)`; self-invocation bypasses the proxy). If the re-read finds nothing, the violation was a different constraint - rethrow. Replay of the same key with a *different* payload is a conflict, not a replay: store a payload fingerprint alongside the key and return 409.

Post-commit side effects via `ApplicationEventPublisher` + `@TransactionalEventListener(AFTER_COMMIT)`. That listener is in-process and not durable - when the side effect must survive a crash (payment capture, partner submission), pair it with an outbox row or a reconciliation job.

### Step 8 - Controller

Use skill: `spring-exception-handling`. When any Step 3 access rule is not `public`, also Use skill: `spring-security-patterns`.

`@RestController @RequestMapping` + constructor injection (Lombok's `@RequiredArgsConstructor` only if the project uses Lombok). `@Valid @RequestBody` on writes - and `@Valid` validates nothing unless the request record's components carry the Step 3 constraints (`@NotBlank`, `@Size`, `@Min`/`@Max`, `@Email`, `@Pattern`), so put them there now. `Pageable` on list. `@RequestParam(required = false)` for filters. `201 CREATED` on POST that creates, `200 OK` when an idempotent POST replays an existing resource, `204 NO_CONTENT` on DELETE, custom verbs as `POST /{id}/{verb}`. Request and Response DTOs are records.

Class-level `@RequestMapping` is the longest prefix every method in the class shares. A sub-resource split across two URI spaces (`POST /api/v1/products/{id}/reviews` for creation and listing, `/api/v1/reviews/{id}` for direct access) shares no prefix - drop the class-level mapping and write full paths on each method, or split into two controllers.

**Enforce each access rule where it can actually be enforced** - a gathered access requirement that no step implements has silently evaporated:

| Access rule       | Where it goes                                                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Public            | `permitAll` matcher placed **above** the chain's `anyRequest()` rule - appended after it, the matcher never matches                 |
| Authenticated     | Covered by the chain's `anyRequest().authenticated()`; no annotation needed                                                        |
| Role-restricted   | `@PreAuthorize("hasRole('X')")` on the handler, where `X` omits the `ROLE_` prefix that `hasRole` adds. The annotation is inert unless `@EnableMethodSecurity` is on a configuration class - add it if absent - and on a JWT resource server the default converter emits `SCOPE_*` authorities only, so a role claim needs a `JwtGrantedAuthoritiesConverter` or the check denies everyone |
| Owner-restricted  | Not expressible at method entry - the row is not loaded yet. `@PreAuthorize("isAuthenticated()")` on the handler, and the service either loads scoped (`findByIdAndOwnerId`, which yields 404 on someone else's row) or loads then compares the principal to the owner (403). Pick one deliberately: it decides what Step 9's denied-case test asserts |
| Machine-to-machine | Its own `@Order`ed, path-scoped `SecurityFilterChain` (shared credential, mTLS, or signature check with a constant-time compare) - a webhook cannot authenticate against the app's user chain |

### Step 9 - Tests

Use skill: `spring-test-integration`.

- Service unit: plain Mockito, `@ExtendWith(MockitoExtension.class)`
- Repository: `@DataJpaTest` + Testcontainers matching production, never H2. `@DataJpaTest` swaps in an embedded DataSource by default, so the container must be bound with `@ServiceConnection` (Boot 3.1+) or `@AutoConfigureTestDatabase(replace = NONE)` - without it the container starts and the test silently runs on H2. Let the migrations build the schema, not `ddl-auto`, or the CHECK constraints and unique indexes from Step 5 are absent from the tested schema. **When the project's existing suite runs on H2 and has no Testcontainers**, adopt it for this feature's repository tests only, list the dependencies as part of the deliverable (`spring-boot-testcontainers` plus the engine module and `junit-jupiter`), and record the split convention and the new Docker requirement under `## Warnings` - do not migrate the existing suite, and do not silently keep H2 for schema Hibernate cannot reproduce
- Controller: `@WebMvcTest` + MockMvc, `@MockitoBean` (Boot 3.4+). The slice does not pick up the `@Configuration` carrying `@EnableMethodSecurity`, so a `@PreAuthorize` role test passes vacuously unless you `@Import` it. Authenticated requests need `spring-security-test` post-processors - `.with(jwt())` on a resource server, `@WithMockUser` on a form-login or basic chain, and `.with(user(<custom principal>))` / `@WithUserDetails` whenever the owner check reads a project-specific principal, since `@WithMockUser` installs a plain `User` that carries no domain id. State-changing requests need `.with(csrf())` whenever the production chain has CSRF enabled - and if that chain is session-based, the production client also needs a token source (`CookieCsrfTokenRepository.withHttpOnlyFalse()` plus the `X-XSRF-TOKEN` header), or the endpoints pass their tests and 403 in the browser

Cover: happy path, not-found, validation errors, filter/search, each access rule (allowed and denied), invalid state transition (409 or 422), plus the duplicate-POST case the feature actually has - business-dedup uniqueness (one X per Y) -> 409 conflict; idempotency-key replay -> original response returned; same key, different payload -> 409. Test only the cases the feature has.

### Step 10 - Validate

Compile with the build tool Step 2 detected (`./gradlew compileJava compileTestJava` or `./mvnw test-compile`), then run the tests - compilation alone proves nothing about the race, constraint, and authorization assertions Step 9 just wrote. Fix what fails and re-run; report a suite still red with the failing test names. If no build wrapper is runnable, verify statically and record that under `## Warnings`.

## Output Format

```markdown
## Generated Files

- Entity: `src/main/java/.../entity/{Name}.java`
- DTOs: `src/main/java/.../dto/{Name}Request.java`, `{Name}Response.java`
- Repository: `src/main/java/.../repository/{Name}Repository.java`
- Service: `src/main/java/.../service/{Name}Service.java`
- Controller: `src/main/java/.../controller/{Name}Controller.java`
- Migration: `src/main/resources/db/migration/...` - version prefix and naming follow the project's existing migration files, or `V1__create_{table}.sql` when the project has none; omit this entry entirely when the feature adds no schema
- Tests: service unit, `@DataJpaTest` repository, `@WebMvcTest` controller
- Supporting: domain exceptions, config beans, extra DTOs/projections, test fixtures - whatever Steps 4-9 produced
- Modified: existing files this feature edits - build file, `SecurityFilterChain`, `@RestControllerAdvice`, enabling configuration - each with what changed

## Endpoints

| Method | URI | Access | Status | Description |
| ------ | --- | ------ | ------ | ----------- |
| ... | one row per endpoint this feature actually has | ... | ... | ... |

## Tests

- Unit: {count}
- Repository: {count}
- Controller: {count}
- Suite result: {passed | failed - <failing test names> | not run - <reason>}

## Assumptions

One bullet per requirement answered by default rather than by the user, and per unobservable stack fact. `None` when every answer came from the user.

## Warnings

Design gate: approved | skipped (<reason>)

- Constructs downgraded for the detected Spring Boot / Java version
- Conventions this feature deviates from, and why
- Anything Step 10 could not verify
```

## Self-Check

Tick, or mark `N/A` with the reason the workflow authorized it.

- [ ] Step 1 - behavioral-principles loaded
- [ ] Step 2 - stack detected: Java and Boot versions, build tool, Lombok, DB engine; below-floor downgrades recorded
- [ ] Step 3 - requirements gathered; access rule per operation, aggregate reads, transitions, and idempotency scope resolved or defaulted into `## Assumptions`
- [ ] Step 4 - design approved, or gate recorded as skipped with its reason
- [ ] Step 5 - entity and migration match (columns, constraints, indexes); CHECKs null-safe; idempotency key scoped
- [ ] Step 6 - `Page<>` on lists; aggregate reads projected, not collection-loaded; idempotency lookup present when needed
- [ ] Step 7 - `readOnly = true` default with write boundaries on mutations; DTO mapping via records; transition map enforced; contended mutations guarded; idempotent-create race handled in a separate transaction
- [ ] Step 8 - controller returns DTOs; correct status codes including idempotent replay; `@Valid` on writes; every Step 3 access rule enforced at the layer that can enforce it
- [ ] Step 9 - container actually bound (`@ServiceConnection` / `replace = NONE`) and schema from migrations, or the H2-suite split recorded in `## Warnings`; method security imported into the slice; security post-processors matching the chain, custom principal where ownership needs one, CSRF where prod has it; the feature's applicable duplicate-POST and transition cases covered
- [ ] Step 10 - compiled and tests run (or the gap recorded in `## Warnings`)
- [ ] Every mandated output section present: files, endpoints with access, test counts, assumptions, warnings

## Avoid

- Generating code before requirements and design are settled or explicitly defaulted
- Exposing JPA entities in API responses (always DTO records)
- `@Autowired` field injection (constructor injection only)
- `@MockBean` on Boot 3.4+ (deprecated; use `@MockitoBean`)
- Unbounded `findAll()` without pagination
- Loading a full collection to compute a count or average the database can aggregate
- Treating a unique index as the whole idempotency implementation - it is the backstop, not the path
