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
- **vs. Observability:** obs owns *can you see it* - dashboards, alerts, and log or trace quality around a mechanism. Reliability owns *does the mechanism exist and is it configured* (the breaker, the fallback), including the breaker's monitoring and the fallback's logging of its original failure (`ops-resiliency`'s `breaker monitoring` / `fallback logging`); report those here and every other visibility gap in obs.
- **vs. core correctness:** core Phase B owns happy-path logic and transaction-boundary correctness. Reliability owns partial failure, dependency failure, and saturation. Idempotency sits at the seam - do not double-report; the umbrella synthesis dedups.

## Invocation

`/task-code-review-reliability [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies: load behavioral-principles unless the spawning prompt inlined its whole Rules section and the disclosure block), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format (a defect in a file the diff does not touch is drafted plain - the parent's verify attributes it), and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

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
| React / Next.js      | `task-react-review-reliability`   | `react`  |

Dispatch keys on the detection's primary `Language` / `Framework` pair; a secondary stack in `Additional` never dispatches. A row matches when both its language and its framework match - a trailing version never blocks a match (`Spring Boot 4.1`) and the Ruby row matches `Rails` or `Ruby on Rails`, while another language or framework does (Kotlin / Spring Boot and Java / Micronaut take the fallback). Python matches under any framework; Node.js / TypeScript matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or `unknown`; a Framework naming Next.js (`React (Next.js)`, `Next.js 16.3 (App Router)`) takes the React row, and every other frontend framework (Vite, CRA, React Router, Remix, Vue, Angular, Svelte) matches no row. Exactly one outcome follows, its one-line announcement printed in chat before anything else (Step 4's precondition prompts and the user's answers follow it) and never part of `report_body`:

- Matched and installed: `Dispatching to task-rails-review-reliability.` (substitute the target); invoke it with the arguments unchanged and stop - Steps 4-5 do not run.
- Matched, plugin not installed: `task-rails-review-reliability is provided by the ruby plugin, which is not installed - running the generic reliability review.` (substitute target and plugin); run Steps 4-5.
- No row: `No stack reliability workflow for <Language> / <Framework> - running the generic reliability review.`; run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with `argument` (the invocation's target, if any), `base` (from `--base`, if given), and `report_type: review-reliability` when running standalone (skip it when the parent supplied a handle); on a failure other than the trunk fail-fast below, surface its message verbatim and stop; on success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal). Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full and trace failure paths across service boundaries. A defect the diff did not introduce, found in that read, is drafted like any other and verification attributes it; a file the diff does not touch is read only to confirm what a finding depends on, and a defect in it is drafted only when the diff newly reaches it (on a sweep, every defect on the reliability surface is drafted). A requirement or acceptance criterion the diff's spec or commits name is evidence for a finding's Impact, never a finding by itself - criterion gaps belong to `task-code-review --req`.

**Whole-service sweep** (reliability-debt pass with no feature branch): when the precondition check fails fast because the head is a trunk, do not stop - announce in one line (`Head is trunk - running a repo-wide reliability sweep at <name>; findings cite current code.`, `<name>` = the trunk its message names), then skip the diff gate and review the reliability surface repo-wide at `<ref>`: the target itself when it resolves as `refs/remotes/<target>` (`origin/main`); else `<name>` when `refs/heads/<name>` exists (`heads/<name>` when a tag shares the name); else the `git for-each-ref --format='%(refname:short)' "refs/remotes/*/<name>"` match - on several, the remote the user chose at the precondition's remote prompt - every external client, queue producer or consumer, scheduled job, pool or worker configuration, and cross-boundary write under the application source tree, plus committed deploy config read for ceilings; when `<ref>` is not the checked-out branch, read files with `git show <ref>:<path>`. The failed check emits no handle, so the writer fields are `branch` = `<name>`, `base_ref` = `head_ref` = `<ref>`, and `base_sha` = `head_sha` = `git rev-parse <ref>`. Verify receives those refs and an empty `diff`: findings verify against code at `<ref>` and attribute `Pre-existing`, noted `_(pre-existing)_` as the first annotation group after each Location's `file:line` (an `Unverified` row carries only its `_(unverified: ...)_`). On a sweep, `Pre-existing` is the expected attribution, not a de-escalation trigger - the one exception to the published-label rule: labels come from severity by the rubric below, and the tally reading `0 confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, 0 resolved by diff)}` is by design. Sweep depth: `standard` reviews the reliability surface; `deep` also traces failure paths across service boundaries and renders the Map.

**Round gate (standalone only; on a sweep, after the sweep announcement).** The handle's `prior_checkpoint` is this lens's checkpoint (`review-reliability-<sanitized head_short_name>.md`) frontmatter (omitted from the handle when the file does not exist), or `legacy` when its frontmatter is missing, unparseable, or another lens's or branch's; a sweep has no handle, so read `review-reliability-<sanitized trunk name>.md` yourself (writer filename rules) under the same conditions. When it is a valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals this run's, and whose `depth` the requested depth does not exceed (`deep` exceeds `standard`), print `No new commits since prior reliability review.` and stop - no review, no report. Otherwise (a passing gate prints nothing) a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` and no `prior_head_sha` (Step 5 overwrites a legacy file). Then read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once (a sweep reads none).

