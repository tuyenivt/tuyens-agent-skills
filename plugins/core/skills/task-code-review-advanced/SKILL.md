---
name: task-code-review-advanced
description: Staff-level code review for high-risk PRs, AI-generated code, or large cross-service changes. Evaluates blast radius, hidden coupling, architecture boundary violations, and systemic risk. Use when the PR is AI-assisted, touches multiple services, is unusually large (500+ lines), or modifies shared infrastructure.
metadata:
  category: review
  tags: [code-review, pull-request, risk-assessment, architecture, ai-quality, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Code Review - Staff Edition

## Purpose

Staff-level code review that prioritizes system risk over style:

- Risk-based evaluation - assess blast radius and cross-module impact before line-level feedback
- Architecture boundary protection - detect coupling, layer violations, and structural drift early
- Maintainability control - catch over-abstraction, verbosity inflation, and premature generalization
- High-signal findings only - no nitpicking, no trivial formatting comments

## When to Use

- Pull request reviews
- Code change reviews before merge
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** Routine PRs (use `task-code-review`), security-only audits (use `task-code-secure`), performance-only review (use `task-code-perf-review`).

## Depth Levels

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full staff-level review for high-risk or AI-generated PRs       | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

**Quick depth produces:**

- Risk level and blast radius (2-3 sentences)
- Top 3 findings only (Blockers first, then Highs)
- Approve / Request Changes / Discuss recommendation

**Deep depth adds (on top of standard):**

- Historical pattern matching: does this change repeat a pattern that caused past incidents?
- Cross-PR context: any known concurrent PRs that interact with this change?
- Architecture evolution note: does this PR move the architecture in the right or wrong direction over time?

Default: `standard`. Use `quick` when user asks for "quick review", "sanity check", or "is this safe?". Use `deep` when user asks for "full review", "architecture review", or "Principal sign-off".

## Scope

| Scope      | What runs                                                                      |
| ---------- | ------------------------------------------------------------------------------ |
| Core       | Phases A-E only (risk, correctness, architecture, AI quality, maintainability) |
| + Perf     | Core + delegate to skill: `task-code-perf-review`                              |
| + Security | Core + delegate to skill: `task-code-secure`                                   |
| Full       | Core + Performance + Security                                                  |

Default: Core. If invoked with an explicit scope argument (e.g., `/task-code-review-advanced +perf`), skip the question and use that scope directly.

Depth and scope are independent. Example: `quick` depth with `+security` scope = risk snapshot + security findings only.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth, middleware, API contracts, shared libraries, service boundaries), skip Phases C-D and produce a streamlined output with Phase B findings only. This avoids over-reviewing trivial changes with the staff-level process. If any architecture-relevant file is touched, proceed with the full workflow regardless of risk level.

### Phase B - Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, unsafe shared state mutation, transaction boundary correctness.

**Test coverage finding:** If the PR adds or modifies logic without corresponding tests, raise this as an explicit finding - at minimum a [Suggestion], escalate to [High] if the changed code is in a critical path (auth, payments, data integrity). Do not bury this in Key Takeaways - it must appear as a named finding.

**Migration PRs (pattern change, not just code change):**
- Use skill: `ops-backward-compatibility` to assess impact on existing clients, active sessions, or in-flight requests
- Verify rollback path exists and is documented

After loading stack-detect, apply correctness checks based on `Stack Type`:

#### Backend Correctness (when Stack Type is `backend` or `fullstack`)

- Transaction management patterns appropriate to the framework
- Concurrency safety for the detected runtime's threading model
- Null/nil/zero-value handling using the language's standard approach
- Error handling following the ecosystem's conventions
- **Synchronous external I/O in hot paths**: flag as [High] any synchronous call to cache, database, or external service added in a shared hot path (auth middleware, request filters, interceptors) where the added latency affects every request

Use skill: `ops-resiliency` for error handling, retry, and fault tolerance patterns.
Use skill: `backend-api-guidelines` if the change touches API contracts or HTTP endpoints.
Use skill: `architecture-concurrency` if concurrency patterns are present in the change.

#### Frontend Correctness (when Stack Type is `frontend` or `fullstack`)

