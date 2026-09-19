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

**Not for:** code-quality review (`task-code-review`), proposing new architecture.

## Inputs

| Input             | Required | Notes                                                                       |
| ----------------- | -------- | --------------------------------------------------------------------------- |
| Root directory    | Yes      | Current working directory (default) or user path                            |
| Repo context file | No       | `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` if present - primary stated source  |
| Focus mode        | No       | `first-pr`, `architect-survey`, `full` (default) - controls emphasis        |
| Scope focus       | No       | Module, service, or concern to prioritize                                   |
| Known pain points | No       | User-flagged areas of concern                                               |
| First-PR candidate | No      | A file or change the user names as their likely first PR - triggers `dependency-impact-analysis` (Step 11) |

If scope focus is given, cover its modules, flows, and hotspots at full depth; compress the rest of the repo to one-line entries (still present, never omitted).

If known pain points are given, investigate each: trace the implicated flow (Step 5), check it against hotspots (Step 7), and report a verdict with evidence in Pain Point Findings.

**Focus modes** (every step still runs to gather context; output weight shifts):

| Mode               | Audience                              | Emphasis                                                                                       |
| ------------------ | ------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `first-pr`         | New engineer shipping first PR        | Full depth: Local Quickstart, Contribution Workflow (incl. First-PR Safe Zones / Avoid), Repository Structure, Onboarding Recommendations |
| `architect-survey` | Senior engineer / due diligence       | Full depth: Architecture, Key Patterns and Conventions, Tech Debt and Risk Hotspots, Ecosystem and Runtime Topology |
| `full` (default)   | Anyone wanting the complete picture   | All sections at equal weight                                                                   |

Weight shift: section order never changes (the Onboarding Recommendations subsections reorder and gate by mode tag, per that section) and no section is dropped; write the mode's emphasized sections at full depth and compress every section not named in the mode's emphasis list - keep tables and command blocks, reduce prose to one-line notes, trim table bodies to the 1-3 most load-bearing rows. Fixed tables (Stack, Operational Context, Ecosystem and Runtime Topology, Contribution Workflow, Pain Point Findings) are exempt - compress their prose, never their rows. Compression never drops a High-severity Tech Debt finding: publish every High, then fold Medium and Low to the 3 most load-bearing (the cap is 8 whenever Tech Debt is not compressed). Scope focus wins over mode compression: focused content stays full depth wherever it lands. If the user's stated goal implies a mode but names none, name the assumed mode in the report header and proceed - this workflow modifies nothing, so no confirmation is needed.

**Delegate outputs fold in.** Every atomic a step loads (stack atomic, guardrail, complexity, standards, observability, dependency-impact-analysis) contributes content to the matching report sections with severities and labels preserved; this workflow's template governs final shape, and no atomic's own output envelope is emitted - a delegate's check-ran marker is satisfied by the folded content itself. For Tech Debt ordering, `[Must]` ranks High and `[Recommend]` Medium, the original label kept visible; when several delegates flag the same location, merge into one finding naming each source. A finding that fits both Architecture and Tech Debt lands in Tech Debt, the only section with a findings slot; Architecture carries pattern and evidence only, and `architecture-guardrail`'s Step 4 output folds into Tech Debt the same way. Close Tech Debt with `Checked clean: <delegates that ran and found nothing>` and, when a delegate's scan could not run (`backend-coding-standards` writes `not assessed - <reason>` for its anti-pattern scan while still emitting its Violations), `Not assessed: <delegate scan - reason>`, so a clean delegate is distinguishable from one that never ran or could not run. Fixed tables are floors - append rows the folded content needs (extra Stack rows for Migrations or Lint). A cell the repo positively shows to be absent takes `none - <evidence>`; a cell nothing reveals takes `unknown - not discoverable from the repo`.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack and Load Atomic

