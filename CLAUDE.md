# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a **Claude Code plugin marketplace repository** - a collection of agent skills and agents for Claude Code and Codex, organized by tech stack. It contains no application code; all files are Markdown skill definitions (`.md`) consumed by the Claude Code plugin system.

## Repository Structure

```
plugins/
  core/          # Stack-agnostic skills (required by all other plugins)
    skills/      # 45 skills: 12 workflow (task-*) + 33 atomic
  delivery/      # Release planning and delivery coordination
    skills/      # 6 workflow skills
  architecture/  # Stack-agnostic architecture design and re-architecture
    skills/      # 13 skills: 9 workflow + 4 atomic
  oncall/        # Incident response workflows
    skills/      # 7 skills: 2 workflow + 5 atomic
  spec/          # Spec-Driven Development (any stack, opt-in)
    skills/      # 19 skills: 10 workflow + 9 atomic
  java/          # Java 21+ / Spring Boot 3.5+
    skills/      # 12 skills (2 workflow + 10 atomic)
    agents/      # 7 agent definitions
  dotnet/        # .NET 8 LTS / ASP.NET Core Web API, Clean Architecture
    skills/      # 11 skills (2 workflow + 9 atomic)
    agents/      # 7 agent definitions
  kotlin/        # Thin companion to java plugin (requires core + java)
    skills/      # 5 skills (2 workflow + 3 atomic)
    agents/      # 7 agent definitions
  python/        # Python 3.11+ / FastAPI (primary), Django (secondary)
    skills/      # 9 skills (2 workflow + 7 atomic)
    agents/      # 7 agent definitions
  rails/         # Ruby on Rails 7+/8
    skills/      # 8 skills (2 workflow + 6 atomic)
    agents/      # 7 agent definitions
  node/          # Node.js/TypeScript, NestJS (primary), Express (secondary)
    skills/      # 10 skills (2 workflow + 8 atomic)
    agents/      # 7 agent definitions
  go/            # Go 1.25+ / Gin / GORM+sqlx
    skills/      # 9 skills (2 workflow + 7 atomic)
    agents/      # 7 agent definitions
  rust/          # Rust 1.94+ / Axum / sqlx
    skills/      # 11 skills (2 workflow + 9 atomic)
    agents/      # 7 agent definitions
  php/           # PHP 8.5 / Laravel 12+
    skills/      # 9 skills (2 workflow + 7 atomic)
    agents/      # 7 agent definitions
  react/         # React 19+ / TypeScript / Next.js (primary), Vite (secondary)
    skills/      # 10 skills (2 workflow + 8 atomic)
    agents/      # 5 agent definitions
  vue/           # Vue 3.5+ / TypeScript / Nuxt 3 (primary), Vite (secondary)
    skills/      # 11 skills (2 workflow + 9 atomic)
    agents/      # 5 agent definitions
  angular/       # Angular 21+ / TypeScript / Angular CLI
    skills/      # 10 skills (2 workflow + 8 atomic)
    agents/      # 5 agent definitions
```

Each plugin folder has its own `README.md`. Each skill lives in its own directory as a `SKILL.md` file.

## Skill File Format

Every `SKILL.md` begins with YAML frontmatter:

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

- **Workflow skills** (`task-*`, `user-invocable: true`): invoked by users as slash commands, orchestrate multiple atomic skills
- **Atomic skills** (`user-invocable: false`): focused reusable patterns, composed into workflows via `Use skill: <name>` directives

## Skill Naming Conventions

- Workflow skills are always prefixed `task-` (e.g., `task-spring-new`, `task-code-review`)
- Atomic skills use `<framework>-<concern>` format (e.g., `spring-jpa-performance`, `go-error-handling`)
- Agent files are plain Markdown in `plugins/<stack>/agents/`

## Plugin Dependencies

- `core` is required by all other plugins
- `kotlin` additionally requires `java`
- `spec` requires only `core`; per-stack agents are supplied by whichever stack plugins are installed (e.g., `java`, `python`, `react`)

