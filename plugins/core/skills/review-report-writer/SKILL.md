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
  - `base_sha`, `head_sha`, or `prior_head_sha` not matching `[0-9a-f]{40}` or `[0-9a-f]{64}` against the entire value (Ruby `\A...\z`, Python `re.fullmatch`, JavaScript `^...$` without the `m` flag; SHA-1 or SHA-256; a trailing newline fails), or a well-formed `head_sha` or `prior_head_sha` whose length differs from a well-formed `base_sha` (the length check runs only when both are well-formed) -> `Invalid input: <field>: <value>` for that field - an abbreviated SHA defeats the next round's same-SHA equality check; when `round` is invalid or `1`, a passed `prior_head_sha` is ignored, neither validated nor emitted
  - Value-set field (`report_type`, `mode`, `depth`) holding a value outside its set, or `scope` not matching the grammar above -> `Invalid input: <field>: <value>`
  - `round` not matching `[1-9][0-9]*` against the entire value, checked as the SHAs are (canonical decimal: no sign, leading zero, `_`, or trailing newline - YAML 1.1 parsers such as PyYAML and Psych read `010` as 8 and `08` as a string, YAML 1.2 parsers such as js-yaml 4 read them as 10 and 8) -> `Invalid input: round: <value>` - a malformed round writes clean today and breaks the next round's checkpoint parse into legacy, losing the chain
  - `round` valid and greater than 1 with no `prior_head_sha` -> `Missing required input: prior_head_sha` (this check is skipped when `round` itself is invalid)
- On any failure: emit the failure lines and stop. Do not write a partial file, invent a default, or blank a field. Value sets are matched exactly, case included: `Core` and `Deep` are invalid, not variants of `core-only` and `deep` - mapping display values to enum values is the caller's job.
- **`report_body` is raw Markdown, never fenced.** The consuming workflow's Output Format section shows its template inside a fence for display only; that fence is not part of the report. When the body's first non-blank line is a fence opener (three or more backticks or tildes) whose info string is `markdown` or `md` - the opener every review workflow's Output Format uses - and its last non-blank line is a bare fence of the same character with at least the opener's count, those two lines are the display wrapper: strip both and write what is between them. Every other fence is content - keep it, including a body that opens and closes with code samples.
- Sanitize `branch` for the filename: replace `/` and any character outside `[A-Za-z0-9_-]` with `-`, collapse consecutive `-`, lowercase, cut to 100 characters, then strip leading/trailing `-`; an empty result becomes `unnamed`. The frontmatter `branch` field keeps the raw value; only the filename is sanitized. `review-precondition-check` applies the same function on the next round.
- Build the filename as `<report_type>-<sanitized branch>.md` (`review-feature-x.md`, `review-perf-feature-x.md`). The scheme is many-to-one (`feature/x` and `Feature-X` share a file, as do a `review` report on `perf-x` and a `review-perf` report on `x`); the raw `branch` and `report_type` fields let the next round detect either mismatch.
- Write the file in the repository root (the workflow runs there; next round's `review-precondition-check` looks for it there): the frontmatter (below), then `report_body` (after any wrapper strip above) starting on the line after the closing `---` (no blank line inserted; leading blank lines of the written body are kept). Write UTF-8 with LF line endings, ending in exactly one newline.
- Overwrite without prompting - the file is a rolling checkpoint, not an archive. Round history lives inside the report body.
- Run no git command (the workflow already captured `base_sha` and `head_sha`).
- Print the confirmation line in Output Format after writing, to the caller - never into the file.

## Frontmatter Contract

Emit exactly this block at the top of the file, one field per line, no comments; the brace annotations on the two conditional lines are authoring notes, never emitted. Every field except the enums (`report_type`, `mode`, `scope`, `depth`) and `round` is double-quoted, because a bare value could parse as a YAML timestamp, number, or boolean; a `"` or `\` inside a quoted value is escaped with a preceding `\`. Emit `prior_head_sha` only when `round > 1`; emit `pr_url` only when the caller passed a non-empty value (never write `pr_url:` with a blank value). `generated_at` is the writer's current UTC time as `YYYY-MM-DDTHH:MM:SSZ`, read with `date -u +%Y-%m-%dT%H:%M:%SZ` - the one shell command this skill runs, and not a git command; the workflow does not pass it.

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
stack: "{stack identifier}"
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

- Summarizing or trimming `report_body` - the file is the full report the next round reconciles against.
