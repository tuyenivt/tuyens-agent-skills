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
4. **Detect renames by hash.** During `fingerprint.py --mode compare`, a hash present in the previous set but missing in the current set, paired with a new path whose hash matches, is emitted as a rename rather than a delete + add. The refresh rewrites the path on existing nodes - both `filePath` and the path segment embedded in `id` (e.g., `function:src/old.ts:foo` -> `function:src/new.ts:foo`) - plus every edge endpoint that references those IDs. No re-analysis. If two files share a hash (empty stubs, identical headers), the pairing is ambiguous - fall back to delete + add for those.
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

Rows are **not** mutually exclusive - a real change-set mixes added/modified/deleted/renamed. Evaluate top-down and take the **first** matching row; that row governs, and a mixed change-set folds the per-list handling (drop deleted, rewrite renamed) into the incremental pass.

| Signal (first match wins) | Action |
| --- | --- |
| `schemaVersion` mismatch, or churn >= 30% | Escalate to full rebuild. |
| All lists empty, HEAD matches `meta.json` | No-op. |
| All lists empty, HEAD stale | Update `meta.json#gitCommitHash` only. |
| `deleted` and/or `renamed` only (no `added`/`modified`) | Drop deleted nodes+edges; rewrite renamed paths/IDs; no analysis pass. |
| Any `added`/`modified` (alone or mixed with deleted/renamed) | Incremental: re-analyze added+modified, splice, and within the splice also drop deleted and rewrite renamed. |

**Churn** = changed files / total scanned files, where changed = added + modified + renamed + deleted. The 30% threshold avoids incremental becoming slower than rebuild.

### Splice semantics (incremental refresh)

1. Rewrite `renamed` nodes in place (Rule 4): update `filePath`, the path in `id`, and referring edge endpoints. These nodes are not dropped or re-analyzed.
2. Drop nodes whose `filePath` is in `modified` or `deleted`.
3. Drop edges where either endpoint is a dropped node.
4. Analyze `added` + `modified` -> new nodes/edges.
5. Merge into the existing graph.
6. Re-validate. Dangling cross-file edges from un-touched files to dropped nodes are acceptable - analysis of `modified` files reproduces them. If validation errors, keep the prior graph and escalate to full rebuild.
7. Layer-assign **only new nodes**. Preserve existing assignments (including renamed nodes).
8. Guides do **not** regenerate on sync - run `task-codemap-guide --rebuild` or `task-codemap --full`.

## Output Format

Hashing logic lives in `task-codemap/fingerprint.py`. Change-set JSON is produced by that script and consumed by `task-codemap` sync mode.

End-of-refresh log line:

```
Refreshed graph: +N added, M modified, R renamed, D deleted, U unchanged (X.X% churn)
```

Churn renders to one decimal place.

## Avoid

- Hashing with timestamps or git blob SHA - breaks across machines.
- Function-level fingerprints - out of scope; belongs in a schema bump.
- Renames treated as delete+add - wastes analysis and loses layer/guide assignments.
