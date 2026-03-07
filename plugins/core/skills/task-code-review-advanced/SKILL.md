---
name: task-code-review-advanced
description: Staff-level code review for high-risk PRs or AI-generated code - blast radius, architecture boundaries, cross-module impact. Use when a basic review is not enough. Not a substitute for task-code-review on routine PRs.
metadata:
  category: review
  tags: [code-review, pull-request, risk-assessment, architecture, ai-quality, multi-stack]
  type: workflow
---

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

## Scope

| Scope      | What runs                                                                      |
| ---------- | ------------------------------------------------------------------------------ |
| Core       | Phases A–E only (risk, correctness, architecture, AI quality, maintainability) |
| + Perf     | Core + delegate to skill: `task-code-perf-review`                              |
| + Security | Core + delegate to skill: `task-code-secure`                                   |
| Full       | Core + Performance + Security                                                  |

Default: Core. If invoked with an explicit scope argument (e.g., `/task-code-review-advanced +perf`), skip the question and use that scope directly.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `pr-risk-analysis` to evaluate cross-cutting risk signals
- Use skill: `blast-radius-analysis` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

### Phase B - Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, unsafe shared state mutation, transaction boundary correctness.

After loading stack-detect, apply correctness checks specific to the detected ecosystem:

- Transaction management patterns appropriate to the framework
- Concurrency safety for the detected runtime's threading model
- Null/nil/zero-value handling using the language's standard approach
- Error handling following the ecosystem's conventions

Use skill: `resiliency`, `api-guidelines`

### Phase C - Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion, architectural drift.

Apply the layering conventions of the detected framework - presentation → service → data access - using the ecosystem's standard patterns.

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.
Key signals: over-abstraction, premature generalization, redundant mapping layers, unnecessary boilerplate, pattern inflation.

### Phase E - Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, complex logic without explanation.
Use skill: `coding-standards`, `observability`

## Framework-Specific Signals

After loading stack-detect, check for framework-specific signals based on the detected ecosystem. These typically include:

- Modern language feature adoption (use current idioms, not deprecated patterns)
- Framework-recommended architecture patterns (layering, DI, response shaping)
- Concurrency model compatibility (thread safety for the detected runtime)
- Test utility currency (use current test annotations and helpers, not deprecated ones)

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

## Key Skills Reference

Correctness and Safety: `resiliency`, `api-guidelines`
Architecture and Quality: `coding-standards`, `observability`, `architecture-guardrail`, `complexity-review`
Risk Assessment: `pr-risk-analysis`, `blast-radius-analysis`
Delegated Reviews: `task-code-perf-review`, `task-code-secure`

## Success Criteria

A well-executed code review passes all of these. Use as a self-check before posting findings.

### Completeness

- [ ] Risk level and blast radius are stated before any line-level findings
- [ ] Every Blocker finding states a system risk, not just a code observation
- [ ] Architecture boundary and coupling impact are assessed, even if no violations found
- [ ] AI-generated code quality is evaluated for over-abstraction and verbosity inflation
- [ ] Framework-specific signals for the detected stack have been applied

### Signal Quality

- [ ] All findings are ordered Blocker > High > Suggestion - no mixing of severity
- [ ] No findings are purely stylistic where no project standard exists
- [ ] Each High finding states concrete impact, not just "this is bad"
- [ ] Suggestions are genuine improvements, not personal preference

### Staff-Level Signal (for tech lead review)

- [ ] The review assesses the change as a system impact, not file-by-file in isolation
- [ ] Architecture notes are present if any coupling, boundary, or drift issue was found
- [ ] Key Takeaways convey systemic risk, not a list of individual findings
- [ ] A reviewer reading only the Summary can make an Approve / Request Changes decision

## Avoid

- Nitpicking style when no project standard exists
- Blocking on personal preference
- Reviewing without understanding module context
- Running performance or security sub-workflows when user requested Core scope only
- Commenting on every file - focus on systemic issues
- Applying framework conventions from a different stack

## After This Skill

If the output needed significant adjustment - risk level was miscalibrated, architecture notes missed real violations, or findings were off-target - run `/task-skill-feedback` to log what changed and why.
