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

Detects the project stack and delegates to the matching stack-specific review workflow (`task-{stack}-review`). When no stack workflow is available, runs a minimal generic Phases A-E review.

## When to Use

- PR review, pre-merge risk assessment, post-AI-generation quality gate.

**Not for:** New-system architecture, security-only audits (`task-code-review-security`), perf-only (`task-code-review-perf`), observability-only (`task-code-review-observability`), reliability-only (`task-code-review-reliability`).

## Invocation

`/task-code-review [<branch> | pr-<N>] [+perf | +sec | +obs | +rel | full | core-only] [standard | deep] [--base <branch>]`

All flags are forwarded to the dispatched stack workflow.

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

Forward the user's invocation verbatim (target ref, `--base`, scope, depth). The stack umbrella owns precondition checks, diff resolution, parallel sub-scope dispatch, and the final report. **If matched, stop. Skip Steps 4-5.**

If a row matches but the target skill does not resolve (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5 as a degraded generic review and note the degradation in the report.

### Step 4 - Generic Fallback (no dispatch)

Runs when no Step 3 row matched the detected stack, or the matched workflow is unavailable.

Use skill: `review-precondition-check` with the user's target argument and any `--base` override (default: current branch). On failure, surface the message verbatim and stop. On success, capture `base_sha`/`head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`, then read once: `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`.

**Mode and round** (from the handle's `prior_checkpoint`):

| Checkpoint state                                                        | Decision                                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Absent, or `prior_checkpoint: legacy`                                    | `mode: full`, `round: 1` (legacy report is overwritten)            |
| `prior head_sha == head_sha`                                             | Print `No new commits since prior review.` and stop - no report    |
| `git merge-base --is-ancestor <prior_head_sha> <head_sha>` fails, OR prior `base_sha`/`base_ref` differs | `mode: full`, `round: prior + 1` |
| Otherwise                                                                | `mode: incremental`, `round: prior + 1`; re-read diff/log scoped to `<prior_head_sha>...<head_ref>` |

**Incremental reconciliation.** When `mode: incremental`, Use skill: `review-prior-findings-reconcile` with the prior report body, the incremental diff, and `git diff --name-status <prior_head_sha>...<head_ref>`; its table goes under `## Prior Round Reconciliation` in the report. Full-mode rounds skip it (fresh pass).

**Depth.** `standard` (default): review diff hunks plus immediate context. `deep`: skip the Phase A fast-path and read each touched file in full.

**Phase A - Risk Snapshot.** Use skill: `review-pr-risk`. Use skill: `review-blast-radius`. State Risk Level (Low/Medium/High/Critical) and Blast Radius (Narrow/Moderate/Wide/Critical) before any line-level finding. If both are Low/Narrow and the diff touches no architecture-sensitive files (auth, middleware, API contracts, shared libs), produce Phase B findings only and skip C-E.

**Phase B - Correctness and Safety.** Logical correctness, error handling, edge cases, transaction boundaries, unsafe shared-state mutation. Use skill: `ops-resiliency` for fault tolerance. Use skill: `backend-api-guidelines` when API contracts change. Use skill: `architecture-concurrency` when concurrency is present. Use skill: `ops-backward-compatibility` for migrations or contract changes. **Raise an explicit named finding when logic was added or modified without tests** ([Recommend] minimum; [Must] for critical paths).

**Phase C - Architecture Guardrails.** Use skill: `architecture-guardrail` for layer violations, new coupling, circular dependency risk, boundary erosion.

**Phase D - AI-Generated Code Quality.** Use skill: `complexity-review` for over-abstraction, premature generalization, redundant mapping layers, speculative config.

**Phase E - Maintainability.** Use skill: `backend-coding-standards`. Use skill: `ops-observability` for logging/metrics/tracing coverage. Flag naming clarity, mixed responsibilities, large unreviewable chunks, hardcoded URLs/secrets/magic numbers.

**Extra scopes.** If `+perf`, `+sec`, `+obs`, or `+rel` was passed, spawn the matching `task-code-review-*` skill as a subagent (`full` = all four) with the read-once diff/log and the detected stack handle. Run in parallel. Sub-scopes return findings to this workflow and write no report - merge them by strongest intent (Must > Recommend > Question; highest wins on duplicates); preserve `file:line` citations.

### Step 5 - Write Report

Use skill: `review-report-writer` with `report_type: review` and every required input: `report_body` (the assembled report per Output Format), `branch` (current branch from the handle), `base_ref`/`head_ref`, `base_sha`/`head_sha` (Step 4), `mode`/`round` (Step 4; plus `prior_head_sha` when round > 1), `scope` (enum value - `core-only` when no scope flag was passed), `depth` (`standard` when no depth flag), `stack` (kebab-case `<language>-<framework>` from the stack-detect output, e.g. `elixir-phoenix`; drop a segment reported unknown; `unknown` only when detection failed entirely).

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |
| [Question]   | Author must answer; reviewer decides if a fix follows.                   |

No `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide | Critical
**Stack Detected:** <identifier or unknown> (generic fallback applied)
**Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full
**Depth:** standard | deep
**Mode:** full | incremental (round <N>)

## Prior Round Reconciliation

<table from `review-prior-findings-reconcile` - incremental rounds only; omit section otherwise>

## High-Impact Findings

### [Must] file:line

- Issue:
- Impact:
- System Risk:
- Fix:

### [Recommend] file:line

[Same structure]

### [Question] file:line

- Question:
- Why it matters:

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

Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope] - [one-line action]

_Omit sections with no findings._
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched and available, stack workflow ran with all flags forwarded, Steps 4-5 skipped; if matched but unavailable, missing plugin named and fallback ran
- [ ] Step 4: if no dispatch, SHAs captured; mode/round decided from `prior_checkpoint`; prior findings reconciled on incremental rounds; Phase A risk stated before line findings; missing tests raised as named finding; extra scopes spawned in parallel and merged without writing their own reports; findings ordered Must > Recommend > Question
- [ ] Step 5: report written via `review-report-writer` with all required inputs (fallback path only)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Producing findings when a stack workflow was dispatched
- State-changing git commands (`fetch`, `checkout`, `merge`)
- Reviewing without reading the full diff first
- Stylistic nits without a project standard
- Blocking on personal preference over correctness, risk, or maintainability
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` / `[Question]` (see Feedback Labels)