Cover the applicable categories. Use skill: `ops-resiliency` for the canonical timeout / retry / breaker / bulkhead / fallback patterns and the per-stack resilience library (for stacks it does not list, apply its rules and tell the user to verify against the ecosystem's resilience-library docs - name no library the review does not know). Load it when the surface includes an external client, a fanning-out service, or breaker / retry / timeout config; skip it on a diff that is purely queue-system idempotency, transaction, or locking work with no synchronous dependency. Its `## Resiliency Assessment` and `backend-idempotency`'s `## Idempotency Assessment` stay internal: each gap entry becomes one finding here - `Missing:` names the Issue, `Risk:` feeds Failure Mode and Blast Radius, `Recommendation:` the Fix - re-rated on the severity rubric below. Location is the `file:line` of the integration point or operation the entry names; a chain gap (timeout budget, retry budget, retry owner) cites the entry hop's call site and names the other hops after it, and a `client ownership` gap cites the first call site and names the others.

Gating skips atomic loads, never checklist rows. An atomic named inside a category loads when that category has surface. Every category below runs on this skill's own text regardless of which atomics loaded; a category goes N/A only when the diff - or, on a sweep, the repo-wide surface - has no matching construct.

**Timeouts and deadlines.** Every external and internal call bounded; no unbounded waits. Chained calls share a timeout budget; deadline / cancellation context propagated downstream.

**Retries.** Exponential backoff with jitter, capped attempts. Retry only transient errors and only idempotent operations (or with an idempotency key). Per-request retry budget on chained paths to prevent amplification.

**Circuit breakers and bulkheads.** One monitored breaker per external dependency with explicit thresholds. Independent failure domains isolated by separate pools / bounded concurrency.

**Idempotency and delivery semantics.** Side-effecting operations (money, notifications, provisioning) require an idempotency key with atomic dedup - a financial or irreversible request without one is rejected, not accepted. Consumers are idempotent for at-least-once delivery; DLQ with bounded retry on poison messages. Use skill: `backend-idempotency`.

**Graceful degradation and fallbacks.** Every critical dependency has a defined fallback (cached / default / partial / queue-for-later / provider failover / fail-fast). Fallbacks log the original failure - never swallow it. Load shedding / backpressure on saturation instead of unbounded queueing.

**Resource exhaustion and saturation.** Connection, thread, and worker pools bounded and sized; queues, buffers, and in-memory accumulators bounded; no unbounded growth under load. Streaming for large payloads. When a pool's ceiling (DB max_connections, deployed concurrency) is not in the diff, read repo config; if still unknown, run the check anyway and mark the figure `(unverified)` in the finding. An external call made while a DB transaction holds its connection, a job enqueued before commit, and a missing lock timeout or statement timeout are reported here (a missing lock itself is outside this lens: an `out of lens` line, owner `task-code-review`, when it can corrupt data): `ops-resiliency` and `backend-idempotency` hand them to `backend-transaction-patterns`, which this lens does not load.

**Failure-mode and blast radius (at any depth when the change adds or changes a dependency, or modifies or newly couples to a shared resource, or on a sweep whose surface includes one).** For each new or changed dependency, state what happens when it is down or slow, and what contains the cascade. Use skill: `failure-propagation-analysis` in `what-if` mode (`**Mode:** what-if`) to trace shared-resource coupling and amplification loops. Its output lands in each finding's Failure Mode and Blast Radius fields, keeping every marker it emits (`(assumed)`, `predicted`, `(failed...)` and `(degraded: ...)`, `(unverified)`, `(suspected - <evidence>)`, `(branch <N><letter> only)`, `(response action)`, `consumers unenumerated`).

**Consistency under partial failure.** For each cross-boundary write, confirm the failure path preserves integrity: no in-transaction dual write (DB-plus-broker) - use a transactional outbox, which records the intent in the same transaction so a crash between commit and publish cannot lose the effect; post-commit dispatch is weaker (a crash after commit loses the message) and passes only where a reconciliation pass recovers it; every at-least-once consumer is idempotent on replay; each eventually-consistent boundary has a defined recovery path (DLQ with bounded retry, reconciliation, or safe re-run) rather than silent divergence. Flag any boundary whose staleness window or recovery path is undefined.

Every finding names the failure mode it enables (not just the missing pattern) and states the blast radius. One construct carrying several defects (a retry that is both non-idempotent and unbackedoff) publishes once at the worst severity, the Issue line naming each defect; each defect goes to verify as its own draft, and only the rows verify keeps merge, published at the first kept row's `file:line` with the highest kept `Label` and every kept row's distinct Annotation groups - provenance groups (`pre-existing`, `unverified`) first, then `mechanism` groups, each set in row order. **Severity**, rated by consequence as `ops-resiliency` and `backend-idempotency` rate it: High = an unbounded failure path or data-loss / corruption risk under a plausible failure (untimed hot call, uncapped retry, in-tx dual write, unbounded queue, a non-idempotent retry or consumer whose duplicate or lost effect is financial or irreversible); Medium = failure is bounded but recovery or containment is impaired (breaker absent on an external dependency, no fallback for a critical dependency, a non-idempotent retry or consumer whose duplicate is a recoverable write); Low = hardening with no immediate failure path. Severity sets the initial intent: High -> `[Must]`, Medium and Low -> `[Recommend]`; where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one (the sweep is the sole carve-out).

**Verify findings (standalone only).** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line` (a `no cite` row - its cell a bare file path or a construct name, not `path:line` - publishes at `<path>:1` of that file when the cell is a path, else of the touched file whose hunk raised it (on a sweep, the file whose read raised it), keeping `_(unverified: no cite)_`; never a directory or a bare construct name - this `path:line` form replaces verify's bare-path heading, since reconcile parses only `path:line`), `Label`, and `Annotation` columns (on a sweep, labels come from severity). The Summary's `Findings verified:` line is the atomic's Summary form of its tally, which counts its table only; the verify table stays internal.

**Reconcile (round 2+, standalone only).** After verification, project the prior report (the file at `report_path`) into reconcile's parse shape: a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding - the label from its label line (with none, the label its impact section maps to under this lens's rule), the bare `file:line` prefix of its Location line, then its annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`; a label line's `_(carried from round <N>)_` follows as its own group) - each followed by an `Issue:` line with its Issue text. Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff -M --name-status <base_ref>...<head_ref>`, and `head_sha`; its output (table, any note lines, tally) renders verbatim as `## Prior Round Reconciliation`. A sweep supplies no diff or name-status, and reconcile's touch states are defined against a range, so a sweep skips reconcile and builds that section from its own repo-wide pass, in reconcile's Output Format (same columns, prior labels and citations verbatim, then its tally line): re-derived -> `Still open`, site read and smell absent -> `Addressed`, file gone or a `[Praise]` row -> `Obsolete`, site not reached -> `Needs re-check`. A `Still open` or `Needs re-check` row this round's pass did not re-derive publishes in its prior impact section at its prior label - `[Blocker]`, `[High]`, `[Critical]` map to `[Must]`, any other label outside `[Must]` / `[Recommend]` to `[Recommend]`, and `[Praise]` is never carried - noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label line's label, its Location the right side of reconcile's cell when that cell extends the prior cite with ` -> <new path>:<line>` (reconcile's rename form), else the prior `file:line`, its prior annotations kept except a prior `_(carried from round ...)_`, which this note replaces; its other block lines are copied from the prior report. A row this round re-derives - this round's pass drafted a finding on the same construct - publishes once, as this round's finding. The table keeps prior labels and citations verbatim.

### Step 5 - Write Report

Standalone only. Use skill: `review-report-writer` with `report_type: review-reliability`, `report_body`, `branch` (the handle's `head_short_name`, or the sweep's trunk name), `base_ref` / `head_ref` from the handle (the sweep's `<ref>`), `base_sha` / `head_sha` from Step 4, `scope: +rel`, `depth` (default `standard`), `stack` (`<language>-<framework>` from `stack-detect`, versions dropped, lowercased, `#` written `sharp` and `+` written `p`, then each run of characters outside `[a-z0-9]` one `-`, leading and trailing `-` stripped (`python-fastapi`, `Vue (Nuxt)` on TypeScript -> `typescript-vue-nuxt`, `C#` / `Unity 6000.3.21f1` -> `csharp-unity`); a segment reported `unknown` dropped; `unknown` when both are), `mode: full`, `round` plus `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a code fence. When Step 3 dispatched, the stack workflow owns the output.

Subagent runs return only `## Findings` with its impact sections and `out of lens` lines - no Summary, Map, reconciliation, Next Steps, or file - and their Locations carry no verify annotation; the parent verifies and reconciles its merged set once.

Each finding block opens with its label line, `**[Must]**` or `**[Recommend]**`, before `Location`. A finding sits in the section of its **impact**; its label line and Next Steps entry carry its **published label** - a `**[Recommend]**` inside High after verify de-escalated a pre-existing finding is correct (on a sweep, labels come from severity). Empty sections are omitted; within a section, `[Must]` first, then by `file:line`. Location is required (verify, the reconcile projection and Next Steps consume it); a multi-line construct cites its first line, and a two-site finding cites its first site and names the other after it. A standalone finding on a file absent from `git diff -M --name-status <base_ref>...<head_ref>` gets `_(pre-existing)_`, written first, unless its Annotation has a group opening `pre-existing` or `unverified` (a verify row whose Verdict is `Unverified`, a carried row keeping a prior `_(unverified: ...)_`, or a merged finding whose kept groups include one, gets no attribution) - the next round's reconcile reads it as provenance. A run with no new finding and no carried row returns `## Findings` containing `No reliability gaps found.` (any `out of lens` lines follow it) and omits Next Steps; carried rows with no new finding publish in their sections and Next Steps with no note.

An `out of lens` line closes `## Findings` - after whichever section is last, with no line and no placeholder when there is no such defect - for each defect outside this lens that would break the build, or corrupt or expose data, naming its owner (`task-code-review-<lens>` for a sibling lens, `task-code-review` when no lens owns it); anything else outside the lens is left to `task-code-review`. These lines count in no Summary tally; `Overall` counts every published finding, carried ones included.

At `deep` (standalone only), `## Failure-Mode and Blast-Radius Map` follows `## Findings`, before `## Prior Round Reconciliation` and Next Steps: one bullet per new or changed dependency - on a sweep, per external dependency on the reliability surface - in the form `<dependency>: down -> <effect>; slow -> <effect>; shared resource: <on the propagation path, or none>; contained by: <what stops propagation - the loop-breaker when a cycle exists - or none>`; the section is omitted when there is no such dependency.

Next Steps (standalone only): one entry per published finding, `[Must]` first, then by `file:line`. `[Implement]` when the fix is local to the change; `[Delegate]` with `[scope: <owner>]` when another owner (platform, infra, a dependency) must act. Either tag takes either label, and both keep the `file:line`.

Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Reliability Review Summary

- **Stack:** [`<Language> / <Framework>` as stack-detect's Stack slot renders it, versions kept as detected (`Python 3.12 / FastAPI 0.115`)] (generic fallback: no stack workflow | generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Overall:** Resilient | Gaps Found - <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Findings verified:** [`review-finding-verify`'s Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## Findings

### High Impact

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line, then the component or boundary when that helps]{ the verify Annotation groups, standalone only}
- **Issue:** [name the gap: unbounded external call, uncapped retry, non-idempotent retry, in-tx dual write, unbounded queue, etc.; several defects on one construct are listed `;`-separated]
- **Failure Mode:** [what fails and how it propagates]
- **Blast Radius:** [what else is affected]
- **Fix:** [specific pattern and library for the detected stack; for a stack `ops-resiliency` does not list, the pattern plus "verify against <ecosystem>'s resilience-library docs"]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

- **out of lens:** file:line - [the defect in one sentence] - owner: [`task-code-review-<lens>` or `task-code-review`]   {one per such defect}

## Failure-Mode and Blast-Radius Map   {deep standalone only, when a dependency qualifies}

- [dependency]: down -> [effect]; slow -> [effect]; shared resource: [resource or none]; contained by: [what stops propagation, or none]

## Prior Round Reconciliation   {round 2+ standalone runs only}

[reconcile's output verbatim - table, any note lines, tally; on a sweep, the table and tally built from the sweep-versus-prior comparison]

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: platform] - [one-line action]
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: exactly one announcement printed before any output; on dispatch the arguments were forwarded and Steps 4-5 skipped (skipped entirely on subagent runs)
- [ ] Step 4: precondition called with `argument` / `base` / `report_type`, a trunk fail-fast converted to a sweep at the named trunk; SHAs captured and the round gate decided (head, base and depth compared) before the diff was read; every applicable category covered (repo-wide on a sweep); every finding names the failure mode, blast radius, and a rubric-based severity; qualifying `out of lens` lines emitted; findings published with verify's `file:line`, `Label`, `Annotation` (sweep labels from severity); round 2+ prior findings projected, reconciled (or compared directly on a sweep), and carried; precondition, SHA capture, gate, verify and reconcile skipped on subagent runs
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure other than the trunk fail-fast surfaced verbatim with no report written (standalone fallback only)

## Avoid

- Writing a report when invoked as a subagent - the parent owns it
- Reliability findings without a named failure mode ("add a timeout" vs "unbounded call to payment-gateway blocks the request thread until the pool exhausts")
- Recommending retries on non-idempotent operations without an idempotency key
- Recommending a circuit breaker with no monitoring
- Overlapping into perf (throughput) or observability (visibility) - name the failure-survival gap, not the speed or the metric
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
