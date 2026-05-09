---
name: review-report-writer
description: Write a completed review report to a Markdown file named by review type and branch. Final step of all task-*-review* workflows.
metadata:
  category: review
  tags: [review, report, output, file]
user-invocable: false
---

# Review Report Writer

## When to Use

Called as the final step of every `task-*-review*` workflow after all findings have been assembled. Persists the review output to a file so the user can read it without scrolling back through the session console.

## Rules

- Determine the current branch name using `git rev-parse --abbrev-ref HEAD`.
- Sanitize the branch name for use in a filename: replace `/` and any character that is not alphanumeric, `-`, or `_` with `-`; collapse consecutive `-` into one; strip leading and trailing `-`.
- Construct the output filename using the `report_type` input:
  - `review` - `review-<branch>.md`
  - `review-perf` - `review-perf-<branch>.md`
  - `review-security` - `review-security-<branch>.md`
  - `review-observability` - `review-observability-<branch>.md`
- Write the complete review output (the full assembled report, not a summary) to the filename in the current working directory.
- After writing, print a one-line confirmation to the session console:

  ```
  Report written to <filename>
  ```

- Do not truncate or summarize the report when writing to file - write the full output exactly as assembled.
- If the branch cannot be determined (detached HEAD), use `detached` as the branch name segment.

## Output Format

```
Report written to <filename>
```

The file contains the full review report in the workflow's standard Output Format markdown.

## Avoid

- Writing a partial or summarized report - always write the complete assembled output
- Creating subdirectories - always write to the current working directory
- Overwriting silently if the file already exists without noting it (a second review run on the same branch simply overwrites; no special handling needed)
- Running any git command other than `git rev-parse --abbrev-ref HEAD`
