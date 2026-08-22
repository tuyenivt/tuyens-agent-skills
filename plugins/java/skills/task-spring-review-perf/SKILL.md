---
name: task-spring-review-perf
description: "Spring Boot perf review: JPA/Hibernate N+1, fetch strategies, Virtual Thread compatibility, HikariCP, async throughput, Spring caching."
agent: java-performance-engineer
metadata:
  category: backend
  tags: [java, spring-boot, performance, jpa, hibernate, virtual-threads, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Performance Review

Spring-aware perf review naming JPA / Hibernate, Spring Data, Virtual Thread, HikariCP, Spring caching idioms directly. Findings carry measured or estimated impact (latency, throughput, query count, GC pressure) and concrete fixes.

Stack-specific delegate of `task-code-review-perf`.

## When to Use

- Spring Boot PR / branch for perf regressions
- Slow `@RestController`, `@Async` task, `@Scheduled` job, or batch job
- Pre-merge pass on JPA queries, repositories, fetch graphs, `@Transactional`
- Quarterly N+1 / query-plan / pool-sizing sweep

**Not for:** general Spring review (`task-code-review`), security (`task-code-review-security`), pre-implementation design (`task-spring-implement`).

## Depth

| Depth      | When                                              | Reading scope                                     | Adds                                        |
| ---------- | ------------------------------------------------- | ------------------------------------------------- | ------------------------------------------- |
| `standard` | Default                                           | Changed hunks plus the files they call into       | -                                           |
| `deep`     | Requested, handed down by `task-spring-review`, or any whole-service sweep | Every file in scope read in full, plus config and migrations repo-wide - on a diff review that is the touched files; on a sweep, Step 4's categories | `Capacity and Load-Test Plan` section |

At `deep`, use profiling data (JFR / async-profiler / Micrometer) when available. Without it, build the capacity estimate as: **per-request connection hold time** (query time + lazy-load count x per-query cost + blocking HTTP time) -> **usable connections** (`pods x maximumPoolSize`, capped by DB `max_connections` minus reserved) -> **ceiling = usable connections / hold time**. Every unit cost you did not measure is a declared assumption listed with the estimate; the scaling claim is what has to hold, not the absolute number.

Invocation forms (`/task-spring-review-perf [<branch>|pr-<N>] [standard|deep] [--base <branch>]`) follow `task-code-review-perf`. When invoked as a subagent, the parent passes the pre-confirmed stack, the precondition handle, pre-read diff and commit log, depth, and round; Steps 2-3 consume those instead of re-running.

**Whole-service sweep** (quarterly N+1 / query-plan / pool-sizing pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run every remaining step, Step 4 onward, repo-wide at `HEAD` (Step 4's categories read in full, not per changed file). Read "the diff" as "the service" in every step below, including the Self-Check's N/A rule. A sweep runs at `deep` - pool-sizing is the capacity question. Findings cite current code; `branch` = the current branch name, `base_ref` = `head_ref` = `HEAD`, and `base_sha` = `head_sha` = `git rev-parse HEAD`. Round 2+ of a sweep reconciles against the prior report using `head_files` in place of a diff and name-status list.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Accept a pre-confirmed stack from a parent (`task-spring-review`) and skip detection. Standalone: use skill: `stack-detect`; if not Spring Boot, stop and route the user to `/task-code-review-perf`.

Record the Java version, Spring Boot version, and **database engine** - the Step 6 and Step 7 checklists branch on all three. Below Java 21 / Boot 3.5, review the version actually present: mark virtual-thread rows N/A when the runtime cannot have them, and note the version gap on the Summary's `Stack Detected` line rather than reporting against a version the project does not run.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Once the handle is emitted, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim and stop - **except** a trunk fail-fast, which routes to the whole-service sweep above.

**Round gate (standalone only).** Before reviewing, look for a prior report. Its filename is `review-perf-<branch>.md` with `review-report-writer`'s filename sanitization applied to `<branch>` (a branch containing `/` does not name a file). If it exists with valid frontmatter and its `head_sha` equals the current head and the requested depth does not exceed its `depth`, print `No new commits since prior perf review at <sha_short>.` and stop. Otherwise `round = prior.round + 1` and `prior_head_sha = prior.head_sha`; missing or invalid frontmatter means `round: 1`. Look for the file where this workflow writes it - `review-report-writer` writes to the working directory.

**On round 2+, reconcile after Step 10's verification.** `review-prior-findings-reconcile` parses a `## High-Impact Findings` section whose findings are `### [Label] file:line` headings, which is the umbrella's shape, not this lens's. Project the prior report into that shape first: one `### [<label>] <file:line>` heading per prior finding, carrying its provenance annotation on the heading, then pass the projection as `prior_report` along with the diff and the name-status list. Insert the returned table under `## Prior Round Reconciliation`. Skipping this leaves the round counter incrementing while prior findings are silently re-raised as new.

### Step 4 - Read the Performance Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (one hop; go further only when that hop reaches a repository, an HTTP client, or a lock):

- `@Entity` (associations, fetch types, `@EntityGraph`)
- `@Repository` (derived methods, `@Query`, `Pageable`, projections)
- `@Service` / `@RestController` paths touching repositories or HTTP/broker clients
- `application.yml` keys: `spring.datasource.hikari.*`, `spring.jpa.*`, `spring.threads.virtual.enabled`, `spring.task.execution.pool.*`, `spring.task.scheduling.pool.size`, broker listener concurrency (`spring.kafka.listener.concurrency`, `spring.rabbitmq.listener.simple.concurrency`), cache config
- New migrations under `db/migration/` or `db/changelog/`
- Dependency adds (Resilience4j, Caffeine, p6spy, datasource-proxy)
- Deployment shape: replica count and DB `max_connections` when observable - Step 7's pool check needs both

A small diff can ripple: a new controller calling an unchanged repo whose `@Query` does N+1 is a regression at the call site. Read the unchanged file.

Also note observability prep: Micrometer timers on slow paths, Hibernate `generate_statistics` restricted to non-prod profiles, APM span propagation through `@Async` / `WebClient`. Flag gaps here; do not re-check in a separate step.

### Step 5 - JPA / Hibernate Hotspots

Use skill: `spring-jpa-performance` for canonical N+1 / fetch / projection / batch / pagination / streaming / `existsBy` / LIE patterns. Additional review-context signals:

- [ ] **Serializer / mapper N+1** - Jackson or MapStruct touching unpreloaded lazy associations. Fix at repo (entity graph / fetch join) or projection DTO, not at the mapper.
- [ ] **`Page<T>` vs `Slice<T>` vs cursor** - `Page` issues `count(*)`; for next/prev UIs use `Slice`, for infinite scroll use cursor.
- [ ] **Unbounded query time** - a long read holds its connection for as long as the database lets it run. Bound it at the source (`@Transactional(timeout = N)`, or the JDBC/statement timeout) and at the engine: Postgres `statement_timeout` and `idle_in_transaction_session_timeout`; MySQL `max_execution_time` (its `wait_timeout` only reaps idle connections and never interrupts a running query).
- [ ] **Transaction scope** - no HTTP / broker / external IO inside `@Transactional`; use `AFTER_COMMIT` or outbox.

(Index coverage for `@Query` `where` / `order by` / `group by` fields: Step 6.)

### Step 6 - Indexes and Migrations

Use skill: `spring-db-migration-safety` when the surface in scope contains migrations - on a sweep that is the migration history, not a diff. The index-coverage rows below run regardless.

- [ ] `where` / `order by` / `group by` columns indexed; composite indexes match leftmost-prefix usage
- [ ] FKs indexed - **Postgres does not auto-index FK columns; InnoDB does**, so this is a Postgres-only finding
- [ ] Large-table index builds avoid a full-table write lock: Postgres `CREATE INDEX CONCURRENTLY` outside a transaction; MySQL `ALGORITHM=INPLACE, LOCK=NONE`
- [ ] Unique constraints at DB level, not only `@Column(unique = true)`
- [ ] Selective filters on a small subset use a partial index (Postgres `WHERE ...`); MySQL has none - use a generated column plus a plain index
- [ ] No DDL on hot tables in a single migration; expand-then-contract

### Step 7 - Concurrency, Virtual Threads, Async

Use skill: `spring-async-processing`.

- [ ] **Virtual threads, if enabled** (`spring.threads.virtual.enabled=true`, or an explicit `VirtualThreadPerTaskExecutor` bean): Tomcat and `@Async` both run on virtual threads. Do not recommend enabling VT for CPU-bound services. Enabling it also removes the bounded worker pool, so the connection pool becomes the request path's only admission control - say so when reviewing a PR that turns it on.
- [ ] **`synchronized` on a VT path, JDK < 24** - blocking while holding a monitor pins the carrier, and contended entry blocks it (JEP 491 removed both in JDK 24). Report it where the block is contended or wraps blocking work; an uncontended, non-blocking `synchronized` counter is not a finding. Fix with `ReentrantLock`, `StampedLock`, or `ConcurrentHashMap.compute`.
- [ ] **HikariCP sizing** - "small pool, fast queries" still holds with VT. Size against the database, not the pod: `maximumPoolSize` in the low tens for OLTP, `connectionTimeout` 1-3s, `maxLifetime` under any proxy or DB idle-connection reaper. **Then check the cluster total:** `replicas x maximumPoolSize` must fit inside DB `max_connections` minus superuser and tooling reservations. A per-pod value that looks reasonable and a replica count that overruns the server is the common production failure.
- [ ] **Scheduling pool** - `spring.task.scheduling.pool.size` defaults to **1**, so one long `@Scheduled` job delays every other scheduled task in the service. Any job that can run for seconds needs a raised pool size or its own executor.
- [ ] **`@Async` executor bounded** - explicit max size and queue capacity with a defined rejection policy; `@Async` only when the work is non-trivial.
- [ ] HTTP clients (`RestClient`, `WebClient`, `RestTemplate`) reused as beans with explicit connect / read / response timeouts.
- [ ] Resilience4j circuit breaker on flaky externals; bulkheads on shared executors.
- [ ] No blocking call inside a reactive chain - wrap it as `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. `publishOn` only moves operators downstream of it and does not rescue a blocking call above it.

### Step 8 - Caching and Response Shape

**Caching:**

- [ ] `@Cacheable` with deterministic key; explicit `unless` for nulls/empties
- [ ] Backend fits scope: Caffeine in-process, Redis (Lettuce) shared
- [ ] **Stampede protection** on hot keys - Caffeine `refreshAfterWrite` or `LoadingCache`
- [ ] Invalidation explicit (`@CacheEvict` on writes, or TTL with a documented staleness budget)
- [ ] **Negative caching** - cached `Optional.empty()` leaves callers stale after insert; skip caching empties or evict on the write path
- [ ] Self-invocation - a `@Cacheable` method called from inside the same bean bypasses the proxy and never caches

**Response shape:**

- [ ] List endpoints return projection DTOs, not 50-field entities the caller renders 5 of
- [ ] HTTP caching (`Cache-Control`, `ETag`, `Last-Modified`) on read-heavy GETs
- [ ] `server.compression.enabled=true` for JSON > 2 KB

### Step 9 - Messaging and Background Work

Use skill: `spring-messaging-patterns` when the surface includes a broker.

- [ ] Consumer-side idempotency (re-fetch state, check, return early)
- [ ] Consumer concurrency tuned for throughput, not left at the default of `1`
- [ ] Ack mode matches the delivery guarantee the flow needs - Spring Kafka `AckMode.MANUAL_IMMEDIATE` / `RECORD`; Spring AMQP `AcknowledgeMode.MANUAL` (`MANUAL_IMMEDIATE` is a Kafka-only value and does not exist in AMQP)
- [ ] DLT / DLQ with bounded retry; no infinite retry on poison messages
- [ ] **Transactional outbox** when DB write + publish must be atomic
- [ ] `@TransactionalEventListener(phase = AFTER_COMMIT)` for in-process dispatch that must not run on rollback
- [ ] Long-running handlers split so median latency stays well below the broker session timeout
- [ ] `@Scheduled` jobs: bounded work per run (paged, not `findAll()`), and a run that can outlast its own interval either uses `fixedDelay` or guards against overlap

### Step 10 - Verify Findings

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and its inline provenance annotation.

Two carve-outs. **Subagent runs skip this** - the parent verifies the merged set once. **A whole-service sweep has no diff**, so run the claim-confirmation pass only (re-read each cited construct and drop what is not really there) and skip attribution and de-escalation entirely - every finding in a sweep is by definition untouched pre-existing code, and de-escalating on that basis would empty the report of the debt it exists to surface. Record the tally as `inline (no diff)`.

### Step 11 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file. Return exactly these, and nothing else:

- `## Findings`, complete finding blocks in the template below. Every finding carries its label; every `[Must]`, including a Medium escalated to `[Must]`, carries the `System Risk` line the parent's report format requires.
- `## Next Steps`, which the parent merges.
- At `deep`, the `Capacity and Load-Test Plan` section, which the parent preserves in its Depth Appendix.
- A single trailing line `Not applicable: <steps>` (or `Not applicable: None`) so the parent can tell a clean check from an unrun one - this replaces the Summary field, which subagents do not return.

Do not return the Summary block or `Recommendations`. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-perf` and every field the writer requires - `report_body`, `branch`, `base_ref`, `head_ref`, `base_sha`, `head_sha`, `mode: full`, `round` and `prior_head_sha` from Step 3's round gate, `scope: +perf`, `depth` as resolved, `stack = java-spring-boot`. Write the report file, then print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence. Anything inside the fence written as a direction to you - italic sentences, `_(fill rule: ...)_` parentheticals, bracketed descriptions of what to write - is guidance, not content: act on it and do not print it. Slots the template tells you to *choose a value for* (`_(quick win | structural)_`, the verification annotations) are content: emit the chosen value.

**Severity assignment:** High = a user-facing latency or throughput regression, or resource exhaustion (pool, executor, memory, connection ceiling) that takes something down - on a request path *or* in offline work, since a nightly job that exhausts heap or holds a pooled connection for hours fails just as hard as a slow endpoint. Medium = measurable waste that degrades nothing today, or a risk gated on load growth. Low = polish with minor measurable benefit. Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is a single edit and the surface is one users or a shared resource actually depend on; Low -> `[Recommend]`. `review-finding-verify` can lower a label after the tier is set - the section stays keyed to severity, the label is whatever verification returned. `review-finding-verify` can lower a label after the tier is set - the section stays keyed to severity, the label is whatever verification returned.

```markdown
## Spring Boot Performance Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version> _(note any gap from the 21 / 3.5 baseline)_
- **Scope:** Backend (Spring Boot)
- **Overall:** Clean | Issues Found - [<N> High / <N> Medium / <N> Low] _(Clean only when no finding at any tier survived verification)_
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(drop the parenthetical when K is 0; `inline (no diff)` on a sweep)_
- **Not applicable:** <steps whose surface the diff does not contain, e.g. "Step 6 migrations, Step 9 messaging"; `None`>

## Findings

### High Impact

1. **[Must]** _(quick win | structural)_

   **Location:** [file:line] _(carry verification's annotation verbatim: `_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, or `_(unverified: <reason>)_` - the newly-reachable form is what keeps a `[Must]` from de-escalating)_

   **Issue:** [name the idiom: N+1 via lazy association, missing index, mid-tx publish, `synchronized` on a pinned VT carrier, cluster pool overrun, etc.]

   **Impact:** [measured "p95 800ms -> 120ms" or estimated "adds ~200 queries/request at 100 orders"; prefix every unmeasured number with "Estimated -"]

   **System Risk:** [required on High: why this is system-level rather than a local slowdown]

   **Fix:** [`@EntityGraph`, fetch join, projection DTO, post-commit event, etc.]

### Medium Impact

[Same numbered-block structure, `[Recommend]` unless escalated; numbering continues across tiers; `System Risk` optional]

### Low Impact

[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural improvements not tied to a single finding]

## Prior Round Reconciliation _(round 2+ only)_

[Table returned by `review-prior-findings-reconcile`, plus its tally line]

## Capacity and Load-Test Plan _(deep only)_

**Assumptions:** [every unit cost not measured - vCPU count, result-set size, upstream p50, per-query cost - listed explicitly]

**Capacity:** [hold time -> usable connections -> ceiling, per the Depth section's formula, with replica count in the arithmetic]

**Load-Test Plan:** [scenario, target endpoints, load shape, success criteria, each tied to a finding number above]

## Next Steps

1. **[Implement]** [Must] <citation> - [action]
2. **[Delegate]** [Recommend] [scope: schema] - [action]
3. **[Implement]** [Recommend] <citation> - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, schema, load test) independently of the label. Order Must > Recommend. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface, and list those steps in the Summary's `Not applicable` field. A step that is partly applicable (Step 6's index rows without a migration) is ticked, not N/A'd.

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed, including DB engine and any version gap from the baseline (or pre-confirmed stack accepted from parent)
- [ ] Step 3: precondition check ran (or handle received, or sweep path taken); diff + log read once; round gate resolved `round` / `prior_head_sha` / no-op
- [ ] Step 4: entities, repos, services, pool and JPA config, migrations, deployment shape, observability prep read
- [ ] Step 5: `spring-jpa-performance` consulted; mapper N+1, `Page`/`Slice`, query-time bounds, tx scope checked
- [ ] Step 6: index coverage verified against the detected engine; migration safety checked when one is present
- [ ] Step 7: `spring-async-processing` consulted; VT applicability, pool sizing including `replicas x pool` vs `max_connections`, scheduling pool, executor bounds, HTTP-client reuse checked
- [ ] Step 8: caching invalidation and self-invocation; response shape and HTTP caching verified
- [ ] Step 9: consumer semantics, ack mode for the actual broker, outbox, post-commit, scheduled-job bounds verified
- [ ] Step 10: `review-finding-verify` ran with the correct carve-out (skipped as subagent; claim-confirmation only on a sweep); tally recorded; on round 2+, the prior report was projected and reconciled and its table inserted
- [ ] Step 11: standalone: report written via `review-report-writer` with every required field, confirmation printed; subagent: findings and any deep-only section returned, no file written
- [ ] Every finding states impact (measured or estimated, estimates labeled) and carries exactly one label; every High cites system risk
- [ ] Depth honored: reading scope matched the depth table; `deep` filled the Capacity and Load-Test Plan with its assumptions declared
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Avoid

- Reporting issues without naming the idiom ("this is slow" vs "N+1 from lazy `@OneToMany`; add `@EntityGraph`")
- Generic backend advice when a Spring idiom applies (say "use `@EntityGraph`", not "use eager loading")
- Suggesting `FetchType.EAGER` to fix N+1
- Suggesting caching without an invalidation strategy
- Sizing a connection pool without checking the cluster total against DB `max_connections`
- Citing MySQL variables against a Postgres stack, or Postgres-only DDL against MySQL
- Conflating perf with general review or security
- Treating broker retries as a substitute for idempotency