## Skill Placement: When a Skill Belongs in `core`

Use this rule to decide where a new or existing skill should live. A skill belongs in `core` when **all** of the following hold:

1. It is an **atomic** skill (`user-invocable: false`), not a workflow.
2. It is referenced by skills or agents in **two or more other plugins**, OR is needed by a `core` workflow.
3. It is **stack-agnostic** - no language- or framework-specific guidance baked in.
4. It does **not** encode a single plugin's domain identity (e.g., ADRs are architecture's identity; release plans are delivery's identity).

Workflow skills (`task-*`) stay in the plugin whose domain they represent. If another plugin needs the same capability, it composes the same atomic building blocks rather than depending on the workflow.

When a skill fails any condition, leave it where it is. When it satisfies all four, the move is a directory rename - skills are resolved by name, not path, so `Use skill: <name>` references continue to work.

## Stack Detection Pattern

Many core workflow skills begin with `Use skill: stack-detect`, which reads the consuming project's `CLAUDE.md` for a `## Tech Stack` section (key-value pairs like `Language:`, `Framework:`, `Database:`). This is the primary mechanism by which skills adapt their output to different ecosystems.

## Spec-Driven Development

The `spec` plugin adds an optional Spec-Driven Development (SDD) pipeline mirroring GitHub Spec Kit. It is opt-in - install the plugin only when a project wants spec-first delivery; nothing in `core` or the stack plugins depends on it.

**Artifact convention.** All SDD artifacts for a feature live under `.specs/<slug>/`:

```
.specs/<slug>/
  spec.md              # what + why (acceptance criteria, NFRs, out-of-scope)
  clarifications.md    # append-only Q&A log from task-spec-clarify
  plan.md              # how (architecture, tech choices, contracts)
  tasks.md             # ordered, dependency-aware execution list
  analysis.md          # cross-artifact consistency findings (append-only)
  checklists/          # requirements-quality gate; one append-only file per theme (default: requirements.md)
  constitution.md      # project principles (append-only amendments)
  evaluation.md        # post-implementation scoring (append-only)
  handoffs/            # orchestration envelopes <NN>-<step>-<agent>.md
```

Append-only files preserve iteration history; comparing runs is part of the workflow.

**Dual-mode (speckit / standalone).** `speckit-detect` decides whether the consuming project already has Spec Kit installed. When Spec Kit is present, SDD workflows defer to its templates and slash commands; otherwise they run standalone using the artifact layout above. Both modes produce the same `.specs/<slug>/` shape.

**Spec-aware workflow contract.** Existing stack workflows (e.g., `task-spring-new`, `task-react-new`) accept a `--spec <slug>` flag. When set, they load `Use skill: spec-aware-preamble` to ingest the spec artifacts and skip their own GATHER/DESIGN steps - the spec is the source of truth. When unset, workflows run their normal interactive flow.

**Orchestration model.** `task-spec-orchestrate` sequences architect → dev → test → review using per-stack agents. Agents communicate by appending YAML envelopes to `handoffs/` (filesystem-as-bus, no central state machine; see `agent-handoff-contract`). After each step `fix-loop-controller` reads the directory and decides `proceed` / `loop` / `pause-for-amendment` / `escalate`. Default fix-loop budget is 3 iterations; hard cap 5.

**Opt-in evaluation.** `task-spec-evaluate` shells out to run the project's tests (`eval-test-runner`), maps every AC and NFR to evidence (`eval-spec-coverage`), and aggregates with review verdicts (`eval-scorer`) into a single `pass` / `needs-fix` / `fail` status appended to `evaluation.md`. When `task-spec-orchestrate` is invoked with `--with-evaluation`, the score is written as a sidecar `<NN>-review-score.yaml` next to each review envelope and becomes the primary fix-loop signal (sidecar wins over envelope status when both exist).

## Environment

