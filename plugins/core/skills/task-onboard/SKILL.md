---
name: task-onboard
description: Onboard to a codebase: bootstrap commands, key files, architecture, conventions, risk hotspots, contribution workflow, first-PR safe zones.
metadata:
  category: code
  tags: [onboarding, architecture, tech-debt, codebase-analysis, patterns, multi-stack]
  type: workflow
user-invocable: true
---

# Codebase Onboarding

Produces a structured codebase map calibrated to the reader's goal so engineer ramp-up moves from weeks to hours. Reads the codebase; modifies nothing.

## When to Use

- First day on a new project or service
- Taking ownership of an unfamiliar module
- Before the first significant change to an unknown codebase
- Due diligence / acquisition code review

**Not for:** explaining a single file or function (`task-code-explain`), code-quality review (`task-code-review`), proposing new architecture.

## Inputs

| Input             | Required | Notes                                                                       |
| ----------------- | -------- | --------------------------------------------------------------------------- |
| Root directory    | Yes      | Current working directory (default) or user path                            |
| Repo context file | No       | `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` if present - primary stated source  |
| Focus mode        | No       | `first-pr`, `architect-survey`, `full` (default) - controls emphasis        |
| Scope focus       | No       | Module, service, or concern to prioritize                                   |
| Known pain points | No       | User-flagged areas of concern                                               |

If scope focus is given, cover its modules, flows, and hotspots at full depth; compress the rest of the repo to one-line entries (still present, never omitted).

If known pain points are given, investigate each: trace the implicated flow (Step 5), check it against hotspots (Step 7), and report a verdict with evidence in Pain Point Findings.

**Focus modes** (every step still runs to gather context; output weight shifts):

| Mode               | Audience                              | Emphasis                                                                                       |
| ------------------ | ------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `first-pr`         | New engineer shipping first PR        | Local bootstrap, contribution workflow, first-PR safe zones, what to read first                |
| `architect-survey` | Senior engineer / due diligence       | Architecture, patterns, tech debt, structural risk                                             |
| `full` (default)   | Anyone wanting the complete picture   | All sections at equal weight                                                                   |

Weight shift: section order never changes and no section is dropped; write the mode's emphasized sections at full depth and compress the rest to their tables plus one-line notes. If the user's stated goal implies a mode, confirm rather than defaulting silently.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack and Load Atomic

Use skill: `stack-detect` to identify language, framework, build tool, test framework, database / ORM, async / messaging, IaC / deployment tooling.

Read repo context file (`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`) plus build manifests (`package.json`, `build.gradle`, `go.mod`, `pyproject.toml`, `Gemfile`, `*.csproj`, `pom.xml`, `Cargo.toml`, `mix.exs`) to fill gaps.

If detected stack matches, load the atomic. It injects stack-specific bootstrap commands, key files, conventions, and risk hotspots into the matching report sections; do not produce a separate "stack-specific" section.

| Detected stack       | Load atomic           |
| -------------------- | --------------------- |
| Java / Spring Boot   | `spring-onboard-map`  |
| Kotlin / Spring Boot | `kotlin-onboard-map`  |
| Python               | `python-onboard-map`  |
| Ruby / Rails         | `rails-onboard-map`   |
| Node.js / TypeScript | `node-onboard-map`    |
| Go / Gin             | `go-onboard-map`      |

If no atomic matches the detected stack (e.g., Elixir), or the matched atomic does not resolve (stack plugin not installed), proceed with the generic workflow and note `no stack-specific onboarding atomic - generic guidance applied` under the Stack table.

Also extract a **one-paragraph system summary**: what problem this system solves, who uses it, and 2-3 main capabilities. Source from `README.md`, repo context file, top-level package descriptions, or service manifest. If not declared, mark `unknown - repo does not declare purpose` rather than inferring from code.

State explicitly what was *declared* vs *inferred* from file presence.

### Step 3 - Map Repository Structure

Explore top-level layout. Identify entry points (`main`, `app`, `server`, `index`, `Program.cs`, `Application.java`), module layout (by domain / layer / feature), configuration files (env, secrets, flags), migration files and tooling, test structure, infrastructure files (`Dockerfile`, `docker-compose.yml`, CI configs, Helm, Terraform).

