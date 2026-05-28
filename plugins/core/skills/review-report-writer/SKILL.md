---
name: review-report-writer
description: Write completed review report to Markdown file named by review type and branch. Final step of every task-*-review* workflow.
metadata:
  category: review
  tags: [review, report, output, file]
user-invocable: false
---

# Review Report Writer

## When to Use

Final step of every `task-*-review*` workflow after findings have been assembled. Persists the full review so the user can read it without scrolling the session console.

## Rules

- Determine the current branch with `git rev-parse --abbrev-ref HEAD`. On detached HEAD, use `detached` as the branch segment.
- Sanitize the branch for the filename: replace `/` and any character outside `[A-Za-z0-9_-]` with `-`, collapse consecutive `-`, strip leading/trailing `-`.
- Build the filename from `report_type`:
  - `review` -> `review-<branch>.md`
  - `review-perf` -> `review-perf-<branch>.md`
  - `review-security` -> `review-security-<branch>.md`
  - `review-observability` -> `review-observability-<branch>.md`
- Write the full assembled report (not a summary) to that filename in the current working directory.
- Print one confirmation line to the console after writing:

  ```
  Report written to <filename>
  ```

- Run no git command other than `git rev-parse --abbrev-ref HEAD`.
- Overwrite without prompting if the file exists - re-runs on the same branch replace prior output.

## Output Format

```
Report written to <filename>
```

The file contains the full review report in the workflow's standard Output Format markdown.

## Avoid

- Writing a partial or summarized report
- Creating subdirectories
- Running any git command beyond `git rev-parse --abbrev-ref HEAD`
