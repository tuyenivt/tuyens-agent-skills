---
name: review-precondition-check
description: Gate code-review workflows before they run. Verifies the reviewer is in a reviewable state (clean working tree, not on a trunk branch, head ref resolves locally) and confirms head vs current branch when they differ. Stops with an exact user-runnable command when a precondition fails. Local git only - no `gh` CLI, no platform API.
metadata:
  category: review
  tags: [review, git, pull-request, local-git, gating]
user-invocable: false
---

# Review Precondition Check

## When to Use

- As Step 0 of any code review workflow (`task-code-review`, `task-code-review-perf`, `task-code-review-security`, `task-code-review-observability`) before risk or finding analysis runs.
- Whenever a free-form invocation argument (a PR number, a branch name, or nothing at all) needs to be turned into a confirmed `(base_ref, head_ref)` pair the consuming workflow can diff against.

This skill **gates only** - it does not read the diff, compute SHAs, or pre-pull commit logs. The consuming workflow reads `git diff <base>...<head>` and `git log <base>..<head>` itself once this skill has approved the run. Review is **PR-shaped only**: a feature branch or fetched PR ref vs its base. Working-tree, commit ranges, and single commits are out of scope - hotfixes and cherry-picks must go through a PR per development policy.

## Rules

- **Local git only.** `git status`, `git rev-parse`, `git symbolic-ref`, `git for-each-ref`. No `gh`, no GitHub MCP, no platform API.
- **Never run state-changing git commands.** No `git fetch`, `git checkout`, `git stash`, `git commit`. When the user must run one, print the exact command and stop.
- **Stop on the first failed precondition.** Do not collect multiple failures - the user fixes one, re-runs, and hits the next if any.
- **Confirm before reviewing a non-current head.** Code review is expensive; when the resolved head ref differs from the current branch, pause for explicit user approval before the workflow proceeds. No checkout is required.
- **Output a minimal handle.** The consuming workflow only needs `base_ref`, `head_ref`, `current_branch`, and `head_matches_current`. Do not bake diff or log commands into the output - the consumer composes those itself.

## Argument Modes

| Argument                                 | Mode             | Trigger                                                                                 | Notes                                                          |
| ---------------------------------------- | ---------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| _(none)_                                 | `branch-vs-base` | No argument passed; current branch (`HEAD`) is **not** a trunk branch                   | Default. Self-review of the local feature branch.              |
| `pr-<N>`, `pr/<N>`, `pull-<N>`, `mr-<N>` | `pr-ref`         | Argument matches `^(pr\|pull\|mr)[-/]\d+$`                                              | Local branch must already exist (created by user via fetch).   |
| `<branch>`                               | `branch-vs-base` | Argument resolves via `git rev-parse --verify refs/heads/<arg>` or `refs/remotes/<arg>` | Self-review or teammate-branch cross-review with many commits. |

Trunk branch list (defaults): `main`, `master`, `develop`, `trunk`. If the resolved head matches a trunk branch, fail fast - there is nothing scoped to review.

When an argument is ambiguous (e.g., a name that is both a branch and a tag), prefer branch resolution and note the ambiguity in the output.

## Pattern

### Step 1 - Working tree must be clean

```bash
git status --porcelain
```

If this produces any output, stop:

```text
Working tree is not clean. Review compares committed code, so uncommitted changes are not in scope.

Either commit your changes to the feature branch, stash them (`git stash push -u`), or discard them - then re-run the review.
```

### Step 2 - Classify the argument and identify the head ref

Apply the Argument Modes table. The result is a candidate `head_ref`:

- No argument → `head_ref = HEAD` (current branch).
- `pr-<N>` (or `pull/<N>`, `mr-<N>`) → `head_ref = refs/heads/pr-<N>` (normalize the prefix).
- `<branch>` → `head_ref = refs/heads/<branch>` if local, else `refs/remotes/<branch>`.

If the argument does not match any mode (not a known PR-ref pattern, not a resolvable branch), stop and ask the user to pass a branch name or `pr-<N>` ref.

