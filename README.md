# Tuyen's Plugins Directory

Single marketplace repository for Claude Code plugins: `architecture`, `oncall`, `java`, `python`, `ruby`, `node`, `go`, and `flutter`.

## Recommended: Project-Scoped Installation

**Install at the project (repo) level, not at the user level.**

Each project should only load the skills it actually needs. Installing all plugins globally at user scope unnecessarily bloats every Claude Code session with skills for stacks you're not using, wasting context window space and making the skill picker noisy.

The right pattern: **one marketplace add per machine, then per-project plugin installs.**

### Step 1 - Add the marketplace once (user scope, done once per machine)

```bash
claude plugin marketplace add tuyenivt/tuyens-agent-skills
```

### Step 2 - Install only the relevant plugins inside each project (project scope)

Run these commands from your project root. Claude Code will store the selection in the project's local settings, so only those skills load when you open that project.

**Java / Spring Boot project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install java@tuyens-agent-skills --scope project
```

**Python / FastAPI or Django project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install python@tuyens-agent-skills --scope project
```

**Ruby on Rails project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install ruby@tuyens-agent-skills --scope project
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

**Flutter / Dart project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install flutter@tuyens-agent-skills --scope project
```

**Architecture and delivery project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install architecture@tuyens-agent-skills --scope project
```

**On-call / Incident project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install oncall@tuyens-agent-skills --scope project
```

> `core` is always required - it provides the stack-agnostic workflow and governance skills used by all other plugins.

## How Skills Work

Each plugin contains two types of skills:

- **Workflow skills** (`task-*`, `user-invocable: true`): End-to-end task flows invoked as slash commands (e.g., `/task-code-review`). These are the skills you interact with directly.
- **Atomic skills** (`user-invocable: false`): Focused, single-concern patterns that are hidden from the slash menu. They are composed automatically by workflow skills or triggered by your prompt - you never call them directly.

> Use only workflow skills (`task-*`) as slash commands. Atomic skills run behind the scenes.

## Which Skill Do I Use?

Quick routing guide across all plugins. Find your intent and pick the right skill.

### Core Skills (all stacks)

```
I want to...
  review code (PR / AI-gen)               -> /task-code-review
  implement a feature                     -> /task-implement (dispatches to stack-specific)
  break a design into tasks / review one  -> /task-breakdown-design [architecture]
  design/review system, API, diagrams     -> /task-design-architecture [architecture]
  write tests                             -> /task-code-test
  create a PR description                 -> /task-pr-create
  write a postmortem                      -> /task-postmortem (run after root-cause) [oncall]
  hand off an on-call shift               -> /task-oncall-start [oncall]
  onboard to a codebase                   -> /task-onboard
  plan/review a database migration        -> /task-db-migration [architecture]
  decompose monolith into services        -> /task-decompose-monolith [architecture]
  consolidate over-split services         -> /task-consolidate-services [architecture]
  modernize a legacy system               -> /task-modernize-legacy [architecture]
  assess risk on a PR / change            -> /task-code-review
  check for security issues               -> /task-code-review-security
  check for performance issues            -> /task-code-review-perf
  check for observability gaps            -> /task-code-review-observability
  check for reliability gaps              -> /task-code-review-reliability
  check API contract / compatibility      -> /task-code-review-api
  assess a version upgrade                -> /task-dependency-upgrade [architecture]
  draft release notes from a diff         -> /task-release-notes [architecture]
```

### Stack-Specific Skills (language plugins)

```
Java / Spring Boot (plugin: java)
  implement a new feature              -> /task-spring-implement
  staff-level code review              -> /task-spring-review
  performance review                   -> /task-spring-review-perf
  security review                      -> /task-spring-review-security
  observability review                 -> /task-spring-review-observability
  reliability review                   -> /task-spring-review-reliability
  API-contract review                  -> /task-spring-review-api
  test strategy / scaffolds            -> /task-spring-test

Python / FastAPI / Django (plugin: python)
  implement a new feature              -> /task-python-implement
  staff-level code review              -> /task-python-review
  performance review                   -> /task-python-review-perf
  security review                      -> /task-python-review-security
  observability review                 -> /task-python-review-observability
  reliability review                   -> /task-python-review-reliability
  API-contract review                  -> /task-python-review-api
  test strategy / scaffolds            -> /task-python-test

Ruby on Rails (plugin: ruby)
  implement a new feature              -> /task-rails-implement
  staff-level code review              -> /task-rails-review
  performance review                   -> /task-rails-review-perf
  security review                      -> /task-rails-review-security
  observability review                 -> /task-rails-review-observability
  reliability review                   -> /task-rails-review-reliability
  API-contract review                  -> /task-rails-review-api
  test strategy / scaffolds            -> /task-rails-test

Node.js / TypeScript / NestJS (plugin: node)
  implement a new feature              -> /task-node-implement
  staff-level code review              -> /task-node-review
  performance review                   -> /task-node-review-perf
  security review                      -> /task-node-review-security
  observability review                 -> /task-node-review-observability
  reliability review                   -> /task-node-review-reliability
  API-contract review                  -> /task-node-review-api
  test strategy / scaffolds            -> /task-node-test

