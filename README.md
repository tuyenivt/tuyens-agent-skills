# Tuyen's Plugins Directory

Single marketplace repository for Claude Code plugins: `architecture`, `delivery`, `oncall`, `spec`, `java`, `kotlin`, `python`, `rails`, `node`, `go`, `dotnet`, `rust`, `php`, `react`, `vue`, and `angular`.

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

**Spec-Driven Development (any stack, opt-in):**

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install spec@tuyens-agent-skills --scope project
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
  review code (PR / AI-gen)         -> /task-code-review
  implement a feature               -> /task-feature-implement (dispatches to stack-specific)
  fix a bug or crash                -> /task-debug (dispatches to stack-specific)
  plan and break down work          -> /task-scope-breakdown [delivery]
  fit tasks into sprints            -> /task-scope-breakdown (sprint-fit mode) [delivery]
  design a system or architecture   -> /task-design-architecture [architecture]
  design an API contract            -> /task-design-api [architecture]
  write tests                       -> /task-code-test
  create a PR description           -> /task-pr-create
  plan a production release         -> /task-release-plan [delivery]
  write a postmortem                -> /task-postmortem (run after root-cause) [oncall]
  hand off an on-call shift         -> /task-oncall-start [oncall]
  onboard to a codebase             -> /task-onboard-codebase
  understand a file or function     -> /task-code-explain
  plan a database migration         -> /task-db-migration-plan
  write documentation               -> /task-docs-generate
  refactor safely                   -> /task-code-refactor
  record an architecture decision   -> /task-adr-create [architecture]
  decompose monolith into services  -> /task-migrate-monolith-to-services [architecture]
  consolidate over-split services   -> /task-consolidate-services [architecture]
  modernize a legacy system         -> /task-modernize-legacy [architecture]
  assess risk before writing code   -> /task-design-risk-analysis [architecture]
  assess risk after writing code    -> /task-code-review
  check for security issues         -> /task-code-secure
  check for performance issues      -> /task-code-perf-review
  triage tech debt by ROI           -> /task-debt-triage [delivery]
  assess a version upgrade          -> /task-upgrade-plan [delivery]
```

### Spec-Driven Development (plugin: spec, opt-in)

```
I want to...
  set project-wide governance rules     -> /task-spec-constitution
  capture a feature's requirements      -> /task-spec-specify
  resolve ambiguities in a spec         -> /task-spec-clarify
  produce an implementation plan        -> /task-spec-plan
  break a plan into ordered tasks       -> /task-spec-tasks
  cross-check spec/plan/tasks           -> /task-spec-analyze
  audit requirements quality            -> /task-spec-checklist
  execute tasks one at a time           -> /task-spec-implement
  run multi-agent pipeline w/ fix loop  -> /task-spec-orchestrate
  score implementation against spec     -> /task-spec-evaluate
```

### Stack-Specific Skills (language plugins)

```
Java / Spring Boot (plugin: java)
  scaffold a new Spring Boot feature  -> /task-spring-new
  debug a Spring Boot issue           -> /task-spring-debug

Kotlin / Spring Boot (plugin: kotlin, requires java)
  scaffold a new Kotlin feature       -> /task-kotlin-new
  debug a Kotlin issue                -> /task-kotlin-debug

Python / FastAPI / Django (plugin: python)
  scaffold a new Python feature       -> /task-python-new
  debug a Python issue                -> /task-python-debug

Ruby on Rails (plugin: rails)
  scaffold a new Rails feature        -> /task-rails-new
  debug a Rails issue                 -> /task-rails-debug

Node.js / TypeScript / NestJS (plugin: node)
  scaffold a new Node feature         -> /task-node-new
  debug a Node issue                  -> /task-node-debug

Go / Gin (plugin: go)
  scaffold a new Go feature           -> /task-go-new
  debug a Go issue                    -> /task-go-debug

.NET / ASP.NET Core (plugin: dotnet)
  scaffold a new .NET feature         -> /task-dotnet-new
  debug a .NET issue                  -> /task-dotnet-debug

Rust / Axum (plugin: rust)
  scaffold a new Rust feature         -> /task-rust-new
  debug a Rust issue                  -> /task-rust-debug

PHP / Laravel (plugin: php)
  scaffold a new Laravel feature      -> /task-laravel-new
  debug a Laravel issue               -> /task-laravel-debug

React / Next.js (plugin: react)
  scaffold a new React feature        -> /task-react-new
  debug a React issue                 -> /task-react-debug

Vue / Nuxt (plugin: vue)
  scaffold a new Vue feature          -> /task-vue-new
  debug a Vue issue                   -> /task-vue-debug

Angular (plugin: angular)
  scaffold a new Angular feature      -> /task-angular-new
  debug an Angular issue              -> /task-angular-debug
