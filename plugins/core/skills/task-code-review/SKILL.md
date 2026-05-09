---
name: task-code-review
description: Code review entry point: risk, correctness, maintainability. Detects stack and dispatches to stack-specific review workflow.
metadata:
  category: review
  tags: [code-review, pull-request, risk-assessment, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles` and propagate the spec context to the dispatched stack workflow.

# Code Review (Router)

This skill is a thin dispatcher. It detects the project stack and delegates to the matching stack-specific skill (e.g., `task-spring-review`, `task-rails-review`, `task-react-review`). The stack workflow runs Phases A-E with framework-specific correctness, architecture, AI-quality, and maintainability checks (Rails: Zeitwerk, callback abuse, fat controllers; Spring: layering, transaction placement; React: hooks, context boundaries) and spawns its own perf / security / observability subagents in parallel for any extra scope.

For unknown stacks, this skill falls back to a minimal generic review protocol.

## When to Use

- Pull request reviews and pre-merge risk assessment
- Code change reviews before merge
- Post-AI-generation quality gate

**Not for:** Architecture/design review of new systems, security-only audits (use `task-code-review-security`), performance-only review (use `task-code-review-perf`), observability-only review (use `task-code-review-observability`).

## Invocation

Accepts the same arguments as the stack-specific review umbrellas:

| Invocation                   | Meaning                                                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------------- |
| `/task-code-review`          | Review current branch vs its base (fails fast on trunk branches)                              |
| `/task-code-review <branch>` | Review `<branch>` vs its base (3-dot diff)                                                    |
| `/task-code-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs `git fetch` first)             |

Scope flags (`+perf`, `+security`, `+observability`, `full`, `core-only`) and depth flags (`quick`, `standard`, `deep`) and `--base <branch>` compose with any of the above and are forwarded to the dispatched stack workflow.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`.

### Step 2 - Dispatch to Stack Workflow

| Detected stack       | Delegate to           |
| -------------------- | --------------------- |
| Java / Spring Boot   | `task-spring-review`  |
| Kotlin / Spring Boot | `task-kotlin-review`  |
| Python               | `task-python-review`  |
| Ruby / Rails         | `task-rails-review`   |
| Node.js / TypeScript | `task-node-review`    |
| Go / Gin             | `task-go-review`      |
| Rust / Axum          | `task-rust-review`    |
| .NET / ASP.NET Core  | `task-dotnet-review`  |
| PHP / Laravel        | `task-laravel-review` |
| React                | `task-react-review`   |
| Vue                  | `task-vue-review`     |
| Angular              | `task-angular-review` |

When delegating, forward the user's full invocation (target ref, `--base`, scope flags, depth flags) and any spec context. The stack umbrella owns precondition checks, diff resolution, and parallel subagent dispatch for non-Core scopes.

If matched, stop. Do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

Run only when Step 2 finds no match. This is a minimum-viable review that works for any language.

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`. If the precondition check stops with a fail-fast message, surface it verbatim and stop.

**Phase A - Risk Snapshot (run first):**

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope
- State Risk Level (Low/Medium/High/Critical) and Blast Radius (Narrow/Moderate/Wide) before any line-level findings

If Risk Level is Low and Blast Radius is Narrow and the change does not touch architecture-relevant files (auth, middleware, API contracts, shared libraries), produce a streamlined output with Phase B findings only.

**Phase B - Correctness and Safety:**

- Logical correctness, error handling, edge cases affecting state integrity
- Backward compatibility (use skill: `ops-backward-compatibility` for migration PRs)
- Unsafe shared state mutation, transaction boundary correctness
- **Test coverage finding:** If logic is added/modified without tests, raise as an explicit named finding (at least [Suggestion]; [High] for critical paths)
- Use skill: `ops-resiliency` for error handling and fault tolerance
- Use skill: `backend-api-guidelines` if the change touches API contracts
- Use skill: `architecture-concurrency` if concurrency patterns are present

**Phase C - Architecture Guardrails:**

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, boundary erosion. For multi-service PRs, check API contract compatibility and deployment ordering.

**Phase D - AI-Generated Code Quality:**

Use skill: `complexity-review` to detect over-abstraction, premature generalization, redundant mapping layers, speculative configurability.

**Phase E - Maintainability:**

Naming clarity, mixed responsibilities, large unreviewable chunks, hardcoded URLs/secrets/magic numbers. Use skill: `backend-coding-standards` (backend) and `ops-observability` (logging/metrics/tracing coverage).

**Extra scopes:** if `+perf`, `+security`, `+observability`, or `full` was passed, spawn the corresponding `task-code-review-*` workflow as a subagent with the read-once diff/log and pre-detected stack. Run subagents in parallel; merge findings by severity (highest wins on duplicates), preserve `file:line` citations.

**Step 4 - Write Report:** Use skill: `review-report-writer` with `report_type: review`.

## Feedback Labels

| Label        | Meaning                                     |
| ------------ | ------------------------------------------- |
| [Blocker]    | Must fix before merge - correctness or risk |
| [High]       | Should fix - significant impact or smell    |
| [Suggestion] | Would improve - non-blocking                |
| [Question]   | Need clarity from author                    |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output.

When fallback runs (Step 3):

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** unknown (generic fallback applied)
**Scope:** Core | +Security | +Perf | +Observability | Full
**Depth:** quick | standard | deep

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete code change or approach]

### [High] file:line

[Same structure]

### [Suggestion] file:line

- Improvement:

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

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope] - [one-line action]

_Omit sections with no findings._
```

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] Spec-aware preamble loaded when `--spec` was passed or `.specs/<slug>/` exists
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped; user's flags and spec context were forwarded
- [ ] If no stack matched, Step 3 fallback ran Phases A-E and any requested extra scopes
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Missing tests raised as a named finding
- [ ] Findings ordered Blocker > High > Suggestion > Question; no purely stylistic findings without a project standard
- [ ] Review report written to file via `review-report-writer`

## Avoid

- Running both Step 2 dispatch and Step 3 fallback
- Producing your own findings when a stack workflow was dispatched
- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reviewing without reading the full diff first
- Nitpicking style where no project standard exists
- Blocking on personal preference rather than correctness, risk, or maintainability
- Treating the fallback as a full equivalent of a stack workflow - install the matching language plugin when one exists
