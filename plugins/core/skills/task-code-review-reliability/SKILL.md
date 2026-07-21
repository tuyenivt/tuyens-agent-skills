---
name: task-code-review-reliability
description: Reliability review entry point: timeouts, retries, circuit breakers, idempotency, graceful degradation, resource exhaustion. Detects stack and dispatches workflow.
metadata:
  category: review
  tags: [reliability, resilience, fault-tolerance, availability, circuit-breaker, idempotency, multi-stack, router]
  type: workflow
user-invocable: true
---

# Reliability Review (Router)

Detects the project stack and delegates to the matching stack-specific reliability review (`task-{stack}-review-reliability`). For unknown stacks, runs a minimal generic reliability review.

Reliability = behavior under failure and saturation - the unhappy path. It owns what happens when a dependency is slow or down, load spikes, or a process crashes mid-operation.

## When to Use

- Pre-release resilience pass on a service that calls external dependencies
- New or changed integration point (HTTP/gRPC client, queue consumer, scheduled job)
- Hardening after a near-miss or as recurring reliability debt review
- Data-integrity-under-failure check (dual writes, outbox, idempotency)

**Not for:** General review (`task-code-review`), performance optimization (`task-code-review-perf`), observability gaps (`task-code-review-observability`), security (`task-code-review-security`), a live incident happening now (oncall plugin `/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns *fast under normal load* (N+1, indexes, cache hit ratio). Reliability owns *correct and available under failure and saturation*. Connection-pool sizing: perf tunes for throughput; reliability verifies it is bounded and that exhaustion degrades gracefully. If the fix is "make it faster," it's perf; if the fix is "survive it being slow or down," it's reliability.
- **vs. Observability:** obs owns *can you see it* (a breaker-state metric, a fallback log). Reliability owns *does the mechanism exist and is it configured* (the breaker, the fallback). Report the mechanism gap here; report the visibility gap in obs.
- **vs. core correctness:** core Phase B owns happy-path logic and transaction-boundary correctness. Reliability owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - do not double-report; the umbrella synthesis dedups.

## Invocation

`/task-code-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack, precondition handle, and read-once diff/log: skip Steps 2-3, run Step 4 on the supplied diff, return findings per Output Format, and skip Step 5 - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                       |
| -------------------- | --------------------------------- |
| Java / Spring Boot   | `task-spring-review-reliability`  |
| Python               | `task-python-review-reliability`  |
| Ruby / Rails         | `task-rails-review-reliability`   |
| Node.js / TypeScript | `task-node-review-reliability`    |
| Go / Gin             | `task-go-review-reliability`      |
| Flutter / Dart       | `task-flutter-review-reliability` |
| React / Next.js      | `task-react-review-reliability`   |

Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow is unavailable (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5. Stacks with no matching plugin fall through to the Step 4 generic fallback.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and trace failure paths across service boundaries.

**Whole-service sweep** (reliability-debt pass with no feature branch): when the precondition check fails fast on trunk, do not stop - skip the diff gate and review the reliability surface repo-wide at `HEAD`; findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

Cover the applicable categories. Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns and the per-stack resilience library (for stacks it does not list, apply the same patterns with the ecosystem's standard resilience libraries).

**Timeouts and deadlines.** Every external and internal call bounded; no unbounded waits. Chained calls share a timeout budget; deadline / cancellation context propagated downstream.

**Retries.** Exponential backoff with jitter, capped attempts. Retry only transient errors and only idempotent operations (or with an idempotency key). Per-request retry budget on chained paths to prevent amplification.

**Circuit breakers and bulkheads.** One monitored breaker per external dependency with explicit thresholds. Independent failure domains isolated by separate pools / bounded concurrency.

**Idempotency and delivery semantics.** Side-effecting operations (money, notifications, provisioning) accept an idempotency key with atomic dedup. Atomic DB-write-plus-publish uses a transactional outbox or post-commit dispatch, not an in-transaction dual write. Consumers are idempotent for at-least-once delivery; DLQ with bounded retry on poison messages. Use skill: `backend-idempotency`.

**Graceful degradation and fallbacks.** Every critical dependency has a defined fallback (cached / default / partial / queue-for-later / provider failover / fail-fast). Fallbacks log the original failure - never swallow it. Load shedding / backpressure on saturation instead of unbounded queueing.

**Resource exhaustion and saturation.** Connection, thread, and worker pools bounded and sized; queues, buffers, and in-memory accumulators bounded; no unbounded growth under load. Streaming for large payloads.

**Failure-mode and blast radius (deep, or when the change touches a shared resource).** For each new or changed dependency, state what happens when it is down or slow, and what contains the cascade. Use skill: `failure-propagation-analysis` to trace shared-resource coupling and amplification loops. Use skill: `architecture-data-consistency` for consistency under partial failure and safe replay / recovery.

Every finding names the failure mode it enables (not just the missing pattern) and states the blast radius. **Severity:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (untimed hot call, uncapped or non-idempotent retry, in-tx dual write, unbounded queue); Medium = failure is bounded but recovery or containment is impaired (breaker absent where a timeout exists, no fallback for a critical dependency, non-idempotent consumer); Low = hardening with no immediate failure path. Next Steps map severity to intent: High -> `[Must]`, Medium -> `[Recommend]`, Low -> `[Recommend]`.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch` (from the handle), the handle's refs, `base_sha` / `head_sha` via `git rev-parse`, `scope: +rel`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case language-framework, or `unknown`), and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Reliability Review Summary

**Stack Detected:** [detected stack, or unknown] (generic fallback applied)
**Overall:** Resilient | Gaps Found - [High/Medium/Low counts]

## Findings

### High Impact

- **Location:** [file:line or integration point]
- **Issue:** [name the gap: unbounded external call, uncapped retry, non-idempotent retry, in-tx dual write, unbounded queue, etc.]
- **Failure Mode:** [what fails and how it propagates]
- **Blast Radius:** [what else is affected]
- **Fix:** [specific pattern and library for the detected stack]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. If all are omitted, state "No reliability gaps found." and omit Next Steps._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: platform] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend. Omit if none._
```

At `deep`, append a `## Failure-Mode and Blast-Radius Map` section before Next Steps - per new / changed dependency: what happens when it is down or slow, the shared resource on the propagation path, and the loop-breaker that contains it.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched and installed, stack workflow ran with arguments forwarded; Steps 4-5 skipped
- [ ] Step 4: if no dispatch, every applicable category (timeouts / retries / breakers / idempotency / degradation / saturation / failure-mode) covered (repo-wide at `HEAD` on a trunk sweep); every finding names the failure mode, blast radius, and a rubric-based severity
- [ ] Step 5: report written via `review-report-writer` with all required inputs (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Reliability findings without a named failure mode ("add a timeout" vs "unbounded call to payment-gateway blocks the request thread until the pool exhausts")
- Recommending retries on non-idempotent operations without an idempotency key
- Recommending a circuit breaker with no monitoring
- Overlapping into perf (throughput) or observability (visibility) - name the failure-survival gap, not the speed or the metric
- Mitigating a live incident here - route to the oncall plugin first
- Emitting labels outside `[Must]` / `[Recommend]`
