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

Spring-aware observability review at the library / starter level: Logback JSON, Boot structured logging, MDC, Actuator, Micrometer, Micrometer Tracing / OTel, listener interceptors, error-tracker starters.

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
- Infra observability (Datadog dashboards, Grafana panels, alert rules, Sentry org settings, log forwarders) - not in source code

## Depth Levels

| Depth      | When                                                          | Reading scope                                                        | Adds                    |
| ---------- | ------------------------------------------------------------- | -------------------------------------------------------------------- | ----------------------- |
| `standard` | Default                                                       | The always-read config in Step 4, plus changed files                 | -                       |
| `deep`     | Post-incident, pre-release of a critical service, or any whole-service audit | The above, plus every instrumented class repo-wide | Step 11 (SLI/SLO)       |

`deep` needs no flag when the request states a post-incident or pre-release reason; record which fired in Notes. A branch review with no stated reason runs `standard` and says so.

## Invocation

| Invocation                                   | Meaning                                                       |
| -------------------------------------------- | ------------------------------------------------------------- |
| `/task-spring-review-observability`          | Current branch vs base; on trunk, routes to the audit path    |
| `/task-spring-review-observability <branch>` | `<branch>` vs base (3-dot diff)                               |
| `/task-spring-review-observability pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)         |
| `/task-spring-review-observability audit`    | Whole-service audit at `HEAD`, from any branch or a detached `HEAD` (an incident tag the user checked out) |
| `/task-spring-review-observability [<target>] deep` | Any row above at `deep` depth                          |

**Whole-service audit** (post-incident or pre-release with no feature branch): entered by the `audit` argument, or when Step 3 fails fast on trunk - do not stop. No handle exists, so assemble the fields: `branch` = `git symbolic-ref -q --short HEAD`, else `git describe --exact-match --tags HEAD`, else `detached-<short sha>`; `base_ref` = `head_ref` = `HEAD`; `base_sha` = `head_sha` = `git rev-parse HEAD`. With the `audit` argument, its dirty-tree check reuses `review-precondition-check` Step 1's filter and stop message. Then run Step 3's round gate and every step from Step 4 against the full instrumentation surface at `HEAD`: findings cite `file:line` at `HEAD`, depth `deep`.

**Subagent mode** (spawned by `task-spring-review`, or run inline by it when it cannot spawn): the parent passes the handle's `base_ref` / `head_ref`, `base_sha` / `head_sha`, the diff and commit log already read, `depth`, the stack (with Boot/Java versions and database engine), `round`, and - on round 2+ - `prior_head_sha` and the prior findings for this scope. Step 3, verification, reconciliation, and the report file are the parent's; never re-raise a prior finding the parent passed unless its cited site changed since `prior_head_sha`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent. If not Spring Boot (standalone only): stop and tell the user to invoke `/task-code-review-observability`; as a subagent, return the mismatch to the parent instead.

Read the Spring Boot version from the build file (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` does not report either. Every construct a finding cites as present and every fix recommends must exist and bind on that version - including fixes taken from a composed atomic. Below Boot 4.0, write the row's or the atomic's Boot 3 form; when it has none, say `Boot 3 form not given` rather than emitting the Boot 4 one.

Record the deployment platform from committed deploy files (`k8s/`, Helm charts, ECS task definitions, `Dockerfile`, `Procfile`) or the project `CLAUDE.md`, and any tracer attached outside the build (an OTel Java agent via `-javaagent` or a declaration in `CLAUDE.md`). Both fill Summary slots; with neither source the platform is `unknown` and the probe rows `Not evaluated`. A `CLAUDE.md` fact the repo contradicts goes in Notes, no finding, and the repo's value fills the slot; a declared agent is the tracer, its missing deploy attachment a Notes line, no finding.

### Step 3 - Resolve the Diff and Round

Skip in subagent mode; the `audit` argument skips only the precondition call - the round gate still runs. Use skill: `review-precondition-check` with the invocation's target argument and `report_type: review-observability`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Fail-fast on trunk -> the whole-service audit only when `git symbolic-ref --short HEAD` equals the named trunk, otherwise print the precondition's trunk message, point at `audit`, and stop; any other fail-fast -> surface the message verbatim and stop. No state-changing git.

