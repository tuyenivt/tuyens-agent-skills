---
name: review-precondition-check
description: Gate code review workflows: clean tree, non-trunk branch, resolve base/head pair, surface prior-round checkpoint for re-review. Local git.
metadata:
  category: review
  tags: [review, git, pull-request, local-git, gating, checkpoint, re-review]
user-invocable: false
---

# Review Precondition Check

## When to Use

- Step 0 of any code review workflow (`task-code-review` and every `task-code-review-*` scoped lens) before risk or finding analysis.
- Whenever a free-form invocation argument (a PR number, a branch name, or nothing) must be turned into a confirmed `(base_ref, head_ref)` pair the workflow can diff against.

This skill **gates only**: it emits ref names and copies through a prior checkpoint; it computes no diff and no SHA. The consuming workflow runs `git diff <base>...<head>` and `git log <base>..<head>` itself. Review is **PR-shaped only**: a feature branch or fetched PR ref vs its base. Working trees, commit ranges, and single commits are out of scope - hotfixes and cherry-picks must go through a PR.

## Inputs

| Field         | Required | Source                                                                                  |
| ------------- | -------- | --------------------------------------------------------------------------------------- |
| `argument`    | no       | The invocation argument: nothing, a branch name, a PR ref, or a bare PR number           |
| `base`        | no       | An explicit base the workflow forwards (typically `--base <branch>`)                     |
| `report_type` | no       | The workflow's report type (`review`, `review-perf`, `review-security`, `review-observability`, `review-reliability`); defaults to `review` |

## Rules

- **Local git only.** `git status`, `git rev-parse`, `git symbolic-ref`, `git for-each-ref`. No `gh`, no GitHub MCP, no platform API.
- **No state-changing git commands.** No `fetch`, `checkout`, `stash`, `commit`. When the user must run one, print the exact command and stop.
- **Stop on first failed precondition.** Do not collect multiple failures.
- **Prompts require a user.** The base-candidate question (Step 4) and the approval gate (Step 5) are interactive. When no user can answer (subagent or non-interactive run), stop: emit the prompt text, then the step's cancel line (Step 4: `Review cancelled: base branch not determined; re-run with --base <branch>.`, Step 5: `Review cancelled at approval gate.`) - the consuming workflow decides how to re-run.
- **Confirm a non-current head before reviewing.** When the resolved head differs from the current branch, pause for explicit approval. No checkout is required.
- **Output the handle only.** The consumer composes its own diff/log commands from it.

## Argument Modes

| Argument                                 | Mode             | Resolution                                                                          |
| ---------------------------------------- | ---------------- | ----------------------------------------------------------------------------------- |
| _(none)_                                 | `branch-vs-base` | The current branch is the head. Default: self-review.                               |
| `pr-<N>`, `pr/<N>`, `pull-<N>`, `mr-<N>`, `<N>` | `pr-ref`         | Matches `^((pr\|pull\|mr)[-/])?\d+$`. A local branch must already exist (created by the user via fetch): try the verbatim argument, then the normalized `pr-<N>` (one check when they coincide). |
| `<branch>`                               | `branch-vs-base` | Resolves via `refs/heads/<arg>`, then `refs/remotes/<arg>`, then `refs/remotes/*/<arg>`. Self-review or teammate-branch cross-review. |

Trunk list: `main`, `master`, `develop`, `trunk`. Match is exact-name (case-insensitive), not substring - `develop-bug` is not a trunk.

## Pattern

Existence checks use `git rev-parse --verify --quiet <ref>` (exit status), and pattern lookups use `git for-each-ref <pattern>` judged by non-empty output - its exit status is 0 either way.

### Step 1 - Working tree must be clean

```bash
git status --porcelain
```

Ignore lines whose path is a repository-root `review-*.md` file, untracked (`??`) or modified (` M`, a committed checkpoint the last round rewrote) - they are this workflow's own checkpoints, and porcelain paths are always repository-root-relative. If any other line remains, stop:

```text
Working tree is not clean. Review compares committed code, so uncommitted changes are out of scope.

Commit to the feature branch, stash (`git stash push -u -- ':(exclude)review-*.md'` keeps the review checkpoints), or discard - then re-run.
```

### Step 2 - Resolve the head

Apply the Argument Modes table. The result is `head_ref` (a short name the consumer can diff against) and `head_short_name` (the branch name the checkpoint keys on, never `HEAD` and never remote-prefixed).

