---
name: review-gap-analysis
description: Analyze why existing review processes failed to catch a production failure
metadata:
  category: governance
  tags: [review, gap-analysis, incident, quality-gate]
user-invocable: false
---

# Review Gap Analysis

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During postmortem to understand why safeguards failed
- When a production failure should have been caught during code review
- When evaluating review process effectiveness after an incident
- When identifying systemic review blind spots across multiple incidents

## Rules

- Focus on process gaps, not individual reviewer blame
- Every gap must identify what structural change would close it
- Distinguish between "missed in review" and "not reviewable with current process"
- Consider cognitive load as a legitimate contributing factor

## Pattern

### Gap Categories

| Category           | Question                                                             |
| ------------------ | -------------------------------------------------------------------- |
| Coverage gap       | Was the risky code path reviewed at all?                             |
| Context gap        | Did the reviewer have enough context to assess the risk?             |
| Checklist gap      | Was there a checklist item that would have caught this?              |
| Tooling gap        | Would automated analysis (lint, static analysis, CI) have caught it? |
| Expertise gap      | Did the reviewer have domain knowledge for this failure type?        |
| Cognitive load gap | Was the PR too large or complex for effective review?                |
| Architecture gap   | Was architectural drift visible in the diff?                         |
| Test gap           | Were test scenarios sufficient to exercise the failure path?         |
| Monitoring gap     | Would pre-deploy monitoring checks have flagged the risk?            |

### Analysis Structure

For each identified gap:

1. **Gap type** -- which category from above
2. **Why it existed** -- structural reason (not individual blame)
3. **What would close it** -- specific process or tooling change
4. **Enforcement** -- how to make the fix stick (automated check, checklist item, policy)

### Good: Specific gap with structural fix

```
Gap: Cognitive load gap
Why: PR changed 47 files across 3 modules. Reviewer approved after reviewing controller layer only.
Fix: Enforce PR size limit (max 15 files or 400 lines). Require module-owner review when changes span multiple modules.
Enforcement: CI check on PR size; CODEOWNERS file for cross-module changes.
```

### Bad: Blame-oriented analysis

```
The reviewer should have caught the missing null check on line 142.
```

## Avoid

- Blaming individual reviewers
- Assuming "more careful review" is a fix (it is not scalable)
- Ignoring cognitive load and PR size as contributing factors
- Proposing only manual process changes without automation support
- Treating review as the only quality gate (consider CI, testing, monitoring)
