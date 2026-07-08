# Tuyen's Plugins Directory

Single marketplace repository for Claude Code plugins: `architecture`, `delivery`, `oncall`, `java`, `kotlin`, `python`, `ruby`, `node`, `go`, `dotnet`, `rust`, `php`, `react`, `vue`, and `angular`.

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

**Kotlin / Spring Boot project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
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

**.NET / ASP.NET Core project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install dotnet@tuyens-agent-skills --scope project
```

**Rust project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install rust@tuyens-agent-skills --scope project
```

**PHP / Laravel project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install php@tuyens-agent-skills --scope project
```

**React / Next.js project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install react@tuyens-agent-skills --scope project
```

**Vue / Nuxt project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install vue@tuyens-agent-skills --scope project
```

**Angular project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install angular@tuyens-agent-skills --scope project
```

**Architecture project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install architecture@tuyens-agent-skills --scope project
```

**Delivery project:**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install delivery@tuyens-agent-skills --scope project
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
  fix a bug or crash                      -> /task-code-debug (dispatches to stack-specific)
  break a design (HLD/LLD) into tasks     -> /task-breakdown-design [delivery]
  review a task breakdown                 -> /task-breakdown-review [delivery]
  design/review system, API, diagrams     -> /task-design-architecture [architecture]
  write tests                             -> /task-code-test
  create a PR description                 -> /task-pr-create
  write a postmortem                      -> /task-postmortem (run after root-cause) [oncall]
  hand off an on-call shift               -> /task-oncall-start [oncall]
  onboard to a codebase                   -> /task-onboard
  understand a file or function           -> /task-code-explain
  plan/review a database migration        -> /task-db-migration [architecture]
  refactor safely                         -> /task-code-refactor
  decompose monolith into services        -> /task-decompose-monolith [architecture]
  consolidate over-split services         -> /task-consolidate-services [architecture]
  modernize a legacy system               -> /task-modernize-legacy [architecture]
  assess risk on a PR / change            -> /task-code-review
  check for security issues               -> /task-code-review-security
  check for performance issues            -> /task-code-review-perf
  check for observability gaps            -> /task-code-review-observability
  assess a version upgrade                -> /task-dependency-upgrade [architecture]
  draft release notes from a diff         -> /task-release-notes [delivery]
```

### Stack-Specific Skills (language plugins)

