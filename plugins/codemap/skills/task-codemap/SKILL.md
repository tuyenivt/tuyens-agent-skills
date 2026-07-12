---
name: task-codemap
description: Build or sync persistent codebase knowledge graph at .codemap/graph.json. Auto-detects full build vs incremental refresh. Pure-LLM, no tree-sitter.
metadata:
  category: code
  tags: [codemap, knowledge-graph, onboarding, architecture, multi-stack]
  type: workflow
user-invocable: true
---

# Task: Codemap

Produces and maintains `.codemap/graph.json` - a persistent, commit-friendly graph of every significant file, function, class, endpoint, and their relationships. Powers `task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`. Commit the graph and teammates skip the build.

One command, two modes: first run -> full build; subsequent runs -> incremental sync via fingerprint diff. Re-run after commits, pulls, or merges to keep the graph current.

## When to Use

- First-time setup.
- After commits, `git pull`, or a merge.
- After major refactors (auto-escalates to full rebuild at >=30% churn or schema bump).
- Before sharing the graph with the team (commit the `.codemap/` artifacts).

**Not for:** one-shot Markdown onboarding (`task-onboard`); questions (`task-codemap-ask`); walkthroughs (`task-codemap-guide`); single-entity deep-dive (`task-codemap-explain`).

## Inputs

| Input | Notes |
| --- | --- |
| `[path]` | Repo root (default `.`) or scope subdirectory. |
| `--full` | Force full rebuild. Confirm with user before overwriting an existing graph. |
| `--scope <dir>` | Limit to subdirectory. CLI flag wins over `.codemap/config.json#scope`; persisted to `config.json` each run. |
| `--validate-only` | Validate existing graph without rebuilding. |
| `--force` | Sync mode: bypass the "no changes" early exit; re-run analysis on all files in the change-set even if hashes match. |
| `--rebuild-on <ratio>` | Override the 30% full-rebuild churn threshold. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

1. Confirm `python --version` (or `python3`). Abort with friendly error if missing.
2. Confirm `git`. Required for fingerprints; scan falls back to `os.walk` without it.
3. Ensure `.codemap/intermediate/` exists and is empty (clear stale contents from a prior crash).

### Step 3 - Decide Mode

| Condition | Mode |
| --- | --- |
| `--validate-only` | Validate-only -> Step 6 (validate existing `graph.json`), then Step 7 (report only). |
| `--full`, or any of `graph.json` / `meta.json` / `fingerprints.json` missing | Full build -> Step 4. |
| All three present | Sync -> Step 5. |

When `--full` would overwrite an existing graph, confirm with the user first.

### Step 4 - Full Build

1. `Use skill: stack-detect`. Cache; reused by pipeline phases 3, 6, 7.
2. If `.codemap/.codemapignore` missing, copy `.gitignore` plus a one-line banner comment: `# Seeded from .gitignore by task-codemap - edit freely.`
3. Resolve scope: CLI `--scope` wins; otherwise `.codemap/config.json#scope`. Persist to `config.json` on completion.
4. `Use skill: codemap-build-pipeline`. Tracks per-phase wall-clock.

On validation failure: do not persist. Skip to Step 7.

### Step 5 - Incremental Sync

#### 5a. Compute Change-Set

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/scan.py" --root <path> [--scope <dir>] --output .codemap/intermediate/scan.json
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compute --scan .codemap/intermediate/scan.json --output .codemap/intermediate/fingerprints-current.json
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compare --current .codemap/intermediate/fingerprints-current.json --previous .codemap/fingerprints.json --output .codemap/intermediate/change-set.json
```

Resolve `--scope` the same way as Step 4.

Use skill: `codemap-fingerprints` for the change-set contract, the refresh decision matrix, and splice semantics.

#### 5b. Act on the Change-Set

Apply the refresh decision matrix from `codemap-fingerprints`:

Churn = changed files / total scanned files, where changed = added + modified + renamed + deleted. The threshold defaults to 30%; `--rebuild-on <ratio>` overrides it.

- **Escalation rows** (`schemaVersionChanged: true`, or churn >= threshold): switch to Step 4 and run a full rebuild. Escalation is an intended response to high churn, so do not re-prompt for overwrite confirmation (that gate is only for an explicit `--full`). The pipeline reuses `intermediate/scan.json` from 5a (same scope, same HEAD) instead of re-running Phase 1. Step 7 renders the **full build report** with the mode line `**Mode:** full build (escalated from sync at <N.N>% churn)`.
- **No-op rows**: jump to Step 7. When HEAD drifted but no files changed, update `meta.json#gitCommitHash` before reporting.
- **Splice-only rows** (`deleted` only, `renamed` only): apply splice semantics from `codemap-fingerprints`, skip 5c.
- **Mixed rows** (any of `added`/`modified` combined with `deleted`/`renamed`, or `--force`): run 5c then 5d; the splice in 5d also drops `deleted` nodes and rewrites `renamed` paths/IDs per `codemap-fingerprints`.

#### 5c. Analyze Changed Files

