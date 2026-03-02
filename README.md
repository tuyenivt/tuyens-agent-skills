# Tuyen's Plugins Directory

Single marketplace repository for Claude Code plugins: `java`, `kotlin`, `python`, `rails`, `node`, `go`, and `dotnet`.

## Add Marketplace

```bash
/plugin marketplace add tuyenivt/tuyens-agent-skills
```

## Installation Order

Install plugins in dependency order:

```bash
/plugin install core@tuyens-agent-skills
```

Then install one or more stack plugins:

```bash
/plugin install java@tuyens-agent-skills
/plugin install kotlin@tuyens-agent-skills   # requires core + java
/plugin install python@tuyens-agent-skills
/plugin install rails@tuyens-agent-skills
/plugin install node@tuyens-agent-skills
/plugin install go@tuyens-agent-skills
/plugin install dotnet@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/core/skills" "$HOME/.codex/skills/tuyens-agent-skills-core-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/java/skills" "$HOME/.codex/skills/tuyens-agent-skills-java-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/kotlin/skills" "$HOME/.codex/skills/tuyens-agent-skills-kotlin-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/python/skills" "$HOME/.codex/skills/tuyens-agent-skills-python-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/rails/skills" "$HOME/.codex/skills/tuyens-agent-skills-rails-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/node/skills" "$HOME/.codex/skills/tuyens-agent-skills-node-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/go/skills" "$HOME/.codex/skills/tuyens-agent-skills-go-skills"
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/dotnet/skills" "$HOME/.codex/skills/tuyens-agent-skills-dotnet-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-core-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/core/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-java-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/java/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-kotlin-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/kotlin/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-python-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/python/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-rails-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/rails/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-node-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/node/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-go-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/go/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-dotnet-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/dotnet/skills"
```

## How Skills Work

Each plugin contains two types of skills:

- **Workflow skills** (`task-*`, `user-invocable: true`): End-to-end task flows invoked as slash commands (e.g., `/task-code-review`). These are the skills you interact with directly.
- **Atomic skills** (`user-invocable: false`): Focused, single-concern patterns that are hidden from the slash menu. They are composed automatically by workflow skills or triggered by your prompt — you never call them directly.

> Use only workflow skills (`task-*`) as slash commands. Atomic skills run behind the scenes.

## Plugin Catalog

| Plugin                   | Focus                                                          | Includes                                      |
| ------------------------ | -------------------------------------------------------------- | --------------------------------------------- |
| [core](plugins/core)     | Stack-agnostic workflows, governance, ops, and review patterns | 41 skills (13 workflow + 28 atomic)           |
| [java](plugins/java)     | Java 21+ / Spring Boot 3.5+                                    | 12 skills + 8 agents                          |
| [kotlin](plugins/kotlin) | Kotlin companion layer for Spring Boot projects                | 5 skills + 1 agent (requires `core` + `java`) |
| [python](plugins/python) | Python 3.11+, FastAPI (primary), Django (secondary)            | 10 skills + 3 agents                          |
| [rails](plugins/rails)   | Ruby on Rails 7+/8                                             | 9 skills + 3 agents                           |
| [node](plugins/node)     | Node.js/TypeScript, NestJS (primary), Express (secondary)      | 10 skills + 3 agents                          |
| [go](plugins/go)         | Go 1.25+ / Gin                                                 | 9 skills + 3 agents                           |
| [dotnet](plugins/dotnet) | .NET 8 LTS / ASP.NET Core Web API, Clean Architecture          | 11 skills + 8 agents                          |

## Notes

- `core` is required by all language plugins.
- `kotlin` is intentionally a thin companion plugin and depends on `java`.
- Each plugin folder has its own README with stack-specific usage and examples.

## Optional: Claude Code Settings Template

- A `settings.template.json` is provided at `.claude/settings.template.json` as a starting point for your local Claude Code settings.
- Copy it to `~/.claude/settings.json` (or merge into your existing one) to get recommended defaults for working with these plugins.

## License

MIT
