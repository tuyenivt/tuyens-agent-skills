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

# Spring Boot Code Review

Spring-aware staff-level review umbrella. Stack-specific delegate of `task-code-review`. Runs standalone with full PR/branch resolution. Coordinates Spring perf / security / observability subagents in parallel.

## When to Use

- Pre-merge Spring Boot PR review, post-AI-generation quality gate, architecture drift detection.
- **Not for:** design (`task-spring-implement`), incidents (`/task-oncall-start`), debugging (`task-spring-debug`), new-system architecture (`task-design-architecture`), single-scope reviews (delegate to `task-spring-review-{perf,security,observability}`).

## Depth and Scope

| Depth      | When                                                              | Runs                                  |
| ---------- | ----------------------------------------------------------------- | ------------------------------------- |
| `quick`    | Fast "safe to merge?" snapshot                                    | Phase A + B summary, top 3 findings   |
| `standard` | Default                                                           | Phases A-E                            |
| `deep`     | Architectural PRs, post-incident review, Principal sign-off       | A-E + historical pattern matching     |

**Auto-promote to `deep`** when Phase A yields Blast Radius `Wide`/`Critical` and the user did not pass `quick`. Surface as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

| Scope             | Adds                                       |
| ----------------- | ------------------------------------------ |
| Core (default)    | Phases A-E only                            |
| + Perf            | `task-spring-review-perf` subagent         |
| + Security        | `task-spring-review-security` subagent     |
| + Observability   | `task-spring-review-observability` subagent|
| Full              | All three in parallel                      |

**Auto-escalation signals** (Step 4 scans the diff; pass `core-only` to suppress):

- **Security:** `MultipartFile`, `SecurityFilterChain`, `@PreAuthorize`/`@PostAuthorize`, `@RequestBody` DTO changes, raw JPQL/native SQL, secrets in `application.yml`, listener consuming user input.
- **Perf:** new Flyway/Liquibase migration, new `@Query`/`@EntityGraph`, new `Pageable` endpoint, loop hitting DB/HTTP, new `@Cacheable`.
- **Obs:** new `@Service`/external client (`RestClient`/`WebClient`/Feign), new `@Async`/`@Scheduled`, logging or actuator change, new Micrometer `Timer`/`Counter`, new `@TransactionalEventListener`.

Two-plus categories -> Full. User-passed scope wins but signals are still recorded so the Summary documents what was deferred.

## Invocation

| Form                            | Meaning                                                           |
| ------------------------------- | ----------------------------------------------------------------- |
| `/task-spring-review`           | Current branch vs base; fails fast on trunk                       |
| `/task-spring-review <branch>`  | `<branch>` vs base (3-dot diff)                                   |
| `/task-spring-review pr-<N>`    | User-fetched local ref `pr-<N>`; see `review-precondition-check`  |

Flags compose: `/task-spring-review pr-50273 --base release/2026.05 +security deep`. No checkout required.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Spec-Aware Preamble (conditional)

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the diff, use skill: `spec-aware-preamble`. Cross-check the diff against `spec.md` and `plan.md`: every changed surface traces to an AC/NFR/task; out-of-scope -> blocker; missing AC coverage -> gap. Never edit spec artifacts.

### Step 3 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review`.

### Step 4 - Resolve the Diff

Use skill: `review-precondition-check` (forward `--base`). Surface fail-fast messages verbatim and stop.

