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

Read-only patterns consumed by `task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`. Every consumer reads `.codemap/graph.json` and walks it; this skill standardizes how.

## When to Use

- Any consumer workflow that reads `.codemap/graph.json`.
- Do not load when producing graph data - that's `codemap-build-pipeline`.

## Rules

1. **Load once per workflow.** Read `graph.json` into memory at workflow start; do not re-read between queries.
2. **Edges are directed.** `source -> target`. Walking "incoming" requires scanning all edges for `target == nodeId`; "outgoing" for `source == nodeId`.
3. **Resolve IDs before paths.** When the user names a file or function, resolve to a node ID first; query in ID space; render results back to file paths and line ranges.
4. **Cap result sets.** Any query returning more than 50 nodes should be summarized (top-N by weight or frequency) rather than dumped.
5. **Don't fabricate.** If a query returns empty, say so explicitly. Do not invent nodes the graph does not contain.

## Patterns

### Resolve user input to node ID

User types `src/auth/login.ts`, `authenticate`, or `auth/login.ts:authenticate`:

1. Exact ID match: `function:src/auth/login.ts:authenticate`.
2. File-path match: nodes with `filePath == input`.
3. Name match (case-insensitive): nodes with `name == input`.
4. Substring match on `filePath` or `id`.

Resolution rules:
- Multiple matches -> list them with type + path, ask user to pick.
- Zero matches -> report and suggest the closest 3 by Levenshtein on `filePath` or `name`.

### Common queries

| Query | How |
| --- | --- |
| Neighbors of node X | All edges where `source == X` (outgoing) or `target == X` (incoming). |
| Outgoing imports of file F | Edges where `source == file:F` and `type == imports`. |
| Callers of function G | Edges where `target == G` and `type == calls`. Resolve sources to (file, line). |
| Callees of function G | Edges where `source == G` and `type == calls`. |
| All functions in file F | Nodes where `filePath == F` and `type == function`. |
| Endpoints in the API | Nodes where `type == endpoint`. Group by HTTP verb if available in `name`. |
| Database tables touched by handler H | BFS from H following `calls`/`uses` until hitting `reads_from`/`writes_to` edges; targets are tables. Cap depth at 4. |
| Layer of node X | Read `node.layer`. If absent, walk `belongs_to` to ancestor with a layer. |
| All nodes in layer L | Filter `nodes` by `layer == L`. |
| Fan-in for node X | Count distinct sources of edges where `target == X`. |
| Fan-out for node X | Count distinct targets of edges where `source == X`. |
| Hub nodes | Top-K by fan-in + fan-out. Used to surface god-modules and core abstractions. |
| Orphans | Nodes with fan-in 0 AND fan-out 0. |
| Shortest path from A to B | BFS on the undirected edge set, cap at depth 6. Return one path; report length. |
| Files changed in diff | Read `diff-overlay.json` if present; else `git diff --name-only`. Map to `file:<path>` IDs. |
| Impacted by change to file F | Reverse BFS from `file:F` over `imports`/`calls`/`uses`/`routes_to` edges. Cap at depth 3. |

### File scope filter

When a user asks "in the auth module", resolve scope to a path prefix and filter:

```
scope = "src/auth"
nodes_in_scope = [n for n in nodes if n.filePath and n.filePath.startswith(scope + "/")]
```

Edges in scope = both endpoints in scope. Edges crossing the scope boundary are useful for "what depends on this module" questions; surface them separately.

### Reading file content from a node

The graph stores summaries, not source. When the workflow needs actual code:

1. From `node.filePath` + `node.lineRange`, call `Read` with `offset` and `limit`.
2. Cap each read at 200 lines unless the user asks for the full file.
3. Prefer reading 2-3 targeted ranges over one large file when answering questions about specific nodes.

### Diff impact (consumed by ask/explain)

```
1. Read .codemap/diff-overlay.json if present.
2. Else compute fresh: parse `git diff --name-only HEAD` -> changed file IDs.
3. For each changed file ID, reverse-BFS depth-3 to gather "impacted" nodes.
4. Group impacted nodes by layer; surface top-fan-in nodes first.
```

## Output Format

This skill defines the query vocabulary. Consumers render results using the conventions below:

- **Node references**: backtick-wrap full ID (e.g., ``function:src/auth/login.ts:authenticate``) so users can grep.
- **File references**: `path/to/file.ext:lineStart-lineEnd` (e.g., `src/auth/login.ts:42-87`) for clickable navigation.
- **Empty results**: state explicitly - `No callers found for authenticate()` - never silently omit a section.
- **Capped results**: when truncating, state the cap - `Showing top 10 of 42 callers by fan-in.`

## Avoid

- Re-reading `graph.json` multiple times in a single workflow. Load once.
- Walking the full graph when a single hop answers the question.
- Inferring relationships not in the graph. If a function isn't connected by `calls`, do not assume it isn't called - say "not recorded in the graph" and offer to grep the source.
- Dumping raw JSON to the user. Render as tables, paths with line ranges, or summary counts.
- Treating the graph as truth without an updated-at check. If `meta.json#gitCommitHash` is stale by many commits, warn the user before answering high-stakes questions.
