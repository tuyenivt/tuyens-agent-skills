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

End-to-end build flow for `task-codemap`. Full path runs all 9 phases; sync mode runs phase 3 (analyze) on changed files, then reuses merge, repair, layer assignment (new nodes only), and validate on the spliced graph - the sync sequence and splice semantics are owned by `codemap-fingerprints`.

**Phase ownership:**

- Python helpers (deterministic): phases 1 (scan), 2 (batch), 4 (merge), 9 (persist + fingerprint).
- LLM (semantic): phases 3 (sub-agent analyze), 5 (repair-LLM pass), 6 (layer assign), 7 (guide generate).
- Composed atomic: phase 8 (`codemap-validate`).
- Mixed: phase 5 also includes a mechanical complexity backfill.

## When to Use

Composed into `task-codemap` for both modes (full build and sync). Pure-LLM extraction - Python helpers only enumerate, batch, merge, and fingerprint.

## Rules

1. **Pure-LLM extraction.** No tree-sitter, no Node, no language parsers. Python does deterministic work; LLM does semantics.
2. **Sub-agent parallelism.** At most 5 `Agent` calls run concurrently; dispatch batches in waves of 5 until all are done. Each gets a batch manifest, returns `{ nodes, edges }`.
3. **Persistence is gated by validate.** Errors block; warnings don't.
4. **Batches cap at 25 files or 800 KB total.** Larger degrades extraction quality.
5. **Abort thresholds.** Scan finding 0 files -> stop with a friendly message, write nothing. More than half the batches landing in `*-error.json` after retries -> abort without persisting; the partial graph is worse than the prior one.

## Patterns

### Phase 1 - Scan

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/scan.py" --root <path> [--scope <dir>] --output .codemap/intermediate/scan.json
```

Pass `--scope` when the caller passed it (or when `.codemap/config.json#scope` is set - the CLI flag wins). Prefers `git ls-files`, falls back to `os.walk`. Applies `.codemapignore` patterns and (in `os.walk` fallback) `.gitignore` patterns. Default ignore set drops `.git`, `node_modules`, etc. Files larger than `--max-file-bytes` (default 500 KB) are skipped and listed under `oversize`. Classifies language by extension. Output:

```json
{
  "rootPath": ".",
  "gitCommitHash": "abc1234",
  "files": [
    { "path": "src/auth/login.ts", "language": "TypeScript", "lines": 142, "bytes": 4821, "category": "code" }
  ],
  "oversize": ["assets/bundle.min.js"],
  "totalFiles": 412,
  "skipped": 18
}
```

`category`: `code` / `config` / `document` / `generated` / `test`.

### Phase 2 - Batch

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/batch.py" --scan .codemap/intermediate/scan.json --output .codemap/intermediate/batches.json
```

Groups files into ~25-file batches, prioritizing same-directory cohesion. Oversized files are already excluded upstream (Phase 1, `scan.json#oversize`); the build report surfaces the count under skipped stats. Output:

```json
{
  "batches": [
    { "index": 0, "files": ["src/auth/login.ts", "src/auth/jwt.ts"], "totalBytes": 38421, "primaryLanguage": "TypeScript" }
  ],
  "totalBatches": 18
}
```

### Phase 3 - Parallel analysis

Dispatch one `Agent` per batch, **at most 5 concurrent** (waves of 5 until done, per Rule 2). Each sub-agent receives the manifest + schema rules, reads each file, emits `{ nodes, edges }` to `.codemap/intermediate/batch-<index>.json`.

Interpolate `{{stack}}` from the cached `stack-detect` output (e.g., `"Go 1.25 / Gin"`) and append the matching stack block from `codemap-layer-patterns` "Stack-specific exceptions" as recognition hints (where the stack keeps routes, entrypoints, and data access). The skeleton is calibrated - extend, do not freehand-rewrite.

**Sub-agent prompt skeleton:**

```
You are a codemap batch analyzer. Read each file in the manifest and produce a JSON object
{ nodes, edges } that conforms to codemap-schema (12 node types, 14 edge types).

Project stack: {{stack}}.
Apply the stack's idioms when recognising endpoints, ORM calls, DI wiring, and test pairing.

Node extraction (cover the full enum where applicable):
- `file` - one per code/config/document file in the batch.
- `function`, `class` - every top-level definition (functions, methods, classes, structs, interfaces, traits).
- `module` - a `module` node for the folder/package when the batch shares one (id = `module:<dir>`); files belong_to module.
- `endpoint` - HTTP routes, gRPC methods, GraphQL resolvers, CLI commands. Pair with `routes_to` edge to the handler function.
- `config` - YAML/TOML/JSON/.env config files. Distinguish from generic data JSON.
- `document` - Markdown and similar prose.
- `table` - DB tables/collections referenced via ORM models, migrations, or raw SQL targets.
- `schema` - DTOs, OpenAPI/JSON-Schema docs, protobuf messages, Pydantic/Zod schemas.
- `service` - external SDKs/clients imported (e.g., `stripe`, `redis`, `sendgrid`) or internal deployed services referenced by config.
- `resource` - queues, topics, buckets, cron schedules referenced in code or config.
- `concept` - optional; only when an unambiguous named concept appears across files (e.g., `JWT`, `Idempotency Key`).

Edge extraction (cover the full enum where applicable):
- `belongs_to` - function/class -> file; file -> module.
- `imports` - one per import statement; target = `file:<resolved path>` when resolvable in the batch or known project files, else omit.
- `exports` - source declares target as its public surface (re-exports, package index files).
- `calls` - function-to-function; emit when callee is in this batch OR a known project file.
- `extends` / `implements` - class inheritance and interface implementation.
- `uses` - generic dependency (DI injection, instantiation, type reference) not covered by calls/imports.
- `depends_on` - module-to-module or service-to-service dependency.
- `reads_from` / `writes_to` - function/class to `table`/`schema`/`config`/`resource` (ORM calls, raw SQL, repo methods, queue publish/consume).
- `tested_by` - production file -> its test file. Heuristic: `foo_test.go` -> `foo.go`; `Foo.test.ts` / `Foo.spec.ts` -> `Foo.ts`; `tests/test_foo.py` -> `foo.py`. Emit only when the partner exists in this batch or the project.
- `documents` - `document` node -> the subject it describes (file/module).
- `configures` - `config` node -> the target it configures (file/module/service).
- `routes_to` - `endpoint` -> handler `function`.

Per-node rules:
- summary: one English sentence, intent not signature.
- tags: 1-5 short kebab-case.
- complexity: simple if <30 lines, moderate if 30-150, complex if >150 or deeply nested.
- No fields beyond the schema.
- Never invent imports/calls/tables to files or symbols that don't exist on disk.

Write output to: .codemap/intermediate/batch-<INDEX>.json.
On unrecoverable error (cannot read a file, malformed manifest), instead write
`.codemap/intermediate/batch-<INDEX>-error.json` with `{ "error": "<short reason>", "index": <INDEX> }`.

Return: one-line confirmation with node/edge counts.

Batch manifest: <files list>
```

