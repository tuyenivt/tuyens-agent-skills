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

## Plugin Catalog

| Plugin                   | Focus                                                          | Includes                                      |
| ------------------------ | -------------------------------------------------------------- | --------------------------------------------- |
| [core](plugins/core)     | Stack-agnostic workflows, governance, ops, and review patterns | 42 skills (14 workflow + 28 atomic)           |
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
