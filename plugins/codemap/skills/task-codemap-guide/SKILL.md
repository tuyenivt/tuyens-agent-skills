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

**Not for:**
- Free-form questions -> `task-codemap-ask`.
- Single-entity deep-dive -> `task-codemap-explain`.

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

1. Confirm `.codemap/graph.json` exists. Missing -> suggest `/task-codemap` and stop.
2. Confirm `.codemap/guides.json` exists. Missing -> offer `--rebuild` and stop.
3. Apply the freshness rule from `codemap-query` (Freshness check); warn but proceed when stale.
4. Load both.

Use skill: `codemap-schema` for guide shape. Use skill: `codemap-query` for traversal and the freshness rule.

### Step 3 - Branch on Mode

#### `--list`

```
Available guides (from .codemap/guides.json):

1. request-lifecycle   basic  - Request lifecycle: login -> JWT (7 steps)
2. auth-flow           full   - Authentication and authorization (14 steps)
3. data-layer          basic  - Repository / ORM walkthrough (6 steps)
4. entrypoints         basic  - All entry points (5 steps)

Run: /task-codemap-guide --guide <name> [--depth basic|full]
```

#### `--rebuild`

1. Apply the guide-selection heuristic from `codemap-build-pipeline` Phase 7.
2. Write `.codemap/guides.json`.
3. Validate via `codemap-validate` (every step `nodeId` must exist in `graph.json`).
4. Print summary, stop.

#### Play a guide (default)

1. If `--guide` missing, list and ask the user to pick.
2. Look up the guide; apply `--depth` override if given.
3. Render per the depth contract.

### Step 4 - Render a Step

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

### Step 5 - Guide Summary

```
**Guide summary:**

- Visited <N> nodes across <layers> layers
- Primary path: <entry> -> ... -> <terminal>
- Connected concepts (if any): ...

Next:
- `/task-codemap-explain <node id>` for deeper dive
- `/task-codemap-ask "<question>"` for follow-up
```

### Step 6 - Stale-Graph Footer

When applicable:

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

**Guide summary:**

- Visited 7 nodes across `api`, `service`, `data`, `infra` layers
- Primary path: `endpoint:POST /login` -> ... -> `table:audit_logs`
- Connected concepts: `JWT`, `Session`
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph + guides loaded; freshness warning when stale
- [ ] Step 3: mode branched correctly
- [ ] Step 4: depth contract honored; full mode includes source excerpts within the 40-line cap
- [ ] Step 5: guide summary included
- [ ] Step 6: stale-graph footer when applicable
- [ ] All cited node IDs resolve in the current graph

## Avoid

- Inventing steps not in `guides.json`.
- Reading whole files when `lineRange` is the exact span.
- Full mode without source excerpts - that's just basic with extra words.
- Skipping freshness on long guides where staleness compounds.