### Phase 3 retry policy

Budget: **3 attempts max per batch** (1 initial + 2 retries). Check expected outputs as each wave completes; re-dispatch failures as part of the next wave (the 5-concurrent cap counts retries). For each expected `batch-<INDEX>.json`:

1. Missing, empty, or unparseable JSON -> re-dispatch the same prompt.
2. Still missing/empty/unparseable after attempt 3 -> write `batch-<INDEX>-error.json` with `{ "error": "<reason>", "index": <INDEX>, "files": [...] }` and continue (subject to the Rule 5 abort threshold).

Surface the dropped batch count in the Phase 3 log line and in the build report's Pipeline table.

### Phase 4 - Merge

```
python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/merge.py" --batches-dir .codemap/intermediate --output .codemap/intermediate/merged.json
```

Concatenates nodes in ascending batch-index order (dup IDs: lowest batch index wins, dup logged - deterministic regardless of sub-agent completion order), dedupes edges by `(source, target, type)`, drops edges with missing endpoints. Tolerant: malformed batch files are skipped with a warning rather than aborting the merge. Reports `{ nodes, edges, droppedDanglingEdges, duplicateNodeIds, malformedBatches, errorBatches }`. When any non-zero, writes `intermediate/merge-log.json` enumerating the affected files.

### Phase 5 - Cross-batch repair

Sanity net, not a generator. Two passes:

**LLM (single pass)** - read `merged.json` + `scan.json`:

1. Confirm cross-batch `imports` resolve; drop unresolved (merge already did this).
2. Flag files whose functions/classes have no `belongs_to` edges (extraction miss) into `intermediate/repair-log.json`. Do not invent.

**Mechanical (Python or inline)** - no judgment required:

3. Backfill missing `complexity` from `scan.json` line counts using the same thresholds as the sub-agent prompt (`<30` simple, `30-150` moderate, `>150` complex).

### Phase 6 - Layer assignment

LLM. Read `merged.json` + `stack-detect` + `codemap-layer-patterns`:

1. For each node with `filePath`, apply the `codemap-layer-patterns` precedence rules (stack-specific exceptions first, then deepest matching directory segment).
2. Members inherit their file's layer via `belongs_to`.
3. Abstract type defaults: `endpoint` -> `api`; `table`/`schema` -> `data`; `service`/`resource` -> `infra`; `config` -> `infra` (unless the file path matches an entry mapping in `codemap-layer-patterns`); `concept`/`document` -> omit `layer`.
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
| `entrypoints` | Always when `entry`-layer nodes exist |
| `domain-model` | `domain`-layer nodes exist |

`basic` = 5-8 steps, `full` = 10-20. Each step: `{ order, nodeId, narration }`. Narration is one sentence explaining why this stop.

### Phase 8 - Validate

Load `codemap-validate`. All 15 errors + 9 warnings against `merged.json` + `guides.json`. Errors abort; warnings proceed.

### Phase 9 - Persist

1. `merged.json` -> `.codemap/graph.json`.
2. Write `.codemap/guides.json`, `.codemap/meta.json`.
3. `python "${CLAUDE_PLUGIN_ROOT}/skills/task-codemap/fingerprint.py" --mode compute --scan .codemap/intermediate/scan.json --output .codemap/fingerprints.json`.
4. Delete `.codemap/intermediate/` **only after** steps 1-3 all succeed - it is the sole recovery source if persist fails midway. On a midway failure, re-run Phase 9 from `intermediate/`; do not restart the pipeline.

## Output Format

The workflow logs one line per phase:

```
Phase 1/9 - scan: 412 files (18 skipped) in 2s
Phase 2/9 - batch: 18 batches
Phase 3/9 - analyze: 18 batches, 5-way parallel (0 dropped after retries)
Phase 4/9 - merge: 412 nodes, 1184 edges (12 dangling dropped, 0 malformed); merge-log.json written when duplicates/malformed/errors present
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
