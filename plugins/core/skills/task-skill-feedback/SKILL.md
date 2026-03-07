---
name: task-skill-feedback
description: Capture feedback on skill output quality - record what was useful, what was adjusted, and why, to inform future skill iterations.
metadata:
  category: meta
  tags: [feedback, skill-quality, learning, continuous-improvement]
  type: workflow
user-invocable: true
---

# Skill Feedback Capture

> **Meta skill**: This is a plugin improvement utility, not a software engineering workflow. Use it after running any skill to log output quality and surface patterns for skill authors.

## Purpose

Record structured feedback on skill output quality after using any workflow skill:

- **Capture adjustments** - what the user changed or overrode in the skill output
- **Surface patterns** - recurring gaps across multiple skill uses
- **Produce a local log** - `skill-feedback.md` at the repo root that accumulates over time
- **Inform skill evolution** - feedback entries become concrete improvement signals for skill authors

This skill writes feedback to a local file. It does not send data anywhere.

## When to Use

- After using any skill and finding the output needed significant adjustment
- After using a skill and finding it worked better than expected (positive signal is equally valuable)
- When you notice a recurring gap across multiple uses of the same skill
- When you want to document why a skill output was overridden before the context is lost

## Inputs

| Input             | Required | Description                                                               |
| ----------------- | -------- | ------------------------------------------------------------------------- |
| Skill name        | Yes      | Which skill was used (e.g., `task-code-review`, `task-release-plan`)      |
| Rating            | Yes      | Overall usefulness: Excellent / Good / Partial / Poor                     |
| What worked       | No       | Parts of the output that were used as-is or needed only minor edits       |
| What was adjusted | No       | Parts of the output that were changed, overridden, or discarded           |
| Why adjusted      | No       | Reason the adjustment was needed (missing context, wrong assumption, etc) |
| Suggested fix     | No       | Concrete change that would have produced a better output                  |

If the user provides minimal input, ask one clarifying question: "What would have made the output more useful?"

## Workflow

### Step 1 - Identify the Skill and Session

Ask or infer from context:

- Which skill was invoked
- Rough summary of what the skill was asked to do (feature type, stack, scope)
- Date of the session (use today's date if not specified)

Do not require exact reproduction of the full skill invocation - a brief description is sufficient.

### Step 2 - Capture the Rating

Prompt for a rating if not provided:

```
How useful was the skill output overall?

  Excellent - Used the output with no meaningful changes
  Good      - Used the output with minor adjustments
  Partial   - Used parts of it; significant sections were rewritten
  Poor      - Output missed the mark; started over or ignored it
```

### Step 3 - Capture Adjustment Details

For ratings of Partial or Poor, ask:

1. **What was adjusted or discarded?** - specific sections, recommendations, or output format elements
2. **Why was it adjusted?** - wrong assumption, missing context, too generic, wrong stack, other
3. **What would have made it better?** - concrete suggestion (e.g., "the risk section ignored our monorepo structure")

For ratings of Excellent or Good, ask:

1. **What worked well?** - which part of the output was most valuable

Keep this conversational - one or two sentences per question is enough.

### Step 4 - Write to skill-feedback.md

Append a new entry to `skill-feedback.md` at the project root. If the file does not exist, create it with the header first.

**File header (create once):**

```markdown
# Skill Feedback Log

Local feedback log for tuyens-agent-skills. Entries are appended by `/task-skill-feedback`.
Use this file to track recurring gaps and inform skill improvement requests.

---
```

**Entry format:**

```markdown
## [skill-name] - [YYYY-MM-DD]

**Rating:** [Excellent | Good | Partial | Poor]
**Context:** [1-2 sentences: what the skill was asked to do, stack/scope if relevant]

**What worked:**
[What was used as-is or needed only minor edits. Omit if Poor rating.]

**What was adjusted:**
[What changed, what was discarded, or what was ignored. Omit if Excellent rating.]

**Why:**
[Root cause: wrong assumption, missing context, too generic, wrong stack, etc.]

**Suggested fix:**
[Concrete improvement: "Add X to step Y", "Default to Z when stack is unknown", etc. Omit if no suggestion.]

---
```

Omit empty fields. Do not include fields with "N/A" or blank values.

### Step 5 - Summarize Patterns (Optional)

If `skill-feedback.md` already contains 3 or more entries for the same skill, offer a brief pattern summary:

```
I notice 3 feedback entries for `task-code-review`. Common theme: [pattern].
Consider opening an improvement request against the skill author.
```

This is optional - only surface it if a clear pattern exists. Do not force a pattern if entries are unrelated.

## Output

Confirmation message after writing:

```
Feedback recorded in skill-feedback.md.

  Skill:   [skill-name]
  Rating:  [rating]
  Date:    [YYYY-MM-DD]

[Optional: "3 entries now logged for this skill. Pattern: [summary]."]
```

No other output. The feedback log is the artifact.

## Output Constraints

- Append only - never overwrite existing entries in `skill-feedback.md`
- Each entry must be separated by `---`
- Keep entries concise: 5-10 lines per entry is the target
- Do not include PII, secrets, or internal code in the feedback log
- Suggested fixes must be concrete and actionable, not generic ("make it better")

## Rules

- If the user provides a rating of Excellent with no other context, write the entry with just the rating and a note that no adjustments were needed - this is valid positive signal
- Do not prompt for more information than necessary - two to three targeted questions maximum
- Do not generate the feedback entry until you have at least a skill name and a rating
- Never truncate or edit previous entries when appending
