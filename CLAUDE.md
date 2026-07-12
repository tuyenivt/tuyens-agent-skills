# CLAUDE.md

Guidance for Claude Code working in this repository.

## Overview

A **Claude Code plugin marketplace repository** - agent skills and agents for Claude Code and Codex, organized by tech stack. Contains only Markdown skill definitions (`.md`); no application code, no build scripts, no test runners.

## Repository Structure

```
plugins/
  core/          # Stack-agnostic skills (required by all other plugins)
  codemap/       # Persistent codebase knowledge graph (any stack, opt-in)
  architecture/  # Stack-agnostic architecture design, re-architecture, task breakdown, and release notes
  oncall/        # Incident response workflows
  java/          # Java 21+ / Spring Boot 3.5+
  dotnet/        # .NET 8 LTS / ASP.NET Core Web API, Clean Architecture
  kotlin/        # Kotlin 2.0+ / Spring Boot 3.5+
  python/        # Python 3.11+ / FastAPI (primary), Django (secondary)
  ruby/          # Ruby 3.4+ / Ruby on Rails 7.2+
  node/          # Node.js/TypeScript, NestJS (primary), Express (secondary)
  go/            # Go 1.25+ / Gin / GORM+sqlx
  rust/          # Rust 1.94+ / Axum / sqlx
  php/           # PHP 8.5 / Laravel 12+
  react/         # React 18+ (React 19 hooks) / TypeScript / Next.js 15 App Router (primary), Vite 5+ (secondary)
  vue/           # Vue 3.5+ / TypeScript / Nuxt 3 (primary), Vite (secondary)
  angular/       # Angular 21+ / TypeScript / Angular CLI
```

Each plugin folder has a `README.md`. Each skill lives in its own directory as `SKILL.md`. Agent files are plain Markdown in `plugins/<stack>/agents/`.

`core` is required by all other plugins.

## Skill File Format

```yaml
---
name: skill-name
description: Short description shown in skill picker
metadata:
  category: backend
  tags: [tag1, tag2]
  type: workflow # only for task-* workflow skills
user-invocable: true # false = atomic skill, hidden from slash menu
---
```

- **Workflow skills** (`task-*`, `user-invocable: true`): user-facing slash commands that orchestrate atomic skills end-to-end.
- **Atomic skills** (`user-invocable: false`): focused single-concern patterns, composed via `Use skill: <name>` directives in Markdown bodies.

**Naming.** Workflow skills are prefixed `task-` (e.g., `task-spring-implement`). Atomic skills use `<framework>-<concern>` (e.g., `spring-jpa-performance`).

**Stack adaptation.** `stack-detect` reads the consuming project's `CLAUDE.md` for a `## Tech Stack` section (key-value pairs like `Language:`, `Framework:`, `Database:`). This is how skills adapt output to different ecosystems.

## Skill Placement

A skill belongs in `core` when **all** hold:

1. It is atomic (`user-invocable: false`), not a workflow.
2. It is referenced by skills/agents in two or more other plugins, OR is needed by a `core` workflow.
3. It is stack-agnostic.
4. It does not encode a single plugin's domain identity (ADRs and release plans are architecture's; postmortems are oncall's).

Workflow skills stay in their domain plugin. Skills are resolved by name, not path, so moving a skill is a directory rename - `Use skill: <name>` references continue to work.

## Codemap (persistent codebase graph, opt-in plugin)

The `codemap` plugin owns a `task-codemap-*` workflow family that builds and consumes a persistent knowledge graph of the consuming project. It is opt-in - no other plugin depends on it. Requires `core` (for `behavioral-principles` and `stack-detect`). All artifacts live under `.codemap/`:

```
.codemap/
  graph.json          # nodes + edges + layers (committed, source of truth)
  guides.json         # generated guided walkthroughs (committed)
  meta.json           # builtAt, gitCommitHash, version (committed)
  config.json         # autoUpdate flag, scope (committed)
  fingerprints.json   # per-file structural hashes (committed)
  .codemapignore      # user-editable, defaults to .gitignore (committed)
  .last-synced-head   # last HEAD the auto-update hook fired on (gitignore)
  intermediate/       # transient build outputs (gitignore)
```

