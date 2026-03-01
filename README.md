# Tuyen's Plugins Directory

Single marketplace repository for Claude Code plugins: `java`, `kotlin`, `python`, `rails`, `node`, and `go`.

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

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-core-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/core/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-java-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/java/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-kotlin-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/kotlin/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-python-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/python/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-rails-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/rails/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-node-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/node/skills"
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-go-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/go/skills"
```

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

## Notes

- `core` is required by all language plugins.
- `kotlin` is intentionally a thin companion plugin and depends on `java`.
- Each plugin folder has its own README with stack-specific usage and examples.

## License

MIT
