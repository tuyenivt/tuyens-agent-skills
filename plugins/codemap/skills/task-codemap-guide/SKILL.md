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

Guided walkthroughs of the codebase, dependency-ordered, generated during `task-codemap`. Each guide visits 5-8 (basic) or 10-20 (full) nodes with narration explaining why each step matters.

## When to Use

- A new engineer wants to learn the request lifecycle, auth flow, or data layer.
- Pair-programming context-setting before diving into a feature.
- Refresher when returning to an unfamiliar module.

**Not for:**
- Free-form questions - use `task-codemap-ask`.
- Deep-dive on one entity - use `task-codemap-explain`.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| `--list` | No | List available guides and exit. |
| `--guide <name>` | No | Play a specific guide by name. Default: prompt user to pick. |
| `--depth basic\|full` | No | Override the guide's saved depth. `basic` collapses narration to one-line headlines; `full` adds source-code excerpts per step. |
| `--rebuild` | No | Regenerate `guides.json` from the current graph without rebuilding the graph itself. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

1. Confirm `.codemap/graph.json` exists. If missing, suggest `task-codemap` and stop.
2. Confirm `.codemap/guides.json` exists. If missing, offer `--rebuild` and stop.
3. Check freshness; warn if stale.
4. Load graph and guides.

Use skill: `codemap-schema` for guide shape.
Use skill: `codemap-query` for traversal.

### Step 3 - Branch on Mode

#### Mode A: `--list`

Print:

```
Available guides (from .codemap/guides.json):

1. request-lifecycle   basic  - Request lifecycle: login -> JWT (7 steps)
2. auth-flow           full   - Authentication and authorization (14 steps)
3. data-layer          basic  - Repository / ORM walkthrough (6 steps)
4. entrypoints         basic  - All entry points (5 steps)

Run: /task-codemap-guide --guide <name> [--depth basic|full]
```

Stop after listing.

#### Mode B: `--rebuild`

Regenerate `guides.json` from the current graph:

1. Apply the guide-selection heuristic from `codemap-build-pipeline` Phase 7.
2. Write guides back to `.codemap/guides.json`.
3. Validate via `codemap-validate` (guide-step `nodeId`s must exist in `graph.json`).
4. Stop after rebuild; print summary.

#### Mode C: Play a guide (default)

1. If `--guide` not given, list guides and ask the user to pick.
2. Look up the guide. Apply `--depth` override if given; otherwise use the guide's saved depth.
3. For each step, render per the depth contract below.

### Step 4 - Render a Guide Step

For **basic** depth:

```
### Step <order> - <node.name>

**Node:** `<node.id>`
**Where:** `<node.filePath>:<lineStart>-<lineEnd>`
**Why this stop:** <step.narration>
```

For **full** depth, add:

- A short source excerpt (read only the `lineRange` from the file; cap 40 lines per step).
- An "incoming" line listing top 3 callers/importers from graph queries.
- An "outgoing" line listing the next-step calls/imports.

### Step 5 - Guide Summary

After the last step:

```
**Guide summary:**

- Visited <N> nodes across <layers> layers
- Primary path: <entry node> -> ... -> <terminal node>
- Connected concepts (if any concept nodes were visited): ...

Next:
- `/task-codemap-explain <node id>` for deeper dive
- `/task-codemap-ask "<question>"` to ask follow-up
```

### Step 6 - Stale-Graph Footer

If freshness check flagged staleness, append the same one-line note as `task-codemap-ask`:

```
> Codemap built from commit abc1234. Run `/task-codemap` for current data.
```

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

### Step 7 - Audit log write

**Node:** `function:internal/repository/audit.go:Append`
**Where:** `internal/repository/audit.go:12-27`
**Why this stop:** Final persistence step - every login attempt lands here.

**Guide summary:**

- Visited 7 nodes across `api`, `service`, `data`, `infra` layers
- Primary path: `endpoint:POST /login` -> ... -> `table:audit_logs`
- Connected concepts: `JWT`, `Session`

Next:
- `/task-codemap-explain function:internal/auth/jwt.go:Sign`
- `/task-codemap-ask "what other endpoints write to audit_logs?"`
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph + guides loaded; freshness warning if stale
- [ ] Step 3: mode branched correctly (`--list`, `--rebuild`, or play)
- [ ] Step 4: each step rendered per depth contract; source excerpts respect 40-line cap in full mode
- [ ] Step 5: guide summary included
- [ ] Step 6: stale-graph footer when applicable
- [ ] All cited node IDs and line ranges resolve in the current graph

## Avoid

- Inventing guide steps not present in `guides.json`.
- Reading whole files when the node's `lineRange` is the exact span.
- Treating `--depth` as binary fixed - the user may flip it per guide; honor the override.
- Rendering full mode without source excerpts; that's just basic with extra words.
- Skipping the freshness check on long guides where staleness compounds.
