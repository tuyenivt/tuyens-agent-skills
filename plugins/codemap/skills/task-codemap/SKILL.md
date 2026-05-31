---
name: task-codemap
description: Build or sync a persistent codebase knowledge graph at .codemap/graph.json. Auto-detects full build vs incremental refresh. Pure-LLM, no tree-sitter.
metadata:
  category: code
  tags: [codemap, knowledge-graph, onboarding, architecture, multi-stack]
  type: workflow
user-invocable: true
---

# Task: Codemap

Produces and maintains `.codemap/graph.json` - a persistent, commit-friendly graph of every significant file, function, class, endpoint, and their relationships. Powers `task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`. Commit the graph and teammates skip the build.

**One slash command, two modes:**
- **First run** (no `.codemap/graph.json`) - full build from scratch.
- **Subsequent runs** (graph exists) - incremental sync: fingerprint diff, re-analyze only changed files, splice into the existing graph.

The auto-update hook (when enabled via `--auto-update`) invokes this same workflow on `git commit | merge | rebase | cherry-pick` and at session start when HEAD has drifted from the graph.

## When to Use

- First-time setup on a project.
- After your own commits, after `git pull`, or after a merge - to sync the graph with the working tree.
- After major refactors. The workflow auto-escalates to a full rebuild at >=30% file churn or schema bump.
- Before sharing the graph with a team - commit the `.codemap/` artifacts.

**Not for:**
- One-shot Markdown onboarding reports - use `task-onboard` (no persistence, no graph).
- Asking questions about an existing graph - use `task-codemap-ask`.
- Playing guided walkthroughs - use `task-codemap-guide`.
- Deep-dive on one entity - use `task-codemap-explain`.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| `[path]` | No | Repo root (default `.`) or scope subdirectory. |
| `--full` | No | Force full rebuild even when fingerprints exist. |
| `--scope <dir>` | No | Limit analysis to a subdirectory (huge monorepos). |
| `--auto-update` / `--auto-update=false` | No | Toggle the post-commit + session-start hook. Writes `autoUpdate: <bool>` to `config.json`. |
| `--validate-only` | No | Skip build; just run validation against existing `graph.json`. |
| `--force` | No | In sync mode, skip the "no changes detected" early exit. |
| `--rebuild-on <ratio>` | No | Override the 30% full-rebuild churn threshold (e.g., `--rebuild-on 0.5`). |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

1. Confirm Python 3 available (`python --version` or `python3 --version`). Abort with a friendly error if missing.
2. Confirm `git` available. Required for fingerprints and HEAD comparison; scan itself falls back to `os.walk` without git.
3. Create `.codemap/intermediate/` (gitignored work area) if not present.

### Step 3 - Decide Mode

| Condition | Mode |
| --- | --- |
| `--validate-only` set | **Validate** - skip to Step 9 against existing graph. |
| `--full` set, OR `.codemap/graph.json` missing, OR `.codemap/fingerprints.json` missing | **Full build** - Step 4 path. |
| All three exist (`graph.json`, `meta.json`, `fingerprints.json`) | **Incremental sync** - Step 5 path. |

If the user passed `--full` but a graph already exists, announce that a full rebuild will replace the current graph and confirm before proceeding.

### Step 4 - Full Build Path

#### 4a. Detect Stack

Use skill: `stack-detect`. Cache the result; used in build pipeline phases 3 (analysis prompts), 6 (layer assignment), and 7 (guide selection).

#### 4b. Initialize Ignore File

If `.codemap/.codemapignore` is missing, copy `.gitignore` to it and append a banner explaining that codemap-specific ignores can be added below.

#### 4c. Run Build Pipeline

Use skill: `codemap-build-pipeline`. Executes phases 1-9 (scan, batch, parallel sub-agent analyze, merge, cross-batch repair, layer assignment, guide generation, validate, persist).

Track wall-clock per phase; report at end. On validation errors, abort - do not persist.

Skip to Step 8 (auto-update config) and Step 9 (report).

### Step 5 - Incremental Sync Path

#### 5a. Quick Freshness Check

Compare `.codemap/meta.json#gitCommitHash` to current `git rev-parse HEAD`. If identical and `--force` not set, proceed to fingerprint scan anyway - the user may have uncommitted edits worth picking up. (The auto-update hook only fires on commit-like events; manual invocations should still catch dirty trees.)

#### 5b. Compute Change-Set

