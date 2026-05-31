#!/usr/bin/env python3
"""
batch.py - Group scanned files into ~25-file batches with directory cohesion.

Reads the scan manifest produced by scan.py. Groups files so that each batch:
- Has up to 25 files
- Stays under 800 KB total bytes
- Prefers same-directory cohesion (siblings group first)

Output: JSON with batches array.

Schema documented in skills/codemap-build-pipeline/SKILL.md (Phase 2).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

MAX_FILES_PER_BATCH = 25
MAX_BYTES_PER_BATCH = 800_000


def group_by_directory(files):
    groups = defaultdict(list)
    for entry in files:
        dir_path = "/".join(entry["path"].split("/")[:-1]) or "."
        groups[dir_path].append(entry)
    return groups


def primary_language(entries):
    counts = defaultdict(int)
    for e in entries:
        counts[e["language"]] += 1
    return max(counts, key=counts.get) if counts else "unknown"


def build_batches(files):
    groups = group_by_directory(files)
    ordered_dirs = sorted(groups.keys())

    batches = []
    current = {"files": [], "totalBytes": 0}

    def flush():
        nonlocal current
        if not current["files"]:
            return
        batches.append({
            "index": len(batches),
            "files": [e["path"] for e in current["files"]],
            "totalBytes": current["totalBytes"],
            "primaryLanguage": primary_language(current["files"]),
        })
        current = {"files": [], "totalBytes": 0}

    for dir_path in ordered_dirs:
        entries = sorted(groups[dir_path], key=lambda e: e["path"])
        for entry in entries:
            byte_size = entry["bytes"]
            would_exceed = (
                len(current["files"]) >= MAX_FILES_PER_BATCH
                or (current["totalBytes"] + byte_size > MAX_BYTES_PER_BATCH and current["files"])
            )
            if would_exceed:
                flush()
            current["files"].append(entry)
            current["totalBytes"] += byte_size
        # End of a directory: prefer to flush if batch is at least 60% full to keep cohesion
        if len(current["files"]) >= int(MAX_FILES_PER_BATCH * 0.6):
            flush()

    flush()
    return batches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", required=True, help="Path to scan.json from scan.py")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    scan_path = Path(args.scan)
    if not scan_path.is_file():
        print(f"error: scan file not found: {scan_path}", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(scan_path.read_text(encoding="utf-8"))
    files = manifest.get("files", [])
    if not files:
        print("error: scan manifest has no files", file=sys.stderr)
        sys.exit(1)

    batches = build_batches(files)

    output = {
        "schemaVersion": 1,
        "totalBatches": len(batches),
        "totalFiles": sum(len(b["files"]) for b in batches),
        "batches": batches,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"batch: {len(batches)} batches covering {output['totalFiles']} files -> {args.output}")


if __name__ == "__main__":
    main()
