---
name: regression-sink-asserter
description: Assert on async sink emissions for outside-in regression - Kafka, S3, SMTP, outbound webhooks, SQS. Reads sink declarations from services.yaml#sinks.
metadata:
  category: testing
  tags: [regression, async, kafka, s3, smtp, webhooks, sinks]
user-invocable: false
---

# Regression Sink Asserter

Drops the silent-out-of-scope deflection from `regression-scenario-author` Rule 9 when the flow's downstream effect is itself the contract under test. Kafka publishes, S3 uploads, SES emails, outbound webhook POSTs - the suite reads from the sink side and asserts.

## When to Use

- `services.yaml#sinks` declares the sink AND the flow has `sinks: [<sink-name>]` in `flows.yaml`.
- `task-regression-discover` enumerated async sinks via its post-step-2 prompt.

**Not for:** in-process side effects (use `rowExists` / HTTP response assertions per `regression-scenario-author` Rule 9 default).

## Rules

1. **Sink must be declared in inventory.** `services.yaml#sinks[].name` is the join key; flow's `sinks:` references it. Undeclared sink in a flow -> abort emission with `regression-sink-asserter: flow '<name>' references undeclared sink '<sink>'; add to services.yaml#sinks.`
2. **Consumer-side resources are run-id-scoped.** Kafka consumer group = `regression-<runId>-<scenario>`. Webhook receiver bind path = `/webhook/<runId>/<scenario>`. S3 prefix = `<runId>/`. Per-run isolation comes for free.
3. **Bounded `pollUntil` for sink reads.** Async sinks have batched export; default timeout 15s, 250ms interval. Override per flow via `sinks.<name>.pollTimeoutMs`.
4. **At-least-once is the default assertion.** Asserting on exactly-once requires a counter the producer already exposes - the suite never tries to enforce exactly-once from outside.
5. **Compose additions are emitted by this skill, not invented elsewhere.** Kafka -> add `kafka` + `kafka-ui` (optional) to compose under a `sinks` profile. SMTP -> add `mailhog`. Webhooks -> add `webhook-sink` (a small `node` listener committed under `.regression/fixtures/sinks/`). S3 -> add `minio` with default bucket creation.
6. **Sink containers participate in both compose profiles.** Same as databases - they have no service repo to swap between `local-build` and `pinned-images`.

## Patterns

### Sink kinds and assertion shape

| Sink kind | Helper signature | What it asserts |
| --- | --- | --- |
| `kafka-topic` | `consumeFrom(topic, { groupId, predicate, timeoutMs })` | At least one message matching predicate within timeout. Predicate gets parsed value. |
| `s3-bucket` | `objectExists(bucket, key, { timeoutMs })` | Object exists with non-zero size. Optionally `objectMatches(bucket, key, schema)`. |
| `webhook-out` | `webhookReceived(path, { timeoutMs, predicate })` | At least one POST to bind path with body matching predicate. |
| `smtp-out` | `mailReceived({ to, subjectRegex, bodyRegex, timeoutMs })` | At least one email matching the criteria via Mailhog HTTP API. |
| `sqs-queue` | `messageReceived(queueUrl, { groupId, predicate, timeoutMs })` | At least one message matching predicate within timeout. |

### Flow shape

```yaml
- name: order-emits-event
  kind: api
  sinks:                          # map form when a sink carries per-flow config
    orders-events:
      predicate: "msg.type === 'OrderCreated' && msg.orderId === orderId"
      pollTimeoutMs: 15000        # overrides the 15s default (Rule 3)
```

`sinks:` accepts a list of names (`sinks: [orders-events]`, see When to Use) when no per-flow config is needed, or a map keyed by sink name when a flow overrides `predicate` / `pollTimeoutMs`. Rule 3's `sinks.<name>.pollTimeoutMs` path refers to the map form.

### Scenario emission - Kafka example

```ts
import { consumeFrom } from "../../fixtures/sinks/kafka";

test("@smoke create order, emit OrderCreated", async ({ request }) => {
  const orderId = scopedId(SCENARIO, "o");
  await request.post("/orders", { data: { id: orderId, items: [...] } });

  await pollUntil(() => consumeFrom("orders-events", {
    groupId: `regression-${process.env.REGRESSION_RUN_ID}-${SCENARIO}`,
    predicate: msg => msg.type === "OrderCreated" && msg.orderId === orderId,
  }), { timeoutMs: 15_000 });
});
```

### Mailhog (SMTP) example

```ts
import { mailReceived } from "../../fixtures/sinks/smtp";

await pollUntil(() => mailReceived({
  to: scopedEmail(SCENARIO),
  subjectRegex: /Welcome to Acme/,
}), { timeoutMs: 10_000 });
```

The helper hits Mailhog's `GET /api/v2/messages` and filters.

### Compose snippet emission

When inventory declares `kind: kafka-topic`:

```yaml
kafka:
  image: confluentinc/cp-kafka@sha256:...
  environment:
    KAFKA_NODE_ID: 1
    KAFKA_PROCESS_ROLES: "broker,controller"
    # ... (KRaft mode; no Zookeeper)
  healthcheck:
    test: ["CMD-SHELL", "kafka-topics --bootstrap-server localhost:9092 --list >/dev/null"]
    interval: 5s
    retries: 30
  networks: [regression-net]
```

The user-declared sink's `target` (`kafka:orders-events`) is the broker:topic; the broker name (`kafka`) becomes the service. The skill creates the topic on broker startup via an init container.

### Asserting nothing emitted

`@negative` cases sometimes need "no message published". Reuse `consumeFrom(..., { timeoutMs: 2_000 })` and assert it returns `null` after timeout. Document this as a "negative-sink" pattern.

## Output Format

- `.regression/fixtures/sinks/<kind>/index.ts` (helpers, committed) per sink kind in use.
- `.regression/fixtures/sinks/webhook-sink/server.ts` (committed) for `webhook-out` sinks.
- Compose additions emitted via `regression-compose-build` consuming `services.yaml#sinks`.

## Avoid

- Cross-run sink contamination - always scope consumer group / webhook path / S3 prefix by `runId + scenario`.
- Synchronous sink reads (`getMessage` instead of `pollUntil(consumeFrom...)`).
- Asserting on exactly-once without a producer-side counter.
- Inventing sinks in the scenario without declaring in `services.yaml`.
- Embedding broker hostnames as literals - reference via `${VAR}` in `services.yaml`.
- Vendoring Kafka clients - declare `kafkajs` as a peer dep of `.regression/package.json`.
