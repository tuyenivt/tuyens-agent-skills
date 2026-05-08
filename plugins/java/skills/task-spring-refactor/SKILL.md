---
name: task-spring-refactor
description: Spring Boot refactor planning for fat controllers, anemic domain, service god-objects, missing layer boundary, `@Transactional` misuse, callback-via-JPA-listener overuse, single-implementation interface bloat, and `@Autowired` field injection. Produces a step-by-step sequence of independently-committable Spring refactoring steps with a JUnit / Spring slice test coverage gate. Stack-specific override of task-code-refactor for Java/Spring Boot.
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spring Boot Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Spring Boot target (controller, service, repository, JPA entity, configuration class, aspect). Identifies Spring-specific smells (fat controllers, anemic domain, service god-objects, `@Transactional` misuse, single-impl interfaces, `@Autowired` field injection, JPA-listener callback abuse) and proposes independently-committable refactoring steps with JUnit / Spring slice test gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Java/Spring Boot.

## When to Use

- Spring Boot code-smell identification and resolution
- Spring technical-debt reduction with a concrete plan
- Safe refactoring of a `@RestController` / `@Service` / `@Repository` / `@Entity` / configuration class
- Pre-merge "this PR grew the fat-controller / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-spring-implement`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-spring-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                  |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, class, or package to refactor (e.g., `OrderController.java`, `com.acme.order.service.OrderService`)                    |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `OrderFulfillmentService`, kill `@PostUpdate` chain, split `UserService`) |
| Test coverage status  | Recommended | Whether JUnit / Spring slice / Testcontainers coverage exists for the target area                                            |
| Shared/public surface | Recommended | Whether the target is used across module / library / team boundaries                                                         |

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Java / Spring Boot. If invoked as a subagent of a Spring-aware parent, accept the pre-confirmed stack. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-refactor` instead.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target class top-to-bottom; note method count, longest method, field injection vs constructor injection, `@Transactional` placement, every external collaborator (`RestClient`, `KafkaTemplate`, `JmsTemplate`, mailers).
2. Read the matching test file (e.g., `OrderServiceTest.java`, `@WebMvcTest(OrderController.class)`); count cases by outcome (happy path, validation failure, external failure, security denial).
3. If callers are obvious (controller calling the service, scheduled job calling the service), read the immediate caller too - removing or reshaping a public method without seeing call sites is how silent breakage happens.

If the user named only the goal without a target file, ask for the target before proceeding. Do not guess.

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Before proposing any refactor:

1. Identify the tests covering the target (`<Target>Test.java`, `<Target>IntegrationTest.java`, `@WebMvcTest(<Target>Controller.class)`, `@DataJpaTest` for repositories)
2. Run coverage assessment - if coverage is missing or thin, **stop and require coverage first** before proposing refactor steps. Recommend `task-spring-test` to fill gaps
3. If coverage exists but is happy-path-only, flag the boundary-test gap as a prerequisite step in the plan (refactor must not silently change validation / 401 / 403 / not-found behavior)

**Output of this step:** explicit coverage status - `Adequate` / `Thin (boundary tests missing)` / `Inadequate (refuse to proceed without coverage)`. Do not proceed past Step 4 if coverage is inadequate.

### Step 4 - Identify Spring Smells

Inspect the target for these Spring-specific smells. Use judgment - these are signals, not hard rules.

**Controller smells:**

| Smell                                         | Signal                                                                                                             | Risk   |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------ |
| Fat Controller                                | Controller method > 10 lines of orchestration (multiple service calls, conditional dispatch, response shaping)     | High   |
| Logic in Controller                           | Business rules, validation beyond Bean Validation, calculation, or domain decisions inside the handler             | High   |
| Direct Repository in Controller               | Controllers call `@Repository` methods directly, bypassing the service layer                                       | Medium |
| JPA Entity in API                             | `@RestController` returns `@Entity` types or accepts entities as `@RequestBody` (mass assignment + lazy load risk) | High   |
| Manual Validation Duplicating Bean Validation | Controller body re-checks `@NotNull` / `@Size` constraints already on the DTO                                      | Low    |

**Service smells:**

| Smell                                         | Signal                                                                                                                                           | Risk   |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| God Service                                   | `@Service` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                  | High   |
| Anemic Domain                                 | Entities are pure data containers; business rules live in services with names like `OrderHelper.calculate(order)` and could belong on the entity | High   |
| Single-Implementation Interface               | `OrderService` interface + single `OrderServiceImpl` with no test double, no second implementation, no AOP target                                | Medium |
| `@Transactional` Self-Invocation              | `this.transactionalMethod()` called from a non-transactional method in the same bean - proxy bypassed, transaction silently does not start       | High   |
| `@Transactional(REQUIRES_NEW)` Without Reason | Propagation `REQUIRES_NEW` used without a comment explaining why outer rollback should not propagate                                             | Medium |
| External I/O Inside `@Transactional`          | HTTP call, message publish, or file write inside a transactional method (defers commit, holds DB locks long)                                     | High   |
| Service Returning Boolean                     | Service returns `boolean`; caller cannot distinguish failure cases (validation vs not-found vs external)                                         | Medium |

**Persistence / JPA smells:**

| Smell                                                   | Signal                                                                                                                     | Risk   |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Entity                                              | `@Entity` > 300 lines; mixes mapping, computed properties, business operations, mapping helpers                            | High   |
| `@PostUpdate` / `@PostPersist` Abuse                    | JPA lifecycle callback dispatching emails, publishing events, calling external services - races commit and silently breaks | High   |
| `FetchType.EAGER` on Collections                        | Eager fetch on `@OneToMany` / `@ManyToMany` - cartesian explosion + locks lazy semantics elsewhere                         | High   |
| Repository Returning `List` for Unbounded Reads         | `findAll()`, `findByX(...)` without `Pageable` parameter                                                                   | Medium |
| `default_scope`-equivalent Hibernate `@Filter` Surprise | Hibernate `@Filter` always-on, silently mutating query results across the app                                              | High   |
| `@Query` String Concatenation                           | Dynamic JPQL built via string concat instead of `Specification` / `Querydsl` / `JpaSpecificationExecutor`                  | Medium |

**Configuration / DI smells:**

| Smell                              | Signal                                                                                             | Risk   |
| ---------------------------------- | -------------------------------------------------------------------------------------------------- | ------ |
| `@Autowired` Field Injection       | `@Autowired private SomeBean bean;` - breaks immutability, hurts testability, hides dependencies   | High   |
| `@Autowired` Setter Injection      | Same problems plus mutable bean state                                                              | Medium |
| `@Value("${...}")` Field Injection | Single config values scattered across classes; should be `@ConfigurationProperties` record         | Medium |
| `ApplicationContextAware` Lookup   | Service uses `ApplicationContext.getBean(...)` for cross-bean lookup - service locator antipattern | High   |
| Hidden `@ConditionalOnProperty`    | Bean conditional on a property with no off path (no environment ever sets it false)                | Low    |

**Aspect / interceptor smells:**

| Smell                         | Signal                                                                                                       | Risk   |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| Aspect as Hidden Control Flow | `@Around` aspect that can swallow exceptions, rewrite return values, or short-circuit method calls invisibly | High   |
| Aspect Across Many Pointcuts  | One `@Aspect` class with > 3 unrelated `@Around` advices - split per-concern                                 | Medium |

**Async / messaging smells:**

| Smell                                 | Signal                                                                                                 | Risk   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------ |
| `@Async` Doing Too Much               | Single `@Async` method orchestrating 4+ business steps without sub-services                            | Medium |
| `@KafkaListener` Without Idempotency  | Listener that re-runs side effects when the same message is delivered twice (no dedup key, no upsert)  | High   |
| `synchronized` on Virtual Thread Path | `synchronized` block in a `@Service` running under Boot 3.2+ Virtual Threads - pins the carrier thread | High   |
| `@Async` Without `TaskDecorator`      | Trace context, MDC, and `SecurityContext` lost across the async boundary                               | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                                         | Signal                                                                               | Risk   |
| --------------------------------------------- | ------------------------------------------------------------------------------------ | ------ |
| `@SpringBootTest` for Unit Logic              | Full context loaded for what could be a plain JUnit + Mockito test                   | Medium |
| H2 in `@DataJpaTest` for Postgres-feature App | Tests pass on H2 but fail in prod on JSONB / partial index / `ON CONFLICT` semantics | High   |
| `@DirtiesContext`                             | Used to work around shared state instead of fixing isolation                         | Medium |

**General OO smells (apply with Spring judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, base classes for two children, premature `Strategy`/`Factory`, redundant mapping layers) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Spring judgment - a 25-line `@Service` method orchestrating clearly named private steps is fine; a 10-line method doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

Spring-specific blast-radius signals:

- [ ] **Public API surface**: target is a controller used by external clients - refactor risks API contract change
- [ ] **Library / module boundary**: target is in a `@AutoConfiguration` class, a published artifact, or a Spring Boot starter consumed by other apps
- [ ] **Aspect with broad pointcut**: refactoring an aspect with a `execution(* com.acme..*.*(..))` pointcut affects every matching method
- [ ] **Bean injected widely**: target is a `@Bean` injected into > 10 callers - signature changes cascade
- [ ] **JPA entity used in many queries**: refactoring an entity affects every `@Query` / `Specification` / `JpaSpecificationExecutor`
- [ ] **`@Transactional` method called from outside**: removing `@Transactional` from a public method may silently break callers depending on its boundary

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single module, multiple callers) / **Wide** (cross-module, public API, broad aspect) / **Critical** (`@AutoConfiguration` published, entity used by 5+ services).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing JUnit / slice / Testcontainers suite continues to pass; new tests added when extracting new units

**Transaction-boundary watch.** When extracting orchestration that runs inside a `@Transactional` method, the extracted unit inherits the transaction context (via the proxy when called from the original entry point). If the extracted code makes HTTP calls, publishes Kafka messages, or writes files, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's `@Transactional`" or "callee uses `@TransactionalEventListener(phase = AFTER_COMMIT)` / outbox to defer side effects." Never silently move I/O across a transaction boundary.

**Common Spring refactor recipes:**

**Recipe: Extract service from fat controller**

1. Add `<Verb><Noun>Service` (e.g., `PlaceOrderService`) with a single intention-revealing method returning a domain result type (record or sealed interface); copy logic from controller; controller still does the original work
2. Add `<Verb><Noun>ServiceTest` with one test per outcome (success, validation failure, external failure)
3. Update controller to call the service; preserve response shape; ensure `@WebMvcTest` slice test passes unchanged
4. Remove the original logic from the controller; verify `@WebMvcTest` passes
5. Add a `@WebMvcTest` example asserting service failure surfaces as the expected error response (likely via `@RestControllerAdvice`)

**Recipe: Convert `@PostUpdate` / JPA lifecycle callback to `@TransactionalEventListener(AFTER_COMMIT)`**

1. Add a `@SpringBootTest` (or focused `@DataJpaTest` + service test) reproducing the current observable behavior (record updated, email sent, event published)
2. Replace the JPA `@PostUpdate` with a domain event published from the service: `applicationEventPublisher.publishEvent(new OrderUpdated(orderId))`. Add an `@EventListener` (or `@TransactionalEventListener(phase = AFTER_COMMIT)`) for the side effect
3. Run tests; confirm pass. Side effects now fire post-commit instead of mid-transaction
4. If callback was doing cross-aggregate work, extract the side-effect handler into its own `@Service`; remove the listener from the entity class
5. Run the full suite; verify no orphan code paths still rely on the JPA lifecycle callback

**Recipe: Untangle fat controller + JPA-callback orchestration (combined case)**

The most common Spring Boot refactor: a controller endpoint triggers an entity write whose `@PostUpdate` / `@PostPersist` callbacks fan out (mailers, message publishes, audit writes). Removing the callbacks and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

1. **Pin behavior with a `@SpringBootTest` (or `@WebMvcTest` + service test)** asserting every observable side effect (record updated, mailer queued, event published, audit row written) - this is the contract the refactor must preserve
2. **Promote JPA callback to `@TransactionalEventListener(AFTER_COMMIT)`** first if callbacks publish events / send mail mid-transaction; tests still pass, but side effects now fire post-commit
3. **Introduce a service** (`<Verb><Noun>Service`) that performs the write _and_ the side effects in one method; controller calls the service _but the JPA callbacks still run_ - this duplicates side effects intentionally and temporarily
4. **Make callbacks no-op when called from the service** via a `ThreadLocal` flag set by the service or a domain-event-vs-callback dedup key (`if (event.source() == ServiceContext.SERVICE) return;`); verify tests still pass with side effects firing exactly once. **This flag is a scaffold, not a feature.** Add a `// TODO: DELETE WITH CALLBACKS IN STEP 5` comment at the call site.
5. **Delete the JPA callbacks entirely**; the service is now the single source of orchestration; remove the bypass flag and the `ThreadLocal` plumbing; tests still green
6. **Audit other call sites** (`@Repository.save` / `entityManager.merge` / scheduled jobs / migrations) - any caller relying on the old callbacks is now broken and must be updated to call the service or have the side effects re-derived