Use skill: `stack-detect` to identify language, framework, build tool, test framework and database / ORM. Async / messaging and IaC / deployment tooling reach `stack-detect` only as `Additional` keys declared in the instruction file: take them from `Additional` when present, since an explicit declaration wins, and otherwise from the manifests and infrastructure files read below. A secondary stack `stack-detect` writes into `Additional` (a fullstack monorepo's `Frontend: TypeScript (React)`) gets its own Stack rows (`Frontend language`, `Frontend framework`).

Read repo context file (`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`) plus build manifests (`package.json`, `build.gradle`, `go.mod`, `pyproject.toml`, `Gemfile`, `*.csproj`, `pom.xml`, `Cargo.toml`, `mix.exs`) to fill gaps. A stack-detect `unknown` may be upgraded from direct repo evidence (ExUnit from `test/test_helper.exs`); mark it Inferred.

If detected stack matches, load the atomic. It injects stack-specific bootstrap commands, key files, conventions, and risk hotspots into the matching report sections; do not produce a separate "stack-specific" section - the atomic governs content, this template governs placement and shape, and the atomic's own section order and envelope are discarded.

| Detected stack       | Load atomic           |
| -------------------- | --------------------- |
| Java / Spring Boot   | `spring-onboard-map`  |
| Python               | `python-onboard-map`  |
| Ruby / Rails         | `rails-onboard-map`   |
| Node.js / TypeScript | `node-onboard-map`    |
| Go / Gin             | `go-onboard-map`      |
| React / Next.js / Vite | `react-onboard-map` |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the generic workflow); a row named by language alone (Python, Node.js / TypeScript) matches that language under any framework, except that a `React (...)` framework matches the React row first, and a `Vue (...)` or `Svelte (...)` framework matches no row even when Vite builds it. Matching keys on the primary `Language`/`Framework` pair; a secondary stack in `Additional` loads its own atomic too when one resolves, and each atomic folds into the sections for its directory. If no atomic matches the detected stack (e.g., Elixir), or the matched atomic does not resolve (stack plugin not installed), proceed with the generic workflow and note `no stack-specific onboarding atomic - generic guidance applied` under the Stack table.

Also extract a **one-paragraph system summary**: what problem this system solves, who uses it, and 2-3 main capabilities. Source from `README.md`, repo context file, top-level package descriptions, or service manifest. If not declared, mark `unknown - repo does not declare purpose` rather than inferring from code.

State explicitly what was *declared* vs *inferred* from file presence.

### Step 3 - Map Repository Structure

Explore top-level layout. Identify entry points (`main`, `app`, `server`, `index`, `Program.cs`, `Application.java`), module layout (by domain / layer / feature), configuration files (env, secrets, flags), migration files and tooling, test structure, infrastructure files (`Dockerfile`, `docker-compose.yml`, CI configs, Helm, Terraform).

Produce a **directory map** (top 2-3 levels, one-line annotations per significant directory) plus:

- **Where to look first** - 2-3 high-leverage directories for early reading
- **Safe to skip initially** - vendored deps, generated code, large fixtures, deprecated modules. Generated or gitignored artifacts left by earlier tooling (prior review reports, build output) are evidence about tooling, not about the code - never cite one as a finding's source

### Step 4 - Identify Architecture Pattern

Classify based on layout, naming, framework conventions, and detected `Stack Type`.

**Backend patterns:** Layered (MVC) - controller/service/repository folders; Clean/Hexagonal - domain/application/infrastructure separation; Modular monolith - feature modules each containing their own layers; Vertical slice - feature folders with controller+service+model+test; Microservice - multiple deployables; Event-driven - events as primary coupling; None established - a flat or single-file module with no layer separation.

**Frontend patterns:** Feature-based - feature folders with components/hooks/tests; Atomic Design - atoms/molecules/organisms; Route-based - pages/routes top-level; Module-based - self-contained modules per feature; Monolith integration - frontend inside a backend framework (Rails views, Django templates, Inertia); None established - no discernible frontend structure.

State which pattern(s) are used, citing file paths and naming evidence.

Use skill: `architecture-guardrail` in its whole-tree audit mode (no diff; every file in scope) to spot existing layer violations or boundary erosion. Its `[Must]` / `[Recommend]` labels fold into Tech Debt as the Delegate outputs paragraph states, and each finding's `Drift:` value is appended to its Signal.

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

Use skill: `complexity-review` to detect complexity concentrations, and reuse the `architecture-guardrail` output already loaded in Step 4 rather than loading it again - its violations publish once.

Scan for:

- **Structural:** god classes/modules; layer violations; circular deps; dead code.
- **Consistency:** mixed architectural patterns; duplicate concerns (two HTTP wrappers); inconsistent error handling; inconsistent logging.
- **Operational:** missing tests on critical paths; no migration rollback; hardcoded config/secrets; missing health checks.
- **Complexity hotspots:** files over `complexity-review`'s size threshold for the stack (200-300 lines); deeply nested conditionals; high-churn areas from `git log`.

