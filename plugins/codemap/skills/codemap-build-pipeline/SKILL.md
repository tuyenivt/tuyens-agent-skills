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
> Load `Use skill: stack-detect` first to inform layer assignment and framework-aware analysis.

End-to-end build flow consumed by `task-codemap` - the full-build path runs all 9 phases; sync mode runs only phase 3 (analyze) on changed files and reuses the merge/repair/validate logic against the spliced graph. Pure-LLM extraction; the only scripts are skill-local Python helpers for deterministic file enumeration, batching, merging, and fingerprinting.

## When to Use

- Composed into `task-codemap` when no `.codemap/graph.json` exists or `--full` is passed.
- Composed into `task-codemap` sync mode for the incremental path (analyze + merge + splice + validate, fed a change-set instead of a fresh scan).

## Rules

1. **Pure-LLM extraction.** No tree-sitter, no Node, no language-specific parsers. Python helpers do file enumeration and hashing only; semantic extraction is the LLM via Read/Grep.
2. **Sub-agents do batch analysis in parallel.** Up to 5 concurrent sub-agents via the `Agent` tool. Each is fed a batch manifest and returns a JSON node/edge list.
3. **Determinism where possible.** Scan, batch, merge, fingerprint, validate are all deterministic Python. Variance is isolated to the analysis phase.
4. **No persistence until validate passes.** Errors block. Warnings do not.
5. **Cap batches at 25 files or 800 KB total.** Larger batches degrade extraction quality.

## Patterns

### Phase 1 - Scan

Run `scan.py` (skill-local in `task-codemap/`):

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/scan.py" --root <path> --output .codemap/intermediate/scan.json
```

`scan.py` enumerates files (prefers `git ls-files`, falls back to `os.walk`), applies `.codemapignore` (auto-generated from `.gitignore` plus user additions), classifies language by extension, counts lines, and writes:

```json
{
  "rootPath": ".",
  "gitCommitHash": "abc1234",
  "files": [
    { "path": "src/auth/login.ts", "language": "TypeScript", "lines": 142, "bytes": 4821, "category": "code" },
    { "path": "README.md", "language": "Markdown", "lines": 80, "bytes": 2104, "category": "document" }
  ],
  "totalFiles": 412,
  "skipped": 18
}
```

`category` is one of `code`, `config`, `document`, `data`, `generated`, `test`.

### Phase 2 - Batch

Run `batch.py`:

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/batch.py" --scan .codemap/intermediate/scan.json --output .codemap/intermediate/batches.json
```

`batch.py` groups files into ~25-file batches, prioritizing same-directory cohesion (a batch should be analyzable as a coherent unit). Output:

```json
{
  "batches": [
    {
      "index": 0,
      "files": ["src/auth/login.ts", "src/auth/jwt.ts", "src/auth/middleware.ts", "..."],
      "totalBytes": 38421,
      "primaryLanguage": "TypeScript"
    }
  ],
  "totalBatches": 18
}
```

### Phase 3 - Parallel analysis (sub-agents)

For each batch, dispatch a sub-agent via the `Agent` tool. Up to **5 concurrent** at a time. Each sub-agent:

1. Receives the batch manifest (file list, languages) plus the schema rules from `codemap-schema`.
2. Reads each file in the batch via the `Read` tool.
3. Extracts nodes (one `file` node per file; one `function`/`class`/`endpoint`/`config` node per top-level definition).
4. Extracts edges (`imports`, `calls`, `extends`, `implements`, `routes_to`, `belongs_to`, `tested_by` when test file naming makes it obvious).
5. Writes `.codemap/intermediate/batch-<index>.json` with `{ nodes, edges }`.

**Sub-agent prompt skeleton** (the workflow constructs this; included here for the contract):

```
You are a codemap batch analyzer. Read each file listed below and produce a JSON object
{ nodes, edges } following the codemap-schema rules exactly.

Strict rules:
- Every code file becomes one `file` node. Every top-level function, class, exported endpoint becomes its own node with belongs_to edge back to the file.
- imports edges: emit one per import statement, target = file:<resolved path> when resolvable, otherwise omit.
- calls edges: only when the call is in the file's source and the callee is also a node you are emitting in this batch OR in a file path that exists in the project.
- summary: one English sentence per node, describing intent, not signature.
- tags: 2-5 short kebab-case tags.
- complexity: simple if <30 lines, moderate if 30-150, complex if >150 or deeply nested.
- No file fields beyond the codemap-schema contract.

Write output to: .codemap/intermediate/batch-<INDEX>.json
Return: a one-line confirmation with node/edge counts.

Batch manifest:
<files list>
```

**Concurrency**: dispatch all batches in waves of 5 (5 in flight, wait, next 5). Each `Agent` call is a separate tool invocation in the same workflow turn.

### Phase 4 - Merge

