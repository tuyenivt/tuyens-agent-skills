---
name: task-code-review
description: Standard code review for PRs - correctness, readability, maintainability, and test coverage. Auto-detects project stack from CLAUDE.md. Not for design review (use task-design-architecture), security-only audit (use task-code-secure), or high-risk AI-generated code (use task-code-review-advanced).
metadata:
  category: review
  tags: [code-review, pull-request, quality, multi-stack]
  type: workflow
user-invocable: true
---

# Code Review

## When to Use

- Pull request reviews
- Code change reviews
- Pre-merge quality checks

## Scope

| Scope      | What runs                                          |
| ---------- | -------------------------------------------------- |
| Basic      | Correctness, readability, maintainability, testing |
| + Perf     | Basic + delegate to skill: `task-code-perf-review` |
| + Security | Basic + delegate to skill: `task-code-secure`      |
| Full       | Basic + Performance + Security                     |

Default: **Basic** (if the user doesn't specify, run Basic only).

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Review (All Stacks)

**Correctness:**

- Does what it's supposed to do
- Edge cases handled
- Error paths considered

**Readability:**

- Self-documenting code
- Clear naming
- Appropriate complexity

**Maintainability:**

- Changes are focused
- Follows existing patterns
- No unnecessary coupling

**Testing:**

- Appropriate coverage
- Edge cases tested

### Step 3 - Framework-Specific Checks

After loading stack-detect, apply framework-specific review criteria based on the detected ecosystem. Key areas to check:

**Language Idioms:**

- Code follows the naming conventions and idioms of the detected language
- Modern language features are used where appropriate (e.g., pattern matching, records, type hints)
- Deprecated patterns or APIs are avoided in favor of current best practices

**Framework Conventions:**

- Layering follows the framework's recommended architecture (controllers/handlers → services → data access)
- Dependency injection uses the framework's standard mechanism
- Response shaping uses proper DTOs/serializers - ORM entities are not exposed in API responses
- The framework's validation mechanism is used for input validation

**Concurrency Safety:**

- Concurrency primitives are appropriate for the detected runtime's threading model
- Shared mutable state is properly synchronized
- Connection pool sizing matches the runtime's concurrency model

**Testing Patterns:**

- Test utilities match the framework's current recommendations (no deprecated test annotations or helpers)
- Integration tests use the ecosystem's standard approach

If the detected stack is unfamiliar, apply the universal review criteria from Step 2 and note that framework-specific checks could not be applied.

### Step 4 - Delegate (if scope includes)

- **+Perf**: delegate to `task-code-perf-review`
- **+Security**: delegate to `task-code-secure`

## Feedback Labels

| Label        | Meaning       | Required |
| ------------ | ------------- | -------- |
| [Blocker]    | Must fix      | Yes      |
| [Suggestion] | Would improve | No       |
| [Question]   | Need clarity  | Clarify  |
| [Nitpick]    | Minor         | No       |
| [Praise]     | Done well     | -        |

## Rules

- Review the whole change, not just individual files
- Check for consistency with existing codebase patterns
- Provide actionable feedback with examples
- Acknowledge good work alongside issues
- Do not apply conventions from one stack to another

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Stack Detected:** [language / framework]
**Done Well:**

- [Positive 1]

## Findings

### [Blocker] Location

- Issue: [description]
- Why: [impact]

### [Suggestion] Location

- [improvement idea]

## Key Takeaways

[Summary]
```

## Key Skills Reference

- Use skill: `coding-standards` for stack-specific conventions
- Use skill: `api-guidelines` for REST endpoint patterns
- Use skill: `architecture-guardrail` for layer violations
- Use skill: `concurrency-model` for concurrency patterns
- Use skill: `observability` for logging and metrics
- Use skill: `resiliency` for fault tolerance

## Success Criteria

A well-executed code review passes all of these. Use as a self-check before posting findings.

### Completeness

- [ ] Correctness, readability, maintainability, and testing are all assessed
- [ ] Framework-specific checks for the detected stack are applied
- [ ] Every Blocker finding states why it must be fixed - not just what is wrong
- [ ] Assessment (Approve / Request Changes / Discuss) is stated upfront in the Summary

### Signal Quality

- [ ] No findings are purely stylistic where no project standard exists
- [ ] No findings based on personal preference
- [ ] Suggestions are genuine improvements that add value, not alternatives of equal merit
- [ ] Good work is acknowledged - Done Well section is not left empty when quality is present

### Staff-Level Signal (for tech lead review)

- [ ] The review assesses the change in context of the existing codebase patterns
- [ ] Blockers are blockers - not things the reviewer would prefer but that don't affect correctness
- [ ] Key Takeaways convey the most important signal from the review in 2-3 bullets
- [ ] Scope is respected - performance or security sub-reviews are not run unless requested

## Avoid

- Nitpicking style when no standard exists
- Blocking on personal preference
- Reviewing without understanding context
- Applying conventions from one stack to another

## After This Skill

If the output needed significant adjustment - findings were off-target, the wrong scope ran, or the assessment missed key context - run `/task-skill-feedback` to log what changed and why.
