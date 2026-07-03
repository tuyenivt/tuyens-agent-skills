---
name: task-spring-refactor
description: "Spring Boot refactor plan: fat controllers, anemic domain, god services, @Transactional misuse, field injection; coverage-gated phased steps."
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Refactor

Safe, step-by-step refactoring plan for a Spring Boot target. Stack-specific delegate of `task-code-refactor` for Java / Spring Boot 3.5+ on Java 21+.

## When to Use

- Spring smell identification and remediation in a known target
- Pre-merge "this PR grew the fat-controller problem" cleanup
- `@RestController` / `@Service` / `@Repository` / `@Entity` / config refactor

**Not for:**

- Debt prioritization across many targets - `task-debt-prioritize`
- Feature changes - `task-spring-implement`
- Architecture restructuring across modules - `task-design-architecture`
- Bug fixes - `task-spring-debug`

## Inputs

| Input                | Required    | Description                                                           |
| -------------------- | ----------- | --------------------------------------------------------------------- |
| Target scope         | Yes         | File, class, or package (`OrderController.java`, not "the order code")|
| Goal                 | Yes         | Concrete end state (extract `PlaceOrderService`, kill `@PostUpdate`)  |
| Test coverage status | Recommended | What tests exist for the target (not project-wide percentage)         |
| Public surface       | Recommended | Whether target crosses module / library / team boundaries             |

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent dispatcher. If not Spring Boot, stop and recommend `/task-code-refactor`.

### Step 3 - Read the Target

Plans grounded in user prose hallucinate smells and miss real ones. Read before classifying.

1. Target class top-to-bottom: method count, longest method, injection style, `@Transactional` placement, every external collaborator (`RestClient`, `KafkaTemplate`, mailers)
2. Matching test file: count cases by outcome (happy path, validation, external failure, security denial)
3. Immediate callers - reshaping a public method without seeing call sites breaks silently

If only the goal was given without a target file, ask for the target. If targets were given with only symptoms as the goal, synthesize the concrete end state from the symptoms and state it up front.

### Step 4 - Coverage Gate (target-scoped, mandatory)

Refactoring without coverage is a rewrite. "60% project coverage" is not the question - the question is what covers *this target's behavior*.

1. Identify covering tests: `<Target>Test.java`, `@WebMvcTest(<Target>.class)`, `@DataJpaTest`, integration tests asserting end-to-end behavior
2. Gate **per refactor target**; the overall status is the worst target in scope:
   - `Adequate` - behavior-asserting tests exist for the paths the refactor touches
   - `Thin` - happy-path-only: proceed, but boundary tests become prerequisite (Phase 0) steps ahead of the refactor steps that rely on them
   - `Inadequate` - no behavior-asserting tests: still deliver the full plan (smells, blast radius, step sequence), but the Step Sequence opens with coverage-building steps (recommend `task-spring-test`) and every refactor step is gated on them. "Stop" means no refactor step executes before its coverage exists - never that the analysis is withheld

**Output:** `Adequate` | `Thin (boundary tests missing)` | `Inadequate (coverage steps precede all refactor steps)`.

### Step 5 - Identify Spring Smells

For any flagged smell, delegate diagnosis to the matching atomic skill rather than restating its rules. A delegate's Output Format block goes in the plan's `Appendix - Delegated Diagnoses`; the plan body cites it, never duplicates it:

- JPA / N+1 / EAGER / `JOIN FETCH` / `MultipleBagFetchException` -> `spring-jpa-performance`
- `@Transactional` placement / propagation / self-invocation / IO-in-tx / post-commit -> `spring-transaction`
- `@Async` / `@Scheduled` / event listener wiring -> `spring-async-processing`
- Kafka / Rabbit / outbox / idempotent consumer -> `spring-messaging-patterns`
- `@RestControllerAdvice` / `ProblemDetail` -> `spring-exception-handling`
- Coverage gap filling -> `spring-test-integration`
- Cross-language hygiene -> `backend-coding-standards`
- Over-engineering (single-impl interfaces, premature Strategy/Factory, redundant mappers) -> `complexity-review`

**Controller:**

- Fat Controller - handler > 10 lines of orchestration (multiple service calls, conditional dispatch, response shaping)
- Logic in Controller - business rules / calculation in the handler
- Direct Repository in Controller - bypasses the service layer
- `@Transactional` on Controller - tx boundary belongs on the service; on handlers it spans serialization and filter work (-> `spring-transaction`)
- JPA Entity in API - returns `@Entity` or accepts entity as `@RequestBody` (mass assignment + lazy load)
- Validation Duplicating DTO - re-checks `@NotNull` / `@Size` already on the DTO

