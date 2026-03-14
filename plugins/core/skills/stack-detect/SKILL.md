---
name: stack-detect
description: Detect project tech stack from marker files and the repo context file (CLAUDE.md, AGENTS.md, or GEMINI.md). Extracts any declared language, framework, build tool, database, and test framework as key-value pairs. Stack-agnostic - works with any ecosystem.
user-invocable: false
---

# Stack Detection

## Purpose

Provide consistent stack detection for all framework-aware skills in the core plugin. Every framework-aware workflow MUST load this skill first.

This skill does NOT maintain a list of supported stacks. It passes through whatever stack information it finds. Framework-aware skills then use this context to adapt their advice using their own knowledge of that ecosystem. If a skill does not recognize the detected stack, it should provide GENERAL best-practice advice and note that its recommendations may need adaptation for the specific framework.

## Detection Procedure

### Step 1 - File-Based Detection (primary)

Check for well-known marker files in the project root. This is reliable, zero-cost, and does not depend on any manually maintained file:

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
| `Makefile`                                      | Check further - could be anything |

File-based detection determines `Language` and often `Build tool`. It cannot determine `Framework`, `Database`, `ORM`, or `Test framework` - those require Step 2.

### Step 2 - Agent Instruction File (supplemental detail)

After file-based detection, optionally read the agent instruction file for supplemental details (framework, database, ORM, test framework) that cannot be inferred from marker files alone.

Check in this priority order, use the **first one found**:

1. `./CLAUDE.md` or `.claude/CLAUDE.md` (Claude Code)
2. `./AGENTS.md` (OpenAI Codex / multi-agent)
3. `./GEMINI.md` (Google Gemini)

From the file, **only extract the `## Tech Stack` section** (or equivalent heading containing "stack", "technology", "tech"). Extract key-value lines like `Language:`, `Framework:`, `Build:`, `Database:`, `ORM:`, `Test:` as-is. Ignore all other content.

Examples of what to extract:

- `Language: Rust` → language = "Rust"
- `Framework: Actix-web` → framework = "Actix-web"
- `ORM: Diesel` → orm = "Diesel"
- `Build: Cargo` → build_tool = "Cargo"
- `Database: PostgreSQL` → database = "PostgreSQL"
- `Test: cargo test + rstest` → test_framework = "cargo test + rstest"

If an instruction file is found but has no stack section, skip it silently. File-based detection results take precedence for any field both sources provide.

If neither step yields a language: language = "unknown". Suggest the user add a `## Tech Stack` section to their agent instruction file.

> **Note for repo maintainers:** Research shows that large or bloated repo context files reduce coding agent task success rates and increase inference cost. Keep your context file lean - the `## Tech Stack` section should be a short list of key-value pairs only. Review and update it whenever the stack changes; stale or incorrect entries are worse than no entry.

### Step 3 - Output

```
Detected stack:
  Language: {as declared or detected}
  Framework: {as declared or detected}
  Build tool: {as declared or detected}
  Database: {as declared or detected}
  Test framework: {as declared or detected}
  ORM: {as declared or detected}
  Additional: {any other properties found in the instruction file}
Source: CLAUDE.md | AGENTS.md | GEMINI.md | file-detection | unknown
```

## Output Format

This is the contract that all consuming workflow skills depend on. Do not change field names or structure.

```
Detected stack:
  Language: {string - as declared or "unknown"}
  Framework: {string - as declared or "unknown"}
  Build tool: {string - as declared or "unknown"}
  Database: {string - as declared or "unknown"}
  Test framework: {string - as declared or "unknown"}
  ORM: {string - as declared or omitted if not declared}
  Additional: {any other declared key-value pairs, or omitted if none}
Source: context-file | file-detection | unknown
```

**Consuming skill contract:**

- All fields except `Language` and `Framework` are optional - omit if not declared
- `Source` is always present - tells consumers how reliable the detection is
- `file-detection` source is lower confidence than instruction-file sources; consuming skills should note this
- `unknown` language means no detection succeeded; consuming skills must degrade gracefully

## Rules

- Never guess - if a field cannot be determined, use `unknown`
- File-based marker detection is the primary source; agent instruction files are supplemental for details (framework, database, ORM) that marker files cannot provide
- Do not prompt the user for stack information - detect silently
- If multiple languages are present (e.g., backend + frontend), report the primary backend language as `language` and note others in `Additional`. Example: `Language: Java`, `Additional: Frontend: TypeScript (React)`. If the CLAUDE.md Tech Stack section lists both, use that as the source of truth; otherwise infer from marker files (e.g., both `build.gradle` and `package.json` present).
- Cache the result mentally for the duration of the conversation - do not re-detect on every skill invocation
- Do not validate detected values against any fixed list - pass through as-is

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

- Do not hard-code stack assumptions - always detect first
- Do not fail loudly if detection is inconclusive - degrade gracefully to `unknown`
- Do not read every file in the project to detect the stack - check a small set of marker files and only the `## Tech Stack` section of instruction files
- Do not maintain a fixed enum of valid languages or frameworks - any value is valid
- Do not validate or reject unfamiliar stack values
