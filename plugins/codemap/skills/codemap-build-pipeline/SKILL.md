---
name: codemap-build-pipeline
description: Codemap build phases - scan, batch, analyze in parallel sub-agents, merge, assign layers, generate guides, validate. Pure-LLM, no tree-sitter.
metadata:
  category: core
  tags: [codemap, pipeline, build, sub-agents]
user-invocable: false
---

# Codemap Build Pipeline

> Load `Use skill: codemap-schema` for graph shape.
> Load `Use skill: codemap-layer-patterns` for layer assignment.
> Load `Use skill: codemap-validate` for the final integrity gate.
> Load `Use skill: stack-detect` first - informs analysis prompts, layers, and guide selection.

End-to-end build flow for `task-codemap`. Full path runs all 9 phases; sync mode runs phase 3 (analyze) on changed files and reuses merge/repair/validate on the spliced graph.

## When to Use

Composed into `task-codemap` for both modes (full build and sync). Pure-LLM extraction - Python helpers only enumerate, batch, merge, and fingerprint.

## Rules

1. **Pure-LLM extraction.** No tree-sitter, no Node, no language parsers. Python does deterministic work; LLM does semantics.
2. **Sub-agent parallelism.** Up to 5 concurrent via `Agent`. Each gets a batch manifest, returns `{ nodes, edges }`.
3. **Persistence is gated by validate.** Errors block; warnings don't.
4. **Batches cap at 25 files or 800 KB total.** Larger degrades extraction quality.

## Patterns

### Phase 1 - Scan

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/scan.py" --root <path> --output .codemap/intermediate/scan.json
```

Prefers `git ls-files`, falls back to `os.walk`. Applies `.codemapignore` (auto-seeded from `.gitignore`). Classifies language by extension. Output:

```json
{
  "rootPath": ".",
  "gitCommitHash": "abc1234",
  "files": [
    { "path": "src/auth/login.ts", "language": "TypeScript", "lines": 142, "bytes": 4821, "category": "code" }
  ],
  "totalFiles": 412,
  "skipped": 18
}
```

`category`: `code` / `config` / `document` / `data` / `generated` / `test`.

### Phase 2 - Batch

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/batch.py" --scan .codemap/intermediate/scan.json --output .codemap/intermediate/batches.json
```

Groups files into ~25-file batches, prioritizing same-directory cohesion. Output:

```json
{
  "batches": [
    { "index": 0, "files": ["src/auth/login.ts", "src/auth/jwt.ts"], "totalBytes": 38421, "primaryLanguage": "TypeScript" }
  ],
  "totalBatches": 18
}
```

### Phase 3 - Parallel analysis

Dispatch one `Agent` per batch, **5 concurrent waves**. Each sub-agent receives the manifest + schema rules, reads each file, emits `{ nodes, edges }` to `.codemap/intermediate/batch-<index>.json`.

**Sub-agent prompt skeleton** (use exactly; small wording changes degrade extraction consistency):

```
You are a codemap batch analyzer. Read each file in the manifest and produce a JSON object
{ nodes, edges } that conforms to codemap-schema.

Rules:
- Every code file -> one `file` node. Every top-level function, class, exported endpoint -> its own node, plus a `belongs_to` edge to the file.
- imports edges: one per import statement; target = file:<resolved path> when resolvable, else omit.
- calls edges: only when the callee is also in this batch OR exists as a file in the project.
- summary: one English sentence per node, intent not signature.
- tags: 2-5 short kebab-case.
- complexity: simple if <30 lines, moderate if 30-150, complex if >150 or deeply nested.
- No fields beyond the schema.

Write output to: .codemap/intermediate/batch-<INDEX>.json
Return: one-line confirmation with node/edge counts.

Batch manifest: <files list>
```

### Phase 4 - Merge

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/merge.py" --batches-dir .codemap/intermediate --output .codemap/intermediate/merged.json
```

Concatenates nodes (dup IDs: first wins, dup logged), dedupes edges by `(source, target, type)`, drops edges with missing endpoints. Reports `{ nodes, edges, droppedDanglingEdges, duplicateNodeIds }`.

### Phase 5 - Cross-batch repair (LLM, single pass)

Sanity net, not a generator. Read `merged.json` + `scan.json`:

1. Confirm cross-batch `imports` resolve; drop unresolved (merge already did this).
2. Flag files whose functions/classes have no `belongs_to` edges (extraction miss) into `intermediate/repair-log.json`. Do not invent.
3. Backfill missing `complexity` from `scan.json` line counts.

### Phase 6 - Layer assignment

LLM. Read `merged.json` + `stack-detect` + `codemap-layer-patterns`:

1. For each node with `filePath`, walk segments deepest-first; first match -> `layer`.
2. Members inherit their file's layer via `belongs_to`.
3. `endpoint` -> `api`; other abstract types via the schema's heuristics.
4. Emit `layers` summary:

```json
"layers": [
  { "id": "layer:entry", "name": "Entry", "nodeIds": ["file:cmd/main.go"] }
]
```

Warn if >25% unassigned.

### Phase 7 - Guide generation

LLM. Generate 3-5 dependency-ordered walkthroughs into `.codemap/guides.json`. Selection heuristic:

| Candidate | When |
| --- | --- |
| `request-lifecycle` | `endpoint` nodes exist |
| `auth-flow` | Auth-tagged cluster (`auth`, `jwt`, `session`) |
| `data-layer` | `data`-layer nodes exist |
| `entrypoints` | Always - all `entry` nodes |
| `domain-model` | `domain`-layer nodes exist |

`basic` = 5-8 steps, `full` = 10-20. Each step: `{ order, nodeId, narration }`. Narration is one sentence explaining why this stop.

### Phase 8 - Validate

Load `codemap-validate`. All 14 errors + 8 warnings against `merged.json` + `guides.json`. Errors abort; warnings proceed.

### Phase 9 - Persist

1. `merged.json` -> `.codemap/graph.json`.
2. Write `.codemap/guides.json`, `.codemap/meta.json`.
3. `python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compute --scan .codemap/intermediate/scan.json --output .codemap/fingerprints.json`.
4. Delete `.codemap/intermediate/`.

## Output Format

The workflow logs one line per phase:

```
Phase 1/9 - scan: 412 files (18 skipped) in 2s
Phase 2/9 - batch: 18 batches
Phase 3/9 - analyze: 18 batches, 5-way parallel
Phase 4/9 - merge: 412 nodes, 1184 edges (12 dangling dropped)
Phase 5/9 - repair: ok
Phase 6/9 - layers: 88% assigned
Phase 7/9 - guides: 4 generated
Phase 8/9 - validate: 0 errors, 2 warnings
Phase 9/9 - persist: graph.json, guides.json, meta.json, fingerprints.json
```

## Avoid

- Re-implementing scan/batch/merge in the LLM. Shell out to the Python helpers.
- Sequential batches - always parallel via sub-agents.
- Sub-agents inventing imports to files that don't exist on disk.
- Persisting before validate passes.
- Rewriting the sub-agent prompt freehand - the contract above is calibrated.
- Regenerating guides on incremental refresh.
