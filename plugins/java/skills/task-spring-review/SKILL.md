---
name: task-spring-review
description: "Spring Boot PR review: layering, fat controllers, JPA leaks, @Transactional misuse, VT pinning; parallel perf/security/obs subagents."
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the diff, load `Use skill: spec-aware-preamble` after `behavioral-principles`. Cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an AC, NFR, or task; flag out-of-scope changes as blockers; flag missing AC coverage as gaps. Never edit `spec.md` / `plan.md` / `tasks.md`.

# Spring Boot Code Review

Spring-aware staff-level review umbrella. Spring-specific correctness, architecture, AI-quality, and maintainability checks. Coordinates Spring-specific perf / security / observability subagents in parallel.

Stack-specific delegate of `task-code-review` for Java / Spring Boot. **Runs standalone** with full PR/branch resolution.

## When to Use

- Reviewing a Spring Boot PR before merge
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**
- Pre-implementation design (use `task-spring-implement`)
- Active incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-spring-debug`)
- New-system architecture (use `task-design-architecture`)
- Single-scope reviews - delegate directly to `task-spring-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth      | When                                                                      | What Runs                                                  |
| ---------- | ------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `quick`    | "Is this safe to merge?" - fast risk snapshot                             | Risk snapshot + top 3 findings (Phases A + B summary)      |
| `standard` | Default                                                                   | Phases A-E                                                 |
| `deep`     | Architectural PRs, post-incident change review, Principal sign-off        | Phases A-E + historical pattern matching + cross-PR context |