- No argument: `git symbolic-ref -q --short HEAD`. Failure means detached `HEAD`: stop and ask for an explicit branch or `pr-<N>` ref. Otherwise `head_ref` = `head_short_name` = the printed name, and `current_branch` = the same.
- `pr-ref`: verify `refs/heads/<verbatim argument>`, then `refs/heads/pr-<N>`. Neither exists: print the fetch instructions below and stop. `head_ref` = `head_short_name` = the branch that resolved.
- `<branch>`: verify `refs/heads/<arg>`; else `refs/remotes/<arg>`; else `git for-each-ref "refs/remotes/*/<arg>"` (one match: use it; several: ask the user which remote). None resolves: stop and ask the user to push or fetch. `head_short_name` is `<arg>` with any leading `<remote>/` segment stripped (`origin/feature/x` -> `feature/x`); record `head_is_remote: true` when the head resolved under `refs/remotes/`.

In either mode, when the head resolved as `refs/heads/<name>`, also verify `refs/tags/<name>`. When both exist, git resolves the bare name to the tag first, so `head_ref` = `heads/<name>` and the note `Argument <name> matched both a local branch and a tag; resolved to branch.` is added.

Fetch instructions for a missing PR ref:

```text
Local ref `pr-<N>` not found. To fetch the PR head, run one of:

    # GitHub
    git fetch origin pull/<N>/head:pr-<N>

    # GitLab
    git fetch origin merge-requests/<N>/head:pr-<N>

    # Bitbucket Server / Data Center
    git fetch origin pull-requests/<N>/from:pr-<N>

    # Bitbucket Cloud (no per-PR refs; fetch the PR's source branch)
    git fetch origin <source-branch>:pr-<N>

This creates a local ref only - no checkout, your current branch is untouched. After the fetch, verify:

    git rev-parse --verify refs/heads/pr-<N>

If that prints a SHA, re-run the review. If it errors, the fetch did not create the local branch (the `:pr-<N>` suffix is what creates it).
```

With an argument, `current_branch` is `git symbolic-ref -q --short HEAD`, or `detached` when that fails.

### Step 3 - Head must not be a trunk branch

Compare `head_short_name` to the trunk list (case-insensitive). If it matches:

```text
Review target is `<name>`, a trunk branch. Nothing scoped to review against itself.

Switch to your feature branch and re-run, or pass an explicit feature branch or `pr-<N>` ref.
```

### Step 4 - Detect the base branch

If the workflow forwarded `base`: resolve via `refs/heads/<base>`, then `refs/remotes/<base>`, then `refs/remotes/*/<base>` (one match: use it; several: ask the user which remote); record `base_source: explicit-override`. Not subject to the trunk fail-fast (that rule applies to the head). If it does not resolve, stop and ask the user to push or fetch the base - do not silently fall back to a trunk.

Otherwise, auto-detect in order:

1. `git symbolic-ref -q refs/remotes/origin/HEAD`. If it prints a ref, strip `refs/remotes/` (giving `origin/main`) and verify the result still resolves - `origin/HEAD` is set at clone time and can point at a deleted branch. Resolved: use it; record `base_source: origin-head`. Not set, or its target no longer resolves: continue to 2.
2. Otherwise probe `main`, `master`, `develop`, `trunk`, each as `refs/heads/<name>` then `refs/remotes/origin/<name>` (a trunk whose local branch was deleted still tracks remotely). Exactly one name resolves: use it; record `base_source: trunk-fallback`. Two or more resolve: ask the user which is the base; record `base_source: user-prompted`.
3. If none resolve, ask the user which branch is the base; record `base_source: user-prompted`.

Record `base_ref` as a short name (`origin/main`, `phase-01`), never `refs/...`. When `base_source` is `trunk-fallback` or `user-prompted`, add a note naming the probe or answer that chose it.

When auto-detect was used and the head is a `pr-<N>` ref, add a note reminding the user that PRs opened against a non-trunk base must pass `--base <branch>` - otherwise the diff will include unrelated commits.

### Step 5 - Confirm head vs current branch (approval gate)

If `head_short_name` equals `current_branch`, set `head_matches_current: true` and skip this step. Otherwise set `head_matches_current: false` and prompt (the checkout line is `git checkout -b <head_short_name> <head_ref>` when `head_is_remote` is true, since no local branch exists yet):

```text
Review target: <head_short_name>
Current branch: <current_branch>
Base: <base_ref>

The review reads git history only - no checkout is required. Your current branch and working tree are untouched.

If you want to run or inspect the code locally:
    git checkout <head_short_name>

Proceed with review of `<head_short_name>` from your current branch? [y/N]
```

Wait for explicit affirmative (`y` / `yes`); on approval add the note `Approval gate: user approved review of <head_short_name> from <current_branch>.`. On `n` or no response, stop with `Review cancelled at approval gate.` and emit no handle.

### Step 6 - Surface prior-round checkpoint (read-only)

This step enables flag-free re-review. It only **reads and reports** - it does not decide the round. The consuming workflow decides.

