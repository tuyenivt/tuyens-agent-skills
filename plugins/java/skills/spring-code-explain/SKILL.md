---
name: spring-code-explain
description: "Spring Boot / Java code-explain signals: bean lifecycle, AOP proxies, @Transactional boundaries, @Async, security filter chain, JPA context."
metadata:
  category: backend
  tags: [explanation, code-understanding, spring, jpa, aop]
user-invocable: false
---

# Spring Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Java / Spring Boot.

## When to Use

- A workflow needs Spring-specific framework-magic, lifecycle, and gotcha signals when explaining a class, method, or module.
- The target code uses Spring annotations (`@Service`, `@RestController`, `@Component`, `@Transactional`, `@Async`, `@EventListener`, `@Scheduled`, `@Cacheable`), JPA (`@Entity`, `@Repository`), or Spring Security filters.

## Rules

- Always identify the Spring stereotype first (`@Component`, `@Service`, `@RestController`, `@Configuration`, `@Repository`) - the stereotype controls lifecycle, scope, and proxy generation.
- Distinguish AOP-proxied behavior from direct method calls. Proxy effects (`@Transactional`, `@Async`, `@Cacheable`, `@PreAuthorize`) only apply when invoked through the bean reference, not via `this.method()`.
- Surface JPA persistence context implications when the code reads or mutates entities - dirty checking, lazy loading, flush timing, and detached-entity behavior are not visible from the call site.
- Surface bean scope (`singleton` default vs `prototype`, `request`, `session`) when state is stored on a field. Singletons sharing mutable state across threads is a frequent bug source.
- Identify the security context (filter chain order, method security, or no security) before describing what the endpoint does.
- If the target code uses no Spring annotations and no Spring-imported types (`org.springframework.*`, `jakarta.persistence.*`), return empty signal blocks and a single note "no Spring-specific signals detected" - do not invent framework behavior.

## Patterns

### Stereotype and Lifecycle

| Annotation                              | Lifecycle / behavior                                                                   | What to flag                                                                                                                            |
| --------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `@RestController` / `@Controller`       | HTTP entry point, singleton bean, methods invoked per-request                          | Mutable instance fields are shared across threads; injected `HttpServletRequest` is request-scoped proxy                                |
| `@Service`                              | Business logic singleton                                                               | Same threading caveat as above; transaction boundary usually starts here                                                                |
| `@Repository`                           | Persistence singleton; JPA exception translation applied                               | Spring Data interfaces generate proxies at runtime - implementation is not in source                                                    |
| `@Component`                            | Generic singleton                                                                      | Used for non-stereotype beans; check what `@PostConstruct` does at startup                                                              |
| `@Configuration`                        | `@Bean`-producing class; `@Bean` methods proxied via CGLIB                             | Inter-`@Bean` calls go through the proxy (so they get singleton semantics); changing `proxyBeanMethods=false` breaks this               |
| `@RestControllerAdvice` / `@ControllerAdvice` | Cross-cutting exception handler                                                  | Order matters when multiple advices match; `@ExceptionHandler` resolution is type-hierarchy based                                       |

### AOP Proxy Gotchas (highest-yield Spring gotcha class)

Proxy-backed annotations: `@Transactional`, `@Async`, `@Cacheable` / `@CacheEvict` / `@CachePut`, `@PreAuthorize` / `@PostAuthorize`, `@Retryable`, `@Validated`.

Three silent-failure modes - flag any of them on a proxy-backed annotation:

- **Self-invocation** (`this.method()`) bypasses the proxy; the annotation does not fire
- **Private / final methods** cannot be advised by JDK or CGLIB proxies
- **`@PostConstruct`-time calls** may run before the proxy is wired

For canonical patterns and fixes (self-injection, bean extraction, `TransactionTemplate`), see `spring-transaction`.

### `@Transactional` Specifics

For propagation, rollback rules, read-only optimization, timeout, and the IO-in-transaction anti-pattern, see `spring-transaction`. When explaining a transactional method, surface: propagation chosen, `readOnly` flag, rollback rules (especially checked-exception handling), and any outbound client (`RestClient`, `WebClient`, `KafkaTemplate`) invoked inside the boundary.