### Step 3 - Head must not be a trunk branch

Resolve the short name of `head_ref` and compare to the trunk list (`main`, `master`, `develop`, `trunk`, case-insensitive). If it matches:

```text
Review target is `<name>`, which is a trunk branch. There is nothing scoped to review against itself.

Switch to your feature branch (`git checkout <feature-branch>`) and re-run, or pass an explicit feature branch or `pr-<N>` ref.
```

### Step 4 - Head ref must exist locally

For `pr-ref` mode, verify the local branch exists:

```bash
git rev-parse --verify refs/heads/pr-<N>
```

If missing, stop and print the fetch command for the user (do not run it):

```text
Local ref `pr-50273` not found. To fetch the PR head from origin, run one of:

    # GitHub
    git fetch origin pull/50273/head:pr-50273

    # GitLab
    git fetch origin merge-requests/50273/head:pr-50273

    # Bitbucket
    git fetch origin pull-requests/50273/from:pr-50273

This adds a local ref only - your working tree is untouched. Re-run the review once the ref exists.
```

For `<branch>` arguments, verify with `git rev-parse --verify`. If neither `refs/heads/<arg>` nor `refs/remotes/<arg>` resolves, stop and ask the user to push or fetch the branch first.

### Step 5 - Detect the base branch

Resolve the base in this order:

1. `git symbolic-ref refs/remotes/origin/HEAD` (typically points to `refs/remotes/origin/main`).
2. If unset, check `main`, then `master`, then `develop` via `git rev-parse --verify`.
3. If none resolve, ask the user which branch is the base.

Record the result as `base_ref` (a name, not a SHA - the consuming workflow uses the name directly in `git diff <base>...<head>`).

### Step 6 - Confirm head vs current branch (approval gate)

```bash
git rev-parse --abbrev-ref HEAD
```

If the short name of `head_ref` matches the current branch, **skip this step** - the user is already on the target.

Otherwise, pause and ask the user to confirm:

```text
Review target: <head-short-name>
Current branch: <current-branch>
Base: <base-short-name>

The review will read git history only - no checkout is required. Your current branch and working tree are untouched.

If you want to run or inspect the code locally during/after review:
    git checkout <head-short-name>

Proceed with review of `<head-short-name>` from your current branch? [y/N]
```

Wait for explicit affirmative (`y` / `yes`). On `n` or no response, stop and let the user re-invoke.

## Output Format

When all preconditions pass, emit this exact handle and nothing more. The consuming workflow reads the diff and commit log itself.

```yaml
review-target:
  mode: branch-vs-base | pr-ref
  argument: <verbatim user argument or "(none)">
  base_ref: <e.g., origin/main>
  head_ref: <e.g., pr-50273, feature/x, or HEAD>
  current_branch: <e.g., feature-A>
  head_matches_current: true | false
  notes:
    - <ambiguities, fallbacks used, approval-gate outcome>
```

When a precondition fails, emit only the stop message described in the relevant step. Do not emit a partial handle.

## Avoid

- Reading the diff, computing SHAs, or pulling `git log` - that is the consuming workflow's job. This skill outputs ref names only.
- Running `git fetch`, `git checkout`, `git stash`, `git commit`, or any state-changing git command - the user must run these so they can protect uncommitted work.
- Calling `gh`, GitHub MCP, or any platform API.
- Silently picking a base branch when `origin/HEAD` is unset and multiple candidates exist - ask the user.
- Skipping the dirty-tree, trunk-branch, or missing-head fail-fasts - each prevents wasted tokens on an unscoped review.
- Skipping the head-vs-current approval gate when they differ - review is expensive and must not start on an unintended target. Equally, do not gate when they match - that just adds friction.
- Forcing the user to `git checkout` the head branch - the consuming workflow's diff and log commands are ref-qualified.
- Reviewing working-tree changes, explicit commit ranges, or single commits - out of scope; review must target a feature branch or PR ref.
