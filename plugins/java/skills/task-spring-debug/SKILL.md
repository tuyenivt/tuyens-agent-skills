---
name: task-spring-debug
description: "Debug Spring Boot stack trace, error log, test failure, or behavior bug: classify, root cause, minimal fix diff, regression test."
metadata:
  category: backend
  tags: [debug, stack-trace, error, fix, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug

## When to Use

Daily developer debugging on Spring Boot / Java: paste an error or describe a misbehavior, get a targeted fix with regression test.

In scope: Java exception, HTTP error response, test failure, build / compilation error, startup failure, behavior mismatch without exception.

Not in scope: production incident triage (containment, blast radius, comms) -> use `/task-oncall-start`. Wholesale redesign or feature work -> use `/task-spring-refactor` or `/task-spring-implement`.

## Workflow

### Step 1 - Load behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Detect stack

Use skill: `stack-detect`. Confirm Java + Spring Boot. If the project is not Spring, stop and route to the matching stack debug workflow (or `task-code-debug` in core).

### Step 3 - Intake and classify

Accept: stack trace, log snippet, HTTP error body, behavior description, or test output. Ask one clarifying question only if the failure signal is ambiguous (no exception class, no repro, no expected vs actual).

Spring wraps exceptions. Walk `Caused by:` to the deepest non-framework cause before matching. Matching the outer wrapper (e.g. `InvalidDataAccessApiUsageException`, `TransactionSystemException`, `NestedServletException`) leads to the wrong fix.

Classify and load the relevant atomic skill if any. Common mappings:

| Deepest cause                                  | Atomic skill                |
| ---------------------------------------------- | --------------------------- |
| `LazyInitializationException`, N+1, slow query | `spring-jpa-performance`    |
| `TransactionSystemException`, `UnexpectedRollbackException`, `OptimisticLockException` | `spring-transaction` |
| `DataIntegrityViolationException`, schema drift | `spring-db-migration-safety` |
| Kafka / RabbitMQ / outbox failures             | `spring-messaging-patterns` |
| Domain exception not mapped to HTTP status     | `spring-exception-handling` |
| `WebSocketHandshakeException`                  | `spring-websocket`          |
| Async / scheduler / VT pinning                 | `spring-async-processing`   |
| Auth / CSRF / method security failure          | `spring-security-patterns`  |
| Build / dependency conflict                    | `java-gradle-build-optimization` |
| Plain `NullPointerException`, JSON binding, `MethodArgumentNotValidException`, `NoSuchBeanDefinitionException`, `BeanCurrentlyInCreationException`, `ConverterNotFoundException`, compilation, generic test failure | none (handle inline) |

When there is no exception (behavior mismatch), route by symptom, not class: silent commit / "not rolling back" / lost update -> `spring-transaction`; data missing after save, stale read -> `spring-jpa-performance` or `spring-transaction`; missing post-commit side effect -> `spring-async-processing` / `spring-messaging-patterns`; wrong auth outcome -> `spring-security-patterns`.

If a skill loaded, its Patterns drive Steps 5-6. Do not re-derive. This workflow's Output Format is the sole deliverable contract - do not also emit the loaded atomic's own output block.

### Step 4 - Locate in codebase

1. First non-framework frame is the entry point.
2. Open the file +/- 50 lines around the failing line.
3. Trace the layers the request actually crosses: Filter / Interceptor -> `@ControllerAdvice` -> `@RestController` -> `@Service` (note `@Transactional` boundary) -> Mapper -> `@Repository` -> async / scheduled / messaging hop.
4. Check `application.yml`, security / async / datasource config when symptoms point there (e.g. LIE with `open-in-view=false`, missing component scan, HikariCP exhaustion).

### Step 5 - Root cause

State WHY, citing file and line. Name the violated pattern if any. Rate confidence:

- **HIGH** - direct evidence in source.
- **MEDIUM** - likely but plausible alternatives exist.
- **LOW** - need more info; list what would raise confidence.

### Step 6 - Propose fix

Show exact before -> after diff. Minimal fix, not redesign. If Step 3 loaded an atomic, draw the fix from its Patterns; when it has no Pattern for this exact bug class, derive the minimal fix from its Rules and say so. Tie-break for boundary bugs: when a regression moved work outside a tx/session boundary, prefer restoring the boundary (e.g., map to DTO inside the service) over widening data fetching (`@EntityGraph` / fetch join) - widen fetching only when the entity legitimately crosses the boundary. Explain why this fix addresses the cause, not the symptom.

### Step 7 - Prevent recurrence

Use skill: `spring-test-integration` for test-slice patterns (singleton Testcontainers, security post-processors, Awaitility for async).

Suggest one regression test that would have caught this bug class; when the request asks for the test itself, deliver the full test class and reference its path from the Prevention bullet. Pick the slice that exercises the actual failure boundary (e.g. integration test outside the original `@Transactional` for LIE; `@WebMvcTest` for binding / validation; concurrent threads for optimistic lock; Testcontainers Postgres for schema / constraint bugs - not H2; a `@SpringBootTest` context-load smoke test for wiring / startup failures like `NoSuchBeanDefinitionException`). If the bug class can recur, grep for sibling call sites of the same violated pattern (not the whole symptom space) and list them.

## Output Format

```
## Bug Analysis
- Error type: <exception or category>
- Layer: <Controller | Service | Repository | Config | Build | Test>
- Confidence: <HIGH | MEDIUM | LOW>
- Loaded skill: <atomic-skill-name or none>

## Root Cause
<why, with file:line citation>

## Fix
```diff
- <before>
+ <after>
```
<one-paragraph explanation>

## Prevention
- Test: <slice + what it asserts>
- Other occurrences: <files or "none found">

## Needs Clarification   <!-- only if confidence is LOW -->
- <specific info that would raise confidence>
```

Omit Prevention if the fix is a one-line typo. Omit Needs Clarification unless confidence is LOW.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: `stack-detect` confirms Spring; otherwise routed away.
- [ ] Step 3: walked `Caused by:` to deepest non-framework cause; loaded atomic skill if table mapped one.
- [ ] Step 4: cited application-code frame and traversed actual layer chain.
- [ ] Step 5: root cause cites file:line; confidence stated.
- [ ] Step 6: before/after diff drawn from loaded atomic's Patterns (when one loaded); fix is minimal and targets the cause.
- [ ] Step 7: regression test names the right slice for this bug class; sibling occurrences grep'd if recurrence-prone.

## Avoid

- Generic advice ("add logging", "set a breakpoint") instead of a fix.
- Matching the outer wrapper exception instead of the deepest cause.
- Re-deriving a fix the loaded atomic already specifies.
- Fixing the symptom (catch-and-swallow, broaden `@Transactional`) instead of the cause.
- Unit test with mocked repository as the "regression test" for an integration-only failure (LIE, constraint, optimistic lock).
- Refactor when a targeted diff suffices.
- Mixing incident response (containment, comms) into developer debugging.
