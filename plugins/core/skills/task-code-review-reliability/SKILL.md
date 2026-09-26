---
name: task-code-review-reliability
description: Reliability review entry point: timeouts, retries, circuit breakers, idempotency, degradation, saturation. Detects stack and dispatches workflow.
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
- **vs. Observability:** obs owns *can you see it* (a breaker-state metric, a fallback log). Reliability owns *does the mechanism exist and is it configured* (the breaker, the fallback). Report the mechanism gap here; report the visibility gap in obs. Monitoring on a breaker, and a fallback logging its original failure, are part of the mechanism - they belong here, not in obs.
- **vs. core correctness:** core Phase B owns happy-path logic and transaction-boundary correctness. Reliability owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - do not double-report; the umbrella synthesis dedups.

## Invocation

`/task-code-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full; repo config may be read at any depth where a category directs it.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                       | Plugin   |
| -------------------- | --------------------------------- | -------- |
| Java / Spring Boot   | `task-spring-review-reliability`  | `java`   |
| Python               | `task-python-review-reliability`  | `python` |
| Ruby / Rails         | `task-rails-review-reliability`   | `ruby`   |
| Node.js / TypeScript | `task-node-review-reliability`    | `node`   |
| Go / Gin             | `task-go-review-reliability`      | `go`     |
| React / Next.js | `task-react-review-reliability` | `react`  |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework; the Node.js / TypeScript row matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or none; a Framework naming Next.js takes the React row: `React (Next.js)` from detection or a declared value such as `Next.js 16.3 (App Router)`. Any other React framework (Vite, CRA, React Router, Remix) and any other frontend framework (Vue, Angular, Svelte) match no row. Dispatch keys on the detection's primary `Language`/`Framework` pair; a secondary stack in `Additional` never dispatches. Announce the dispatch in one line (`Dispatching to task-rails-review-reliability.` - substitute the target), forward the arguments unchanged, and stop. **If matched, skip Steps 4-5.** If the matched workflow is unavailable (stack plugin not installed), announce it in one line before Step 4 (`task-rails-review-reliability is provided by the ruby plugin, which is not installed - running the generic reliability review.` - substitute the row's target and plugin), then run Steps 4-5. A detected stack matching no row at all falls through to the Step 4 generic fallback - announce it in one line (`No stack reliability workflow for <stack> - running the generic reliability review.`, `<stack>` = the detection's Language / Framework pair), then run it.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with the invocation's target, any `--base` override, and `report_type: review-reliability` when running standalone (skip if the parent supplied a handle); on a failure other than the trunk fail-fast below, surface its message verbatim and stop. Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and trace failure paths across service boundaries.

**Round gate (standalone only; on a sweep it runs after the sweep announcement).** Before reviewing, decide the round from the handle: with `report_type: review-reliability` passed, its `report_path` is this lens's checkpoint (`review-reliability-<sanitized head_short_name>.md`) and its `prior_checkpoint` is that file's frontmatter - or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch. A sweep has no handle: read `review-reliability-<sanitized trunk name>.md` yourself (writer filename rules), treating it as `legacy` on the same conditions. If `prior_checkpoint` is a valid block, its `head_sha` equals the captured `head_sha`, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior reliability review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 5 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and commit log once.

**Whole-service sweep** (reliability-debt pass with no feature branch): when the precondition check fails fast on trunk, do not stop - announce in one line (`Head is trunk - running a repo-wide reliability sweep at HEAD; findings cite current code.`), then skip the diff gate and review the reliability surface repo-wide at `HEAD` - every external client, queue producer or consumer, scheduled job, pool or worker configuration, and cross-boundary write under the application source tree, plus committed deploy config read for ceilings. The failed check emits no handle, so assemble the writer fields directly: `branch` = current branch short name, `base_ref` = `head_ref` = that name, `base_sha` = `head_sha` = `git rev-parse HEAD`. The verify step receives those refs and an empty `diff` on a sweep - findings verify against code at `HEAD` and attribute `Pre-existing`, noted as `_(pre-existing)_` on each finding's Location line. On a sweep, `Pre-existing` is the expected attribution, not a de-escalation trigger: this is the one documented exception to the published-label rule in Output Format - the sweep supplies no diff, so every finding attributes `Pre-existing`, and labels come from severity by the rubric below unchanged. The tally reading `0 confirmed, N reattributed` is by design - reattribution is the sweep's confirmation. Sweep depth: `standard` reviews the reliability surface; `deep` additionally traces failure paths across service boundaries and renders the Map.

Cover the applicable categories. Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns and the per-stack resilience library (for stacks it does not list, apply its rules and tell the user to verify against the ecosystem's resilience-library docs - name no library the review does not know). Its `## Resiliency Assessment` and `backend-idempotency`'s `## Idempotency Assessment` stay internal: each gap entry becomes one finding here - Location is the `file:line` of the integration point or operation the entry names, `Missing:` names the Issue, `Risk:` feeds Failure Mode and Blast Radius, `Recommendation:` the Fix - re-rated on the severity rubric below. Gate it: load `ops-resiliency` when the surface includes an external client, a fanning-out service, or breaker / retry / timeout config; skip it on a diff that is purely queue-system idempotency, transaction, or locking work with no synchronous dependency.