1. Scan: `python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/scan.py" --root <path> --output .codemap/intermediate/scan.json`.
2. Fingerprint current tree: `python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compute --scan .codemap/intermediate/scan.json --output .codemap/intermediate/fingerprints-current.json`.
3. Compare against stored: `python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compare --current .codemap/intermediate/fingerprints-current.json --previous .codemap/fingerprints.json --output .codemap/intermediate/change-set.json`.

Use skill: `codemap-fingerprints` for the contract.

#### 5c. Apply Decision Tree

| Change-set signal | Action |
| --- | --- |
| `schemaVersionChanged: true` | Escalate: rerun this workflow with `--full`. Surface a one-line note and stop. |
| `churnRatio >= 0.30` (or `--rebuild-on` override) | Escalate to `--full`. |
| All change lists empty, gitCommitHash matches HEAD | Early exit: "graph is up to date". Skip to Step 9 report. |
| All change lists empty, gitCommitHash stale | Update `meta.json#gitCommitHash` only; skip Steps 5d-5f. |
| `deleted` only | Run 5e (drop) + 5f (validate + persist). Skip analysis. |
| `renamed` only | Run 5e (rename) + 5f. Skip analysis. |
| `added` or `modified` non-empty | Run 5d-5f. |

#### 5d. Detect Stack & Analyze Changed Files

Use skill: `stack-detect`. Reuse cached if already loaded; needed only if new files in new languages appear.

For `added` + `modified` files, build batch list (group by directory, cap 25 per batch / 800 KB). Dispatch sub-agents per `codemap-build-pipeline` Phase 3 contract. Outputs `intermediate/batch-<N>.json`.

#### 5e. Splice

1. Load existing `.codemap/graph.json`.
2. Drop all nodes whose `filePath` is in `modified` or `deleted`.
3. Drop all edges where either endpoint references a dropped node ID.
4. For `renamed`, rewrite `filePath` and any node `id` containing the old path; rewrite edges referencing renamed IDs.
5. Merge new nodes/edges from 5d (use the same dedup logic as `merge.py`).
6. Recompute `layer` **only** for newly added or rewritten nodes (via `codemap-layer-patterns`). Existing layers preserved.
7. Guides are **not** regenerated in sync mode. To regenerate, run `task-codemap-guide --rebuild` or `task-codemap --full`.

### Step 6 - Generate `.gitignore` Recommendation (full builds only)

Surface to the user (do not auto-modify):

```
.codemap/intermediate/
.codemap/diff-overlay.json
```

Suggest committing `.codemap/graph.json`, `.codemap/guides.json`, `.codemap/meta.json`, `.codemap/config.json`, `.codemap/fingerprints.json`, `.codemap/.codemapignore`.

### Step 7 - Configure Auto-Update (if `--auto-update` set)

Write or update `.codemap/config.json` with the new `autoUpdate` value. If enabled, surface:
- Hook files ship at `plugins/codemap/hooks/codemap-auto-update.json`. Claude Code auto-registers plugin hooks.
- The hook calls `/task-codemap` (this workflow) on commit/merge/rebase/cherry-pick and on session start when HEAD has drifted from the graph.
- On Codex/Cursor/Copilot the hook does not fire - run `/task-codemap` manually after pulls and commits.

### Step 8 - Validate

Use skill: `codemap-validate`. Errors block persistence; warnings logged.

- Full build path: validate ran inside `codemap-build-pipeline` Phase 8.
- Sync path: validate the spliced graph now. **On error, do not overwrite** the existing `graph.json` - keep the prior version intact and print the validation report.

### Step 9 - Persist & Report

#### Persist (skip if `--validate-only`)

- Full build: handled by `codemap-build-pipeline` Phase 9.
- Sync: write spliced graph -> `.codemap/graph.json`; update `meta.json` with new `gitCommitHash`/`builtAt`/`analyzedFiles`; promote `intermediate/fingerprints-current.json` to `.codemap/fingerprints.json`; delete `.codemap/intermediate/`.

#### Report

Render the report block (Output Format below) with mode-appropriate sections.

## Output Format

### Full build report