- Rendering correctness: components render the right content for all states (loading, error, empty, populated)
- State consistency: no stale closures, no state updates on unmounted components, no race conditions between async operations and UI state
- Memory leaks: event listeners, subscriptions, timers, and observers cleaned up on unmount
- Side effect isolation: effects/subscriptions have proper dependency arrays and cleanup functions
- Error boundaries: errors in child components do not crash the entire application
- Accessibility: interactive elements are keyboard-accessible, ARIA attributes are correct, focus management works

Use skill: `frontend-state-management` to verify state patterns are appropriate.
Use skill: `frontend-accessibility` for accessibility compliance.
Use skill: `frontend-api-integration` if the change involves data fetching.

### Phase C - Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion, architectural drift.

**Multi-service PRs (when change spans 2+ services):**
- Check API contract compatibility between services after the change
- Verify deployment can be done in any order (or document required order)
- Check for shared library version alignment
- Use skill: `ops-backward-compatibility` for any changed inter-service contracts

**Backend:** Apply the layering conventions of the detected framework - presentation → service → data access - using the ecosystem's standard patterns.

**Frontend:** Apply component boundary conventions - page components → feature components → shared UI components. Detect: business logic leaking into components, components reaching across feature boundaries, shared state used for single-feature concerns, tightly coupled component hierarchies that prevent reuse.

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.
Key signals: over-abstraction, premature generalization, redundant mapping layers, unnecessary boilerplate, pattern inflation.

### Phase E - Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, complex logic without explanation.

**Backend/fullstack:** Use skill: `backend-coding-standards` for naming, structure, and anti-pattern enforcement.
**All stacks:** Use skill: `ops-observability` to check logging, metrics, and tracing coverage (backend) or error tracking and analytics instrumentation (frontend).

## Framework-Specific Signals

After loading stack-detect, check for framework-specific signals based on the detected ecosystem and `Stack Type`. The atomic skills loaded in Phases B-E handle detailed pattern enforcement. In addition, check these staff-level concerns:

**Backend signals:**

- **Architectural fit**: Does the change follow the framework's recommended layering and DI patterns, or does it introduce a competing pattern?
- **Concurrency model match**: Are concurrency primitives appropriate for the detected runtime's threading model (e.g., virtual threads vs. thread pools in Java 21+, goroutines vs. OS threads)?
- **Ecosystem currency**: Does the change use current language features and framework APIs, or does it introduce deprecated patterns that create future migration burden?
- **ORM entities in API responses**: Are data layer entities exposed directly in API responses instead of using DTOs/serializers?

**Frontend signals:**

- **Component boundary discipline**: Does the change respect component single-responsibility, or does it create god components?
- **State management escalation**: Does the change introduce global state where local state would suffice, or use prop drilling where context/stores are warranted?
- **Rendering performance**: Does the change introduce unnecessary re-renders, missing memoization, or heavy computation in render paths?
- **Ecosystem currency**: Does the change use current framework APIs (e.g., React 19 hooks, Vue 3.5 features, Angular signals), or does it introduce deprecated patterns?

If the detected stack is unfamiliar, apply only the universal review criteria and note the limitation.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** [language / framework]

## High-Impact Findings

### [Blocker] file:line

- Issue:
- Impact:
- System Risk:

### [High] file:line

- Issue:
- Impact:

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

- 2–4 concise bullets summarizing systemic impact.
```

## Output Constraints

- Do NOT list trivial formatting issues
- If risk is low, say so and keep findings minimal
- Findings ordered by severity: Blocker > High > Suggestion
- Omit empty sections
- No [Nitpick] or [Praise] labels
- Optimize for token efficiency

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Never comment on trivial formatting or style where no project standard exists
- Never block on personal preference
- Default to Core scope
- Do not apply conventions from one stack to another

## Self-Check

- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Architecture boundary impact assessed even if no violations found (including component boundaries for frontend)
- [ ] AI-generated code evaluated for over-abstraction and verbosity inflation
- [ ] Findings ordered Blocker > High > Suggestion; no purely stylistic findings without a project standard
- [ ] Key Takeaways convey systemic risk; Summary alone is enough for an Approve/Request Changes decision
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Stack Type determined; backend and/or frontend checks applied appropriately

## Avoid

- Nitpicking style when no project standard exists
- Blocking on personal preference
- Reviewing without understanding module context
- Running performance or security sub-workflows when user requested Core scope only
- Commenting on every file - focus on systemic issues
- Applying framework conventions from a different stack
