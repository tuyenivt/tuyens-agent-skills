---
name: task-code-review
description: Standard code review for PRs - correctness, readability, maintainability, and test coverage. Auto-detects project stack and applies framework-specific checks. Use for routine PRs and pre-merge quality checks.
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

**Not for:** Architecture/design review (use `task-design-architecture`), security-only audit (use `task-code-secure`), high-risk or AI-generated PRs (use `task-code-review-advanced`).

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

After loading stack-detect, apply framework-specific review criteria based on the detected ecosystem. The atomic skills above handle detailed pattern enforcement. In addition, check these cross-cutting concerns:

**Language and Framework Fit:**

- Code uses modern language features and current idioms - no deprecated patterns or APIs
- Layering follows the framework's recommended architecture (controllers/handlers → services → data access)
- Dependency injection and response shaping use the framework's standard mechanisms
- ORM entities are not exposed in API responses

**Data Access:**

- No N+1 query patterns (loops that trigger per-row queries)
- Queries are bounded - no unbounded fetches without pagination or limit
- Transactions are scoped correctly and not held across I/O

**Configuration Hygiene:**

- No hardcoded URLs, secrets, credentials, or environment-specific values in code
- Magic numbers or strings are named constants or configuration entries

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

### [Blocker] file:line

- Issue: [what is wrong]
- Why: [impact on correctness, reliability, or maintainability]
- Fix: [concrete code change or approach]

### [Suggestion] file:line

- Issue: [what could be improved]
- Fix: [specific improvement]

## Key Takeaways

- [2-3 bullets summarizing overall quality and what to address before merge]
```

**Example finding (good depth):**

```markdown
### [Blocker] PaymentWebhookController.java:45

- Issue: Webhook signature verification happens after the request body is parsed and partially processed
- Why: An attacker can trigger side effects (order status update) with a forged webhook payload before verification fails
- Fix: Move `verifySignature(request)` to the first line of the handler, before any business logic executes
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading. Always include at least one [Praise] in Done Well.

## Self-Check

- [ ] Stack detected and framework-specific checks applied (or noted as unfamiliar)
- [ ] Every finding has a label, location (file:line), and actionable fix
- [ ] Findings ordered: Blocker > Suggestion > Question > Nitpick
- [ ] At least one [Praise] included in Done Well
- [ ] Key Takeaways summarize the overall assessment - Summary alone is enough for an Approve/Request Changes decision
- [ ] No framework conventions applied from a different stack than detected

## Avoid

- Reviewing without reading the full diff first
- Applying conventions from one stack to another (e.g., Java conventions on Go code)
- Nitpicking style where no project standard exists
- Providing vague feedback without a concrete fix ("this could be better")
- Blocking on personal preference rather than correctness or maintainability
- Commenting on every file - focus on the most impactful findings
