---
name: task-spring-review-observability
description: "Spring Boot observability review: Logback JSON, MDC, Actuator, Micrometer, Micrometer Tracing/OTel, listener instrumentation, error trackers."
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, observability, logging, metrics, tracing, actuator, micrometer, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Observability Review

Spring-aware observability review naming Micrometer, Spring Boot Actuator, Logback / Logstash JSON, MDC, Micrometer Tracing / OTel, listener interceptors, error-tracker starters - at the library / starter level. Infra concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

Stack-specific delegate of `task-code-review-observability` for Java / Spring Boot.

## When to Use

- Spring Boot PR with observability regressions or new instrumentation gaps
- Pre-release observability check for a new Spring service / major feature
- Post-incident review when diagnosis was slow or evidence was missing
- Adopting Micrometer Tracing / OTel / Logstash JSON encoder
- Auditing async / messaging tracing and MDC correlation

**Not for:**
- General Spring review (`task-spring-review`)
- Perf with known bottleneck (`task-spring-review-perf`)
- Active incident (`/task-oncall-start`)
- Infra observability (Datadog dashboards, Grafana panels, alert rules) - not in source code

## Depth Levels

| Depth      | When                                                          | What Runs                                            |
| ---------- | ------------------------------------------------------------- | ---------------------------------------------------- |
| `quick`    | Single endpoint, controller, or listener                      | Logging + Micrometer metrics only                    |
| `standard` | Default                                                       | All steps                                            |
| `deep`     | Pre-release of critical service or post-incident review       | All steps + SLI/SLO suggestions for Spring endpoints |

Default: `standard`.

## Invocation

| Invocation                                   | Meaning                                                       |
| -------------------------------------------- | ------------------------------------------------------------- |
| `/task-spring-review-observability`          | Current branch vs base; fails fast on trunk                   |
| `/task-spring-review-observability <branch>` | `<branch>` vs base (3-dot diff)                               |
| `/task-spring-review-observability pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)         |

When invoked as a subagent, the parent passes the precondition handle + pre-read diff and commit log; Step 3 below is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a Spring-aware parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review-observability`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent and the parent passed the handle plus artifacts.

If the precondition check stops with a fail-fast message, surface verbatim and stop. No state-changing git from this workflow.

### Step 4 - Read the Instrumentation Surface

Before applying checklists, open files that actually configure observability so findings cite real lines:

- `logback-spring.xml` (and `logback-spring-<profile>.xml`) - encoder type, MDC patterns, masking
- `application.yml` (and per-profile) - `management.*`, `logging.*`, `spring.kafka.listener.observation-enabled`, `management.tracing.*`
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-actuator`, `micrometer-registry-prometheus`, `micrometer-tracing-bridge-otel`, error-tracker starters
- Every changed file registering `MeterRegistry`, `Counter`, `Timer`, `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@Async`, `@Scheduled`, or `MDC`

For diffs touching only one surface (a new listener but no `application.yml` change), still read existing config to know whether MDC propagation, observation flags, and starters are wired - a missing wire is the finding.

### Step 5 - Structured Logging

- [ ] **Production logger emits JSON** - Logstash Logback encoder (`net.logstash.logback.encoder.LogstashEncoder`) or Logback 1.5+ `JsonEncoder` / `JsonLayout`. No raw text logs in prod.
- [ ] **MDC correlation injected** on every log line: `traceId`, `spanId`, `requestId`, `userId` (when authenticated), `tenantId`, plus business correlation IDs (`orderId`, `invoiceId`). `MDC.put(...)` in a filter / interceptor at request boundary; clear in `finally`.
- [ ] **`logging.pattern.console` / `pattern.file`** include `%X{traceId}` and `%X{spanId}` so non-JSON local logs show correlation
- [ ] **Sensitive-field masking** - Logback masking encoder or Logstash `maskMessageRegex` covers `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`. DTOs use `@JsonIgnore` on the same fields so `log.info("payload={}", dto)` can't leak via Jackson.
- [ ] **No `log.info("user={}", user)`** that serializes a JPA entity (lazy loads, PII risk). Log specific fields by ID.
- [ ] **No HTTP body logging in prod paths** - `RestClient` / `WebClient` body-logging interceptors leak PII. Scope to non-prod profile or use a redacting interceptor with an explicit allowlist.
- [ ] **Log levels correct** - `error` actionable, `warn` recoverable, `info` state transitions, `debug` verbose. Default root `INFO` in prod
- [ ] **Parameterized logging** - `log.info("processing order={}", orderId)`; no string concatenation; no `String.format(...)` in logger calls
- [ ] **No log spam in hot loops** - per-iteration `forEach` / per-second `@Scheduled` / high-TPS listener uses `log.atDebug()` or sampling
- [ ] **Async appenders** - `AsyncAppender` / Logstash async TCP for high-volume; queue-full policy explicit

### Step 6 - Spring Boot Actuator

- [ ] **`spring-boot-starter-actuator`** present (flag if absent in a service that warrants observability)
- [ ] **`management.endpoints.web.exposure.include`** minimal in prod: typically `health, info, metrics, prometheus` (+ `loggers` if dynamic log-level change is needed). Never `*` in prod
- [ ] **Sensitive endpoints gated** - `env`, `heapdump`, `threaddump`, `mappings`, `configprops`, `loggers` are auth-required (`management.endpoint.<name>.access` or behind a separate `SecurityFilterChain` for `/actuator/**`)
- [ ] **Health depth** - `/actuator/health` high-level only by default; `management.endpoint.health.show-details: when-authorized` (not `always`)
- [ ] **Liveness vs readiness** - Boot 2.3+ probes configured for Kubernetes (`management.endpoint.health.probes.enabled: true`); liveness depends on JVM/app only; readiness reflects ability to serve (DB, caches warmed)
- [ ] **`info` endpoint** - build, git, version info on (`management.info.git.enabled`, `management.info.build.enabled`); no env-var or sensitive leakage
- [ ] **`management.server.port`** separated from main port in prod when network isolation is required

### Step 7 - Micrometer Metrics

- [ ] **`micrometer-registry-prometheus`** (or equivalent) on classpath; `/actuator/prometheus` exposed
- [ ] **Auto-instrumentation enabled** - `http.server.requests`, HikariCP `hikaricp.*`, JPA `hibernate.*` (`generate_statistics=true` non-prod), JVM `jvm.memory.*` / `jvm.gc.*`, container `tomcat.*`
- [ ] **Custom business metrics** under a consistent namespace (`acme.orders.placed`, `acme.payments.failed`); units explicit (`Counter` counts, `Timer` durations, `Gauge` instantaneous, `DistributionSummary` histograms)
- [ ] **Tag cardinality bounded.** Reject:
  - **High-cardinality identifiers** - `userId`, `orderId`, `paymentId`, `requestId`, `traceId` (these belong on traces and logs)
  - **Continuously varying numerics** - `amount`, `latency_ms`, `payload_size_bytes` (use `DistributionSummary` / histogram)
  - **Free text** - error messages, search terms, raw HTTP paths with embedded IDs (normalize `/orders/42` → `/orders/{id}`)
  Allowed: enums / bounded categories (`status`, `tenant_tier`, `region`, `error_code`)
- [ ] **`http.server.requests` URI templating** - tag must be the route template (`/orders/{id}`), not the resolved path. Verify `WebMvcMetricsFilter` is in the chain; custom HTTP timers use `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE`
- [ ] **`@Timed` on hot paths** - critical user journeys; `histogram = true` only when latency-distribution is required (cost: more series)
- [ ] **`MeterFilter`** trims unused / high-cardinality metrics
- [ ] **No metric registration in hot loop** - `Counter.builder(...).register(...)` _creates_ each call; cache the result in a `final` field

### Step 8 - Distributed Tracing

_Skipped at `quick` depth._

- [ ] **Tracing bridge configured** - `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` (OTel pipelines) or `micrometer-tracing-bridge-brave` (Zipkin). Boot 3+ uses Micrometer Tracing; Boot 2.x Sleuth flagged for migration
- [ ] **Sampling policy explicit** - `management.tracing.sampling.probability` per env (e.g., `0.1` prod, `1.0` staging); not left at default
- [ ] **`Observation` API used** for custom spans on Boot 3+ - `Observation.start("process-order", registry)` over manual span management
- [ ] **`traceparent` propagation** - `RestClient` / `WebClient` / Feign auto-instrumented; manual `OkHttpClient` / `HttpClient` flagged for missing tracing interceptor
- [ ] **`@Async` and Virtual Thread tracing** - `ContextSnapshot` / `TaskDecorator` propagates trace context across thread boundaries
- [ ] **Database span enrichment** - `p6spy` / `datasource-proxy` attaches SQL to spans non-prod
- [ ] **Spans not over-granular** - don't wrap `getUserById` in `Observation` if JDBC span already covers it

### Step 9 - Async / Messaging Observability

_Skipped at `quick` depth unless the diff touches `@KafkaListener` / `@RabbitListener` / `@JmsListener` / `@Async` / `@Scheduled`._

- [ ] **Kafka observability** - `spring.kafka.listener.observation-enabled: true` (Boot 3+) bridges producer trace context
- [ ] **RabbitMQ observability** - `spring.rabbitmq.listener.simple.observation-enabled: true`
- [ ] **MDC propagation across consumer threads** - filter / aspect copies `traceId`, `userId`, `tenantId` from message headers; clears in `finally`
- [ ] **Listener metrics** - per-topic `Timer` for handle latency, `Counter` for retries / DLT, queue / partition lag exposed
- [ ] **`@Async` decoration** - `TaskDecorator` (or `ContextPropagatingTaskDecorator`) preserves MDC, security, trace context
- [ ] **`@Scheduled` instrumentation** - each method emits `Observation`; per-job duration timer; missed-execution alerting

### Step 10 - Error Tracking

_Skipped at `quick` depth unless the diff modifies `@RestControllerAdvice`, error-tracker config, or DSN/API-key handling._

- [ ] **Boot starter wired** - `sentry-spring-boot-starter-jakarta`, `honeybadger`, or `rollbar-spring-boot-starter`
- [ ] **DSN / API key** in env var or Vault - not in `application.yml`
- [ ] **Release / env tags** from build metadata (`sentry.release`, `sentry.environment`)
- [ ] **PII scrubbing on** - `sentry.send-default-pii: false` in prod; explicit breadcrumb allowlist
- [ ] **MDC forwarded** - error event includes `traceId`, `userId`, `tenantId`
- [ ] **Sample rate explicit** - `sentry.traces-sample-rate`, `profiles-sample-rate` per env; not `1.0` in prod
- [ ] **Ignored exceptions documented** - `sentry.ignored-exceptions-for-type` (e.g., `OptimisticLockException` when retry handles it); each ignore has a comment
- [ ] **`@RestControllerAdvice`** captures the original exception before replacing it with a response DTO

### Step 11 - Health Checks and SLIs (`deep` only)

- [ ] Critical user journeys have a Micrometer SLI (`http.server.requests` filtered to the journey URI, success rate, p95)
- [ ] DB / cache / broker / external API checked via `HealthIndicator`; custom indicators for non-Spring-managed dependencies
- [ ] SLO targets documented in code, not a free-floating Confluence page
- [ ] Synthetic probes (k6 / Gatling) call `/actuator/health/readiness`, not `/actuator/health`

### Step 12 - Write Report

Use skill: `review-report-writer` with `report_type: review-observability`. Write to the report file before ending; print confirmation.

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed (or accepted from parent)
- [ ] `review-precondition-check` ran (or handle received)
- [ ] Diff and commit log read once and reused
- [ ] When `head_matches_current` was false, explicit user approval obtained (skipped when running as subagent)
- [ ] Instrumentation surfaces (logback-spring.xml, application.yml management/logging, build dependencies, changed listeners) read before checklists
- [ ] Structured logging assessed: JSON encoder, MDC, masking, level discipline, parameterized
- [ ] Actuator config reviewed: exposure minimal, sensitive gated, probes configured, info / health depth bounded
- [ ] Micrometer metrics: registry present, auto-instrumentation enabled, tag cardinality bounded, custom metrics namespaced
- [ ] Tracing: Micrometer Tracing on Boot 3+ or Sleuth-migration flag, sampling explicit, propagation across `@Async` and outbound clients
- [ ] Messaging observability: Kafka / Rabbit / JMS listener observation, MDC propagation, queue lag metric
- [ ] Error tracker: starter wired, DSN externalized, PII scrubbed, MDC forwarded, sample rate explicit
- [ ] Findings name a Spring / Micrometer / Logback idiom - not "add observability"
- [ ] Library-level scope respected; infra concerns explicitly deferred to ops
- [ ] Depth honored: `quick` skipped tracing / messaging / error-tracker / SLI unless signals fired; `deep` ran SLI step
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered High > Medium > Low (omit if none)
- [ ] Report written via `review-report-writer`; confirmation printed

## Output Format

```markdown
## Spring Boot Observability Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Logging:** Logback + Logstash JSON | Logback JsonEncoder | log4j2 | other
**Metrics:** Micrometer + Prometheus | Micrometer + StatsD | none
**Tracing:** Micrometer Tracing (OTel) | Micrometer Tracing (Brave/Zipkin) | Sleuth (deprecated) | none
**Error Tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [count: High/Medium/Low]

## Findings

### High Impact
- **Location:** [file:line or config key]
- **Issue:** [name the idiom: missing MDC propagation across `@Async`, unbounded tag cardinality on `userId`, Actuator `*` exposure, etc.]
- **Impact:** [diagnosability / alertability / cost]
- **Fix:** [specific Spring / Micrometer / Logback change with code or YAML]

### Medium Impact
[Same structure]

### Low Impact / Quick Wins
[Same structure]

_Omit empty sections._

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Prioritized, each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting / dashboards / ops). Order: High > Medium > Low.

1. **[Implement]** [High] file:line - [one-line action]
2. **[Delegate]** [High] [scope: ops] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git from this workflow
- Reporting gaps without naming the idiom ("add metrics" vs "register `Counter` named `acme.orders.placed` with bounded tags")
- Generic observability advice when a Spring starter exists (say "add `spring-boot-starter-actuator`", not "expose health endpoints")
- Reviewing infra concerns (Datadog, Grafana, log forwarder, on-call) - belong to ops review
- Treating high tag cardinality (`userId`, `orderId`) as acceptable
- Leaving `*` in `management.endpoints.web.exposure.include` for prod
- Suggesting `log.info("...", e)` (loses stack) instead of `log.error("...", e)`
- Approving Sleuth on Boot 3 - migrate to Micrometer Tracing
- Approving `WebSecurityConfigurerAdapter` patterns gating Actuator - use `SecurityFilterChain`