Produce a **directory map** (top 2-3 levels, one-line annotations per significant directory) plus:

- **Where to look first** - 2-3 high-leverage directories for early reading
- **Safe to skip initially** - vendored deps, generated code, large fixtures, deprecated modules

### Step 4 - Identify Architecture Pattern

Classify based on layout, naming, framework conventions, and detected `Stack Type`.

**Backend patterns:** Layered (MVC/MVS) - controller/service/repository folders; Clean/Hexagonal - domain/application/infrastructure separation; Modular monolith - feature modules each containing their own layers; Vertical slice - feature folders with controller+service+model+test; Microservice - multiple deployables; Event-driven - events as primary coupling.

**Frontend patterns:** Feature-based - feature folders with components/hooks/tests; Atomic Design - atoms/molecules/organisms; Route-based - pages/routes top-level; Module-based - self-contained modules per feature; Monolith integration - frontend inside a backend framework (Rails views, Django templates, Inertia).

State which pattern(s) are used, citing file paths and naming evidence.

Use skill: `architecture-guardrail` to spot existing layer violations or boundary erosion.

### Step 5 - Map Key Modules and Data Flows

For each significant module / bounded context: responsibility (one sentence), data entities owned, dependencies (modules, external services), entry points (controllers, consumers, jobs, CLI), data access pattern (ORM, repository, raw queries).

**External integrations** - third-party services, where integration code lives, credential management, failure handling.

Trace the **primary request/event flow** end-to-end for the most important operation - or the flow implicated by a known pain point or scope focus:

```
Request -> [Layer 1] -> [Layer 2] -> [Data store]
       (async) [Side effect via queue / event]
```

### Step 6 - Extract Key Patterns and Conventions

Read representative files. Focus on what applies to the detected `Stack Type`.

**Backend (when `backend` or `fullstack`):** DI style (constructor / annotation / manual); error handling and propagation; logging (library, structured?, correlation IDs); config loading (env, files, secrets manager); auth and authz enforcement (middleware, annotations, filters); transaction scoping; background jobs (discovery, queue topology, retries, monitoring); caching (library, strategy, invalidation).

Use skill: `backend-coding-standards` to compare observations to best practice for the detected stack.

**Frontend (when `frontend` or `fullstack`):** component architecture (smart/dumb split, feature components, shared UI); state strategy (local, store/context, URL, server state); data fetching (hooks/composables, server components, global fetch wrapper); routing (file-based vs manual, layouts, guards); styling (CSS modules, Tailwind, styled-components, tokens); form handling; accessibility discipline.

**Tests (all stacks):** unit / integration / E2E split; test data construction (factories, fixtures, builders, MSW); mocking approach; naming conventions.

**Domain knowledge (all stacks):** key terms (define each in one line), critical invariants (must-never-violate rules - source from validations, assertion-heavy tests, contracts), edge cases that matter (timezones, currency, soft-delete, multi-tenant isolation).

Cap each domain table at 5 most load-bearing items; cite where each is enforced.

### Step 7 - Surface Tech Debt and Risk Hotspots

Use skill: `complexity-review` and `architecture-guardrail` to detect complexity concentrations and boundary violations.

Scan for:

- **Structural:** god classes/modules; layer violations; circular deps; dead code.
- **Consistency:** mixed architectural patterns; duplicate concerns (two HTTP wrappers); inconsistent error handling; inconsistent logging.
- **Operational:** missing tests on critical paths; no migration rollback; hardcoded config/secrets; missing health checks.
- **Complexity hotspots:** files >~300 lines; deeply nested conditionals; high-churn areas from `git log`.

**Common pitfalls** for the new engineer: skipped/disabled tests (`skip`, `xit`, `@Disabled`, `t.Skip`, `pytest.mark.skip`, files named `flaky`); high TODO/FIXME density; module-level side effects (`init()`, top-level imports with effects, framework auto-registration); legacy modules pending deprecation; slow tests excluded from default CI.