Go / Gin (plugin: go)
  implement a new feature              -> /task-go-implement
  staff-level code review              -> /task-go-review
  performance review                   -> /task-go-review-perf
  security review                      -> /task-go-review-security
  observability review                 -> /task-go-review-observability
  reliability review                   -> /task-go-review-reliability
  API-contract review                  -> /task-go-review-api
  test strategy / scaffolds            -> /task-go-test

Flutter / Dart (plugin: flutter)
  implement a new feature              -> /task-flutter-implement
  staff-level code review              -> /task-flutter-review
  performance review                   -> /task-flutter-review-perf
  security review                      -> /task-flutter-review-security
  observability review                 -> /task-flutter-review-observability
  reliability review                   -> /task-flutter-review-reliability
  test strategy / scaffolds            -> /task-flutter-test
```

> Flutter has no `review-api` counterpart: it is a client that consumes API contracts rather than designing them. Adaptivity, accessibility, and localization are handled during `/task-flutter-implement` and checked at baseline depth inside `/task-flutter-review`.

**Common decision points:**

- "Universal entry points vs stack-specific" - most `task-code-*` skills (`review`, `review-perf`, `review-security`, `review-observability`, `review-reliability`, `test`) are **thin routers**: they auto-detect your stack and dispatch to `/task-<stack>-<verb>`. Use the universal entry point if unsure; for installed language plugins, calling the stack-specific skill directly skips the routing layer. `/task-onboard` is a **composing workflow**: it remains a direct entry point and weaves a stack-specific atomic into a single output. `/task-implement` is a router (delegates to `/task-<stack>-implement`).
- "Review code" vs "Review a design" - `/task-code-review` (and stack-specific reviews) target source code and PRs, and also handle pre-merge risk analysis of a change. Architecture workflows (`/task-design-architecture`, `/task-db-migration`, `/task-dependency-upgrade`, `/task-decompose-monolith`, `/task-consolidate-services`, `/task-modernize-legacy`, `/task-breakdown-design`) each double as a review workflow for the corresponding artifact - paste an existing artifact instead of authoring requirements.
- "Design-to-tasks breakdown" vs "Architecture" - `/task-breakdown-design` turns an approved design into a phased, dependency-ordered task graph with effort sizing (or, in review mode, critiques a breakdown someone else authored). Architecture produces the design proposal itself (boundaries, failure modes). Run architecture first, then break the resulting design into tasks.
- "Root cause" vs "Postmortem" - root cause runs during or immediately after an incident. Postmortem runs after resolution to extract systemic improvements.
- "PR conflict analysis" vs "Code review" - conflict analysis detects semantic conflicts across concurrent PRs (shared schema, API, shared code). Code review evaluates a single PR for quality. Run conflict analysis before batch-merging a sprint.
- "Upgrade plan" vs "Feature implement" - upgrade plan assesses the risk and effort of a version bump and produces a Go/No-Go recommendation. Feature implement writes the migration code. Run upgrade plan first.

## Plugin Catalog

| Plugin                               | Focus                                                                                                                                                                               |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [core](plugins/core)                 | Stack-agnostic workflows, governance, ops, and review patterns                                                                                                                     |
| [architecture](plugins/architecture) | Stack-agnostic architecture, re-architecture, and delivery: unified system design (boundaries + API contracts + C4 diagrams), monolith decomposition, service consolidation, legacy modernization, DB migration, dependency upgrade, design-to-tasks breakdown (HLD/LLD -> task graph), task-breakdown review, and release notes with rollback risk register. Every design workflow doubles as a review workflow. |
| [oncall](plugins/oncall)             | Incident response: triage, investigation, root cause analysis, and postmortem                                                                                                       |
| [java](plugins/java)                 | Java 21+ / Spring Boot 3.5+                                                                                                                                                         |
| [python](plugins/python)             | Python 3.11+, FastAPI (primary), Django (secondary)                                                                                                                                 |
| [ruby](plugins/ruby)                 | Ruby on Rails 7.2+                                                                                                                                                                  |
| [node](plugins/node)                 | Node.js/TypeScript, NestJS (primary), Express (secondary)                                                                                                                           |
| [go](plugins/go)                     | Go 1.25+ / Gin                                                                                                                                                                      |
| [flutter](plugins/flutter)           | Flutter / Dart 3.x client apps - Riverpod, go_router, Dio, Drift. Mobile primary, desktop secondary, web tertiary                                                                    |

## Notes

- `core` is required by all other plugins.
- Each plugin folder has its own README with stack-specific usage and examples.

## Optional: Claude Code Settings Template

- A `settings.template.json` is provided at `.claude/settings.template.json` as a starting point for your local Claude Code settings.
- Copy it to `~/.claude/settings.json` (or merge into your existing one) to get recommended defaults for working with these plugins.

## License

This project is proprietary. All rights reserved.