**Round gate (standalone), before any surface read.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs. An audit has its SHAs already and reads `review-observability-<branch>.md` (the writer's filename sanitization) directly as its `prior_checkpoint` - `legacy` when the frontmatter is missing, unparseable, or another lens's or branch's. A valid `prior_checkpoint` with the same `head_sha`, the same kind (an audit's `base_sha` equals its `head_sha`; a diff review's does not), and a `depth` not below this run's -> print `No new commits since prior observability review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` -> `round: 1`. Then read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once and reuse (an audit has neither). Read the build and deploy files at `git show <head_ref>:<path>` after the round gate, never from the working tree before it - Step 2's version read included.

### Step 4 - Read the Instrumentation Surface

**Always read in full, at any depth** - these four files decide most findings, and a missing wire in them is itself the finding:

- `logback-spring.xml` (+ per-profile) - encoder type, MDC patterns, masking, timestamp format
- `application.yml` (+ per-profile) - `management.*`, `logging.*`, `management.tracing.*`, listener observation flags for the broker actually in use (`spring.kafka.listener.observation-enabled`, `spring.kafka.template.observation-enabled`, `spring.rabbitmq.listener.simple.observation-enabled` / `...listener.direct.observation-enabled`, `spring.rabbitmq.template.observation-enabled`)
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-actuator`, a metrics registry, tracing bridges, error-tracker starters
- Any `@Configuration` registering a `MeterRegistry`, `TaskDecorator`, `Executor`, `MeterFilter`, or MDC filter, and any `SecurityFilterChain` matching `/actuator/**`

Then the code: changed files using `MeterRegistry`, `Counter`, `Timer`, `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@Async`, `@Scheduled`, `MDC`, or an HTTP client (`RestClient`, `WebClient`, `RestTemplate`, `HttpClient`, `@FeignClient`). At `deep` this widens to every such class repo-wide, prioritized by incident path (request entry, money, external calls) - state in the Summary's `Coverage` field what you read and what you did not.

**Inert on the declared version** - a bare `micrometer-tracing-bridge-*` jar on Boot 4 (no tracing auto-configuration without `spring-boot-starter-opentelemetry`, `spring-boot-starter-zipkin`, or a `spring-boot-micrometer-tracing-*` module); `management.tracing.enabled` on Boot 4 (binds nothing - `management.tracing.export.enabled`); `logging.structured.*` below Boot 3.4; `spring.task.execution.propagate-context` below Boot 4.1. A finding whose impact or fix assumes the inert construct works is wrong.

Every row ends as a finding, a pass, or `Not evaluated - <reason>` in Notes (code out of reading scope, platform unknown). When a step's prerequisite is absent - no exporting registry (Step 7), no tracer (Step 8), no error tracker (Step 10) - the absence is one finding and that step's dependent rows fold into it, said once.

### Step 5 - Structured Logging

- [ ] **JSON in prod** - `logging.structured.format.console: ecs|logstash|gelf` (Boot 3.4+) needs no dependency and no `logback-spring.xml` change; `LogstashEncoder` or Logback `JsonEncoder` are equally valid. No raw text logs in prod paths
- [ ] **Timestamps complete** - full date and offset (`ISO8601` / `%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}`), never time-only. A time-only pattern makes an overnight or multi-hour incident unreconstructable
- [ ] **MDC correlation** - `traceId`, `spanId`, `requestId`, plus business IDs (`orderId`, `tenantId`, `userId` when authenticated) put in a request-boundary filter and cleared in `finally`. Non-JSON patterns include `%X{traceId}` / `%X{spanId}`. `LogstashEncoder` emits the whole MDC by default; `<includeMdcKeyName>` is an allowlist that *narrows* it, so removing those entries widens output rather than dropping correlation
- [ ] **Sensitive-field masking** - encoder masks `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`; a card or account number never shows beyond its last four digits; personal data (email, phone, address, government id) is not logged in the clear either; DTOs use `@JsonIgnore` on the same fields so `log.info("payload={}", dto)` cannot leak via Jackson
- [ ] **Responsible payloads** - no JPA-entity serialization in log args (lazy-load + PII); no HTTP body logging on prod profiles
- [ ] **Levels and form** - `error` actionable (5xx, unexpected), `warn` recoverable, `info` state transitions, `debug` verbose; a handled client error (validation, not found, conflict, business decline) is `warn` or `info` without the stack (`log.warn("... {}", ex.getMessage())`), never ERROR-with-stack. Parameterized only, no string concat or `String.format`; hot loops use `log.atDebug()` or sampling
- [ ] **`@RestControllerAdvice`** - the catch-all handler logs the original `Throwable` at `error` before mapping it to a response DTO, tracker or not; mapped 4xx handlers follow the level rule, so an inconsistent handler set is fixed by demoting the noisy ones, not by adding logging to the quiet ones
- [ ] **Exceptions logged whole** - an `error` log passes the `Throwable` as the last argument. `log.error(e.getMessage())` discards the stack *and* puts an attacker- or data-controlled string into the log line, which a plain-text pattern lets carry newlines and forge entries; `log.info("...", e)` keeps the stack but hides the event from `level:ERROR` alerting and error-tracker capture
- [ ] **Logger levels are profile-scoped** - a framework logger turned up in `logback-spring.xml` or `logging.level.*` without a `<springProfile>` or per-profile guard follows the build into prod. `org.hibernate.SQL` at DEBUG logs every statement; request/response loggers at DEBUG log bodies
- [ ] **Async appenders** for high volume with an explicit queue-full policy

### Step 6 - Spring Boot Actuator

- [ ] **`spring-boot-starter-actuator`** present (flag if absent in a service that warrants observability)
- [ ] **Exposure minimal in prod** - typically `health, info, metrics, prometheus`. Never `*` in prod. `heapdump` and `threaddump` never web-exposed
- [ ] **Sensitive endpoints gated** - `env`, `configprops`, `mappings`, `loggers` sit behind a `SecurityFilterChain` for `/actuator/**`, or are off (`management.endpoint.<id>.access: none` on Boot 3.4+, `...enabled: false` below). `access: read-only` limits operations and authenticates nobody - a `read-only` `env` is still public. Exposure and gating are one finding per endpoint, not two - and a wildcard `include: "*"` is one finding about the wildcard, not one per endpoint it exposes
- [ ] **Health depth** - `show-details` at `never` (the default) or `when-authorized`; `always` is the finding, an unset key is not
- [ ] **Liveness vs readiness probes** - Boot 4 enables the liveness and readiness groups by default (`management.endpoint.health.probes.enabled` defaults to `true`); Boot 3 enabled them only on detected Kubernetes, so a Boot 3 service off-K8s needs the property (platform from Step 2). Liveness depends on JVM/app only; readiness reflects ability to serve. Whatever polls the service must target `/actuator/health/readiness`, not aggregate `/actuator/health` - one dependency blip on the aggregate endpoint pulls every instance out of rotation at once
- [ ] **Readiness composition** - the readiness group includes only dependencies the service genuinely cannot serve without. An indicator for an optional dependency added to that group drags the whole fleet unready when that dependency degrades; a Resilience4j breaker is a common case, though it contributes only with `management.health.circuitbreakers.enabled: true` (default `false`) and `registerHealthIndicator` per instance
- [ ] **`info` endpoint** - build + git enabled, no env-var or secret leakage
- [ ] **`management.server.port`** isolated from the main port when prod network policy requires it

### Step 7 - Micrometer Metrics

- [ ] **Registry present** - `micrometer-registry-prometheus`, `micrometer-registry-otlp` (inside Boot 4's `spring-boot-starter-opentelemetry`), or equivalent, with an export path; the Actuator-default `SimpleMeterRegistry` stores in memory and exports nothing, so a service with only that has no metrics at all
- [ ] **Auto-instrumentation enabled** - `http.server.requests`, `hikaricp.*`, `hibernate.*` (needs `org.hibernate.orm:hibernate-micrometer`, Boot-managed, plus `generate_statistics=true` non-prod), `jvm.*`, `tomcat.*`; Spring Kafka and Spring AMQP register listener and template timers by default, so per-topic timing usually needs configuration, not new code
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

- [ ] **Exactly one tracer, and at least one** - Boot 4: `spring-boot-starter-opentelemetry`, `spring-boot-starter-zipkin` for Brave, or a `spring-boot-micrometer-tracing-*` module with its bridge. Boot 3: `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp`, or `micrometer-tracing-bridge-brave` + `zipkin-reporter-brave`. An OTel Java agent recorded in Step 2 (declared included), or `opentelemetry-spring-boot-starter`, is the tracer too: record it, raise no absence finding, and never recommend a bridge beside it. **None** is a High gap in any service that calls another; **two** (two bridges, or a bridge beside an agent) is a finding, since competing tracers and propagators duplicate spans or make B3 and W3C `traceparent` disagree at every hop. Boot 2.x Sleuth flagged for migration
- [ ] **Sampling explicit per env** - `management.tracing.sampling.probability` defaults to `0.1`, dropping 90% of traces; `1.0` in prod is a cost and cardinality problem. Set it per profile, and check that a value set once in the default profile is actually overridden where it needs to differ
- [ ] **`Observation` API** for custom spans over manual span management
- [ ] **`traceparent` propagation** - only clients built from Boot's injected `RestClient.Builder`, `WebClient.Builder`, or `RestTemplateBuilder` are instrumented. `RestClient.create()`, `RestClient.builder()`, `WebClient.create()`, `new RestTemplate()`, and a manual `OkHttpClient` / `HttpClient` are not; Feign needs `feign-micrometer`
- [ ] **Cross-thread continuity** - trace context survives `@Async`, executor, and virtual-thread hops. A raw `new Thread()` or a hand-rolled `ExecutorService` bypasses `@Async` decoration entirely and is this row's finding; a missing `TaskDecorator` on the `@Async` executor is Step 9's row, reported once there. WebFlux needs `spring.reactor.context-propagation: auto` (Boot 3.2+) for MDC across operators
- [ ] **DB span enrichment** non-prod via `p6spy` / `datasource-proxy`
- [ ] **Not over-granular** - no `Observation` around a method whose only work is a JDBC call already spanned

### Step 9 - Async / Messaging Observability

- [ ] **Broker observation on both sides** - a consumer flag alone creates a consumer span but cannot join a context the producer never wrote. Enable the listener *and* template flags for the broker in use; when the producer is external, say so and scope the finding to the consumer span and its timer
- [ ] **Consumer MDC propagation** - filter / aspect copies `traceId`, `userId`, `tenantId` from message headers and clears in `finally`
- [ ] **Listener metrics** - per-topic handle latency, retry and DLT counters, queue / partition lag exposed
- [ ] **`@Async` decoration** - `ContextPropagatingTaskDecorator` propagates only values with a registered `ThreadLocalAccessor`: observation context (so `traceId`/`spanId` reappear in the MDC) and `SecurityContext` on Spring Security 6.5+ (below, `DelegatingSecurityContextAsyncTaskExecutor`), never MDC keys a request filter set - `requestId` vanishes without its own accessor. Register it with `spring.task.execution.propagate-context=true` (Boot 4.1) or a `ContextPropagatingTaskDecorator` `@Bean` (Boot 3.2+); a `new` executor needs `setTaskDecorator`
- [ ] **Which executor `@Async` runs on** - Any user Executor bean - a ThreadPoolTaskScheduler included - backs off Boot's applicationTaskExecutor unless it is @Bean(defaultCandidate = false) (Boot 3.4+) or spring.task.execution.mode=force (Boot 3.5+). Once it is backed off, with two or more TaskExecutor beans (Boot's @EnableScheduling taskScheduler counts) and none named taskExecutor, unnamed @Async runs on a new SimpleAsyncTaskExecutor - unbounded, one thread per task. spring.task.execution.propagate-context (Boot 4.1) and TaskDecorator beans reach only Boot-built executors. This row reports the lost context; the unbounded executor is perf / reliability's finding. At any depth, grep every unnamed `@Async` site. Fix: an escape hatch above restores Boot's executor, or name one user executor `taskExecutor` with `setTaskDecorator(new ContextPropagatingTaskDecorator())` - the name alone moves the work, not the context
- [ ] **Async failures surface** - an `@Async` method returning `void` routes exceptions to `AsyncUncaughtExceptionHandler`, so one must be configured; a `Future` the caller discards, or a listener `catch` that neither rethrows, counts, nor logs at `error`, swallows the failure - no log, no metric, no retry or DLT
- [ ] **`@Scheduled` instrumentation** - per-job `Observation` and duration timer; failures logged at `error`; missed or overrunning executions alertable

### Step 10 - Error Tracking

No tracker wired is one `[Recommend]` gap (Step 4's absent-prerequisite rule).

- [ ] **Boot integration wired** - Sentry `sentry-spring-boot-4-starter` (Boot 4) / `sentry-spring-boot-starter-jakarta` (Boot 3), Honeybadger `honeybadger-java`, Rollbar `rollbar-spring-boot3-webmvc` (Boot 3; no Boot 4 artifact published)
- [ ] **Config externalized** - a Sentry DSN is a write-only ingest key, not a credential; committing it risks quota abuse and cross-environment event mixing rather than exfiltration; genuine API keys stay in env or Vault
- [ ] **Release / env tags** from build metadata
- [ ] **PII off in prod** - `sentry.send-default-pii: false`; explicit breadcrumb allowlist
- [ ] **MDC forwarded** - error event includes `traceId`, `userId`, `tenantId`
- [ ] **Sample rate explicit per env** - `sentry.traces-sample-rate`, `profiles-sample-rate`; not `1.0` in prod
- [ ] **Ignored exceptions documented** - each ignored type has a stated reason

### Step 11 - Health Checks and SLIs (`deep` only)

- [ ] Critical user journeys have a Micrometer SLI (`http.server.requests` filtered to the journey URI: success rate, p95)
- [ ] DB / cache / broker / external APIs covered by a `HealthIndicator`. Boot auto-configures `db`, `redis`, `rabbit`, `mongo` and others but ships **none for `spring-kafka`** - a Kafka dependency needs a custom indicator
- [ ] SLO targets live in code (config or constants), not a free-floating page
- [ ] Synthetic probes call `/actuator/health/readiness`, not `/actuator/health`

### Step 12 - Verify and Reconcile

Subagent runs skip this step (the parent verifies and reconciles its merged set). Standalone: Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns, with one exception applied after verify (the parent applies it too): a missing-wire finding (only these three kinds: an absent observation flag, probe property, or health indicator) with a `Pre-existing` verdict keeps its drafted label and carries `_(pre-existing)_`, since the diff has no line to attribute it to. An audit has no diff: run the claim-confirmation pass only - no attribution, no de-escalation, no annotation but `_(unverified: <reason>)_` - which still drops a claim that does not hold at `HEAD`.

**Round 2+.** Project every tier of the prior report (the file at the handle's `report_path`; on an audit, the file the round gate read) into reconcile's parse shape: one `## High-Impact Findings` section; per finding a `### [<Label>] <file:line>` heading from the bold label opening its block (a trailing `_(carried from round <N>)_` kept as its own group) and the bare `file:line` prefix of its Location line, a `_(pre-existing)_` annotation kept as its own group (verify's combined `_(pre-existing; newly reachable via ...)_` splits into `_(pre-existing)_ _(newly reachable via ...)_`), and its Issue as the `Issue:` line. A prior finding whose path is absent from the name-status is projected with `_(pre-existing)_`, so an `Unverified` or one-hop finding in an untouched file is never closed as `Addressed` without being read. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D`. An audit, or any round whose prior checkpoint's `base_sha` equals its `head_sha` (an audit or trunk run), builds the comparison table directly - never call reconcile, which would mark every finding in an untouched file `Addressed`. Its rows: re-derived -> `Still open`, site read and smell absent -> `Addressed`, file gone or a `[Praise]` row -> `Obsolete`, site not reached -> `Needs re-check`. `Still open` and `Needs re-check` rows carry into their prior tier at their prior label, marked `_(carried from round <N>)_` (`<N>` = the round the finding was first raised; a finding already carrying the group keeps it, never a second), each republishing its prior block with the prior Location annotation kept (it skips verify, so the annotation is not re-derived), and into Next Steps; a finding this round re-derives publishes once. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and publishes as `[Must]` when it was `[Blocker]`, `[High]`, or `[Critical]`, else `[Recommend]`.

### Step 13 - Write Report

**Subagent mode:** write no file. Return exactly `## Findings` (the tier sections and complete numbered finding blocks: label line, Location, Issue, Impact, and Fix, plus `System Risk` on every `[Must]`, and no Location annotation of its own - the umbrella's obs carve-out keys on verify's `Pre-existing` verdict plus `raised by: +obs`, missing-wire kinds only), then `## Next Steps`, prerequisites first, then one trailing line `Coverage: <what you read>; not evaluated: <rows>; <platform, tracer, depth trigger>`, which the parent puts in a Notes bullet. No Summary, `Prior Round Reconciliation`, or `Recommendations`.

Standalone: Use skill: `review-report-writer` with `report_type: review-observability`, `report_body`, `branch` (the handle's `head_short_name`; an audit's assembled `branch`), `base_ref` / `head_ref` as the handle emitted them (audit: `HEAD`), `base_sha` / `head_sha` and `round` / `prior_head_sha` from the Step 3 round gate, `mode: full`, `scope: +obs`, `depth` as run (audits pass `deep`), `stack = java-spring-boot`, and `pr_url` when the request carried a PR URL, else `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence. Every italic line, brace annotation, bracketed placeholder, and enum listing inside the fence is a fill rule addressed to you, not content: act on it, never print it.

**Severity assignment:** High = the gap blocks incident diagnosis or exposes secrets (no exported metrics at all, no tracer at all in a service that calls others, unstructured or timestamp-less logs on an incident path, lost trace/MDC context across a hop, swallowed async failures, credentials or payment-card data in logs, unsecured Actuator, severed traces from competing tracers). Medium = diagnosis possible but degraded or costly (missing metrics on key flows, unbounded tag cardinality, sampling wrong for the environment, personal data such as names or emails in logs). Low = polish (naming, levels, encoder tuning, per-call meter rebuilds). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` only when the incident named in the request or an in-repo postmortem passed through the finding's component - the label changes, never the tier, and System Risk names the incident; Low -> `[Recommend]`. A one-line fix never escalates by itself.

Headings are severity tiers; a finding stays in its tier after verify changes its label. The Label line carries the verified Label (the severity mapping only where verify did not run); Next Steps copies each finding's Label line, never re-derives it. Overall counts tiers. The Label line holds only the label and the carried marker; any other annotation goes on the Location line, which on an audit carries only `_(unverified: <reason>)_`.

```markdown
## Spring Boot Observability Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version> _(append `- below the floor (<Boot 3.x | Java < 21>)` when either is, and `- past OSS end` when the spring.io support table says so)_
- **Logging:** Boot structured logging (`logging.structured.format`) | Logback + Logstash JSON | Logback JsonEncoder | log4j2 | plain-text pattern (unstructured) | other
- **Platform:** Kubernetes | ECS | VM | PaaS (<name>) | unknown
- **Metrics:** Micrometer + Prometheus | Micrometer + OTLP | Micrometer + <other registry> | Micrometer via Actuator - no export registry | none | not determinable from what was read
- **Tracing:** Micrometer Tracing (OTel) | Micrometer Tracing (Brave/Zipkin) | OTel Java agent{ - declared outside the repo} | OTel Spring Boot starter | multiple tracers - conflicting | Sleuth (deprecated) | none
- **Error Tracker:** Sentry | Honeybadger | Rollbar | none
- **Coverage:** <what was read; on a diff review, the always-read config plus the changed files; at deep, which classes were and were not read>
- **Overall:** Adequate | Gaps Found - [<N> High / <N> Medium / <N> Low]
- **Round:** <N>   {round 2+ only}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}   {diff review}
- **Findings verified:** <N> confirmed, <U> unverified, <K> dropped - inline (no diff)   {audit, instead}
- **Notes:** <the depth trigger that fired; the audited tag or ref; which step's rows went `Not evaluated` and why, named by step rather than row when more than three; a `CLAUDE.md` fact the repo contradicts or does not show; `None`>

## Findings

### High Impact

1. **[Must]** | **[Recommend]**{ _(carried from round <N>)_}

   **Location:** [file:line; a config finding cites its key's line, `application-prod.yml:14`]{ the verify Annotation verbatim}

   **Issue:** [name the idiom and the key: missing MDC propagation across `@Async`, unbounded tag cardinality on `userId`, Actuator `*` exposure, two tracers, etc.]

   **Impact:** [diagnosability / alertability / cost]

   **System Risk:** [required on every `[Must]`: what an incident looks like with this gap in place]

   **Fix:** [specific Spring / Micrometer / Logback change with code or YAML, in the form the declared Boot version binds]

### Medium Impact

[Same block; `System Risk` optional on `[Recommend]`; numbering continues across tiers]

### Low Impact

[Same numbered-block structure]

_Omit empty sections._

## Recommendations

Open with the dependency order: which findings are prerequisites for the rest, so a service with broad gaps gets a sequence rather than an inventory. Then structural improvements not tied to a specific finding.

## Prior Round Reconciliation   {round 2+ standalone only}

[table, note line and tally from `review-prior-findings-reconcile`; when Step 12 built it instead, its comparison table]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Must] | [Recommend] [scope: ops] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting / dashboards / ops). Order Must > Recommend, and within a label put prerequisites before what depends on them. Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed Spring Boot (else delegated out); Boot and Java versions read from the build file, every cited construct and fix binding on them; platform and any out-of-build tracer recorded
- [ ] Step 3 - standalone: `report_type: review-observability` passed or audit fields assembled; round decided before any surface read, or the stop line printed; diff and log read once
- [ ] Step 4 - always-read config opened in full before any checklist; inert constructs judged as inert; every row a finding, a pass, or `Not evaluated`; absent prerequisites reported once
- [ ] Step 5 - structured logging: encoder or Boot structured format, timestamps, MDC, masking including personal data, payload discipline, levels with handled 4xx below ERROR, advice logging, whole-exception logging
- [ ] Step 6 - Actuator: exposure and gating (`access` is not auth), health depth against the default, probes against the platform, readiness composition, info safe
- [ ] Step 7 - Micrometer: exporting registry, auto-instrumentation, namespacing, tag cardinality, async timing correctness
- [ ] Step 8 - tracing: exactly one tracer (agent included) in the version's form, sampling per env, client construction checked, cross-thread continuity
- [ ] Step 9 - messaging / async: observation on both sides, consumer MDC, listener metrics, decoration by version, executor resolution, failure surfacing including swallowing listeners
- [ ] Step 10 - error tracker rows run, or the absence reported once
- [ ] Step 11 - SLI / health indicators reviewed (`deep` only); every row a finding, a pass, or `Not evaluated`
- [ ] Step 12 - standalone: `review-finding-verify` ran inline (claim-confirmation only on an audit), missing-wire exception applied, tally filled; round 2+: prior findings projected and reconciled (audit, or an audit or trunk-run prior: comparison table, no reconcile call); subagent: skipped
- [ ] Step 13 - standalone: report written via `review-report-writer` with every field from the round gate, confirmation printed; subagent: findings, Next Steps, and the coverage line returned, no file written
- [ ] Every finding sits in its severity tier with its verified label; every `[Must]` cites system risk; Recommendations state dependency order

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git
- "Add observability" without naming the idiom (say "register `Counter` named `acme.orders.placed` with bounded tags")
- Generic advice when a Spring starter or property exists ("set `logging.structured.format.console: ecs`" on Boot 3.4+, not "make logs structured")
- Reporting a Boot default as a defect (`show-details` unset, probe properties unset on Boot 4 or on Kubernetes, `send-default-pii` unset)
- Emitting a flat inventory of every failed checklist row when a service is broadly uninstrumented - collapse to the prerequisites and sequence them
