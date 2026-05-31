#!/usr/bin/env python3
"""
scan.py - Enumerate project files for codemap analysis.

Reads .codemapignore (if present) or falls back to .gitignore. Prefers
`git ls-files` for accurate ignored-file handling; falls back to os.walk.

Output: JSON manifest at the path given by --output.

Schema is documented in skills/codemap-build-pipeline/SKILL.md (Phase 1).
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXTENSION_LANGUAGE = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".vue": "Vue", ".svelte": "Svelte",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".erb": "ERB",
    ".php": "PHP",
    ".cs": "C#", ".fs": "F#", ".vb": "VB.NET",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cc": "C++", ".hh": "C++",
    ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C++",
    ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hrl": "Erlang",
    ".clj": "Clojure", ".cljs": "Clojure",
    ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".fish": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".yml": "YAML", ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON", ".jsonc": "JSON",
    ".xml": "XML",
    ".md": "Markdown", ".mdx": "Markdown",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SASS", ".less": "LESS",
    ".dockerfile": "Dockerfile",
    ".tf": "Terraform", ".hcl": "HCL",
    ".proto": "Protobuf",
    ".graphql": "GraphQL", ".gql": "GraphQL",
    ".r": "R", ".R": "R",
    ".dart": "Dart",
    ".zig": "Zig",
}

SPECIAL_FILENAMES = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "Gemfile": "Ruby",
    "Rakefile": "Ruby",
    "go.mod": "Go",
    "go.sum": "Go",
    "Cargo.toml": "Rust",
    "Cargo.lock": "Rust",
    "package.json": "JSON",
    "package-lock.json": "JSON",
    "pnpm-lock.yaml": "YAML",
    "tsconfig.json": "JSON",
    "composer.json": "JSON",
    "composer.lock": "JSON",
    "pyproject.toml": "TOML",
    "requirements.txt": "Text",
    "build.gradle": "Groovy",
    "build.gradle.kts": "Kotlin",
    "pom.xml": "XML",
    "mix.exs": "Elixir",
    "CMakeLists.txt": "CMake",
    ".env.example": "DotEnv",
    "README": "Markdown",
}

CATEGORY_RULES = [
    # (predicate -> category) - first match wins
    (lambda p, lang: lang == "Markdown", "document"),
    (lambda p, lang: any(seg in p.parts for seg in ("test", "tests", "__tests__", "spec", "specs")), "test"),
    (lambda p, lang: p.name.endswith((".test.ts", ".test.js", ".test.tsx", ".test.jsx",
                                       "_test.go", ".spec.ts", ".spec.js")), "test"),
    (lambda p, lang: lang in ("YAML", "TOML", "JSON", "XML", "HCL", "DotEnv") or p.name in ("Dockerfile", "Makefile"), "config"),
    (lambda p, lang: any(seg in p.parts for seg in ("generated", "gen", "node_modules", "vendor", "dist", "build", "target", "out")), "generated"),
    (lambda p, lang: lang is not None, "code"),
]

DEFAULT_IGNORE = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "target",
    "out", ".next", ".nuxt", ".angular", ".svelte-kit", ".cache", "coverage",
    ".pytest_cache", "__pycache__", ".tox", ".venv", "venv", "env",
    ".idea", ".vscode", ".DS_Store",
    ".codemap",  # never scan ourselves
}


def classify_language(path: Path):
    if path.name in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[path.name]
    return EXTENSION_LANGUAGE.get(path.suffix.lower())


def classify_category(path: Path, language):
    for predicate, category in CATEGORY_RULES:
        if predicate(path, language):
            return category
    return "code"


def count_lines_and_bytes(path: Path):
    try:
        data = path.read_bytes()
        return data.count(b"\n") + (0 if data.endswith(b"\n") else 1), len(data)
    except OSError:
        return 0, 0


def git_ls_files(root: Path):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True,
        )
        return [root / Path(line) for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def walk_filesystem(root: Path):
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE]
        for fn in filenames:
            results.append(Path(dirpath) / fn)
    return results


def load_codemapignore(root: Path):
    ignore_file = root / ".codemap" / ".codemapignore"
    if not ignore_file.exists():
        ignore_file = root / ".gitignore"
    if not ignore_file.exists():
        return []
    patterns = []
    for line in ignore_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def git_commit_hash(root: Path):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--scope", default=None, help="Optional subdirectory to limit scan to")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: root not found or not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    scope_path = root
    if args.scope:
        scope_path = (root / args.scope).resolve()
        if not scope_path.is_dir():
            print(f"error: scope not found: {scope_path}", file=sys.stderr)
            sys.exit(1)

    files = git_ls_files(scope_path)
    fallback_used = False
    if files is None:
        files = walk_filesystem(scope_path)
        fallback_used = True

    skipped = 0
    entries = []
    for path in files:
        rel = path.relative_to(root)
        rel_parts = rel.parts
        if any(part in DEFAULT_IGNORE for part in rel_parts):
            skipped += 1
            continue
        if not path.is_file():
            continue
        language = classify_language(path)
        category = classify_category(rel, language)
        lines, byte_size = count_lines_and_bytes(path)
        entries.append({
            "path": str(rel).replace(os.sep, "/"),
            "language": language or "unknown",
            "lines": lines,
            "bytes": byte_size,
            "category": category,
        })

    manifest = {
        "schemaVersion": 1,
        "scannedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rootPath": str(root.relative_to(root.parent)) if root.parent != root else ".",
        "scope": args.scope,
        "gitCommitHash": git_commit_hash(root),
        "totalFiles": len(entries),
        "skipped": skipped,
        "enumerationMethod": "os.walk" if fallback_used else "git ls-files",
        "files": entries,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"scan: {len(entries)} files ({skipped} skipped) -> {args.output}")


if __name__ == "__main__":
    main()
