---
name: task-kotlin-review-observability
description: Kotlin / Spring Boot observability review: Micrometer, Actuator, Logback MDC + coroutine context, OpenTelemetry tracing, @Async/Kafka instrumentation.
agent: kotlin-tech-lead
metadata:
  category: backend
  tags: [kotlin, spring-boot, observability, logging, metrics, tracing, actuator, micrometer, coroutines, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Observability Review

## Purpose

Kotlin-aware observability review for Micrometer, Spring Boot Actuator, Logback / Logstash, MDC + `MDCContext` coroutine correlation, Micrometer Tracing / OpenTelemetry, listener / `@Async` / scope-launch interceptors, error tracker starters. Focuses on library-level wiring (production behavior visible / diagnosable / alertable). Infra concerns (Datadog SaaS, Sentry org settings, log forwarders) stay out of scope.

Stack-specific delegate of `task-code-review-observability`.

## When to Use

- Kotlin / Spring Boot PR for observability regressions
- Pre-release observability check for a new service or major feature
- Post-incident review when diagnosis was slow / evidence missing
- Adopting Micrometer Tracing / OTel / Logstash JSON in a Kotlin app
- Auditing async / coroutine / messaging tracing across request → `@Async` / `CoroutineScope.launch` / listener boundary

**Not for:** general review (`task-kotlin-review`), perf with a known bottleneck (`task-kotlin-review-perf`), active incidents (`/task-oncall-start`), infra dashboards / alerts.

## Depth Levels

| Depth      | When                                                                | What runs                                          |
| ---------- | ------------------------------------------------------------------- | -------------------------------------------------- |
| `quick`    | Single endpoint, controller, or listener                            | Logging + Micrometer metrics only                  |
| `standard` | Default                                                             | All steps                                          |
| `deep`     | Pre-release of a critical service, or post-incident                 | All steps + SLI/SLO suggestions for endpoints      |

## Invocation

| Invocation                                   | Meaning                                       |
| -------------------------------------------- | --------------------------------------------- |
| `/task-kotlin-review-observability`          | Current branch vs base                         |
| `/task-kotlin-review-observability <branch>` | `<branch>` vs base                             |
| `/task-kotlin-review-observability pr-<N>`   | PR head in `pr-<N>`                            |

When invoked as a subagent, Step 3 skipped.

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-confirmed.

### Step 3 - Resolve diff

Use skill: `review-precondition-check`. Read once. Skip if parent passed handle.

### Step 4 - Read the instrumentation surface

- `src/main/resources/logback-spring.xml` + per-profile variants - encoder type, MDC patterns, masking
- `application.yml` - `management.*`, `logging.*`, `spring.kafka.listener.observation-enabled`, `management.tracing.*`
- `build.gradle.kts` - `spring-boot-starter-actuator`, `micrometer-registry-prometheus`, `micrometer-tracing-bridge-otel`, error-tracker starters, `kotlinx-coroutines-slf4j` (for `MDCContext`)
- Every changed file registering `MeterRegistry` / `Counter` / `Timer` / `@KafkaListener` / `@RabbitListener` / `@JmsListener` / `@Async` / `@Scheduled` / `CoroutineScope.launch`, or modifying MDC

When only one surface changed (new listener but no `application.yml`), read existing config to confirm MDC propagation, observation flags, starters are wired.

### Step 5 - Structured logging (Logback + Logstash / SLF4J)

- [ ] **JSON encoder in prod** - Logstash Logback encoder or Logback 1.5+ `JsonEncoder`. No raw-text prod logs
- [ ] **MDC correlation**: `traceId`, `spanId`, `requestId`, `userId` (authenticated), `tenantId`, business correlation IDs. Set in filter / interceptor at request boundary; clear in `finally`
- [ ] **`logging.pattern.console` / `file`** includes `%X{traceId}` and `%X{spanId}` for non-JSON local dev
- [ ] **Sensitive-field masking**: covers `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`. DTOs use `@JsonIgnore`
- [ ] **No `log.info("user={}", user)`** that serializes a JPA entity (lazy loads + may log PII / hashed passwords). Log specific fields by ID
- [ ] **Log levels**: `error` for actionable, `warn` for recoverable, `info` for state transitions, `debug` for verbose
- [ ] **Parameterized SLF4J only** (`log.info("processing order={}", orderId)`) - **NOT Kotlin string templates** (`log.info("processing order=$orderId")`). String templates build the string before the level check and prevent structured loggers from preserving placeholders. Flag every string-template log call as [High] in prod
- [ ] **No log spam in hot loops** - `forEach` over large collections, scheduled jobs, Kafka listeners at high TPS use `log.atDebug()` or sampled logging
- [ ] **Async appenders** for high-volume paths
- [ ] **No `println` / `System.out.println` / `dump()`** in production
- [ ] **No HTTP body logging in prod** - full body logs leak PII and explode volume. Only behind `debug` + env flag + masking. Flag unconditional body logs as [High]

### Step 6 - Spring Boot Actuator

- [ ] **Actuator present** (`spring-boot-starter-actuator`)
- [ ] **`management.endpoints.web.exposure.include`** minimal in prod (e.g., `health, info, metrics, prometheus`). Never `*`
- [ ] **Sensitive endpoints gated**: `env`, `heapdump`, `threaddump`, `mappings`, `configprops`, `loggers` auth-required (separate `SecurityFilterChain` for `/actuator/**`)
- [ ] **`management.endpoint.health.show-details: when-authorized`** (not `always` in prod)
- [ ] **Liveness vs readiness**: probes configured; liveness doesn't depend on downstream services
- [ ] **`info` endpoint**: build / git / version; no env-var leaks
- [ ] **`management.server.port`** separated in prod when network isolation needed

### Step 7 - Micrometer metrics

- [ ] **`micrometer-registry-prometheus`** on classpath; `/actuator/prometheus` exposed
- [ ] **Auto-instrumentation enabled**: `http.server.requests`, `hikaricp.*`, `hibernate.*`, `jvm.*`, `tomcat.*`
- [ ] **Custom metrics** in consistent namespace (`acme.orders.placed`); units explicit
- [ ] **Tag cardinality bounded** - never use as tags:
  - **High-cardinality IDs**: `userId`, `orderId`, `requestId`, `traceId`, sessions, UUIDs
  - **Numeric measurements**: amounts, counts, sizes, durations - these are *values*
  - **Free-text**: error messages, exception messages, user-supplied strings, URL query strings
  - Acceptable: bounded enumerations (status code families, error class names, region, tenant tier)
- [ ] **`http.server.requests` URI templating preserved**: must record `/users/{id}` not `/users/123`. Silently broken by custom `HandlerInterceptor` / filter that overrides URI attributes, or `MeterFilter` dimensioning on raw URI. Verify in `/actuator/prometheus`
- [ ] **`@Timed` on hot paths**: critical user journeys; `histogram = true` only when distribution observability needed
- [ ] **`MeterFilter`** trims unused metrics / denies high-cardinality dimensions
- [ ] **No metric registration in hot loops**: cache `Counter.builder(...).register(...)` in `companion object val` or constructor field

### Step 8 - Distributed tracing

_Skipped at `quick`._

- [ ] **Bridge configured**: `io.micrometer:micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` (OTel) or `micrometer-tracing-bridge-brave` (Zipkin)
- [ ] **Sampling explicit**: `management.tracing.sampling.probability` per env (e.g., `0.1` in prod)
- [ ] **`Observation` API for custom spans** (Boot 3+) - `Observation.start("process-order", registry)`
- [ ] **`traceparent` propagation**: `WebClient` / `RestClient` auto-instrumented; manual `OkHttpClient` flagged
- [ ] **`@Async` + VT tracing**: `ContextSnapshot` / `TaskDecorator` propagates trace context across thread boundaries
- [ ] **Coroutine tracing**: `MDCContext` from `kotlinx-coroutines-slf4j` (or `MicrometerObservationCoroutineContextElement`) carries trace context across dispatcher switches; flag `suspend` paths losing trace correlation
- [ ] **DB span enrichment**: `p6spy` / `datasource-proxy` attaches SQL to spans in non-prod
- [ ] **Not over-instrumented**: don't wrap `getUserById` in `Observation` if the JDBC span already covers it

### Step 9 - Async / messaging observability

_Skipped at `quick` unless diff touches messaging / scheduled / launch._

- [ ] **Kafka**: `spring.kafka.listener.observation-enabled: true`
- [ ] **RabbitMQ**: `spring.rabbitmq.listener.simple.observation-enabled: true`
- [ ] **MDC across consumer threads**: filter / aspect copies `traceId`, `userId`, `tenantId` from message headers into MDC at handler entry; clears in `finally`
- [ ] **MDC across coroutines**: `withContext(MDCContext()) { ... }` or `applicationScope.launch(MDCContext() + ...)`
- [ ] **Listener metrics**: per-topic `Timer` for handle latency; `Counter` for retries / DLT; queue lag metric
- [ ] **`@Async` decoration**: `TaskDecorator` (or `ContextPropagatingTaskDecorator`) preserves MDC, security, trace context
- [ ] **`@Scheduled`**: each method emits `Observation`; per-job duration timer; missed-execution metric
- [ ] **`CoroutineScope.launch`**: scope built with `MDCContext` + `CoroutineExceptionHandler` logging uncaught exceptions; fire-and-forget without observability = [High]

### Step 10 - Error tracking

_Skipped at `quick` unless diff touches advice / error-tracker config / DSN handling._

- [ ] **Boot starter** (`sentry-spring-boot-starter-jakarta`, `honeybadger`, `rollbar-spring-boot-starter`) integrates with `@RestControllerAdvice` + MDC + Logback automatically
- [ ] **DSN / API key** in env / Vault, not `application.yml`
- [ ] **Release / environment tags** from build metadata
- [ ] **PII scrubbing on**: `sentry.send-default-pii: false` in prod
- [ ] **MDC forwarded** in error events
- [ ] **Sample rate explicit** per env; not `1.0` in prod for tracing
- [ ] **Ignored exceptions documented** with rationale
- [ ] **`@RestControllerAdvice` maps to responses without losing the stack** - tracker captures the original exception before the advice replaces it

### Step 11 - Health checks / SLIs

_Deep only._ Critical journeys have a Micrometer SLI (filtered `http.server.requests`, success rate, p95); DB / cache / broker / external API via `HealthIndicator`; SLO targets documented; synthetic probes use `/actuator/health/readiness`.

### Step 12 - Write report

Use skill: `review-report-writer` with `report_type: review-observability`. Print confirmation.

## Output Format

```markdown
## Kotlin / Spring Boot Observability Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Logging:** Logback + Logstash JSON | Logback JsonEncoder | other
**Metrics:** Micrometer + Prometheus | StatsD | none
**Tracing:** Micrometer Tracing (OTel) | (Brave/Zipkin) | none
**Coroutine MDC:** MDCContext wired | absent | n/a
**Error Tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [count by impact]

## Findings

### High Impact
- **Location:** [file:line or config key]
- **Issue:** [Kotlin/Spring/Micrometer/Logback idiom: missing MDCContext across `suspend`, Kotlin string-template log breaks parameterization, unbounded tag cardinality on `userId`, Actuator `*` exposure, `println` in prod, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific change with code or YAML]

### Medium / Low / Quick Wins
[Same structure]

_Omit empty sections._

## Recommendations
[Structural improvements]

## Next Steps
1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: ops] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]
```

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] Stack confirmed (or accepted from parent)
- [ ] `review-precondition-check` ran (or handle received)
- [ ] Diff and log read once; reused
- [ ] When `head_matches_current` was false, user approval obtained
- [ ] Instrumentation surfaces read directly
- [ ] Logback / SLF4J assessed: JSON encoder, MDC, masking, log level discipline, parameterized logging (NOT string templates), no `println`
- [ ] Actuator reviewed: exposure list, sensitive endpoints gated, probes, health depth
- [ ] Micrometer assessed: registry, auto-instrumentation, tag cardinality, namespacing
- [ ] Tracing bridge assessed: Boot 3+ Micrometer Tracing, sampling, propagation through `@Async` and outbound clients
- [ ] **Coroutine MDC / trace propagation** assessed: `MDCContext` for `suspend` and `CoroutineScope.launch`
- [ ] Messaging observability: Kafka / RabbitMQ / JMS listener observation, MDC propagation across consumer threads
- [ ] Error tracker: starter wired, DSN externalized, PII scrubbed, MDC forwarded
- [ ] Findings name a Kotlin/Spring/Micrometer/Logback idiom directly
- [ ] Library scope respected; infra explicitly deferred
- [ ] Depth honored
- [ ] Next Steps ordered High > Medium > Low
- [ ] Report written; confirmation printed

## Avoid

- State-changing git
- Reporting gaps without naming a Kotlin/Spring/Micrometer/Logback idiom
- Generic observability advice when a Spring starter / auto-config exists
- Reviewing infra concerns (Datadog SaaS, Grafana alert rules, log forwarders)
- Treating high tag cardinality (`userId`, `orderId`) as acceptable
- Leaving `*` in `management.endpoints.web.exposure.include` in prod
- Suggesting `log.info("...", e)` (loses stack) over `log.error("...", e)`
- Approving Spring Cloud Sleuth on Boot 3 - migrate to Micrometer Tracing
- Approving Kotlin string-template logging in production
- Approving fire-and-forget `CoroutineScope.launch` without `MDCContext` + `CoroutineExceptionHandler`
