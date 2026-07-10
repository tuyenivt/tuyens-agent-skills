---
name: task-pr-create
description: Generate PR title and description from a git diff: summary, risk level, test plan, linked context for reviewers.
metadata:
  category: code
  tags: [pull-request, pr-description, git, collaboration, documentation]
  type: workflow
user-invocable: true
---

# PR Description Generator

Turns a git diff into a reviewer-ready PR description: title, summary, risk, test plan, linked context. Writes the description; does not open or submit the PR.

## When to Use

- After finishing a feature, fix, or refactor branch, before opening the PR
- When the diff is large and reviewers need a clear summary
- When you want a consistent format without writing it by hand

**Not for:** code-quality review (`task-code-review`), release notes (`task-release-notes`).

## Inputs

| Input                | Required | Source                                          |
| -------------------- | -------- | ----------------------------------------------- |
| Git diff / file list | Yes      | `git diff <base>...HEAD` or pasted              |
| Commit messages      | Yes      | `git log <base>...HEAD --oneline`               |
| Ticket reference     | No       | Branch name, commit message, or user-supplied   |
| ADR references       | No       | Commit messages or `docs/adr/`                  |
| Related PRs          | No       | Commit messages or user-supplied                |

The base branch is detected in Step 2; the user does not supply it unless detection fails.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Resolve Branch and Base

Establish `(base_ref, head_ref)` before any diff is read. PR creation runs against the current feature branch only.

1. **Resolve head:** `head_ref = HEAD`; `current_branch = git rev-parse --abbrev-ref HEAD`.
2. **Reject trunk heads:** if `current_branch` is `main`, `master`, `develop`, or `trunk` (case-insensitive), stop:

   ```text
   You are on `<current_branch>`, a trunk branch. Nothing scoped to describe.
   Switch to your feature branch and re-run.
   ```

3. **Detect base** in order; first that succeeds wins:
   1. `git symbolic-ref refs/remotes/origin/HEAD`
   2. `git rev-parse --verify origin/main`, then `origin/master`, then `origin/develop`
   3. `git rev-parse --verify main`, then `master`, then `develop`
4. **Ask only if ambiguous:** if none resolve - or `origin/HEAD` is unset and more than one trunk candidate resolves (e.g., gitflow with both `main` and `develop`) - ask the user. Do not pick silently; the wrong base pulls unrelated commits into the diff.

Record `base_ref` for Step 4.

### Step 3 - Detect Stack

Use skill: `stack-detect` to inform test commands in the test plan (e.g., `./gradlew test`, `pytest`, `go test ./...`).

### Step 4 - Gather Context

Run or accept:

1. `git diff <base_ref>...HEAD`
2. `git log <base_ref>...HEAD --oneline --no-merges`
3. `current_branch` from Step 2
4. `git diff <base_ref>...HEAD --name-only`

If the diff is empty, stop and tell the user. If `git status --porcelain` shows uncommitted changes, warn that they are excluded - the description covers committed work only.

Extract from above:

- **Tickets:** `PROJ-123`, `#123`, `closes #`, `fixes #`, `resolves #` in branch or commits
- **ADRs:** `ADR-`, `adr/`, `docs/decisions/` mentions
- **Related PRs:** `PR #`, `pull/`, sibling branch names in commits

### Step 5 - Classify Risk

Use skill: `review-pr-risk`. Condense its output into the Risk section of the Output Format:

- `Risk Level:` + `Signals:` become `**[Low | Medium | High | Critical]** - [1-2 sentence rationale]`
- If it emits `Action:` (e.g., split PR, require additional reviewer), append it as a second line under Risk: `Suggested action: [action]`. Never drop it.

### Step 6 - Write the PR Description

Compose using the Output Format below.

**Title:**
- Imperative ("Add", "Fix", "Refactor") - not "Added" / "Adding"
- Under 72 characters; no ticket number (goes in body)
- Format: `<type>: <what changed>` where type is `feat`, `fix`, `refactor`, `perf`, `chore`, `docs`, or `test`
- Mixed concerns: pick the type of the dominant user-facing change (a bugfix wrapped in refactoring is `fix`)

**Summary:**
- Explain the *why* (problem, motivation) more than the *what* (mechanics)
- Up to 5 bullets, each starting with a verb; proportional to the diff (a trivial change needs one)
- If the *why* is not inferable from diff, commits, or ticket, ask the user - do not invent it
- Reference ticket/ADR inline only if essential context

**Test Plan:**
- Concrete, runnable steps. Include the exact test command for the detected stack when production code changed; docs-only changes need only a relevant verification step (e.g., render check).
- Manual verification for UI/API changes; migration steps when applicable.
- New infrastructure dependency (Redis, DB, broker): include the setup step (e.g., `docker-compose up -d redis`).

**Checklist:** include only items relevant to this PR; omit non-applicable items.

### Step 7 - Surface Linked Context

Add a **Linked Context** section only if at least one of: ticket reference, ADR reference, related PR. If none found, omit entirely - no empty placeholders.

## Output Format

```markdown
## [type]: [imperative title under 72 chars]

### Summary

- [Why this change was needed / problem solved]
- [What changed at a high level - domain, layer, component]
- [Notable design decision or tradeoff]

### Risk

**[Low | Medium | High | Critical]** - [1-2 sentence rationale]
Suggested action: [only if `review-pr-risk` emitted `Action:`; otherwise omit this line]

### Test Plan

- [ ] Run tests: `[stack-appropriate command]`
- [ ] [Manual verification step 1 - e.g., "POST /api/v1/orders returns 201"]
- [ ] [Manual verification step 2]
- [ ] [Migration step if applicable - e.g., "Run `./gradlew flywayMigrate` on staging before deploy"]

### Deployment Notes

_{Include only when there are deployment-time implications: new infrastructure dependency, config change, behavior change to existing endpoints, or feature flag. Otherwise omit.}_

- {consideration}

### Checklist

- [ ] Tests added or updated for new behavior
- [ ] No secrets, tokens, or PII introduced
- [ ] Migration is reversible (if applicable)
- [ ] Breaking API changes documented (if applicable)

### Linked Context

Closes [TICKET-ID](link-if-available)
ADR: [ADR title or path]
Related: #[PR number or branch]
```

## Output Constraints

- Title is the first line with `##` prefix - not a separate field
- Risk appears before Test Plan
- Omit sections with no content
- No line-by-line diff description - orient reviewers, do not duplicate the diff
- Test plan includes at least one runnable command for the detected stack when production code changed
- Total description under 400 words

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: branch and base resolved; trunk-branch HEAD rejected; base auto-detected or asked when ambiguous
- [ ] Step 3: stack detected and reflected in test plan command
- [ ] Step 4: diff and commits gathered against resolved `base_ref`, not hardcoded `main`
- [ ] Step 5: risk classification present with rationale; `Action:` from `review-pr-risk` carried over if emitted
- [ ] Step 6: title imperative, under 72 chars, type-prefixed; summary explains *why*, not *how*; test plan has a runnable command when production code changed
- [ ] Step 7: Linked Context only when real references exist; nothing invented
- [ ] Empty sections omitted; total under 400 words

## Avoid

- Inventing ticket IDs, ADR titles, PR references, or motivations not found in git context
- Duplicating the diff in the summary - orient, do not re-describe
- Vague test plans ("test it works") instead of concrete commands
- Personal opinions about code quality - this is documentation, not review
- Empty placeholder sections (Linked Context with no content)
- Adding a second inline risk rating after Step 5's classification
