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

**Two modes, one command:**
- First run (no `.codemap/graph.json`) -> full build.
- Subsequent runs -> incremental sync via fingerprint diff.

The optional auto-update hook invokes this workflow on `git commit | merge | rebase | cherry-pick` and on session-start drift.

## When to Use

- First-time setup.
- After commits, `git pull`, or a merge.
- After major refactors (auto-escalates to full rebuild at >=30% churn or schema bump).
- Before sharing the graph with the team (commit the `.codemap/` artifacts).

**Not for:**
- One-shot Markdown onboarding -> `task-onboard`.
- Questions about the graph -> `task-codemap-ask`.
- Guided walkthroughs -> `task-codemap-guide`.
- Single-entity deep dive -> `task-codemap-explain`.

## Inputs

| Input | Notes |
| --- | --- |
| `[path]` | Repo root (default `.`) or scope subdirectory. |
| `--full` | Force full rebuild. |
| `--scope <dir>` | Limit to a subdirectory (huge monorepos). CLI flag overrides `.codemap/config.json#scope`; persisted to `config.json` on each run. |
| `--auto-update[=false]` | Toggle the post-commit + session-start hook in `config.json`. |
| `--validate-only` | Validate the existing graph without rebuilding. |
| `--force` | In sync mode, skip the "no changes" early exit. |
| `--rebuild-on <ratio>` | Override the 30% full-rebuild churn threshold. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

1. Confirm `python --version` (or `python3`). Abort with friendly error if missing.
2. Confirm `git`. Required for fingerprints; scan falls back to `os.walk` without it.
3. Create `.codemap/intermediate/` if missing.

### Step 3 - Decide Mode

| Condition | Mode |
| --- | --- |
| `--validate-only` | Validate-only -> Step 8. |
| `--full`, or `graph.json` / `fingerprints.json` missing | Full build -> Step 4. |
| `graph.json`, `meta.json`, `fingerprints.json` all present | Sync -> Step 5. |

When `--full` would overwrite an existing graph, confirm with the user first.

### Step 4 - Full Build

1. **Stack:** `Use skill: stack-detect`. Cache; reused in phases 3, 6, 7.
2. **Ignore file:** if `.codemap/.codemapignore` missing, copy `.gitignore` + banner.
3. **Resolve scope:** CLI `--scope` wins; otherwise read `.codemap/config.json#scope`. Pass to `scan.py` in pipeline Phase 1 and persist to `config.json` on completion.
4. **Pipeline:** `Use skill: codemap-build-pipeline`. Runs phases 1-9. Track per-phase wall-clock.

Validation errors abort - do not persist. Skip to Step 7.

### Step 5 - Incremental Sync

#### 5a. Compute Change-Set

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/scan.py" --root <path> [--scope <dir>] --output .codemap/intermediate/scan.json
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compute --scan .codemap/intermediate/scan.json --output .codemap/intermediate/fingerprints-current.json
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compare --current .codemap/intermediate/fingerprints-current.json --previous .codemap/fingerprints.json --output .codemap/intermediate/change-set.json
```

Resolve `--scope` the same way as Step 4 (CLI flag wins over `config.json#scope`).

Use skill: `codemap-fingerprints` for the contract.

#### 5b. Apply Decision Tree

| Change-set | Action |
| --- | --- |
| `schemaVersionChanged: true` | Escalate to `--full`, surface note, stop. |
| `churnRatio >= 0.30` (or `--rebuild-on` override) | Escalate to `--full`. |
| All empty, HEAD matches | Early exit: "graph up to date". Skip to Step 8. |
| All empty, HEAD stale | Update `meta.json#gitCommitHash` only; skip 5c-5d. |
| `deleted` only | Splice (drop) + validate. No analysis. |
| `renamed` only | Splice (rename) + validate. No analysis. |
| `added` or `modified` | Run 5c + 5d. |

#### 5c. Analyze Changed Files

`Use skill: stack-detect` (reuse cached). Build batches (group by directory, cap 25/800 KB). Dispatch sub-agents per `codemap-build-pipeline` Phase 3.

#### 5d. Splice

1. Load existing `graph.json`.
2. Drop nodes in `modified` / `deleted`; drop edges with dropped endpoints.
3. `renamed`: rewrite `filePath` and any node `id` containing the old path; rewrite affected edges.
4. Merge new nodes/edges (dedup logic from `merge.py`).
5. Re-layer **only** new/rewritten nodes via `codemap-layer-patterns`.
6. Guides do **not** regenerate. `task-codemap-guide --rebuild` or `--full` to refresh.

