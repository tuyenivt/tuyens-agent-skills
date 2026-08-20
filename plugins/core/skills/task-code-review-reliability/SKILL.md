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

**Not for:** General review (`task-code-review`), performance optimization (`task-code-review-perf`), observability gaps (`task-code-review-observability`), security (`task-code-review-security`).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns *fast under normal load* (N+1, indexes, cache hit ratio). Reliability owns *correct and available under failure and saturation*. Connection-pool sizing: perf tunes for throughput; reliability verifies it is bounded and that exhaustion degrades gracefully. If the fix is "make it faster," it's perf; if the fix is "survive it being slow or down," it's reliability.
- **vs. Observability:** obs owns *can you see it* (a breaker-state metric, a fallback log). Reliability owns *does the mechanism exist and is it configured* (the breaker, the fallback). Report the mechanism gap here; report the visibility gap in obs.
- **vs. core correctness:** core Phase B owns happy-path logic and transaction-boundary correctness. Reliability owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - do not double-report; the umbrella synthesis dedups.

## Invocation

`/task-code-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full, and repo config may be read where a category directs it.

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
| React / Next.js      | `task-react-review-reliability`   |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework. Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow is unavailable (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5. Stacks with no matching plugin fall through to the Step 4 generic fallback.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and trace failure paths across service boundaries.

**Round gate (standalone only; on a sweep it runs after the sweep announcement, with `branch` = the trunk name).** Before reviewing, check `review-reliability-<branch>.md` (writer filename rules; the handle's `prior_checkpoint` is keyed to the general review report - never use it here). If it exists with valid frontmatter, its `head_sha` equals the current head, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior reliability review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent file -> `round: 1`, no `prior_head_sha`.

**Whole-service sweep** (reliability-debt pass with no feature branch): when the precondition check fails fast on trunk, do not stop - announce in one line (`Head is trunk - running a repo-wide reliability sweep at HEAD; findings cite current code.`), then skip the diff gate and review the reliability surface repo-wide at `HEAD`. The failed check emits no handle, so assemble the writer fields directly: `branch` = current branch short name, `base_ref` = `head_ref` = that name, `base_sha` = `head_sha` = `git rev-parse HEAD`. The verify step receives an empty `diff` on a sweep - findings verify against code at `HEAD` and attribute `Pre-existing`, noted as `(pre-existing)` on each finding's Location line. On a sweep, `Pre-existing` is the expected attribution, not a de-escalation trigger: severity maps to labels by the rubric below unchanged, and the tally reading `0 confirmed, N reattributed` is by design - reattribution is the sweep's confirmation. Sweep depth: `standard` reviews the reliability surface; `deep` additionally traces failure paths across service boundaries and renders the Map.

Cover the applicable categories. Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns and the per-stack resilience library (for stacks it does not list, apply the same patterns with the ecosystem's standard resilience libraries). Gate it: load `ops-resiliency` when the surface includes an external client, a fanning-out service, or breaker / retry / timeout config; skip it on a diff that is purely queue-system idempotency, transaction, or locking work with no synchronous dependency.

Gating skips atomic loads, never checklist rows. An atomic named inside a category loads when that category has surface. Every category below runs on this skill's own text regardless of which atomics loaded; a category goes N/A only when the diff has no matching surface (the Self-Check rule).

**Timeouts and deadlines.** Every external and internal call bounded; no unbounded waits. Chained calls share a timeout budget; deadline / cancellation context propagated downstream.

**Retries.** Exponential backoff with jitter, capped attempts. Retry only transient errors and only idempotent operations (or with an idempotency key). Per-request retry budget on chained paths to prevent amplification.

**Circuit breakers and bulkheads.** One monitored breaker per external dependency with explicit thresholds. Independent failure domains isolated by separate pools / bounded concurrency.

**Idempotency and delivery semantics.** Side-effecting operations (money, notifications, provisioning) accept an idempotency key with atomic dedup. Atomic DB-write-plus-publish uses a transactional outbox or post-commit dispatch, not an in-transaction dual write. Consumers are idempotent for at-least-once delivery; DLQ with bounded retry on poison messages. Use skill: `backend-idempotency`.

**Graceful degradation and fallbacks.** Every critical dependency has a defined fallback (cached / default / partial / queue-for-later / provider failover / fail-fast). Fallbacks log the original failure - never swallow it. Load shedding / backpressure on saturation instead of unbounded queueing.

**Resource exhaustion and saturation.** Connection, thread, and worker pools bounded and sized; queues, buffers, and in-memory accumulators bounded; no unbounded growth under load. Streaming for large payloads. When a pool's ceiling (DB max_connections, deployed concurrency) is not in the diff, read repo config; if still unknown, run the check anyway and state the assumption in the finding (e.g. `verify: max_connections unknown`) - never silently skip it.

**Failure-mode and blast radius (deep; when the change modifies or newly couples to a shared resource; or on a sweep whose surface includes one).** For each new or changed dependency, state what happens when it is down or slow, and what contains the cascade. Use skill: `failure-propagation-analysis` to trace shared-resource coupling and amplification loops. Outside a standalone deep run, this category's output lands in each finding's Failure Mode and Blast Radius fields; the Map section renders only standalone at deep.

**Consistency under partial failure.** For each cross-boundary write, confirm the failure path preserves integrity: no in-transaction dual write (DB-plus-broker) - use a transactional outbox or post-commit dispatch so a crash between the two cannot lose or duplicate the effect; every at-least-once consumer is idempotent on replay; each eventually-consistent boundary has a defined recovery path (DLQ with bounded retry, reconciliation, or safe re-run) rather than silent divergence. Flag any boundary whose staleness window or recovery path is undefined.

Every finding names the failure mode it enables (not just the missing pattern) and states the blast radius. One construct carrying several defects (a retry that is both non-idempotent and unbackedoff) publishes once at the worst severity, the Issue line naming each defect. **Severity:** High = an unbounded failure path or data-loss / corruption risk under a plausible failure (untimed hot call, uncapped or non-idempotent retry, in-tx dual write, unbounded queue); Medium = failure is bounded but recovery or containment is impaired (breaker absent on an external dependency, no fallback for a critical dependency, non-idempotent consumer); Low = hardening with no immediate failure path. Next Steps map severity to intent: High -> `[Must]`, Medium -> `[Recommend]`, Low -> `[Recommend]`.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and fill the Summary's `Findings verified:` line with its tally - the verify table itself stays internal. On round 2+, after verification, Use skill: `review-prior-findings-reconcile` with the prior report body and the diff (empty on a sweep - reconcile against code at `HEAD`); its table renders as `## Prior Round Reconciliation` between Findings and Next Steps. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch` (from the handle, or assembled directly on a sweep), the handle's refs, `base_sha` / `head_sha` via `git rev-parse`, `scope: +rel`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case language-framework, versions dropped, or `unknown`), `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## Findings` heading and its impact sections only - Summary, Prior Round Reconciliation, Next Steps, the deep Failure-Mode Map, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` (High) or `**[Recommend]**` (Medium/Low), before `Location`, and empty impact sections are omitted. Verify annotations (`_(pre-existing)_`, `(unverified ...)`) sit on the `Location` line (standalone only - subagent runs skip verification). A clean run in either mode returns `## Findings` containing `No reliability gaps found.`. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Reliability Review Summary

**Stack Detected:** [detected stack, or unknown] (generic fallback applied)
**Overall:** Resilient | Gaps Found - [High/Medium/Low counts]
**Findings verified:** [N] confirmed, [M] reattributed, [K] dropped

## Findings

### High Impact

**[Must]**
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
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched and installed, stack workflow ran with arguments forwarded; Steps 4-5 skipped (skipped entirely on subagent runs)
- [ ] Step 4: if no dispatch, round gate decided before any review; every applicable category (timeouts / retries / breakers / idempotency / degradation / saturation / failure-mode / consistency) covered (repo-wide at `HEAD` on a trunk sweep); every finding names the failure mode, blast radius, and a rubric-based severity; prior findings reconciled on round 2+
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Reliability findings without a named failure mode ("add a timeout" vs "unbounded call to payment-gateway blocks the request thread until the pool exhausts")
- Recommending retries on non-idempotent operations without an idempotency key
- Recommending a circuit breaker with no monitoring
- Overlapping into perf (throughput) or observability (visibility) - name the failure-survival gap, not the speed or the metric
- Emitting labels outside `[Must]` / `[Recommend]`
