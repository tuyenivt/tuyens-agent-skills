---
name: task-spring-review-observability
description: Spring Boot observability review for Micrometer metrics, Spring Boot Actuator, structured logging via Logback / Logstash encoder, MDC correlation, OpenTelemetry / Micrometer Tracing, `@KafkaListener` / `@RabbitListener` instrumentation, and error-tracker integration (Sentry / Honeybadger / Rollbar starters). Library-level focus, not infra. Use when reviewing a Spring PR for observability gaps, before releasing a new Spring service, or after an incident where Spring diagnosis was slow. Stack-specific override of task-code-review-observability for Java/Spring Boot.
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, observability, logging, metrics, tracing, actuator, micrometer, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spring Boot Observability Review

## Purpose

Spring-aware observability review that names Micrometer, Spring Boot Actuator, Logback / Logstash JSON encoder, MDC correlation, Micrometer Tracing (Boot 3+) / OpenTelemetry, `@KafkaListener` / `@RabbitListener` interceptors, and error-tracker Spring Boot starters directly instead of routing through the generic adapter. Focuses on whether Spring production behavior is visible, diagnosable, and alertable - at the _library and starter_ level. Infra-level concerns (Datadog SaaS dashboards, Sentry org settings, log forwarder config) stay out of scope.

This workflow is the stack-specific delegate of `task-code-review-observability` for Java/Spring Boot. The core workflow's contract (depth levels, output format) is preserved.

## When to Use

- Reviewing a Spring Boot PR for observability regressions or new instrumentation gaps
- Pre-release observability check for a new Spring service or major feature
- Post-incident review when Spring diagnosis was slow or evidence was missing
- Adopting Micrometer Tracing / OpenTelemetry / Logstash JSON encoder in a Spring Boot app
- Auditing async / messaging tracing and correlation across the request → `@Async` / listener boundary

**Not for:**

- General Spring Boot code review (use `task-spring-review`)
- Spring performance issues with a known bottleneck (use `task-spring-review-perf`)
- Active production incident investigation (use `/task-oncall-start`)
- Infra-level observability (Datadog dashboards, Grafana panels, alert rules, log forwarder config) - those are not in source code

## Depth Levels

| Depth      | When to Use                                                       | What Runs                                            |
| ---------- | ----------------------------------------------------------------- | ---------------------------------------------------- |
| `quick`    | Single endpoint, controller, or listener                          | Logging + Micrometer metrics check only              |
| `standard` | Default - full Spring observability review                        | All steps                                            |
| `deep`     | Pre-release of a critical Spring service, or post-incident review | All steps + SLI/SLO suggestions for Spring endpoints |

Default: `standard`.

## Invocation

Mirrors `task-code-review-observability`:

| Invocation                                   | Meaning                                                                                               |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-spring-review-observability`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-spring-review-observability <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-spring-review-observability pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-observability` or `task-spring-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Java / Spring Boot. If invoked as a subagent of a Spring-aware parent, accept the pre-confirmed stack and skip re-detection. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-review-observability` instead.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Structured Logging (Logback + Logstash encoder / SLF4J)

Inspect `src/main/resources/logback-spring.xml`, `application.yml` `logging.*` keys, and any `log.*` callsite in the diff:

- [ ] **Production logger emits JSON** - Logstash Logback encoder (`net.logstash.logback.encoder.LogstashEncoder`) or equivalent (Logback `JsonEncoder` in Logback 1.5+, `JsonLayout`). No raw text logs in production.
- [ ] **MDC correlation fields injected** in every log line: `traceId`, `spanId`, `requestId`, `userId` (when authenticated), `tenantId`, plus business correlation IDs (`orderId`, `invoiceId`). Use `MDC.put(...)` in a filter / interceptor at request boundary; clear in `finally`.
- [ ] **`logging.pattern.console` / `pattern.file`** include `%X{traceId}` and `%X{spanId}` placeholders so non-JSON local dev logs still show correlation
- [ ] **Sensitive-field masking**: Logback masking encoder or Logstash `maskMessageRegex` covers `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`. DTOs use `@JsonIgnore` for the same fields so `log.info("payload={}", dto)` cannot leak them via Jackson.
- [ ] **No `log.info("user={}", user)` / `log.info(entity.toString())`** that serializes a JPA entity (triggers lazy loads and may log PII / hashed passwords). Always log specific fields by ID.
- [ ] **Log levels used correctly**: `error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose diagnostics. Default root level `INFO` in prod; `DEBUG`/`TRACE` reserved for targeted packages
- [ ] **Parameterized logging only** (`log.info("processing order={}", orderId)`) - no string concatenation (`log.info("processing order=" + orderId)`); no `String.format(...)` inside logger calls
- [ ] **No log spam in hot loops** - `forEach` over large collections, scheduled jobs running every second, Kafka listener at high TPS must not log per-iteration; use `log.atDebug()` or sampled logging
- [ ] **Async appenders** (`AsyncAppender` or Logstash async TCP) configured for high-volume paths so logging is not on the request critical path; queue-full policy explicit (`neverBlock=true` for non-critical paths)

### Step 4 - Spring Boot Actuator

Inspect `application.yml` `management.*` keys and any custom `@Endpoint` / `HealthIndicator` / `InfoContributor`:

- [ ] **Actuator dependency present** (`spring-boot-starter-actuator`) - if absent in a service that warrants observability, flag it
- [ ] **`management.endpoints.web.exposure.include`** is minimal in prod: typically `health, info, metrics, prometheus` (and `loggers` if dynamic log-level change is needed). Never `*` in prod.
- [ ] **Sensitive endpoints gated**: `env`, `heapdump`, `threaddump`, `mappings`, `configprops`, `loggers` (when exposed) are auth-required (`management.endpoint.<name>.access` or behind a separate `SecurityFilterChain` for `/actuator/**`)
- [ ] **Health endpoint depth**: `/actuator/health` exposes high-level status only by default; `management.endpoint.health.show-details: when-authorized` (not `always` in prod). Custom `HealthIndicator` implementations report cleanly (no exception leak in the response body)
- [ ] **Liveness vs readiness**: Boot 2.3+ liveness/readiness groups configured for Kubernetes (`management.endpoint.health.probes.enabled: true`); `/actuator/health/liveness` does not depend on downstream services (only on the JVM/app itself); `/actuator/health/readiness` reflects whether the app is ready to serve (DB up, caches warmed)
- [ ] **`info` endpoint**: build, git, and version info exposed (`management.info.git.enabled`, `management.info.build.enabled`); does not leak environment variables or sensitive config
- [ ] **`management.server.port`** separated from main server port in prod when network isolation is required (cluster-internal access only)

### Step 5 - Micrometer Metrics

Inspect any `MeterRegistry`, `@Timed`, or `Counter` / `Timer` registration:

- [ ] **`micrometer-registry-prometheus`** (or equivalent) on the classpath; `/actuator/prometheus` exposed; scrape endpoint used by the org's metrics platform
- [ ] **Spring auto-instrumentation enabled**: HTTP server timer (`http.server.requests`), JDBC (HikariCP `hikaricp.*`), JPA (`hibernate.*` with `spring.jpa.properties.hibernate.generate_statistics=true` non-prod), JVM (`jvm.memory.*`, `jvm.gc.*`), Tomcat / Jetty / Undertow (`tomcat.*`)
- [ ] **Custom business metrics** named under a consistent namespace (`acme.orders.placed`, `acme.payments.failed`); units explicit (`Counter` for counts, `Timer` for durations, `Gauge` for instantaneous values, `DistributionSummary` for histograms)
- [ ] **Tag cardinality bounded**: tags do not include unbounded values (`userId`, `orderId`, `requestId`) - causes metric-cardinality blow-up. Allowed tag values are enums / known categories (`status`, `tenant_tier`, `region`)
- [ ] **`@Timed` on hot paths**: service methods on critical user journeys; `histogram = true` only when latency-distribution observability is required (cost: more series)
- [ ] **`MeterFilter`** trims unused metrics or denies high-cardinality dimensions where applicable
- [ ] **No metric registration in hot loop**: `meterRegistry.counter(...)` looked up per-request returns the cached counter, but `Counter.builder(...).register(...)` _creates_ on each call. Cache the builder result in a `final` field

### Step 6 - Distributed Tracing (Micrometer Tracing / OpenTelemetry)

Inspect tracing dependencies and bridge config:

- [ ] **Tracing bridge configured**: `io.micrometer:micrometer-tracing-bridge-otel` + `io.opentelemetry:opentelemetry-exporter-otlp` (preferred for OpenTelemetry pipelines), or `micrometer-tracing-bridge-brave` for Zipkin. Boot 3+ uses Micrometer Tracing; Boot 2.x apps using Sleuth flagged for migration
- [ ] **Sampling policy explicit**: `management.tracing.sampling.probability` set per env (e.g., `0.1` in prod, `1.0` in staging); not left at default
- [ ] **`Observation` API used** for custom spans (Boot 3+) - `Observation.start("process-order", registry)` over manual span management
- [ ] **`traceparent` propagation** validated on outbound: `RestClient` / `WebClient` / Feign auto-instrumented; manual `OkHttpClient` / `HttpClient` instances flagged for missing tracing interceptor
- [ ] **`@Async` and Virtual Thread tracing**: `ContextSnapshot` / `TaskDecorator` propagates trace context across thread boundaries; flag `@Async` methods that lose trace correlation
- [ ] **Database span enrichment**: `p6spy` or `datasource-proxy` attaches SQL to spans in non-prod; `query_log_tags`-equivalent (Hibernate `hibernate.session.events.log` or `StatementInspector`) attaches the originating service/method to slow queries
- [ ] **Spans not too granular**: do not wrap `getUserById` in an `Observation` if the JDBC span already covers it - over-instrumentation is noise

### Step 7 - Async / Messaging Observability

Inspect `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@Async`, `@Scheduled`:

- [ ] **Kafka observability enabled**: `spring.kafka.listener.observation-enabled: true` (Boot 3+) so consumer messages create spans bridging producer trace context
- [ ] **RabbitMQ observability**: `spring.rabbitmq.listener.simple.observation-enabled: true`; producer / consumer span linkage via `traceparent` header
- [ ] **MDC propagation across consumer threads**: filter / aspect copies `traceId`, `userId`, `tenantId` from message headers into MDC at handler entry; clears in `finally`
- [ ] **Listener metrics**: per-topic `Timer` for handle latency; `Counter` for retries / DLT; queue / partition lag metric exposed
- [ ] **`@Async` decoration**: `TaskDecorator` (or `ContextPropagatingTaskDecorator` from Micrometer Context Propagation) preserves MDC, security context, and trace context across the boundary
- [ ] **`@Scheduled` instrumentation**: each scheduled method emits an `Observation` so trace data exists; per-job duration timer; missed-execution alerting via metric

### Step 8 - Error Tracking (Sentry / Honeybadger / Rollbar starters)

Inspect Sentry / Honeybadger / Rollbar dependencies and config:

- [ ] **Boot starter** present (`sentry-spring-boot-starter-jakarta`, `honeybadger`, `rollbar-spring-boot-starter`) - integrates with `@RestControllerAdvice`, MDC, and Logback automatically
- [ ] **DSN / API key** in env var or Vault, not committed to `application.yml`
- [ ] **Release / environment tags** populated from build metadata (`sentry.release`, `sentry.environment`)
- [ ] **PII scrubbing on**: `sentry.send-default-pii: false` in prod; explicit allowlist of breadcrumb fields
- [ ] **MDC fields forwarded**: error event includes `traceId`, `userId`, `tenantId` so Sentry incidents link back to traces / users
- [ ] **Sample rate explicit**: `sentry.traces-sample-rate`, `sentry.profiles-sample-rate` per env; not `1.0` in prod for tracing
- [ ] **Ignored exceptions documented**: `sentry.ignored-exceptions-for-type` lists classes that should not page (e.g., `OptimisticLockException` when retry handles it); each ignore has a comment
- [ ] **`@RestControllerAdvice` maps exceptions to user-facing responses without losing the stack** - error tracker captures the original exception before the advice replaces it with a response DTO

### Step 9 - Health Checks and SLIs (deep depth only)

When invoked at `deep`, evaluate:

- [ ] Critical user journeys have at least one Micrometer SLI (`http.server.requests` filtered to the journey URI, success rate, p95 latency)
- [ ] DB / cache / message broker / external API health checked via `HealthIndicator` (Spring Boot auto-configures most); custom indicators for non-Spring-managed dependencies
- [ ] SLO targets documented in code (`@SLO`-style annotations or service README) - not a free-floating Confluence page
- [ ] Synthetic probes (k6 / Gatling) call `/actuator/health/readiness` not just `/actuator/health` - readiness reflects ability to serve

## Self-Check

- [ ] Stack confirmed as Java / Spring Boot (or accepted from parent dispatcher)
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained (skipped when invoked as a subagent - the parent already gated)
- [ ] Logback / SLF4J structured logging assessed: JSON encoder, MDC correlation, sensitive-field masking, log level discipline, parameterized logging
- [ ] Spring Boot Actuator config reviewed: exposure list minimal, sensitive endpoints gated, liveness/readiness probes configured, info / health depth bounded
- [ ] Micrometer metrics assessed: registry on classpath, auto-instrumentation enabled, tag cardinality bounded, custom metrics named under namespace
- [ ] Tracing bridge assessed: Boot 3+ Micrometer Tracing or Sleuth-migration-flag, sampling explicit, propagation across `@Async` and outbound clients
- [ ] Messaging observability assessed: Kafka / RabbitMQ / JMS listener observation, MDC propagation across consumer threads, queue lag metric
- [ ] Error tracker integration assessed: Boot starter wired, DSN externalized, PII scrubbed, MDC forwarded, sample rate explicit
- [ ] Findings name a Spring / Micrometer / Logback idiom directly - not "add observability"
- [ ] Library-level scope respected; infra-level concerns (Datadog dashboards, log forwarder config, alert rules) explicitly deferred to ops
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered High > Medium > Low

## Output Format

```markdown
## Spring Boot Observability Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Logging:** Logback + Logstash JSON encoder | Logback JsonEncoder | log4j2 | other
**Metrics:** Micrometer + Prometheus | Micrometer + StatsD | none
**Tracing:** Micrometer Tracing (OTel) | Micrometer Tracing (Brave/Zipkin) | Spring Cloud Sleuth (deprecated) | none
**Error Tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [count by impact: High/Medium/Low]

## Findings

### High Impact

- **Location:** [file:line or config key]
- **Issue:** [what is missing / wrong - name the Spring idiom: missing MDC propagation across `@Async`, unbounded tag cardinality on `userId`, Actuator `*` exposure, etc.]
- **Impact:** [diagnosability / alertability / cost cost]
- **Fix:** [specific Spring / Micrometer / Logback change with code or YAML example]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings._

## Recommendations

[Structural improvements not tied to a specific finding - e.g., "Add Logstash JSON encoder", "Migrate Sleuth → Micrometer Tracing", "Introduce `ContextPropagatingTaskDecorator` for `@Async`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting instrumentation, dashboard work, or ops collaboration). Order: High > Medium > Low Impact.

1. **[Implement]** [High] file:line - [one-line action, e.g., "Add `MDC.put(\"orderId\", id)` at OrderService#place entry; clear in `finally`"]
2. **[Delegate]** [High] [scope: ops] - [one-line action, e.g., "Wire `/actuator/prometheus` to org Prometheus scrape config"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reporting gaps without naming the Spring / Micrometer / Logback idiom ("add metrics" vs "register Micrometer `Counter` named `acme.orders.placed` with bounded tags")
- Recommending generic observability advice when a Spring starter or auto-config exists (say "add `spring-boot-starter-actuator`", not "expose health endpoints")
- Reviewing infra-level concerns (Datadog SaaS settings, Grafana alert rules, log forwarder config, on-call rotation) - those are not in source code and belong to ops review
- Treating high tag cardinality (`userId`, `orderId`) as acceptable - metric series cost compounds; require enum / category tags
- Leaving `*` in `management.endpoints.web.exposure.include` as acceptable in prod
- Suggesting `log.info("...", e)` (loses stack trace) instead of `log.error("...", e)` (preserves it)
- Approving Sleuth on Boot 3 - migrate to Micrometer Tracing
- Approving `WebSecurityConfigurerAdapter` patterns gating Actuator - removed in Spring Security 6, use `SecurityFilterChain`