**Common pitfalls** for the new engineer: skipped/disabled tests (`skip`, `xit`, `@Disabled`, `t.Skip`, `pytest.mark.skip`, files named `flaky`); high TODO/FIXME density; module-level side effects (`init()`, top-level imports with effects, framework auto-registration); legacy modules pending deprecation; slow tests excluded from default CI; documentation that contradicts the code (a README or incident doc naming a call the code does not make).

For each finding: location, signal observed, risk to anyone changing that area.

For each known pain point, record a verdict: `confirmed` (cite the signal), `not confirmed` (state what was checked), or `not assessable from the repo`.

### Step 8 - Operational Context

CI/CD (what runs on PR vs merge, deploy targets); deployment model (container, serverless, bare metal, cloud); env config (dev/staging/prod differences, secrets injection); observability (logging, metrics, tracing if detectable); migration trigger strategy. Local dev setup belongs to Step 9 - the Operational Context table carries only a one-line summary.

Use skill: `ops-observability` in review mode (its `### Gaps` / `### No Gaps Found` alternation) to assess whether observability is production-sufficient: the Observability row reads `sufficient - no gaps found` when it emits `### No Gaps Found`, otherwise `<N> gaps (<H> High) - see Tech Debt`, and the gaps themselves land in Tech Debt at their severity.

### Step 9 - Local Bootstrap and Smoke Test

Reconstruct the exact path from clone to running app. A first PR cannot ship without this.

Read `README.md`, `CONTRIBUTING.md`, `Makefile`, `Justfile`, `docker-compose.yml`, `.env.example`, `package.json` scripts, `bin/`, language task files (`Rakefile`, `manage.py`, `mix.exs`). Capture:

- **Prerequisites** - language version (`.tool-versions`, `.nvmrc`, `.python-version`, `go.mod`, build files); required services (DB, Redis, broker); system tools.
- **Bootstrap sequence** - exact ordered commands after the clone: config -> install -> start deps -> migrate -> seed -> run. Cite each.
- **Required config** - env vars, example file location, secret sources (1Password, Vault, team handoff).
- **Smoke check** - health endpoint, default port, login URL, local default credentials; when no health endpoint exists, give the closest verifiable check (framework status command, a known route) - never invent an endpoint.
- **Common first-run failures** - documented gotchas (port conflicts, native deps, Apple Silicon notes).

If a step is required but undocumented (e.g., code reads `DATABASE_URL` but no `.env.example`), flag as a documentation gap rather than inventing values. When no bootstrap artifact exists at all, list the commands the manifests imply, each marked `(undocumented)`, and raise the absence as a High documentation finding in Tech Debt.

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

Capture the path from edit to merge. Read `README.md`, `CONTRIBUTING.md`, `.github/` (PR template, CODEOWNERS, workflows), `.gitlab/`, pre-commit configs (`.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`), lint configs, CI files.

- **Branching** - default branch, naming rules, forbidden direct pushes.
- **PR requirements** - template fields, required reviewers via `CODEOWNERS`, required approvals, required CI checks.
- **Local quality gates** - pre-commit hooks, linters, formatters, exact commands.
- **Test commands** - unit / integration / full suite / single file - exact commands cited from `package.json` scripts, Makefile, language conventions.
- **CI shape** - what runs on PR open vs merge; approximate stages; known slowness/flake.
- **Module owners** - from `CODEOWNERS` and, where helpful, recent committers (read-only `git log` / `git shortlog`).
- **Communication channels** - Slack/Teams/mailing list referenced in repo - cite source, do not invent.
- **Common rejection reasons** - patterns visible in `CONTRIBUTING.md`, PR template, lint configs, recent merged PRs. Cite source.
- **Reference example PRs** - linked from `README`, `CONTRIBUTING`, or PR template; otherwise `unknown - not discoverable from the repo` (do not invent PR numbers).
- **First-PR safe zones** - cross-reference Step 7 hotspots. List 2-3 well-tested, low-churn, narrow-blast areas; list 2-3 areas to avoid first. When the repo cannot honestly supply that many (nothing is tested), list what qualifies and say why the rest does not.

Use skill: `dependency-impact-analysis` when the user names a specific candidate change for their first PR, to estimate blast radius; a bare file name becomes the smallest plausible change to that file's public surface, stated in the rationale, and a module-level scope focus alone does not trigger it. Its Impact rows fold into the First-PR Safe Zones / Avoid rationale for that candidate; its migration, deployment-order, and cross-team notification sections are not emitted (this report maps, it does not plan). A clean result is named in `Checked clean:`.

