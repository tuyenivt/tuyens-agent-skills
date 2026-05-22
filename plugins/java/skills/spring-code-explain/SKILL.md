---
name: spring-code-explain
description: "Spring/JPA explain signals: stereotype lifecycle, AOP proxy gotchas, @Transactional boundaries, JPA persistence-context surprises, security context."
metadata:
  category: backend
  tags: [explanation, code-understanding, spring, jpa, aop]
user-invocable: false
---

# Spring Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-code-explain` when the stack is Java / Spring Boot.

## When to Use

- A workflow needs Spring framework-magic signals when explaining a class, method, or module
- Target code uses Spring annotations, JPA, or Spring Security

If the code has no Spring annotations and no `org.springframework.*` / `jakarta.persistence.*` imports, return empty signal blocks and the note "no Spring-specific signals detected" - do not invent behavior.

## Rules

- Identify the stereotype first - it controls lifecycle, scope, and proxy generation
- Distinguish AOP-proxied calls from `this.X()` (proxy bypass)
- Surface JPA persistence-context implications when reading or mutating entities
- Identify the security context (filter chain / method security / none) before describing endpoint behavior
- Note bean scope when state lives on fields - singletons sharing mutable state is a frequent bug

## Patterns

### Stereotype quick reference

| Annotation                           | Lifecycle / behavior                                         | What to flag                                                                          |
| ------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| `@RestController` / `@Controller`    | HTTP entry, singleton, methods per-request                   | Mutable fields shared across threads; `HttpServletRequest` injected is request-scoped proxy |
| `@Service`                           | Business logic singleton; usual transaction boundary         | Same threading caveats                                                                |
| `@Repository`                        | Persistence singleton; JPA exception translation             | Spring Data interfaces have runtime-generated proxies - implementation not in source  |
| `@Configuration`                     | `@Bean` factory; CGLIB-proxied for inter-`@Bean` calls       | `proxyBeanMethods=false` breaks singleton semantics across `@Bean` calls              |
| `@RestControllerAdvice`              | Cross-cutting exception handler                              | Order matters; `@ExceptionHandler` resolves by type hierarchy                         |

### AOP proxy gotchas (highest-yield Spring bug class)

Proxy-backed: `@Transactional`, `@Async`, `@Cacheable` / `@CacheEvict` / `@CachePut`, `@PreAuthorize` / `@PostAuthorize`, `@Retryable`, `@Validated`.

Silent-failure modes:

- **Self-invocation** (`this.method()`) - bypasses the proxy; annotation does not fire
- **Private / final methods** - cannot be advised
- **`@PostConstruct`-time calls** - may run before the proxy is wired

For canonical fixes (extract to bean, self-injection), see `spring-transaction`.

### `@Transactional` specifics

Defer to `spring-transaction`. When explaining a transactional method, surface: propagation, `readOnly`, rollback rules for checked exceptions, any outbound IO (`RestClient`, `WebClient`, `KafkaTemplate`) inside the boundary.

### JPA persistence context

Defer to `spring-jpa-performance` for N+1 / fetch / projection depth. Per entity-touching method, surface:

- **Dirty checking** - mutations in an open transaction flush at commit without explicit `save()`; outside, no DB effect
- **Lazy access boundary** - `LazyInitializationException` when a lazy association is touched after the persistence context closes (controller, mappers, async threads)
- **Flush timing** - writes buffer until commit / query / explicit `flush()`
- **Detached entities** - returned from a `@Transactional` method are detached; `merge()` returns a new managed instance
- **Optimistic locking** - `@Version` throws `OptimisticLockException` on concurrent writes; callers must retry or escalate

### Async, scheduled, events

