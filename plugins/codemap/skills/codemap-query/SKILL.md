---
name: codemap-query
description: Traversal patterns for reading codemap graph - neighbors, fan-in/out, layer filter, path finding, callers/callees, file scope.
metadata:
  category: core
  tags: [codemap, query, traversal, read-only]
user-invocable: false
---

# Codemap Query

> Load `Use skill: codemap-schema` first for node/edge shape and ID format.

Read-only patterns for `task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`. Every consumer reads `.codemap/graph.json` and walks it; this skill standardizes how.

## When to Use

Any consumer workflow that reads `.codemap/graph.json`. Not for producers - that's `codemap-build-pipeline`.

## Rules

1. **Load once per workflow.** Read `graph.json` at workflow start; do not re-read between queries.
2. **Edges are directed.** Incoming = scan all edges for `target == nodeId`; outgoing for `source`.
3. **Resolve before traversing.** Map user-named entities to node IDs first, query in ID space, render back to file paths and line ranges.
4. **Cap large results.** Queries returning >50 nodes get summarized top-N by weight or frequency, never dumped.
5. **Don't fabricate.** Empty result -> say so. Never invent nodes the graph doesn't contain.

## Patterns

### Resolve user input to node ID

User types `src/auth/login.ts`, `authenticate`, or `auth/login.ts:authenticate`:

1. Exact ID match: `function:src/auth/login.ts:authenticate`.
2. `filePath == input`.
3. Case-insensitive `name == input`.
4. Substring on `filePath` or `id`.

Multiple matches -> list with type+path, ask user to pick. Zero matches -> suggest closest 3 by Levenshtein.

### Common queries

| Query | How |
| --- | --- |
| Neighbors of X | Edges where `source == X` (out) or `target == X` (in). |
| Outgoing imports of file F | `source == file:F`, `type == imports`. |
| Callers of function G | `target == G`, `type == calls`. Render sources as `file:line`. |
| Callees of function G | `source == G`, `type == calls`. |
| Functions in file F | `filePath == F`, `type == function`. |
| Endpoints | `type == endpoint`. Group by HTTP verb when present in `name`. |
| Tables touched by handler H | BFS from H via `calls`/`uses` until hitting `reads_from`/`writes_to`. Cap depth 4 (handler -> service -> repository -> table + 1 hop slack). |
| Layer of X | `node.layer`. If absent, walk `belongs_to` up to a layered ancestor. |
| Nodes in layer L | Filter `nodes` by `layer == L`. |
| Fan-in / fan-out for X | Count distinct edge sources/targets. |
| Hub nodes | Top-K by fan-in + fan-out. |
| Orphans | Fan-in 0 AND fan-out 0. |
| Shortest path A -> B | BFS on undirected edge set, cap depth 6. One path, report length. |
| Files in current diff | `git diff --name-only` (and `git diff --name-only <base>...HEAD` for branch diffs). Map to `file:<path>` IDs. |
| Impact of change to F | Reverse BFS from `file:F` over `imports`/`calls`/`uses`/`routes_to`. Cap depth 3. Group by layer. |

### File-scope filter

When the user says "in the auth module", resolve to a path prefix and filter:

```
scope = "src/auth"
nodes_in_scope = [n for n in nodes if n.filePath and n.filePath.startswith(scope + "/")]
```

Edges in-scope = both endpoints in-scope. Cross-boundary edges answer "what depends on this module" - surface them separately.

### Freshness check (shared by all consumers)

Run once per workflow before answering. Compare `.codemap/meta.json` against the working tree:

| Signal | Action |
| --- | --- |
| `meta.json` missing | Stop; tell the user to run `/task-codemap`. |
| `meta.json#gitCommitHash != git rev-parse HEAD` and HEAD is >10 commits ahead | Warn `stale`; proceed; append stale footer. |
| `meta.json#builtAt` older than 7 days | Warn `stale`; proceed; append stale footer. |
| Otherwise | `in-sync`; proceed without warning. |

Footer format:

```
> Codemap built from commit <hash> (<N> commits behind HEAD, <D> days old). Run `/task-codemap` to sync.
```

Workflows reference this rule instead of re-defining it.

### Large-graph access (>5MB `graph.json`)

When `graph.json` exceeds ~5 MB, skip the full-file Read; use targeted reads.

- Find one node: `Grep "\"id\": \"<id>\"" .codemap/graph.json -A 5`.
- One-off aggregations: `Bash python -c "import json; g=json.load(open('.codemap/graph.json')); ..."`.
- Slice by type/layer: `Grep "\"type\": \"<type>\"" .codemap/graph.json` then resolve hits.

Rule 1 ("Load once per workflow") relaxes here: prefer multiple narrow reads to one full-file load that blows the context.

### Reading source from a node

Graph stores summaries, not source. When source detail is needed:

1. `Read` with `offset`/`limit` from `node.lineRange`.
2. Cap each read at 200 lines unless the user asks for the full file.
3. Prefer 2-3 targeted ranges over one large read.

## Output Format

- **Node references:** backtick-wrap full ID (e.g., ``function:src/auth/login.ts:authenticate``).
- **File references:** `path:lineStart-lineEnd` for clickable navigation.
- **Empty results:** state explicitly (`No callers found for authenticate()`). Never silently omit a section.
- **Truncated results:** name the cap (`Showing top 10 of 42 callers by fan-in`).

## Avoid

- Re-reading `graph.json` between queries.
- Walking the full graph when a single hop answers the question.
- Inferring relationships not in the graph. If `calls` is silent, say "not recorded - grep the source" rather than guess.
- Dumping raw JSON to the user. Render as tables or summary counts.
- Treating the graph as truth without checking `meta.json#gitCommitHash` for high-stakes questions.