The intermediate "callbacks no-op when called from service" step is the safety net - it keeps the codebase shippable between the introduction of the service (step 3) and the deletion of the callbacks (step 5). If step 5 is skipped, the `ThreadLocal` becomes a permanent fixture and the codebase ends up worse than it started; landing steps 3-5 in separate PRs is acceptable only if step 5 has a tracked owner and deadline.

**Recipe: Split god service into focused services**

1. Identify the orthogonal concerns inside the service (e.g., `OrderService` doing place + cancel + refund + reporting → split into `PlaceOrderService`, `CancelOrderService`, `RefundOrderService`, `OrderReportService`)
2. Extract one concern at a time into a new `@Service` with clear constructor injection; original god service delegates to it temporarily
3. Update callers to inject and call the new focused service directly; remove delegation from god service
4. Repeat until god service is empty; delete it. Each extraction commits independently
5. Verify all `@WebMvcTest` / `@SpringBootTest` callers still pass

**Recipe: Eliminate single-implementation interface**

1. Confirm the interface has no test doubles, no second implementation, no AOP target requirement (some AOP cases need an interface for JDK proxies)
2. Inline the interface: rename `OrderServiceImpl` → `OrderService`, delete the interface, update callers (most cases the IDE rename handles it)
3. Run tests; confirm pass. Caller code is shorter and clearer
4. **Skip if** the interface is part of a published library API or has a real second implementation - the smell is fake