Schema is owned by the `codemap-schema` atomic - 12 node types, 14 edge types, 6 layer enum. Producer (`task-codemap`) and consumers (`task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`) all `Use skill: codemap-schema` for the contract. Build pipeline is pure-LLM extraction with sub-agent parallelism; skill-local Python helpers in `plugins/codemap/skills/task-codemap/` handle deterministic scan/batch/merge/fingerprint.

`task-onboard` (in `core`, one-shot Markdown report, no graph dependency) remains the lightweight onboarding path. The codemap family does not duplicate it - orientation from the graph happens via `task-codemap-guide` (guided walkthroughs) and `task-codemap-ask` (ask anything).

## Plugin Hooks

Plugin folders may contain a `hooks/` directory with hook definitions that Claude Code auto-registers when the plugin is installed. Currently: `plugins/codemap/hooks/codemap-auto-update.json` plus `codemap-refresh-prompt.md`. Hooks are Claude-Code-only and must be opt-in (gated by a config flag in the consuming project, never always-on).

## Environment

- **Shell:** Git Bash on Windows. Use Unix commands (`mv`, `cp`, `mkdir -p`, forward slashes). No PowerShell or CMD.
- **Git: read-only.** Run only read operations (`git log`, `git diff`, `git status`, `git blame`). Never run state-changing git commands - the user manages all commits and branches.

## Writing Conventions

- Use `-` (hyphen-minus). Never `—` or `–` (em/en dash) in any Markdown file.

## Behavioral Principles

How Claude reasons and acts in this repo, in addition to the technical rules above.

- **Think before acting.** State assumptions before editing. If a request has multiple interpretations, present them. Read a skill before editing it; confirm referenced skills exist; count before claiming a number.
- **Minimum change, surgical scope.** Make the smallest edit that satisfies the request. Don't reformat untouched files, bump unrelated versions, or improve adjacent skills. Match existing conventions even if you'd do them differently.
- **Surface confusion, don't paper over it.** When skills contradict, frontmatter is missing, a `Use skill:` target doesn't exist, or versions disagree across `plugin.json`/`marketplace.json` - stop and name it. Don't silently pick a side.
- **Present tradeoffs.** When multiple viable approaches exist (atomic vs. workflow, new skill vs. extension), state the options and tradeoff. A default is fine; the alternative must be named.
- **Push back when the user is likely wrong.** If a request would break a documented convention (skipping the Post-Change Checklist, mixing workflow steps into an atomic skill, em dashes), say so before acting.
- **Verify after editing.** Re-read the changed section, check cross-references resolve, confirm the Post-Change Checklist is addressed. Work isn't done until verified.

## Adding a New Skill

1. Create `plugins/<stack>/skills/<skill-name>/SKILL.md` with the frontmatter above.
2. Workflow skills: prefix `task-`, set `user-invocable: true`, `type: workflow`. Atomic skills: set `user-invocable: false`.
3. Write the body following the standards below.
4. Update the plugin's `README.md` skill table.

### Composition Contracts

- **Workflow skills must load `Use skill: behavioral-principles` as Step 1**, before any other delegation including `stack-detect`. Universal and unconditional - the behavioral rules must be in effect for every subsequent step.
- Workflows that adapt output to the project's stack load `Use skill: stack-detect` immediately after behavioral-principles, as Step 2 (the shipped convention in core and stack routers). Workflows that don't depend on stack (e.g. `task-db-migration`) skip it entirely.
- Atomic skills that consume `stack-detect` output declare it at the top of the body with a blockquote: `> Load `Use skill: stack-detect` first to determine the project stack.` The consuming workflow loads `stack-detect`, not the atomic skill itself.

### Skill Content Standards

#### Description (frontmatter)