**Service:**

- God Service - `@Service` > 500 lines mixing orchestration / persistence / mapping / external clients
- Anemic Domain - entities pure data, business rules live in `OrderHelper.calculate(order)`
- Single-Impl Interface - `OrderService` + lone `OrderServiceImpl` with no AOP / second impl / test seam need
- `@Transactional` Self-Invocation - `this.txMethod()` from non-tx method same bean; proxy bypassed
- `REQUIRES_NEW` Without Reason - propagation declared with no written justification
- External I/O Inside `@Transactional` - HTTP / publish / file write inside tx (holds DB conn, defers commit)
- Service Returning `boolean` - caller can't distinguish validation vs not-found vs external failure

**Persistence / JPA:**

- Fat Entity - `@Entity` > 300 lines mixing mapping / computed properties / business operations
- `@PostUpdate` / `@PostPersist` Abuse - lifecycle callback firing emails / events; races commit
- `FetchType.EAGER` on Collections - cartesian explosion
- Unbounded `findAll()` - no `Pageable`
- Always-on Hibernate `@Filter` - silently mutates queries across the app
- `@Query` String Concatenation - dynamic JPQL via concat instead of `Specification` / Querydsl

**DI / Config:**

- `@Autowired` Field Injection - breaks immutability, hurts test, hides dependencies
- `@Value("${...}")` Field Injection - scattered config; should be `@ConfigurationProperties` record
- `ApplicationContextAware` Lookup - service locator antipattern

**Aspect / Async / Messaging:**

- Aspect as Hidden Control Flow - `@Around` swallowing exceptions / rewriting returns
- `@KafkaListener` Without Idempotency - re-runs side effects on redelivery
- `synchronized` on Virtual Thread Path - pins the carrier thread on JDK < 24 (JEP 491 removes this), defeating Boot 3.2+ VT
- `@Async` Without `TaskDecorator` - loses trace / MDC / SecurityContext across boundary

**Test (when in scope):**

- `@SpringBootTest` for Unit Logic - full context where JUnit + Mockito suffices
- H2 in `@DataJpaTest` for Postgres-Feature App - passes on H2, fails on JSONB / `ON CONFLICT` in prod
- `@DirtiesContext` - working around shared state instead of fixing isolation

Judgment over rules: a 25-line `@Service` method with named private steps is fine; a 10-line method doing three unrelated things is not.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. Spring-specific signals:

- Public API surface (external clients consume the controller)
- Library / module boundary (`@AutoConfiguration`, published starter)
- Aspect with broad pointcut (`execution(* com.acme..*.*(..))`)
- Bean injected widely (signature change cascades)
- JPA entity used in many queries / `Specification`s
- `@Transactional` method called from outside the bean (removing the annotation silently changes caller semantics)

State **Narrow** / **Moderate** / **Wide** / **Critical** before proposing steps - the whole-plan level, with per-step escalations noted where a single step exceeds it. Emit `review-blast-radius`'s full block in the plan's Blast Radius section, headed by the one-line summary.

### Step 7 - Propose the Step Sequence

Each step is:

1. **Independently committable** - compiles, suite passes
2. **Behaviorally invariant** - no behavior change unless explicitly noted
3. **Reversible** - one revert
4. **Tested** - existing tests stay green; new tests added for new units

**Transaction-boundary watch.** Extracting from a `@Transactional` method, the callee inherits the transaction via the proxy. If the extracted code does HTTP / Kafka / file writes, they now happen mid-transaction. State the transaction stance per step:

- *inside caller's `@Transactional`* | *AFTER_COMMIT via `@TransactionalEventListener`* | *outbox* | *not transactional*

**Recipe map.** Pick the goal-shaped recipe; the detailed mechanics live in the named atomic skill.