- Shell: Git Bash on Windows - use Unix commands (`mv`, `cp`, `mkdir -p`, forward slashes). Do not use PowerShell cmdlets or CMD commands.
- **Git: read-only**. Only read operations are allowed (`git log`, `git diff`, `git status`, `git blame`, etc.). Never run state-changing git commands (`git add`, `git commit`, `git push`, `git checkout`, `git reset`, `git rebase`, `git merge`, `git stash`, `git branch -d/-D`, etc.). The user manages all commits and branch operations manually.

## Writing Conventions

- Always use `-` (hyphen-minus) instead of `-` (em dash) in all Markdown files.

## Key Design Principles

- **Atomic vs workflow separation**: Atomic skills are focused single-concern patterns; workflow skills (`task-*`) orchestrate them into end-to-end user-facing flows.
- **Stack-agnostic core**: The `core` plugin adapts to any detected stack - it never hardcodes framework assumptions.
- **No application code**: This repo contains only Markdown; there are no build scripts, test runners, or executables to run.
- **Composition via `Use skill:`**: Skills reference other skills using `Use skill: <skill-name>` directives in their Markdown body - this is how skill composition works at runtime.

## Behavioral Principles

These principles govern how Claude should reason and act when working in this repository. They apply in addition to, not instead of, the technical rules above.

- **Think before acting.** State assumptions explicitly before editing. If a request has multiple interpretations, present them - don't pick silently. If something is unclear, stop and name it. Read a skill before editing it; confirm a referenced skill exists before citing it; count skills before claiming a number.
- **Simplicity first.** Make the minimum change that satisfies the request. No speculative additions, no restructuring beyond the stated scope. If an edit touches 10 files but 3 would do, use 3.
- **Surgical changes.** Touch only what the request requires. Don't improve adjacent skills, bump unrelated versions, or reformat files that weren't the target. Match existing conventions even if you'd do it differently.
- **Surface confusion, don't paper over it.** When two skills contradict each other, when a frontmatter field is missing, when a `Use skill:` target does not exist, when a plugin version is inconsistent across `plugin.json` and `marketplace.json` - stop and name the inconsistency. Do not silently pick one side.
- **Present tradeoffs, don't hide them.** When multiple viable approaches exist (e.g., atomic skill vs. workflow step, new skill vs. extending an existing one), state the options and the tradeoff explicitly. Let the user pick. A chosen default is acceptable, but the alternative must be named.
- **Push back when the user is likely wrong.** If a request would break a documented convention (e.g., skipping the Post-Change Checklist, mixing workflow steps into an atomic skill, using an em dash), say so before acting. Compliance without challenge produces drift.
- **Goal-driven execution with verification.** Treat each instruction as a declarative goal, not an imperative script. After every edit, verify the goal is met: re-read the changed section, check cross-references still resolve, confirm the Post-Change Checklist items are addressed. Work is not done until verified.

## Adding a New Skill

