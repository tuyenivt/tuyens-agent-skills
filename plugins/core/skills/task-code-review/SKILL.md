---
name: task-code-review
description: Standard code review for PRs - correctness, readability, maintainability, and test coverage. Auto-detects project stack. Not for architecture or design review (use task-design-architecture), not for security-only audit (use task-code-secure), and not for high-risk AI-generated code (use task-code-review-advanced).
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

## Depth Levels

| Depth      | When to Use                                             | What Runs                               |
| ---------- | ------------------------------------------------------- | --------------------------------------- |
| `quick`    | Trivial changes, hotfix, or "is this safe to merge?"    | Correctness + top 2-3 findings only     |
| `standard` | Default - routine PRs                                   | Steps 2-4 (full review)                 |
| `deep`     | Complex refactors, unfamiliar code, or cross-module PRs | Full review + pattern consistency check |

Default: `standard`. Use `quick` when user asks for "quick look", "sanity check", or "is this ok?".

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
- Edge cases handled (empty input, nulls, boundary values)
- Error paths considered - external calls, I/O, and parsing have failure handling

**Readability:**

- Self-documenting code
- Clear naming
- Appropriate complexity

**Maintainability:**

- Changes are focused and scoped
- Follows existing patterns in the codebase
- No unnecessary coupling
- No hardcoded values (URLs, credentials, magic numbers) - use config or constants

**Testing:**

- New behavior has tests: happy path + at least one error/edge case
- Tests are meaningful - not just coverage theater

### Step 3 - Framework-Specific Checks

Use skill: `coding-standards` for naming, structure, and anti-pattern enforcement.
Use skill: `concurrency-model` if concurrency patterns are present in the change.
Use skill: `observability` to check logging, metrics, and tracing coverage.
Use skill: `resiliency` for error handling, retry, and circuit breaker patterns.
Use skill: `api-guidelines` if the change touches API contracts or HTTP endpoints.

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

**Data Access:**

- No N+1 query patterns (loops that trigger per-row queries)
- Queries are bounded - no unbounded fetches without pagination or limit
- Transactions are scoped correctly and not held across I/O

**Configuration Hygiene:**

- No hardcoded URLs, secrets, credentials, or environment-specific values in code
- Magic numbers or strings are named constants or configuration entries

**Error Handling:**

- External service calls (HTTP, messaging, DB) have explicit error handling
- Failures return meaningful errors rather than swallowing exceptions or returning null
- Happy path and error path are both covered in tests

**Concurrency Safety:**

- Concurrency primitives are appropriate for the detected runtime's threading model
- Shared mutable state is properly synchronized
- Connection pool sizing matches the runtime's concurrency model

**Testing Patterns:**

- New behavior has tests covering at least: happy path, primary error path, and one edge case
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