### Step 12 - Synthesize Recommendations and Summary

From Steps 2-11, produce `## Onboarding Recommendations` - the subsections whose tag list contains the active mode, plus First-Day Checklist and First-Week Knowledge Gaps (cap 5 each) - and `## Summary`: 3-5 bullets on architectural strengths, primary risk areas, the recommended first-PR target when the mode is `first-pr`, and the biggest first-week knowledge gaps. Invent nothing here that earlier steps did not establish.

## Output Format

```markdown
# Codebase Onboarding Report

**Mode:** [focus mode]{ (assumed)} | **Scope focus:** [module, or none] | **Pain points:** [list, or none]

## System Summary

[One paragraph from README / repo context, or `unknown - repo does not declare purpose`]

## Stack

| Concern    | Technology              | Source              |
| ---------- | ----------------------- | ------------------- |
| Language   | [e.g., Go 1.25]         | Declared / Inferred |
| Framework  | [Gin + GORM]            | Declared / Inferred |
| Build      | [Go modules]            | Declared / Inferred |
| Test       | [testify + mockery]     | Declared / Inferred |
| Database   | [PostgreSQL via GORM]   | Declared / Inferred |
| Async/Jobs | [Asynq (Redis)]         | Declared / Inferred |
| Deployment | [Docker + GH Actions]   | Declared / Inferred |
| Stack Type | [backend / frontend / fullstack] | Inferred            |

[`no stack-specific onboarding atomic - generic guidance applied` when Step 2 matched no row, or the matched atomic did not resolve; omit the line otherwise]

## Repository Structure

[directory map - top 2-3 levels with one-line annotations]

**Where to look first:** [2-3 paths with reason]

**Safe to skip initially:** [vendored, generated, fixtures, deprecated]

## Architecture

**Pattern:** [backend: Layered / Clean / Modular monolith / Vertical slice / Microservice / Event-driven / None established | frontend: Feature-based / Atomic Design / Route-based / Module-based / Monolith integration / None established - name one per applicable `Stack Type` half]

**Evidence:** [2-3 paths / naming observations]

### Modules

| Module | Responsibility | Data Owned | Dependencies | Entry Points | Data Access |
| ------ | -------------- | ---------- | ------------ | ------------ | ----------- |

### External Integrations

| Service | Integration code | Credentials | Failure handling |
| ------- | ---------------- | ----------- | ---------------- |

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

### Findings

Order findings High -> Medium -> Low. Publish every High; cap Medium and Low together at the 8 most load-bearing (3 under mode compression), closing the section, when anything was folded, with one line naming how many and which delegates they came from. For each:

- **[Severity]** [High | Medium | Low, keeping the delegate's own label alongside when it emitted one - `[Must]` ranks High, `[Recommend]` Medium] - [short label]
- **Location:** [the delegate's anchor as emitted - `file:line`, a `symbol`, `caller:line -> callee:line`, `cause:line -> symptom:line`, an entry point or layer with other sites in parentheses, or a module or edge]  **Signal:** [observed; a guardrail finding appends its `Drift:` value, a complexity finding its `Measured:` value]  **Risk:** [what breaks]  **Source:** [delegate(s) that flagged it, or `direct scan` for a Step 7 finding no delegate produced - High when it risks incorrect behaviour, data loss, or a security hole; Medium when it impairs recovery or diagnosis; Low otherwise]

`Checked clean:` [delegates that ran and found nothing; omit when none did]

`Not assessed:` [delegate - reason, for one that ran but could not judge; omit when none]

## Common Pitfalls

- **Skipped/flaky tests:** [paths + marker; every bullet below takes `none observed` when nothing was found, except where it says omit]
- **Hidden side effects:** [module-level init, package `init()`, auto-registration]
- **Legacy / deprecated:** [paths]
- **Slow tests:** [paths + tag + how excluded]
- **TODO/FIXME density:** [paths and approximate count; `none - <N> in total, no cluster` when low]
- **Docs that contradict the code:** [claim, its source, what the code does; omit if none found]
- **Other documented gotchas:** [cite source]

## Operational Context

| Concern            | Details |
| ------------------ | ------- |
| Local setup        | [summary - full in Local Quickstart] |
| CI on PR / merge   | [summary - full in Contribution Workflow] |
| Deploy target      | [platform / mechanism] |
| Config             | [strategy] |
| Observability      | [`sufficient - no gaps found` \| `<N> gaps (<H> High) - see Tech Debt`] |
| Migration strategy | [how / when migrations run] |

## Local Quickstart

**Prerequisites:** [language version, services, system tools - cite source files]

**Bootstrap (in order):**

```
[command 1 - e.g., cp .env.example .env]
[command 2 - e.g., uv sync]
[command 3 - e.g., docker compose up -d postgres redis]
[command 4 - e.g., make migrate]
[command 5 - e.g., make seed]
[command 6 - e.g., make dev]
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
| Default branch         | [`git symbolic-ref refs/remotes/origin/HEAD`, else the branch CI, `CONTRIBUTING`, or `README` treat as the merge target; `unknown - not discoverable from the repo` if neither resolves] |
| Branch naming          | |
| PR requirements        | |
| CODEOWNERS             | [`none - <evidence>` if absent] |
| Module owners          | [from CODEOWNERS / recent committers; `none - <evidence>` if absent] |
| Local quality gates    | [exact commands] |
| Test commands          | [unit / integration / suite / single file] |
| CI pipeline            | [PR vs merge; slowness/flake] |
| Channels               | [`none - <evidence>` if absent] |
| Common rejection reasons | [cite source] |
| Reference example PRs  | [`unknown - not discoverable from the repo` when nothing links one] |