1. Create `plugins/<stack>/skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter with `name`, `description`, `metadata`, and `user-invocable`
3. For workflow skills: prefix with `task-`, set `user-invocable: true`, `type: workflow`
4. For atomic skills: set `user-invocable: false`
5. Write skill body following the content standards below
6. Update the plugin's `README.md` skill table

### Workflow Skill Contract Convention

**Every workflow skill (`task-*`) must load `Use skill: behavioral-principles` as its first workflow step, before any other delegation including `stack-detect`.** This is universal and unconditional - it applies to stack-specific workflows (e.g., `task-spring-new`), stack-agnostic workflows (e.g., `task-release-plan`, `task-db-migration-plan`), and any future workflow regardless of whether it needs stack detection. The behavioral-principles skill governs how Claude reasons throughout the workflow; it must be loaded first so the rules are in effect for every subsequent step.

Workflow skills that also adapt output to the project tech stack should load `Use skill: stack-detect` as Step 2 (immediately after behavioral-principles). Workflows that do not depend on the stack (e.g., delivery, release, database-migration-plan workflows) should skip stack-detect entirely.

### Atomic Skill Contract Convention

Atomic skills that consume stack-detect output must declare this dependency at the top of their body with a blockquote:

```markdown
> Load `Use skill: stack-detect` first to determine the project stack.
```

This signals to workflow authors that `stack-detect` must have already run before invoking this atomic skill. The consuming workflow is responsible for loading `stack-detect` - the atomic skill does not load it itself.

### Skill Content Standards

Every skill must follow these content quality standards. Skills that skip these produce weaker output.

#### Description (frontmatter)

- 1-2 sentences focused on what the skill **does** (positive framing)
- Do not list what the skill is NOT for in the description - move that to "When to Use" in the body
- Description drives skill selection in the slash menu - make it trigger-accurate

#### Required Body Sections

**Workflow skills** (`task-*`) must include:

| Section           | Purpose                                                                             |
| ----------------- | ----------------------------------------------------------------------------------- |
| **When to Use**   | Scope, constraints, and when NOT to use                                             |
| **Workflow**      | Numbered steps (STEP 1, STEP 2, ...) with `Use skill:` delegations to atomic skills |
| **Output Format** | Template showing the expected deliverable structure                                 |
| **Self-Check**    | Checkbox list of completion criteria, aligned 1:1 with workflow steps               |
| **Avoid**         | Anti-patterns and common mistakes                                                   |

**Atomic skills** must include:

| Section           | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| **When to Use**   | Usage scope                                            |
| **Rules**         | Non-negotiable constraints governing the pattern       |
| **Patterns**      | Detailed guidance with bad/good code example pairs     |
| **Output Format** | Structured contract that consuming workflows depend on |
| **Avoid**         | Domain-specific anti-patterns                          |

#### Content Quality Rules

- **Output format is a contract.** Consuming workflow skills parse atomic skill output. Use exact field names and value enums (e.g., `Blast Radius: {Narrow | Moderate | Wide | Critical}`).
- **Self-check items must match workflow steps.** Every numbered step should have a corresponding checkbox. Do not add checks for steps that do not exist.
- **Code examples use bad/good pairs.** Show the mistake immediately followed by the correct approach, both with brief explanations.
- **Tables for decision support.** Use tables for depth levels, scope options, classification criteria - anything a user needs to scan quickly.
- **Handle edge cases explicitly.** Skills must handle: missing input, unknown stack, partial information. Do not fail silently.
- **Workflow skills must delegate to all relevant atomic skills.** If an atomic skill exists for a concern the workflow touches, compose it via `Use skill:`.
- **Consistent depth across stacks.** A Python atomic skill should cover the same categories (patterns, anti-patterns, output format, avoid) as an equivalent Java skill.

## Adding a New Agent

1. Create `plugins/<stack>/agents/<agent-name>.md`
2. Follow the standard agent frontmatter schema below
3. Update the plugin's `README.md` agents table

### Agent Frontmatter Schema

All agent files use this standard frontmatter schema:

```yaml
---
name: <stack>-<role> # required: kebab-case, matches filename
description: Short description # required: shown in agent picker
category: quality | engineering | planning | ops # optional but encouraged
tools: Read, Write, Edit, Bash, Glob, Grep # optional: restrict available tools
model: sonnet | opus # optional: override default model
---
```

Minimum required: `name` and `description`. The `category`, `tools`, and `model` fields are optional but should be included when they provide meaningful constraints.

## Post-Change Checklist

After any change that affects plugin content (skills, agents, structure, conventions) - **excluding changes that only touch `CLAUDE.md` or `README.md` files** - review and update the following:

1. **`CLAUDE.md`**: Update if the change affects repository structure, conventions, naming rules, design principles, or workflow guidance documented here.
2. **Root `README.md` and affected plugin `README.md`**: Reflect any added/removed/renamed skills, agents, or structural changes.
