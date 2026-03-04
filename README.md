# Tuyen's Plugins Directory

Single marketplace repository for Claude Code plugins: `java`, `kotlin`, `python`, `rails`, `node`, `go`, and `dotnet`.

## Recommended: Project-Scoped Installation

**Install at the project (repo) level, not at the user level.**

Each project should only load the skills it actually needs. Installing all plugins globally at user scope unnecessarily bloats every Claude Code session with skills for stacks you're not using, wasting context window space and making the skill picker noisy.

The right pattern: **one marketplace add per machine, then per-project plugin installs.**

### Step 1 — Add the marketplace once (user scope, done once per machine)

```bash
claude plugin marketplace add tuyenivt/tuyens-agent-skills
```

### Step 2 — Install only the relevant plugins inside each project (project scope)

Run these commands from your project root. Claude Code will store the selection in the project's local settings, so only those skills load when you open that project.

**Java / Spring Boot project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install java@tuyens-agent-skills --scope project
```

**Kotlin / Spring Boot project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install java@tuyens-agent-skills --scope project
claude plugin install kotlin@tuyens-agent-skills --scope project
```

**Python / FastAPI or Django project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install python@tuyens-agent-skills --scope project
```

**Ruby on Rails project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install rails@tuyens-agent-skills --scope project
```

**Node.js / TypeScript project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install node@tuyens-agent-skills --scope project
```

**Go project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install go@tuyens-agent-skills --scope project
```

**.NET / ASP.NET Core project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install dotnet@tuyens-agent-skills --scope project
```

> `core` is always required — it provides the stack-agnostic workflow and governance skills used by all language plugins.

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

| Plugin                   | Focus                                                          | Includes                             |
| ------------------------ | -------------------------------------------------------------- | ------------------------------------ |
| [core](plugins/core)     | Stack-agnostic workflows, governance, ops, and review patterns | 41 skills                            |
| [java](plugins/java)     | Java 21+ / Spring Boot 3.5+                                    | 11 skills + 8 agents                 |
| [kotlin](plugins/kotlin) | Kotlin companion layer for Spring Boot projects                | 5 skills + 1 agent (requires `java`) |
| [python](plugins/python) | Python 3.11+, FastAPI (primary), Django (secondary)            | 9 skills + 3 agents                  |
| [rails](plugins/rails)   | Ruby on Rails 7+/8                                             | 8 skills + 3 agents                  |
| [node](plugins/node)     | Node.js/TypeScript, NestJS (primary), Express (secondary)      | 9 skills + 3 agents                  |
| [go](plugins/go)         | Go 1.25+ / Gin                                                 | 8 skills + 3 agents                  |
| [dotnet](plugins/dotnet) | .NET 8 LTS / ASP.NET Core Web API, Clean Architecture          | 11 skills + 8 agents                 |

## Notes

- `core` is required by all language plugins.
- `kotlin` is intentionally a thin companion plugin and depends on `java`.
- Each plugin folder has its own README with stack-specific usage and examples.

## Optional: Claude Code Settings Template

- A `settings.template.json` is provided at `.claude/settings.template.json` as a starting point for your local Claude Code settings.
- Copy it to `~/.claude/settings.json` (or merge into your existing one) to get recommended defaults for working with these plugins.

## License

MIT