```

**Common decision points:**

- "Implement" vs "scaffold" - `/task-feature-implement` and `/task-debug` are universal entry points that auto-detect your stack and delegate to the stack-specific skill. Use them if unsure; use the stack-specific skill directly for faster dispatch.
- "Review code" vs "Design a system" - if code already exists, use a review skill. If it doesn't, use `/task-design-architecture` or `/task-design-risk-analysis`.
- "Debug" vs "Explain" - if something is broken, use `/task-debug`. If it works but you don't understand it, use `/task-code-explain`.
- "Scope breakdown" vs "Architecture" - scope breakdown produces sprint tasks and effort sizing. Architecture produces a design proposal with boundaries and failure modes. They complement each other; run architecture first on complex features.
- "Root cause" vs "Postmortem" - root cause runs during or immediately after an incident. Postmortem runs after resolution to extract systemic improvements.
- "Risk analysis" vs "Advanced review" - risk analysis is pre-code (proposed change). Advanced review is post-code (actual diff).
- "Debt triage" vs "Code review" - debt triage ranks existing debt by blast radius, change frequency, and team pain to produce a prioritized backlog. Code review evaluates a specific PR or file for quality. Use debt triage before a planning session, not as a substitute for PR review.
- "PR conflict analysis" vs "Code review" - conflict analysis detects semantic conflicts across concurrent PRs (shared schema, API, shared code). Code review evaluates a single PR for quality. Run conflict analysis before batch-merging a sprint.
- "Upgrade plan" vs "Feature implement" - upgrade plan assesses the risk and effort of a version bump and produces a Go/No-Go recommendation. Feature implement writes the migration code. Run upgrade plan first.

## Plugin Catalog

| Plugin                               | Focus                                                                                                                                                                               | Includes                              |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| [core](plugins/core)                 | Stack-agnostic workflows, governance, ops, frontend, and review patterns                                                                                                            | 45 skills                             |
| [delivery](plugins/delivery)         | Release planning, scope breakdown, tech debt triage, dependency upgrades, PR conflicts                                                                                              | 5 skills                              |
| [architecture](plugins/architecture) | Stack-agnostic architecture design and re-architecture: system design, API design, risk analysis, ADR creation, monolith decomposition, service consolidation, legacy modernization | 10 skills                             |
| [oncall](plugins/oncall)             | Incident response: triage, investigation, root cause analysis, and postmortem                                                                                                       | 7 skills                              |
| [spec](plugins/spec)                 | Spec-Driven Development: persistent per-feature artifacts under `.specs/<slug>/` (spec, plan, tasks, analysis, evaluation), multi-agent orchestration with fix loop, opt-in scoring | 19 skills                             |
| [java](plugins/java)                 | Java 21+ / Spring Boot 3.5+                                                                                                                                                         | 12 skills + 7 agents                  |
| [kotlin](plugins/kotlin)             | Kotlin companion layer for Spring Boot projects                                                                                                                                     | 5 skills + 7 agents (requires `java`) |
| [python](plugins/python)             | Python 3.11+, FastAPI (primary), Django (secondary)                                                                                                                                 | 9 skills + 7 agents                   |
| [rails](plugins/rails)               | Ruby on Rails 7+/8                                                                                                                                                                  | 8 skills + 7 agents                   |
| [node](plugins/node)                 | Node.js/TypeScript, NestJS (primary), Express (secondary)                                                                                                                           | 10 skills + 7 agents                  |
| [go](plugins/go)                     | Go 1.25+ / Gin                                                                                                                                                                      | 9 skills + 7 agents                   |
| [dotnet](plugins/dotnet)             | .NET 8 LTS / ASP.NET Core Web API, Clean Architecture                                                                                                                               | 11 skills + 7 agents                  |
| [rust](plugins/rust)                 | Rust 1.94+ / Axum / sqlx                                                                                                                                                            | 11 skills + 7 agents                  |
| [php](plugins/php)                   | PHP 8.5 / Laravel 12+                                                                                                                                                               | 9 skills + 7 agents                   |
| [react](plugins/react)               | React 19+ / TypeScript / Next.js (primary), Vite (secondary)                                                                                                                        | 10 skills + 5 agents                  |
| [vue](plugins/vue)                   | Vue 3.5+ / TypeScript / Nuxt 3 (primary), Vite (secondary)                                                                                                                          | 11 skills + 5 agents                  |
| [angular](plugins/angular)           | Angular 21+ / TypeScript / Angular CLI                                                                                                                                              | 10 skills + 5 agents                  |

## Notes

- `core` is required by all other plugins.
- `kotlin` additionally requires `java` (thin companion plugin).
- Each plugin folder has its own README with stack-specific usage and examples.

## Optional: Claude Code Settings Template

- A `settings.template.json` is provided at `.claude/settings.template.json` as a starting point for your local Claude Code settings.
- Copy it to `~/.claude/settings.json` (or merge into your existing one) to get recommended defaults for working with these plugins.

## License

This project is proprietary. All rights reserved.
