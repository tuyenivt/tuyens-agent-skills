#!/usr/bin/env python3
"""
scan.py - Enumerate project files for codemap analysis.

Reads .codemapignore (if present) or falls back to .gitignore. Prefers
`git ls-files` for accurate ignored-file handling; falls back to os.walk.

Output: JSON manifest at the path given by --output.

Schema is documented in skills/codemap-build-pipeline/SKILL.md (Phase 1).
"""
import argparse
import fnmatch
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


def load_ignore_patterns(root: Path):
    """Return (codemapignore_patterns, gitignore_patterns).

    `.codemap/.codemapignore` is always applied. `.gitignore` is read as a fallback
    pattern source for the os.walk path (git ls-files already respects it).
    """
    def _read(path: Path):
        if not path.exists():
            return []
        patterns = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
        return patterns

    return _read(root / ".codemap" / ".codemapignore"), _read(root / ".gitignore")


def matches_pattern(rel_path: str, patterns: list) -> bool:
    """Match a forward-slash relative path against gitignore-style patterns.

    Supports: bare names (any depth), `dir/` (directory prefix), `**` segments,
    and standard fnmatch globs. Negation (`!`) is not supported.
    """
    if not patterns:
        return False
    parts = rel_path.split("/")
    for pat in patterns:
        if pat.startswith("!"):
            continue
        p = pat.rstrip("/")
        is_dir_only = pat.endswith("/")
        # Anchored to repo root if pattern contains a slash (other than trailing).
        anchored = "/" in p
        if anchored:
            if fnmatch.fnmatch(rel_path, p):
                return True
            if is_dir_only and (rel_path == p or rel_path.startswith(p + "/")):
                return True
            # `**` support via fnmatch translation
            if "**" in p and fnmatch.fnmatch(rel_path, p.replace("**", "*")):
                return True
        else:
            # Unanchored: match against any path segment or the basename.
            if any(fnmatch.fnmatch(part, p) for part in parts):
                return True
    return False


def git_commit_hash(root: Path):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


DEFAULT_MAX_FILE_BYTES = 500_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--scope", default=None, help="Optional subdirectory to limit scan to")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES,
                        help="Skip files larger than this byte count (default 500000; 0 disables).")
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

    codemap_patterns, gitignore_patterns = load_ignore_patterns(root)

    files = git_ls_files(scope_path)
    fallback_used = False
    if files is None:
        files = walk_filesystem(scope_path)
        fallback_used = True

    skipped_default = 0
    skipped_codemapignore = 0
    skipped_gitignore = 0
    skipped_oversize = 0
    oversize_paths = []
    entries = []
    for path in files:
        rel = path.relative_to(root)
        rel_str = str(rel).replace(os.sep, "/")
        if any(part in DEFAULT_IGNORE for part in rel.parts):
            skipped_default += 1
            continue
        if not path.is_file():
            continue
        if matches_pattern(rel_str, codemap_patterns):
            skipped_codemapignore += 1
            continue
        # Only apply .gitignore in the os.walk fallback - git ls-files already honored it.
        if fallback_used and matches_pattern(rel_str, gitignore_patterns):
            skipped_gitignore += 1
            continue
        language = classify_language(path)
        category = classify_category(rel, language)
        lines, byte_size = count_lines_and_bytes(path)
        if args.max_file_bytes and byte_size > args.max_file_bytes:
            skipped_oversize += 1
            oversize_paths.append({"path": rel_str, "bytes": byte_size})
            continue
        entries.append({
            "path": rel_str,
            "language": language or "unknown",
            "lines": lines,
            "bytes": byte_size,
            "category": category,
        })

    skipped_total = skipped_default + skipped_codemapignore + skipped_gitignore + skipped_oversize

    manifest = {
        "schemaVersion": 1,
        "scannedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rootPath": str(root.relative_to(root.parent)) if root.parent != root else ".",
        "scope": args.scope,
        "gitCommitHash": git_commit_hash(root),
        "totalFiles": len(entries),
        "skipped": skipped_total,
        "skippedBreakdown": {
            "default": skipped_default,
            "codemapignore": skipped_codemapignore,
            "gitignore": skipped_gitignore,
            "oversize": skipped_oversize,
        },
        "oversize": oversize_paths,
        "maxFileBytes": args.max_file_bytes,
        "enumerationMethod": "os.walk" if fallback_used else "git ls-files",
        "files": entries,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"scan: {len(entries)} files ({skipped_total} skipped: "
        f"{skipped_default} default, {skipped_codemapignore} .codemapignore, "
        f"{skipped_gitignore} .gitignore, {skipped_oversize} oversize) -> {args.output}"
    )


if __name__ == "__main__":
    main()
