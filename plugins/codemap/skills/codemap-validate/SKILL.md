---
name: codemap-validate
description: Validate codemap graph - referential integrity, schema conformance, dangling edges, ID uniqueness, layer coverage, guide resolvability.
metadata:
  category: core
  tags: [codemap, validation, integrity, quality]
user-invocable: false
---

# Codemap Validate

> Load `Use skill: codemap-schema` for the canonical shape.

Last step of every build or refresh. Confirms the produced `graph.json` (and `guides.json` when present) meets the schema contract.

## When to Use

- Final phase of `codemap-build-pipeline` after merge + layer assignment + guide generation.
- Final phase of `task-codemap` sync mode after the splice step.
- On demand against an existing graph (`task-codemap --validate-only` or read-only).

## Rules

1. **Validation is blocking.** Errors prevent persistence to `graph.json`. Warnings are logged but do not block.
2. **One pass, exhaustive.** Run all checks every time. Do not short-circuit on first failure - users want the full report.
3. **No fixing.** Validation reports issues; producers fix them. Auto-repair belongs in the merge step, not here.

## Patterns

### Checks (errors block persistence)

| # | Check | Failure example |
| --- | --- | --- |
| 1 | Top-level `schemaVersion` matches current | `schemaVersion: 0` against current `1` |
| 2 | `nodes` and `edges` are arrays | `nodes: null` |
| 3 | Every node has required fields (`id`, `type`, `name`, `summary`, `tags`) | Node missing `summary` |
| 4 | Every node `type` is in the enum (12 values) | `type: "method"` (should be `function`) |
| 5 | Node IDs are globally unique | Two nodes with `id: file:src/auth/login.ts` |
| 6 | Node ID format matches `<type>:<path>[:<name>]` | `id: login` |
| 7 | Code-node IDs reference an existing file node | `function:src/foo.ts:bar` exists but `file:src/foo.ts` does not |
| 8 | Every edge `type` is in the enum (14 values) | `type: "invokes"` |
| 9 | Every edge `source` and `target` reference an existing node ID | Edge to `function:src/gone.ts:dead` not in `nodes` |
| 10 | `lineRange` is `[start, end]` with `start <= end` and `start >= 1` for nodes that require it | `lineRange: [42, 10]` |
| 11 | `tags` is a 1-5 element string array | `tags: "auth"` (string, not array) |
| 12 | `complexity`, when present, is in `{simple, moderate, complex}` | `complexity: "high"` |
| 13 | `layer`, when present, is in the 6-layer enum | `layer: "controller"` (should be `api`) |
| 14 | When `guides.json` is present, every `nodeId` in every step exists in `graph.json#nodes` | Guide step references stale node ID |

### Checks (warnings, non-blocking)

| # | Check | Warning example |
| --- | --- | --- |
| W1 | Orphan nodes - 0 incoming and 0 outgoing edges | Standalone util file with no callers and no imports declared |
| W2 | Self-edges - `source == target` | `calls` from a function to itself with no recursion intent flagged |
| W3 | Duplicate edges - identical `(source, target, type)` | Same `imports` edge emitted twice |
| W4 | Layer coverage - more than 25% of nodes have no `layer` assigned | Suggests layout doesn't match patterns table |
| W5 | Empty layers - a layer with 0 nodes (excluding `domain` for frontend-only projects) | `data` empty in a fullstack project |
| W6 | Hub nodes - any node with > 50 outgoing edges | Likely a god-module |
| W7 | Documentation gap - 0 `document` nodes when `README.md` exists at root | Docs not analyzed |
| W8 | Test coverage gap - 0 `tested_by` edges when test directories detected by stack-detect | Tests not linked to code |

### Output shape

```json
{
  "schemaVersion": 1,
  "validatedAt": "2026-05-30T12:00:00Z",
  "errors": [
    {
      "check": 5,
      "message": "Duplicate node ID",
      "details": "id: file:src/auth/login.ts appears 2 times"
    }
  ],
  "warnings": [
    {
      "check": "W4",
      "message": "Layer coverage below threshold",
      "details": "32% of nodes have no layer assigned (132 of 412)"
    }
  ],
  "stats": {
    "nodes": 412,
    "edges": 1184,
    "nodesByType": { "file": 198, "function": 156, "class": 42, "...": 16 },
    "edgesByType": { "imports": 612, "calls": 388, "...": 184 },
    "nodesByLayer": { "entry": 8, "api": 64, "service": 88, "domain": 42, "data": 70, "infra": 18, "unassigned": 122 }
  }
}
```

Written to `.codemap/intermediate/validation.json` during build; the final `validation.json` (without `intermediate/`) is kept at `.codemap/` root only when explicitly requested via `task-codemap --validate-only`.

### Failure handling

- **Errors present**: do not write `graph.json`. Print the error list with file/node IDs. Surface the build failure.
- **Errors empty, warnings present**: write the artifact, print the warning summary, do not block.
- **All clean**: write the artifact, print stats only.

## Output Format

This skill produces the validation report shape above. Build pipelines must echo a one-line summary to the user:

```
Validation: <E> errors, <W> warnings, <N> nodes, <M> edges, <L>% layer coverage
```

When errors block persistence, list them grouped by check number, most affected first.

## Avoid

- Auto-repairing nodes or edges. Validation reports; merge fixes.
- Silencing warnings by tightening enums. If the schema gains a value, update `codemap-schema`, not this skill.
- Failing on warnings. They are signals, not errors.
- Running validation before merge. The merge step deduplicates edges and drops dangling ones; running validation before merge produces noise.
