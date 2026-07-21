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

Spring-aware observability review at the library / starter level: Logback / Logstash JSON, MDC, Spring Boot Actuator, Micrometer, Micrometer Tracing / OTel, listener interceptors, error-tracker starters. Infra concerns (Datadog dashboards, Sentry org settings, log forwarder config) stay out of scope.

Stack-specific delegate of `task-code-review-observability` for Java / Spring Boot.

## When to Use

- Spring Boot PR with observability regressions or new instrumentation gaps
- Pre-release observability check for a new service / major feature
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
| `standard` | Default                                                       | All steps except 11                                  |
| `deep`     | Pre-release of critical service or post-incident review       | All steps + SLI/SLO suggestions                      |

Default: `standard`. Post-incident and pre-release-of-critical-service invocations run `deep` without needing a flag (the Depth table's When column authorizes it).

## Invocation

| Invocation                                   | Meaning                                                       |
| -------------------------------------------- | ------------------------------------------------------------- |
| `/task-spring-review-observability`          | Current branch vs base; fails fast on trunk                   |
| `/task-spring-review-observability <branch>` | `<branch>` vs base (3-dot diff)                               |
| `/task-spring-review-observability pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)         |

**Whole-service audit** (post-incident or pre-release with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-12 against the full instrumentation surface at `HEAD` (no diff scoping; findings cite current code). The report is always `mode: full`; `round` via Step 12's lookup.

When invoked as a subagent, the parent passes the precondition handle + pre-read diff and commit log; Step 3 is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a Spring-aware parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review-observability`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with parent-supplied artifacts. On fail-fast on trunk, switch to the whole-service audit path (Invocation section); on any other fail-fast, surface the message verbatim and stop. No state-changing git.

### Step 4 - Read the Instrumentation Surface

Open the files that wire observability so findings cite real lines, even when the diff only touches one surface (a missing wire is the finding):

- `logback-spring.xml` (+ per-profile) - encoder type, MDC patterns, masking
- `application.yml` (+ per-profile) - `management.*`, `logging.*`, `spring.kafka.listener.observation-enabled`, `management.tracing.*`
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-actuator`, `micrometer-registry-prometheus`, `micrometer-tracing-bridge-otel`, error-tracker starters
- Changed files (whole-service audit: all files) using `MeterRegistry`, `Counter`, `Timer`, `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@Async`, `@Scheduled`, or `MDC`

### Step 5 - Structured Logging

- [ ] **JSON in prod** - `LogstashEncoder` or Logback 1.5+ `JsonEncoder`. No raw text logs in prod paths
- [ ] **MDC correlation** - `traceId`, `spanId`, `requestId`, plus business IDs (`orderId`, `tenantId`, `userId` when authenticated) put in a request-boundary filter and cleared in `finally`. Non-JSON patterns include `%X{traceId}` / `%X{spanId}`
- [ ] **Sensitive-field masking** - encoder masks `password`, `token`, `authorization`, `creditCard`, `ssn`, `apiKey`; DTOs use `@JsonIgnore` on the same fields so `log.info("payload={}", dto)` cannot leak via Jackson
- [ ] **Responsible payloads** - no JPA-entity serialization in log args (lazy-load + PII); no HTTP body logging on prod profiles (`RestClient` / `WebClient` interceptors gated to non-prod or redacted)
- [ ] **Levels and form** - `error` actionable, `warn` recoverable, `info` state transitions, `debug` verbose; parameterized only (`log.info("processing order={}", id)`), no string concat or `String.format`; hot loops use `log.atDebug()` or sampling
- [ ] **Async appenders** for high volume with an explicit queue-full policy

### Step 6 - Spring Boot Actuator

- [ ] **`spring-boot-starter-actuator`** present (flag if absent in a service that warrants observability)
- [ ] **Exposure minimal in prod** - typically `health, info, metrics, prometheus` (+ `loggers` only if dynamic level change is needed). Never `*` in prod
- [ ] **Sensitive endpoints gated** - `env`, `heapdump`, `threaddump`, `mappings`, `configprops`, `loggers` require auth via `management.endpoint.<name>.access` or a dedicated `SecurityFilterChain` for `/actuator/**` (no `WebSecurityConfigurerAdapter` on Boot 3)
- [ ] **Health depth** - `management.endpoint.health.show-details: when-authorized`, not `always`
- [ ] **Liveness vs readiness probes** - `management.endpoint.health.probes.enabled: true`; liveness depends on JVM/app only, readiness reflects ability to serve (DB, caches warmed)
- [ ] **`info` endpoint** - build + git enabled, no env-var or secret leakage
- [ ] **`management.server.port`** isolated from the main port when prod network policy requires it

### Step 7 - Micrometer Metrics

- [ ] **Registry present** - `micrometer-registry-prometheus` (or equivalent); `/actuator/prometheus` exposed
- [ ] **Auto-instrumentation enabled** - `http.server.requests`, `hikaricp.*`, `hibernate.*` (`generate_statistics=true` non-prod), `jvm.*`, `tomcat.*`
- [ ] **Custom metrics namespaced** - `acme.orders.placed`, `acme.payments.failed`; `Counter` counts, `Timer` durations, `Gauge` instantaneous, `DistributionSummary` histograms
- [ ] **Tag cardinality bounded.** Reject:
  - **Unbounded identifiers** - `userId`, `orderId`, `paymentId`, `requestId`, `traceId` (belong on traces / logs)
  - **Continuous numerics** - `amount`, `latency_ms`, `payload_size` (use `DistributionSummary`)
  - **Free text** - error messages, raw paths with embedded IDs (normalize `/orders/42` to `/orders/{id}`)
  Allowed: bounded enums (`status`, `tenant_tier`, `region`, `error_code`)
- [ ] **`http.server.requests` URI templating** - tag is the route template, not the resolved path. Custom HTTP timers use `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE`
- [ ] **`@Timed`** on hot paths; `histogram = true` only when latency distribution is required
- [ ] **`MeterFilter`** trims unused / high-cardinality series
- [ ] **No meter registration in hot loops** - cache the `Counter` / `Timer` in a `final` field; `Counter.builder(...).register(...)` creates each call

### Step 8 - Distributed Tracing

- [ ] **Tracing bridge configured** - `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp`, or `micrometer-tracing-bridge-brave` for Zipkin. Boot 2.x Sleuth flagged for migration
- [ ] **Sampling explicit per env** - `management.tracing.sampling.probability` (e.g., `0.1` prod, `1.0` staging); never left at default
- [ ] **`Observation` API** for custom spans (`Observation.start("process-order", registry)`) over manual span management
- [ ] **`traceparent` propagation** - `RestClient` / `WebClient` / Feign auto-instrumented; manual `OkHttpClient` / `HttpClient` flagged for missing interceptor
- [ ] **Cross-thread context** - `ContextSnapshot` / `TaskDecorator` propagates trace across `@Async` and Virtual Thread boundaries (a missing decorator is *one* finding - Step 9's `@Async` decoration row owns it; here only verify trace continuity)
- [ ] **DB span enrichment** non-prod via `p6spy` / `datasource-proxy`
- [ ] **Not over-granular** - no `Observation` around a method whose only work is a JDBC call already spanned

### Step 9 - Async / Messaging Observability

- [ ] **Kafka** - `spring.kafka.listener.observation-enabled: true` (Boot 3+) bridges producer trace context
- [ ] **RabbitMQ** - `spring.rabbitmq.listener.simple.observation-enabled: true`
- [ ] **Consumer MDC propagation** - filter / aspect copies `traceId`, `userId`, `tenantId` from message headers and clears in `finally`
- [ ] **Listener metrics** - per-topic `Timer` for handle latency, `Counter` for retries / DLT, queue / partition lag exposed
- [ ] **`@Async` decoration** - `ContextPropagatingTaskDecorator` (or custom `TaskDecorator`) preserves MDC, security, trace
- [ ] **`@Scheduled` instrumentation** - per-job `Observation` and duration timer; missed-execution alertable

### Step 10 - Error Tracking

- [ ] **Boot starter wired** - `sentry-spring-boot-starter-jakarta`, `honeybadger`, or `rollbar-spring-boot-starter`
- [ ] **Secrets externalized** - DSN / API key in env var or Vault, never `application.yml`
- [ ] **Release / env tags** from build metadata
- [ ] **PII off in prod** - `sentry.send-default-pii: false`; explicit breadcrumb allowlist
- [ ] **MDC forwarded** - error event includes `traceId`, `userId`, `tenantId`
- [ ] **Sample rate explicit per env** - `sentry.traces-sample-rate`, `profiles-sample-rate`; not `1.0` in prod
- [ ] **Ignored exceptions documented** - each `sentry.ignored-exceptions-for-type` entry has a comment (e.g., `OptimisticLockException` when retry handles it)
- [ ] **`@RestControllerAdvice`** captures the original exception before mapping it to a response DTO

### Step 11 - Health Checks and SLIs (`deep` only)

- [ ] Critical user journeys have a Micrometer SLI (`http.server.requests` filtered to the journey URI: success rate, p95)
- [ ] DB / cache / broker / external APIs covered by `HealthIndicator`; custom indicators for non-Spring-managed dependencies
- [ ] SLO targets live in code (config or constants), not a free-floating Confluence page
- [ ] Synthetic probes call `/actuator/health/readiness`, not `/actuator/health`

### Step 12 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file - return the findings in this skill's Output Format for the parent to merge (the parent owns the report; `review-report-writer` rejects subagent writes and the parent passes no checkpoint fields). Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-observability` and these inputs: `branch`, `base_ref`, `base_sha`/`head_sha` (`git rev-parse` the refs Step 3 resolved; whole-service audit: both = `HEAD`), `scope: +obs`, `depth` (Depth table), `stack = java-spring-boot`, and always `mode: full` (this report type has no incremental analysis), with `round` via your own lookup of `review-observability-<branch>.md` (`review-precondition-check` keys prior checkpoints to `review-<branch>.md`, so its lookup never finds this report): exists with valid frontmatter -> increment its `round` and pass its `head_sha` as `prior_head_sha`; else `round: 1`. Write the file before ending; print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = the gap blocks incident diagnosis or exposes data (lost trace/MDC context across a hop, swallowed stack traces, PII in logs, unsecured Actuator). Medium = diagnosis possible but degraded or costly (unstructured logs, missing metrics on key flows, unbounded tag cardinality). Low = polish (naming, levels, encoder tuning). Intent labels follow severity: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on an incident-path surface; Low -> `[Recommend]`.

```markdown
## Spring Boot Observability Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Logging:** Logback + Logstash JSON | Logback JsonEncoder | log4j2 | plain-text pattern (unstructured) | other
**Metrics:** Micrometer + Prometheus | Micrometer + StatsD | Micrometer via Actuator - no export registry | none
**Tracing:** Micrometer Tracing (OTel) | Micrometer Tracing (Brave/Zipkin) | Sleuth (deprecated) | none
**Error Tracker:** Sentry | Honeybadger | Rollbar | none
**Overall:** Adequate | Gaps Found - [<N> High / <N> Medium / <N> Low]

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

_Repeat the four-line block per finding, numbered, within its severity section. Omit empty sections._

## Recommendations

[Structural improvements not tied to a specific finding]

## Next Steps

Prioritized, each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting / dashboards / ops). Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: ops] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed (or accepted from parent)
- [ ] Step 3 - precondition check ran (or handle received); diff + commit log read once and reused
- [ ] Step 4 - logback config, `application.yml`, build deps, and changed instrumentation files opened before checklists
- [ ] Step 5 - structured logging: JSON encoder, MDC, masking, payload discipline, levels, async appenders
- [ ] Step 6 - Actuator: exposure minimal, sensitive endpoints gated, probes, health depth, info safe
- [ ] Step 7 - Micrometer: registry, auto-instrumentation, namespaced custom metrics, tag cardinality bounded, no hot-loop registration
- [ ] Step 8 - tracing: bridge + sampling + propagation + cross-thread context
- [ ] Step 9 - messaging / async: listener observation flags, consumer MDC, listener metrics
- [ ] Step 10 - error tracker: starter, secrets externalized, PII off, MDC forwarded, sample rate explicit
- [ ] Step 11 - SLI / health indicators reviewed (`deep` only)
- [ ] Step 12 - standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git
- "Add observability" without naming the idiom (say "register `Counter` named `acme.orders.placed` with bounded tags")
- Generic advice when a Spring starter exists ("add `spring-boot-starter-actuator`", not "expose health endpoints")
- Reviewing infra (Datadog, Grafana, log forwarder, on-call) - belongs to ops review
- Treating `userId` / `orderId` / `paymentId` tags as acceptable
- Leaving `*` in `management.endpoints.web.exposure.include` for prod
- `log.info("...", e)` (loses stack) instead of `log.error("...", e)`
- Approving Sleuth on Boot 3 - migrate to Micrometer Tracing
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
