#!/usr/bin/env python3
"""
merge.py - Concatenate batch-*.json into one graph, dedupe edges, drop danglers.

Reads every batch-<N>.json (or batch-<N>-part-<K>.json) in a directory.
- Concatenates nodes. On duplicate IDs, keeps the first and logs dup.
- Concatenates edges. Dedupes by (source, target, type).
- Drops edges where source or target ID is not present in the node set.

Output: merged graph JSON without `layers` or `guides`.

Schema documented in skills/codemap-build-pipeline/SKILL.md (Phase 4).
"""
import argparse
import json
import re
import sys
from pathlib import Path

BATCH_FILE_PATTERN = re.compile(r"^batch-\d+(-part-\d+)?\.json$")
ERROR_FILE_PATTERN = re.compile(r"^batch-\d+(-part-\d+)?-error\.json$")


def numeric_sort_key(p: Path):
    # batch-10.json must sort after batch-2.json (lexicographic order would not).
    return [int(n) for n in re.findall(r"\d+", p.name)], p.name


def load_batches(batches_dir: Path):
    files = sorted(
        (p for p in batches_dir.iterdir() if BATCH_FILE_PATTERN.match(p.name)),
        key=numeric_sort_key,
    )
    if not files:
        print(f"error: no batch-*.json files found in {batches_dir}", file=sys.stderr)
        sys.exit(1)
    return files


def load_error_batches(batches_dir: Path):
    return sorted(
        (p for p in batches_dir.iterdir() if ERROR_FILE_PATTERN.match(p.name)),
        key=numeric_sort_key,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches-dir", required=True, help="Directory containing batch-*.json files")
    parser.add_argument("--output", required=True, help="Output merged graph JSON path")
    args = parser.parse_args()

    batches_dir = Path(args.batches_dir)
    if not batches_dir.is_dir():
        print(f"error: batches directory not found: {batches_dir}", file=sys.stderr)
        sys.exit(1)

    nodes_by_id = {}
    duplicate_node_ids = []
    edge_set = set()  # (source, target, type)
    edges = []
    malformed_batches = []

    for batch_file in load_batches(batches_dir):
        try:
            payload = json.loads(batch_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            # Tolerant: log and continue, matching duplicate-ID handling.
            malformed_batches.append({"file": batch_file.name, "reason": str(e)})
            print(f"warn: {batch_file.name} skipped ({e})", file=sys.stderr)
            continue

        for node in payload.get("nodes", []):
            node_id = node.get("id")
            if not node_id:
                continue
            if node_id in nodes_by_id:
                duplicate_node_ids.append({
                    "id": node_id,
                    "firstFrom": nodes_by_id[node_id].get("_sourceBatch", "?"),
                    "secondFrom": batch_file.name,
                })
                continue
            node["_sourceBatch"] = batch_file.name
            nodes_by_id[node_id] = node

        for edge in payload.get("edges", []):
            key = (edge.get("source"), edge.get("target"), edge.get("type"))
            if None in key:
                continue
            if key in edge_set:
                continue
            edge_set.add(key)
            edges.append(edge)

    # Strip internal _sourceBatch markers
    for node in nodes_by_id.values():
        node.pop("_sourceBatch", None)

    # Drop dangling edges
    valid_ids = set(nodes_by_id.keys())
    kept_edges = [e for e in edges if e["source"] in valid_ids and e["target"] in valid_ids]
    dropped = len(edges) - len(kept_edges)

    merged = {
        "schemaVersion": 1,
        "nodes": list(nodes_by_id.values()),
        "edges": kept_edges,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    # Collect any explicit error-batch sidecars written by retry-exhausted sub-agents.
    error_batches = []
    for err_file in load_error_batches(batches_dir):
        try:
            error_batches.append({
                "file": err_file.name,
                "payload": json.loads(err_file.read_text(encoding="utf-8")),
            })
        except (json.JSONDecodeError, OSError):
            error_batches.append({"file": err_file.name, "payload": None})

    summary = {
        "nodes": len(merged["nodes"]),
        "edges": len(merged["edges"]),
        "droppedDanglingEdges": dropped,
        "duplicateNodeIds": len(duplicate_node_ids),
        "malformedBatches": len(malformed_batches),
        "errorBatches": len(error_batches),
    }
    print(
        f"merge: {summary['nodes']} nodes, {summary['edges']} edges, "
        f"{dropped} dangling dropped, {len(duplicate_node_ids)} duplicate IDs, "
        f"{len(malformed_batches)} malformed, {len(error_batches)} error-batches"
    )

    # Write a merge log when anything noteworthy happened.
    if duplicate_node_ids or malformed_batches or error_batches:
        log_path = output_path.parent / "merge-log.json"
        log_path.write_text(json.dumps({
            "duplicateNodeIds": duplicate_node_ids,
            "malformedBatches": malformed_batches,
            "errorBatches": error_batches,
        }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
