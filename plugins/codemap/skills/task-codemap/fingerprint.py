#!/usr/bin/env python3
"""
fingerprint.py - Compute per-file structural fingerprints for incremental refresh.

Two modes:
  --mode compute   Compute fingerprints for every file in the scan manifest.
                   Output: fingerprints.json.
  --mode compare   Compare freshly computed fingerprints against an existing
                   fingerprints.json. Output: a change-set JSON describing
                   added/modified/renamed/deleted files.

Hashing rule (deterministic, cross-machine):
  1. Read file as UTF-8 (replace invalid bytes).
  2. Split on \\n.
  3. Trim trailing whitespace per line.
  4. Collapse 2+ consecutive blank lines into one blank line.
  5. Join with \\n, no trailing newline.
  6. sha256, hex-encoded, "sha256:" prefix.

Schema documented in skills/codemap-fingerprints/SKILL.md.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BLANK_RUN = re.compile(r"\n{3,}")


def normalize_content(raw: bytes) -> bytes:
    text = raw.decode("utf-8", errors="replace")
    lines = [line.rstrip() for line in text.split("\n")]
    joined = "\n".join(lines)
    collapsed = BLANK_RUN.sub("\n\n", joined)
    return collapsed.encode("utf-8")


def hash_file(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return "sha256:" + "0" * 64
    normalized = normalize_content(raw)
    digest = hashlib.sha256(normalized).hexdigest()
    return "sha256:" + digest


def compute_mode(scan_path: Path, output_path: Path, root: Path):
    manifest = json.loads(scan_path.read_text(encoding="utf-8"))
    files_info = {}
    for entry in manifest.get("files", []):
        rel = entry["path"]
        abs_path = root / rel
        content_hash = hash_file(abs_path)
        files_info[rel] = {
            "contentHash": content_hash,
            "byteSize": entry.get("bytes", 0),
            "lineCount": entry.get("lines", 0),
            "language": entry.get("language", "unknown"),
        }

    fingerprints = {
        "schemaVersion": 1,
        "computedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files_info,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fingerprints, indent=2), encoding="utf-8")
    print(f"fingerprint compute: {len(files_info)} files -> {output_path}")


def compare_mode(current_path: Path, previous_path: Path, output_path: Path):
    if not previous_path.is_file():
        print(f"error: previous fingerprints not found: {previous_path}", file=sys.stderr)
        sys.exit(1)

    current = json.loads(current_path.read_text(encoding="utf-8"))
    previous = json.loads(previous_path.read_text(encoding="utf-8"))

    # Schema version gate
    if current.get("schemaVersion") != previous.get("schemaVersion"):
        change_set = {
            "schemaVersionChanged": True,
            "added": list(current.get("files", {}).keys()),
            "modified": [],
            "renamed": [],
            "deleted": [],
            "unchanged": 0,
        }
        output_path.write_text(json.dumps(change_set, indent=2), encoding="utf-8")
        print("fingerprint compare: schema version mismatch - full rebuild required")
        return

    cur_files = current.get("files", {})
    prev_files = previous.get("files", {})
    cur_paths = set(cur_files.keys())
    prev_paths = set(prev_files.keys())

    added_paths = cur_paths - prev_paths
    deleted_paths = prev_paths - cur_paths
    common_paths = cur_paths & prev_paths

    # Detect renames: a deleted path's hash equals a new path's hash
    renamed = []
    used_added = set()
    used_deleted = set()
    prev_hash_to_path = {prev_files[p]["contentHash"]: p for p in deleted_paths}
    for new_path in list(added_paths):
        new_hash = cur_files[new_path]["contentHash"]
        if new_hash in prev_hash_to_path:
            old_path = prev_hash_to_path[new_hash]
            if old_path in used_deleted:
                continue
            renamed.append({"from": old_path, "to": new_path})
            used_added.add(new_path)
            used_deleted.add(old_path)

    added = sorted(added_paths - used_added)
    deleted = sorted(deleted_paths - used_deleted)

    modified = []
    unchanged = 0
    for path in common_paths:
        if cur_files[path]["contentHash"] != prev_files[path]["contentHash"]:
            modified.append(path)
        else:
            unchanged += 1
    modified.sort()

    total = len(cur_paths) + len(deleted)
    churn = ((len(added) + len(modified) + len(deleted) + len(renamed)) / total) if total else 0.0

    change_set = {
        "schemaVersionChanged": False,
        "added": added,
        "modified": modified,
        "renamed": renamed,
        "deleted": deleted,
        "unchanged": unchanged,
        "churnRatio": round(churn, 4),
        "recommendation": "full" if churn >= 0.30 else "incremental",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(change_set, indent=2), encoding="utf-8")
    print(
        f"fingerprint compare: +{len(added)} added, {len(modified)} modified, "
        f"{len(renamed)} renamed, {len(deleted)} deleted, {unchanged} unchanged "
        f"({churn*100:.1f}% churn) -> {change_set['recommendation']}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["compute", "compare"], required=True)
    parser.add_argument("--scan", help="scan.json (required for --mode compute)")
    parser.add_argument("--root", default=".", help="Project root (default: current dir)")
    parser.add_argument("--current", help="Current fingerprints.json (for compare)")
    parser.add_argument("--previous", help="Previous fingerprints.json (for compare)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    if args.mode == "compute":
        if not args.scan:
            print("error: --scan is required for --mode compute", file=sys.stderr)
            sys.exit(1)
        compute_mode(Path(args.scan), Path(args.output), Path(args.root).resolve())
    else:
        if not args.current or not args.previous:
            print("error: --current and --previous are required for --mode compare", file=sys.stderr)
            sys.exit(1)
        compare_mode(Path(args.current), Path(args.previous), Path(args.output))


if __name__ == "__main__":
    main()