For each finding: location, signal observed, risk to anyone changing that area.

For each known pain point, record a verdict: `confirmed` (cite the signal), `not confirmed` (state what was checked), or `not assessable from the repo`.

### Step 8 - Operational Context

CI/CD (what runs on PR vs merge, deploy targets); deployment model (container, serverless, bare metal, cloud); env config (dev/staging/prod differences, secrets injection); observability (logging, metrics, tracing if detectable); migration trigger strategy. Local dev setup belongs to Step 9 - the Operational Context table carries only a one-line summary.

Use skill: `ops-observability` to assess whether observability is production-sufficient.

### Step 9 - Local Bootstrap and Smoke Test

Reconstruct the exact path from clone to running app. A first PR cannot ship without this.

Read `README.md`, `CONTRIBUTING.md`, `Makefile`, `Justfile`, `docker-compose.yml`, `.env.example`, `package.json` scripts, `bin/`, language task files (`Rakefile`, `manage.py`, `mix.exs`). Capture:

- **Prerequisites** - language version (`.tool-versions`, `.nvmrc`, `.python-version`, `go.mod`, build files); required services (DB, Redis, broker); system tools.
- **Bootstrap sequence** - exact ordered commands: clone -> install -> start deps -> migrate -> seed -> run. Cite each.
- **Required config** - env vars, example file location, secret sources (1Password, Vault, team handoff).
- **Smoke check** - health endpoint, default port, login URL, local default credentials.
- **Common first-run failures** - documented gotchas (port conflicts, native deps, Apple Silicon notes).

If a step is required but undocumented (e.g., code reads `DATABASE_URL` but no `.env.example`), flag as a documentation gap rather than inventing values.

### Step 10 - Ecosystem and Runtime Topology

Map where the service lives in the wider system. Read CI configs, IaC, deployment manifests, observability references, integration code.

- **Upstream callers** - clients, sibling services, scheduled triggers, webhooks (from API docs, OpenAPI, route names).
- **Downstream dependencies** - DBs, caches, queues, third-party APIs, sibling services (from integration code, config keys, IaC).
- **Environments** - dev / staging / prod targets, URLs/hostnames if discoverable.
- **Where to watch it** - logs destination (Datadog, CloudWatch, Loki), metrics dashboard, tracing UI, error tracker (Sentry/Rollbar/Bugsnag), alerting channel. Cite paths or config keys; do not invent URLs.
- **Trace a request locally** - correlation ID header name, request-ID middleware, tracing instrumentation; how to reproduce a prod issue against local.
- **Deployment platform specifics** - k8s cluster/namespace, Lambda name, ECS service, Heroku app, Vercel project.
- **Feature flags and env config diffs** - flag library (LaunchDarkly, Unleash, in-house), where defined and read; how dev/staging/prod configs differ.

Mark `unknown - not discoverable from the repo` for anything the codebase does not reveal. Do not invent URLs, endpoints, channels.

### Step 11 - Contribution Workflow

Capture the path from edit to merge. Read `CONTRIBUTING.md`, `.github/` (PR template, CODEOWNERS, workflows), `.gitlab/`, pre-commit configs (`.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`), lint configs, CI files.

- **Branching** - default branch, naming rules, forbidden direct pushes.
- **PR requirements** - template fields, required reviewers via `CODEOWNERS`, required approvals, required CI checks.
- **Local quality gates** - pre-commit hooks, linters, formatters, exact commands.
- **Test commands** - unit / integration / full suite / single file - exact commands cited from `package.json` scripts, Makefile, language conventions.
- **CI shape** - what runs on PR open vs merge; approximate stages; known slowness/flake.
- **Module owners** - from `CODEOWNERS` and, where helpful, recent committers (read-only `git log` / `git shortlog`).
- **Communication channels** - Slack/Teams/mailing list referenced in repo - cite source, do not invent.
- **Common rejection reasons** - patterns visible in `CONTRIBUTING.md`, PR template, lint configs, recent merged PRs. Cite source.
- **Reference example PRs** - linked from `README`, `CONTRIBUTING`, or PR template; otherwise omit (do not invent PR numbers).
- **First-PR safe zones** - cross-reference Step 7 hotspots. List 2-3 well-tested, low-churn, narrow-blast areas; list 2-3 areas to avoid first.