Run `merge.py`:

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/merge.py" --batches-dir .codemap/intermediate --output .codemap/intermediate/merged.json
```

`merge.py`:
1. Reads every `batch-*.json`.
2. Concatenates nodes; on duplicate IDs, keeps the first occurrence and logs the dup.
3. Concatenates edges; dedupes by `(source, target, type)`.
4. Drops edges where either endpoint is not in the merged node set (dangling).
5. Reports counts: `{ nodes, edges, droppedDanglingEdges, duplicateNodeIds }`.

Output is `merged.json` matching `codemap-schema` top-level shape minus `layers`.

### Phase 5 - Cross-batch repair (LLM, single pass)

After merge, the LLM does one cleanup pass:

1. Read `merged.json` plus `intermediate/scan.json`.
2. For each `imports` edge that resolved during analysis but whose target was in a different batch, confirm the target file node exists. If not, drop (already done by merge).
3. For each file with no `belongs_to` edges from its functions/classes (extraction missed them), flag in `intermediate/repair-log.json` for visibility but do not invent.
4. Recompute `complexity` for any node lacking it from `scan.json` line counts.

No new nodes or edges should be invented here. This step is a sanity net, not a generator.

### Phase 6 - Layer assignment

LLM step. Read `merged.json` + `stack-detect` output + `codemap-layer-patterns` table:

1. For each node with a `filePath`, walk the path's directory segments deepest-first.
2. First match in the patterns table -> assign `layer`.
3. For nodes inheriting from a file (via `belongs_to`), assign the same layer as the file.
4. For `concept`, `service`, `schema`, `resource`, `endpoint` nodes - assign by heuristic in the schema rules (endpoints -> `api`, etc.).
5. Write the layered graph in-place.
6. Compute `layers` summary array:

```json
"layers": [
  { "id": "layer:entry", "name": "Entry", "nodeIds": ["file:cmd/main.go"] },
  { "id": "layer:api", "name": "API", "nodeIds": ["file:internal/handler/auth.go", "..."] }
]
```

Surface a warning if more than 25% of nodes are unassigned (per `codemap-layer-patterns` threshold).

### Phase 7 - Guide generation

LLM step. Generate 3-5 dependency-ordered walkthroughs into `.codemap/guides.json`. Guide selection heuristic:

| Guide candidate | When to include |
| --- | --- |
| `request-lifecycle` | When `endpoint` nodes exist - traces one common request end-to-end |
| `auth-flow` | When auth-tagged nodes cluster (tags include `auth`, `jwt`, `session`) |
| `data-layer` | When `data`-layer nodes exist - walks repository/ORM patterns |
| `entrypoints` | Always - walks all `entry` nodes for orientation |
| `domain-model` | When `domain`-layer nodes exist - walks core entities and invariants |

Each guide has 5-8 steps for `basic` depth, 10-20 for `full`. Each step is `{ order, nodeId, narration }`. `narration` is one sentence in English explaining why this node is the next stop.

### Phase 8 - Validate

Load `codemap-validate`. Apply all 14 error checks + 8 warning checks against `merged.json` + `guides.json`.

- Errors -> abort, do not persist. Print error list.
- Warnings -> proceed, print warning summary.

### Phase 9 - Persist

1. Write `merged.json` -> `.codemap/graph.json`.
2. Write `.codemap/guides.json`.
3. Write `.codemap/meta.json` with `gitCommitHash`, `builtAt`, `analyzedFiles`, `version`.
4. Run `python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compute --scan .codemap/intermediate/scan.json --output .codemap/fingerprints.json` -> writes `.codemap/fingerprints.json`.
5. Delete `.codemap/intermediate/`.

## Output Format

This skill produces no artifact directly; it standardizes the phases the workflow runs. The workflow logs one line per phase to keep the user informed:

```
Phase 1/9 - scan: 412 files (18 skipped) in 2s
Phase 2/9 - batch: 18 batches
Phase 3/9 - analyze: 18 batches in parallel (5 concurrent waves)
Phase 4/9 - merge: 412 nodes, 1184 edges (12 dangling dropped)
Phase 5/9 - cross-batch repair: ok
Phase 6/9 - layers: 88% assigned
Phase 7/9 - guides: 4 generated
Phase 8/9 - validate: 0 errors, 2 warnings
Phase 9/9 - persist: graph.json, guides.json, meta.json, fingerprints.json
```

## Avoid

- Re-implementing scan/batch/merge in the LLM. Always shell out to the Python helpers - they are deterministic, fast, and zero-dep.
- Running batches sequentially. Always parallel via sub-agents.
- Letting sub-agents invent imports between files that do not exist on disk. The sub-agent prompt forbids this.
- Persisting before validation. Validation is the gate, not a courtesy.
- Regenerating guides on incremental refresh. Guides regenerate only on full builds or explicit request.
- Writing the analysis prompt freehand. Use the contract above; small wording changes degrade extraction consistency.
