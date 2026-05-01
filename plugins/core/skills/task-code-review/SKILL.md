---
name: task-code-review
description: Staff-level code review for PRs - risk-based evaluation, architecture boundary protection, correctness, AI-generated code quality control, and maintainability. Auto-detects project stack and applies framework-specific checks. Use for all PRs, including AI-assisted, large, or cross-service changes.
metadata:
  category: review
  tags: [code-review, pull-request, risk-assessment, architecture, ai-quality, quality, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**, not suggestions; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Code Review

## Purpose

Staff-level code review that prioritizes system risk over style. AI-generated code is now standard, so every review evaluates:

- Risk-based evaluation - assess blast radius and cross-module impact before line-level feedback
- Architecture boundary protection - detect coupling, layer violations, and structural drift early
- Correctness and safety - logical correctness, error handling, edge cases, backward compatibility
- AI-generated code quality control - catch over-abstraction, verbosity inflation, and premature generalization
- Maintainability - clear naming, focused responsibilities, reviewable chunks
- High-signal findings only - no nitpicking, no trivial formatting comments

## When to Use

- Pull request reviews
- Code change reviews before merge
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** Architecture/design review of new systems (use `task-design-architecture`), security-only audits (use `task-code-secure-review`), performance-only review (use `task-code-perf-review`).

## Depth Levels

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full staff-level review                                         | Phases A-E                                                   |
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

| Scope            | What runs                                                                      |
| ---------------- | ------------------------------------------------------------------------------ |
| Core             | Phases A-E only (risk, correctness, architecture, AI quality, maintainability) |
| + Perf           | Core + delegate to skill: `task-code-perf-review`                              |
| + Security       | Core + delegate to skill: `task-code-secure-review`                            |
| + Observability  | Core + delegate to skill: `task-code-observability-review`                     |
| Full             | Core + Performance + Security + Observability                                  |

Default: **Core**. If invoked with an explicit scope argument (e.g., `/task-code-review +perf`), skip the question and use that scope directly.

Depth and scope are independent. Example: `quick` depth with `+security` scope = risk snapshot + security findings only.

**Scope escalation signals:** If the change involves any of the following, recommend the user add the corresponding scope:

- File uploads, auth flows, user input deserialization, secrets handling -> recommend +Security
- Bulk operations, new database queries, new endpoints with large payloads -> recommend +Perf
- New service, new external dependency, new async/queue boundary, or change to logging/metrics/tracing wiring -> recommend +Observability
- Multiple signal categories present -> recommend Full

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

**Bulk operations (if applicable):**

- Partial failure handling defined (skip-and-continue vs. all-or-nothing)
- Idempotency for retryable bulk operations
- Transaction boundaries appropriate (not one giant transaction, not one per row)
- Background processing for operations that exceed request timeout

**Migration PRs (pattern change, not just code change):**

- Use skill: `ops-backward-compatibility` to assess impact on existing clients, active sessions, or in-flight requests
- Verify rollback path exists and is documented

After loading stack-detect, apply correctness checks based on `Stack Type`. If `Stack Type: fullstack`, apply both backend and frontend checks to the relevant parts of the change.

#### Backend Correctness (when Stack Type is `backend` or `fullstack`)

- Transaction management patterns appropriate to the framework
- Concurrency safety for the detected runtime's threading model
- Null/nil/zero-value handling using the language's standard approach
- Error handling following the ecosystem's conventions
- **Synchronous external I/O in hot paths**: flag as [High] any synchronous call to cache, database, or external service added in a shared hot path (auth middleware, request filters, interceptors) where the added latency affects every request
- No N+1 query patterns (loops that trigger per-row queries)
- Queries are bounded - no unbounded fetches without pagination or limit
- ORM entities are not exposed in API responses

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
- Form inputs have associated labels; images have alt text (decorative images use empty alt)

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
Key signals: over-abstraction, premature generalization, redundant mapping layers, unnecessary boilerplate, pattern inflation, speculative configurability, unused parameters added "for flexibility".

### Phase E - Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, complex logic without explanation, hardcoded URLs/secrets/credentials/magic numbers that should be config or named constants.

**Backend/fullstack:** Use skill: `backend-coding-standards` for naming, structure, and anti-pattern enforcement.
**All stacks:** Use skill: `ops-observability` to check logging, metrics, and tracing coverage (backend) or error tracking and analytics instrumentation (frontend).

### Step 2 - Delegate (if scope includes)

- **+Perf**: delegate to `task-code-perf-review`
- **+Security**: delegate to `task-code-secure-review`
- **+Observability**: delegate to `task-code-observability-review`

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

If the detected stack is unfamiliar, apply only the universal review criteria from Phase B and note the limitation.

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels - this is staff-level review; trivia is filtered out.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** [language / framework]

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete code change or approach]

### [High] file:line

- Issue:
- Impact:
- Fix:

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

- 2-4 concise bullets summarizing systemic impact and what to address before merge.
```

**Example finding (good depth):**

```markdown
### [Blocker] PaymentWebhookController.java:45

- Issue: Webhook signature verification happens after the request body is parsed and partially processed
- Impact: An attacker can trigger side effects (order status update) with a forged webhook payload before verification fails
- System Risk: Auth boundary erosion - any future handler added to this controller inherits the same flaw
- Fix: Move `verifySignature(request)` to the first line of the handler, before any business logic executes
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Output Constraints

- Do NOT list trivial formatting issues
- If risk is low, say so and keep findings minimal
- Findings ordered by severity: Blocker > High > Suggestion > Question
- Omit empty sections
- No purely stylistic findings without a project standard
- Optimize for token efficiency

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Check for consistency with existing codebase patterns
- Provide actionable feedback with examples
- Never comment on trivial formatting or style where no project standard exists
- Never block on personal preference
- Default to Core scope
- Do not apply conventions from one stack to another

## Self-Check

- [ ] Stack detected and Stack Type determined; appropriate checks applied (backend, frontend, or both)
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Architecture boundary impact assessed even if no violations found (including component boundaries for frontend)
- [ ] AI-generated code evaluated for over-abstraction and verbosity inflation
- [ ] Every finding has a label, location (file:line), and actionable fix
- [ ] Findings ordered Blocker > High > Suggestion > Question; no purely stylistic findings without a project standard
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Key Takeaways convey systemic risk; Summary alone is enough for an Approve/Request Changes decision
- [ ] No framework conventions applied from a different stack than detected
- [ ] Frontend checks (accessibility, state, components) applied when Stack Type is frontend or fullstack
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker

## Avoid

- Reviewing without reading the full diff first
- Applying conventions from one stack to another (e.g., Java conventions on Go code)
- Nitpicking style where no project standard exists
- Providing vague feedback without a concrete fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Commenting on every file - focus on the most impactful findings
- Running performance or security sub-workflows when user requested Core scope only
