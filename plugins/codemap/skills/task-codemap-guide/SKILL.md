---
name: task-codemap-guide
description: Play dependency-ordered codebase guides from .codemap/guides.json - basic headlines or full narration. List, play, or rebuild guides.
metadata:
  category: code
  tags: [codemap, guide, walkthrough, knowledge-graph, onboarding]
  type: workflow
user-invocable: true
---

# Task: Codemap Guide

Guided codebase walkthroughs generated during `task-codemap`. Each guide visits 5-8 (basic) or 10-20 (full) nodes with narration explaining each stop.

## When to Use

- Onboarding a new engineer to the request lifecycle, auth flow, or data layer.
- Pair-programming context-setting before a feature dive.
- Refresher on an unfamiliar module.

**Not for:** free-form questions (`task-codemap-ask`); single-entity deep-dive (`task-codemap-explain`).

## Inputs

| Input | Notes |
| --- | --- |
| `--list` | List available guides and exit. |
| `--guide <name>` | Play a specific guide. Without it, prompt the user to pick. |
| `--depth basic\|full` | Override the guide's saved depth. |
| `--rebuild` | Regenerate `guides.json` from the current graph. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

Use skill: `codemap-schema` (guide shape). Use skill: `codemap-query` (traversal patterns, freshness check).

1. Missing `.codemap/graph.json` -> suggest `/task-codemap` and stop.
2. Missing `.codemap/guides.json` -> offer `--rebuild` and stop.
3. Run the `codemap-query` freshness check; warn but proceed when stale.
4. Load both.

### Step 3 - Branch on Mode

**`--list`** - print the available guides, then stop:

```
Available guides (from .codemap/guides.json):

1. request-lifecycle   basic  - Request lifecycle: login -> JWT (7 steps)
2. auth-flow           full   - Authentication and authorization (14 steps)
3. data-layer          basic  - Repository / ORM walkthrough (6 steps)
4. entrypoints         basic  - All entry points (5 steps)

Run: /task-codemap-guide --guide <name> [--depth basic|full]
```

**`--rebuild`** - regenerate `guides.json`, then stop:

1. Apply the guide-selection heuristic from `codemap-build-pipeline` Phase 7.
2. Write `.codemap/guides.json`.
3. `Use skill: codemap-validate`.
4. Print a one-line summary (`Rebuilt N guides, total M steps`).

**Play (default)** - continue to Step 4:

1. If `--guide` missing, list guides and ask the user to pick.
2. Look up the guide; apply `--depth` override if given.

### Step 4 - Render Steps

For each step, follow the depth contract:

**Basic:**

```
### Step <order> - <node.name>

**Node:** `<node.id>`
**Where:** `<node.filePath>:<lineStart>-<lineEnd>`
**Why this stop:** <step.narration>
```

**Full:** basic plus
- Source excerpt from `node.lineRange` (cap 40 lines per step).
- "Incoming" line: top 3 callers/importers.
- "Outgoing" line: next-step calls/imports.

Full mode without source excerpts is just basic with extra words - skip it or include excerpts.

### Step 5 - Render Summary + Footer

```
**Guide summary:**

- Visited <N> nodes across <layers> layers
- Primary path: <entry> -> ... -> <terminal>
- Connected concepts (if any): ...

Next:
- `/task-codemap-explain <node id>` for deeper dive
- `/task-codemap-ask "<question>"` for follow-up
```

Append the freshness footer per Output Format.

## Output Format

```markdown
# Guide: request-lifecycle (basic, 7 steps)

> Codemap freshness: in sync with HEAD.

### Step 1 - Login endpoint

**Node:** `endpoint:POST /login`
**Where:** `internal/handler/auth.go:18-32`
**Why this stop:** Entry point for password-based authentication. Maps to the `Login` handler.

### Step 2 - Login handler

**Node:** `function:internal/handler/auth.go:Login`
**Where:** `internal/handler/auth.go:34-58`
**Why this stop:** Parses the request body, delegates to the auth service, returns the JWT or a 401.

...

**Guide summary:**

- Visited 7 nodes across `api`, `service`, `data`, `infra` layers
- Primary path: `endpoint:POST /login` -> ... -> `table:audit_logs`
- Connected concepts: `JWT`, `Session`
```

Stale variant of the freshness footer:

```
> Codemap built from commit abc1234. Run `/task-codemap` for current data.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph + guides loaded; freshness warning when stale
- [ ] Step 3: mode branched correctly; `--list` / `--rebuild` exited; play mode proceeded
- [ ] Step 4: depth contract honored; full mode includes source excerpts within the 40-line cap
- [ ] Step 5: guide summary + freshness footer included
- [ ] All cited node IDs resolve in the current graph

## Avoid

- Inventing steps not in `guides.json`.
- Reading whole files when `lineRange` is the exact span.
- Skipping freshness on long guides where staleness compounds.
