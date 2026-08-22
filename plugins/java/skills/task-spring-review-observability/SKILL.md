---
name: task-spring-review-observability
description: "Spring Boot observability review: Logback JSON, MDC, Actuator, Micrometer, Micrometer Tracing/OTel, listener instrumentation, error trackers."
agent: java-observability-engineer
metadata:
  category: backend
  tags: [java, spring-boot, observability, logging, metrics, tracing, actuator, micrometer, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Observability Review

Spring-aware observability review at the library / starter level: Logback JSON, Boot structured logging, MDC, Actuator, Micrometer, Micrometer Tracing / OTel, listener interceptors, error-tracker starters. Infra concerns (Datadog dashboards, Sentry org settings, log forwarder config) stay out of scope.

Stack-specific delegate of `task-code-review-observability` for Java / Spring Boot.

## When to Use

- Spring Boot PR with observability regressions or new instrumentation gaps
- Pre-release observability check for a new service / major feature
- Post-incident review when diagnosis was slow or evidence was missing
- Adopting Micrometer Tracing / OTel / structured logging
- Auditing async / messaging tracing and MDC correlation

**Not for:**
- General Spring review (`task-spring-review`)
- Perf with known bottleneck (`task-spring-review-perf`)
- Infra observability (Datadog dashboards, Grafana panels, alert rules) - not in source code

## Depth Levels

| Depth      | When                                                          | Reading scope                                                        | Adds                    |
| ---------- | ------------------------------------------------------------- | -------------------------------------------------------------------- | ----------------------- |
| `standard` | Default                                                       | The always-read config in Step 4, plus changed files                 | -                       |
| `deep`     | Post-incident, pre-release of a critical service, or any whole-service audit | The above, plus every instrumented class repo-wide | Step 11 (SLI/SLO)       |

`deep` needs no flag when the invocation itself is a post-incident or pre-release request; take the user's stated reason as the trigger and record which one fired in Summary Notes. The whole-service audit path is `deep` by nature. On a branch review with no stated reason, run `standard` and say so.

## Invocation

| Invocation                                   | Meaning                                                       |
| -------------------------------------------- | ------------------------------------------------------------- |
| `/task-spring-review-observability`          | Current branch vs base; on trunk, routes to the audit path    |
| `/task-spring-review-observability <branch>` | `<branch>` vs base (3-dot diff)                               |
| `/task-spring-review-observability pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)         |

**Whole-service audit** (post-incident or pre-release with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run every remaining step, Step 4 onward, against the full instrumentation surface at `HEAD`. Findings cite current code. `branch` = the current branch name, `base_ref` = `head_ref` = `HEAD`, and `base_sha` = `head_sha` = `git rev-parse HEAD` (a resolved SHA, not the literal string).

When invoked as a subagent, the parent passes the precondition handle + pre-read diff and commit log; Step 3 is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a Spring-aware parent. Record the Boot version and the deployment platform - several rows below turn on both. If not Spring Boot, stop and tell the user to invoke `/task-code-review-observability`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with parent-supplied artifacts. On fail-fast on trunk, switch to the whole-service audit path; on any other fail-fast, surface the message verbatim and stop. No state-changing git.

**Round gate (standalone only).** Look for `review-observability-<branch>.md`, applying `review-report-writer`'s filename sanitization to `<branch>`; `review-precondition-check` keys prior checkpoints to `review-<branch>.md`, a different report, so its lookup never finds this one. Exists with valid frontmatter, `head_sha` equal to the current head, and a `depth` not below the one requested -> print `No new commits since prior observability review at <sha_short>.` and stop. Otherwise `round = prior.round + 1`, `prior_head_sha = prior.head_sha`; missing or invalid frontmatter means `round: 1`.

**On round 2+, reconcile after Step 12's verification.** `review-prior-findings-reconcile` parses a `## High-Impact Findings` section whose findings are `### [Label] file:line` headings, which is not this lens's shape. Project the prior report into it first - one `### [<label>] <file:line>` heading per prior finding, carrying its annotation - then pass the projection as `prior_report` with the diff and name-status list, or with `head_files` alone on the audit path where neither exists. Insert the returned table under `## Prior Round Reconciliation`. Skipping this advances the round counter while fixed findings are re-raised as new.

### Step 4 - Read the Instrumentation Surface

**Always read in full, at any depth** - these four files decide most findings, and a missing wire in them is itself the finding:

- `logback-spring.xml` (+ per-profile) - encoder type, MDC patterns, masking, timestamp format
- `application.yml` (+ per-profile) - `management.*`, `logging.*`, `management.tracing.*`, listener observation flags for the broker actually in use (`spring.kafka.listener.observation-enabled`, `spring.kafka.template.observation-enabled`, `spring.rabbitmq.listener.simple.observation-enabled` / `...listener.direct.observation-enabled`, `spring.rabbitmq.template.observation-enabled`)
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-actuator`, a metrics registry, tracing bridges, error-tracker starters
- Any `@Configuration` registering a `MeterRegistry`, `TaskDecorator`, `MeterFilter`, or MDC filter

Then the code: changed files using `MeterRegistry`, `Counter`, `Timer`, `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@Async`, `@Scheduled`, or `MDC`. At `deep` this widens to every such class repo-wide, prioritized by incident path (request entry, money, external calls) - state in the Summary's `Coverage` field what you read and what you did not.

A row you could not evaluate because its code was out of reading scope is reported as `Not evaluated`, never as a pass.

### Step 5 - Structured Logging

- [ ] **JSON in prod** - on Boot 3.4+, `logging.structured.format.console: ecs|logstash|gelf` needs no dependency and no `logback-spring.xml` change; `LogstashEncoder` or Logback `JsonEncoder` are the pre-3.4 routes. No raw text logs in prod paths
- [ ] **Timestamps complete** - full date and offset (`ISO8601` / `%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}`), never time-only. A time-only pattern makes an overnight or multi-hour incident unreconstructable
- [ ] **MDC correlation** - `traceId`, `spanId`, `requestId`, plus business IDs (`orderId`, `tenantId`, `userId` when authenticated) put in a request-boundary filter and cleared in `finally`. Non-JSON patterns include `%X{traceId}` / `%X{spanId}`. `LogstashEncoder` emits the whole MDC by default; `<includeMdcKeyName>` is an allowlist that *narrows* it, so removing those entries widens output rather than dropping correlation
- [ ] **Sensitive-field masking** - encoder masks `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`; personal data (email, phone, address, government id) is not logged in the clear either; DTOs use `@JsonIgnore` on the same fields so `log.info("payload={}", dto)` cannot leak via Jackson
- [ ] **Responsible payloads** - no JPA-entity serialization in log args (lazy-load + PII); no HTTP body logging on prod profiles
- [ ] **Levels and form** - `error` actionable, `warn` recoverable, `info` state transitions, `debug` verbose; parameterized only, no string concat or `String.format`; hot loops use `log.atDebug()` or sampling
- [ ] **Exceptions logged whole** - pass the `Throwable` as the last argument. `log.warn(e.getMessage())` discards the stack *and* puts an attacker- or data-controlled string into the log line, which a plain-text pattern lets carry newlines and forge entries; `log.info("...", e)` keeps the stack but hides the event from `level:ERROR` alerting and error-tracker capture
- [ ] **Logger levels are profile-scoped** - a framework logger turned up in `logback-spring.xml` or `logging.level.*` without a `<springProfile>` or per-profile guard follows the build into prod. `org.hibernate.SQL` at DEBUG logs every statement; request/response loggers at DEBUG log bodies
- [ ] **Async appenders** for high volume with an explicit queue-full policy

### Step 6 - Spring Boot Actuator

- [ ] **`spring-boot-starter-actuator`** present (flag if absent in a service that warrants observability)
- [ ] **Exposure minimal in prod** - typically `health, info, metrics, prometheus`. Never `*` in prod. `heapdump` and `threaddump` never web-exposed
- [ ] **Sensitive endpoints gated** - `env`, `configprops`, `mappings`, `loggers` require auth via `management.endpoint.<name>.access` or a dedicated `SecurityFilterChain` for `/actuator/**`. Exposure and gating are one finding per endpoint, not two - and a wildcard `include: "*"` is one finding about the wildcard, not one per endpoint it exposes
- [ ] **Health depth** - `show-details` at `never` (the default) or `when-authorized`; `always` is the finding, an unset key is not
- [ ] **Liveness vs readiness probes** - Boot auto-enables the probe groups only when it detects Kubernetes, so `management.endpoint.health.probes.enabled: true` is required off-K8s and redundant on it. Liveness depends on JVM/app only; readiness reflects ability to serve. Whatever polls the service must target `/actuator/health/readiness`, not aggregate `/actuator/health` - one dependency blip on the aggregate endpoint pulls every instance out of rotation at once
- [ ] **Readiness composition** - the readiness group includes only dependencies the service genuinely cannot serve without. An indicator for an optional dependency added to that group drags the whole fleet unready when that dependency degrades; a Resilience4j breaker is a common case, though it contributes only where `registerHealthIndicator` was turned on per instance
- [ ] **`info` endpoint** - build + git enabled, no env-var or secret leakage
- [ ] **`management.server.port`** isolated from the main port when prod network policy requires it

### Step 7 - Micrometer Metrics

- [ ] **Registry present** - `micrometer-registry-prometheus` (or equivalent) with an export path; the Actuator-default `SimpleMeterRegistry` stores in memory and exports nothing, so a service with only that has no metrics at all
- [ ] **Auto-instrumentation enabled** - `http.server.requests`, `hikaricp.*`, `hibernate.*` (`generate_statistics=true` non-prod), `jvm.*`, `tomcat.*`; Spring Kafka and Spring AMQP register listener and template timers by default, so per-topic timing usually needs configuration, not new code
- [ ] **Custom metrics namespaced** - `acme.orders.placed`; `Counter` counts, `Timer` durations, `Gauge` instantaneous, `DistributionSummary` histograms
- [ ] **Tag cardinality bounded.** Reject:
  - **Unbounded identifiers** - `userId`, `orderId`, `paymentId`, `requestId`, `traceId` (belong on traces / logs). Each distinct value creates a meter the registry never evicts - this, not the call site, is what leaks memory
  - **Continuous numerics** - `amount`, `latency_ms`, `payload_size` (use `DistributionSummary`)
  - **Free text** - error messages, raw paths with embedded IDs (normalize `/orders/42` to `/orders/{id}`)
  Allowed: bounded enums (`status`, `tenant_tier`, `region`, `error_code`)
- [ ] **`http.server.requests` URI templating** - tag is the route template, not the resolved path
- [ ] **Meters resolved once per call site** - `register()` is get-or-create keyed on name plus tags, so a per-call rebuild wastes allocation rather than duplicating meters; hold the `Counter` / `Timer` in a field. Report it as waste at `Low`, and route the memory harm to the cardinality row when a tag is unbounded
- [ ] **Timers measure the right span** - the test is whether the timed call returns before the work finishes, not what type it returns. `timer.record(() -> client.sendAsync(...))` stops the clock at submission; a `record` whose lambda blocks and then wraps the result in a completed future is correct. Where the work outlives the call, stop a `Timer.Sample` in the completion callback
- [ ] **`MeterFilter`** trims unused / high-cardinality series

### Step 8 - Distributed Tracing

- [ ] **Exactly one tracing bridge, and at least one** - `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp`, or `micrometer-tracing-bridge-brave` for Zipkin. **None** means no distributed trace exists at all, which is a High gap in any service that calls another; **both** is a finding rather than a redundancy, since competing `Tracer` and propagator beans make B3 and W3C `traceparent` disagree at every hop and traces sever silently. Boot 2.x Sleuth flagged for migration
- [ ] **Sampling explicit per env** - `management.tracing.sampling.probability` defaults to `0.1`, dropping 90% of traces; `1.0` in prod is a cost and cardinality problem. Set it per profile, and check that a value set once in the default profile is actually overridden where it needs to differ
- [ ] **`Observation` API** for custom spans over manual span management
- [ ] **`traceparent` propagation** - `RestClient` / `WebClient` / Feign auto-instrumented; manual `OkHttpClient` / `HttpClient` flagged for missing interceptor
- [ ] **Cross-thread continuity** - trace context survives `@Async`, executor, and virtual-thread hops. A raw `new Thread()` or a hand-rolled `ExecutorService` bypasses `@Async` decoration entirely and is this row's finding; a missing `TaskDecorator` on the `@Async` executor is Step 9's row, reported once there
- [ ] **DB span enrichment** non-prod via `p6spy` / `datasource-proxy`
- [ ] **Not over-granular** - no `Observation` around a method whose only work is a JDBC call already spanned

### Step 9 - Async / Messaging Observability

- [ ] **Broker observation on both sides** - a consumer flag alone creates a consumer span but cannot join a context the producer never wrote. Enable the listener *and* template flags for the broker in use; when the producer is external, say so and scope the finding to the consumer span and its timer
- [ ] **Consumer MDC propagation** - filter / aspect copies `traceId`, `userId`, `tenantId` from message headers and clears in `finally`
- [ ] **Listener metrics** - per-topic handle latency, retry and DLT counters, queue / partition lag exposed
- [ ] **`@Async` decoration** - `ContextPropagatingTaskDecorator` propagates only values with a registered `ThreadLocalAccessor`; observation context qualifies, so `traceId`/`spanId` reappear in the MDC. It does **not** carry `SecurityContext` (wrap the executor in `DelegatingSecurityContextAsyncTaskExecutor`) or arbitrary MDC keys a request filter set, so custom keys like `requestId` still vanish unless an accessor is registered
- [ ] **Async failures surface** - an `@Async` method returning `void` routes exceptions to `AsyncUncaughtExceptionHandler`, so one must be configured; a method returning a `Future` whose caller discards it swallows the exception entirely - no log, no metric, no error event
- [ ] **`@Scheduled` instrumentation** - per-job `Observation` and duration timer; failures logged at `error`; missed or overrunning executions alertable

### Step 10 - Error Tracking

Skip the rows below when no tracker is wired, and say so once: a service with no error tracker is a `Recommend`-level gap, not eight findings. The `@RestControllerAdvice` row is the exception - it holds whether or not a tracker exists, since an advice that discards the exception loses it from the logs too.

- [ ] **Boot starter wired** - `sentry-spring-boot-starter-jakarta`, `honeybadger`, or `rollbar-spring-boot-starter`
- [ ] **Config externalized** - a Sentry DSN is a write-only ingest key, not a credential; committing it risks quota abuse and cross-environment event mixing rather than exfiltration. Report it accurately and keep genuine API keys in env or Vault
- [ ] **Release / env tags** from build metadata
- [ ] **PII off in prod** - `sentry.send-default-pii: false`; explicit breadcrumb allowlist
- [ ] **MDC forwarded** - error event includes `traceId`, `userId`, `tenantId`
- [ ] **Sample rate explicit per env** - `sentry.traces-sample-rate`, `profiles-sample-rate`; not `1.0` in prod
- [ ] **Ignored exceptions documented** - each ignored type has a stated reason
- [ ] **`@RestControllerAdvice`** captures the original exception before mapping it to a response DTO

### Step 11 - Health Checks and SLIs (`deep` only)

- [ ] Critical user journeys have a Micrometer SLI (`http.server.requests` filtered to the journey URI: success rate, p95)
- [ ] DB / cache / broker / external APIs covered by a `HealthIndicator`. Boot auto-configures `db`, `redis`, `rabbit`, `mongo` and others but ships **none for `spring-kafka`** - a Kafka dependency needs a custom indicator
- [ ] SLO targets live in code (config or constants), not a free-floating page
- [ ] Synthetic probes call `/actuator/health/readiness`, not `/actuator/health`

### Step 12 - Verify Findings

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and inline provenance annotation.

Runs at every depth. Three carve-outs: **subagent runs skip it** - the parent verifies the merged set once; a **whole-service audit has no diff**, so run the claim-confirmation pass only, skip attribution and de-escalation, and record the tally as `inline (no diff)`; and **a missing-wire finding does not de-escalate for being untouched**. This lens's central findings - an absent observation flag, an absent probe property, an unregistered indicator - are absences with no line in the diff to attribute. Verify their claim, keep their severity, and annotate them `_(pre-existing)_` so the reader knows the PR did not introduce them.

### Step 13 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file. Return exactly these, and nothing else:

- `## Findings`, complete finding blocks. Every finding carries its label and citation; every `[Must]`, including a Medium escalated to `[Must]`, carries the `System Risk` line the parent's report format requires. A finding about a surface the diff did not touch is marked `_(pre-existing)_` on its Location line so the parent's verify pass can attribute it.
- `## Next Steps`, which the parent merges, prerequisites first.
- One trailing line `Coverage: <what you read>; not evaluated: <rows>; <one-line notes>` - this carries the disclosures the Summary would otherwise hold, since subagents do not return a Summary.

Do not return the Summary block or `Recommendations`. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-observability` and every field the writer requires - `report_body`, `branch`, `base_ref`, `head_ref`, `base_sha`, `head_sha`, `mode: full`, `round` and `prior_head_sha` from Step 3's round gate, `scope: +obs`, `depth`, `stack = java-spring-boot`. Write the file before ending; print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence. Anything inside the fence written as a direction to you - italic sentences, fill-rule parentheticals, bracketed descriptions of what to write - is guidance, not content: act on it and do not print it. Slots the template tells you to *choose a value for*, such as the verification annotations, are content: emit the chosen value.

**Severity assignment:** High = the gap blocks incident diagnosis or exposes data (no exported metrics at all, no tracing bridge at all in a service that calls others, unstructured or timestamp-less logs on an incident path, lost trace/MDC context across a hop, swallowed async failures, PII in logs, unsecured Actuator, severed traces from competing bridges). Medium = diagnosis possible but degraded or costly (missing metrics on key flows, unbounded tag cardinality, sampling wrong for the environment). Low = polish (naming, levels, encoder tuning, per-call meter rebuilds). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` only when the gap sits on the path of an incident the service has actually had or is being reviewed for; Low -> `[Recommend]`. A one-line fix does not by itself escalate - almost every fix in this lens is one line.

```markdown
## Spring Boot Observability Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version>
- **Logging:** Boot structured logging (`logging.structured.format`) | Logback + Logstash JSON | Logback JsonEncoder | log4j2 | plain-text pattern (unstructured) | other
- **Metrics:** Micrometer + Prometheus | Micrometer + StatsD | Micrometer via Actuator - no export registry | none | not determinable from what was read
- **Tracing:** Micrometer Tracing (OTel) | Micrometer Tracing (Brave/Zipkin) | multiple bridges - conflicting | Sleuth (deprecated) | none
- **Error Tracker:** Sentry | Honeybadger | Rollbar | none
- **Coverage:** <what was read; on a diff review, the always-read config plus the changed files; at deep, which classes were and were not read>
- **Overall:** Adequate | Gaps Found - [<N> High / <N> Medium / <N> Low]
- **Round:** <N> _(from round 2 onward)_
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(drop the parenthetical when K is 0. On an audit, attribution did not run: write `<N> confirmed, <K> dropped - inline (no diff)`.)_
- **Notes:** <the depth trigger that fired; which step's rows went `Not evaluated` and why, named by step rather than row when more than three; `None`>

## Findings

### High Impact

1. **[Must]**

   **Location:** [file:line or config key] _(append `_(pre-existing)_` or `_(unverified: ...)_` when verification returned one)_

   **Issue:** [name the idiom: missing MDC propagation across `@Async`, unbounded tag cardinality on `userId`, Actuator `*` exposure, two tracing bridges, etc.]

   **Impact:** [diagnosability / alertability / cost]

   **System Risk:** [required on High: what an incident looks like with this gap in place]

   **Fix:** [specific Spring / Micrometer / Logback change with code or YAML]

### Medium Impact

[Same numbered-block structure, `[Recommend]` unless escalated; numbering continues across tiers; `System Risk` optional]

### Low Impact

[Same numbered-block structure]

_Omit empty sections._

## Recommendations

Open with the dependency order: which findings are prerequisites for the rest, so a service with broad gaps gets a sequence rather than an inventory. Then structural improvements not tied to a specific finding.

## Prior Round Reconciliation _(round 2+ only)_

[Table returned by `review-prior-findings-reconcile`, plus its tally line]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting / dashboards / ops). Order Must > Recommend, and within a label put prerequisites before what depends on them. Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed, Boot version and deployment platform recorded (or accepted from parent)
- [ ] Step 3 - precondition check ran, handle received, or audit path taken; diff + commit log read once where one exists; round gate resolved
- [ ] Step 4 - the four always-read config surfaces opened in full before any checklist; unevaluable rows marked `Not evaluated`
- [ ] Step 5 - structured logging: encoder or Boot structured format, timestamps, MDC, masking including personal data, payload discipline, levels, whole-exception logging
- [ ] Step 6 - Actuator: exposure and gating, health depth against the default, probes against the platform, readiness composition, info safe
- [ ] Step 7 - Micrometer: exporting registry, auto-instrumentation, namespacing, tag cardinality, async timing correctness
- [ ] Step 8 - tracing: exactly one bridge, sampling per env, propagation, cross-thread continuity
- [ ] Step 9 - messaging / async: observation on both sides, consumer MDC, listener metrics, decoration limits, async failure surfacing
- [ ] Step 10 - error tracker rows run, or the absence reported once
- [ ] Step 11 - SLI / health indicators reviewed (`deep` only)
- [ ] Step 12 - `review-finding-verify` ran with the correct carve-out; tally in Summary
- [ ] Step 13 - standalone: report written via `review-report-writer` with every required field, confirmation printed; subagent: findings and Next Steps returned, no file written
- [ ] Every finding carries exactly one label; every High cites system risk; Recommendations state dependency order

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git
- "Add observability" without naming the idiom (say "register `Counter` named `acme.orders.placed` with bounded tags")
- Generic advice when a Spring starter or property exists ("set `logging.structured.format.console: ecs`", not "make logs structured")
- Reviewing infra (Datadog, Grafana, log forwarder, on-call) - belongs to ops review
- Reporting a Boot default as a defect (`show-details` unset, probes on Kubernetes, `send-default-pii` unset)
- Treating `userId` / `orderId` / `paymentId` tags as acceptable
- Approving Sleuth on Boot 3 - migrate to Micrometer Tracing
- Emitting a flat inventory of every failed checklist row when a service is broadly uninstrumented - collapse to the prerequisites and sequence them