```markdown
# Codemap Build Report

**Mode:** full build
**Built at:** 2026-05-30T12:00:00Z
**Git commit:** abc1234
**Stack:** Go 1.25 / Gin + GORM (backend)
**Scope:** . (full repo)

## Pipeline

| Phase | Result | Wall-clock |
| --- | --- | --- |
| 1. Scan | 412 files (18 skipped) | 2s |
| 2. Batch | 18 batches | <1s |
| 3. Analyze | 18 batches, 5-way parallel | 96s |
| 4. Merge | 412 nodes, 1184 edges (12 dangling dropped) | <1s |
| 5. Repair | clean | 4s |
| 6. Layers | 88% assigned | 6s |
| 7. Tours | 4 generated | 8s |
| 8. Validate | 0 errors, 2 warnings | <1s |
| 9. Persist | graph.json (412 KB), guides.json (18 KB) | <1s |

## Validation Summary

**Errors:** 0
**Warnings:**
- W4: Layer coverage 88% (threshold 75%) - OK
- W7: 0 document nodes despite README.md present - investigate

## Artifacts Written

- `.codemap/graph.json` (412 KB)
- `.codemap/guides.json` (18 KB, 4 guides)
- `.codemap/meta.json`
- `.codemap/config.json` (autoUpdate: <true|false>)
- `.codemap/fingerprints.json`
- `.codemap/.codemapignore`

## Recommended .gitignore Additions

```
.codemap/intermediate/
.codemap/diff-overlay.json
```

## Next Steps

- `/task-codemap-guide --list` to see available walkthroughs; `--guide <name>` to play one
- `/task-codemap-ask "<question>"` to ask the graph
- `/task-codemap-explain <path>` for deep-dive on a file or function
- `/task-codemap` after future commits (or enable `--auto-update`)
```

### Incremental sync report

```markdown
# Codemap Sync Report

**Mode:** incremental sync (12.4% churn)
**From commit:** abc1234 -> def5678
**Synced at:** 2026-05-30T12:00:00Z

## Change-Set

- Added: 3 files
- Modified: 18 files
- Renamed: 2 files
- Deleted: 1 file
- Unchanged: 388 files

## Pipeline

| Phase | Result | Wall-clock |
| --- | --- | --- |
| Scan | 412 files | 2s |
| Fingerprint compare | 21 changed | <1s |
| Analyze | 2 batches, 2-way parallel | 14s |
| Splice | -29 nodes / -78 edges / +34 nodes / +91 edges | <1s |
| Validate | 0 errors, 1 warning | <1s |
| Persist | graph.json updated | <1s |

## Validation Summary

**Errors:** 0
**Warnings:**
- W4: Layer coverage 87% - OK

## Next

- Guides not regenerated. Run `/task-codemap-guide --rebuild` for fresh walkthroughs.
- Or `/task-codemap --full` to rebuild from scratch.
```

### No-op report (early exit)

```markdown
# Codemap Sync Report

**Mode:** no-op (graph is up to date with HEAD; no fingerprint changes)
**Graph commit:** abc1234 (matches HEAD)
**Last built:** 2026-05-30T11:42:00Z
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: Python/git preflight passed; intermediate dir present
- [ ] Step 3: mode decided per the decision matrix; user confirmation requested before `--full` overwrite of existing graph
- [ ] Full path (Step 4): stack detected, ignore file initialized, build pipeline ran all 9 phases
- [ ] Sync path (Step 5): change-set computed; decision tree applied; analysis ran only on changed files; splice preserved unchanged nodes' layer assignments
- [ ] Step 6: `.gitignore` recommendation surfaced on full builds (not auto-applied)
- [ ] Step 7: auto-update config written when flag set; portability caveat surfaced
- [ ] Step 8: validation ran; errors blocked persistence
- [ ] Step 9: artifacts persisted (unless `--validate-only`); report block printed for the correct mode

## Avoid

- Replacing a valid graph silently with `--full`. Confirm first.
- Re-analyzing unchanged files in sync mode. The whole point of incremental.
- Overwriting `graph.json` when validation fails in sync mode. Keep the prior version.
- Regenerating guides during sync. They drift slowly; full rebuilds handle them.
- Recomputing layer for every node during sync - only new and renamed nodes.
- Silently escalating to full rebuild on schema mismatch or high churn without telling the user.
- Running analysis batches sequentially - always 5-way parallel via sub-agents.
- Modifying the user's `.gitignore` automatically. Surface the recommendation; let the user commit it.
- Embedding source code in node summaries. Summaries are intent; code lives in files.
- Renaming Python helpers or moving them outside `task-codemap/`. They are skill-local by design.
