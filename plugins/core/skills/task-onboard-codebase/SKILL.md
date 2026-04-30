---
name: task-onboard-codebase
description: Whole-codebase or large subsystem orientation for engineers new to a project. Detects stack, maps architecture and ecosystem, captures the local bootstrap and contribution workflow, extracts conventions, and surfaces risk hotspots and first-PR safe zones. Use when joining a new project, taking over an unfamiliar codebase, or doing a pre-implementation survey.
metadata:
  category: code
  tags: [onboarding, architecture, tech-debt, codebase-analysis, patterns, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Codebase Onboarding

## Purpose

Reduce engineer ramp-up from weeks to hours by producing a structured codebase map calibrated to the reader's goal:

- **Stack and tooling** - what the project is built with, in full
- **Local bootstrap** - the exact path from clone to a running app
- **Architecture map** - how the system is structured, what owns what
- **Ecosystem and runtime topology** - where the service lives, who calls it, what it calls, where to watch it
- **Key patterns and conventions** - how the team writes code here, not how you did it elsewhere
- **Contribution workflow** - branches, tests, lint hooks, CI, code owners - how a PR actually lands
- **Risk hotspots and first-PR safe zones** - what to avoid touching first, and where it is safer to start
- **Operational context** - how it runs, how it deploys, how it fails

This skill reads the codebase. It does not modify any files.

## When to Use

- First day on a new project or after joining a new team
- When taking ownership of an unfamiliar service or module
- Before making the first significant change to a codebase you don't fully know
- When conducting a due diligence or acquisition code review

## Not For

- Explaining a single file, function, class, or module - use `task-code-explain` for that (it gives deep targeted explanation with gotchas, invariants, and data flow for a specific target)
- Reviewing code quality - use `task-code-review` for that
- Architecture decision review or proposing new system designs

## Inputs

| Input             | Required | Source                                                                                 |
| ----------------- | -------- | -------------------------------------------------------------------------------------- |
| Root directory    | Yes      | Current working directory (default) or user-specified path                             |
| Repo context file | No       | Auto-read if present - primary source of declared stack and intent                     |
| Focus mode        | No       | One of `first-pr`, `architect-survey`, `full` - controls which sections are emphasized |
| Scope focus       | No       | User-specified module, service, or concern to prioritize                               |
| Known pain points | No       | User-provided areas of concern ("payments module is a problem")                        |

If the user provides a scope focus, prioritize that area but still produce the full codebase overview. If no focus is given, cover the entire repository.

**Focus mode** controls emphasis (every step still runs to gather context, but output weight shifts):

| Mode               | Audience                              | Emphasis                                                                                     |
| ------------------ | ------------------------------------- | -------------------------------------------------------------------------------------------- |
| `first-pr`         | New engineer shipping their first PR  | Local bootstrap, contribution workflow, first-PR safe zones, recommended files to read first |
| `architect-survey` | Senior engineer / due diligence       | Architecture, patterns, tech debt, structural risk - the original "map" emphasis             |
| `full` (default)   | Anyone who wants the complete picture | All sections at equal weight                                                                 |

If the user does not state a mode, default to `full` and ask once whether `first-pr` is more useful given their stated goal. Do not silently assume.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify:

- Language and version
- Primary framework(s) and secondary frameworks
- Build tool and dependency manager
- Test framework(s)
- Database(s) and ORM/query layer
- Async/messaging infrastructure (if present)
- Infrastructure-as-code or deployment tooling (if detectable)

Read the repo context file (`CLAUDE.md`, `AGENTS.md`, or `GEMINI.md` if present), plus `package.json`, `build.gradle`, `go.mod`, `pyproject.toml`, `Gemfile`, `*.csproj`, `pom.xml`, `Cargo.toml`, `mix.exs` to fill in gaps.

Also extract a **one-paragraph system summary** answering: what problem does this system solve, who uses it, and what are its 2-3 main capabilities. Pull from `README.md`, repo context file, top-level package descriptions, or service manifest. If the repo does not state this, mark as `unknown - repo does not declare purpose` rather than inferring from code.

State clearly what was detected vs what was inferred from file presence.

### Step 2 - Map Repository Structure

Explore the top-level directory layout and key subdirectories.

Identify and describe:

- **Entry points** - `main`, `app`, `server`, `index`, `Program.cs`, `Application.java`, etc.
- **Module / package layout** - how the codebase is decomposed (by domain, by layer, by feature)
- **Configuration files** - env files, secrets management, feature flags
- **Migration files** - location and tooling (Flyway, Alembic, Django, golang-migrate, etc.)
- **Test structure** - where tests live, how they are organized relative to production code
- **Infrastructure / deployment** - `Dockerfile`, `docker-compose.yml`, CI pipeline files (`.github/`, `.gitlab-ci.yml`, `Jenkinsfile`), Helm charts, Terraform

Produce a **directory map** showing the top 2-3 levels with a one-line annotation per significant directory.

Also surface, for the new engineer:

- **Where to look first** - the 2-3 directories that contain the core domain logic and are highest leverage to read early
- **Safe to skip initially** - directories that exist (vendor, generated code, legacy modules pending deprecation, large fixture trees) but are not productive starting reading material

### Step 3 - Identify Architecture Pattern

Based on the file layout, naming, key framework conventions, and detected `Stack Type`, classify the dominant architectural pattern:

**Backend patterns:**

| Pattern           | Signals                                                                        |
| ----------------- | ------------------------------------------------------------------------------ |
| Layered (MVC/MVS) | `controller/`, `service/`, `repository/` or `model/` top-level folders         |
| Clean / Hexagonal | `domain/`, `application/`, `infrastructure/`, `ports/`, `adapters/` separation |
| Modular monolith  | Feature-based top-level modules each containing their own layers               |
| Vertical slice    | Feature folders each containing controller + service + model + test            |
| Microservice      | Multiple independently deployable services with separate entry points          |
| Event-driven      | Dominant use of events/messages as primary coupling mechanism                  |

**Frontend patterns:**

| Pattern              | Signals                                                                               |
| -------------------- | ------------------------------------------------------------------------------------- |
| Feature-based        | Feature folders each containing components + hooks/composables + tests                |
| Atomic Design        | `atoms/`, `molecules/`, `organisms/`, `templates/`, `pages/` directory structure      |
| Route-based          | Pages/routes as top-level organization, shared components in separate directory       |
| Module-based         | `modules/` or `features/` directories with self-contained UI + state + API per module |
| Monolith integration | Frontend embedded within a backend framework (Rails views, Django templates, Inertia) |

State which pattern(s) are in use, with evidence (file paths, naming conventions observed).

Use skill: `architecture-guardrail` to identify any visible layer violations or boundary erosion already present.

### Step 4 - Map Key Modules and Data Flows

For each significant module or bounded context found:

- **Responsibility** - what this module does in one sentence
- **Owns** - which data entities or domain objects it is authoritative for
- **Depends on** - other modules, external services, or shared libraries it calls
- **Entry points** - controllers, consumers, scheduled jobs, CLI commands
- **Data access** - ORM entities, repositories, raw queries - what pattern is used

- **External integrations** - third-party services the system depends on (payment providers, email services, analytics, etc.), where the integration code lives, how credentials are managed, and how failures are handled

Identify the **primary request/event flow** for the most important operation in the codebase (e.g., the main user-facing action) and trace it through the layers:

```
Request → [Layer 1] → [Layer 2] → [Data store]
       ↳ [Async side effect via queue/event]
```

### Step 5 - Extract Key Patterns and Conventions

Read representative files across the codebase to extract the patterns the team actually uses. Focus on the patterns relevant to the detected `Stack Type`.

**Backend code patterns (when Stack Type is `backend` or `fullstack`):**

- How dependency injection is done (constructor, framework annotation, manual wiring)
- How errors are handled and propagated
- How logging is done (library, structured vs unstructured, correlation IDs)
- How configuration is loaded (env vars, config files, secrets manager)
- How authentication and authorization are enforced (middleware, annotations, filters)
- How database transactions are scoped
- How background jobs or async processing is handled
- How caching is implemented (library, strategy, invalidation, what is cached and what is not)
- How async/background processing is structured (task discovery, queue topology, retry configuration, monitoring)

Use skill: `backend-coding-standards` to compare observed patterns against known best practices for the detected stack. Note where the codebase follows conventions and where it diverges.

**Frontend code patterns (when Stack Type is `frontend` or `fullstack`):**

- Component architecture approach (smart/dumb split, feature components, shared UI library)
- State management strategy (local state, stores/context, URL state, server state)
- Data fetching approach (hooks/composables, server components, global fetch wrapper)
- Routing strategy (file-based, manual configuration, layouts and guards)
- Styling approach (CSS modules, Tailwind, styled-components, scoped styles, design tokens)
- Form handling patterns (validation library, submission flow, error display)
- How accessibility is addressed (semantic HTML discipline, ARIA usage, keyboard navigation)

**Test patterns to identify (all stacks):**

- Unit vs integration vs end-to-end split
- How test data is created (factories, fixtures, builders, MSW handlers)
- How external dependencies are mocked (library, approach)
- Test naming conventions

**Domain knowledge to capture (all stacks):**

- **Key concepts and terms** - domain vocabulary that recurs in code or docs (e.g., `Tenant`, `Booking`, `Ledger`); define each in one line
- **Critical invariants** - things the system must never violate (e.g., "an order's total always equals the sum of its line items", "balance must never go negative outside a tracked overdraft transaction"). Source from comments, validations, assertion-heavy tests, or explicit contracts
- **Edge cases that matter** - business edge cases visible in code (e.g., timezone handling, currency rounding, soft-delete semantics, multi-tenant isolation rules)

Cap at the 5 most load-bearing items per category. Cite the file where each is enforced.

### Step 6 - Surface Tech Debt and Risk Hotspots

Use skill: `complexity-review` to identify complexity concentrations.
Use skill: `architecture-guardrail` to detect existing boundary violations.

Scan for these signals:

**Structural debt:**

- God classes or god modules (single file/class doing many unrelated things)
- Layer violations (e.g., HTTP concerns in service layer, DB queries in controllers)
- Circular dependencies between modules
- Dead code or unused modules detectable from naming/imports

**Consistency debt:**

- Mixed architectural patterns (some modules use one style, others another)
- Multiple implementations of the same concern (e.g., two HTTP client wrappers)
- Inconsistent error handling (some throw, some return error values, some silently swallow)
- Inconsistent logging (some structured, some `System.out.println`)

**Operational debt:**

- Missing or insufficient test coverage on critical paths (inferred from test directory inspection)
- No migration rollback strategy (only `up` migrations, no `down`)
- Hardcoded configuration or secrets detectable in source
- Missing health check or liveness endpoint

**Complexity hotspots:**

- Files exceeding ~300 lines (infer from directory counts if exact count unavailable)
- Functions with deeply nested conditionals or long parameter lists
- Areas with many recent changes visible from git log (high churn = high risk)

**Common pitfalls (signals worth flagging explicitly for a new engineer):**

- Tests marked `skip`, `xit`, `@Disabled`, `t.Skip`, `pytest.mark.skip`, or named with `flaky`/`flake` - these are landmines for first-PR CI
- Modules with TODO/FIXME density above the codebase average
- Hidden side effects in module-level code (init blocks, top-level imports with side effects, package `init()` functions, framework auto-registration)
- Legacy modules pending deprecation - usually flagged in README, ADRs, or top-of-file comments
- Slow tests or slow suites (annotated with `@Tag("slow")`, `slow` markers, or excluded from default CI)

For each finding: state the location, the signal observed, and the risk it poses to someone making changes there.

### Step 7 - Operational Context

Identify how the application runs and is operated:

- **Local dev setup** - `README` instructions, `Makefile`, `docker-compose`, seed scripts
- **CI/CD pipeline** - what runs on PR (lint, test, build), what runs on merge (deploy targets)
- **Deployment model** - containers, serverless, bare metal, cloud platform (inferred from Dockerfile, IaC)
- **Environment configuration** - how dev/staging/prod configs differ (env file strategy, secrets injection)
- **Observability** - logging library and format, metrics endpoint, tracing instrumentation (if detectable)
- **Database migration strategy** - manual trigger, auto-run on startup, CI step

Use skill: `ops-observability` to assess whether the observability setup is sufficient for production operation.

### Step 8 - Local Bootstrap and Smoke Test

Reconstruct the exact path from a fresh clone to a running app. A new engineer cannot ship a first PR until this works.

Read `README.md`, `CONTRIBUTING.md`, `Makefile`, `Justfile`, `docker-compose.yml`, `.env.example`, `package.json` scripts, `bin/` directory, language-specific task files (`Rakefile`, `manage.py`, `mix.exs`, etc.) and capture:

- **Prerequisites** - language version (from `.tool-versions`, `.nvmrc`, `.python-version`, `go.mod`, `pyproject.toml`, build files), required services (DB, Redis, message broker), system tools (Docker, specific CLIs)
- **Bootstrap sequence** - the ordered command list: clone → install deps → start dependencies → run migrations → seed data → start the app. Cite the exact commands.
- **Required configuration** - which env vars must be set, where the example file is, which secrets are needed and from where (1Password, Vault, team handoff)
- **Smoke check** - how to verify the app is running (health endpoint, default port, login URL, default credentials for local)
- **Common first-run failures** - any documented gotchas (port conflicts, native deps, platform-specific build steps, Apple Silicon notes)

If a step is undocumented but clearly required (e.g., the code reads `DATABASE_URL` but no env file is shown), flag it as a documentation gap rather than inventing the value.

### Step 9 - Ecosystem and Runtime Topology

Map where the service actually lives in the wider system. Read CI configs, infrastructure-as-code, deployment manifests, observability dashboards referenced in code or README, and integration code paths.

Identify:

- **Upstream callers** - clients, sibling services, scheduled triggers, webhooks that send traffic in (from API docs, OpenAPI specs, README, request handlers, route names)
- **Downstream dependencies** - databases, caches, queues, third-party APIs, internal sibling services this service calls (from integration code, config keys, IaC service references)
- **Environments** - dev / staging / prod targets, their URLs or hostnames if discoverable from config or deployment manifests, how to reach each
- **Where to watch it** - logging destination (stdout shipped where? Datadog? CloudWatch? Loki?), metrics dashboard, tracing UI, error tracker (Sentry/Rollbar/Bugsnag), on-call alerting channel - cite paths or config keys, do not invent URLs
- **How to trace a request locally** - log format and how to find a single request's trail (correlation ID header name, request ID middleware, tracing instrumentation), and how to reproduce a real production issue against a local instance
- **Deployment platform specifics** - Kubernetes cluster/namespace, Lambda function name, ECS service, Heroku app, Vercel project (whatever the IaC or deployment files reveal)
- **Feature flags and config differences** - flag library (LaunchDarkly, Unleash, in-house), where flags are defined and read, and how dev / staging / prod configs differ (env file overlays, secrets injection, region-specific config)

State `unknown - not discoverable from the repo` for fields that the codebase does not reveal. Do not invent endpoints or dashboard URLs.

### Step 10 - Contribution Workflow

Capture the path a change takes from edit to merge. A new engineer needs to know the rules before touching code.

Read `CONTRIBUTING.md`, `.github/` (PR template, CODEOWNERS, workflows), `.gitlab/`, `.gitignore`, pre-commit configs (`.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`), lint configs, and CI files.

Identify:

- **Branching convention** - default branch, naming rules (`feature/`, `fix/`, ticket-prefix), forbidden direct pushes
- **PR requirements** - PR template fields, required reviewers via `CODEOWNERS`, required approvals, required CI checks before merge
- **Local quality gates** - pre-commit hooks, linters, formatters that will reject the PR if skipped; the commands to run them locally
- **Test commands** - the exact command to run unit tests, integration tests, the full test suite, and a single test file (cite from `package.json` scripts, Makefile targets, language conventions)
- **CI pipeline shape** - what runs on PR open, what runs on merge to main, approximate stages (lint → test → build → deploy); flag if CI is slow or known-flaky from README or comments
- **Module owners** - top contributors per area from `CODEOWNERS` and, where helpful, recent committers (read-only `git log`/`git shortlog` is acceptable)
- **Communication channels** - Slack/Teams channels, mailing lists, or office-hours referenced in `README.md`, `CONTRIBUTING.md`, or `CODEOWNERS` comments - cite the source, do not invent channel names
- **What usually gets PRs rejected here** - patterns visible in `CONTRIBUTING.md`, PR template checkboxes, lint configs, or comments in recent merged PRs (e.g., "missing changelog entry", "no test coverage on critical path", "schema change without migration"). Cite source.
- **Reference example PRs** - if `README.md`, `CONTRIBUTING.md`, or PR template links to canonical "good" example PRs, capture them. Otherwise omit - do not invent PR numbers.
- **First-PR safe zones** - cross-reference Step 6 risk hotspots: list 2-3 areas that are well-tested, low-churn, and low-blast-radius - good candidates for a first change. List 2-3 areas to avoid touching first.

Use skill: `dependency-impact-analysis` when the user names a candidate first-PR area to estimate its blast radius before they commit to it.

## Output Format

```markdown
# Codebase Onboarding Report

## System Summary

[One paragraph: what problem this system solves, who uses it, 2-3 main capabilities. Mark `unknown - repo does not declare purpose` if not stated anywhere.]

## Stack

| Concern    | Technology                      | Confidence        |
| ---------- | ------------------------------- | ----------------- |
| Language   | [e.g., Go 1.25]                 | Declared/Inferred |
| Framework  | [e.g., Gin + GORM]              | Declared/Inferred |
| Build      | [e.g., Go modules]              | Inferred          |
| Test       | [e.g., testify + mockery]       | Inferred          |
| Database   | [e.g., PostgreSQL via GORM]     | Inferred          |
| Async/Jobs | [e.g., Asynq (Redis)]           | Inferred          |
| Deployment | [e.g., Docker + GitHub Actions] | Inferred          |

## Repository Structure
```

[directory map - top 2-3 levels with one-line annotations]

```

## Architecture

**Pattern:** [Layered / Clean / Modular monolith / Vertical slice / Microservice / Event-driven]
**Evidence:** [2-3 file paths or naming observations that support this classification]

### Modules

| Module        | Responsibility       | Data Owned    | Key Dependencies        |
| ------------- | -------------------- | ------------- | ----------------------- |
| [name]        | [one sentence]       | [entities]    | [modules / services]    |

### Primary Flow

```

[Trace the main request/event through the system layers]

```

## Key Patterns and Conventions

### How This Codebase Does Things

| Concern           | Pattern Observed                                | Location Example         |
| ----------------- | ----------------------------------------------- | ------------------------ |
| DI                | [e.g., constructor injection via wire]          | [file path]              |
| Error handling    | [e.g., wrapped errors with fmt.Errorf %w]       | [file path]              |
| Logging           | [e.g., slog structured, request-scoped]         | [file path]              |
| Config            | [e.g., viper + env vars, no hardcoding]         | [file path]              |
| Auth              | [e.g., JWT middleware on Gin router groups]     | [file path]              |
| Transactions      | [e.g., GORM WithContext transaction]            | [file path]              |
| Background jobs   | [e.g., Asynq workers in internal/worker/]       | [file path]              |
| Components        | [e.g., feature-based, smart/dumb split]         | [file path]              |
| State management  | [e.g., Zustand stores, local useState]          | [file path]              |
| Data fetching     | [e.g., TanStack Query with MSW for testing]     | [file path]              |
| Routing           | [e.g., Next.js App Router, file-based]          | [file path]              |
| Styling           | [e.g., Tailwind CSS with design tokens]         | [file path]              |
| Tests             | [e.g., table-driven, mockery mocks]             | [file path]              |

_Include only rows relevant to the detected Stack Type. Omit backend rows for frontend-only projects and vice versa._

## Domain Knowledge

### Key Concepts

| Term       | Definition (one line)        | Defined / Enforced In |
| ---------- | ---------------------------- | --------------------- |
| [name]     | [meaning in this codebase]   | [file path]           |

### Critical Invariants

| Invariant                                       | Enforced In           |
| ----------------------------------------------- | --------------------- |
| [must-never-violate rule]                       | [file path]           |

### Edge Cases That Matter

- **[Case]**: [what makes it tricky] - [file path]

_Cap each table at 5 most load-bearing items. Omit any subsection if nothing meaningful was found._

## Where to Look First

| Priority | Path             | Why read this early                                          |
| -------- | ---------------- | ------------------------------------------------------------ |
| 1        | [path]           | [core domain logic / primary flow entry point / etc.]        |
| 2        | [path]           | [reason]                                                     |

**Safe to skip initially:** [vendored deps, generated code, large fixtures, deprecated modules - cite paths]

## Tech Debt and Risk Hotspots

### [High | Medium | Low] - [Short label]

- **Location:** [file or module path]
- **Signal:** [what was observed]
- **Risk:** [what breaks or becomes harder if you change this area]

[Repeat per finding, ordered High → Medium → Low]

## Common Pitfalls

Short list of landmines a new engineer should know about before their first PR runs through CI:

- **Skipped or flaky tests**: [paths or test names + the marker used (`@Disabled`, `xit`, etc.)]
- **Hidden side effects**: [module-level init, package `init()`, framework auto-registration paths]
- **Legacy / deprecated modules**: [paths flagged for removal]
- **Slow tests**: [paths or tags + how they are excluded from default CI]
- **Other gotchas documented in `README` / `CONTRIBUTING`**: [cite source]

## Operational Context

| Concern            | Details                                      |
| ------------------ | -------------------------------------------- |
| Local setup        | [how to run locally - summary, full detail in Local Quickstart] |
| CI on PR           | [what runs]                                  |
| Deploy target      | [platform / mechanism]                       |
| Config management  | [strategy]                                   |
| Observability      | [logging/metrics/tracing setup]              |
| Migration strategy | [how and when migrations run]                |

## Local Quickstart

**Prerequisites:** [language version + required services + system tools, citing source files like `.tool-versions`, `docker-compose.yml`]

**Bootstrap (in order):**

```

[exact command 1 - e.g., cp .env.example .env]
[exact command 2 - e.g., docker-compose up -d postgres redis]
[exact command 3 - e.g., make migrate]
[exact command 4 - e.g., make seed]
[exact command 5 - e.g., make dev]

```

**Required env vars:** [list, with example values or source - flag any missing from .env.example]

**Smoke check:** [how to verify - e.g., `curl localhost:3000/health` returns 200; default login user/pass for local]

**Known first-run gotchas:** [platform-specific notes, port conflicts, native deps - omit section if none documented]

## Ecosystem and Runtime Topology

| Concern               | Details                                                           |
| --------------------- | ----------------------------------------------------------------- |
| Upstream callers      | [who sends traffic in]                                            |
| Downstream services   | [DBs, caches, queues, third-party APIs, sibling services]         |
| Environments          | [dev / staging / prod targets if discoverable, else `unknown`]    |
| Logs                  | [destination + how to access]                                     |
| Metrics / dashboards  | [tool + paths/keys cited; `unknown` if not discoverable]          |
| Tracing               | [tool / instrumentation]                                          |
| Trace a request       | [correlation ID header, request-ID middleware, tracing setup]     |
| Reproduce locally     | [steps to replay a prod issue against local instance]             |
| Error tracking        | [Sentry/Rollbar/etc. + DSN config key]                            |
| Deployment platform   | [k8s cluster/namespace, Lambda name, ECS service, Heroku app...]  |
| Feature flags         | [library + where flags are defined and read]                      |
| Env config diffs      | [how dev / staging / prod configs differ; secrets injection]      |
| On-call / alerting    | [channel or runbook reference, if any]                            |

## Contribution Workflow

| Concern             | Details                                                                |
| ------------------- | ---------------------------------------------------------------------- |
| Default branch      | [main / master / trunk]                                                |
| Branch naming       | [convention, with examples]                                            |
| PR requirements     | [template fields, required reviewers, required checks]                 |
| CODEOWNERS          | [path or `none`; cite a few owner mappings]                            |
| Local quality gates | [pre-commit / hooks / formatters - the exact commands]                 |
| Test commands       | [unit / integration / full suite / single file - exact commands]       |
| CI pipeline         | [stages on PR open vs merge; known slowness/flake notes]               |
| Channels            | [Slack/Teams channel, mailing list - cite source or `none documented`] |
| Common rejection reasons | [what gets PRs sent back here; cite source]                       |
| Reference example PRs | [linked from README/CONTRIBUTING/PR template, or `none cited`]       |

### First-PR Safe Zones

| Area      | Why safe                                  | Suggested entry file |
| --------- | ----------------------------------------- | -------------------- |
| [path]    | [well-tested, low churn, narrow blast]    | [file path]          |

### Avoid for First PR

| Area      | Why to wait                                          |
| --------- | ---------------------------------------------------- |
| [path]    | [high churn / wide blast / weak tests / unowned]     |

## Onboarding Recommendations

Tailor depth to the requested `Focus` mode. In `first-pr` mode, lead with Mission Framing + First-PR Playbook; in `architect-survey` mode, lead with First-Week Knowledge Gaps; in `full` mode, include all subsections.

### Mission Framing (first-pr mode)

What counts as a valid first PR in this codebase:

- **Realistic targets**: [e.g., small bug fix in low-churn module, logging improvement, missing test, config tweak] - grounded in observed safe zones
- **Suggested timeline**: [e.g., "open PR within 2-3 days of finished local setup"] - based on CI duration and review cadence observed
- **What a "good" first PR looks like here**: [cite reference example PRs if available; otherwise describe expected size and shape]

### First-PR Playbook (first-pr mode)

Step-by-step path tying the report's findings together:

1. Run the project locally (see Local Quickstart) and confirm the smoke check passes
2. Pick a candidate task from First-PR Safe Zones; verify ownership against CODEOWNERS
3. Reproduce the existing behavior (run the relevant tests, hit the relevant endpoint or screen)
4. Trace the code path end to end using the patterns in Key Patterns and Conventions
5. Make the minimal change and add or adjust tests in the project's existing style
6. Run local quality gates (lint, format, full test suite) using the exact Contribution Workflow commands
7. Open the PR using the project's PR template; tag the right CODEOWNERS; address Common Rejection Reasons proactively

### First-Day Checklist (action-oriented, ship-ready)

1-5 concrete actions to get a working local environment and PR-ready setup:

- **[Action]**: [exact command or file to read; expected outcome]

### First-Week Knowledge Gaps (deeper learning)

1-5 areas of the codebase a new engineer should study before taking on broader work:

- **[Topic]**: [why it matters; suggested reading path - files, modules, or docs]

## Summary

3-5 bullets covering:
- Architectural strengths (what the codebase does well)
- Primary risk areas (where to be careful)
- Recommended first-PR target (if `Focus: first-pr` was requested)
- Biggest knowledge gaps to close in the first week
```

### Output Constraints

- Stack table must distinguish declared (from repo context file) from inferred (from file presence)
- Architecture classification must cite specific file paths as evidence - no guessing
- Patterns table must cite a real file path for each pattern - not invented examples
- Local Quickstart commands must be cited from real files (`Makefile`, `package.json`, `README`, etc.) - never invented
- System Summary must be cited from `README.md` or repo context file; mark `unknown - repo does not declare purpose` if not stated
- Ecosystem fields that the repo does not reveal must be marked `unknown - not discoverable from the repo`, never invented URLs
- Domain Knowledge tables capped at 5 items each; each entry cites the file where the concept or invariant is enforced
- Communication channels and reference example PRs must cite the source file or be marked `none cited` - never invented
- Tech debt findings ordered High → Medium → Low
- First-PR Safe Zones and Avoid lists each capped at 3 items
- First-PR Playbook is included only in `first-pr` and `full` modes; omit in `architect-survey` mode
- First-Day Checklist and First-Week Knowledge Gaps each limited to 5 items - prioritize ruthlessly
- Omit any section where nothing meaningful was found, including First-PR sections in `architect-survey` mode if the user did not request them
- Do not comment on code style or formatting in tech debt - focus on structural and operational risk
- Total output should be comprehensive but scannable - use tables over prose wherever possible

## Rules

- Read files, do not modify them
- Never invent file paths or module names - only report what is observed
- If a directory or file cannot be read, note it and continue
- If the codebase is monorepo with multiple services, scope the report to the service the user is focused on, then note other services exist
- Do not generate code, refactoring plans, or migration plans - produce a map, not a roadmap

## Self-Check

- [ ] Focus mode acknowledged (`first-pr`, `architect-survey`, or `full`); section emphasis matches
- [ ] System Summary captured (or marked unknown); cites source
- [ ] Stack table distinguishes declared (from repo context file) from inferred (from file presence)
- [ ] Repository structure includes "Where to Look First" and "Safe to Skip Initially"
- [ ] Architecture classification cites specific file paths as evidence
- [ ] Patterns table references real file paths for each observed pattern
- [ ] Domain Knowledge captured: key concepts, critical invariants, edge cases - each cited
- [ ] Local Quickstart commands cited from real files; missing prerequisites flagged as documentation gaps
- [ ] Ecosystem unknowns marked `unknown - not discoverable from the repo` rather than invented; trace-a-request and feature-flag rows present or omitted with reason
- [ ] Contribution Workflow includes exact test commands, local quality gates, channels, rejection reasons, and example PRs (or `none cited`)
- [ ] Common Pitfalls section flags skipped/flaky tests and module-level side effects with concrete locations
- [ ] First-PR Safe Zones and Avoid lists each have 1-3 entries with concrete reasoning
- [ ] Tech debt findings ordered High → Medium → Low with concrete locations
- [ ] In `first-pr` or `full` mode: Mission Framing and First-PR Playbook present
- [ ] First-Day Checklist and First-Week Knowledge Gaps each limited to 5 items
- [ ] No invented file paths, module names, commands, URLs, channels, PR numbers, or pattern examples

## Avoid

- Inventing file paths, module names, commands, env var values, or dashboard/environment URLs not observed in the codebase
- Commenting on code style or formatting as tech debt - focus on structural and operational risk
- Generating refactoring plans or migration strategies (this produces a map, not a roadmap)
- Over-exploring irrelevant directories (vendor, node_modules, build output)
- Producing an exhaustive inventory instead of a scannable summary
- Recommending a candidate first-PR area without cross-referencing risk hotspots and CODEOWNERS
- Skipping the Focus question when the user's stated goal clearly implies one mode (e.g., "I need to ship my first PR") - confirm the mode rather than defaulting silently