**Recipe: Migrate `@Autowired` field injection to constructor injection**

1. Verify the class is not a Spring-instantiated bean that must use field injection (rare; almost never the case)
2. Add a constructor accepting the injected dependencies as parameters; mark fields `final`
3. Remove `@Autowired` annotations on fields. Lombok `@RequiredArgsConstructor` works if the project already uses Lombok
4. Run tests; confirm pass. Mockito `@InjectMocks` continues to work
5. Repeat per class; one class per commit if the suite is slow

**Recipe: Make `@KafkaListener` idempotent**

1. Add a listener test asserting the side effect happens exactly once when the same message is delivered twice (different offsets, same business key)
2. Add an idempotency guard: dedup table keyed by message UUID, business-key upsert (`ON CONFLICT DO NOTHING`), or version check
3. Verify retries on transient failures still complete the work
4. Configure DLT (`spring.kafka.listener.ack-mode: manual_immediate` + retry / DLT topic) so poison messages do not loop forever

**Recipe: Move external I/O out of `@Transactional`**

The most damaging Spring smell: a `@Service` method does DB write -> HTTP call -> DB write all inside one `@Transactional`. Under load the HTTP call holds a HikariCP connection for its full duration, exhausting the pool.

1. Add an integration test asserting current observable behavior end-to-end (DB row state, side effect fired)
2. Decide the new ordering. Two viable shapes:
   - **Outbox pattern:** within the transaction, write the side effect intent to an `outbox` table; a separate scheduled poller (or `@TransactionalEventListener(AFTER_COMMIT)`) reads the outbox and performs the I/O. Strongest delivery guarantee.
   - **Defer side effect to `@TransactionalEventListener(AFTER_COMMIT)`:** publish a domain event from the service; a listener performs the HTTP call after commit. Simpler, but at-most-once - if the listener fails, the side effect is lost.
