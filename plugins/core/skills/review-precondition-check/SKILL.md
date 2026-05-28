---
name: review-precondition-check
description: Gate code review workflows: verify clean tree, non-trunk branch, head ref resolves locally, confirm base/head pair. Local git only.
metadata:
  category: review
  tags: [review, git, pull-request, local-git, gating]
user-invocable: false
---

# Review Precondition Check

## When to Use

- Step 0 of any code review workflow (`task-code-review`, `task-code-review-perf`, `task-code-review-security`, `task-code-review-observability`) before risk or finding analysis.
- Whenever a free-form invocation argument (a PR number, a branch name, or nothing) must be turned into a confirmed `(base_ref, head_ref)` pair the workflow can diff against.

This skill **gates only**: it emits ref names, not diffs or SHAs. The consuming workflow runs `git diff <base>...<head>` and `git log <base>..<head>` itself. Review is **PR-shaped only**: a feature branch or fetched PR ref vs its base. Working trees, commit ranges, and single commits are out of scope - hotfixes and cherry-picks must go through a PR.

## Rules

- **Local git only.** `git status`, `git rev-parse`, `git symbolic-ref`, `git for-each-ref`. No `gh`, no GitHub MCP, no platform API.
- **No state-changing git commands.** No `fetch`, `checkout`, `stash`, `commit`. When the user must run one, print the exact command and stop.
- **Stop on first failed precondition.** Do not collect multiple failures.
- **Confirm a non-current head before reviewing.** When the resolved head differs from the current branch, pause for explicit approval. No checkout is required.
- **Output a minimal handle.** Just `base_ref`, `head_ref`, `current_branch`, `head_matches_current` (plus notes). The consumer composes its own diff/log commands.

## Argument Modes

| Argument                                 | Mode             | Trigger                                                                                 | Notes                                                          |
| ---------------------------------------- | ---------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| _(none)_                                 | `branch-vs-base` | No argument; current branch (`HEAD`) is **not** a trunk branch                          | Default: self-review of the local feature branch.              |
| `pr-<N>`, `pr/<N>`, `pull-<N>`, `mr-<N>` | `pr-ref`         | Matches `^(pr|pull|mr)[-/]\d+$`                                                         | Local branch must already exist (created by user via fetch).   |
| `<branch>`                               | `branch-vs-base` | Resolves via `git rev-parse --verify refs/heads/<arg>` or `refs/remotes/<arg>`          | Self-review or teammate-branch cross-review.                   |

Trunk list (default): `main`, `master`, `develop`, `trunk`. If the resolved head matches a trunk, fail fast.

When an argument is ambiguous (a name that is both a branch and a tag), prefer branch resolution and note the ambiguity in the output.

### Explicit base override

Local git cannot know the true target branch of a PR opened against a non-trunk base (e.g., `pr-123` against `phase-01`). When the workflow forwards an explicit base (typically `--base <branch>`), use it directly and skip trunk-branch auto-detection in Step 5.

- Resolve via `refs/heads/<arg>` then `refs/remotes/<arg>`.
- Not subject to the trunk-branch fail-fast (that rule applies to the head, not the base).
- If unresolved, stop and ask the user to push or fetch - do not silently fall back to a trunk.

## Pattern

### Step 1 - Working tree must be clean

```bash
git status --porcelain
```

If any output, stop:

```text
Working tree is not clean. Review compares committed code, so uncommitted changes are out of scope.

Commit to the feature branch, stash (`git stash push -u`), or discard - then re-run.
```

### Step 2 - Classify the argument and identify the head ref

Apply the Argument Modes table. The result is a candidate `head_ref`:

- No argument -> `head_ref = HEAD`.
- `pr-<N>` (or `pull/<N>`, `mr-<N>`) -> `head_ref = refs/heads/pr-<N>` (normalize prefix).
- `<branch>` -> `head_ref = refs/heads/<branch>` if local, else `refs/remotes/<branch>`.

If the argument matches no mode, stop and ask for a branch name or `pr-<N>` ref.

### Step 3 - Head must not be a trunk branch