Gating skips atomic loads, never checklist rows. An atomic named inside a category loads when that category has surface. Every category below runs on this skill's own text regardless of which atomics loaded; a category goes N/A only when the diff - or, on a sweep, the repo-wide surface at `HEAD` - has no matching construct (the Self-Check rule).

**Timeouts and deadlines.** Every external and internal call bounded; no unbounded waits. Chained calls share a timeout budget; deadline / cancellation context propagated downstream.

**Retries.** Exponential backoff with jitter, capped attempts. Retry only transient errors and only idempotent operations (or with an idempotency key). Per-request retry budget on chained paths to prevent amplification.

**Circuit breakers and bulkheads.** One monitored breaker per external dependency with explicit thresholds. Independent failure domains isolated by separate pools / bounded concurrency.

**Idempotency and delivery semantics.** Side-effecting operations (money, notifications, provisioning) require an idempotency key with atomic dedup - a financial or irreversible request without one is rejected, not accepted. Atomic DB-write-plus-publish uses a transactional outbox, not an in-transaction dual write; post-commit dispatch is weaker and passes only where a reconciliation pass recovers a crash between commit and publish. Consumers are idempotent for at-least-once delivery; DLQ with bounded retry on poison messages. Use skill: `backend-idempotency`.

**Graceful degradation and fallbacks.** Every critical dependency has a defined fallback (cached / default / partial / queue-for-later / provider failover / fail-fast). Fallbacks log the original failure - never swallow it. Load shedding / backpressure on saturation instead of unbounded queueing.

**Resource exhaustion and saturation.** Connection, thread, and worker pools bounded and sized; queues, buffers, and in-memory accumulators bounded; no unbounded growth under load. Streaming for large payloads. When a pool's ceiling (DB max_connections, deployed concurrency) is not in the diff, read repo config; if still unknown, run the check anyway and state the assumption in the finding (e.g. `verify: max_connections unknown`) - never silently skip it.

**Failure-mode and blast radius (at any depth when the change adds or changes a dependency, or modifies or newly couples to a shared resource, or on a sweep whose surface includes one).** For each new or changed dependency, state what happens when it is down or slow, and what contains the cascade. Use skill: `failure-propagation-analysis` in `what-if` mode (`**Mode:** what-if` - its Primary failure carries `(assumed)` and its Cascading components the `predicted` prefix) to trace shared-resource coupling and amplification loops. This category's output lands in each finding's Failure Mode and Blast Radius fields, keeping the `(assumed)` and `predicted` markers; the Map section renders only standalone at deep.