### JPA / Hibernate Persistence Context

For N+1 detection, fetch strategies, projections, and pagination, see `spring-jpa-performance`. Surface for each entity-touching method:

- **Dirty checking**: mutations inside an open transaction flush at commit without explicit `save()`; mutations outside have no DB effect
- **Lazy access boundary**: `LazyInitializationException` fires when a lazy association is touched after the persistence context closes (controller layer, mappers, async threads)
- **Flush timing**: writes buffer until commit, query execution, or explicit `flush()`; a `findById` after `save` in the same transaction returns the cached managed entity
- **Detached entities**: returned from a `@Transactional` method are detached; `merge()` returns a new managed instance, the original stays detached
- **Optimistic locking**: entities with `@Version` throw `OptimisticLockException` on concurrent writes; callers must retry or escalate
- **Entity-as-return-type**: exposes a detached object; mutations after return do not persist. Project to DTO instead

### Async, Scheduled, and Events

- `@Async`: returns immediately; method runs on a `TaskExecutor` thread. Return type must be `void`, `Future<T>`, or `CompletableFuture<T>`. Exceptions on `void` returns are swallowed unless an `AsyncUncaughtExceptionHandler` is configured. Exceptions on `CompletableFuture<T>` returns surface only when the caller awaits via `.get()` / `.join()` - if the caller never awaits, the failure is silent.
- `@Scheduled`: runs on the scheduling thread pool (default size 1); a long-running scheduled task blocks all others. Use `@EnableAsync` + `@Async` on the scheduled method to detach.
- `@EventListener`: synchronous by default - fires on the publisher's thread inside the publisher's transaction. A throwing listener rolls back the publisher's transaction.
- `@TransactionalEventListener`: defers listener execution until a transaction phase. Phases:
  - `BEFORE_COMMIT` (default): runs after the publisher returns but before commit; can still abort the TX.
  - `AFTER_COMMIT`: runs only if the TX committed; the entity is now persisted but the TX is closed (lazy access fails).
  - `AFTER_ROLLBACK`: runs only if the TX rolled back.
  - `AFTER_COMPLETION`: runs in either case.
  Choosing the wrong phase changes behavior dramatically (e.g., publishing to Kafka in `BEFORE_COMMIT` can publish events for a transaction that then rolls back).
- `ApplicationEventPublisher.publishEvent`: synchronous unless the listener is `@Async`. Listener exceptions roll back the publisher's transaction (unless the listener is `@Async` or `@TransactionalEventListener(AFTER_COMMIT)`).

### Spring Security Signals

- **Filter chain:** request passes through `SecurityFilterChain` before reaching the controller. Look for the configuration class (`SecurityFilterChain` bean) to see what runs before the handler.
- **Method security:** `@PreAuthorize`, `@PostAuthorize`, `@Secured` are AOP-proxied - same self-invocation gotcha as `@Transactional`.
- **`SecurityContextHolder`:** holds auth in a `ThreadLocal` by default. `@Async` methods do not inherit the security context unless `DelegatingSecurityContextExecutor` or `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` is configured.
- **CSRF and session:** stateless REST APIs typically disable CSRF and use `STATELESS` session creation policy. Check `SecurityFilterChain` config to confirm.

### Spring Boot 3.x / Java 21+ Baseline Signals

- **`jakarta.*` packages** (not `javax.*`): Spring Boot 3 moved to Jakarta EE 9+. Code still importing `javax.persistence` / `javax.servlet` is pre-3.0 and almost certainly mismatched against the current dependency set.
- **Virtual threads:** when `spring.threads.virtual.enabled=true`, Tomcat request threads and `@Async` executors run on Loom virtual threads. `synchronized` blocks pin the carrier thread - flag any `synchronized` in request-path code as a perf risk in this mode.
- **Observation API (Micrometer Tracing):** Spring 6 replaced Sleuth. `@Observed` and the `ObservationRegistry` produce both metrics and traces from one instrumentation point. If the code uses the legacy Sleuth `Tracer` directly, it is on an older Spring version.
- **`RestClient` / `HttpExchange`:** the modern synchronous HTTP client is `RestClient` (Spring 6.1+), and declarative clients use `@HttpExchange`. `RestTemplate` is in maintenance mode; flag new code that introduces it.
- **Records as DTOs:** Java 17+ record types are idiomatic for request/response DTOs. They are immutable, no setters; serialization-library quirks (Jackson constructor binding, `@JsonCreator`) can surprise callers who treat them like POJOs.

