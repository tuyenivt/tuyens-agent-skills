---
name: task-onboard-codebase
description: Senior engineer onboarding to a whole codebase or large subsystem. Detects stack, maps architecture, identifies key patterns and conventions, surfaces tech debt and risk hotspots. Not for explaining a single file or function - use task-code-explain for that.
metadata:
  category: workflow
  tags: [onboarding, architecture, tech-debt, codebase-analysis, patterns, multi-stack]
  type: workflow
user-invocable: true
---

# Codebase Onboarding - Senior Edition

## Purpose

Reduce senior engineer ramp-up from weeks to hours by producing a structured codebase map:

- **Stack and tooling** - what the project is built with, in full
- **Architecture map** - how the system is structured, what owns what
- **Key patterns and conventions** - how the team writes code here, not how you did it elsewhere
- **Risk hotspots** - tech debt, complexity concentrations, and fragile areas to approach carefully
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
- Architecture decision review - use `task-design-architecture` for proposing new designs

## Inputs

| Input                 | Required | Source                                                             |
| --------------------- | -------- | ------------------------------------------------------------------ |
| Root directory        | Yes      | Current working directory (default) or user-specified path         |
| CLAUDE.md / AGENTS.md | No       | Auto-read if present - primary source of declared stack and intent |
| Scope focus           | No       | User-specified module, service, or concern to prioritize           |
| Known pain points     | No       | User-provided areas of concern ("payments module is a problem")    |

If the user provides a scope focus, prioritize that area but still produce the full codebase overview. If no focus is given, cover the entire repository.

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

Read `CLAUDE.md`, `AGENTS.md`, `package.json`, `build.gradle`, `go.mod`, `pyproject.toml`, `Gemfile`, `*.csproj`, `pom.xml`, `Cargo.toml`, `mix.exs` to fill in gaps not declared in agent files.

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

### Step 3 - Identify Architecture Pattern

Based on the file layout, naming, and key framework conventions, classify the dominant architectural pattern:

| Pattern           | Signals                                                                        |
| ----------------- | ------------------------------------------------------------------------------ |
| Layered (MVC/MVS) | `controller/`, `service/`, `repository/` or `model/` top-level folders         |
| Clean / Hexagonal | `domain/`, `application/`, `infrastructure/`, `ports/`, `adapters/` separation |
| Modular monolith  | Feature-based top-level modules each containing their own layers               |
| Vertical slice    | Feature folders each containing controller + service + model + test            |
| Microservice      | Multiple independently deployable services with separate entry points          |
| Event-driven      | Dominant use of events/messages as primary coupling mechanism                  |

State which pattern(s) are in use, with evidence (file paths, naming conventions observed).

Use skill: `architecture-guardrail` to identify any visible layer violations or boundary erosion already present.

### Step 4 - Map Key Modules and Data Flows

For each significant module or bounded context found:

- **Responsibility** - what this module does in one sentence
- **Owns** - which data entities or domain objects it is authoritative for
- **Depends on** - other modules, external services, or shared libraries it calls
- **Entry points** - controllers, consumers, scheduled jobs, CLI commands
- **Data access** - ORM entities, repositories, raw queries - what pattern is used

Identify the **primary request/event flow** for the most important operation in the codebase (e.g., the main user-facing action) and trace it through the layers:

```
Request → [Layer 1] → [Layer 2] → [Data store]
       ↳ [Async side effect via queue/event]
```

### Step 5 - Extract Key Patterns and Conventions

Read representative files across the codebase to extract the patterns the team actually uses:

**Code patterns to identify:**

- How dependency injection is done (constructor, framework annotation, manual wiring)
- How errors are handled and propagated
- How logging is done (library, structured vs unstructured, correlation IDs)
- How configuration is loaded (env vars, config files, secrets manager)
- How authentication and authorization are enforced (middleware, annotations, filters)
- How database transactions are scoped
- How background jobs or async processing is handled

**Test patterns to identify:**

- Unit vs integration vs end-to-end split
- How test data is created (factories, fixtures, builders)
- How external dependencies are mocked (library, approach)
- Test naming conventions

Use skill: `coding-standards` to compare observed patterns against known best practices for the detected stack. Note where the codebase follows conventions and where it diverges.

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

For each finding: state the location, the signal observed, and the risk it poses to someone making changes there.

### Step 7 - Operational Context

Identify how the application runs and is operated:

- **Local dev setup** - `README` instructions, `Makefile`, `docker-compose`, seed scripts
- **CI/CD pipeline** - what runs on PR (lint, test, build), what runs on merge (deploy targets)
- **Deployment model** - containers, serverless, bare metal, cloud platform (inferred from Dockerfile, IaC)
- **Environment configuration** - how dev/staging/prod configs differ (env file strategy, secrets injection)
- **Observability** - logging library and format, metrics endpoint, tracing instrumentation (if detectable)
- **Database migration strategy** - manual trigger, auto-run on startup, CI step