**Consistency under partial failure.** For each cross-boundary write, confirm the failure path preserves integrity: no in-transaction dual write (DB-plus-broker) - use a transactional outbox, which records the intent in the same transaction so a crash between commit and publish cannot lose the effect; post-commit dispatch is weaker (a crash after commit loses the message) and is acceptable only where a reconciliation pass recovers it; every at-least-once consumer is idempotent on replay; each eventually-consistent boundary has a defined recovery path (DLQ with bounded retry, reconciliation, or safe re-run) rather than silent divergence. Flag any boundary whose staleness window or recovery path is undefined.

Every finding names the failure mode it enables (not just the missing pattern) and states the blast radius. One construct carrying several defects (a retry that is both non-idempotent and unbackedoff) publishes once at the worst severity, the Issue line naming each defect. **Severity:** rated by consequence, as `ops-resiliency` and `backend-idempotency` rate it. High = an unbounded failure path or data-loss / corruption risk under a plausible failure (untimed hot call, uncapped retry, in-tx dual write, unbounded queue, a non-idempotent retry or consumer whose duplicate or lost effect is financial or irreversible); Medium = failure is bounded but recovery or containment is impaired (breaker absent on an external dependency, no fallback for a critical dependency, a non-idempotent retry or consumer whose duplicate is a recoverable write); Low = hardening with no immediate failure path. Severity assigns each finding an initial intent: High -> `[Must]`, Medium and Low -> `[Recommend]`; where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one (the sweep exception above is the sole carve-out). A defect outside this lens that would break the build, or corrupt or expose data, becomes an `out of lens` line (shape in Output Format). Next Steps carry each finding published label.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns (except on a sweep, where labels come from severity per Step 4); the Summary's `Findings verified:` line is the Summary form the atomic prescribes, filled from its tally (`<N> confirmed, <M> reattributed, <U> unverified, <K> dropped`, plus its false-positive/resolved split when emitted) - the verify table itself stays internal. On round 2+, after verification, re-project the prior report's findings (the file at `report_path`) into reconcile's parse shape - a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its label line (or, when the prior report wrote no label line, the label its severity section maps to under this lens's severity rule - reconcile's verbatim rule has nothing to preserve there) and the `file:line` prefix of its Location line (trailing component prose stays out of the heading), keeping a `_(pre-existing)_` annotation on the heading (reconcile splits untouched files on it; verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_`), with its Issue line as the smell - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, and `head_sha` (a sweep supplies no diff or name-status, and reconcile's touch states are defined against a range - so on a sweep skip reconcile: the repo-wide pass at `HEAD` re-derives every prior finding that still holds, so build `## Prior Round Reconciliation` from that comparison directly - re-derived -> `Still open`, site read and smell absent -> `Addressed`, file gone or a `[Praise]` row -> `Obsolete`, site not reached -> `Needs re-check`). Its table and tally render as `## Prior Round Reconciliation` between Findings and Next Steps; unresolved rows (`Still open`, `Needs re-check`) carry into their prior impact sections at their prior label, noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label on its label line, its prior Location annotation kept; the reconciliation table row and its Next Steps entry are its only other appearances. A prior label outside `[Must]` / `[Recommend]` (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in that table, which reconcile owns, and maps before it is published in a findings section: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; `[Suggestion]`, `[Nitpick]`, `[Question]`, `[Medium]`, `[Low]`, and any unrecognised label -> `[Recommend]`; `[Praise]` rows are never carried. A carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. The table preserves each prior citation exactly; the published finding carries the corrected `file:line` when verification found the prior cite stale. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch` (the handle's `head_short_name`, or the trunk name on a sweep), the handle's refs (or `base_ref` = `head_ref` = the trunk name on a sweep), `base_sha` / `head_sha` from Step 4, `pr_url` when the request text carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present, `scope: +rel`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case `<language>-<framework>`, versions dropped; drop a segment reported unknown; `unknown` only when detection failed entirely), `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## Findings` heading, its impact sections, and any `out of lens` lines only - Summary, Prior Round Reconciliation, Next Steps, the deep Failure-Mode Map, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` or `**[Recommend]**`, before `Location`, and empty impact sections are omitted. A finding sits in the section matching its **impact**; its label line and its Next Steps entry carry its **published label**. The two diverge whenever verification de-escalated a pre-existing finding - a `**[Recommend]**` inside a High section is correct, not a mismatch to fix (on a sweep, labels come from severity, per Step 4). A defect outside this lens that would break the build, or corrupt or expose data gets one `out of lens` line each at the end of `## Findings`, so it is not silently dropped; anything else outside the lens is left to `task-code-review`. Verify annotations (the Annotation column: `_(pre-existing)_`, `_(pre-existing; newly reachable via ...)_`, `_(unverified: ...)_`, `_(mechanism: ...)_`) sit on the `Location` line (standalone only - subagent runs skip verification). A clean run in either mode returns `## Findings` containing `No reliability gaps found.`. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Reliability Review Summary

- **Stack Detected:** [kebab-case `<language>-<framework>`, versions dropped - the same string passed as the writer `stack` input; or `unknown`] (generic fallback: no stack workflow) | (generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Overall:** Resilient | Gaps Found - <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Findings verified:** [from `review-finding-verify`'s tally, in its Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## Findings

### High Impact

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line - required, so verification, the reconcile projection and Next Steps can all consume it; name the component or boundary after it when that helps]{ the verify Annotation, standalone only}
- **Issue:** [name the gap: unbounded external call, uncapped retry, non-idempotent retry, in-tx dual write, unbounded queue, etc.; several defects on one construct are listed `;`-separated]
- **Failure Mode:** [what fails and how it propagates]
- **Blast Radius:** [what else is affected]
- **Fix:** [specific pattern and library for the detected stack]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. If all are omitted, state "No reliability gaps found." (before any `out of lens` line) and omit Next Steps._

- **out of lens:** file:line - [the defect in one sentence, and the lens that owns it]   {one per such defect, only when it would break the build or corrupt or expose data}


## Prior Round Reconciliation

[table and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; on a sweep, built directly from the sweep-versus-prior-report comparison; omit the section otherwise]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: platform] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, platform, infra). Order Must > Recommend. Omit if none._
```

At `deep`, append a `## Failure-Mode and Blast-Radius Map` section before Next Steps - per new / changed dependency - or, on a sweep, per external dependency on the reliability surface: what happens when it is down or slow, the shared resource on the propagation path, and the loop-breaker that contains it.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent runs: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched and installed, dispatch announced and stack workflow ran with arguments forwarded, Steps 4-5 skipped; if not installed or no row matched, the announcement printed and fallback ran (skipped entirely on subagent runs)
- [ ] Step 4: if no dispatch, SHAs captured; round gate decided from the handle (`report_type: review-reliability`), or from the checkpoint read directly on a sweep, before the diff was read; `out of lens` lines emitted for qualifying defects outside the lens; every applicable category (timeouts / retries / breakers / idempotency / degradation / saturation / failure-mode / consistency) covered (repo-wide at `HEAD` on a trunk sweep); every finding names the failure mode, blast radius, and a rubric-based severity; prior findings projected into reconcile's parse shape and reconciled on round 2+; the round gate, `review-finding-verify` (whose tally fills the `Findings verified:` Summary line) and reconciliation are standalone-only - subagent runs skip all three
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written - except the trunk fail-fast, which converts to a sweep rather than stopping (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Reliability findings without a named failure mode ("add a timeout" vs "unbounded call to payment-gateway blocks the request thread until the pool exhausts")
- Recommending retries on non-idempotent operations without an idempotency key
- Recommending a circuit breaker with no monitoring
- Overlapping into perf (throughput) or observability (visibility) - name the failure-survival gap, not the speed or the metric
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
