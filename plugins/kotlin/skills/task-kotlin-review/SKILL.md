---
name: task-kotlin-review
description: Kotlin / Spring Boot code review: null safety, coroutines, !! abuse, @Transactional, JPA; spawns perf/security/observability subagents.
agent: kotlin-tech-lead
metadata:
  category: backend
  tags: [kotlin, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` is passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 1 and Step 2. Cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an AC / NFR / task; flag out-of-scope changes as blockers; flag missing coverage of in-scope ACs as gaps. Never edit `spec.md`, `plan.md`, `tasks.md`.

# Kotlin / Spring Boot Code Review

## Purpose

Staff-level review with Kotlin-aware checks: null safety / `!!` discipline, `data class` vs JPA, plugin presence, coroutine structured concurrency, `@Transactional` boundaries, Virtual Thread pinning, `@MockkBean` vs `@MockBean`. Coordinates perf / security / observability subagents in parallel.

The stack-specific delegate of `task-code-review` for Kotlin / Spring Boot. Runs standalone with full PR/branch resolution.

## When to Use

- Reviewing a Kotlin / Spring Boot PR before merge
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-kotlin-implement`), incident triage (`/task-oncall-start`), single-error debug (`task-kotlin-debug`), new-system architecture (`task-design-architecture`), or single-scope reviews (delegate directly to the perf / security / observability workflow).

## Depth Levels

| Depth      | When                                       | What runs                                       |
| ---------- | ------------------------------------------ | ----------------------------------------------- |
| `quick`    | "Is this safe to merge?" - time-pressured  | Risk snapshot + top 3 findings (Phase A + B)    |
| `standard` | Default                                    | Phases A-E                                      |
| `deep`     | Architectural PRs, post-incident, Principal sign-off | Phases A-E + historical patterns + cross-PR |

Default: `standard`.

**Auto-promote to `deep`** if Phase A blast radius is Wide or Critical and user didn't pass `quick`. Surface as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                |
| --------------- | -------------------------------------------------------- |
| Core            | Phases A-E (Kotlin-flavored)                             |
| + Perf          | Core + parallel `task-kotlin-review-perf`                |
| + Security      | Core + parallel `task-kotlin-review-security`            |
| + Observability | Core + parallel `task-kotlin-review-observability`       |
| Full            | Core + all three subagents in parallel                   |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Kotlin-tuned):**

- **Security**: file uploads, `SecurityFilterChain` / `@PreAuthorize` changes, `@RequestBody` data class changes, raw JPQL / native SQL, secrets in `application.yml`, `@KafkaListener` consuming user input
- **Perf**: new Flyway / Liquibase migration, new `@Query` / `@EntityGraph`, new `Pageable` endpoints, loops over collections hitting DB or HTTP, new `@Cacheable`, new `Flow<T>` streaming
- **Observability**: new `@Service` / `@Component`, new external client (`WebClient` / `RestClient`), new `@Async` / `@Scheduled` / `CoroutineScope.launch`, logging or actuator config change, new Micrometer registrations, new `@TransactionalEventListener`
- Two or more categories present - promote to **Full**

## Invocation

| Invocation                     | Meaning                                                                     |
| ------------------------------ | --------------------------------------------------------------------------- |
| `/task-kotlin-review`          | Current branch vs its base - fails fast on trunk                            |
| `/task-kotlin-review <branch>` | `<branch>` vs its base (3-dot diff)                                          |
| `/task-kotlin-review pr-<N>`   | PR head in local `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first |

**No checkout required.** Read via ref-qualified diffs. Pass `--base <branch>` when PR opened against a non-trunk base.

Scope and depth flags compose: `/task-kotlin-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Behavioral principles (mandatory, first)

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not Kotlin/Spring Boot, redirect to `/task-code-review`.

### Step 3 - Resolve diff

Use skill: `review-precondition-check`. Forward `--base <branch>`. If it stops with a fail-fast message, surface verbatim and stop.

Once approved, read once and reuse:

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Skip this step when invoked as a subagent and the parent passed the precondition handle plus diff + log.

### Step 4 - Scope auto-escalation

Scan files + diff for escalation signals. Log each as `signal: <category> -> <file:line>`.

