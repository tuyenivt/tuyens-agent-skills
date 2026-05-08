---
name: spring-code-explain
description: Spring Boot / Java framework signals for code explanation - bean lifecycle, AOP proxies, transaction boundaries, async execution, security filter chain, and JPA persistence context. Used by task-code-explain to explain Spring code with stack-aware gotchas.
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

Annotations that depend on the Spring proxy: `@Transactional`, `@Async`, `@Cacheable` / `@CacheEvict` / `@CachePut`, `@PreAuthorize` / `@PostAuthorize`, `@Retryable`, `@Validated` (on parameters).

**Self-invocation bypasses the proxy.** When `methodA()` in a `@Service` calls `this.methodB()` and `methodB` has `@Transactional`, the transactional boundary is **not** opened. The call must go through the injected bean reference (or a self-injected proxy) for the annotation to fire.

**Private and final methods are not advised.** Default JDK / CGLIB proxies cannot intercept private or final methods; the annotation is silently ignored.

**Initialization-time calls miss advice.** Methods called from `@PostConstruct` may run before the proxy is fully wired - `@Async` and `@Transactional` may not apply.

### `@Transactional` Specifics

- **Propagation:** default `REQUIRED` joins existing transaction or starts a new one. `REQUIRES_NEW` always opens a new transaction; useful for audit logging that must survive parent rollback. `NESTED` requires JDBC savepoint support.
- **Read-only flag:** `readOnly = true` enables Hibernate flush-skip and DB-level read-only hints; performance-relevant for queries.
- **Rollback rules:** rolls back on `RuntimeException` and `Error` only by default. Checked exceptions do **not** roll back unless `rollbackFor = CheckedException.class` is set.
- **Timeout:** measured in seconds; counts wall-clock time including waiting on locks.
- **Isolation:** `Isolation.DEFAULT` uses the database default - usually `READ_COMMITTED` on PostgreSQL/MySQL, not `REPEATABLE_READ`.

### JPA / Hibernate Persistence Context

- **Dirty checking:** entities loaded inside a transaction are tracked; field mutations are flushed at transaction commit without an explicit `save()` call. Mutating an entity outside a transaction has no DB effect.
- **Lazy loading:** `@OneToMany`, `@ManyToOne(fetch = LAZY)`, and Hibernate proxies throw `LazyInitializationException` when accessed after the persistence context is closed (e.g., in the controller layer when `@Transactional` ended in the service).
- **N+1 queries:** loops over a collection of entities accessing a lazy association issue one query per entity. Detect: collection access in a loop + a `@OneToMany` or `@ManyToOne(LAZY)` field.
- **Flush timing:** writes are buffered and flushed at commit, before query execution within the same transaction, or on explicit `flush()`. A `findById` after a `save` in the same transaction may return the cached entity, not a fresh DB row.
- **Detached entities:** entities passed across transaction boundaries are detached; `merge()` reattaches but returns a new managed instance - the original reference is still detached.

### Async, Scheduled, and Events

- `@Async`: returns immediately; method runs on a `TaskExecutor` thread. Return type must be `void`, `Future<T>`, or `CompletableFuture<T>`. Exceptions on `void` returns are swallowed unless an `AsyncUncaughtExceptionHandler` is configured.
- `@Scheduled`: runs on the scheduling thread pool (default size 1); a long-running scheduled task blocks all others. Use `@EnableAsync` + `@Async` on the scheduled method to detach.
- `@EventListener`: synchronous by default - fires on the publisher's thread inside the publisher's transaction. `@TransactionalEventListener` defers until commit. Add `@Async` for true async.
- `ApplicationEventPublisher.publishEvent`: synchronous unless the listener is `@Async`. Publisher exceptions roll back the publisher's transaction.

### Spring Security Signals

- **Filter chain:** request passes through `SecurityFilterChain` before reaching the controller. Look for the configuration class (`SecurityFilterChain` bean) to see what runs before the handler.
- **Method security:** `@PreAuthorize`, `@PostAuthorize`, `@Secured` are AOP-proxied - same self-invocation gotcha as `@Transactional`.
- **`SecurityContextHolder`:** holds auth in a `ThreadLocal` by default. `@Async` methods do not inherit the security context unless `DelegatingSecurityContextExecutor` or `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` is configured.
- **CSRF and session:** stateless REST APIs typically disable CSRF and use `STATELESS` session creation policy. Check `SecurityFilterChain` config to confirm.

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

**Into "Change Impact Preview":**

- Adding `@Transactional` to a method already called via `this.X()` will not take effect - flag the call sites
- Removing `readOnly=true` may double DB load on queries
- Changing return type away from `CompletableFuture` breaks `@Async` semantics

## Avoid

- Explaining Spring annotations as if they always fire - check the proxy chain first
- Treating `@Service` and `@Component` as semantically different at runtime - they are not; only the stereotype changes
- Confusing `@Bean` (method-level, in `@Configuration`) with `@Component` (class-level)
- Describing JPA `save()` as the trigger for DB writes - dirty checking + commit is the actual trigger
- Mentioning N+1 risk without naming the lazy field that causes it
- Ignoring profile-conditional bean activation - a bean may not exist in the runtime profile
