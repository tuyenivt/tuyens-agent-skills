---
name: regression-observability-check
description: Assert OTel spans, structured log lines, metric deltas during a flow. Opt-in via flow.checks tokens otel-span:<name>, log:<key>, metric:<name>.
metadata:
  category: testing
  tags: [regression, observability, otel, logs, metrics]
user-invocable: false
---

# Regression Observability Check

Catches regressions where a deploy silently drops a span, removes a structured log field, or stops incrementing a metric the SRE dashboard depends on. The instrumentation is part of the contract.

## When to Use

- Flow has `checks:` containing `otel-span:<name>` or `log:<key>` or `metric:<name>`.
- The user passes `--check otel-span:<name>` to `task-regression-scenario`.

## Rules

1. **Sink first, then assertion.** A scenario asserting on a span requires an OTLP collector / log aggregator / metrics scraper running in the compose project. The skill emits collector container additions for `regression-compose-build`; without them the assertion has no source of truth. Default collector: `otel/opentelemetry-collector-contrib` with file exporter -> `.regression/.cache/otel/<runId>.jsonl`.
2. **Service must be instrumented BY the user.** The skill does not add instrumentation to backends - that lives in the service repo. It asserts on already-emitted telemetry.
3. **Bounded read-after-write via `pollUntil`.** Telemetry export is async (default OTLP batch interval 5s). `pollUntil` with `timeoutMs: 10_000` is the only sanctioned waiting pattern.
4. **Span match by `(name, status.code, attributes-subset)`.** Trace ID is not asserted (it changes per run by design). Attribute subset assertion: required attributes must be present with the exact value; extra attributes are allowed.
5. **Log match by `(level >= INFO, message-regex, fields-subset)`.** DEBUG / TRACE assertions are forbidden - too noisy and prone to churn.
6. **Metric match by `(name, label-subset, delta-from-baseline)`.** Absolute values are forbidden (depend on warm-up); only deltas.

## Patterns

### `checks:` syntax

```yaml
- name: order-create
  checks:
    - otel-span:POST /orders          # name match
    - otel-span:POST /orders {http.status_code=201}    # name + attr subset
    - log:order.confirmed {orderId, tenantId}          # message contains "order.confirmed", required fields
    - metric:orders_created_total {tenant=acme-test-*} >= 1   # delta lower bound
```

### Helper signatures

```ts
import { findSpan, findLog, metricDelta } from "../../fixtures/otel";
// All return Promise<boolean>; designed to be wrapped in pollUntil.

await pollUntil(() => findSpan({
  name: "POST /orders",
  status: "ok",
  attrs: { "http.status_code": 201 },
}), { timeoutMs: 10_000 });

await pollUntil(() => findLog({
  levelAtLeast: "INFO",
  messageRegex: /order\.confirmed/,
  fields: { orderId: scopedId(SCENARIO, "o") },
}), { timeoutMs: 10_000 });

expect(await metricDelta("orders_created_total", { tenant: scopedId(SCENARIO, "t") })).toBeGreaterThanOrEqual(1);
```

### Collector compose snippet

`regression-compose-build` adds, when any flow has an observability check:

```yaml
otel-collector:
  image: otel/opentelemetry-collector-contrib@sha256:...
  command: ["--config=/etc/otelcol/config.yaml"]
  volumes:
    - ./fixtures/otel/collector-config.yaml:/etc/otelcol/config.yaml:ro
    - ./.cache/otel:/data
  healthcheck: { test: ["CMD-SHELL", "test -e /data/ready"], interval: 2s, retries: 30 }
  networks: [regression-net]
```

The collector writes received telemetry to `.cache/otel/<runId>.jsonl`; the helpers read this file.

### Service-side wiring

User adds `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` to the backend service's `env:` in `services.yaml`. The skill surfaces this requirement in the discover report when a flow opts into observability checks but the backend has no `OTEL_EXPORTER_OTLP_ENDPOINT`.

### Why deltas, not absolutes

Metrics survive the seed phase: a fresh DB has zero `orders_created_total`, but a previous flow in the same run may have already incremented it. Delta-from-baseline (captured before the scenario starts) is the only stable assertion.

## Output Format

- `.regression/.cache/otel/<runId>.jsonl` (gitignored) - collector output.
- Scenario assertions on `findSpan` / `findLog` / `metricDelta` helpers.
- `regression-compose-build` adds an `otel-collector` service when at least one flow opts in.

## Avoid

- Asserting on trace IDs (change per run).
- DEBUG / TRACE log assertions (noisy, churn-prone).
- Absolute metric values (warm-up dependent).
- Adding instrumentation in the test repo - it belongs in the service repo.
- Polling without `pollUntil` - exporter latency makes a single read flake.
- Hardcoding the collector endpoint - reference via `${VAR}` in `services.yaml`.