### Configuration and Profiles

- `application.yml` / `application.properties` + profile-specific variants (`application-prod.yml`, `application-dev.yml`). Active profile via `spring.profiles.active`.
- `@ConfigurationProperties` binding: type-safe, validated via `@Validated`. `@Value("${...}")` is fragile - typos fail at runtime, not startup.
- `@ConditionalOn*` annotations enable beans based on classpath, properties, or other beans; check these before assuming a bean is always present.

### Testing-Adjacent Behavior to Know About When Reading Code

- `@SpringBootTest` boots the full context - slow but realistic. `@WebMvcTest`, `@DataJpaTest` are slice tests with a partial context.
- `@MockBean` replaces a bean in the context; if the code under test uses `@Cacheable` on a mocked bean, the cache layer wraps the mock.
- Test transactions are rolled back by default (`@Transactional` on the test class) - data inserted in the test is not visible to async threads spawned during the test.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following into the parent workflow's output sections:

**Into "Flow Context":**

- Spring stereotype (`@Service` / `@RestController` / etc.) and bean scope
- Filter chain entry (for HTTP handlers): which filters run before this handler
- Transaction boundary: where it opens and closes for this code path
- Async/scheduled/event triggers if applicable

**Into "Non-Obvious Behavior":**

- AOP proxy gotchas that apply (self-invocation, private/final methods, init-time calls)
- JPA dirty checking, lazy loading risks, flush timing surprises
- `@Transactional` propagation/rollback specifics if used
- Security context inheritance gaps (e.g., async without `DelegatingSecurityContextExecutor`)

**Into "Key Invariants":**

- Bean is singleton: instance fields shared across all callers and threads
- Transaction must be active for entity mutation to persist
- Caller must invoke through bean reference for proxy-backed annotations to fire
- A synchronous `@EventListener` must not throw, or the publisher's transaction rolls back - flag this when the publisher persists state before publishing
- Entities returned from a `@Transactional` method become detached at the boundary; callers cannot rely on lazy associations or dirty checking
- If `@Version` is on the entity, concurrent writers will trigger optimistic-lock failures - the calling flow must either retry or escalate

**Into "Change Impact Preview":**

- Adding `@Transactional` to a method already called via `this.X()` will not take effect - flag the call sites and recommend either self-injection (`@Autowired private SelfType self; self.X()`) or extraction into a separate bean
- Removing `readOnly=true` may double DB load on queries
- Changing return type away from `CompletableFuture` breaks `@Async` semantics
- Switching `@EventListener` from sync to `@Async` or `@TransactionalEventListener(AFTER_COMMIT)` changes failure semantics: the publisher TX will commit even if the listener fails. Identify listeners and confirm they tolerate at-most-once execution.
- Moving an external IO call (HTTP, broker publish) out of a `@Transactional` block changes ordering: the DB write may commit before the side effect fires. If the side effect was load-bearing, the new order needs an outbox pattern.
- Returning a record/DTO instead of an entity removes detachment risk but requires every caller using lazy fields to receive the data they need on the projection

## Avoid

- Explaining Spring annotations as if they always fire - check the proxy chain first
- Treating `@Service` and `@Component` as semantically different at runtime - they are not; only the stereotype changes
- Confusing `@Bean` (method-level, in `@Configuration`) with `@Component` (class-level)
- Describing JPA `save()` as the trigger for DB writes - dirty checking + commit is the actual trigger
- Mentioning N+1 risk without naming the lazy field that causes it
- Ignoring profile-conditional bean activation - a bean may not exist in the runtime profile