- Zero or `core-only` → Core
- One category → add it
- Two+ → Full
- Explicit user scope → respect (don't downgrade)

Surface decision in Summary's `Scope:` field.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`
- Use skill: `review-blast-radius`

Output risk level and blast radius before findings.

**Low-risk short-circuit:** Risk Low + Blast Narrow + no architecture-relevant files (security config, filters, API contracts, shared base classes, `application.yml`, Flyway migrations, `build.gradle.kts` plugins) - skip Phases C-D and produce Phase B findings only.

### Phase B - Kotlin correctness and safety

**Test coverage finding** (named, explicit, not buried in takeaways): if PR adds or modifies logic without JUnit / kotest / Spring slice / Testcontainers coverage. Minimum [Suggestion]; [High] for auth / Spring Security / `@PreAuthorize` / billing / multi-table writes / state machines / `CoroutineScope.launch` / `@KafkaListener` mutating data / Flyway changing column semantics.

**Kotlin checks:**

- [ ] **Null safety / `!!`**: no `!!` outside truly impossible-null sites; `T?` over `Optional<T>`; platform types treated nullable; `error()` / `requireNotNull` over `!!` for fail-fast
- [ ] **`data class` vs JPA**: every `@Entity` / `@MappedSuperclass` is a regular `class` with ID-based equals/hashCode
- [ ] **Kotlin plugins**: `kotlin("plugin.jpa")` + `kotlin("plugin.spring")` configured; no manual `open` workarounds
- [ ] **`@Transactional`**: writes at service layer (not controller / repository); no external I/O inside (use `@TransactionalEventListener(AFTER_COMMIT)` or outbox)
- [ ] **`@Transactional` self-invocation**: no `this.transactionalMethod()` from a same-bean caller
- [ ] **`@Transactional` on `suspend`**: no `withContext(...)` switches inside (detaches from TX)
- [ ] **Coroutine scope**: no `GlobalScope.launch`; fire-and-forget uses an injected `CoroutineScope` bean; `coroutineScope` for required fan-out; `supervisorScope` only with explicit fallbacks
- [ ] **`runBlocking`**: never in services / controllers; only at non-suspend framework boundaries
- [ ] **Dispatchers vs VTs**: with `spring.threads.virtual.enabled=true`, `Dispatchers.IO` for blocking JDBC is redundant; `Dispatchers.Default` for CPU only
- [ ] **`Flow` exception transparency**: no `throw` inside `collect`; cleanup in `finally` wrapped in `withContext(NonCancellable)` for suspend calls
- [ ] **Bean Validation**: every `@RequestBody` / `@RequestParam` data class has `@Valid` + `@field:`-targeted constraints
- [ ] **Strong typing**: `@RequestBody` uses DTOs, not JPA entities (mass-assignment risk - depth in `task-kotlin-review-security`)
- [ ] **N+1**: walking associations after a query uses `@EntityGraph` / `join fetch`; lazy access outside the TX flagged
- [ ] **`Optional` from repositories**: converted to `T?` at the boundary; no `.get()` without `isPresent()`
- [ ] **JPA entities in API**: controllers return DTOs / projections, never entities
- [ ] **Authorization**: every controller method has explicit `SecurityFilterChain` matcher or `@PreAuthorize`; `permitAll` documented
- [ ] **Error handling**: `@RestControllerAdvice` + `ProblemDetail`; sealed-class results converted at controller boundary; no blanket `catch (e: Exception)`; no `println(e)` / `e.printStackTrace()`
- [ ] **Bulk operations**: partial-failure defined; idempotency for retryable bulk; JPA batch size sized
- [ ] **Idempotency on writes**: any new POST/PUT/PATCH that mutates state checks `Idempotency-Key` (or equivalent) and short-circuits replays. [Blocker] for money/billing, [High] otherwise
- [ ] **Dual-write reliability**: DB write + event/HTTP publish uses outbox or `@TransactionalEventListener(AFTER_COMMIT)`. `BEFORE_COMMIT` for I/O = trap (rollback on listener exception); `AFTER_COMMIT` exceptions silently swallowed by default

**Migration PRs (any change in `db/migration/` or `db/changelog/`):**

- [ ] Two-phase deploys for rename / drop
- [ ] `NOT NULL` on existing columns via two-step
- [ ] `CREATE INDEX CONCURRENTLY` on large tables; concurrent statement outside a transaction
- [ ] FK validation deferred (or as a separate validate step)
- [ ] DDL and DML in separate migrations
- [ ] Rollback path documented
- Use skill: `ops-backward-compatibility` for client / in-flight impact
- Use skill: `kotlin-spring-db-migration-safety` for canonical patterns

**Concurrency:**

- [ ] Singleton beans hold no mutable state, or use `val` / `ConcurrentHashMap` / `AtomicReference` / lock
- [ ] **No `synchronized` on shared instances on Virtual Thread paths** (Boot 3.2+ with VT) - pins carrier thread. Use `ReentrantLock` or `Mutex`
- [ ] No `companion object` mutable fields (`var`) without explicit thread-safety design
- [ ] Race-prone updates use DB-level locking (`@Lock(LockModeType.PESSIMISTIC_WRITE)`, `@Version`)

Atomic skills consulted in Phase B:

- `kotlin-spring-jpa-performance` for JPA correctness
- `kotlin-spring-transaction` for `@Transactional` semantics
- `kotlin-spring-async-processing` for `@Async` / `CoroutineScope.launch`
- `kotlin-spring-exception-handling` for advice / sealed-result handling
- `kotlin-coroutines-spring` for `suspend` / `Flow`
- `kotlin-idioms` for general idiomatic review

### Phase C - Architecture guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering**: `@RestController` → `@Service` → `@Repository`. No business logic in controllers; no HTTP clients in repositories; no view rendering in services. Mapping via extension functions
- [ ] **Service-layer discipline**: controller orchestration > 5 lines extracted to `@Service`; intention-revealing service methods; cross-aggregate orchestration in services, not JPA `@PostPersist` / `@PostUpdate`
- [ ] **Anemic domain**: when rules accumulate in services and entities are pure data, flag for refactor (`task-kotlin-refactor`)
- [ ] **DI style**: primary-constructor injection only; no `@Autowired` fields; `lateinit` only for test fields and necessary cases; no `ApplicationContextAware`
- [ ] **Configuration**: typed `@ConfigurationProperties` over scattered `@Value`; profile-separated `application.yml`; no hardcoded config
- [ ] **Package layout**: feature-package preferred; cross-feature imports through public service interfaces
- [ ] **Multi-tenant isolation**: tenant scoping at repository / `@Filter` layer, not controller-only. `findByIdAndTenantId(id, tenantId)` over `findById(id)` + in-controller check (latter is racy)
- [ ] **Aspects**: cross-cutting concerns only - not hidden control flow that swallows exceptions or rewrites returns

Single-implementation `@Service` interface bloat is owned by Phase D (`kotlin-overengineering-review`).

**Multi-service PRs**: API contract compatibility checked (Spring Cloud Contract / Pact); deployment order documented or independent; use `ops-backward-compatibility` for inter-service changes.

### Phase D - AI-generated code quality

Use skill: `complexity-review`.
Use skill: `kotlin-overengineering-review` for the necessity catalog (redundant Bean Validation, defensive guards on guarantees, premature abstraction, scope-function nesting, single-variant sealed classes).

**AI smells not in the necessity catalog:**

- [ ] **Java-in-Kotlin**: `if (x != null)` chains over `?.` / `?:`; `for` loops over `map` / `filter`; companion-object statics where extension functions fit; `CompletableFuture` over `suspend`
- [ ] **Redundant mapping**: `Entity → Domain → ServiceDTO → ResponseDTO` when one extension function suffices
- [ ] **Test verbosity**: `@SpringBootTest` setup > 30 lines for a single assertion; `@MockkBean` chains that should be a slice
- [ ] **Reactive / coroutine misapplication**: `Mono` / `Flux` (or `suspend`) in a non-coroutine servlet stack
- [ ] **Comment cruft**: comments restating method names; KDoc on private helpers; stale TODOs

### Phase E - Maintainability

- [ ] **Naming**: services describe the operation (`OrderFulfillmentService`); data classes name their role; no `Util` / `Manager` / `Helper` accumulators; `internal` over `public` for module-local symbols
- [ ] **Magic numbers / strings**: extracted to `const val` / `@ConfigurationProperties`; `Duration.ofMinutes(...)` over `60_000L`
- [ ] **Hardcoded URLs / credentials**: in `application.yml` / env / Vault
- [ ] **Method length**: > 20 lines reviewed for extraction; > 50 lines flagged unless orchestrating private methods
- [ ] **Duplicated queries**: same JPQL / `Specification` in 3+ places extracted
- [ ] **Logging hygiene**: parameterized SLF4J (`log.info("order={}", id)`) - **never** Kotlin string templates (`log.info("order=$id")`); correct levels; no `println` / `System.out`
- [ ] **KDoc**: on public extension and `suspend` function contracts (cancellation, exception propagation)
- [ ] **`val` over `var`** except framework-required mutable fields

Use skill: `backend-coding-standards` for cross-language naming.
Use skill: `ops-observability` for cross-cutting logging / metrics presence (depth: `task-kotlin-review-observability`).

### Step 5 - Delegate extra scopes (if scope includes)

Spawn subagents in parallel:

| Scope                | Subagents                                                                                          |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| Core + Perf          | `task-kotlin-review-perf`                                                                          |
| Core + Security      | `task-kotlin-review-security`                                                                      |
| Core + Observability | `task-kotlin-review-observability`                                                                 |
| Full                 | All three in parallel                                                                              |

Each subagent prompt includes: resolved review target (`base_ref`, `head_ref`) + pre-read diff + log, depth, pre-confirmed stack, instruction to use its own Output Format.

If a subagent fails: continue with remaining results. Note `Scope incomplete: <scope>` in Summary.

### Step 6 - Synthesize (if Step 5 ran)

- Deduplicate cross-cutting findings (same issue across scopes → one entry citing all)
- Highest severity wins (`Blocker > High > Suggestion > Question`)
- Preserve `file:line`
- Order by severity, not scope
- Merge Next Steps into one prioritized list

## Feedback Labels

| Label        | Meaning                                       | Required |
| ------------ | --------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk   | Yes      |
| [High]       | Should fix - significant impact or smell      | Strong   |
| [Suggestion] | Would improve - non-blocking                  | No       |
| [Question]   | Need clarity from author                      | Clarify  |

No `[Nitpick]` or `[Praise]`.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line
- Issue: [Kotlin/Spring idiom: `!!` abuse, `data class` JPA, missing `kotlin-jpa` plugin, `GlobalScope.launch`, `synchronized` on VT, `@Transactional` self-invocation, `every` on suspend, etc.]
- Impact: [user-visible / operational]
- System Risk: [why systemic]
- Fix: [concrete Kotlin change with code]

### [High] file:line
- Issue:
- Impact:
- Fix:

### [Suggestion] file:line
- Improvement:

## Architecture Notes
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes
- Over-engineering:
- Simplification opportunities:

## Key Takeaways
- 2-4 bullets, systemic impact, what to address before merge

## Next Steps
1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit empty sections._
```

### Step 7 - Write report

Use skill: `review-report-writer` with `report_type: review`. Print the confirmation line.

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] Stack confirmed (or accepted from parent)
- [ ] `review-precondition-check` ran (or handle received)
- [ ] Diff and log read once via ref-qualified commands
- [ ] For `pr-ref`, user-run fetch surfaced and local ref existed
- [ ] When `head_matches_current` was false, user approval obtained
- [ ] Scope auto-escalation evaluated; decision recorded
- [ ] Depth auto-promoted to `deep` when Wide/Critical and user didn't pass `quick`
- [ ] Risk + blast radius stated before findings
- [ ] Phase B Kotlin checks applied (null-safety, `data class` JPA, plugins, `@Transactional`, scopes, dispatchers, Flow, validation, JPA-in-API, authz, advice, VT pinning)
- [ ] Phase C architecture checks applied
- [ ] Phase D applied via `complexity-review` + `kotlin-overengineering-review`; AI smells covered
- [ ] Phase E maintainability checks applied
- [ ] Missing tests raised as explicit finding
- [ ] Every Blocker states system risk
- [ ] Every finding has label + file:line + Kotlin fix
- [ ] If `--spec`, every finding traces to AC / NFR / task or is flagged out-of-scope blocker
- [ ] For non-Core scopes: subagents ran in parallel with pre-resolved handle
- [ ] Subagent findings merged with dedup + highest-severity-wins
- [ ] Failed scopes noted as `Scope incomplete: <scope>`
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by severity
- [ ] Report written via `review-report-writer`; confirmation printed

## Avoid

- State-changing git from this workflow
- Reviewing without reading full diff + log
- Generic backend advice when a Kotlin idiom applies
- Nitpicking style without a project standard
- Vague feedback without concrete Kotlin fix
- Blocking on preference vs correctness / risk / maintainability
- Running extra scopes when `core-only` was passed
- Sequential extra scopes that could run in parallel
- Appending raw subagent reports section-by-section
- Recommending `WebSecurityConfigurerAdapter`, `@Autowired` fields, `data class` JPA, `GlobalScope.launch`, `every` for suspend, `@MockBean` for Kotlin