Resolve the short name of `head_ref` and compare to the trunk list (case-insensitive). If it matches:

```text
Review target is `<name>`, a trunk branch. Nothing scoped to review against itself.

Switch to your feature branch and re-run, or pass an explicit feature branch or `pr-<N>` ref.
```

### Step 4 - Head ref must exist locally

For `pr-ref` mode:

```bash
git rev-parse --verify refs/heads/pr-<N>
```

If missing, print the appropriate fetch command and stop (do not run it):

```text
Local ref `pr-<N>` not found. To fetch the PR head, run one of:

    # GitHub
    git fetch origin pull/<N>/head:pr-<N>

    # GitLab
    git fetch origin merge-requests/<N>/head:pr-<N>

    # Bitbucket
    git fetch origin pull-requests/<N>/from:pr-<N>

This creates a local ref only - no checkout, your current branch is untouched. After the fetch, verify:

    git rev-parse --verify refs/heads/pr-<N>

If that prints a SHA, re-run the review. If it errors, the fetch did not create the local branch (the `:pr-<N>` suffix is what creates it).
```

For `<branch>` arguments, verify with `git rev-parse --verify` against `refs/heads/<arg>` then `refs/remotes/<arg>`. If neither resolves, stop and ask the user to push or fetch.

### Step 5 - Detect the base branch

If the workflow forwarded an explicit base override (see above), resolve and use it; record `base_source: explicit-override`. If it does not resolve, stop and ask the user to push or fetch the base - do not silently fall back to a trunk.

Otherwise, auto-detect in order:

1. `git symbolic-ref refs/remotes/origin/HEAD` (typically `refs/remotes/origin/main`); record `base_source: origin-head`.
2. If unset, try `main`, `master`, `develop` via `git rev-parse --verify`; record `base_source: trunk-fallback`.
3. If none resolve, ask the user which branch is the base; record `base_source: user-prompted`.

Record `base_ref` as a name, not a SHA - the consuming workflow uses the name directly in `git diff <base>...<head>`.

When auto-detect was used (no explicit override) and the head is a `pr-<N>` ref, add a note reminding the user that PRs opened against a non-trunk base must pass `--base <branch>` - otherwise the diff will include unrelated commits.

### Step 6 - Confirm head vs current branch (approval gate)

```bash
git rev-parse --abbrev-ref HEAD
```

If the short name of `head_ref` matches the current branch, skip this step.

Otherwise:

```text
Review target: <head-short-name>
Current branch: <current-branch>
Base: <base-short-name>

The review reads git history only - no checkout is required. Your current branch and working tree are untouched.

If you want to run or inspect the code locally:
    git checkout <head-short-name>

Proceed with review of `<head-short-name>` from your current branch? [y/N]
```

Wait for explicit affirmative (`y` / `yes`). On `n` or no response, stop.

## Output Format

When all preconditions pass, emit this handle and nothing more:

```yaml
review-target:
  mode: branch-vs-base | pr-ref
  argument: <verbatim user argument or "(none)">
  base_ref: <e.g., origin/main, phase-01>
  base_source: explicit-override | origin-head | trunk-fallback | user-prompted
  head_ref: <e.g., pr-50273, feature/x, or HEAD>
  current_branch: <e.g., feature-A>
  head_matches_current: true | false
  notes:
    - <ambiguities, fallbacks used, approval-gate outcome, non-trunk-base reminder for pr-ref>
```

When a precondition fails, emit only the stop message from the relevant step. Do not emit a partial handle.

## Avoid

- Reading the diff, computing SHAs, or pulling `git log` - the consuming workflow does that.
- Running any state-changing git command - the user must run these to protect uncommitted work.
- Calling `gh`, GitHub MCP, or any platform API.
- Silently picking a base when `origin/HEAD` is unset and multiple candidates exist - ask.
- Skipping the dirty-tree, trunk-branch, or missing-head fail-fasts.
- Gating head-vs-current when they already match - that just adds friction.
- Forcing a `git checkout` of the head branch.
- Reviewing working-tree changes, explicit commit ranges, or single commits - out of scope.
