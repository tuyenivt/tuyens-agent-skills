---
name: review-report-writer
description: Write the review report to Markdown with checkpoint frontmatter (head_sha, base_sha, round) so the next round can reconcile prior findings.
metadata:
  category: review
  tags: [review, report, output, file, checkpoint, re-review]
user-invocable: false
---

# Review Report Writer

## When to Use

Final step of every `task-*-review*` workflow after findings have been assembled. Persists the full review and embeds a checkpoint so the next invocation on the same branch is recognized as a re-review without user flags.

## Inputs

The consuming workflow passes these fields when invoking this skill:

| Field             | Required          | Source                                                                              |
| ----------------- | ----------------- | ----------------------------------------------------------------------------------- |
| `report_type`     | yes               | `review` / `review-perf` / `review-security` / `review-observability` / `review-reliability` |
| `report_body`     | yes               | The full assembled Markdown report (no frontmatter)                                 |
| `branch`          | yes               | Head short name from the `review-precondition-check` handle - the review target, which is also the checkpoint lookup key. Equals the current branch in the usual self-review case. |
| `base_ref`        | yes               | From `review-precondition-check` handle                                             |
| `base_sha`        | yes               | `git rev-parse <base_ref>` output captured by the workflow                          |
| `head_ref`        | yes               | From `review-precondition-check` handle                                             |
| `head_sha`        | yes               | `git rev-parse <head_ref>` output captured by the workflow                          |
| `mode`            | yes               | `full` - the only accepted value; anything else fails validation. Every round analyzes the full `base...head` range; the field stays in the frontmatter so pre-change reports still parse on the next round's lookup |
| `round`           | yes               | `1` for first review on this branch; increment per re-review                        |
| `prior_head_sha`  | only if `round>1` | The `head_sha` from the prior round's frontmatter                                   |
| `scope`           | yes               | `core-only` / `full` / one or more of `+perf` `+sec` `+obs` `+rel`, space-joined in that order (all four = `full`) |
| `depth`           | yes               | `standard` / `deep`                                                                 |
| `stack`           | yes               | Stack identifier from `stack-detect` (e.g., `java-spring-boot`, `unknown`)          |
| `pr_url`          | no                | PR/MR URL if the review input carried one (e.g., a pasted GitHub PR link)           |

Only the workflow that owns the report invokes this skill. Sub-agents spawned for extra scopes return findings to the parent and never write - the parent supplies every field above. No field is optional for any caller except `prior_head_sha` on round 1 and `pr_url` (present only when the review input carried a PR/MR URL). A plain core review (workflows display `Scope: Core`, with or without the `core-only` user flag) passes `scope: core-only`; there is no separate `core` value.

## Rules

- Validate every input before writing anything, and report all failures at once - one line per bad field, so the caller fixes them in a single pass instead of rediscovering them one re-run at a time:
  - Missing or empty required field -> `Missing required input: <field>`
  - Value-set field (`report_type`, `mode`, `scope`, `depth`) holding a value outside its set -> `Invalid input: <field>: <value>`
- Do not write a partial file, invent a default, or blank a field. Value sets are matched exactly, case included: `Core` and `Deep` are invalid, not variants of `core-only` and `deep` - mapping display values to enum values is the caller's job.
- **`report_body` is raw Markdown, never fenced.** The consuming workflow's Output Format section shows its template inside a ` ```markdown ` fence for display only; that fence is not part of the report. The written body must render as Markdown - real headings, tables, and lists, not one monospace block. If the received `report_body` opens with a fence on its first line, that fence is the workflow's display wrapper - strip it and its matching closer before writing. Match by fence length: a wrapper opened with more backticks than any fence it contains (a 4-backtick ````` ````markdown ````` opener around samples using 3-backtick ```` ``` ````) closes at its own backtick count, which disambiguates a body that ends with a code sample. An info string adds no length - ```` ```markdown ```` and ```` ``` ```` are both 3 backticks, which is the same-length case. When the opener and an inner fence are the same length, the wrapper's closer is the last fence in the body. Fenced blocks *inside* the body (a code sample on a Fix line) are content - keep them.
- Sanitize `branch` for the filename: replace `/` and any character outside `[A-Za-z0-9_-]` with `-`, collapse consecutive `-`, strip leading/trailing `-`. The frontmatter `branch` field keeps the raw value; only the filename is sanitized.
- Build the filename from `report_type`:
  - `review` -> `review-<branch>.md`
  - `review-perf` -> `review-perf-<branch>.md`
  - `review-security` -> `review-security-<branch>.md`
  - `review-observability` -> `review-observability-<branch>.md`
  - `review-reliability` -> `review-reliability-<branch>.md`
- Write the file in the current working directory (where the workflow runs - next round's `review-precondition-check` looks for it there): the frontmatter (below) immediately followed by `report_body`.
- Overwrite without prompting - the file is a rolling checkpoint, not an archive. Round history lives inside the report body.
- Run no git command (the workflow already captured `base_sha` and `head_sha`).
- Print one confirmation line after writing:

  ```
  Report written to <filename> (round <N>)
  ```

## Frontmatter Contract

Emit exactly this block at the top of the file. Emit `prior_head_sha` whenever `round > 1` - it records the prior round's head for chain continuity. Emit `pr_url` only when the caller passed a non-empty value; omit the line entirely otherwise (never write `pr_url:` with a blank value). `generated_at` is the writer's current UTC time (ISO 8601, `Z` suffix); the workflow does not pass it.

```yaml
---
branch: <branch>
base_ref: <base_ref>
base_sha: <full SHA>
head_ref: <head_ref>
head_sha: <full SHA>
mode: full
round: <N>
prior_head_sha: <full SHA from prior round>                     # omit on round 1; required on round 2+
scope: core-only | full | space-joined subset of +perf +sec +obs +rel in that order
depth: standard | deep
stack: <stack identifier>
pr_url: <PR/MR URL>                                             # omit unless the review input carried one
generated_at: <ISO 8601 UTC timestamp>
---
```

This frontmatter is the **checkpoint contract** consumed by `review-precondition-check` on the next round. Beyond the optional `pr_url` and `prior_head_sha` lines, do not add, rename, or drop fields; downstream parsing depends on exact names.

## Output Format

```
Report written to <filename> (round <N>)
```

The file contains the YAML frontmatter followed by the workflow's standard Markdown report body.

On validation failure, the output is the failure lines from Rules (one per bad field) and no file - there is no partial success.

## Avoid

- Writing a partial or summarized report
- Wrapping the report body in an outer code fence (renders the whole report as fixed-width text instead of Markdown)
- Emitting frontmatter without the trailing `---` delimiter (breaks the next round's parse)
- Creating subdirectories or archiving prior rounds to separate files
- Running git commands - the workflow supplies all SHAs
- Inventing fields not in the contract or renaming existing ones
