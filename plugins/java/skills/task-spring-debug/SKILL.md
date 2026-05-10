---
name: task-spring-debug
description: "Debug a Spring Boot stack trace, error log, or unexpected behavior: root cause, minimal fix with code, regression test."
metadata:
  category: backend
  tags: [debug, stack-trace, error, fix, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug - Developer Debugging Workflow

## Purpose

Daily developer debugging: paste an error, get a fix. This is not incident response - it's "here's a stack trace, help me fix it" work.

- **Understand the error** - classify it before jumping to code
- **Trace through your codebase** - follow the call chain to the actual bug
- **Explain why, not just what** - root cause understanding prevents repeat bugs
- **Minimal fix** - smallest correct change, aligned with project patterns

For production incident analysis with containment and blast radius assessment, use `/task-oncall-start` instead.

## When to Use

- Java exception or stack trace you need help understanding
- Unexpected HTTP error response from your API
- Test failure you can't figure out
- Build or compilation error
- Spring Boot startup failure
- Behavior that doesn't match expectations (no error, but wrong result)

## Inputs

| Input                       | Required | Description                                       |
| --------------------------- | -------- | ------------------------------------------------- |
| Stack trace or error        | Yes      | The primary failure signal                        |
| Relevant source file        | No       | File where the error occurs (if known)            |
| Steps to reproduce          | No       | What triggers the error                           |
| Expected vs actual behavior | No       | For logic bugs without exceptions                 |
| Test output                 | No       | Full test failure output including assertion diff |

## Rules

- Always classify the error before reading code
- Show the exact code change needed - no vague suggestions
- Explain WHY the error happened, not just how to fix it
- Prefer minimal fixes over refactors - fix the bug, don't redesign
- If confidence is LOW, say so and state what additional info would help
- Do not suggest unrelated improvements or style changes
- Reference atomic skills only when the fix involves a pattern they cover

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Load these rules first - they govern every step including stack detection, scope decisions, and finding generation.

### Step 2 - Intake

Accept one or more of:

- Stack trace (Java exception)
- Application log snippet
- HTTP error response
- Description of unexpected behavior
- Test failure output

If the input is ambiguous, ask one clarifying question before proceeding.

### Step 3 - Classify the Error

Identify the error category to guide investigation. Spring wraps exceptions heavily (`InvalidDataAccessApiUsageException` wraps `LazyInitializationException`; `TransactionSystemException` wraps `ConstraintViolationException`; `NestedServletException` wraps controller errors). **Always walk the `Caused by:` chain to the deepest non-framework cause and match the table against that** - matching the outer wrapper leads to the wrong fix.

**Compilation error** → syntax or type issue, check imports and type signatures

**Runtime exception** → identify the deepest cause and look it up:

| Exception (deepest cause)                 | Likely Cause                             | Load Skill                              |
| ----------------------------------------- | ---------------------------------------- | --------------------------------------- |
| `NullPointerException`                    | Null reference in call chain             | -                                       |
| `LazyInitializationException`             | JPA session/transaction scope issue      | Use skill: `spring-jpa-performance`     |
| `DataIntegrityViolationException`         | DB constraint violation                  | Use skill: `spring-db-migration-safety` |
| `HttpMessageNotReadableException`         | JSON deserialization failure             | -                                       |
| `HttpMediaTypeNotSupportedException`      | Wrong Content-Type header                | -                                       |
| `MethodArgumentTypeMismatchException`     | Path/query param type conversion failure | -                                       |
| `MissingServletRequestParameterException` | Required query param absent              | -                                       |
| `MethodArgumentNotValidException`         | `@Valid` body validation failed          | -                                       |
| `TransactionSystemException`              | Nested exception in `@Transactional`     | Use skill: `spring-transaction`         |
| `UnexpectedRollbackException`             | Inner TX marked rollback-only            | Use skill: `spring-transaction`         |
| `NoSuchBeanDefinitionException`           | Spring context wiring issue              | -                                       |
| `BeanCurrentlyInCreationException`        | Circular dependency                      | -                                       |
| `DataAccessResourceFailureException`      | DB connection pool / network failure     | -                                       |
| `QueryTimeoutException`                   | Statement exceeded `javax.persistence.query.timeout` | -                                       |
| `JpaSystemException` / `MappingException` | Entity mapping or dialect mismatch       | -                                       |
| `ConverterNotFoundException`              | Missing custom `Converter` registration  | -                                       |
| `AsyncRequestNotUsableException`          | Response committed/aborted on async path | -                                       |
| Virtual Thread pinning                    | `synchronized` block in VT context       | -                                       |
| Kafka consumer lag / DLT messages         | Consumer error, redelivery loop          | Use skill: `spring-messaging-patterns`  |
| RabbitMQ DLQ / unacked messages           | Consumer throwing, no DLQ config         | Use skill: `spring-messaging-patterns`  |
| Outbox event not published                | Scheduled publisher or TX issue          | Use skill: `spring-messaging-patterns`  |
| `OptimisticLockException`                 | Concurrent update on `@Version` entity   | Use skill: `spring-transaction`         |
| `ConstraintViolationException`            | Bean Validation failed before DB insert  | -                                       |
| `PaymentDeclinedException` (domain)       | External payment gateway declined charge | Use skill: `spring-exception-handling`  |
| `WebSocketHandshakeException`             | WS auth or CORS failure                  | Use skill: `spring-websocket`           |

If a skill is loaded above, its patterns drive Step 6's fix construction - do not re-derive a fix from first principles.

**Test failure** → analyze assertion mismatch, check test setup and mocks

**Build failure** → Gradle configuration, dependency resolution, or version conflict. Diagnose first (read the failing task output, check `gradle dependencies` for conflicts). Only load `java-gradle-build-optimization` if the failure is itself a build-config or dependency-management problem; that skill is about build *health*, not arbitrary build errors.

### Step 4 - Locate in Codebase

1. Read the stack trace to identify the **source file and line number**. The first frame in **application code** (not Spring/Hibernate/Tomcat internals) is the starting point.
2. Open the file and surrounding context (~50 lines above and below).
3. Trace the call chain from entry point through every Spring layer the request actually traverses:
   - **Filter / Interceptor / `OncePerRequestFilter`** - auth, request scoping, MDC setup
   - **`@ControllerAdvice` / `HandlerExceptionResolver`** - error mapping (often hides the real exception)
   - **Controller** (`@RestController`, `@Controller`)
   - **Service** (`@Service`, `@Transactional` boundary)
   - **Mapper / DTO assembler** (MapStruct, manual mapper) - common site for `LazyInitializationException`
   - **Repository** (`JpaRepository`, custom `@Query`, `EntityManager`)
   - **Async / scheduled / messaging boundary** (`@Async`, `@Scheduled`, `@KafkaListener`, `@RabbitListener`)
4. Check **configuration files** (`application.yml`, `application.properties`, security config, async config, datasource config) when the error could be config-related (e.g., `LazyInitializationException` with `spring.jpa.open-in-view=false` requires explicit fetch strategy, `NoSuchBeanDefinitionException` from missing component scan, `DataAccessResourceFailureException` from HikariCP pool sizing).
5. Identify which layer the bug is in (Filter | ControllerAdvice | Controller | Service | Mapper | Repository | Configuration | Async/Messaging | Build).

### Step 5 - Root Cause Analysis

- Explain **WHY** this error occurred, not just what happened
- Reference the **specific code** that causes the issue
- If it's a pattern violation (not just a one-off bug), name the pattern
- Rate confidence:
  - **HIGH** - certain, evidence is clear
  - **MEDIUM** - likely, but alternative causes exist
  - **LOW** - need more info to confirm

### Step 6 - Propose Fix

- If Step 3 loaded an atomic skill (e.g., `spring-jpa-performance`, `spring-transaction`, `spring-messaging-patterns`), draw the candidate fixes from that skill's Patterns section. Do not re-derive a fix from first principles when a vetted recipe exists.
- Show the **exact code change** needed (before → after).
- If multiple fixes are possible, rank by:
  1. Correctness - does it actually fix the bug?
  2. Minimal change surface - smallest diff that's correct
  3. Alignment with project patterns - follows existing conventions
- Explain any trade-offs between alternatives. For known multi-fix bugs, name them explicitly:
  - `LazyInitializationException` → `JOIN FETCH` query, `@EntityGraph`, projection DTO at the query level, or a dedicated read-only `@Transactional` service method. Prefer the projection when the caller only needs a flat shape.
  - `OptimisticLockException` → retry on `@Version` conflict, narrow the transaction, or move to pessimistic lock for true contention.
  - `TransactionSystemException` (validation) → move `@Valid` to controller boundary so violations surface as 400 instead of being wrapped at commit time.

### Step 7 - Prevent Recurrence

Use skill: `spring-test-integration` for the test-slice patterns referenced below (singleton Testcontainers, `@DataJpaTest` rollback, security test post-processors, Awaitility for async).

- Suggest a **test that would have caught this bug**, calibrated to the error class:
  - `LazyInitializationException` → `@SpringBootTest` (or `@DataJpaTest`) integration test that invokes the controller/mapper *outside* the original `@Transactional` boundary so lazy access actually fails. Unit tests with mocked repositories will not catch this.
  - `DataIntegrityViolationException` → `@DataJpaTest` exercising the constraint with a real schema (Testcontainers Postgres), not H2.
  - `TransactionSystemException` (validation) → controller-layer test (`@WebMvcTest` + `MockMvc`) asserting 400 with field errors.
  - `OptimisticLockException` → concurrent test using two threads / two `EntityManager`s on the same entity.
  - Concurrency / VT pinning → JFR or `-Djdk.tracePinnedThreads=short` assertion in a load test, not a unit test.
- If it's a pattern violation, reference the relevant atomic skill.
- If the same bug could exist elsewhere, identify other occurrences (grep for similar patterns - e.g., other mappers accessing the same lazy association).

## Edge Cases

- **Vague description, no stack trace**: Ask for the exact error message, the class/method where it occurs, and steps to reproduce before classifying.
- **Multiple errors**: If the input contains multiple errors, identify the root error (usually the earliest in the chain or the "Caused by") and focus on that. Mention secondary errors only if they are independent.
- **No source code available**: If the stack trace points to framework internals only, explain the framework behavior and ask the user for the application code that triggered it.
- **Intermittent/non-deterministic bug**: Note that the issue may be concurrency-related; ask for thread dump or load conditions if confidence is LOW.
- **Virtual Thread pinning**: If the user suspects pinning, suggest running with `-Djdk.tracePinnedThreads=short` JVM flag to get pinning diagnostics, or check JFR events for `jdk.VirtualThreadPinned`.

## Output

Present the analysis in this structure:

**Bug Analysis** - error type, confidence (HIGH/MEDIUM/LOW), layer (Controller/Service/Repository/Configuration/Build)

**Root Cause** - explanation of why this happened, referencing specific code

**Fix** - before/after code diff showing the exact change, with explanation

**Prevention** (omit if fix is trivial) - test that would catch this bug, pattern reference, other occurrences found via grep

### Output Constraints

- Keep the analysis focused - one bug, one fix
- Omit Prevention section if the fix is trivial (e.g., typo, missing import)
- If confidence is LOW, add a **Needs Clarification** section listing what info would help
- No code style commentary unrelated to the bug
- No suggestions for unrelated improvements

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before any other delegation
- [ ] Error classified by walking the `Caused by:` chain to the deepest non-framework cause, before any code is read or fix proposed
- [ ] If the table loaded an atomic skill, Step 6's fix was drawn from that skill's Patterns - not re-derived
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Fix does not introduce constructs that violate project conventions (no `synchronized` blocks on Virtual Threads, no field `@Autowired`)
- [ ] Suggested prevention test would actually have caught this bug class (e.g., LIE → integration test outside original TX, not a unit test with mocks)
- [ ] If the bug pattern can recur, other occurrences grep'd and listed

## Avoid

- Generic debugging advice ("add more logging", "set a breakpoint")
- Fixing symptoms instead of root causes
- Suggesting refactors when a targeted fix suffices
- Analysis without reading the actual source code
- Proposing fixes that violate domain constraints (e.g., adding `synchronized`, using `@Autowired`)
- Mixing incident response concerns into developer debugging
