---
name: task-spring-debug
description: "Debug a Spring Boot stack trace, error log, or unexpected behavior: root cause, minimal fix with code, regression test."
metadata:
  category: backend
  tags: [debug, stack-trace, error, fix, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug

## When to Use

Daily developer debugging: paste an error, get a fix.

- Java exception or stack trace
- Unexpected HTTP error response
- Test failure
- Build / compilation error
- Spring Boot startup failure
- Behavior mismatch with no exception (logic bug)

For production incident analysis (containment, blast radius), use `/task-oncall-start` instead.

## Inputs

| Input                       | Required | Description                                       |
| --------------------------- | -------- | ------------------------------------------------- |
| Stack trace or error        | Yes      | The primary failure signal                        |
| Relevant source file        | No       | File where the error occurs                       |
| Steps to reproduce          | No       | What triggers the error                           |
| Expected vs actual behavior | No       | For logic bugs without exceptions                 |
| Test output                 | No       | Full test failure including assertion diff        |

## Rules

- Classify the error before reading code
- Show the exact code change (before → after) - no vague suggestions
- Explain WHY, not just how to fix
- Minimal fix, not redesign
- LOW confidence → say so and list what info would help
- Reference atomic skills only when the fix involves a pattern they cover

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Intake

Accept any of: stack trace, application log snippet, HTTP error response, behavior description, test failure output. Ask one clarifying question if input is ambiguous.

### Step 3 - Classify the Error

Spring wraps exceptions heavily (`InvalidDataAccessApiUsageException` wraps `LazyInitializationException`; `TransactionSystemException` wraps `ConstraintViolationException`; `NestedServletException` wraps controller errors). **Walk the `Caused by:` chain to the deepest non-framework cause** and match the table against that - matching the outer wrapper leads to the wrong fix.

| Exception (deepest cause)                  | Likely Cause                                         | Load Skill                              |
| ------------------------------------------ | ---------------------------------------------------- | --------------------------------------- |
| `NullPointerException`                     | Null reference in call chain                         | -                                       |
| `LazyInitializationException`              | JPA session/transaction scope issue                  | `spring-jpa-performance`                |
| `DataIntegrityViolationException`          | DB constraint violation                              | `spring-db-migration-safety`            |
| `HttpMessageNotReadableException`          | JSON deserialization failure                         | -                                       |
| `HttpMediaTypeNotSupportedException`       | Wrong Content-Type header                            | -                                       |
| `MethodArgumentTypeMismatchException`      | Path/query param type conversion failure             | -                                       |
| `MissingServletRequestParameterException`  | Required query param absent                          | -                                       |
| `MethodArgumentNotValidException`          | `@Valid` body validation failed                      | -                                       |
| `TransactionSystemException`               | Nested exception in `@Transactional`                 | `spring-transaction`                    |
| `UnexpectedRollbackException`              | Inner tx marked rollback-only                        | `spring-transaction`                    |
| `OptimisticLockException`                  | Concurrent update on `@Version` entity               | `spring-transaction`                    |
| `NoSuchBeanDefinitionException`            | Spring context wiring issue                          | -                                       |
| `BeanCurrentlyInCreationException`         | Circular dependency                                  | -                                       |
| `DataAccessResourceFailureException`       | DB connection pool / network failure                 | -                                       |
| `QueryTimeoutException`                    | Statement exceeded query timeout                     | -                                       |
| `JpaSystemException` / `MappingException`  | Entity mapping or dialect mismatch                   | -                                       |
| `ConverterNotFoundException`               | Missing custom `Converter` registration              | -                                       |
| `AsyncRequestNotUsableException`           | Response committed / aborted on async path           | -                                       |
| Virtual Thread pinning                     | `synchronized` block in VT context                   | -                                       |
| Kafka consumer lag / DLT messages          | Consumer error, redelivery loop                      | `spring-messaging-patterns`             |
| RabbitMQ DLQ / unacked messages            | Consumer throwing, no DLQ config                     | `spring-messaging-patterns`             |
| Outbox event not published                 | Scheduled publisher or tx issue                      | `spring-messaging-patterns`             |
| `ConstraintViolationException`             | Bean Validation failed before DB insert              | -                                       |
| `PaymentDeclinedException` (domain)        | External payment gateway declined                    | `spring-exception-handling`             |
| `WebSocketHandshakeException`              | WS auth or CORS failure                              | `spring-websocket`                      |

If a skill is loaded, its patterns drive Step 6's fix - do not re-derive.

**Other categories:**
- **Compilation** - check imports, type signatures
- **Test failure** - assertion mismatch, test setup, mocks
- **Build failure** - read failing task output, `gradle dependencies` for conflicts. Load `java-gradle-build-optimization` only if the failure is itself a build-config / dependency-management problem

### Step 4 - Locate in Codebase

1. First frame in **application code** (not Spring/Hibernate/Tomcat internals) is the starting point
2. Open the file ±50 lines around the failing line
3. Trace the call chain through every Spring layer the request actually traverses: Filter / Interceptor → `@ControllerAdvice` → `@RestController` → `@Service` (with `@Transactional` boundary) → Mapper → `@Repository` → async / scheduled / messaging boundary
4. Check `application.yml`, security/async/datasource config when config-related (LIE with `open-in-view=false`, missing component scan, HikariCP sizing)

### Step 5 - Root Cause

- Explain **WHY**, referencing specific source
- If pattern violation, name the pattern
- Rate confidence: **HIGH** (clear evidence) / **MEDIUM** (likely but alternatives exist) / **LOW** (need more info)

### Step 6 - Propose Fix

- If Step 3 loaded an atomic, draw candidates from that skill's Patterns - do not re-derive
- Show exact before → after diff
- For known multi-fix bugs:
  - `LazyInitializationException` → `JOIN FETCH`, `@EntityGraph`, projection DTO, or read-only `@Transactional` service method. Prefer the projection when the caller only needs a flat shape.
  - `OptimisticLockException` → retry on `@Version` conflict, narrow the transaction, or pessimistic lock for true contention.
  - `TransactionSystemException` (validation) → move `@Valid` to controller so violations surface as 400 instead of being wrapped at commit.

### Step 7 - Prevent Recurrence

Use skill: `spring-test-integration` for test-slice patterns (singleton Testcontainers, security post-processors, Awaitility).

Suggest a test that would have caught this bug class:
- `LazyInitializationException` → `@SpringBootTest` / `@DataJpaTest` that invokes the controller/mapper outside the original `@Transactional` so lazy access actually fails. Unit tests with mocked repositories will not catch this.
- `DataIntegrityViolationException` → `@DataJpaTest` against Testcontainers Postgres (not H2).
- `TransactionSystemException` (validation) → `@WebMvcTest` + `MockMvc` asserting 400 with field errors.
- `OptimisticLockException` → concurrent test using two threads / `EntityManager`s on the same entity.
- VT pinning → JFR or `-Djdk.tracePinnedThreads=short` assertion in a load test.

If the bug pattern can recur, grep for other occurrences (e.g., other mappers touching the same lazy association).

## Edge Cases

- **Vague description, no stack trace** - ask for exact error message, class/method, repro steps before classifying
- **Multiple errors** - identify the root error (earliest / deepest `Caused by`); mention secondaries only if independent
- **No source available** - if the trace points only to framework internals, explain the framework behavior and ask for the application code that triggered it
- **Intermittent bug** - likely concurrency; ask for thread dump or load conditions if confidence is LOW
- **Virtual Thread pinning** - run with `-Djdk.tracePinnedThreads=short` or check JFR for `jdk.VirtualThreadPinned`

## Output

**Bug Analysis** - error type, confidence, layer (Controller/Service/Repository/Configuration/Build)

**Root Cause** - why this happened, with source citation

**Fix** - before/after diff + explanation

**Prevention** (omit if fix is trivial) - test that would catch it, pattern reference, other occurrences via grep

If confidence is LOW, add **Needs Clarification** listing what info would help.

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1
- [ ] Walked `Caused by:` chain to deepest non-framework cause before reading code
- [ ] If the table loaded an atomic skill, the fix was drawn from that skill - not re-derived
- [ ] Root cause cites source file and line; confidence stated
- [ ] Before/after diff provided; fix addresses root cause, not symptom
- [ ] Fix does not violate conventions (no `synchronized` on VT path, no field `@Autowired`)
- [ ] Suggested test would catch this bug class (integration test for LIE, not unit test with mocks)
- [ ] If pattern can recur, other occurrences grep'd

## Avoid

- Generic debugging advice ("add logging", "set a breakpoint")
- Fixing symptoms instead of root causes
- Refactors when a targeted fix suffices
- Analysis without reading the source
- Mixing incident response into developer debugging