- **`@Async`**: returns immediately on a `TaskExecutor` thread. Return type must be `void`, `Future`, or `CompletableFuture`. Exceptions on `void` swallowed unless `AsyncUncaughtExceptionHandler` is set. Exceptions on `CompletableFuture` only surface if the caller awaits.
- **`@Scheduled`**: default pool size 1; long-running tasks block siblings. Detach with `@EnableAsync` + `@Async`.
- **`@EventListener`**: synchronous; runs on publisher's thread inside publisher's transaction. A throwing listener rolls back the publisher.
- **`@TransactionalEventListener` phases**:
  - `BEFORE_COMMIT` (default in older docs - check version) - can still abort the tx
  - `AFTER_COMMIT` - persisted but tx closed (lazy access fails)
  - `AFTER_ROLLBACK` - only on rollback
  - `AFTER_COMPLETION` - either
- **`ApplicationEventPublisher.publishEvent`**: sync unless the listener is `@Async`.

### Spring Security

- Filter chain runs before the controller - look for the `SecurityFilterChain` bean for what runs first
- `@PreAuthorize` / `@PostAuthorize` are AOP-proxied (same self-invocation gotcha)
- `SecurityContextHolder` is thread-local; `@Async` does not inherit unless `DelegatingSecurityContextExecutor` or `MODE_INHERITABLETHREADLOCAL` is configured
- STATELESS REST APIs typically disable CSRF and use `STATELESS` session policy

### Boot 3.x / Java 21+ signals

- `jakarta.*` packages (not `javax.*`) - Boot 3 moved to Jakarta EE 9+; code on `javax.persistence` is pre-3.0
- Virtual Threads enabled when `spring.threads.virtual.enabled=true` - `synchronized` in request-path code is a pinning risk
- `Observation` API (Micrometer Tracing) replaced Sleuth in Spring 6; legacy `Tracer` usage = older version
- `RestClient` / `@HttpExchange` for modern sync HTTP; `RestTemplate` is maintenance-only
- Records as DTOs are idiomatic; Jackson constructor binding can surprise

### Configuration

- `application.yml` + profile variants (`application-prod.yml`). Active via `spring.profiles.active`.
- `@ConfigurationProperties` is type-safe and validated; `@Value("${...}")` is fragile (typos fail at runtime)
- `@ConditionalOn*` - a bean may not exist in the runtime profile

## Output Format

Inject the following into the parent workflow's output sections:

**Flow Context:**
- Stereotype and bean scope
- Filter chain entry (for HTTP handlers)
- Transaction boundary (where it opens / closes)
- Async / scheduled / event triggers

**Non-Obvious Behavior:**
- AOP proxy gotchas in play (self-invocation, private/final methods, init-time calls)
- JPA dirty checking, lazy loading, flush timing
- Transactional propagation / rollback specifics
- Security context inheritance gaps across `@Async`

**Key Invariants:**
- Bean is singleton - fields shared across threads
- Tx must be active for entity mutation to persist
- Caller must invoke through bean reference for proxy annotations to fire
- A synchronous `@EventListener` must not throw - or the publisher's tx rolls back
- Entities returned from `@Transactional` are detached at the boundary
- `@Version` writers must retry on conflict

**Change Impact Preview:**
- Adding `@Transactional` to a method called via `this.X()` does not take effect - flag call sites; recommend self-injection or extraction
- Removing `readOnly=true` may double DB load on queries
- Changing return type away from `CompletableFuture` breaks `@Async` semantics
- Switching `@EventListener` to `@Async` or `AFTER_COMMIT` changes failure semantics - publisher tx commits even on listener failure
- Moving external IO out of `@Transactional` changes ordering - DB commit may precede the side effect; load-bearing side effects need an outbox
- Returning a DTO instead of entity eliminates detachment risk but requires the projection cover every caller's needs

## Avoid

- Explaining Spring annotations as if they always fire - check the proxy chain
- Treating `@Service` and `@Component` as different at runtime (they're not - stereotype is for tooling)
- Confusing `@Bean` (method-level in `@Configuration`) with `@Component` (class-level)
- Describing `save()` as the trigger for DB writes (dirty checking + commit is)
- Mentioning N+1 risk without naming the lazy field
- Ignoring profile-conditional bean activation
