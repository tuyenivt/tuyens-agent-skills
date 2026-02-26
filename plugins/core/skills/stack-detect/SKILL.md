---
name: stack-detect
description: Detect project tech stack by reading CLAUDE.md. Extracts any declared language, framework, build tool, database, and test framework as key-value pairs. Stack-agnostic — works with any ecosystem.
user-invocable: false
---

# Stack Detection

## Purpose

Provide consistent stack detection for all framework-aware skills in the core plugin. Every framework-aware workflow MUST load this skill first.

This skill does NOT maintain a list of supported stacks. It passes through whatever stack information it finds. Framework-aware skills then use this context to adapt their advice using their own knowledge of that ecosystem. If a skill does not recognize the detected stack, it should provide GENERAL best-practice advice and note that its recommendations may need adaptation for the specific framework.

## Detection Procedure

### Step 1 — Read CLAUDE.md

1. Read the project's CLAUDE.md file (check `./CLAUDE.md`, then `.claude/CLAUDE.md`)
2. Find any section about the tech stack — headings containing "stack", "technology", "tech", "requirements", "tools", or key-value lines like `Language:`, `Framework:`, `Build:`, `Database:`, `ORM:`, `Test:`
3. Extract ALL declared properties as-is. Do not validate against a known list.

Examples of what to extract:

- `Language: Rust` → language = "Rust"
- `Framework: Actix-web` → framework = "Actix-web"
- `ORM: Diesel` → orm = "Diesel"
- `Build: Cargo` → build_tool = "Cargo"
- `Database: PostgreSQL` → database = "PostgreSQL"
- `Test: cargo test + rstest` → test_framework = "cargo test + rstest"

Whatever the user declares, that's what we use. The output is a structured bag of properties, not a switch on known values.

### Step 2 — File-Based Fallback

If CLAUDE.md has no stack section, fall back to file-based detection. This is a **best-effort heuristic** and is explicitly **non-exhaustive**:

| Marker File(s)                                  | Detected Ecosystem                |
| ----------------------------------------------- | --------------------------------- |
| `build.gradle` / `build.gradle.kts` / `pom.xml` | Java ecosystem                    |
| `Gemfile` / `Rakefile`                          | Ruby ecosystem                    |
| `go.mod`                                        | Go ecosystem                      |
| `package.json`                                  | JavaScript/TypeScript ecosystem   |
| `Cargo.toml`                                    | Rust ecosystem                    |
| `pyproject.toml` / `requirements.txt`           | Python ecosystem                  |
| `mix.exs`                                       | Elixir ecosystem                  |
| `*.csproj` / `*.sln`                            | .NET ecosystem                    |
| `Makefile`                                      | Check further — could be anything |

If nothing matches: language = "unknown". Warn the user to add stack info to CLAUDE.md for better results.

### Step 3 — Output

```
Detected stack:
  Language: {as declared or detected}
  Framework: {as declared or detected}
  Build tool: {as declared or detected}
  Database: {as declared or detected}
  Test framework: {as declared or detected}
  ORM: {as declared or detected}
  Additional: {any other properties found in CLAUDE.md}
Source: CLAUDE.md | file-detection | unknown
```

## Rules

- Never guess — if a field cannot be determined, use `unknown`
- CLAUDE.md is the authoritative source; file-based detection is a fallback only
- Do not prompt the user for stack information — detect silently
- If multiple languages are present (e.g., backend + frontend), report the primary backend language as `language` and note the frontend separately
- Cache the result mentally for the duration of the conversation — do not re-detect on every skill invocation
- Do not validate detected values against any fixed list — pass through as-is

## When to Use

- Called automatically by any skill that contains `Use skill: stack-detect`
- Called at the start of any workflow skill that adapts its output based on tech stack
- Called when a skill needs to determine which ecosystem-specific patterns to apply

## How Skills Consume the Result

After detection, the calling skill uses the detected values to adapt its advice:

```
Use skill: stack-detect

Use the detected language, framework, and tooling to:
  → Apply ecosystem-appropriate patterns and idioms
  → Reference the detected framework's conventions and libraries
  → Provide guidance consistent with the detected build tool and test framework

If the detected stack is unfamiliar:
  → Apply universal, language-agnostic best practices
  → Note that recommendations may need adaptation for the specific framework
  → Suggest the user consult their framework's documentation
```

## Avoid

- Do not hard-code stack assumptions — always detect first
- Do not fail loudly if detection is inconclusive — degrade gracefully to `unknown`
- Do not read every file in the project to detect the stack — check CLAUDE.md and a small set of marker files only
- Do not maintain a fixed enum of valid languages or frameworks — any value is valid
- Do not validate or reject unfamiliar stack values