- **Hard cap 150 chars; aim for 100-140.** Descriptions load on every session and trigger `/doctor` truncation past ~1% of the context window.
- **Keyword-dense, not prose.** Lead with a verb (Review/Plan/Detect), pack identifying tokens (framework names, key tools, problem space). The skill picker matches on this text - make it trigger-accurate.
- **Positive framing only.** Describe what the skill does. Move "when not to use", phase enumerations, and anti-pattern walls into the body's `When to Use` / `Patterns` sections.

#### Required Body Sections

**Workflow skills** (`task-*`):

| Section           | Purpose                                                                  |
| ----------------- | ------------------------------------------------------------------------ |
| **When to Use**   | Scope, constraints, when NOT to use                                      |
| **Workflow**      | Numbered steps with `Use skill:` delegations to atomic skills            |
| **Output Format** | Template showing the expected deliverable                                |
| **Self-Check**    | Checkbox list aligned 1:1 with workflow steps                            |
| **Avoid**         | Anti-patterns and common mistakes                                        |

**Atomic skills:**

| Section           | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| **When to Use**   | Usage scope                                            |
| **Rules**         | Non-negotiable constraints                             |
| **Patterns**      | Detailed guidance with bad/good code pairs             |
| **Output Format** | Structured contract that consuming workflows parse     |
| **Avoid**         | Domain-specific anti-patterns                          |

#### Content Quality Rules

- **Output format is a contract.** Use exact field names and value enums (e.g., `Blast Radius: {Narrow | Moderate | Wide | Critical}`) - workflow skills parse this.
- **Self-check matches workflow steps 1:1.** No checks for steps that don't exist.
- **Bad/good code pairs.** Show the mistake then the fix, both with brief explanation.
- **Tables for decision support** (depth levels, scope options, classification).
- **Handle missing input, unknown stack, partial information explicitly.** Don't fail silently.
- **Workflows compose every relevant atomic skill** via `Use skill:`.
- **Consistent depth across stacks.** Equivalent skills (Python vs. Java) cover the same categories.

#### Authoring for Token Efficiency

Skills load into context on every invocation - longer is not better. Optimize up front so skills ship close to their post-eval state.

- **Rewrite, don't patch.** Layered patches accumulate ambiguity. When a section grows unclear, rewrite it.
- **Abstract, don't accumulate.** Three rules saying variations of the same thing collapse to one. Specific cases live in `Patterns`, not `Rules`.
- **Micro-examples beat large examples.** A 3-5 line bad/good pair clarifies more than a 30-line scenario. Keep examples only when they clarify behavior, define output structure, or show a non-obvious convention.
- **No duplication.** Each rule appears once. If it overlaps with `behavioral-principles` or another atomic skill, delete the local copy and let composition handle it.
- **Cut filler.** Drop "this skill helps you...", restated frontmatter, repeated motivation, procedural narration. Every sentence adds new information.
- **No hedging.** Skills are contracts - state the rule or omit it. No "you might want to consider...".
- **Halve any section that doesn't lose meaning when halved.**
- **Don't add unless necessary.** Default to simplify/compress/generalize over append.

## Adding a New Agent

1. Create `plugins/<stack>/agents/<agent-name>.md` with the frontmatter below.
2. Update the plugin's `README.md` agents table.

```yaml
---
name: <stack>-<role>                              # required: kebab-case, matches filename
description: Short description                    # required: shown in agent picker
category: quality | engineering | planning | ops  # optional but encouraged
tools: Read, Write, Edit, Bash, Glob, Grep        # optional: restrict tools
---
```

Only `name` and `description` are required; include the others when they meaningfully constrain the agent.

## Post-Change Checklist

After any change to plugin content (skills, agents, structure, conventions) - **excluding changes that only touch `CLAUDE.md` or `README.md`**:

1. **`CLAUDE.md`** - update if structure, conventions, naming, design principles, or workflow guidance changed.
2. **Root `README.md` and affected plugin `README.md`** - reflect added/removed/renamed skills or agents.