```
Java / Spring Boot (plugin: java)
  implement a new feature              -> /task-spring-implement
  debug an issue                       -> /task-spring-debug
  staff-level code review              -> /task-spring-review
  performance review                   -> /task-spring-review-perf
  security review                      -> /task-spring-review-security
  observability review                 -> /task-spring-review-observability
  test strategy / scaffolds            -> /task-spring-test
  refactor plan                        -> /task-spring-refactor

Kotlin / Spring Boot (plugin: kotlin)
  implement a new feature              -> /task-kotlin-implement
  debug an issue                       -> /task-kotlin-debug
  staff-level code review              -> /task-kotlin-review
  performance review                   -> /task-kotlin-review-perf
  security review                      -> /task-kotlin-review-security
  observability review                 -> /task-kotlin-review-observability
  test strategy / scaffolds            -> /task-kotlin-test
  refactor plan                        -> /task-kotlin-refactor

Python / FastAPI / Django (plugin: python)
  implement a new feature              -> /task-python-implement
  debug an issue                       -> /task-python-debug
  staff-level code review              -> /task-python-review
  performance review                   -> /task-python-review-perf
  security review                      -> /task-python-review-security
  observability review                 -> /task-python-review-observability
  test strategy / scaffolds            -> /task-python-test
  refactor plan                        -> /task-python-refactor

Ruby on Rails (plugin: ruby)
  implement a new feature              -> /task-rails-implement
  debug an issue                       -> /task-rails-debug
  staff-level code review              -> /task-rails-review
  performance review                   -> /task-rails-review-perf
  security review                      -> /task-rails-review-security
  observability review                 -> /task-rails-review-observability
  test strategy / scaffolds            -> /task-rails-test
  refactor plan                        -> /task-rails-refactor

Node.js / TypeScript / NestJS (plugin: node)
  implement a new feature              -> /task-node-implement
  debug an issue                       -> /task-node-debug
  staff-level code review              -> /task-node-review
  performance review                   -> /task-node-review-perf
  security review                      -> /task-node-review-security
  observability review                 -> /task-node-review-observability
  test strategy / scaffolds            -> /task-node-test
  refactor plan                        -> /task-node-refactor

Go / Gin (plugin: go)
  implement a new feature              -> /task-go-implement
  debug an issue                       -> /task-go-debug
  staff-level code review              -> /task-go-review
  performance review                   -> /task-go-review-perf
  security review                      -> /task-go-review-security
  observability review                 -> /task-go-review-observability
  test strategy / scaffolds            -> /task-go-test
  refactor plan                        -> /task-go-refactor

.NET / ASP.NET Core (plugin: dotnet)
  implement a new feature              -> /task-dotnet-implement
  debug an issue                       -> /task-dotnet-debug
  staff-level code review              -> /task-dotnet-review
  performance review                   -> /task-dotnet-review-perf
  security review                      -> /task-dotnet-review-security
  observability review                 -> /task-dotnet-review-observability
  test strategy / scaffolds            -> /task-dotnet-test
  refactor plan                        -> /task-dotnet-refactor

Rust / Axum (plugin: rust)
  implement a new feature              -> /task-rust-implement
  debug an issue                       -> /task-rust-debug
  staff-level code review              -> /task-rust-review
  performance review                   -> /task-rust-review-perf
  security review                      -> /task-rust-review-security
  observability review                 -> /task-rust-review-observability
  test strategy / scaffolds            -> /task-rust-test
  refactor plan                        -> /task-rust-refactor

PHP / Laravel (plugin: php)
  implement a new feature              -> /task-laravel-implement
  debug an issue                       -> /task-laravel-debug
  staff-level code review              -> /task-laravel-review
  performance review                   -> /task-laravel-review-perf
  security review                      -> /task-laravel-review-security
  observability review                 -> /task-laravel-review-observability
  test strategy / scaffolds            -> /task-laravel-test
  refactor plan                        -> /task-laravel-refactor

React / Next.js (plugin: react)
  implement a new feature              -> /task-react-implement
  debug an issue                       -> /task-react-debug
  staff-level code review              -> /task-react-review
  performance review                   -> /task-react-review-perf
  security review                      -> /task-react-review-security
  observability review                 -> /task-react-review-observability
  test strategy / coverage / scaffolds -> /task-react-test
  refactor plan                        -> /task-react-refactor

Vue / Nuxt (plugin: vue)
  implement a new feature              -> /task-vue-implement
  debug an issue                       -> /task-vue-debug
  staff-level code review              -> /task-vue-review
  performance review                   -> /task-vue-review-perf
  security review                      -> /task-vue-review-security
  observability review                 -> /task-vue-review-observability
  test strategy / coverage / scaffolds -> /task-vue-test
  refactor plan                        -> /task-vue-refactor

Angular (plugin: angular)
  implement a new feature              -> /task-angular-implement
  debug an issue                       -> /task-angular-debug
  staff-level code review              -> /task-angular-review
  performance review                   -> /task-angular-review-perf
  security review                      -> /task-angular-review-security
  observability review                 -> /task-angular-review-observability
  test strategy / coverage / scaffolds -> /task-angular-test
  refactor plan                        -> /task-angular-refactor
```

**Common decision points:**