`Use skill: stack-detect` and cache the result (sync has no earlier detection to reuse; the cache serves 5d re-layering). Build batches inline from the change-set (batch.py takes a full scan, not a file list) (group by directory, cap 25 files / 800 KB). Dispatch sub-agents per `codemap-build-pipeline` Phase 3.

#### 5d. Splice

Apply splice semantics from `codemap-fingerprints`. Re-layer only new/rewritten nodes via `codemap-layer-patterns`. Guides do not regenerate - point user at `task-codemap-guide --rebuild` or `task-codemap --full`.

### Step 6 - Validate

`Use skill: codemap-validate`.

- Full build: validation already ran inside pipeline phase 8. Skip.
- Sync: validate the spliced graph. **On error, keep the prior `graph.json` intact** - do not overwrite - then escalate to a full rebuild (Step 4), per `codemap-fingerprints` splice semantics.
- Validate-only: validate the existing `graph.json` (+ `guides.json` when present), promote the report to `.codemap/validation.json`, then go to Step 7 to render the validate-only report. No persistence of the graph.

### Step 7 - Persist & Report

**Persist** (skip if `--validate-only`):

- Full build: handled by pipeline phase 9.
- Sync: write spliced graph; update `meta.json` (`builtAt`, `gitCommitHash`, `analyzedFiles`); promote `fingerprints-current.json` -> `fingerprints.json`; delete `intermediate/`.

**Report:** render the template that matches the mode. When a full build failed validation, nothing was persisted (including `config.json`, which is written only on completion): keep the Validation Summary with errors grouped by check and omit the Artifacts and Next sections.

## Output Format

### Full build report

```markdown
# Codemap Build Report

**Mode:** full build
**Built at:** 2026-05-30T12:00:00Z | **Commit:** abc1234
**Stack:** Go 1.25 / Gin + GORM (backend) | **Scope:** . (full repo)

## Pipeline

(Per-phase rows as emitted by `codemap-build-pipeline` Output Format.)

## Validation Summary

**Errors:** 0
**Warnings:**
- W4: Layer coverage 88% - OK
- W7: 0 document nodes despite README.md present

## Artifacts

`.codemap/graph.json`, `guides.json`, `meta.json`, `config.json`, `fingerprints.json`, `.codemapignore`

## Recommended .gitignore

```
.codemap/intermediate/
```

## Next

- `/task-codemap-guide --list`
- `/task-codemap-ask "<question>"`
- `/task-codemap-explain <path>`
- Re-run `/task-codemap` after future commits
```

### Sync report

```markdown
# Codemap Sync Report

**Mode:** incremental sync (12.4% churn)
**From -> To:** abc1234 -> def5678 | **Synced at:** 2026-05-30T12:00:00Z

## Change-Set

Added: 3, Modified: 18, Renamed: 2, Deleted: 1, Unchanged: 388

## Pipeline

| Phase | Result | Wall-clock |
| --- | --- | --- |
| Scan + Fingerprint | 21 changed | 2s |
| Analyze | 2 batches, 2-way parallel | 14s |
| Splice | -29 nodes / -78 edges / +34 nodes / +91 edges | <1s |
| Validate | 0 errors, 1 warning | <1s |
| Persist | graph.json updated | <1s |

## Next

- Guides not regenerated. `/task-codemap-guide --rebuild` to refresh, or `/task-codemap --full` to rebuild from scratch.
```

### No-op

```markdown
# Codemap Sync Report

**Mode:** no-op (graph in sync with HEAD; no fingerprint changes)
**Graph commit:** abc1234 | **Last built:** 2026-05-30T11:42:00Z
```

### Validate-only

```markdown
# Codemap Validation Report

**Mode:** validate-only (existing graph; nothing rebuilt)
**Graph commit:** abc1234 | **Validated at:** 2026-05-30T12:00:00Z

(Render `codemap-validate` Output Format: errors grouped by check, warnings, stats, and the outcome summary line.)

Report written to `.codemap/validation.json`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: Python/git preflight passed; `intermediate/` exists and empty
- [ ] Step 3: mode decided; `--full` overwrite confirmed; `--validate-only` routed through Step 6
- [ ] Step 4: stack detected, ignore initialized, scope resolved, pipeline ran (full path or sync escalation)
- [ ] Step 5: change-set computed; decision matrix applied; analysis only on changed files (non-escalated sync path)
- [ ] Step 6: validation ran (sync, escalation-skip, or validate-only); on sync error the prior `graph.json` was preserved and sync escalated to full rebuild; `validation.json` promoted when `--validate-only`
- [ ] Step 7: persisted (unless `--validate-only`); correct report rendered

## Avoid

- Silently overwriting a valid graph with `--full` - confirm first.
- Re-analyzing unchanged files in sync mode (except when `--force`).
- Overwriting `graph.json` when sync validation fails.
- Regenerating guides during sync.
- Re-layering unchanged nodes during sync.
- Auto-modifying the user's `.gitignore` - surface the recommendation only.
