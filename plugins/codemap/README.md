# Tuyen's Agent Skills - Codemap

Opt-in plugin that builds and maintains a **persistent codebase knowledge graph** at `.codemap/graph.json`, plus a small family of workflows that read from it: ask the graph questions, play guided walkthroughs, deep-dive on a single entity.

Pure-LLM extraction. No tree-sitter, no Node toolchain, no `pnpm install`. Skill-local Python helpers (stdlib only) handle deterministic file enumeration, batching, merging, and fingerprinting. Sub-agents do the per-batch semantic analysis in parallel.

Requires the `core` plugin (for `behavioral-principles` and `stack-detect`). No other plugin in this marketplace depends on `codemap` - it stays out of your context unless you install it.

## Install

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install codemap@tuyens-agent-skills --scope project
```

## What you get

```
.codemap/
  graph.json          # nodes + edges + layers (committed, source of truth)
  guides.json         # generated guided walkthroughs (committed)
  meta.json           # builtAt, gitCommitHash, version (committed)
  config.json         # autoUpdate flag, scope (committed)
  fingerprints.json   # per-file structural hashes (committed)
  .codemapignore      # user-editable, defaults to .gitignore (committed)
  .last-synced-head   # last HEAD the auto-update hook fired on (gitignore this)
  intermediate/       # transient build outputs (gitignore this)
```

Commit the artifacts and teammates skip the build entirely - opening the project gets them the graph for free.

**Recommended `.gitignore` additions:**

```
.codemap/intermediate/
.codemap/.last-synced-head
```

## Workflow Skills

| Skill                   | Description                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `task-codemap`          | **Build or sync the graph.** Auto-detects mode: first run does a full build (scan -> batch -> parallel sub-agent analyze -> merge -> layer -> guide -> validate); subsequent runs do an incremental sync via fingerprint diff, re-analyzing only changed files. Use `--full` to force a rebuild, `--auto-update` to toggle the post-commit hook.                            |
| `task-codemap-ask`      | **Questions about the system.** Free-form Q&A over the graph plus targeted file reads. 1-3 sentence answers with node-ID + `file:line` citations. Pick when you don't know which entity matters yet.                                                                                                                                                                      |
| `task-codemap-guide`    | **Guided walkthroughs.** List, play, or rebuild dependency-ordered codebase walkthroughs from `.codemap/guides.json`. `--depth basic\|full` controls narration density. Basic = headlines; full = adds source excerpts and caller/callee context per step.                                                                                                                |
| `task-codemap-explain`  | **Structured deep-dive on one named entity.** Fixed sections: callers, callees, data touchpoints, tests, blast radius, related concepts. Composes stack-specific `*-code-explain` atomics (from installed language plugins) for framework gotchas. Falls back to `task-code-explain` when the graph is missing.                                                              |

### When to use which

| You want to... | Use |
| --- | --- |
| Build the graph for the first time | `/task-codemap` |
| Refresh the graph after your edits or a pull | `/task-codemap` (mode auto-detected) |
| Answer "which handlers write to the orders table?" | `/task-codemap-ask` |
| Onboard to the auth flow end-to-end | `/task-codemap-guide --guide auth-flow` |
| Understand one function's role in the system | `/task-codemap-explain <path>` |
| One-shot Markdown onboarding report (no graph needed) | `/task-onboard` (from `core`) |

## Atomic Skills

Atomic skills are hidden from the slash menu (`user-invocable: false`) and composed by the workflow skills above.

| Skill                     | Description                                                                                                                              |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `codemap-schema`          | Canonical graph schema - 12 node types, 14 edge types, 6 layer enum, JSON shapes for `graph.json`, `guides.json`, `meta.json`, `config.json`. Loaded by every codemap workflow. |
| `codemap-layer-patterns`  | Directory-to-layer mapping (entry/api/service/domain/data/infra) across Spring, Rails, Django, FastAPI, Go, Rust, React, Vue. Used at layer assignment.   |
| `codemap-fingerprints`    | Per-file structural fingerprint contract for incremental sync - hash inputs, comparison rules, change-set shape, escalation thresholds.          |
| `codemap-validate`        | Validates `graph.json` and `guides.json` - 15 error checks (schema, refs, uniqueness, stack block), 8 warning checks (orphans, hubs, layer coverage, test gaps). |
| `codemap-query`           | Read-only traversal patterns - neighbors, fan-in/out, layer filter, path finding, callers/callees, file scope. Used by every consumer workflow.    |
| `codemap-build-pipeline`  | The 9 build phases: scan, batch, parallel sub-agent analyze, merge, repair, layer assign, guide generate, validate, persist. Pure-LLM extraction.    |

## Skill Dependency Index

| Workflow                  | Atomic skills used                                                                                                                                                                                |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `task-codemap`            | `behavioral-principles`, `stack-detect`, `codemap-schema`, `codemap-fingerprints`, `codemap-layer-patterns`, `codemap-validate`, `codemap-build-pipeline`                                          |
| `task-codemap-ask`        | `behavioral-principles`, `codemap-schema`, `codemap-query`                                                                                                                                          |
| `task-codemap-guide`      | `behavioral-principles`, `codemap-schema`, `codemap-query`, `codemap-validate` (on `--rebuild`)                                                                                                     |
| `task-codemap-explain`    | `behavioral-principles`, `stack-detect`, `codemap-schema`, `codemap-query` + `*-code-explain` (per installed stack plugin), `architecture-guardrail`, `complexity-review`                            |

`behavioral-principles`, `stack-detect`, `architecture-guardrail`, `complexity-review` all live in the `core` plugin (required).

## Usage Examples

**First-time build:**

```
/task-codemap
```

Scans the repo, batches files, dispatches up to 5 parallel sub-agents to extract a structured graph, assigns architectural layers, generates 3-5 guided walkthroughs, validates, and writes `.codemap/graph.json` + `guides.json` + `meta.json` + `fingerprints.json`.

**Sync after edits or a pull:**

```
/task-codemap
```

Same slash command. The workflow detects the existing `.codemap/` and runs an incremental sync via fingerprint diff - re-analyzing only changed files. Auto-escalates to a full rebuild on >=30% churn or schema-version bump. Use `--full` to force.

**Enable the auto-update hook (Claude Code only):**

```
/task-codemap --auto-update
```

Sets `autoUpdate: true` in `.codemap/config.json`. The plugin's hook then auto-syncs on `git commit | merge | rebase | cherry-pick` and at session start when HEAD has drifted from the graph. Disable with `/task-codemap --auto-update=false`.

**Ask the graph anything:**

```
/task-codemap-ask How does the payment flow work?
/task-codemap-ask Which handlers write to the orders table?
/task-codemap-ask Where is the JWT signing key configured?
```

**Play a guided walkthrough:**

```
/task-codemap-guide --list
/task-codemap-guide --guide request-lifecycle --depth full
```

**Deep-dive on a single entity:**

```
/task-codemap-explain src/auth/login.ts
/task-codemap-explain function:internal/auth/login.go:Authenticate
```

## Hooks

The plugin ships one optional hook at `hooks/codemap-auto-update.json`. It activates only when `.codemap/config.json` has `autoUpdate: true` (set via `/task-codemap --auto-update`).

- **`PostToolUse`** on `Bash` matching `git (commit|merge|cherry-pick|rebase)` - prints an instruction to sync the graph after the commit lands.
- **`SessionStart`** - compares `.codemap/meta.json#gitCommitHash` to current `HEAD` via Python; instructs a sync when stale.

