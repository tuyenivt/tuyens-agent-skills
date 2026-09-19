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
| `branch`          | yes               | `head_short_name` from the `review-precondition-check` handle - the name the checkpoint keys on (`feature/x`), never `HEAD` and never remote-prefixed |
| `base_ref`        | yes               | From `review-precondition-check` handle                                             |
| `base_sha`        | yes               | `git rev-parse <base_ref>` output captured by the workflow                          |
| `head_ref`        | yes               | From `review-precondition-check` handle - the ref the diff used (`origin/feature/x`, `pr-42`, or the same name as `branch`) |
| `head_sha`        | yes               | `git rev-parse <head_ref>` output captured by the workflow                          |
| `mode`            | yes               | `full` - the only accepted value; anything else fails validation. Every round analyzes the full `base...head` range; the field stays in the frontmatter so pre-change reports still parse on the next round's lookup |
| `round`           | yes               | `1` for first review on this branch; increment per re-review                        |
| `prior_head_sha`  | only if `round>1` | The `head_sha` from the prior round's frontmatter                                   |
| `scope`           | yes               | `core-only` / `full` / one to three of `+perf` `+sec` `+obs` `+rel`, space-joined in that order (all four lenses are passed as `full`; the four-flag string is invalid) |
| `depth`           | yes               | `standard` / `deep`                                                                 |
| `stack`           | yes               | Stack identifier from `stack-detect` (e.g., `java-spring-boot`, `unknown`)          |
| `pr_url`          | no                | PR/MR URL if the review input carried one (e.g., a pasted GitHub PR link), or copied through from the prior checkpoint |

Only the workflow that owns the report invokes this skill. Sub-agents spawned for extra scopes return findings to the parent and never write - the parent supplies every field above. No field is optional for any caller except `prior_head_sha` on round 1 and `pr_url`. A plain core review (workflows display `Scope: Core`, with or without the `core-only` user flag) passes `scope: core-only`; there is no separate `core` value.

## Rules

- Validate every input before anything else runs, and report all failures at once - one line per bad field (the first matching check below wins), in the input table's row order, so the caller fixes them in a single pass:
  - Missing or empty required field -> `Missing required input: <field>`
  - `branch` equal to `HEAD` or starting with `refs/` -> `Invalid input: branch: <value>` (stripping a remote prefix is `review-precondition-check`'s job, done before this skill runs)
  - `base_sha`, `head_sha`, or `prior_head_sha` not matching `[0-9a-f]{40}` (`[0-9a-f]{64}` in a SHA-256 repo) -> `Invalid input: <field>: <value>` - an abbreviated SHA defeats the next round's same-SHA equality check
  - Value-set field (`report_type`, `mode`, `depth`) holding a value outside its set, or `scope` not matching the grammar above -> `Invalid input: <field>: <value>`
  - `round` not a positive integer -> `Invalid input: round: <value>` - a malformed round writes clean today and breaks the next round's checkpoint parse into legacy, losing the chain
  - `round` valid and greater than 1 with no `prior_head_sha` -> `Missing required input: prior_head_sha` (this check is skipped when `round` itself is invalid)
- On any failure: emit the failure lines and stop. Do not write a partial file, invent a default, or blank a field. Value sets are matched exactly, case included: `Core` and `Deep` are invalid, not variants of `core-only` and `deep` - mapping display values to enum values is the caller's job.
- **`report_body` is raw Markdown, never fenced.** The consuming workflow's Output Format section shows its template inside a fence for display only; that fence is not part of the report. When the body's first line is a fence opener (three or more backticks or tildes) and its last non-blank line is a fence of the same character with at least the opener's count, those two lines are the workflow's display wrapper: strip both and write what is between them. Otherwise the body is not wrapped and every fence in it (a code sample on a Fix line) is content - keep it.
- Sanitize `branch` for the filename: replace `/` and any character outside `[A-Za-z0-9_-]` with `-`, collapse consecutive `-`, lowercase, cut to 100 characters, then strip leading/trailing `-`; an empty result becomes `unnamed`. The frontmatter `branch` field keeps the raw value; only the filename is sanitized. `review-precondition-check` applies the same function on the next round.
- Build the filename as `<report_type>-<sanitized branch>.md` (`review-feature-x.md`, `review-perf-feature-x.md`). The scheme is many-to-one: a `review` report on a branch that starts with `perf-` shares a filename with a `review-perf` report on the rest of the name, and `feature/x` shares one with `Feature-X`; the `report_type` and raw `branch` frontmatter fields let the next round detect either mismatch.
- Write the file in the repository root (the workflow runs there; next round's `review-precondition-check` looks for it there): the frontmatter (below), then `report_body` starting on the line after the closing `---` (no blank line inserted; the body's own leading blank lines are kept). Write UTF-8 with LF line endings.
- Overwrite without prompting - the file is a rolling checkpoint, not an archive. Round history lives inside the report body.
- Run no git command (the workflow already captured `base_sha` and `head_sha`).
- Print one confirmation line after writing:

  ```
  Report written to <filename> (round <N>)
  ```

## Frontmatter Contract

Emit exactly this block at the top of the file, one field per line, no comments; the brace annotations on the two conditional lines are authoring notes, never emitted. Every field except the enums (`report_type`, `mode`, `scope`, `depth`, `stack`) and `round` is double-quoted, because a bare value could parse as a YAML timestamp, number, or boolean; a `"` or `\` inside a quoted value is escaped with a preceding `\`. Emit `prior_head_sha` only when `round > 1`; emit `pr_url` only when the caller passed a non-empty value (never write `pr_url:` with a blank value). `generated_at` is the writer's current UTC time (`date -u +%Y-%m-%dT%H:%M:%SZ`) as `YYYY-MM-DDTHH:MM:SSZ`; the workflow does not pass it.

```yaml
---
report_type: {report_type}
branch: "{branch}"
base_ref: "{base_ref}"
base_sha: "{full SHA}"
head_ref: "{head_ref}"
head_sha: "{full SHA}"
mode: {mode}
round: {N}
prior_head_sha: "{full SHA from prior round}"   {only when round > 1}
scope: {scope}
depth: {depth}
stack: {stack identifier}
pr_url: "{PR/MR URL}"   {only when a non-empty pr_url was passed}
generated_at: "{YYYY-MM-DDTHH:MM:SSZ}"
---
```

This frontmatter is the **checkpoint contract** consumed by `review-precondition-check` on the next round. Beyond the conditional `pr_url` and `prior_head_sha` lines, do not add, rename, or drop fields; downstream parsing depends on exact names.

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