3. Implement the chosen shape. The transactional method now contains only DB work; the I/O moves to the listener / poller
4. Run the integration test - failure semantics changed (the side effect now fires after commit, not before; if the I/O fails, the DB write still stands). Confirm this is acceptable for the use case
5. Audit retry/idempotency: if the side effect can be retried, the listener / poller must be idempotent against the receiver

**State the failure-mode change explicitly in the step.** The old code rolled back the DB on a failed HTTP call; the new code does not. If callers relied on that coupling, this is a behavioral change, not a pure refactor.

**Recipe: Replace JPA `@Entity` in API with record-DTO**

`@RestController` accepting or returning `@Entity` types causes mass-assignment, lazy-load failures, and accidentally exposes internal columns.

1. Define a request record (e.g., `record CreateOrderRequest(@NotBlank String customerEmail, @Positive int quantity) {}`) with Bean Validation annotations
2. Define a response record (e.g., `record OrderResponse(UUID id, String status, BigDecimal total) {}`)
3. Add explicit mapping from entity to response record in the service or a dedicated mapper - inside the `@Transactional` boundary so lazy associations resolve
4. Update controller signature: `@RequestBody @Valid CreateOrderRequest`, return `OrderResponse`
5. Update `@WebMvcTest` to assert the new shape (no entity fields leaking)
6. Verify no other callers were depending on the entity shape over the wire (API consumers must be coordinated separately if so)

