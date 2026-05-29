---
name: spring-code-explain
description: Spring/JPA explain signals - stereotype lifecycle, AOP proxy bypass, @Transactional boundary, JPA persistence context, security context, async/events.
metadata:
  category: backend
  tags: [explanation, code-understanding, spring, jpa, aop]
user-invocable: false
---

# Spring Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-code-explain` when the stack is Java / Spring Boot.

## When to Use

Workflow needs Spring framework-magic signals: proxy semantics, transaction boundary, persistence context, security context, async timing.

If no `org.springframework.*` / `jakarta.persistence.*` imports and no Spring annotations, return "no Spring-specific signals detected" - do not invent behavior.

## Rules

- Identify the stereotype and bean scope - singletons share field state across threads
- Every proxy-backed annotation has the same three failure modes: self-invocation, private/final, init-time call. Apply to all of them, not just `@Transactional`
- Name the transaction boundary explicitly - where it opens, where it commits, what runs inside vs after
- External IO (HTTP, Kafka, email) inside `@Transactional` is a correctness signal - the side effect can happen before commit or be retried on rollback
- JPA mutations flush at commit via dirty checking, not `save()` - say so when the code mutates entities
- Entities crossing the transaction boundary are detached - lazy access fails after return
- Identify the security context (filter chain / method security / none) before describing endpoint behavior

## Patterns

### Stereotypes

| Annotation                        | Lifecycle                                              | Flag                                                                                |
| --------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `@RestController` / `@Controller` | Singleton, methods per-request                         | Mutable fields are shared; `HttpServletRequest` is a request-scoped proxy           |
| `@Service`                        | Singleton, usual tx boundary                           | Field state shared across threads                                                   |
| `@Repository`                     | Singleton; JPA exception translation                   | Spring Data interfaces are runtime proxies - no implementation in source            |
| `@Configuration`                  | CGLIB-proxied so `@Bean` calls return the singleton    | `proxyBeanMethods=false` makes inter-`@Bean` calls create new instances             |
| `@RestControllerAdvice`           | Cross-cutting handler; resolves by exception hierarchy | `@Order` resolves ambiguity                                                         |

`@Service` vs `@Component` differ only in tooling/semantics, not runtime.

### Proxy-backed annotations (the highest-yield bug class)

Proxied: `@Transactional`, `@Async`, `@Cacheable` / `@CacheEvict` / `@CachePut`, `@PreAuthorize` / `@PostAuthorize`, `@Retryable`, `@Validated`.

All share three silent-failure modes:

- **Self-invocation** (`this.x()` or unqualified call inside the same bean) - bypasses the proxy; the annotation does not fire
- **Private or final methods** - cannot be advised
- **Calls during `@PostConstruct` / constructor** - proxy may not be wired yet

Bad:
```java
@Transactional public void outer() { inner(); }   // inner's @Async/@Transactional ignored
@Async public void inner() { ... }
```
Good: extract `inner` to a separate bean, or self-inject (`@Autowired OrderService self; self.inner();`).

Canonical fix details: `spring-transaction`.

### `@Transactional` boundary

Surface, per transactional method:

- Propagation (default `REQUIRED` joins caller's tx; `REQUIRES_NEW` suspends it)
- `readOnly` - hints flush mode, avoids dirty-check overhead
- Rollback rules - rolls back on unchecked only by default; checked exceptions commit unless declared
- **External IO inside the boundary** - `RestClient` / `WebClient` / `KafkaTemplate` / email. The side effect runs before commit and is not undone on rollback. Load-bearing side effects need an outbox or `AFTER_COMMIT` listener.

### JPA persistence context

Per entity-touching method:

- **Dirty checking** - mutations in an open tx flush at commit without `save()`; outside a tx, no DB effect
- **Lazy boundary** - lazy associations throw `LazyInitializationException` when touched after the tx closes (controller, mappers, async threads)
- **Flush timing** - writes buffer until commit / JPQL query / explicit `flush()`
- **Detached entities** - returned from a `@Transactional` method are detached; `merge()` returns a new managed instance, the original stays detached
- **`@Version`** - throws `OptimisticLockException` on concurrent writes; callers retry or escalate

N+1, fetch strategy, projection depth: defer to `spring-jpa-performance`.

### Async, scheduled, events

- **`@Async`**: proxy hop to a `TaskExecutor`; return `void`, `Future`, or `CompletableFuture`. Exceptions on `void` go to `AsyncUncaughtExceptionHandler` (default: logged). On `CompletableFuture`, exceptions only surface if the caller awaits. Subject to all proxy-bypass modes.
- **`@Scheduled`**: default pool size 1 - long-running tasks block siblings. Combine with `@Async` to detach.
- **`@EventListener`**: synchronous, runs on publisher's thread inside publisher's tx. A throwing listener rolls back the publisher.
- **`@TransactionalEventListener`**: phases gate when the listener runs relative to commit. `AFTER_COMMIT` (most common) runs post-commit so listener failure does not roll back the publisher - and lazy access fails because the tx is closed.

### Spring Security

- Filter chain (`SecurityFilterChain` bean) runs before the controller - check it first for auth/CSRF/CORS behavior
- `@PreAuthorize` / `@PostAuthorize` are proxy-backed (same bypass rules)
- `SecurityContextHolder` is thread-local; `@Async` does not inherit it unless `DelegatingSecurityContextExecutor` or `MODE_INHERITABLETHREADLOCAL` is wired
- Stateless REST APIs typically disable CSRF and use `SessionCreationPolicy.STATELESS`

### Configuration and Boot 3.x cues

- `application.yml` + profile variants; `@ConditionalOn*` may leave a bean absent at runtime
- `@ConfigurationProperties` is type-safe and `jakarta.validation`-validated; `@Value("${...}")` typos fail at runtime
- `jakarta.*` imports = Boot 3+; `javax.persistence` = pre-3.0
- `spring.threads.virtual.enabled=true` makes the request thread virtual - `synchronized` in the hot path pins the carrier; prefer `ReentrantLock`

## Output Format

Inject into the parent workflow's sections. Cite class/method, omit blocks with nothing to report.

**Flow Context**
- Stereotype + bean scope
- For HTTP: filter chain entry, method-security annotations
- Transaction boundary: where it opens, what runs inside, when it commits
- Async / scheduled / event hop (and the thread that runs the work)

**Non-Obvious Behavior**
- Proxy bypass in play (self-invocation, private/final, init-time) - name the call site
- External IO inside `@Transactional` - committed-before-tx vs lost-on-rollback
- JPA: dirty checking, lazy access after boundary, flush timing
- Security context not inherited across `@Async`

**Key Invariants**
- Singleton scope - field state shared across threads
- A proxied annotation fires only when invoked through the proxy
- Entity mutations persist only if a tx is active at commit
- Entities returned from a `@Transactional` method are detached
- External side effects inside `@Transactional` are not transactional - use outbox or `AFTER_COMMIT`
- `@Version` writers must handle conflict

**Change Impact Preview**
- Add `@Transactional` to a method called via `this.x()`: no effect - flag the call site
- Remove `readOnly=true` on a query method: doubles dirty-check cost
- Change `@Async` return to a non-future type: silently runs sync (still proxied) or loses exception surfacing
- Switch `@EventListener` to `@TransactionalEventListener(AFTER_COMMIT)`: publisher commits even if listener fails
- Move external IO out of `@Transactional`: changes ordering, may need outbox to preserve at-least-once
- Return DTO instead of entity: removes detachment risk; projection must cover all caller fields

## Avoid

- Treating a proxied annotation as always-firing - check the call path first
- Saying `save()` triggers the DB write (dirty checking + commit does)
- Describing `@EventListener` as async (it is sync unless `@Async`)
- Mentioning N+1 without naming the lazy field
- Conflating `@Bean` (method in `@Configuration`) with `@Component` (class)
- Ignoring `@ConditionalOn*` - the bean may not exist in this profile