Compute the prior-report filename as `review-report-writer` does: `<report_type>-<sanitized head_short_name>.md`, where sanitizing replaces `/` and any character outside `[A-Za-z0-9_-]` with `-`, collapses consecutive `-`, lowercases, cuts to 100 characters, then strips leading/trailing `-`, and turns an empty result into `unnamed`. The key is the thing being reviewed, not the branch you happen to stand on, so a cross-branch review of `pr-123` chains with the last review of `pr-123`, and `origin/feature/x` chains with a later local review of `feature/x`.

Record the filename as `report_path`. Look for it in the repository root (`git rev-parse --show-toplevel`), where `review-report-writer` writes it; only that exact filename is read - any other `review-*.md` file is ignored. If it does not exist, omit `prior_checkpoint` from the handle and continue.

If the file exists, read the leading YAML frontmatter (delimited by `---` lines at the start of the file). Scalar values may be double-quoted, single-quoted, or bare: strip the quotes, unescape `\"` and `\\` inside double quotes and `''` inside single quotes. Fields the writer no longer emits or this skill does not list (`generated_at`) are ignored. Parse fields:

| Field            | Required for valid checkpoint                                 |
| ---------------- | -------------------------------------------------------------- |
| `branch`         | yes - and it must equal `head_short_name` exactly (the filename is many-to-one: `Feature-X` and `feature/x` share one); a different value means the file is another branch's checkpoint: treat as legacy |
| `base_ref`       | yes                                                            |
| `base_sha`       | yes                                                            |
| `head_ref`       | yes                                                            |
| `head_sha`       | yes                                                            |
| `mode`           | yes - `full`; a report predating full-range re-review may say `incremental`, which is emitted as `full` in the handle; any other value is unparseable |
| `round`          | yes (positive integer)                                         |
| `scope`          | yes                                                            |
| `depth`          | yes                                                            |
| `stack`          | yes                                                            |
| `report_type`    | no - when present it must equal this run's `report_type`, otherwise the file is another lens's checkpoint: treat as legacy |
| `prior_head_sha` | no - copy through when present (absent on a round-1 checkpoint) |
| `pr_url`         | no - copy through when present                                 |

If the file lacks a frontmatter block, lacks `---` delimiters, or any required field is missing or unparseable, treat as legacy: emit `prior_checkpoint: legacy` (a single literal value) and continue. The workflow uses this signal to overwrite the legacy report at `report_path` with a fresh round-1 run.

If frontmatter is valid, emit the block in the handle (see Output Format below). Do not resolve SHAs against the live repository, do not check reachability, do not compare to the current head - those checks belong to the consuming workflow.

## Output Format

When all preconditions pass, emit this handle and nothing more. `base_ref` and `head_ref` are short names (`origin/main`, `feature/x`, `pr-42`, `heads/hotfix-1` in the tag-collision case), never `refs/...`. Omit `notes` when empty.

```yaml
review-target:
  mode: {branch-vs-base | pr-ref}
  argument: {verbatim user argument or "(none)"}
  report_type: {review | review-perf | review-security | review-observability | review-reliability}
  base_ref: {e.g., origin/main, phase-01}
  base_source: {explicit-override | origin-head | trunk-fallback | user-prompted}
  head_ref: {e.g., pr-50273, feature/x, origin/feature/x}
  head_short_name: {e.g., feature/x - the writer's `branch` input}
  head_is_remote: {true | false}
  current_branch: {e.g., feature-A, or detached}
  head_matches_current: {true | false}
  report_path: {the computed checkpoint filename, emitted whether or not the file exists}
  notes:
    - {ambiguities, fallbacks used, approval-gate outcome, non-trunk-base reminder for pr-ref}
prior_checkpoint:                       # omitted entirely when no prior report file exists;
                                        # the scalar `legacy` when the file exists but its frontmatter is missing/invalid
  branch: {from prior report}
  base_ref: {from prior report}
  base_sha: {from prior report}
  head_ref: {from prior report}
  head_sha: {from prior report}
  mode: full
  round: {integer}
  scope: {from prior report}
  depth: {from prior report}
  stack: {from prior report}
  prior_head_sha: {from prior report; omitted if absent}
  pr_url: {from prior report; omitted if absent}
```

When a precondition fails, emit only the stop message from the relevant step. Do not emit a partial handle.

## Avoid

- Reading the diff, computing SHAs, or pulling `git log` - the consuming workflow does that.
- Running any state-changing git command - the user must run these to protect uncommitted work.
- Silently picking a base when `origin/HEAD` is unset and multiple candidates exist - ask.
- Skipping the dirty-tree, trunk-branch, or missing-head fail-fasts.
- Gating head-vs-current when they already match - that just adds friction.
- Forcing a `git checkout` of the head branch.
- Deciding the round, or comparing the prior head to the current one, in Step 6 - just surface the checkpoint; the workflow decides.