Use skill: `observability` to assess whether the observability setup is sufficient for production operation.

## Output Format

```markdown
# Codebase Onboarding Report

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

| Concern         | Pattern Observed                            | Location Example         |
| --------------- | ------------------------------------------- | ------------------------ |
| DI              | [e.g., constructor injection via wire]      | [file path]              |
| Error handling  | [e.g., wrapped errors with fmt.Errorf %w]   | [file path]              |
| Logging         | [e.g., slog structured, request-scoped]     | [file path]              |
| Config          | [e.g., viper + env vars, no hardcoding]     | [file path]              |
| Auth            | [e.g., JWT middleware on Gin router groups] | [file path]              |
| Transactions    | [e.g., GORM WithContext transaction]        | [file path]              |
| Background jobs | [e.g., Asynq workers in internal/worker/]  | [file path]              |
| Tests           | [e.g., table-driven, mockery mocks]         | [file path]              |

## Tech Debt and Risk Hotspots

### [High | Medium | Low] - [Short label]

- **Location:** [file or module path]
- **Signal:** [what was observed]
- **Risk:** [what breaks or becomes harder if you change this area]

[Repeat per finding, ordered High → Medium → Low]

## Operational Context

| Concern            | Details                                      |
| ------------------ | -------------------------------------------- |
| Local setup        | [how to run locally]                         |
| CI on PR           | [what runs]                                  |
| Deploy target      | [platform / mechanism]                       |
| Config management  | [strategy]                                   |
| Observability      | [logging/metrics/tracing setup]              |
| Migration strategy | [how and when migrations run]                |

## Onboarding Recommendations

1-5 prioritized actions for the new engineer based on the findings above:

- **[Action]**: [Why this matters first]
- **[Action]**: [What risk it removes or knowledge it builds]

## Summary

3-5 bullets covering:
- Architectural strengths (what the codebase does well)
- Primary risk areas (where to be careful)
- Biggest knowledge gaps to close in the first week
```

### Output Constraints

- Stack table must distinguish declared (from CLAUDE.md) from inferred (from file presence)
- Architecture classification must cite specific file paths as evidence - no guessing
- Patterns table must cite a real file path for each pattern - not invented examples
- Tech debt findings ordered High → Medium → Low
- Onboarding Recommendations limited to 5 items - prioritize ruthlessly
- Omit any section where nothing meaningful was found
- Do not comment on code style or formatting in tech debt - focus on structural and operational risk
- Total output should be comprehensive but scannable - use tables over prose wherever possible

## Rules

- Read files, do not modify them
- Never invent file paths or module names - only report what is observed
- If a directory or file cannot be read, note it and continue
- If the codebase is monorepo with multiple services, scope the report to the service the user is focused on, then note other services exist
- Do not generate code, refactoring plans, or migration plans - produce a map, not a roadmap

## Key Skills Reference

- Use skill: `stack-detect` for technology identification
- Use skill: `architecture-guardrail` for boundary violation and layer erosion detection
- Use skill: `complexity-review` for complexity hotspot identification
- Use skill: `coding-standards` for pattern comparison against detected stack conventions
- Use skill: `observability` for operational observability assessment

## Success Criteria

A well-executed onboarding report passes all of these. Use as a self-check before presenting the report.

### Accuracy

- [ ] Every file path, module name, and technology cited is observed - nothing invented
- [ ] Stack table distinguishes declared (from CLAUDE.md) from inferred (from file presence)
- [ ] Architecture classification cites specific file paths as evidence - not inferred from project type alone
- [ ] Patterns table references real file paths for each pattern - not invented examples

### Completeness

- [ ] All 7 workflow steps are covered: stack, structure, architecture, modules, patterns, tech debt, ops
- [ ] At least one primary request/event flow is traced through the layers
- [ ] Tech debt findings are ordered High > Medium > Low and include location, signal, and risk
- [ ] Onboarding Recommendations are limited to 5 items and prioritized by day-one impact

### Staff-Level Signal (for senior engineer use)

- [ ] A new senior engineer could read this report and make their first PR safely without asking the team
- [ ] Risk hotspots are actionable - each states what breaks if you change that area
- [ ] Operational context is sufficient to run the service locally and understand the deploy pipeline
- [ ] The report identifies the most important thing to learn in the first week

## Avoid

- Inventing architecture descriptions without reading actual files
- Recommending rewrites or refactors - this is an onboarding map, not a remediation plan
- Reporting every file - summarize at module level, drill down only for key examples
- Conflating tech debt with code style - focus on structural risk and operational fragility
- Generic advice ("add more tests", "improve logging") without citing specific observed gaps
- Treating absence of a file as a problem without checking if it exists elsewhere

## After This Skill

If the output needed significant adjustment - architecture was misread, key patterns were missed, or tech debt hotspots were wrong - run `/task-skill-feedback` to log what changed and why.
