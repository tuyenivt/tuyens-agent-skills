---
name: codemap-fingerprints
description: Per-file structural fingerprint contract for incremental codemap refresh - hash inputs, comparison rules, change-set output shape.
metadata:
  category: core
  tags: [codemap, incremental, fingerprints, change-detection]
user-invocable: false
---

# Codemap Fingerprints

> Load `Use skill: codemap-schema` for graph shape.

Per-file structural fingerprint used by `task-codemap` sync mode to decide which files need re-analysis. Computed by skill-local `fingerprint.py`, stored at `.codemap/fingerprints.json`.

## When to Use

- After every successful build, write `fingerprints.json` alongside `graph.json`.
- Before an incremental refresh, recompute fingerprints for the working tree, diff against the stored set, and pass only changed files to analysis.

## Rules

1. **Hash content + path only.** No timestamps, no inode, no git blob SHA. Deterministic across machines and re-clones.
2. **File-level granularity.** Sub-file change detection is out of scope - belongs in a future schema version, not producer-side improvisation.
3. **Whitespace-insensitive.** Trim trailing whitespace per line and collapse blank-line runs before hashing - reformats don't trigger re-analysis.
4. **Detect renames by hash.** Same hash under a different path is a rename. The refresh updates `filePath` on existing nodes rather than rebuilding.
5. **Schema-version gate.** `fingerprints.json#schemaVersion` mismatch forces full rebuild.

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
    }
  }
}
```

### Hash input (deterministic)

1. Read file as UTF-8 (replace invalid bytes with `�`).
2. Split on `\n`, trim trailing whitespace per line.
3. Collapse runs of 2+ blank lines into one.
4. Join with `\n`, no trailing newline.
5. `sha256` over the bytes, hex-encoded, prefixed with `sha256:`.

### Change-set shape (passed to analysis phase)

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

`unchanged` is a count, not a list.

### Refresh decision matrix

| Signal | Action |
| --- | --- |
| All lists empty, HEAD matches `meta.json` | No-op. |
| All lists empty, HEAD stale | Update `meta.json#gitCommitHash` only. |
| `added` or `modified` non-empty, churn < 30% | Incremental: re-analyze affected, splice. |
| Churn >= 30%, or `schemaVersion` mismatch | Escalate to full rebuild. |
| `deleted` only | Drop nodes + edges; no analysis pass. |
| `renamed` only | Rewrite `filePath` and IDs; no analysis pass. |

The 30% threshold avoids incremental becoming slower than rebuild.

### Splice semantics (incremental refresh)

1. Drop nodes whose `filePath` is in `modified` or `deleted`.
2. Drop edges where either endpoint is a dropped node.
3. Analyze `added` + `modified` -> new nodes/edges.
4. Merge into the existing graph.
5. Re-validate. Dangling cross-file edges from un-touched files to dropped nodes are acceptable - analysis of `modified` files reproduces them.
6. Layer-assign **only new nodes**. Preserve existing assignments.
7. Guides do **not** regenerate on sync - run `task-codemap-guide --rebuild` or `task-codemap --full`.

## Output Format

Hashing logic lives in `task-codemap/fingerprint.py`. Change-set JSON is produced by that script and consumed by `task-codemap` sync mode.

End-of-refresh log line:

```
Refreshed graph: +N added, M modified, R renamed, D deleted, U unchanged (X% churn)
```

## Avoid

- Hashing with timestamps or git blob SHA - breaks across machines.
- Function-level fingerprints - out of scope; belongs in a schema bump.
- Renames treated as delete+add - wastes analysis and loses layer/guide assignments.
