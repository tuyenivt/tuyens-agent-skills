# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a **Claude Code plugin marketplace repository** - a collection of agent skills and agents for Claude Code and Codex, organized by tech stack. It contains no application code; all files are Markdown skill definitions (`.md`) consumed by the Claude Code plugin system.

## Repository Structure

```
plugins/
  core/          # Stack-agnostic skills (required by all other plugins)
    skills/      # 50 skills: 22 workflow (task-*) + 28 atomic
  java/          # Java 21+ / Spring Boot 3.5+
    skills/      # 12 skills (2 workflow + 10 atomic)
    agents/      # 8 agent definitions
  dotnet/        # .NET 8 LTS / ASP.NET Core Web API, Clean Architecture
    skills/      # 11 skills (2 workflow + 9 atomic)
    agents/      # 8 agent definitions
  kotlin/        # Thin companion to java plugin (requires core + java)
  python/        # Python 3.11+ / FastAPI (primary), Django (secondary)
    agents/      # 8 agent definitions
  rails/         # Ruby on Rails 7+/8
    agents/      # 8 agent definitions
  node/          # Node.js/TypeScript, NestJS (primary), Express (secondary)
    skills/      # 10 skills (2 workflow + 8 atomic)
    agents/      # 8 agent definitions
  go/            # Go 1.25+ / Gin / GORM+sqlx
    skills/      # 9 skills (2 workflow + 7 atomic)
    agents/      # 8 agent definitions
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

- `core` is required by all language plugins
- `kotlin` requires both `core` and `java`
- All other language plugins require only `core`

## Stack Detection Pattern

Many core workflow skills begin with `Use skill: stack-detect`, which reads the consuming project's `CLAUDE.md` for a `## Tech Stack` section (key-value pairs like `Language:`, `Framework:`, `Database:`). This is the primary mechanism by which skills adapt their output to different ecosystems.

## Writing Conventions

- Always use `-` (hyphen-minus) instead of `-` (em dash) in all Markdown files.

## Key Design Principles

- **Atomic vs workflow separation**: Atomic skills are focused single-concern patterns; workflow skills (`task-*`) orchestrate them into end-to-end user-facing flows.
- **Stack-agnostic core**: The `core` plugin adapts to any detected stack - it never hardcodes framework assumptions.
- **No application code**: This repo contains only Markdown; there are no build scripts, test runners, or executables to run.
- **Composition via `Use skill:`**: Skills reference other skills using `Use skill: <skill-name>` directives in their Markdown body - this is how skill composition works at runtime.

## Adding a New Skill

1. Create `plugins/<stack>/skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter with `name`, `description`, `metadata`, and `user-invocable`
3. For workflow skills: prefix with `task-`, set `user-invocable: true`, `type: workflow`
4. For atomic skills: set `user-invocable: false`
5. Update the plugin's `README.md` skill table

## Adding a New Agent

1. Create `plugins/<stack>/agents/<agent-name>.md`
2. Update the plugin's `README.md` agents table

## Post-Change Checklist

After any change that affects plugin content (skills, agents, structure, conventions) - **excluding changes that only touch `CLAUDE.md` or `README.md` files** - review and update the following:

1. **`CLAUDE.md`**: Update if the change affects repository structure, conventions, naming rules, design principles, or workflow guidance documented here.
2. **Root `README.md` and affected plugin `README.md`**: Reflect any added/removed/renamed skills, agents, or structural changes.
3. **Version bump**: Increment the version in **all** plugins (including `core`) to the next universal version whenever any plugin has substantive changes. Update both:
   - Each plugin's `plugins/<name>/.claude-plugin/plugin.json`
   - The marketplace registry at `.claude-plugin/marketplace.json` (same version on every plugin entry)