### Step 6 - Configure Auto-Update (when `--auto-update` set)

Write `autoUpdate` to `.codemap/config.json`. If enabled, surface:

- Claude Code auto-registers `plugins/codemap/hooks/codemap-auto-update.json`. Hook fires on commit/merge/rebase/cherry-pick and on session-start when HEAD drifts.
- Codex/Cursor/Copilot have no hook support - run `/task-codemap` manually after pulls.

### Step 7 - Validate

`Use skill: codemap-validate`.

- Full build: validation already ran in pipeline Phase 8.
- Sync: validate the spliced graph now. **On error, keep the prior `graph.json` intact** - do not overwrite.

### Step 8 - Persist & Report

**Persist** (skip if `--validate-only`):

- Full build: handled by pipeline Phase 9.
- Sync: write spliced graph; update `meta.json`; promote `fingerprints-current.json` -> `fingerprints.json`; delete `intermediate/`.

**Report:** render the appropriate template below.

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
| 3. Analyze | 18 batches, 5-way parallel (0 dropped after retries) | 96s |
| 4. Merge | 412 nodes, 1184 edges (12 dangling dropped, 0 malformed) | <1s |
| 5. Repair | clean | 4s |
| 6. Layers | 88% assigned | 6s |
| 7. Guides | 4 generated | 8s |
| 8. Validate | 0 errors, 2 warnings | <1s |
| 9. Persist | graph.json (412 KB), guides.json (18 KB) | <1s |

## Validation Summary

**Errors:** 0
**Warnings:**
- W4: Layer coverage 88% - OK
- W7: 0 document nodes despite README.md present

## Artifacts

- `.codemap/graph.json`, `guides.json`, `meta.json`, `config.json`, `fingerprints.json`, `.codemapignore`

## Recommended .gitignore

```
.codemap/intermediate/
.codemap/.last-synced-head
```

## Next

- `/task-codemap-guide --list` - browse walkthroughs
- `/task-codemap-ask "<question>"` - ask the graph
- `/task-codemap-explain <path>` - deep-dive
- `/task-codemap` after future commits (or enable `--auto-update`)
```

### Sync report

```markdown
# Codemap Sync Report

**Mode:** incremental sync (12.4% churn)
**From commit:** abc1234 -> def5678
**Synced at:** 2026-05-30T12:00:00Z

## Change-Set

- Added: 3, Modified: 18, Renamed: 2, Deleted: 1, Unchanged: 388

## Pipeline

| Phase | Result | Wall-clock |
| --- | --- | --- |
| Scan + Fingerprint | 21 changed | 2s |
| Analyze | 2 batches, 2-way parallel | 14s |
| Splice | -29 nodes / -78 edges / +34 nodes / +91 edges | <1s |
| Validate | 0 errors, 1 warning | <1s |
| Persist | graph.json updated | <1s |

## Next

- Guides not regenerated. `/task-codemap-guide --rebuild` for fresh walkthroughs.
- Or `/task-codemap --full` to rebuild from scratch.
```

### No-op

```markdown
# Codemap Sync Report

**Mode:** no-op (graph in sync with HEAD; no fingerprint changes)
**Graph commit:** abc1234
**Last built:** 2026-05-30T11:42:00Z
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: Python/git preflight passed; intermediate dir present
- [ ] Step 3: mode decided; `--full` overwrite confirmed with user
- [ ] Step 4: stack detected, ignore initialized, scope resolved (CLI wins over `config.json#scope`), pipeline ran all 9 phases (full path)
- [ ] Step 5: change-set computed; decision tree applied; analysis only on changed files; splice preserved existing layer assignments (sync path)
- [ ] Step 6: auto-update config written + portability caveat surfaced (when flag set)
- [ ] Step 7: validation ran; errors did not overwrite prior graph (sync OR full mode)
- [ ] Step 8: persisted (unless `--validate-only`); correct report rendered

## Avoid

- Silently overwriting a valid graph with `--full`. Confirm first.
- Re-analyzing unchanged files in sync mode.
- Overwriting `graph.json` when sync validation fails.
- Regenerating guides during sync.
- Recomputing layer for unchanged nodes during sync.
- Auto-modifying the user's `.gitignore`. Surface the recommendation.