### First-PR Safe Zones (cap 3)

| Area | Why safe | Suggested entry file |
| ---- | -------- | -------------------- |

### Avoid for First PR (cap 3)

| Area | Why to wait |
| ---- | ----------- |

## Onboarding Recommendations

Emit a subsection only when its tag list contains the active mode; untagged subsections appear in every mode. Ordering: `first-pr` leads with Mission Framing then First-PR Playbook; `architect-survey` leads with First-Week Knowledge Gaps; `full` keeps template order.

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
- [ ] Step 2: `stack-detect` ran; stack atomic loaded, or no-atomic fallback noted under Stack table; signals merged into Stack, Repository Structure, Local Quickstart, Key Patterns, Tech Debt; System Summary captured or marked unknown
- [ ] Step 3: directory map plus "Where to look first" and "Safe to skip initially"
- [ ] Step 4: architecture pattern classified with cited evidence
- [ ] Step 5: modules table; primary flow traced (pain-point or scope flow when given)
- [ ] Step 6: patterns table cites real paths; Domain Knowledge tables capped at 5, each cited
- [ ] Step 7: tech debt findings ordered High -> Medium -> Low with concrete locations; pitfalls flagged with markers and paths; each known pain point given a verdict from the enum (table omitted when none given)
- [ ] Step 8: Operational Context populated
- [ ] Step 9: Local Quickstart commands cited from real files; missing prerequisites flagged as documentation gaps
- [ ] Step 10: ecosystem unknowns marked, not invented
- [ ] Step 11: contribution workflow with exact commands, channels, rejection reasons (or `none - <evidence>`); First-PR Safe Zones and Avoid each 2-3 items
- [ ] Focus mode honored: emphasized sections full depth, rest compressed, no section dropped; subsection tags applied; First-Day Checklist and First-Week Gaps each capped at 5
- [ ] Delegates loaded where their step directs (`architecture-guardrail` Step 4 in audit mode, `backend-coding-standards` Step 6 when `Stack Type` is backend or fullstack, `complexity-review` Step 7, `ops-observability` Step 8, `dependency-impact-analysis` Step 11 when a candidate was named); each that ran clean is named in `Checked clean:`, each that could not judge in `Not assessed:`
- [ ] Step 12: Onboarding Recommendations and Summary produced from earlier steps
- [ ] No invented paths, modules, commands, URLs, channels, PR numbers, or examples

## Avoid

- Inventing file paths, module names, commands, env values, dashboard or environment URLs
- Generating refactoring or migration plans (this produces a map, not a roadmap)
- Commenting on pure style or formatting (whitespace, line length, quote style) as tech debt - a delegate's structural-drift finding is not style; focus on structural and operational risk
- Over-exploring vendor, node_modules, build output
- Producing an exhaustive inventory instead of a scannable summary
- Recommending a first-PR area without cross-referencing hotspots and CODEOWNERS
