---
name: task-code-review
description: Code review entry point: risk, correctness, maintainability. Detects stack and dispatches to stack-specific review workflow.
metadata:
  category: review
  tags: [code-review, pull-request, risk-assessment, multi-stack, router]
  type: workflow
user-invocable: true
---

# Code Review (Router)

Detects the project stack and delegates to the matching stack-specific review workflow (`task-{stack}-review`). When no stack workflow is available, runs a minimal generic Phase 0-E review.

## When to Use

- PR review, pre-merge risk assessment, post-AI-generation quality gate.

**Not for:** New-system architecture, security-only audits (`task-code-review-security`), perf-only (`task-code-review-perf`), observability-only (`task-code-review-observability`), reliability-only (`task-code-review-reliability`).

## Invocation

`/task-code-review [<branch> | pr-<N>] [+perf | +sec | +obs | +rel | full | core-only] [standard | deep] [--base <branch>] [--req <path>]`

Scope flags combine (`+sec +perf`); `full` expands to all four. All flags are forwarded to the dispatched stack workflow. `--req <path>` names a requirement source for Phase 0 (ticket export, PRD, spec); without it Phase 0 falls back to whatever requirement is already in context.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Universal and unconditional.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to           |
| -------------------- | --------------------- |
| Java / Spring Boot   | `task-spring-review`  |
| Python               | `task-python-review`  |
| Ruby / Rails         | `task-rails-review`   |
| Node.js / TypeScript | `task-node-review`    |
| Go / Gin             | `task-go-review`      |
| React / Next.js / Vite | `task-react-review` |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework. Dispatch keys on the detection's primary `Language`/`Framework` pair; a secondary stack in `Additional` never dispatches. When the matched row's workflow resolves, announce the dispatch in one line (`Dispatching to task-rails-review.` - substitute the target name), then forward the user's invocation - re-issue the argument string unchanged (target ref, `--base`, `--req`, scope, depth), except `full`, which expands to `+perf +sec +obs +rel` because no stack umbrella accepts a bare `full` flag. The announcement is the router's only output; the detection block stays internal. The stack umbrella owns precondition checks, diff resolution, parallel sub-scope dispatch, and the final report. **If matched, stop. Skip Steps 4-5.**

If a row matches but the target skill does not resolve (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5 as a degraded generic review and note the degradation in the report. If no row matches the detected stack at all, announce that in one line (`No stack workflow for <stack> - running the generic review.`) and run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch)

Runs when no Step 3 row matched the detected stack, or the matched workflow is unavailable.

Use skill: `review-precondition-check` with the user's target argument (default target: current branch) and any `--base` override. On failure, surface the message verbatim and stop. On success, capture `base_sha`/`head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`, then read once: `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`.

