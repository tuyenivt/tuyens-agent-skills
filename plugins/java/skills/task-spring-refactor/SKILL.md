---
name: task-spring-refactor
description: "Spring Boot refactor plan: fat controllers, anemic domain, @Transactional misuse, field injection; phased steps with JUnit slice test gates."
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Refactor

Produce a safe, step-by-step refactoring plan for a Spring Boot target. Identifies Spring smells and proposes independently-committable steps with JUnit / slice test gates between each.

Stack-specific delegate of `task-code-refactor` for Java / Spring Boot.

## When to Use

- Spring code-smell identification and resolution
- Safe refactor of `@RestController` / `@Service` / `@Repository` / `@Entity` / configuration
- Pre-merge "this PR grew the fat-controller problem - what's the cleanup?"

**Not for:**
- Debt prioritization (use `task-debt-prioritize`)
- Feature changes (use `task-spring-implement`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-spring-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                    |
| --------------------- | ----------- | -------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, class, or package (e.g., `OrderController.java`)                                                         |
| Goal                  | Yes         | What the refactor should achieve (e.g., extract `OrderFulfillmentService`, kill `@PostUpdate` chain)           |
| Test coverage status  | Recommended | Whether JUnit / slice / Testcontainers coverage exists                                                         |
| Shared / public surface | Recommended | Whether the target crosses module / library / team boundaries                                                |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent dispatcher. If not Spring Boot, stop and tell the user to invoke `/task-code-refactor`.

### Step 3 - Read the Target

A refactor plan grounded in the user's prose hallucinates smells that aren't there and misses ones that are. Read source before classifying.

1. Read the target class top-to-bottom: method count, longest method, injection style, `@Transactional` placement, every external collaborator (`RestClient`, `KafkaTemplate`, mailers)
2. Read the matching test file; count cases by outcome (happy path, validation, external failure, security denial)
3. Read immediate callers (the controller that calls the service, the scheduled job) - removing or reshaping a public method without seeing call sites is how silent breakage happens

If the user named only the goal without a target file, ask for the target.

### Step 4 - Coverage Gate (mandatory)

Refactoring without coverage is a rewrite with extra steps.

1. Identify covering tests (`<Target>Test.java`, `@WebMvcTest(<Target>Controller.class)`, `@DataJpaTest`)
2. Assess - if missing or thin, **stop and require coverage first**. Recommend `task-spring-test`
3. If happy-path-only, flag boundary-test gap as a prerequisite step

**Output:** explicit status - `Adequate` / `Thin (boundary tests missing)` / `Inadequate (cannot proceed)`.

### Step 5 - Identify Spring Smells

For deeper diagnosis on any flagged smell, load the matching atomic rather than restating its rules:

- JPA / Hibernate (N+1, EAGER on `@OneToMany`, paginated `JOIN FETCH`, `MultipleBagFetchException`) → `spring-jpa-performance`
- `@Transactional` placement, propagation, self-invocation, IO-in-tx, post-commit → `spring-transaction`
- `@Async` / `@Scheduled` / event listener mis-wiring → `spring-async-processing`
- Kafka / Rabbit / outbox / idempotent consumer → `spring-messaging-patterns`
- `@RestControllerAdvice` / `ProblemDetail` refactor → `spring-exception-handling`
- Coverage gap filling → `spring-test-integration`

**Controller smells:**

| Smell                              | Signal                                                                                                              | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller                     | Method > 10 lines of orchestration (multiple service calls, conditional dispatch, response shaping)                 | High   |
| Logic in Controller                | Business rules, calculation, or domain decisions inside the handler                                                 | High   |
| Direct Repository in Controller    | Controllers bypass the service layer                                                                                | Medium |
| JPA Entity in API                  | Returns `@Entity` types or accepts entities as `@RequestBody` (mass assignment + lazy load risk)                    | High   |
| Manual Validation Duplicating DTO  | Controller re-checks `@NotNull` / `@Size` already on the DTO                                                        | Low    |

**Service smells:**

| Smell                              | Signal                                                                                                              | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service                        | `@Service` > 500 lines mixing orchestration / persistence / mapping / external clients / scheduling                 | High   |
| Anemic Domain                      | Entities are pure data; business rules in services like `OrderHelper.calculate(order)` belong on the entity         | High   |
| Single-Implementation Interface    | `OrderService` interface + lone `OrderServiceImpl` with no AOP / second impl / non-Mockito test seam                | Medium |
| `@Transactional` Self-Invocation   | `this.txMethod()` from a non-tx method in the same bean - proxy bypassed                                            | High   |
| `REQUIRES_NEW` Without Reason      | Propagation `REQUIRES_NEW` used without a written justification                                                     | Medium |
| External I/O Inside `@Transactional` | HTTP / message publish / file write inside the transaction (defers commit, holds DB locks)                        | High   |
| Service Returning Boolean          | Caller cannot distinguish validation vs not-found vs external failure                                               | Medium |

**Persistence / JPA smells:**

| Smell                              | Signal                                                                                                              | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Entity                         | `@Entity` > 300 lines mixing mapping / computed properties / business operations                                    | High   |
| `@PostUpdate` / `@PostPersist` Abuse | Lifecycle callback firing emails / events / external calls - races commit and breaks silently                     | High   |
| `FetchType.EAGER` on Collections   | Eager `@OneToMany` / `@ManyToMany` - cartesian explosion                                                            | High   |
| Repository Returning Unbounded List | `findAll()` / `findByX(...)` without `Pageable`                                                                    | Medium |
| Always-on Hibernate `@Filter`      | Silently mutates query results across the app                                                                       | High   |
| `@Query` String Concatenation      | Dynamic JPQL via string concat instead of `Specification` / Querydsl                                                | Medium |

**Configuration / DI smells:**

| Smell                              | Signal                                                                                                              | Risk   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| `@Autowired` Field Injection       | Breaks immutability, hurts testability, hides dependencies                                                          | High   |
| `@Value("${...}")` Field Injection | Scattered config; should be `@ConfigurationProperties` record                                                       | Medium |
| `ApplicationContextAware` Lookup   | Service locator antipattern                                                                                         | High   |
| Hidden `@ConditionalOnProperty`    | Bean conditional on a property with no off path                                                                     | Low    |

**Aspect / async / messaging:**

| Smell                                | Signal                                                                                                            | Risk   |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------- | ------ |
| Aspect as Hidden Control Flow        | `@Around` that swallows exceptions, rewrites returns, or short-circuits invisibly                                 | High   |
| `@KafkaListener` Without Idempotency | Re-runs side effects on redelivery (no dedup key, no upsert)                                                      | High   |
| `synchronized` on Virtual Thread Path | Pins the carrier thread - defeats Boot 3.2+ Virtual Threads                                                      | High   |
| `@Async` Without `TaskDecorator`     | Trace / MDC / SecurityContext lost across the boundary                                                            | Medium |

**Test smells (when in scope):**

| Smell                                         | Signal                                                                                  | Risk   |
| --------------------------------------------- | --------------------------------------------------------------------------------------- | ------ |
| `@SpringBootTest` for Unit Logic              | Full context for what could be plain JUnit + Mockito                                    | Medium |
| H2 in `@DataJpaTest` for Postgres-Feature App | Pass on H2, fail on JSONB / partial index / `ON CONFLICT` in prod                       | High   |
| `@DirtiesContext`                             | Used to work around shared state instead of fixing isolation                            | Medium |

Use skill: `backend-coding-standards` for cross-language smells. Use skill: `complexity-review` when the target shows over-engineering (single-impl interfaces, base classes for two children, premature Strategy/Factory, redundant mapping layers) - those are simplification opportunities.

Apply judgment: a 25-line `@Service` method with clearly named private steps is fine; a 10-line method doing three unrelated things is not.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. Spring-specific signals:

- **Public API surface** - target is a controller used by external clients
- **Library / module boundary** - `@AutoConfiguration`, published artifact, or starter
- **Aspect with broad pointcut** - `execution(* com.acme..*.*(..))` affects every match
- **Bean injected widely** - `@Bean` with > 10 callers; signature changes cascade
- **JPA entity used in many queries** - cascades through every `@Query` / `Specification`
- **`@Transactional` method called from outside** - removing `@Transactional` from a public method may silently break callers

State blast radius before proposing steps: **Narrow** / **Moderate** / **Wide** / **Critical**.

### Step 7 - Propose the Step Sequence

Each step is:

1. **Independently committable** - codebase compiles, suite passes
2. **Behaviorally invariant** - no behavior change unless explicitly noted
3. **Reversible** - one revert away
4. **Tested** - existing tests stay green; new tests added when extracting new units

**Transaction-boundary watch.** When extracting orchestration from a `@Transactional` method, the extracted unit inherits the transaction (via the proxy). If the extracted code does HTTP / Kafka / file writes, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's `@Transactional`" or "callee uses `@TransactionalEventListener(AFTER_COMMIT)` / outbox to defer side effects."

**Common recipes:**

**Extract service from fat controller**

1. Add `<Verb><Noun>Service` (e.g., `PlaceOrderService`) with one intention-revealing method returning a domain result type; copy logic from controller
2. Add `<Verb><Noun>ServiceTest` - one test per outcome
3. Controller calls the service; preserve response shape; `@WebMvcTest` passes unchanged
4. Remove the original controller logic; verify `@WebMvcTest`
5. Add `@WebMvcTest` asserting service failure surfaces as the expected error response (likely via `@RestControllerAdvice`)

**Convert `@PostUpdate` to `@TransactionalEventListener(AFTER_COMMIT)`**

1. Add a test pinning current observable behavior (record updated, email sent, event published)
2. Replace `@PostUpdate` with a domain event published from the service. Add listener (sync or `@TransactionalEventListener(AFTER_COMMIT)`)
3. Run tests; confirm pass. Side effects now post-commit
4. If callback was cross-aggregate work, extract the handler to its own `@Service`; remove the listener from the entity
5. Full suite; verify no code path still relies on the JPA callback

**Untangle fat controller + JPA-callback orchestration**

1. **Pin behavior** with a test asserting every observable side effect
2. **Promote callbacks to AFTER_COMMIT** by publishing a domain event from where the callback fires today. Side effects now post-commit; tests stay green
3. **Introduce a service** that owns orchestration; controller calls it. Audit other call sites (`save`, `merge`, scheduled jobs) and route them through the service
4. **Delete the entity-level callbacks**; service + AFTER_COMMIT listeners are the single source

Do not introduce a `ThreadLocal` "skip when called from service" flag - it traps the codebase. Promote to AFTER_COMMIT first, then move ownership.

**Split god service**

1. Identify orthogonal concerns (`OrderService` doing place + cancel + refund + reporting → `PlaceOrderService`, `CancelOrderService`, ...)
2. Extract one concern at a time; god service delegates temporarily
3. Update callers to inject the focused service; remove delegation
4. Repeat; delete the empty god service
5. Verify all callers still pass

**Eliminate single-implementation interface**

1. Confirm no test doubles, second impl, AOP target requirement
2. Inline: rename `OrderServiceImpl` → `OrderService`, delete the interface
3. Run tests
4. **Skip if** the interface is part of a published library API

**Migrate `@Autowired` field to constructor injection**

1. Verify the class isn't a Spring-instantiated bean that needs field injection (almost never)
2. Add a constructor accepting injected dependencies; mark fields `final`
3. Remove `@Autowired` annotations. Lombok `@RequiredArgsConstructor` works
4. Run tests; Mockito `@InjectMocks` continues to work

**Make `@KafkaListener` idempotent**

1. Test asserting the side effect happens exactly once when the same message is delivered twice (different offsets, same business key)
2. Idempotency guard: dedup table on message UUID, business-key upsert (`ON CONFLICT DO NOTHING`), or version check
3. Verify retries on transient failures still complete
4. Configure DLT so poison messages don't loop

**Move external I/O out of `@Transactional`** (most damaging smell)

A `@Service` method does DB write → HTTP call → DB write inside one `@Transactional`. Under load, the HTTP call holds a HikariCP connection for its full duration, exhausting the pool.

1. Add an integration test asserting current end-to-end behavior
2. Choose:
   - **Outbox** - within the transaction, write the side-effect intent to an `outbox` table; a separate scheduled poller (or AFTER_COMMIT) reads it and performs the I/O. Strongest guarantee.
   - **AFTER_COMMIT listener** - publish a domain event; listener performs HTTP after commit. Simpler, but at-most-once; if the listener fails, the side effect is lost.
3. Implement; transactional method now contains DB only; I/O moves to listener / poller
4. Run integration test - failure semantics changed (side effect now post-commit; HTTP failure no longer rolls back DB). Confirm acceptable
5. Audit retry/idempotency on the receiver

**State the failure-mode change in the step.** Old code rolled back the DB on a failed HTTP call; new code does not. If callers relied on the coupling, this is a behavioral change.

**Replace JPA entity in API with record DTO**

1. Define request record with Bean Validation
2. Define response record
3. Add explicit entity → response mapping in the service or dedicated mapper - inside `@Transactional` so lazy associations resolve
4. Update controller signatures; return record
5. Update `@WebMvcTest` to assert the new shape (no entity fields leaking)
6. Coordinate API consumers separately if they were depending on the old shape

**Fix `@Transactional` self-invocation**

See `spring-transaction` for the canonical fix patterns (extract to separate bean, self-injection, `TransactionTemplate`). Add a regression test asserting the transaction *actually starts* (a row written in the inner method is rolled back when an exception is thrown after the call returns).

**Replace `synchronized` on Virtual Thread paths**

1. Confirm the path runs under Virtual Threads (Boot 3.2+ + `spring.threads.virtual.enabled=true`)
2. Replace `synchronized` with `ReentrantLock` (or `StampedLock` for read-heavy paths)
3. Verify with a concurrency test
4. Audit other `synchronized` blocks in the same module

### Step 8 - Validate Plan Against Goal

- [ ] Goal achieved at end of sequence
- [ ] Each step < 30 minutes to review
- [ ] Tests run between every step
- [ ] Low-risk first (extracts, additions) before high-risk (deletions, signature changes)
- [ ] Rollback is one revert per step
- [ ] No "while we're here" cleanup bundled in

## Output Format

```markdown
## Spring Boot Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Stack:** Java <version> / Spring Boot <version>

## Coverage Gate

**Status:** Adequate | Thin (boundary tests missing) | Inadequate (cannot proceed)

[If Inadequate: what coverage must exist; recommend `task-spring-test` first.]

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [paragraph citing callers, tests, public surface]

## Step Sequence

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Test gate:** [JUnit / `@WebMvcTest` / `@DataJpaTest` / `@SpringBootTest`]
- **Transaction stance:** [inside caller's `@Transactional` | AFTER_COMMIT | not transactional]
- **Rollback:** [how to revert in one revert]

[... continue numbering ...]

## Verification

- [ ] Goal achieved: [restate goal]
- [ ] Each step independently committable
- [ ] Test suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback is one revert per step
- [ ] No I/O silently moved across `@Transactional` boundaries

## Out of Scope

[Adjacent improvements NOT in this plan]
```

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed (or accepted from parent dispatcher)
- [ ] Target file(s) and tests read directly - no smells inferred from prose
- [ ] Coverage gate evaluated; refused to proceed if inadequate
- [ ] Spring smells identified from Step 5 catalog
- [ ] Blast radius stated before steps
- [ ] Each step independently committable with explicit test gate
- [ ] Transaction stance stated per step
- [ ] Low-risk first; no unrelated cleanup bundled
- [ ] Goal mapped to end state; rollback is one revert per step

## Avoid

- Refactor without a coverage gate - that's a rewrite
- Bundling behavior changes with refactor steps - keep separate, label
- "While we're here" cleanups - their own PR
- Renaming during refactor - rename PRs are separate
- Removing JPA `@PostUpdate` / `@PostPersist` without a test asserting the original behavior
- Extracting an interface with one implementation - wait for the second use case
- Fixing `@Transactional` self-invocation by adding `@Transactional` to the inner method without restructuring the call - proxy is still bypassed
- Moving HTTP / message publish across `@Transactional` boundaries without explicit transaction stance
- Refactoring `@AutoConfiguration` without a backward-compatibility plan - published API
- `synchronized` → `ReentrantLock` on a non-VT path with no concurrency benefit