Use skill: `dependency-impact-analysis` if the user names a candidate first-PR area, to estimate blast radius.

## Output Format

```markdown
# Codebase Onboarding Report

## System Summary

[One paragraph from README / repo context, or `unknown - repo does not declare purpose`]

## Stack

| Concern    | Technology              | Source              |
| ---------- | ----------------------- | ------------------- |
| Language   | [e.g., Go 1.25]         | Declared / Inferred |
| Framework  | [Gin + GORM]            | Declared / Inferred |
| Build      | [Go modules]            | Inferred            |
| Test       | [testify + mockery]     | Inferred            |
| Database   | [PostgreSQL via GORM]   | Inferred            |
| Async/Jobs | [Asynq (Redis)]         | Inferred            |
| Deployment | [Docker + GH Actions]   | Inferred            |

## Repository Structure

[directory map - top 2-3 levels with one-line annotations]

**Where to look first:** [2-3 paths with reason]
**Safe to skip initially:** [vendored, generated, fixtures, deprecated]

## Architecture

**Pattern:** [Layered / Clean / Modular monolith / Vertical slice / Microservice / Event-driven]
**Evidence:** [2-3 paths / naming observations]

### Modules

| Module | Responsibility | Data Owned | Dependencies |
| ------ | -------------- | ---------- | ------------ |

### Primary Flow

[Trace main request/event through layers]

## Key Patterns and Conventions

| Concern         | Pattern               | Example Location |
| --------------- | --------------------- | ---------------- |

Include only rows relevant to detected `Stack Type`; draw concerns from the Step 6 lists.

## Domain Knowledge

### Key Concepts (cap 5)

| Term | Definition | Defined/Enforced In |
| ---- | ---------- | ------------------- |

### Critical Invariants (cap 5)

| Invariant | Enforced In |
| --------- | ----------- |

### Edge Cases That Matter (cap 5)

- **[Case]**: [why tricky] - [file path]

## Tech Debt and Risk Hotspots

### Pain Point Findings (only when Known pain points given)

| Pain point | Verdict | Evidence |
| ---------- | ------- | -------- |

Verdict: `confirmed` / `not confirmed` / `not assessable from the repo`.

Order findings High -> Medium -> Low. For each:

- **[Severity]** - [short label]
- **Location:** [path]  **Signal:** [observed]  **Risk:** [what breaks]

## Common Pitfalls

- **Skipped/flaky tests:** [paths + marker]
- **Hidden side effects:** [module-level init, package `init()`, auto-registration]
- **Legacy / deprecated:** [paths]
- **Slow tests:** [paths + tag + how excluded]
- **Other documented gotchas:** [cite source]

## Operational Context

| Concern            | Details |
| ------------------ | ------- |
| Local setup        | [summary - full in Local Quickstart] |
| CI on PR           | [what runs] |
| Deploy target      | [platform / mechanism] |
| Config             | [strategy] |
| Observability      | [logging / metrics / tracing] |
| Migration strategy | [how / when migrations run] |

## Local Quickstart

**Prerequisites:** [language version, services, system tools - cite source files]

**Bootstrap (in order):**

```
[command 1 - e.g., cp .env.example .env]
[command 2 - e.g., docker-compose up -d postgres redis]
[command 3 - e.g., make migrate]
[command 4 - e.g., make seed]
[command 5 - e.g., make dev]
```

**Required env vars:** [list with examples / source; flag any missing from `.env.example`]
**Smoke check:** [verification step - e.g., `curl localhost:3000/health` returns 200]
**Known first-run gotchas:** [platform notes; omit if none documented]

## Ecosystem and Runtime Topology

| Concern             | Details (or `unknown - not discoverable from the repo`) |
| ------------------- | -------------------------------------------------------- |
| Upstream callers    | |
| Downstream services | |
| Environments        | |
| Logs                | |
| Metrics / dashboards | |
| Tracing             | |
| Trace / reproduce a request locally | |
| Error tracking      | |
| Deployment platform | |
| Feature flags       | |
| Env config diffs    | |
| On-call / alerting  | |

## Contribution Workflow

| Concern                | Details |
| ---------------------- | ------- |
| Default branch         | |
| Branch naming          | |
| PR requirements        | |
| CODEOWNERS             | [`none` if absent] |
| Local quality gates    | [exact commands] |
| Test commands          | [unit / integration / suite / single file] |
| CI pipeline            | [PR vs merge; slowness/flake] |
| Channels               | [`none documented` if absent] |
| Common rejection reasons | [cite source] |
| Reference example PRs  | [`none cited` if absent] |

### First-PR Safe Zones (cap 3)

| Area | Why safe | Suggested entry file |
| ---- | -------- | -------------------- |

### Avoid for First PR (cap 3)

| Area | Why to wait |
| ---- | ----------- |

## Onboarding Recommendations

Include subsections per their Focus tags; untagged subsections appear in every mode. `first-pr`: lead with Mission Framing + First-PR Playbook. `architect-survey`: lead with First-Week Knowledge Gaps. `full`: keep template order.

### Mission Framing (first-pr)

- **Realistic first-PR targets:** [grounded in safe zones - small bug fix in low-churn module, logging improvement, missing test, config tweak]
- **Suggested timeline:** [based on CI duration / review cadence]
- **What good looks like here:** [cite reference example PRs or describe expected size/shape]

### First-PR Playbook (first-pr, full)

1. Run locally (Local Quickstart); confirm smoke check.
2. Pick from First-PR Safe Zones; verify ownership against CODEOWNERS.
3. Reproduce existing behavior (run tests, hit endpoint or screen).
4. Trace the code path using Key Patterns.
5. Make minimal change; add or adjust tests in existing style.
6. Run local quality gates with the exact Contribution Workflow commands.
7. Open the PR with the project template; tag CODEOWNERS; preempt Common Rejection Reasons.

### First-Day Checklist (cap 5)

Concrete actions: command or file to read; expected outcome.

### First-Week Knowledge Gaps (cap 5)

Areas to study before broader work: why it matters; suggested reading path.

## Summary

3-5 bullets: architectural strengths; primary risk areas; recommended first-PR target (if Focus first-pr); biggest knowledge gaps for first week.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran; stack atomic loaded, or no-atomic fallback noted under Stack table; signals merged into Stack, Local Quickstart, Architecture, Patterns, Tech Debt, First-PR sections; System Summary captured or marked unknown
- [ ] Step 3: directory map plus "Where to look first" and "Safe to skip initially"
- [ ] Step 4: architecture pattern classified with cited evidence
- [ ] Step 5: modules table; primary flow traced (pain-point or scope flow when given)
- [ ] Step 6: patterns table cites real paths; Domain Knowledge tables capped at 5, each cited
- [ ] Step 7: tech debt findings ordered High -> Medium -> Low with concrete locations; pitfalls flagged with markers and paths; each known pain point given a verdict (or n/a)
- [ ] Step 8: Operational Context populated
- [ ] Step 9: Local Quickstart commands cited from real files; missing prerequisites flagged as documentation gaps
- [ ] Step 10: ecosystem unknowns marked, not invented
- [ ] Step 11: contribution workflow with exact commands, channels, rejection reasons (or `none cited`); First-PR Safe Zones and Avoid each 1-3 items
- [ ] Focus mode honored: emphasized sections full depth, rest compressed, no section dropped; subsection tags applied; First-Day Checklist and First-Week Gaps each capped at 5
- [ ] No invented paths, modules, commands, URLs, channels, PR numbers, or examples

## Avoid

- Inventing file paths, module names, commands, env values, dashboard or environment URLs
- Generating refactoring or migration plans (this produces a map, not a roadmap)
- Commenting on code style or formatting as tech debt - focus on structural and operational risk
- Over-exploring vendor, node_modules, build output
- Producing an exhaustive inventory instead of a scannable summary
- Recommending a first-PR area without cross-referencing hotspots and CODEOWNERS