| Goal                                          | Recipe shape                                                                                 | Delegate                       |
| --------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------ |
| Extract service from fat controller           | Add `<Verb><Noun>Service` + test -> controller calls it -> remove old logic -> verify `@WebMvcTest` | -                       |
| `@PostUpdate` -> `AFTER_COMMIT`               | Pin behavior test -> publish domain event -> add `@TransactionalEventListener(AFTER_COMMIT)` -> delete callback | `spring-transaction`  |
| Untangle fat controller + entity callbacks    | Pin behavior -> promote callbacks to AFTER_COMMIT -> introduce service -> delete callbacks (use this only when a controller smell is also in scope; for a callback alone use the row above) | `spring-transaction` |
| Split god service                             | Identify orthogonal concerns -> extract one at a time, god delegates -> migrate callers -> delete shell | -                    |
| Eliminate single-impl interface               | Confirm no doubles / AOP / second impl -> inline impl, delete interface (skip if published API) | `complexity-review`         |
| `@Autowired` field -> constructor injection   | Add constructor with `final` fields -> remove `@Autowired` (`@RequiredArgsConstructor` works) | -                              |
| Make `@KafkaListener` idempotent              | Double-delivery test -> dedup table / business-key upsert -> verify retries -> configure DLT | `spring-messaging-patterns`    |
| Move external I/O out of `@Transactional`     | Integration test -> choose outbox (strong) or AFTER_COMMIT listener (simple) -> tx contains DB only -> audit receiver idempotency | `spring-transaction` |
| Replace JPA entity in API with record DTO     | Define request/response records -> mapping inside tx (lazy assoc) -> update controller -> assert no entity fields leak | -            |
| Fix `@Transactional` self-invocation          | See `spring-transaction` (extract bean / self-inject / `TransactionTemplate`) + regression test that tx *actually starts* | `spring-transaction` |
| Replace `synchronized` on VT path             | Confirm VT enabled + JDK < 24 -> `ReentrantLock` (or `StampedLock` read-heavy) -> concurrency test -> audit siblings | `spring-async-processing` |

**Failure-mode disclosure.** When moving I/O out of `@Transactional`: old code rolled back DB on HTTP failure; new code does not. State this as a behavioral change, not a refactor.

**Anti-trap.** Never solve self-invocation with a `ThreadLocal` "skip when called from inside" flag. Promote to AFTER_COMMIT first, then move ownership.

### Step 8 - Validate Plan

- Goal achieved at end of sequence
- Each step < 30 minutes to review
- Tests run between every step
- Low-risk first (extracts, additions) before high-risk (deletions, signature changes)
- No "while we're here" cleanup bundled in
- Transaction stance stated for every step touching `@Transactional` code

## Output Format

```markdown
## Spring Boot Refactor Plan

**Target:** [file:line or path]
**Goal:** [end state]
**Stack:** Java <version> / Spring Boot <version>

## Coverage Gate

**Status:** Adequate | Thin (boundary tests missing) | Inadequate (coverage steps precede all refactor steps)

[If Thin/Inadequate: name the prerequisite (Phase 0) coverage steps; recommend `task-spring-test`.]

## Smells Identified

| Smell        | Location  | Notes                                  |
| ------------ | --------- | -------------------------------------- |
| [Smell name] | file:line | [Why this is the smell - one sentence] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [callers, tests, public surface; per-step escalations if any]
[full `review-blast-radius` output block]

## Step Sequence

### Step 1 - [Verb + Noun]

- **Change:** [what is added / extracted / moved]
- **Test gate:** [JUnit | `@WebMvcTest` | `@DataJpaTest` | `@SpringBootTest`]
- **Transaction stance:** [inside caller's `@Transactional` | AFTER_COMMIT | outbox | not transactional]
- **Rollback:** [one-revert description]
- **Behavior change?** [No | Yes - describe]

[... continue ...]

## Out of Scope

[Adjacent improvements deliberately deferred]

## Appendix - Delegated Diagnoses

[Output blocks emitted by delegated atomic skills; omit the section when no delegate produced one]
```

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed (or accepted from parent dispatcher)
- [ ] Target file(s) and tests read directly - no inference from prose
- [ ] Coverage gate evaluated per target (worst target governs); Thin/Inadequate produce Phase 0 coverage steps gating the refactor steps
- [ ] Spring smells named from the Step 5 catalog; deep dives delegated to atomic skills
- [ ] Blast radius stated before any step
- [ ] Each step independently committable with a test gate and transaction stance
- [ ] Low-risk before high-risk; no unrelated cleanup bundled
- [ ] Behavioral changes (failure-mode shifts, AFTER_COMMIT semantics) flagged, not hidden in a refactor step

## Avoid

- Refactor without a target-scoped coverage gate - that's a rewrite
- Bundling behavior changes into refactor steps without labeling them
- "While we're here" cleanups - separate PR
- Renaming during refactor - separate PR
- Removing JPA lifecycle callbacks without a test pinning current behavior
- Extracting an interface with one implementation - wait for the second use case
- "Fixing" self-invocation by annotating the inner method - proxy still bypassed
- Moving HTTP / publish across a `@Transactional` boundary without stating the new failure mode
- Refactoring `@AutoConfiguration` without a backward-compatibility plan
- `synchronized` -> `ReentrantLock` on a non-VT path with no concurrency need