**Recipe: Fix `@Transactional` self-invocation**

`methodA()` calls `this.methodB()`; `methodB` is `@Transactional`. The proxy is bypassed; no transaction starts.

1. Identify the call site. Confirm the inner method is intended to run in its own transaction (otherwise just inline)
2. Pick one fix:
   - **Extract `methodB` to a different bean** (preferred) - inject the new bean, call it through that reference. Forces a clearer responsibility split.
   - **Self-injection** - inject `Self self;` (the bean's own proxy) and call `self.methodB()`. Works but signals the design needs splitting; treat as a temporary fix.
   - **`TransactionTemplate`** - drop `@Transactional` on `methodB`, wrap the body in `transactionTemplate.execute(...)`. Verbose; useful when propagation needs differ per call site.
3. Verify with a test that asserts the transaction *actually starts* (e.g., assert a row written in `methodB` is rolled back when an exception is thrown after the call returns)

Adding `@Transactional` to `methodB` without restructuring the call does **not** fix the bug - the proxy is still bypassed. Reject that as a fix.

**Recipe: Replace `synchronized` on Virtual Thread paths**

1. Confirm the path runs under Virtual Threads (Boot 3.2+ with `spring.threads.virtual.enabled=true`)
2. Replace `synchronized(this)` / `synchronized(lock)` with `ReentrantLock` (or `StampedLock` for read-heavy paths)
3. Verify behavior with a concurrency test (multiple Virtual Threads racing the critical section)
4. Audit other `synchronized` blocks in the same module - they pin too

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, aspect rewrites)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Spring Boot Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Stack:** Java <version> / Spring Boot <version>

## Coverage Gate

**Status:** Adequate | Thin (boundary tests missing) | Inadequate (cannot proceed)

[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-spring-test` first.]

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Test gate:** [which tests must pass after this step - JUnit / `@WebMvcTest` / `@DataJpaTest` / `@SpringBootTest`]
- **Transaction stance:** [callee runs inside caller's `@Transactional` | callee uses `@TransactionalEventListener(AFTER_COMMIT)` | not transactional]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] Test suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across `@Transactional` boundaries

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

- [ ] Stack confirmed as Java / Spring Boot (or accepted from parent dispatcher) (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Coverage gate evaluated; refused to propose plan if coverage was inadequate (Step 3)
- [ ] Spring-specific smells identified using Step 4 catalog (controller, service, persistence, configuration/DI, aspect, async/messaging) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] Each step independently committable; test gate stated per step (Step 6)
- [ ] Transaction stance stated per step (no I/O silently moved across `@Transactional` boundary) (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, aspect rewrites, signature changes) (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)
- [ ] Rollback path is one revert per step (Step 7)

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing JPA `@PostUpdate` / `@PostPersist` callbacks without a test asserting the original behavior is preserved
- Extracting an interface with one implementation - wait for the second use case before generalizing
- Replacing `@Transactional` self-invocation by adding `@Transactional` to the inner method without restructuring the call - the proxy is still bypassed
- Moving HTTP calls or message publishes from a non-transactional context to inside a transactional one (or vice versa) without explicitly stating the transaction stance
- Refactoring an `@AutoConfiguration` class without a backward-compatibility plan - that is a published API
- Replacing `synchronized` with `ReentrantLock` on a non-Virtual-Thread path with no concurrency benefit (premature change)
