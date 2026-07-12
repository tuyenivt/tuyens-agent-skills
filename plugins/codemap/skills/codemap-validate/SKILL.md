---
name: codemap-validate
description: Validate codemap graph - schema conformance, referential integrity, dangling edges, ID uniqueness, layer coverage, guide resolvability, top-level fields.
metadata:
  category: core
  tags: [codemap, validation, integrity, quality]
user-invocable: false
---

# Codemap Validate

> Load `Use skill: codemap-schema` for the canonical shape.

Last step of every build or refresh. Confirms `graph.json` (and `guides.json` when present) meet the schema contract.

## When to Use

- Final phase of `codemap-build-pipeline` after merge + layer + guides.
- Final phase of `task-codemap` sync after splice.
- On-demand against an existing graph (`task-codemap --validate-only`).

## Rules

1. **Errors block persistence; warnings log only.**
2. **Exhaustive single pass.** Run every check against every node/edge; do not short-circuit. A node failing several checks produces one finding per failed check (independent predicates), not one combined finding.
3. **One finding per check.** Each check emits at most one entry, aggregating all affected entities in `details` (e.g., W5 lists all empty layers in one finding). So `errors.length`/`warnings.length` and the summary counts are deterministic regardless of graph size.
4. **Report only, no fixing.** Auto-repair belongs in merge, not here.

## Patterns

### Error checks (block persistence)

| # | Check | Failure example |
| --- | --- | --- |
| 1 | Top-level `schemaVersion` matches current | `schemaVersion: 0` against current `1` |
| 2 | `nodes` and `edges` are arrays | `nodes: null` |
| 3 | Every node has `id`, `type`, `name`, `summary`, `tags` | Missing `summary` |
| 4 | Every node `type` is in the 12-value enum | `type: "method"` |
| 5 | Node IDs globally unique | Two nodes with `id: file:src/auth/login.ts` |
| 6 | Node ID matches its type's format: file-backed `<type>:<path>[:<name>]`; abstract types (`concept`, `service`, `table`, `schema`, `resource`, `endpoint`) `<type>:<name>` | `id: login` |
| 7 | Code nodes (`function`, `class`) reference an existing file node | `function:src/foo.ts:bar` exists but `file:src/foo.ts` does not |
| 8 | Every edge `type` is in the 14-value enum | `type: "invokes"` |
| 9 | Edge `source` and `target` reference existing nodes | Edge to a node not in `nodes` |
| 10 | `lineRange` is `[start, end]`, `start <= end`, `start >= 1` | `[42, 10]` |
| 11 | `tags` is a 1-5 element string array | `tags: "auth"` |
| 12 | `complexity`, when present, is in `{simple, moderate, complex}` | `complexity: "high"` |
| 13 | `layer`, when present, is in the 6-value enum | `layer: "controller"` |
| 14 | `guides.json` steps reference live nodes, have monotonically increasing `order`, and `depth` is `basic` or `full` | Stale node ID, out-of-order step, `depth: "medium"` |
| 15 | Top-level `stack` is an object with `language`, `framework`, `stackType` (strings; framework may be `null`) | `stack: null` or missing |

### Warning checks (non-blocking)

| # | Check | Signal |
| --- | --- | --- |
| W1 | Orphan nodes (0 in, 0 out edges) | Standalone util with no callers/imports |
| W2 | Self-edges (`source == target`) | Recursion not flagged |
| W3 | Duplicate edges (`source, target, type`) | Same import twice |
| W4 | >25% of nodes have no `layer` - exclude test files from the denominator (targets of `tested_by` edges, or paths matching test conventions), matching `codemap-layer-patterns` | Layout doesn't match patterns table |
| W5 | A layer has 0 nodes (skip when `nodes` < 50 - small/partial graphs won't populate all 6 layers; use `stack.stackType` to skip benign cases: frontend-only -> `data` may be empty; library -> `entry`/`api` may be empty) | `data` empty in a fullstack |
| W6 | Hub node with > 50 outgoing edges | God-module candidate |
| W7 | 0 `document` nodes despite `README.md` at root | Docs not analyzed |
| W8 | 0 `tested_by` edges when the graph contains test files (paths matching test conventions) - self-contained, no stack-detect dependency, so it works in `--validate-only` | Tests not linked |
| W9 | Code nodes (`function`, `class`) missing `complexity` | Repair backfill was skipped |

### Output shape

```json
{
  "schemaVersion": 1,
  "validatedAt": "2026-05-30T12:00:00Z",
  "errors": [
    { "check": 5, "message": "Duplicate node ID", "details": "file:src/auth/login.ts appears 2 times" }
  ],
  "warnings": [
    { "check": "W4", "message": "Layer coverage below threshold", "details": "32% unassigned (132 of 412)" }
  ],
  "stats": {
    "nodes": 412,
    "edges": 1184,
    "nodesByType": { "file": 198, "function": 156, "class": 42 },
    "edgesByType": { "imports": 612, "calls": 388 },
    "nodesByLayer": { "entry": 8, "api": 64, "service": 88, "domain": 42, "data": 70, "infra": 18, "unassigned": 122 }
  }
}
```

Written to `.codemap/intermediate/validation.json` during build. Promoted to `.codemap/validation.json` only when `--validate-only` is set.

### Outcome summary line

```
Validation: <E> errors, <W> warnings, <N> nodes, <M> edges, <L>% layer coverage
```

Layer coverage = share of non-test nodes carrying `layer` (same denominator as W4).

On errors, list them grouped by check number, most affected first.

## Avoid

- Auto-repairing nodes or edges - merge fixes, validation reports.
- Silencing a warning by tightening enums - extend `codemap-schema` instead.
- Running validation before merge - dedup hasn't happened, you'll get false positives.
