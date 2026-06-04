---
name: regression-pr-comment
description: Post or sticky-update a PR comment with regression verdict + counts. GitHub (gh) and GitLab (glab) backends. One sticky comment per PR per matrix key.
metadata:
  category: testing
  tags: [regression, pr-comment, ci, github, gitlab]
user-invocable: false
---

# Regression PR Comment

Posts the run verdict back to the PR as a sticky comment so reviewers see results without leaving the review surface. Edits in place across runs - never spams a new comment per re-run.

## When to Use

- During `task-regression` Step 7 after `regression-report-format` produces `summary.md`, only when `--pr-comment` is set.
- Never as part of `task-regression-discover` / `task-regression-scenario` (no run output to comment on).

## Rules

1. **Sticky identifier as the first line.** Every comment body starts with the literal HTML marker `<!-- regression-bot:<matrix-key> -->`. The skill greps PR comments for this marker and edits in place. No marker -> create new. Matrix key default is `default`; sharded runs that complete on different jobs each post their own sticky.
2. **Required env vars.** Either `GH_TOKEN` + `REGRESSION_PR_REF` (`owner/repo#123`) for GitHub, OR `GITLAB_TOKEN` + `CI_MERGE_REQUEST_PROJECT_PATH` + `CI_MERGE_REQUEST_IID` for GitLab. Missing -> exit `4` with a one-line stderr explaining which vars are missing. Never logs token values.
3. **CLI shell-out, not an SDK.** `gh pr comment ... --edit-last` for GitHub, `glab mr note ...` for GitLab. The plugin does not vendor an HTTP client.
4. **Body cap 60 KiB.** GitHub silently truncates comments over 65 KiB; render a "comment truncated - see full summary.md artifact" footer at 60 KiB.
5. **Verdict + counts + top-3 clusters only.** Do not paste the full per-flow table; reviewers can open the artifact. The PR comment is a triage signal, not the full report.
6. **No comment on `**PASS**`.** A green run leaves the prior sticky in place (so reviewers can see the trend), but if there is no prior sticky, do not create one. Configurable via `--pr-comment-on=all|fail|noisy` (default `noisy` - posts on `FAIL` or `PASS-WITH-NOISE`).

## Patterns

### Body template

```markdown
<!-- regression-bot:default -->
## Regression: **FAIL**

1 real-bug failure, 2 flakes, 0 infra, 0 seed-drift. [Full report]({artifact-url})

| Bucket | Count |
| --- | --- |
| Passed | 21 |
| Real bugs | 1 |
| Flake | 2 |
| Infra | 0 |
| Seed-drift | 0 |
| BudgetViolations | 1 |

### Top failure clusters

1. AssertionError: expected 201, got 500 - 1 scenario - order-checkout-happy
2. ...

_Updated {ISO timestamp}, run `{runId}`, profile `{profile}`._
```

The artifact URL is derived from the CI provider: for GitHub Actions, `https://github.com/$REGRESSION_PR_REF/actions/runs/$GITHUB_RUN_ID`; for GitLab, `$CI_JOB_URL`. When neither is set, the URL line is omitted.

### Find-and-edit logic (GitHub)

```bash
# Find sticky comment by marker
existing=$(gh api repos/$OWNER/$REPO/issues/$PR/comments --paginate \
  | jq -r ".[] | select(.body | startswith(\"$MARKER\")) | .id" | head -n1)

if [ -n "$existing" ]; then
  gh api repos/$OWNER/$REPO/issues/comments/$existing -X PATCH -f body="$BODY"
else
  gh pr comment "$PR" --body "$BODY" --repo "$OWNER/$REPO"
fi
```

### Find-and-edit logic (GitLab)

```bash
existing=$(glab api projects/:id/merge_requests/$MR/notes --paginate \
  | jq -r ".[] | select(.body | startswith(\"$MARKER\")) | .id" | head -n1)
if [ -n "$existing" ]; then
  glab api projects/:id/merge_requests/$MR/notes/$existing -X PUT -f body="$BODY"
else
  glab mr note "$MR" --message "$BODY"
fi
```

## Output Format

- One PR/MR comment posted or updated.
- stderr line: `[pr-comment] {edited|created} on {owner/repo}#{pr} marker=<matrix-key>`.
- Exit `0` on success, `4` on missing env vars, `5` on API error (token invalid / PR not found / rate-limited).

## Avoid

- Posting a new comment per run instead of editing the sticky.
- Embedding token values in the body or in stderr.
- Pasting the full per-flow table (the report artifact has it).
- Commenting on `**PASS**` runs by default (noise).
- Hardcoding the marker - it must include the matrix key to survive sharded jobs.
- Vendoring an HTTP client - shell out to `gh` / `glab`.
