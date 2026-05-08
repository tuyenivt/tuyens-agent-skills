---
name: task-kotlin-review-observability
description: Kotlin/Spring Boot observability review for Micrometer metrics, Spring Boot Actuator, structured logging via Logback / Logstash encoder, MDC + coroutine context correlation, OpenTelemetry / Micrometer Tracing, @KafkaListener / @Async / CoroutineScope.launch instrumentation, and error-tracker integration. Library-level focus, not infra. Stack-specific override of task-code-review-observability for Kotlin/Spring Boot.
agent: kotlin-tech-lead
metadata:
  category: backend
  tags: [kotlin, spring-boot, observability, logging, metrics, tracing, actuator, micrometer, coroutines, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Observability Review

## Purpose

Kotlin-aware observability review that names Micrometer, Spring Boot Actuator, Logback / Logstash JSON encoder, MDC + `MDCContext` coroutine correlation, Micrometer Tracing / OpenTelemetry, `@KafkaListener` / `@Async` / `CoroutineScope.launch` interceptors, and error-tracker Spring Boot starters directly. Focuses on whether Kotlin/Spring production behavior is visible, diagnosable, and alertable - at the library / starter level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Kotlin/Spring Boot.

## When to Use

- Reviewing a Kotlin/Spring Boot PR for observability regressions
- Pre-release observability check for a new Kotlin service or major feature
- Post-incident review when Kotlin diagnosis was slow or evidence was missing
- Adopting Micrometer Tracing / OpenTelemetry / Logstash JSON encoder in a Kotlin app
- Auditing async / coroutine / messaging tracing across the request -> `@Async` / `CoroutineScope.launch` / listener boundary

**Not for:**

- General Kotlin/Spring Boot code review (use `task-kotlin-review`)
- Performance issues with a known bottleneck (use `task-kotlin-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                      | What Runs                                            |
| ---------- | ---------------------------------------------------------------- | ---------------------------------------------------- |
| `quick`    | Single endpoint, controller, or listener                         | Logging + Micrometer metrics check only              |
| `standard` | Default - full Kotlin/Spring observability review                | All steps                                            |
| `deep`     | Pre-release of a critical Kotlin service, or post-incident review | All steps + SLI/SLO suggestions for Spring endpoints |

Default: `standard`.

## Invocation

| Invocation                                   | Meaning                                                             |
| -------------------------------------------- | ------------------------------------------------------------------- |
| `/task-kotlin-review-observability`          | Review current branch vs its base                                   |
| `/task-kotlin-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                          |
| `/task-kotlin-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>`                 |

When invoked as a subagent, Step 3 (diff resolution) is skipped.

## Workflow

### Step 1 - Load Behavioral Principles (mandatory, first)

Use skill: `behavioral-principles`. Load these rules first - they govern every subsequent step.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Kotlin / Spring Boot. Accept pre-confirmed stack from parent.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read diff and commit log once. Skip if invoked as subagent and parent passed the handle.

### Step 4 - Read the Instrumentation Surface

Open files that actually configure observability:

- `src/main/resources/logback-spring.xml` (and per-profile variants) - encoder type, MDC patterns, masking
- `src/main/resources/application.yml` - `management.*`, `logging.*`, `spring.kafka.listener.observation-enabled`, `management.tracing.*`
- `build.gradle.kts` - confirm `spring-boot-starter-actuator`, `micrometer-registry-prometheus`, `micrometer-tracing-bridge-otel`, error-tracker starters, `kotlinx-coroutines-slf4j` (for `MDCContext`)
- Every changed file that registers a `MeterRegistry`, `Counter`, `Timer`, `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@Async`, `@Scheduled`, `CoroutineScope.launch`, or modifies `MDC`

For diffs touching only one of these surfaces (a new listener but no `application.yml` change), still read the existing config to know whether MDC propagation, observation flags, and starters are wired.

### Step 5 - Structured Logging (Logback + Logstash encoder / SLF4J)

Inspect `logback-spring.xml`, `application.yml` `logging.*` keys, and any `log.*` callsite:

- [ ] **Production logger emits JSON** - Logstash Logback encoder (`net.logstash.logback.encoder.LogstashEncoder`) or Logback `JsonEncoder` (Logback 1.5+). No raw text logs in production
- [ ] **MDC correlation fields injected** in every log line: `traceId`, `spanId`, `requestId`, `userId` (when authenticated), `tenantId`, plus business correlation IDs. Use `MDC.put(...)` in a filter / interceptor at request boundary; clear in `finally`
- [ ] **`logging.pattern.console` / `pattern.file`** include `%X{traceId}` and `%X{spanId}` placeholders so non-JSON local dev logs still show correlation
- [ ] **Sensitive-field masking**: Logback masking encoder or Logstash `maskMessageRegex` covers `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`. DTOs use `@JsonIgnore` for the same fields
- [ ] **No `log.info("user={}", user)`** that serializes a JPA entity (triggers lazy loads and may log PII / hashed passwords). Always log specific fields by ID
- [ ] **Log levels used correctly**: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics
- [ ] **Parameterized SLF4J logging only** (`log.info("processing order={}", orderId)`) - **NOT Kotlin string templates** (`log.info("processing order=$orderId")`). String-template interpolation defeats parameterized-logging benefits: it builds the string before the level check and prevents structured loggers (Logstash) from preserving placeholders as JSON keys. Flag every Kotlin string-template log call as [High] in production code
- [ ] **No log spam in hot loops** - `forEach` over large collections, scheduled jobs, Kafka listeners at high TPS must not log per-iteration; use `log.atDebug()` or sampled logging
- [ ] **Async appenders** (`AsyncAppender` or Logstash async TCP) configured for high-volume paths
- [ ] **No `println` / `System.out.println` / `dump()`** in production code - flag and replace with SLF4J logger

### Step 6 - Spring Boot Actuator

Inspect `application.yml` `management.*` keys and any custom `@Endpoint` / `HealthIndicator` / `InfoContributor`:

- [ ] **Actuator dependency present** (`spring-boot-starter-actuator`) - if absent in a service that warrants observability, flag it
- [ ] **`management.endpoints.web.exposure.include`** is minimal in prod: typically `health, info, metrics, prometheus`. Never `*` in prod
- [ ] **Sensitive endpoints gated**: `env`, `heapdump`, `threaddump`, `mappings`, `configprops`, `loggers` are auth-required (behind a separate `SecurityFilterChain` for `/actuator/**`)
- [ ] **Health endpoint depth**: `management.endpoint.health.show-details: when-authorized` (not `always` in prod)
- [ ] **Liveness vs readiness**: liveness/readiness groups configured for Kubernetes (`management.endpoint.health.probes.enabled: true`); `/actuator/health/liveness` does not depend on downstream services
- [ ] **`info` endpoint**: build, git, version info exposed; does not leak environment variables
- [ ] **`management.server.port`** separated from main server port in prod when network isolation is required

### Step 7 - Micrometer Metrics

Inspect any `MeterRegistry`, `@Timed`, or `Counter` / `Timer` registration:

- [ ] **`micrometer-registry-prometheus`** on the classpath; `/actuator/prometheus` exposed
- [ ] **Spring auto-instrumentation enabled**: HTTP server timer (`http.server.requests`), JDBC (`hikaricp.*`), JPA (`hibernate.*`), JVM (`jvm.memory.*`, `jvm.gc.*`), Tomcat (`tomcat.*`)
- [ ] **Custom business metrics** named under a consistent namespace (`acme.orders.placed`); units explicit
- [ ] **Tag cardinality bounded**: tags do not include unbounded values (`userId`, `orderId`, `requestId`) - causes metric-cardinality blow-up
- [ ] **`@Timed` on hot paths**: service methods on critical user journeys; `histogram = true` only when latency-distribution observability is required
- [ ] **`MeterFilter`** trims unused metrics or denies high-cardinality dimensions
- [ ] **No metric registration in hot loop**: cache `Counter.builder(...).register(...)` results in a `companion object val` or constructor-initialized field

### Step 8 - Distributed Tracing (Micrometer Tracing / OpenTelemetry)

_Skipped at `quick` depth._

Inspect tracing dependencies and bridge config:

- [ ] **Tracing bridge configured**: `io.micrometer:micrometer-tracing-bridge-otel` + `io.opentelemetry:opentelemetry-exporter-otlp` (preferred for OTel pipelines), or `micrometer-tracing-bridge-brave` for Zipkin
- [ ] **Sampling policy explicit**: `management.tracing.sampling.probability` set per env (e.g., `0.1` in prod)
- [ ] **`Observation` API used** for custom spans (Boot 3+) - `Observation.start("process-order", registry)`
- [ ] **`traceparent` propagation** validated on outbound: `WebClient` / `RestClient` auto-instrumented; manual `OkHttpClient` instances flagged
- [ ] **`@Async` and Virtual Thread tracing**: `ContextSnapshot` / `TaskDecorator` propagates trace context across thread boundaries
- [ ] **Coroutine tracing**: `MDCContext` from `kotlinx-coroutines-slf4j` (or `MicrometerObservationCoroutineContextElement`) carries trace context across `suspend` dispatcher switches; flag `suspend` service paths that lose trace correlation
- [ ] **Database span enrichment**: `p6spy` or `datasource-proxy` attaches SQL to spans in non-prod
- [ ] **Spans not too granular**: do not wrap `getUserById` in an `Observation` if the JDBC span already covers it

### Step 9 - Async / Messaging Observability

_Skipped at `quick` depth unless the diff touches `@KafkaListener` / `@RabbitListener` / `@JmsListener` / `@Async` / `@Scheduled` / `CoroutineScope.launch`._

Inspect listeners, scheduled jobs, and coroutine launches:

- [ ] **Kafka observability enabled**: `spring.kafka.listener.observation-enabled: true` (Boot 3+)
- [ ] **RabbitMQ observability**: `spring.rabbitmq.listener.simple.observation-enabled: true`
- [ ] **MDC propagation across consumer threads**: filter / aspect copies `traceId`, `userId`, `tenantId` from message headers into MDC at handler entry; clears in `finally`
- [ ] **MDC propagation across coroutines**: `withContext(MDCContext()) { ... }` or `applicationScope.launch(MDCContext() + ...)` carries MDC across dispatcher switches
- [ ] **Listener metrics**: per-topic `Timer` for handle latency; `Counter` for retries / DLT; queue lag metric exposed
- [ ] **`@Async` decoration**: `TaskDecorator` (or `ContextPropagatingTaskDecorator` from Micrometer Context Propagation) preserves MDC, security context, and trace context
- [ ] **`@Scheduled` instrumentation**: each scheduled method emits an `Observation` so trace data exists; per-job duration timer; missed-execution alerting via metric
- [ ] **`CoroutineScope.launch` instrumentation**: scope built with `MDCContext` and `CoroutineExceptionHandler` that logs uncaught exceptions; fire-and-forget without observability is a [High] finding

### Step 10 - Error Tracking (Sentry / Honeybadger / Rollbar starters)

_Skipped at `quick` depth unless the diff modifies `@RestControllerAdvice`, error-tracker config, or DSN/API-key handling._

Inspect Sentry / Honeybadger / Rollbar dependencies:

- [ ] **Boot starter** present (`sentry-spring-boot-starter-jakarta`, `honeybadger`, `rollbar-spring-boot-starter`) - integrates with `@RestControllerAdvice`, MDC, Logback automatically
- [ ] **DSN / API key** in env var or Vault, not committed to `application.yml`
- [ ] **Release / environment tags** populated from build metadata (`sentry.release`, `sentry.environment`)
- [ ] **PII scrubbing on**: `sentry.send-default-pii: false` in prod
- [ ] **MDC fields forwarded**: error event includes `traceId`, `userId`, `tenantId`
- [ ] **Sample rate explicit**: `sentry.traces-sample-rate`, `sentry.profiles-sample-rate` per env; not `1.0` in prod for tracing
- [ ] **Ignored exceptions documented**: each ignore has a comment explaining why
- [ ] **`@RestControllerAdvice` maps exceptions to user-facing responses without losing the stack** - error tracker captures the original exception before the advice replaces it

### Step 11 - Health Checks and SLIs (deep depth only)

When invoked at `deep`:

- [ ] Critical user journeys have at least one Micrometer SLI (`http.server.requests` filtered to the journey URI, success rate, p95 latency)
- [ ] DB / cache / message broker / external API health checked via `HealthIndicator`
- [ ] SLO targets documented in code or service README
- [ ] Synthetic probes call `/actuator/health/readiness` not just `/actuator/health`

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before stack detection or any other delegation
- [ ] Stack confirmed as Kotlin / Spring Boot (or accepted from parent dispatcher)
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused
- [ ] When `head_matches_current` was false, explicit user approval was obtained
- [ ] Instrumentation surfaces (logback-spring.xml, application.yml `management.*`, build.gradle.kts dependencies, changed listeners/registrations) read directly
- [ ] Logback / SLF4J structured logging assessed: JSON encoder, MDC correlation, sensitive-field masking, log level discipline, parameterized logging (NOT Kotlin string templates), no `println`
- [ ] Spring Boot Actuator config reviewed: exposure list minimal, sensitive endpoints gated, liveness/readiness probes, info / health depth bounded
- [ ] Micrometer metrics assessed: registry on classpath, auto-instrumentation enabled, tag cardinality bounded, custom metrics namespaced
- [ ] Tracing bridge assessed: Boot 3+ Micrometer Tracing, sampling explicit, propagation across `@Async` and outbound clients
- [ ] **Coroutine MDC / trace propagation** assessed: `MDCContext` for `suspend` paths and `CoroutineScope.launch`
- [ ] Messaging observability assessed: Kafka / RabbitMQ / JMS listener observation, MDC propagation across consumer threads
- [ ] Error tracker integration assessed: Boot starter wired, DSN externalized, PII scrubbed, MDC forwarded
- [ ] Findings name a Kotlin/Spring/Micrometer/Logback idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing/messaging/error-tracker/SLI; `deep` ran the SLI step
- [ ] Next Steps section produced ordered High > Medium > Low

## Output Format

```markdown
## Kotlin / Spring Boot Observability Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Logging:** Logback + Logstash JSON encoder | Logback JsonEncoder | other
**Metrics:** Micrometer + Prometheus | Micrometer + StatsD | none
**Tracing:** Micrometer Tracing (OTel) | Micrometer Tracing (Brave/Zipkin) | none
**Coroutine MDC:** MDCContext wired | absent | n/a (no coroutines)
**Error Tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [name the Kotlin/Spring/Micrometer/Logback idiom: missing MDCContext across `suspend`, Kotlin string-template log breaks parameterization, unbounded tag cardinality on `userId`, Actuator `*` exposure, `println` in production, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Kotlin/Spring/Micrometer/Logback change with code or YAML example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements - e.g., "Add Logstash JSON encoder", "Wrap CoroutineScope launches with MDCContext", "Replace string-template log calls with parameterized SLF4J in OrderService.kt"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/actuator/prometheus` to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- Running state-changing git commands from this workflow
- Reporting gaps without naming the Kotlin/Spring/Micrometer/Logback idiom
- Recommending generic observability advice when a Spring starter or auto-config exists
- Reviewing infra-level concerns (Datadog SaaS, Grafana alert rules, log forwarder config) - those belong to ops review
- Treating high tag cardinality (`userId`, `orderId`) as acceptable
- Leaving `*` in `management.endpoints.web.exposure.include` in prod
- Suggesting `log.info("...", e)` (loses stack trace) instead of `log.error("...", e)`
- Approving Spring Cloud Sleuth on Boot 3 - migrate to Micrometer Tracing
- Approving Kotlin string-template logging in production code (`log.info("user=$userId")`) - flag as [High] in favor of parameterized SLF4J
- Approving fire-and-forget `CoroutineScope.launch` without `MDCContext` and `CoroutineExceptionHandler`
