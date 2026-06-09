---
name: review-report-writer
description: Write review report to Markdown with checkpoint frontmatter (head_sha, base_sha, round, mode) so the next round can auto-detect incremental scope.
metadata:
  category: review
  tags: [review, report, output, file, checkpoint, incremental]
user-invocable: false
---

# Review Report Writer

## When to Use

Final step of every `task-*-review*` workflow after findings have been assembled. Persists the full review and embeds a checkpoint so the next invocation on the same branch can auto-detect incremental re-review scope without user flags.

## Inputs

The consuming workflow passes these fields when invoking this skill:

| Field             | Required          | Source                                                                              |
| ----------------- | ----------------- | ----------------------------------------------------------------------------------- |
| `report_type`     | yes               | `review` / `review-perf` / `review-security` / `review-observability`               |
| `report_body`     | yes               | The full assembled Markdown report (no frontmatter)                                 |
| `branch`          | yes               | Resolved current branch name (or `detached`)                                        |
| `base_ref`        | yes               | From `review-precondition-check` handle                                             |
| `base_sha`        | yes               | `git rev-parse <base_ref>` output captured by the workflow                          |
| `head_ref`        | yes               | From `review-precondition-check` handle                                             |
| `head_sha`        | yes               | `git rev-parse <head_ref>` output captured by the workflow                          |
| `mode`            | yes               | `full` or `incremental`                                                             |
| `round`           | yes               | `1` for first review on this branch; increment per re-review                        |
| `prior_head_sha`  | only if `round>1` | The `head_sha` from the prior round's frontmatter                                   |
| `scope`           | yes               | `core-only` / `+perf` / `+sec` / `+obs` / `full`                                    |
| `depth`           | yes               | `quick` / `standard` / `deep`                                                       |
| `stack`           | yes               | Stack identifier from `stack-detect` (e.g., `java-spring-boot`, `unknown`)          |

## Rules

- If any required input from the Inputs table is missing or empty, halt and return `Missing required input: <field>` to the caller. Do not write a partial file, do not invent a default, do not blank the field.
- Sanitize `branch` for the filename: replace `/` and any character outside `[A-Za-z0-9_-]` with `-`, collapse consecutive `-`, strip leading/trailing `-`.
- Build the filename from `report_type`:
  - `review` -> `review-<branch>.md`
  - `review-perf` -> `review-perf-<branch>.md`
  - `review-security` -> `review-security-<branch>.md`
  - `review-observability` -> `review-observability-<branch>.md`
- Write a file containing the frontmatter (below) immediately followed by `report_body`.
- Overwrite without prompting - the file is a rolling checkpoint, not an archive. Round history lives inside the report body.
- Run no git command (the workflow already captured `base_sha` and `head_sha`).
- Print one confirmation line after writing:

  ```
  Report written to <filename> (round <N>, mode: <mode>)
  ```

## Frontmatter Contract

Emit exactly this block at the top of the file. Emit `prior_head_sha` whenever `round > 1`, independent of `mode` - a full re-review on round 2+ still records the prior round's head for chain continuity. `generated_at` is the writer's current UTC time (ISO 8601, `Z` suffix); the workflow does not pass it.

```yaml
---
branch: <branch>
base_ref: <base_ref>
base_sha: <full SHA>
head_ref: <head_ref>
head_sha: <full SHA>
mode: full | incremental
round: <N>
prior_head_sha: <full SHA from prior round>   # omit on round 1; required on round 2+
scope: core-only | +perf | +sec | +obs | full
depth: quick | standard | deep
stack: <stack identifier>
generated_at: <ISO 8601 UTC timestamp>
---
```

This frontmatter is the **checkpoint contract** consumed by `review-precondition-check` on the next round. Do not add, rename, or drop fields; downstream parsing depends on exact names.

## Output Format

```
Report written to <filename> (round <N>, mode: <mode>)
```

The file contains the YAML frontmatter followed by the workflow's standard Markdown report body.

## Avoid

- Writing a partial or summarized report
- Emitting frontmatter without the trailing `---` delimiter (breaks the next round's parse)
- Creating subdirectories or archiving prior rounds to separate files
- Running git commands - the workflow supplies all SHAs
- Inventing fields not in the contract or renaming existing ones