Once approved, read once and reuse (skip when a parent passed the handle plus artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

### Step 5 - Evaluate Auto-Escalation

Scan files and diff against signal categories (above). Log `signal: <category> -> <file:line>` for each match. Resolve scope (Core / +X / Full) and surface in Summary: `auto-escalated from Core; signals: <list>` or, when user-pinned with conflicting signals, `Scope user-pinned; <category> signals present: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`.
- Use skill: `review-blast-radius`.
- Output Risk and Blast Radius before findings.

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` + no architecture-relevant files touched (security config, filters, API contracts, shared base classes, aspects, `application.yml`, migrations) -> skip Phases C-D, deliver Phase B findings only.

### Phase B - Spring Correctness and Safety

Logical correctness, error handling, backward compatibility, transaction boundary correctness. Use atomic skills `spring-transaction`, `spring-jpa-performance`, `spring-async-processing`, `spring-exception-handling`, `spring-messaging-patterns` as relevant.

**Spring idioms (cite the named smell in findings):**

- [ ] **Transactions** - writes at service layer; no HTTP/broker/IO inside `@Transactional`; `readOnly = true` on reads; `rollbackFor` for checked exceptions; no `this.txMethod()` self-invocation.
- [ ] **JPA in API** - controllers never expose `@Entity` types; DTO/record/projection only.
- [ ] **N+1** - `@EntityGraph`/`join fetch` wherever lazy associations are walked post-query (depth -> `task-spring-review-perf`).
- [ ] **Bean Validation** - `@Valid` on every `@RequestBody`/`@RequestParam` DTO; no manual checks duplicating annotations.
- [ ] **Authorization coverage** - every controller method covered by `SecurityFilterChain` matcher or `@PreAuthorize`; `permitAll` documented (depth -> `task-spring-review-security`).
- [ ] **Error handling** - `@RestControllerAdvice` maps validation/not-found/access-denied; no blanket `catch (Exception)`; no `printStackTrace()`.
- [ ] **Optional discipline** - `.orElseThrow`/`.map`; never `.get()` unguarded; never as a parameter.
- [ ] **Idempotency** - monetary/notification side effects accept an idempotency key.
- [ ] **Dual-write** - `save` + `kafkaTemplate.send` + `save` in `@Transactional` is a smell; use outbox or `AFTER_COMMIT`.
- [ ] **VT pinning** - on `spring.threads.virtual.enabled=true`, no `synchronized` on shared instances; use `ReentrantLock`/`StampedLock`.
- [ ] **Race-prone updates** - counters/balances/state transitions use `@Lock(PESSIMISTIC_WRITE)`/`@Version`/`SELECT FOR UPDATE`.
- [ ] **Singleton state** - no mutable fields; if required, `final` immutable, `ConcurrentHashMap`, `AtomicReference`, or lock-guarded.
- [ ] **Bulk operations** - partial-failure path; `hibernate.jdbc.batch_size` set; retries idempotent.

**Test coverage as a named finding** (not buried in Takeaways): logic changes without JUnit / slice / Testcontainers -> `[Suggestion]`; escalate to `[High]` for security, money, multi-table state machines, `@Async`/`@KafkaListener` mutations, or migrations changing column semantics.

**Migration PRs** (`db/migration/`, `db/changelog/`) - use skills `spring-db-migration-safety`, `ops-backward-compatibility`:

- [ ] Column rename/drop via two-phase deploy (add -> backfill -> cut over -> remove).
- [ ] New `NOT NULL` on existing columns via two-step (add nullable -> backfill -> set NOT NULL).
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`, split outside a transaction.
- [ ] FKs validated separately (`NOT VALID` then `VALIDATE`).
- [ ] Long backfills isolated from DDL, not inline in Flyway/Liquibase.
- [ ] Rollback path documented.

### Phase C - Spring Architecture Guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering** - `@RestController` -> `@Service` -> `@Repository`. No business logic in controllers; no HTTP clients in repos/entities; no view rendering in services. DTO mapping at service/controller boundary.
- [ ] **Service-layer discipline** - controller orchestration > 5 lines -> extract `@Service`; methods reveal intent (`fulfillOrder(orderId)`) over CRUD pass-through; cross-aggregate work lives in a service, not `@PostPersist`/`@PostUpdate`.
- [ ] **Anemic domain** - rules accumulating in services with entities as pure data -> flag for refactor (see `task-spring-refactor`).
- [ ] **DI style** - constructor only; `final` fields with `@RequiredArgsConstructor`; no setter injection, no field `@Autowired`, no `ApplicationContextAware`.
- [ ] **Configuration** - typed `@ConfigurationProperties` records over `@Value`; profiles separated; no hardcoded values.
- [ ] **Module boundaries** - feature-package layout; cross-feature access via public service interfaces, not direct `OtherFeatureRepository` calls.
- [ ] **Multi-tenant isolation** - tenant scoping at repository/`@Filter`/`@TenantId` layer. Derived queries like `findByIdAndUserId` are acceptable only when every read on that aggregate uses one - a single missing variant exposes other tenants' data.
- [ ] **Read replica / routing** - `AbstractRoutingDataSource` reads declare target via `@Transactional(readOnly = true)` or explicit annotation; no surprise cross-DB joins.
- [ ] **Aspect discipline** - `@Aspect` for genuinely cross-cutting concerns, not hidden control flow.

**Multi-service PRs:** API contract compatibility verified (Spring Cloud Contract/Pact); deployment order documented or independent; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity. Use skill: `spring-overengineering-review` for necessity findings (redundant Bean Validation, defensive guards, premature abstraction) - the atomic owns the catalog.

**Additional Spring AI smells:**

- [ ] Redundant mapping chains (`Entity -> Domain -> ServiceDTO -> ResponseDTO` when one would do).
- [ ] `@SpringBootTest` > 30 lines for a single assertion; `@MockBean` chains better served by a slice test.
- [ ] `Mono`/`Flux` in a servlet stack.
- [ ] Comments restating method names; Javadoc on private helpers; stale TODOs.

### Phase E - Spring Maintainability

Use skill: `backend-coding-standards`. Use skill: `ops-observability` for cross-cutting logging/metrics presence.

- [ ] **Naming** - operations described (`OrderFulfillmentService` over `OrderHelper`); records named by role (`OrderUpdateRequest`); no `Util`/`Manager`/`Helper` grab bags; package-private over `public` when not crossing the feature boundary.
- [ ] **Magic numbers/strings** - `static final` or `@ConfigurationProperties`; durations use `Duration.ofMinutes(...)`.
- [ ] **Hardcoded URLs/credentials** - in `application.yml`/env/Vault.
- [ ] **Method length** - > 20 lines reviewed for extraction; > 50 flagged unless clearly orchestrating named helpers.
- [ ] **Duplicated queries** - same JPQL/`Specification` predicate in 3+ places -> `Specification` factory or repo method.
- [ ] **Logging hygiene** - SLF4J parameterized, not concatenation; correct levels; MDC for structured fields (depth -> `task-spring-review-observability`).

### Step 6 - Delegate Extra Scopes in Parallel

Skip if Core only. Spawn each extra subagent in parallel with the main thread.

| Scope                | Subagents                                                          |
| -------------------- | ------------------------------------------------------------------ |
| Core + Perf          | `task-spring-review-perf`                                          |
| Core + Security      | `task-spring-review-security`                                      |
| Core + Observability | `task-spring-review-observability`                                 |
| Full                 | All three in parallel                                              |

**Subagent prompt contract:** pass the resolved `base_ref`/`head_ref`, the already-read diff and commit log, depth level, and pre-confirmed stack. Subagent skips `review-precondition-check` and re-reading the diff. Return findings using its own Output Format.

**Failure isolation:** if a subagent fails or times out, continue. Record `Scope incomplete: <scope> review did not complete` under Summary.

### Step 7 - Synthesize

Skip if Step 6 didn't run. Merge subagent findings into the single Output Format - never append raw reports.

- **Deduplicate** cross-cutting findings (e.g., external call in `@Transactional` flagged by Phase B and Perf) into one entry citing all scopes.
- **Severity wins** when labels differ: `Blocker` > `High` > `Suggestion` > `Question`.
- **Preserve `file:line` citations**; order by severity, not by scope.
- **Merge Next Steps**: combine, preserve `[Implement]`/`[Delegate]`, dedupe, re-sort.

### Step 8 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Print confirmation. The report writer owns label semantics (`[Blocker]`/`[High]`/`[Suggestion]`/`[Question]` - no `[Nitpick]`/`[Praise]`).

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(append `auto-escalated from Core; signals: <list>` if applicable)_
**Depth:** quick | standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` if applicable)_

## High-Impact Findings

### [Blocker] file:line
- Issue: [named Spring idiom: `@Transactional` self-invocation, fat controller, JPA entity in API, field `@Autowired`, missing `@PreAuthorize`, `synchronized` on VT, dual-write, etc.]
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

_Omit if no actionable findings._
```

Omit empty sections.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - spec preamble loaded when `--spec` / `.specs/<slug>/spec.md` present; findings traced to AC/NFR/task or flagged out-of-scope
- [ ] Step 3 - stack confirmed (or accepted from parent)
- [ ] Step 4 - `review-precondition-check` ran (or handle received); diff and commit log read once and shared with subagents
- [ ] Step 5 - scope decision recorded with firing signals; user-pinned conflicts surfaced
- [ ] Phase A - Risk and Blast Radius stated before findings; depth auto-promoted on Wide/Critical unless `quick`
- [ ] Phase B - Spring idioms applied (transactions, JPA-in-API, authz coverage, exception advice, VT pinning, dual-write); migration safety where applicable; missing tests raised as named finding
- [ ] Phase C - layering, anemic domain, constructor injection, configuration, boundaries, multi-tenant
- [ ] Phase D - `complexity-review` + `spring-overengineering-review` invoked; remaining AI smells covered
- [ ] Phase E - maintainability applied
- [ ] Step 6 - subagents ran in parallel with pre-resolved handle (when scope > Core)
- [ ] Step 7 - findings deduped, highest-severity wins, severity-ordered, raw subagent reports not appended; missing scopes noted
- [ ] Step 8 - report written via `review-report-writer`; confirmation printed
- [ ] Every Blocker cites system risk; every finding has label, `file:line`, actionable Spring fix
- [ ] Next Steps tagged `[Implement]`/`[Delegate]`, ordered Blocker > High > Suggestion (omit if none)

## Avoid

- State-changing git (`fetch`/`checkout`/etc.) from this workflow.
- Reviewing without reading full diff + commit log first.
- Generic backend phrasing when a Spring idiom exists ("extract to a `@Service`", not "helper class").
- Vague feedback without a concrete Spring fix; blocking on personal preference; nitpicking absent project standard.
- Running perf/security/observability when user passed `core-only`; sequential subagent runs when they could be parallel.
- Appending raw subagent reports instead of one severity-ordered list.
- Approving `WebSecurityConfigurerAdapter`, field `@Autowired`, or `@Transactional` self-invocation.