- "Universal entry points vs stack-specific" - most `task-code-*` skills (`debug`, `refactor`, `review`, `review-perf`, `review-security`, `review-observability`, `test`) are **thin routers**: they auto-detect your stack and dispatch to `/task-<stack>-<verb>`. Use the universal entry point if unsure; for installed language plugins, calling the stack-specific skill directly skips the routing layer. `/task-code-explain` and `/task-onboard` are **composing workflows**: they remain direct entry points and weave a stack-specific atomic into a single output. `/task-implement` is a router (delegates to `/task-<stack>-implement`).
- "Review code" vs "Review a design" - `/task-code-review` (and stack-specific reviews) target source code and PRs, and also handle pre-merge risk analysis of a change. Architecture workflows (`/task-design-architecture`, `/task-db-migration`, `/task-dependency-upgrade`, `/task-decompose-monolith`, `/task-consolidate-services`, `/task-modernize-legacy`) each double as a review workflow for the corresponding design artifact - paste an existing artifact instead of authoring requirements.
- "Debug" vs "Explain" - if something is broken, use `/task-code-debug`. If it works but you don't understand it, use `/task-code-explain`.
- "Design-to-tasks breakdown" vs "Architecture" - `/task-breakdown-design` turns an approved design into a phased, dependency-ordered task graph with effort sizing. Architecture produces the design proposal itself (boundaries, failure modes). Run architecture first, then break the resulting design into tasks.
- "Root cause" vs "Postmortem" - root cause runs during or immediately after an incident. Postmortem runs after resolution to extract systemic improvements.
- "PR conflict analysis" vs "Code review" - conflict analysis detects semantic conflicts across concurrent PRs (shared schema, API, shared code). Code review evaluates a single PR for quality. Run conflict analysis before batch-merging a sprint.
- "Upgrade plan" vs "Feature implement" - upgrade plan assesses the risk and effort of a version bump and produces a Go/No-Go recommendation. Feature implement writes the migration code. Run upgrade plan first.

## Plugin Catalog

| Plugin                               | Focus                                                                                                                                                                               |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [core](plugins/core)                 | Stack-agnostic workflows, governance, ops, frontend, and review patterns                                                                                                            |
| [delivery](plugins/delivery)         | Design-to-tasks breakdown (HLD/LLD -> task graph), task-breakdown review, release notes with rollback risk register                                                                  |
| [architecture](plugins/architecture) | Stack-agnostic architecture design and re-architecture: unified system design (boundaries + API contracts + C4 diagrams), monolith decomposition, service consolidation, legacy modernization, DB migration, dependency upgrade. Every workflow doubles as a review workflow. |
| [oncall](plugins/oncall)             | Incident response: triage, investigation, root cause analysis, and postmortem                                                                                                       |
| [java](plugins/java)                 | Java 21+ / Spring Boot 3.5+                                                                                                                                                         |
| [kotlin](plugins/kotlin)             | Kotlin 2.0+ / Spring Boot 3.5+                                                                                                                 |
| [python](plugins/python)             | Python 3.11+, FastAPI (primary), Django (secondary)                                                                                                                                 |
| [ruby](plugins/ruby)                 | Ruby on Rails 7.2+                                                                                                                                                                  |
| [node](plugins/node)                 | Node.js/TypeScript, NestJS (primary), Express (secondary)                                                                                                                           |
| [go](plugins/go)                     | Go 1.25+ / Gin                                                                                                                                                                      |
| [dotnet](plugins/dotnet)             | .NET 8 LTS / ASP.NET Core Web API, Clean Architecture                                                                                                                               |
| [rust](plugins/rust)                 | Rust 1.94+ / Axum / sqlx                                                                                                                                                            |
| [php](plugins/php)                   | PHP 8.5 / Laravel 12+                                                                                                                                                               |
| [react](plugins/react)               | React 18+ (React 19 hooks) / TypeScript / Next.js 15 App Router (primary), Vite 5+ (secondary)                                                                                      |
| [vue](plugins/vue)                   | Vue 3.5+ / TypeScript / Nuxt 3 (primary), Vite (secondary)                                                                                                                          |
| [angular](plugins/angular)           | Angular 21+ / TypeScript / Angular CLI                                                                                                                                              |

## Notes

- `core` is required by all other plugins.
- Each plugin folder has its own README with stack-specific usage and examples.

## Optional: Claude Code Settings Template

- A `settings.template.json` is provided at `.claude/settings.template.json` as a starting point for your local Claude Code settings.
- Copy it to `~/.claude/settings.json` (or merge into your existing one) to get recommended defaults for working with these plugins.

## License

This project is proprietary. All rights reserved.
