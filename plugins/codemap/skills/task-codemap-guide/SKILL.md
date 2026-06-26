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
2. Missing `.codemap/guides.json` -> if `--rebuild` was passed, proceed (that's the remedy); otherwise offer `--rebuild` and stop.
3. Run the `codemap-query` freshness check; warn but proceed when stale.
4. Load the graph (and guides.json when present).

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
4. Print a one-line summary (`Rebuilt N guides, total M steps`). If **zero** guides qualified (e.g., a library with no entry/api/data/domain layers), that is a valid outcome - say so explicitly: `No guides generated - this graph has no request/auth/data/entry flow to walk. Use /task-codemap-ask for targeted questions.`

**Play (default)** - continue to Step 4:

1. If `--guide` missing, list guides and ask the user to pick.
2. Look up the guide. Unknown name -> list the available guides and stop. Apply `--depth` override if given.
3. Verify each step's `nodeId` still resolves in the freshly loaded graph (guides.json can lag a rebuild). Drop steps whose node was deleted, renumber `order`, and note `(N steps dropped - guide stale, run --rebuild)`.

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
- Source excerpt from `node.lineRange` (cap 40 lines per step, from the start of the range). Abstract nodes (`table`, `concept`, `module`, `service`) have no `lineRange` - render the node `summary` in place of an excerpt; don't fabricate source.
- "Incoming" line: top 3 callers/importers, ranked by edge weight then ascending node ID (per `codemap-query` cap rule).
- "Outgoing" line: next-step calls/imports.

A guide authored `basic` has a basic-sized step set (5-8). `--depth full` over it adds excerpts/context to those steps but keeps the count - label the header `(full render of a basic guide, N steps)` so it isn't mistaken for a 10-20 step full guide. For a true full guide, run `--rebuild`.

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

Stale variant of the freshness footer (use the canonical `codemap-query` format verbatim):

```
> Codemap built from commit abc1234 (12 commits behind HEAD, 9 days old). Run `/task-codemap` to sync.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph + guides loaded; freshness warning when stale
- [ ] Step 3: mode branched correctly; `--list` / `--rebuild` exited (0-guides outcome stated when applicable); unknown guide name listed available; play-path step nodeIds re-verified against the graph
- [ ] Step 4: depth contract honored; full mode includes excerpts (or summary for abstract nodes) within the 40-line cap; basic-guide full render labeled
- [ ] Step 5: guide summary + freshness footer included
- [ ] All cited node IDs resolve in the current graph (stale steps dropped in Step 3.3)

## Avoid

- Inventing steps not in `guides.json`.
- Reading whole files when `lineRange` is the exact span.
- Skipping freshness on long guides where staleness compounds.
