---
name: task-pr-create
description: Generate a production-ready PR description from git diff. Writes title, summary, risk level, test plan, and links to related tickets or ADRs. Not for code review. Does not create the PR via CLI - generates the description text only.
metadata:
  category: workflow
  tags: [pull-request, pr-description, git, collaboration, documentation]
  type: workflow
user-invocable: true
---

# PR Description Generator

## Purpose

Turn a git diff into a complete, reviewer-ready pull request description in one command:

- **Title** - concise, imperative, under 72 characters
- **Summary** - what changed and why (not how)
- **Risk classification** - helps reviewers calibrate attention
- **Test plan** - what to verify before merging
- **Linked context** - tickets, ADRs, related PRs surfaced from commit messages and CLAUDE.md

This skill writes the PR description. It does not open or submit the PR.

## When to Use

- After finishing a feature, fix, or refactor branch and before opening the PR
- When you want a consistent, complete PR description without writing it manually
- When the diff is large and you need a clear summary to orient reviewers

## Inputs

| Input                    | Required | Source                                                        |
| ------------------------ | -------- | ------------------------------------------------------------- |
| Git diff or file list    | Yes      | `git diff main...HEAD` or paste diff directly                 |
| Commit messages          | Yes      | `git log main...HEAD --oneline`                               |
| Ticket / issue reference | No       | Branch name, commit message, or user-provided (e.g. JIRA-123) |
| ADR references           | No       | Mentioned in commit messages or `docs/adr/` directory         |
| Related PRs              | No       | User-provided or referenced in commit messages                |

If no diff is provided, run `git diff main...HEAD` to obtain it. If the base branch is not `main`, ask the user for the base branch before proceeding.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling. This informs test plan language (e.g., "run `./gradlew test`" vs `pytest` vs `go test ./...`).

### Step 2 - Gather Context

Run or ask for:

1. **Diff**: `git diff main...HEAD` (or supplied by user)
2. **Commits**: `git log main...HEAD --oneline --no-merges`
3. **Branch name**: `git rev-parse --abbrev-ref HEAD`
4. **Changed files**: `git diff main...HEAD --name-only`

Extract from the above:

- **Ticket references**: patterns like `PROJ-123`, `#123`, `closes #`, `fixes #`, `resolves #` in branch name or commit messages
- **ADR references**: mentions of `ADR-`, `adr/`, or `docs/decisions/` in commits or diff
- **Related PRs**: mentions of `PR #`, `pull/`, or sibling branch names in commits

### Step 3 - Classify Risk

Use skill: `pr-risk-analysis`

Produce a single-line risk output:

```
Risk: Low | Medium | High | Critical  -  [1-2 sentence rationale]
```

This appears verbatim in the PR description to orient reviewers immediately.

### Step 4 - Write PR Description

Compose the description following the Output Format below.

**Title rules:**

- Imperative mood: "Add", "Fix", "Refactor", "Remove", "Update" - not "Added" or "Adding"
- Under 72 characters
- No ticket number in the title (goes in the body)
- Format: `<type>: <what changed>` where type is one of: `feat`, `fix`, `refactor`, `perf`, `chore`, `docs`, `test`

**Summary rules:**

- Explain the _why_ (motivation, problem being solved) more than the _what_ (code mechanics)
- 3-5 bullet points; each starts with a verb
- Do not re-describe the diff line by line
- Reference the ticket/ADR inline if it provides essential context

**Test Plan rules:**

- Concrete, runnable steps - not "test it works"
- Include the exact test command for the detected stack
- Add manual verification steps for UI/API changes
- Add migration steps if a DB migration is included

**Checklist rules:**

- Only include items relevant to this specific PR
- Skip items that don't apply (don't list empty boxes for non-applicable items)

### Step 5 - Surface Linked Context

At the bottom of the PR description, add a **Linked Context** section only if at least one of the following exists:

- A ticket reference was found → link as `Closes PROJ-123` / `Ref #123`
- An ADR reference was found → link by title if resolvable, otherwise by path
- A related PR was found → reference by number or branch name

If nothing was found, omit the section entirely - do not add empty placeholders.

## Output Format

```markdown
## [type]: [concise imperative title under 72 chars]

### Summary

- [Why this change was needed / what problem it solves]
- [What changed at a high level - domain, layer, component]
- [Any notable design decision or trade-off made]

### Risk

**[Low | Medium | High | Critical]** - [1-2 sentence rationale based on change signals]

### Test Plan

- [ ] Run tests: `[stack-appropriate test command]`
- [ ] [Manual verification step 1 - e.g., "Call POST /api/v1/orders and verify 201 response"]
- [ ] [Manual verification step 2 - e.g., "Check that existing orders are unaffected"]
- [ ] [Migration step if applicable - e.g., "Run `./gradlew flywayMigrate` on staging before deploying"]

### Checklist

- [ ] Tests added or updated for new behaviour
- [ ] No secrets, tokens, or PII introduced
- [ ] Migration is reversible (if applicable)
- [ ] Breaking API changes are documented (if applicable)

### Linked Context

Closes [TICKET-ID](link-if-available)
ADR: [ADR title or path]
Related: #[PR number or branch]
```

### Output Constraints

- Title is the first line with `##` prefix - not a separate field
- Risk always appears before Test Plan - it frames reviewer attention
- Omit any section that has no content (e.g., omit Linked Context if nothing found)
- Do not include implementation details visible in the diff - orient reviewers, don't duplicate the diff
- Test plan must include at least one runnable command for the detected stack
- Keep total PR description under 400 words - reviewers read it, not file it

## Rules

- Never invent ticket IDs or ADR titles that don't appear in the git context
- If the diff is empty or the branch has no commits ahead of base, say so and stop
- If the diff is too large to summarize meaningfully (500+ files), ask the user to scope the input
- Do not include personal opinions about code quality - this is documentation, not review
- Risk classification from Step 3 must be the only risk assessment - do not add a second one inline
