---
name: codemap-fingerprints
description: Per-file structural fingerprint contract for incremental codemap refresh - hash inputs, comparison rules, change-set output shape.
metadata:
  category: core
  tags: [codemap, incremental, fingerprints, change-detection]
user-invocable: false
---

# Codemap Fingerprints

> Load `Use skill: codemap-schema` for graph shape and ID format.

Per-file structural fingerprint used by `task-codemap` sync mode to detect which files need re-analysis. The fingerprint is computed by `fingerprint.py` (skill-local script in `task-codemap/`) and stored in `.codemap/fingerprints.json`.

## When to Use

- After a successful full build, write `fingerprints.json` alongside `graph.json`.
- Before an incremental refresh, recompute fingerprints for the working tree, diff against the stored set, and pass only changed files to the analysis phase.

## Rules

1. **Fingerprint hashes content + path, nothing else.** No timestamps, no inode, no git metadata. Deterministic across machines.
2. **Per-file, not per-node.** Granularity is the file. Sub-file change detection is out of scope.
3. **Whitespace-insensitive hashing.** Trim trailing whitespace per line and collapse blank-line runs before hashing. A reformat that does not change semantics should not trigger re-analysis.
4. **Renames detected by content hash.** If `fingerprints.json` contains the same hash under a different path, classify as rename, not delete+add. The refresh workflow updates `filePath` on existing nodes rather than rebuilding them.
5. **Schema version gate.** If `fingerprints.json#schemaVersion` does not match the current version, treat all files as changed (forces a full rebuild).

## Patterns

### Fingerprint shape (`.codemap/fingerprints.json`)

```json
{
  "schemaVersion": 1,
  "computedAt": "2026-05-30T12:00:00Z",
  "files": {
    "src/auth/login.ts": {
      "contentHash": "sha256:abc123...",
      "byteSize": 4821,
      "lineCount": 142,
      "language": "TypeScript"
    },
    "src/auth/login_test.ts": {
      "contentHash": "sha256:def456...",
      "byteSize": 2104,
      "lineCount": 63,
      "language": "TypeScript"
    }
  }
}
```

### Hash input (deterministic)

The script normalizes file content before hashing:

1. Read file as UTF-8 (replace invalid bytes with `�`).
2. Split on `\n`.
3. Trim trailing whitespace from each line.
4. Collapse runs of 2+ blank lines into a single blank line.
5. Join with `\n`, no trailing newline.
6. `sha256` over the resulting bytes, hex-encoded, prefixed with `sha256:`.

This is the same operation in every implementation; do not deviate.

### Change-set output (passed to analysis phase)

After comparing current fingerprints to stored fingerprints:

```json
{
  "added": ["src/auth/refresh_token.ts"],
  "modified": ["src/auth/login.ts"],
  "renamed": [
    { "from": "src/auth/old_login.ts", "to": "src/auth/login_v2.ts" }
  ],
  "deleted": ["src/auth/legacy_session.ts"],
  "unchanged": 408
}
```

`unchanged` is a count, not a list - the list is implied by `fingerprints.json` minus the other three categories.

### Refresh decision tree

| Change-set signal | Action |
| --- | --- |
| `unchanged == total` and HEAD commit matches `meta.json` | No-op; nothing to do. |
| Only `meta.json#gitCommitHash` is stale, no file content changes | Update `meta.json` only. |
| `added` or `modified` non-empty, total churn < 30% of files | Incremental: re-analyze only affected files; splice into graph. |
| Total churn >= 30% of files, or `schemaVersion` mismatch | Full rebuild via `task-codemap --full`. |
| `deleted` only | Remove the nodes and their edges; no analysis pass needed. |
| `renamed` only | Update `filePath` on existing nodes; rewrite node IDs that embed the path; rewrite edges referencing those IDs. No analysis pass. |

The 30% threshold avoids the pathological case where an incremental refresh becomes slower than a rebuild.

### Splice semantics for incremental updates

1. Drop all nodes whose `filePath` is in `modified` or `deleted`.
2. Drop all edges where source or target referenced a dropped node ID.
3. Run analysis on `added` + `modified`. Produces new nodes and edges.
4. Merge new nodes/edges into the existing graph.
5. Re-validate (via `codemap-validate`). Dangling cross-file edges from un-touched files to dropped nodes are acceptable here - the analysis of `modified` files will reproduce them.
6. Recompute layer assignment **only for new nodes**. Existing layer assignments are preserved.
7. Guides are **not** regenerated on incremental refresh. They re-run only on `--full` or via explicit `task-codemap-guide --rebuild`.

## Output Format

This skill describes the contract. The actual hashing logic lives in `task-codemap/fingerprint.py`. The change-set JSON is produced by that script and consumed by `task-codemap` in sync mode.

Log a one-line summary at the end of a refresh:

```
Refreshed graph: +N added, M modified, R renamed, D deleted, U unchanged (X% churn)
```

## Avoid

- Hashing the full file with timestamps or git blob SHA - those break across machines and re-clones.
- Trying to detect intra-file changes (function-level fingerprints) - file-level granularity is the contract; smarter granularity belongs in a future schema version, not in producer-side improvisation.
- Triggering full rebuild on the schema-version field changing by patch - only major schema changes (`schemaVersion` integer bump) force a full rebuild.
- Treating renames as delete+add - it wastes analysis budget and loses guide/layer assignments.