The instruction text directs the agent to read `hooks/codemap-refresh-prompt.md` and run `/task-codemap` without user confirmation. The workflow's own decision tree picks incremental sync vs full rebuild.

Claude Code is the only platform with hook support. Users on Codex, Cursor, Copilot, etc. run `/task-codemap` manually after pulls.

## Requirements

- **Claude Code.** The workflows shell out to skill-local Python scripts via `${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/*.py` - that env var is set by Claude Code's plugin runtime. Other platforms (Codex, Cursor, Copilot, Gemini CLI) install the plugin's skill bodies fine but will not resolve the script paths; they cannot run `/task-codemap` or `/task-codemap` sync. The read-only workflows (`/task-codemap-ask`, `/task-codemap-guide`, `/task-codemap-explain`) work everywhere as long as `.codemap/graph.json` already exists - so a teammate on Codex can still query a graph that a Claude Code user built and committed.
- **Python 3** on PATH (skill-local helpers use stdlib only - no `pip install` needed).
- **git** on PATH (for fingerprints and HEAD comparison; scan falls back to `os.walk` if missing).
- **Hooks (optional, auto-update only) require a POSIX shell.** The hook command uses `[ -f ... ]`, `grep -q`, `printf`. Works on Linux/macOS out of the box; on Windows it needs Git Bash or WSL on PATH. On native Windows without either, leave `autoUpdate: false` and run `/task-codemap` manually after pulls.
- The `core` plugin installed in the same project.

## Sharing the graph with your team

The graph is just JSON - **commit it once, teammates skip the build**. Good for onboarding, PR reviews, and docs-as-code.

**Commit:** `.codemap/graph.json`, `.codemap/guides.json`, `.codemap/meta.json`, `.codemap/config.json`, `.codemap/fingerprints.json`, `.codemap/.codemapignore`.

**Gitignore:** `.codemap/intermediate/`, `.codemap/.last-synced-head`.

**Keep it fresh:** enable `--auto-update`, or run `/task-codemap` manually after pulls and before releases.

For graphs above ~10 MB, track with **git-lfs**.

**Note on diff churn:** `meta.json#builtAt` and `fingerprints.json#computedAt` are ISO timestamps, so every rebuild produces a non-zero diff even when the graph itself is unchanged. If diff noise on these files is a problem, consider a pre-commit hook that strips them, or accept the churn in exchange for a recorded build time.

## License

Same as the parent marketplace.