Default: `standard`. **Auto-promote to `deep`** when Phase A computes Blast Radius `Wide` or `Critical` and the user did not pass `quick`. Surface in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                   |
| --------------- | --------------------------------------------------------------------------- |
| Core            | Phases A-E only (Spring-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-spring-review-perf`                         |
| + Security      | Core + parallel subagent: `task-spring-review-security`                     |
| + Observability | Core + parallel subagent: `task-spring-review-observability`                |
| Full            | Core + all three Spring subagents in parallel                               |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Spring-tuned):**

- `MultipartFile`, `SecurityFilterChain` / `@EnableMethodSecurity`, `@PreAuthorize` / `@PostAuthorize`, `@RequestBody` DTO changes, raw JPQL / native SQL, secrets in `application.yml`, listener consuming user input → **+Security**
- New Flyway/Liquibase migration, new `@Query` / `@EntityGraph`, new `Pageable` endpoints, payload endpoints, loops hitting DB or HTTP, new `@Cacheable` → **+Perf**
- New `@Service` / `@Component`, new external client (`RestClient`/`WebClient`/Feign), new `@Async` / `@Scheduled`, `logback-spring.xml` / `application.yml` logging or actuator change, new Micrometer `Timer`/`Counter`, new `@TransactionalEventListener` → **+Observability**
- Two or more signal categories → **Full**

## Invocation

| Invocation                     | Meaning                                                                                                                                                              |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-spring-review`          | Current branch vs base; fails fast on trunk (`main`/`master`/`develop`)                                                                                              |
| `/task-spring-review <branch>` | `<branch>` vs base (3-dot diff)                                                                                                                                      |
| `/task-spring-review pr-<N>`   | PR head fetched into local branch `pr-<N>` (user runs `git fetch origin pull/<N>/head:pr-<N>`; see `review-precondition-check` for GitLab/Bitbucket variants)        |

No checkout required. Stay on your current branch; the workflow reads via ref-qualified diffs.

**Explicit base override:** pass `--base <branch>` when the PR was opened against a non-trunk base. Flags compose: `/task-spring-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not Spring Boot, stop and tell the user to invoke `/task-code-review`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` (forward `--base` if passed). If it stops with a fail-fast message, surface it verbatim and stop.

Once approved, read once and reuse:

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Skip this step when a parent dispatcher passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for auto-escalation signals (above). Log `signal: <category> -> <file:line>` for each.

- Zero signals or `core-only` → Core
- One signal category → matching extra scope
- Two or more → Full
- User-passed explicit scope → respect it; still record signals so the Summary documents what was deliberately deferred

Surface decision in Summary. If escalated: `auto-escalated from Core; signals: <list>`. If user-pinned with conflicting signals: `Scope user-pinned to Core; +Security signals present: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure-propagation scope
- Output risk level and blast radius before findings

**Low-risk short-circuit:** if Phase A yields Risk `Low` and Blast Radius `Narrow`, AND the change does not touch architecture-relevant files (security config, filters, API contracts, shared base classes, aspects, `application.yml`, Flyway migrations), skip Phases C-D - produce a streamlined output with Phase B findings only.

### Phase B - Spring Correctness and Safety

Logical correctness, error handling, edge cases affecting state integrity, backward compatibility, transaction boundary correctness.

**Test coverage finding:** if the PR adds or modifies logic without JUnit / Spring slice / Testcontainers coverage, raise as an explicit finding. Default `[Suggestion]`; escalate to `[High]` for critical paths (Spring Security / OAuth2 / JWT, `@PreAuthorize`, money / billing, multi-table state machines, `@Async` / `@KafkaListener` that mutate data, Flyway migrations changing column semantics). A named entry in Findings - not buried in Key Takeaways.

**Spring correctness scan:**

- [ ] **Transactions** - writes at service layer; no HTTP / broker / external IO inside `@Transactional`; `readOnly = true` on read paths; checked-exception `rollbackFor`; no `this.txMethod()` self-invocation. See `spring-transaction`.
- [ ] **JPA in API** - controllers never return or accept `@Entity` types - DTO/record/projection only. See `spring-jpa-performance`.
- [ ] **N+1** - `@EntityGraph` / `join fetch` on any code walking lazy associations after a query (depth → `task-spring-review-perf`).
- [ ] **Bean Validation** - `@Valid` on every `@RequestBody` / `@RequestParam` DTO + `@NotNull` / `@Size` / `@Pattern`; no manual validation duplicating annotations.
- [ ] **Authorization coverage** - every controller method covered by a `SecurityFilterChain` matcher or `@PreAuthorize`; `permitAll` documented (depth → `task-spring-review-security`).
- [ ] **Error handling** - `@RestControllerAdvice` maps `MethodArgumentNotValidException` / `EntityNotFoundException` / `AccessDeniedException`; no blanket `catch (Exception)`; no `printStackTrace()`. See `spring-exception-handling`.
- [ ] **`Optional` discipline** - `.orElseThrow` / `.map`; never `.get()` without `isPresent()`; never as a method parameter.
- [ ] **Idempotency on state-mutating writes** - monetary / billing / notification side effects accept an idempotency key; retries otherwise double-charge.
- [ ] **Dual-write reliability** - any `save` + `kafkaTemplate.send` + `save` inside `@Transactional` is a smell. See `spring-messaging-patterns` for outbox / AFTER_COMMIT.
- [ ] **Bulk operations** - partial-failure handling defined; `hibernate.jdbc.batch_size` set; retries idempotent.

**Migration PRs** (`db/migration/` or `db/changelog/`):

- [ ] Two-phase deploys for column rename / drop (add → backfill → cut over → remove)
- [ ] `NOT NULL` on existing columns added via two-step (add nullable → backfill → set NOT NULL)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY`; migration split so the concurrent statement runs outside a transaction
- [ ] FKs added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL; long backfills not in Flyway/Liquibase scripts
- [ ] Rollback path documented
- Use skill: `ops-backward-compatibility` for client/session/in-flight impact
- Use skill: `spring-db-migration-safety` for safe-migration patterns

**Concurrency safety:**

- [ ] Singleton beans hold no mutable state; if state is required, `final` immutable / `ConcurrentHashMap` / `AtomicReference` / lock-guarded
- [ ] **No `synchronized` on shared instances on Virtual Thread paths** (Boot 3.2+ with `spring.threads.virtual.enabled=true`) - pinning the carrier defeats the model. Use `ReentrantLock` / `StampedLock`.
- [ ] No `static` mutable fields
- [ ] Race-prone updates (counters, balance, state transitions) use DB-level locking (`@Lock(PESSIMISTIC_WRITE)`, `@Version`, or `SELECT ... FOR UPDATE`)
- [ ] Cache writes thread-safe; `@Cacheable` keys deterministic; lock-on-fill on hot keys (Caffeine `LoadingCache`)

Use skill: `spring-jpa-performance`, `spring-transaction`, `spring-async-processing`, `spring-exception-handling` as relevant to the diff.

### Phase C - Spring Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations, new coupling, circular dependencies, bypassed abstractions, boundary erosion.

- [ ] **Layering** - `@RestController` → `@Service` → `@Repository`. No business logic in controllers; no HTTP clients in repositories or entities; no view rendering inside services. Repositories return entities or projections; DTO mapping at service or controller boundary
- [ ] **Service-layer discipline** - controller method with > 5 lines of orchestration → extract to a `@Service`; services expose intention-revealing methods (`fulfillOrder(orderId)`), not CRUD pass-throughs; cross-aggregate work in a service, not in `@PostPersist` / `@PostUpdate`
- [ ] **Anemic domain** - rules accumulating in services with entities as pure data → flag for refactor (see `task-spring-refactor`)
- [ ] **DI style** - constructor injection only; `final` fields with `@RequiredArgsConstructor`; no setter injection; no `ApplicationContextAware`
- [ ] **Configuration discipline** - typed `@ConfigurationProperties` records over `@Value("${...}")`; `application.yml` profiles separated; no hardcoded values
- [ ] **Module boundaries** - feature-package layout preferred; cross-feature imports go through public service interfaces, not direct `OtherFeatureRepository` calls
- [ ] **Multi-tenant isolation** - tenant scoping at the repository / `@Filter` / `@TenantId` layer, not the controller alone. Derived queries taking the tenant as a parameter (`findByIdAndUserId`) are acceptable only when **every** repository read on that aggregate uses one - a single missing variant exposes other tenants' data
- [ ] **Multi-database / read replica** - `AbstractRoutingDataSource` queries declare target via `@Transactional(readOnly = true)` or explicit annotation; no surprise cross-DB joins
- [ ] **Aspect discipline** - `@Aspect` for genuinely cross-cutting concerns, not hidden control flow

**Multi-service PRs:**

- API contract compatibility checked (Spring Cloud Contract or Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for changed inter-service contracts

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity and over-engineering. Use skill: `spring-overengineering-review` for necessity findings (redundant Bean Validation, defensive guards, premature abstraction). The atomic owns the catalog and citation contract.

**Spring AI smells not covered by the necessity skill:**

- [ ] **Redundant mapping layers** - `Entity → DomainObject → ServiceDTO → ResponseDTO` when one would suffice
- [ ] **Test verbosity** - `@SpringBootTest` setup > 30 lines for a single assertion; `@MockBean` chains that could be a slice test
- [ ] **Reactive misapplication** - `Mono` / `Flux` in a non-reactive servlet stack
- [ ] **Comment cruft** - comments restating method names; Javadoc on private helpers; stale TODOs

### Phase E - Spring Maintainability

- [ ] **Naming** - services describe their operation (`OrderFulfillmentService` over `OrderHelper`); records named after their role (`OrderUpdateRequest`); no `Util` / `Manager` / `Helper` accumulating unrelated methods; package-private over `public` when not crossing the feature boundary
- [ ] **Magic numbers / strings** - extracted to `static final` or `@ConfigurationProperties`; durations use `Duration.ofMinutes(...)` not `60_000L`
- [ ] **Hardcoded URLs / credentials** - in `application.yml` / env / Vault, never inline
- [ ] **Method length** - methods > 20 lines reviewed for extraction; > 50 lines flagged unless they're a clearly orchestrating service method calling named private helpers
- [ ] **Duplicated queries** - same JPQL / `Specification` predicate in 3+ places → factor into a `Specification` factory or repository method
- [ ] **Logging hygiene** - SLF4J parameterized (`log.info("processing order={}", orderId)`), not concatenation; correct levels (`error` for actionable, `warn` recoverable, `info` state transitions, `debug` verbose); MDC for structured fields (depth → `task-spring-review-observability`)

Use skill: `backend-coding-standards` for cross-language conventions. Use skill: `ops-observability` for cross-cutting logging / metrics presence.

### Step 5 - Delegate Extra Scopes in Parallel

If scope is Core only, skip this step.

For each extra scope, spawn an independent subagent **in parallel** with the main thread.

| Scope                | Subagents                                                                                                                    |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | `task-spring-review-perf`                                                                                                    |
| Core + Security      | `task-spring-review-security`                                                                                                |
| Core + Observability | `task-spring-review-observability`                                                                                           |
| Full                 | All three in parallel                                                                                                        |

**Subagent prompt contract:**

- Resolved review target from Step 3 (`base_ref`, `head_ref`) + already-read diff and commit log - subagent skips `review-precondition-check` and `git diff`
- Depth level
- Pre-confirmed stack
- Instruction to return findings using its own skill's Output Format

**Failure isolation:** if a subagent fails / times out, continue with the rest. Note the missing scope in the synthesized output.

### Step 6 - Synthesize

(Skip if Step 5 didn't run.) Merge subagent findings into the single Output Format - do not append raw reports.

- **Deduplicate cross-cutting findings** - same issue surfacing in multiple scopes (e.g., external call inside `@Transactional` flagged by Core/Phase B and Perf). One entry citing all scopes.
- **Severity wins** when labels differ across scopes (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations**.
- **Order by severity, not by scope.**
- **Note missing scopes** under Summary: `Scope incomplete: <scope> review did not complete`.
- **Merge Next Steps** - combine Core + subagent steps; preserve `[Implement]` / `[Delegate]`; dedupe items mapping to the same fix; re-sort by severity.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write the assembled review to the report file before ending; print confirmation.

## Feedback Labels

| Label        | Meaning                                     |
| ------------ | ------------------------------------------- |
| `[Blocker]`  | Must fix before merge - correctness or risk |
| `[High]`     | Should fix - significant impact or smell    |
| `[Suggestion]` | Would improve - non-blocking              |
| `[Question]` | Need clarity from author                    |

No `[Nitpick]` or `[Praise]`.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [name the Spring idiom: `@Transactional` self-invocation, fat controller, JPA entity in API, `@Autowired` field injection, missing `@PreAuthorize`, `synchronized` on VT, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Spring change with code]

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
- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized, each tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit if no actionable findings._
```

Omit empty sections.

## Rules

- Review the whole change as a system impact, not file-by-file
- Lead with risk before line-level findings
- Apply Spring conventions over generic backend ones
- Provide actionable feedback with Spring code examples
- No nitpicking on style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only`
- Delegate perf / security / observability depth to dedicated subagents

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed (or accepted from parent)
- [ ] `review-precondition-check` ran (or handle received); `base_ref` / `head_ref` / `current_branch` / `head_matches_current` captured. If `--base` was passed, `base_source: explicit-override`
- [ ] Diff and commit log read once and reused (and shared with subagents) - no mid-review re-issuing
- [ ] For `pr-ref` mode, user-run fetch surfaced; local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval obtained
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded with firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level and blast radius stated before findings
- [ ] Phase B Spring correctness applied: transactions, JPA-in-API, `@PreAuthorize` coverage, exception advice, VT pinning
- [ ] Phase C architecture applied: layering, anemic domain, constructor injection, configuration discipline, package boundaries, multi-tenant
- [ ] Phase D via `complexity-review` + `spring-overengineering-review`; remaining AI smells covered
- [ ] Phase E maintainability applied
- [ ] Missing tests raised as a named finding (not in Takeaways)
- [ ] Every Blocker cites system risk
- [ ] Every finding has label, `file:line`, actionable Spring fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged out-of-scope
- [ ] For non-Core scopes, Spring subagents ran in parallel with pre-resolved diff handle
- [ ] Subagent findings merged with dedup + highest-severity-wins; raw subagent reports not appended
- [ ] Failed/missing subagent scope noted under Summary
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Blocker > High > Suggestion (omit if none)
- [ ] Review report written via `review-report-writer`; confirmation printed

## Avoid

- Running `git fetch`, `git checkout`, or state-changing git from this workflow
- Reviewing without reading full diff + commit log first
- Generic backend conventions when a Spring idiom exists (say "extract to a `@Service`", not "helper class")
- Nitpicking style where no project standard exists
- Vague feedback without a concrete Spring fix
- Blocking on personal preference
- Running perf / security / observability when user passed `core-only`
- Duplicating subagent depth checks here
- Sequential subagent runs when they could be parallel
- Appending raw subagent reports instead of merging into one severity-ordered list
- Approving `WebSecurityConfigurerAdapter`, `@Autowired` field injection, or `@Transactional` self-invocation