**Round** (from the handle's `prior_checkpoint`). Every round analyzes the full `<base_ref>...<head_ref>` range read above - risk, scope, and requirement fit score the whole change each time, so a small follow-up commit cannot under-score a large PR. Rounds differ only in that round 2+ reconciles against the prior report:

| Checkpoint state                                                        | Decision                                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Absent, or `prior_checkpoint: legacy`                                    | `round: 1` (legacy report is overwritten)                          |
| `prior head_sha == head_sha`, and the checkpoint's `scope`/`depth` cover the requested ones (covering = superset: `full` covers every scope, `+perf +sec` covers `+sec`, any scope covers `core-only` - flags add lenses to the core review; `deep` covers `standard`) | Print `No new commits since prior review.` and stop - no report |
| `prior head_sha == head_sha`, requested scope or depth exceeds the checkpoint's | `round: prior + 1` - same commits, wider lens                       |
| Otherwise                                                                | `round: prior + 1`                                                 |

**Prior-round reconciliation.** On round 2+, Use skill: `review-prior-findings-reconcile` with the prior report body, the full-range diff, and `git diff --name-status <base_ref>...<head_ref>`; its table and tally line go under `## Prior Round Reconciliation` in the report. Round 1 skips it. Run this after the phases below and after **Verify findings**, so reconciliation matches against the verified set. Reconcile marks a row `Still open` or `Needs re-check`; both are unresolved and both carry forward by the rules here. A carried prior finding the current phases re-derive publishes once, noted `carried from round <N>` on its heading line (`<N>` = the prior report's own `round` value from its frontmatter, not this round) - the reconciliation table is its only other appearance - and takes the label this round assigns it. A carried finding the phases did not re-derive is carried into the findings sections at its prior label with the same note, skipping verify - reconciliation already re-checked it. A prior label outside this workflow's vocabulary (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in the reconciliation table, which reconcile owns, and maps through Feedback Labels before it is published in the findings sections. The table preserves each prior citation exactly; the published finding carries the corrected `file:line` when verification found the prior cite stale.

**Depth.** `standard` (default): review diff hunks plus immediate context. `deep`: skip the Phase A fast-path and read each touched file in full.

**Phase 0 - Change Intent.** Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and `prior_checkpoint.report_path` when round > 1. Its `## Change Brief` block is carried into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its findings join the assembled set for **Verify findings** with the rest (the atomic's requirement-findings section - or its `### No Requirement Findings` marker - is consumed into the set, never rendered). When no requirement source resolves, the Brief still renders and the traceability block and its two Summary lines are omitted. Phase 0 runs before Phase A - acceptance criteria decide what counts as a defect downstream - and no short-circuit skips it.

**Phase A - Risk Snapshot.** Use skill: `review-pr-risk`. Use skill: `review-blast-radius`. State Risk Level (Low/Medium/High/Critical) and Blast Radius (Narrow/Moderate/Wide/Critical) before any line-level finding - only those two Summary lines carry into the report; the atomics' full output blocks inform the review and are not emitted. If both are Low/Narrow and the diff touches no architecture-sensitive files (auth, middleware, API contracts, shared libs), produce the Phase 0 outputs (Change Brief, traceability, requirement findings) and Phase B findings only, and skip C-E.

**Phase B - Correctness and Safety.** Logical correctness, error handling, edge cases, transaction boundaries, unsafe shared-state mutation. Use skill: `ops-resiliency` for fault tolerance. Use skill: `architecture-concurrency` when concurrency is present. **Raise an explicit named finding when logic was added or modified without tests** ([Recommend] minimum; [Must] for critical paths - money movement, auth, data integrity).

**API contract gate (mandatory).** When the diff touches a route/handler registration, a controller, a request/response DTO or params schema, a serializer or response model, or a published spec file, Use skill: `backend-api-guidelines` and Use skill: `ops-backward-compatibility`. Both run - the first judges design, the second judges consumer breakage. Cover: contract compatibility from the consumer's view (removed/renamed/retyped field, tightened constraint, new required request field, changed status code or error shape is breaking until proven otherwise; "no callers" requires a search); response honesty (DTOs never raw ORM entities, RFC 9457 errors, collections paginated); versioning on breaking change; and **OpenAPI drift** - when the project publishes a spec or generated client, changed endpoints, schemas, status codes, and error shapes match the code. Each finding names the impacted consumer and the concrete harm - who breaks and how for a compatibility finding, what internal detail the response now exposes for a design finding - not just the deviated convention. Severity maps to labels: High -> [Must] = unversioned breaking change to an externally consumed contract, or a leaked internal shape (High for any consumer - the leak couples every caller to internals); Medium -> [Recommend] = breaking change to an internal contract without a coordinated-deploy note, inconsistent status code or error envelope, unpaginated unbounded collection; Low = naming drift with no consumer impact - below the reporting bar, write nothing. When consumption is unknown, treat a published or versioned surface (`/v1/`, OpenAPI-documented) as externally consumed. Migrations and non-API contract changes still load `ops-backward-compatibility` on their own.

**Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.

**Phase C - Architecture Guardrails.** Use skill: `architecture-guardrail` for layer violations, new coupling, circular dependency risk, boundary erosion.

**Phase D - AI-Generated Code Quality.** Use skill: `complexity-review` for over-abstraction, premature generalization, redundant mapping layers, speculative config.

**Phase E - Maintainability.** Use skill: `backend-coding-standards`. Use skill: `ops-observability` for logging/metrics/tracing coverage. Flag naming clarity, mixed responsibilities, large unreviewable chunks, hardcoded URLs/secrets/magic numbers.

**Extra scopes.** If `+perf`, `+sec`, `+obs`, or `+rel` was passed, load the matching `task-code-review-*` skill (`full` = all four) and run it as a subagent, passing the read-once diff/log, the precondition handle, the active depth, and the stack-detect output. Each sub-scope skill defines the subagent contract it runs under in its own Invocation section. Run in parallel; when subagents are unavailable, run each sub-scope skill inline in sequence under the same contract. Sub-scopes return findings to this workflow and write no report - merge them by strongest intent (Must > Recommend; highest wins on duplicates); preserve `file:line` citations. A sub-scope may also return a coverage list (security's OWASP rows): it confirms the lens ran to completion and informs the review, and is not rendered.

**Cross-phase dedup.** A single defect can surface in more than one phase or lens - the Phase B contract gate and a sub-scope, Phase 0 and Phase B, Phase B and the Phase C guardrail. Whether or not extra scopes ran, merge before **Verify findings**: publish one entry at the strongest intent whose Issue line names each lens that surfaced it and whose System Risk line states the combined exposure in one sentence; preserve `file:line`.

**Order of operations.** The phases above only gather. Then, in this order: merge sub-scope findings into the set, dedup across phases and lenses, run **Verify findings**, reconcile against the prior round (round 2+), then write Step 5. The reading order of this step is not its execution order.

**Verify findings.** Use skill: `review-finding-verify` with the assembled findings (including any merged from sub-scopes), the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column. Fill the Summary's `Findings verified:` line as `<N> confirmed, <M> reattributed, <K> dropped` from its counts, appending the `(<F> false positive, <R> resolved by diff)` split and the `; <U> of these unverified` suffix when the atomic emits them. Atomic output blocks (risk, resiliency, guardrail, the verify table) inform the review and are never emitted - the report carries only the slots Output Format names.

### Step 5 - Write Report

Use skill: `review-report-writer` with `report_type: review` and every required input: `report_body` (the assembled report per Output Format), `branch` (head short name from the handle - for `head_ref: HEAD`, the handle's `current_branch`, never the literal `HEAD`; strip any leading `<remote>/` segment so a remote-resolved head and a later local review chain on one file; this is the review target and the checkpoint lookup key), `base_ref`/`head_ref`, `base_sha`/`head_sha` (Step 4), `mode: full` (the writer's only accepted value), `round` (Step 4; plus `prior_head_sha` when round > 1 - on a same-SHA wider-lens round it equals `head_sha`, which is expected), `scope` (writer enum value - `core-only` when no scope flag was passed; combined flags join with single spaces in the canonical order `+perf +sec +obs +rel`; all four = `full`), `depth` (`standard` when no depth flag), `stack` (kebab-case `<language>-<framework>` from the stack-detect output, e.g. `elixir-phoenix`; drop a segment reported unknown; `unknown` only when detection failed entirely).

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

Findings arriving from phase atomics or sub-scopes with High/Medium/Low severity map High -> `[Must]`, Medium/Low -> `[Recommend]`; a phase's own mapping (the Phase B contract gate) governs its findings, and a defect outside that mapping's enum falls back to the general mapping. A maintainability-only High - complexity, structure, naming - carries `[Recommend]`: `[Must]` blocks a merge, and readability alone does not. A finding this workflow raises directly, with no atomic-supplied severity, takes `[Must]` when it risks incorrect behaviour, data loss, or a security hole, and `[Recommend]` otherwise. Where `review-finding-verify` publishes a different `Label` than the mapping assigned, the published label governs - including in Next Steps and in Assessment.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

**Assessment** derives from the published findings - verified and carried-forward alike: any `[Must]` -> Request Changes; no `[Must]` but at least one `[Recommend]` -> Discuss; none -> Approve.

**Annotations** sit on the `###` heading line after `file:line`: `review-finding-verify`'s `_(pre-existing)_` / `_(pre-existing; newly reachable via ...)_` / `_(unverified: ...)_`, and `carried from round <N>` for a carried finding. A heading may carry both.

**Scope** displays combined flags capitalized in the canonical order (`+Perf +Sec`); the writer input keeps the lowercase form in the same order.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical
- **Stack Detected:** <identifier or unknown> (generic fallback applied)
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full
- **Depth:** standard | deep
- **Round:** <N> _(include from round 2 onward)_
- **Findings verified:** <`<N> confirmed, <M> reattributed, <K> dropped` from `review-finding-verify`, plus its false-positive/resolved split and unverified suffix when emitted>
- **Requirement Source:** <path or origin> (Specified | Self-attested) _(this line and the next are emitted together, or both omitted when Phase 0 resolved no source)_
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable

## Change Brief

**Requested:** <what the change was asked to do; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability

<table from `review-change-intent` - omit the section when no requirement source resolved>

## Prior Round Reconciliation

<table and tally from `review-prior-findings-reconcile` - round 2+ only; omit section otherwise>

## High-Impact Findings

### [Must] file:line

- Issue:
- Impact:
- System Risk:
- Fix:

### [Recommend] file:line

[Same structure]

## Architecture Notes

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact

## Next Steps

Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: owning area - dependencies, schema, platform, infra] - [one-line action]

_Omit sections with no findings._

_Publish every `[Must]`. Where `[Recommend]` findings exceed roughly a dozen, publish the highest-impact dozen and close High-Impact Findings with one line naming how many were folded and the files they sit in - never drop a `[Must]` to fit. A defect-dense diff legitimately yields many `[Must]` findings; that is the correct output, not a reason to demote._
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched and available, stack workflow ran with the invocation forwarded unchanged, Steps 4-5 skipped; if matched but unavailable, missing plugin named and fallback ran
- [ ] Step 4: if no dispatch, SHAs captured; round decided from `prior_checkpoint`; prior findings reconciled on round 2+; Phase 0 `review-change-intent` ran on the full-range diff with its Change Brief in the report; Phase A risk stated before line findings; the Phase B API contract gate ran when the diff touched a route, controller, DTO, serializer, or spec file; missing tests raised as named finding; extra scopes spawned in parallel and merged without writing their own reports; `review-finding-verify` ran on the assembled findings with Dropped rows excluded; findings ordered Must > Recommend
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the `No new commits since prior review.` stop line printed, or a precondition failure surfaced verbatim with no report written (fallback path only)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Producing findings when a stack workflow was dispatched
- State-changing git commands (`fetch`, `checkout`, `merge`)
- Reviewing without reading the full diff first
- Stylistic nits without a project standard
- Blocking on personal preference over correctness, risk, or maintainability
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` (see Feedback Labels)
