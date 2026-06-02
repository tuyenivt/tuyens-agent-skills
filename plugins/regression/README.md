# Tuyen's Agent Skills - Regression

Opt-in plugin that owns **outside-in regression testing across many services**. A dedicated test repo (e.g. `autotest/`) sits outside every service repo; `.regression/` at its root holds services, flows, compose, seeds, Playwright scenarios, and per-run reports. The plugin treats services as black boxes (build context + ports + env + healthcheck + declared role), composes them, seeds them, drives them from outside via Playwright, captures a verdict, tears everything down with `-v`.

**Polyrepo-only.** The plugin does not run inside a service repo, does not piggyback on a monolith repo, and does not coexist with the code it tests. Regression is QA work; QA sits outside the system under test.

**Playwright-only.** One runtime covers HTTP (`request` fixture), browser (`page` fixture), WebSocket (native), and gRPC (standard JS clients). DB read-after-write assertions use Node drivers (`pg`, `mysql2`, `mongodb`) inside tests. Unit and integration tests remain owned by per-stack `task-*-test` skills.

**Stack-agnostic by construction.** Every container is classified into one of three structural roles - **Frontend Service**, **Backend Service**, **Database** - via user-declared structural metadata. The plugin never framework-detects Spring vs FastAPI vs Express vs Rails.

**Codemap is optional and authoring-time only.** `regression-flow-extract` reads symlinked sibling `.codemap/graph.json` files (under `.regression/.cache/codemap/`) during `/task-regression-discover` to enrich flow suggestions. Once `flows.yaml` is committed, the suite runs without any codemap read. `.regression/` is the single source of truth.

Requires the `core` plugin (for `behavioral-principles`, `stack-detect`). No other plugin in this marketplace depends on `regression`.

## Install

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install regression@tuyens-agent-skills --scope project
```

Run the installs from the dedicated test repo's root (the polyrepo sibling that hosts `.regression/`), not from a service repo.

## What you get

```
.regression/
  config.json                       # committed: layout, parallelism, timeouts, ports, profiles, fail-fast=false
  services.yaml                     # committed: services keyed by role (Frontend/Backend/Database) + source (sibling-path | git | image)
  flows.yaml                        # committed: named flows + steps + services touched + assertions hints
  docker-compose.regression.yml     # committed: scaffold compose (services, networks, volumes, healthchecks)
  docker-compose.override.yml       # gitignored: local overrides (developer secrets, port shifts)
  seeds/                            # committed: SQL/JSON seed files, idempotent, ordered by 00-init/10-domain/...
  scenarios/                        # committed: Playwright .spec.ts files
    api/                            # HTTP-only flows (uses request fixture)
    browser/                        # UI flows (uses page fixture)
    mixed/                          # API setup + browser assertion in one test
  playwright.config.ts              # committed: projects, retries, trace, reporters
  package.json                      # committed: pinned playwright + DB drivers
  package-lock.json                 # committed: deterministic installs
  fixtures/                         # committed: shared page objects, request helpers, factories
  reports/                          # gitignored: per-run output (junit.xml, summary.md, traces, videos)
  runs/                             # gitignored: per-run state (run-id, compose project name, timings)
  .cache/                           # gitignored: cloned git sources, downloaded codemap snapshots
  .env.example                      # committed: required env var list
```

Commit `services.yaml`, `flows.yaml`, `docker-compose.regression.yml`, `seeds/`, `scenarios/`, `playwright.config.ts`, `package.json`, `package-lock.json`, `fixtures/`, `.env.example`, `config.json`. Once committed, teammates clone the test repo and run `/task-regression` with no further discovery needed.

**Recommended `.gitignore` additions:**

```
.regression/reports/
.regression/runs/
.regression/.cache/
.regression/docker-compose.override.yml
```

## Workflow Skills

| Skill                        | Description                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `task-regression`            | **Headline run.** End-to-end: preflight, resolve compose profile, mint a per-run ID, `docker compose up -d --build --wait`, apply seeds in order, run Playwright scenarios, collect JUnit XML and traces into `reports/<runId>/`, classify failures, teardown with `down -v --remove-orphans` (trap-guarded). Exit non-zero only on real-bug-classified failures.            |
| `task-regression-discover`   | **Build or refresh `.regression/`.** One-shot, idempotent. Asks the user to declare each service's role (Frontend / Backend / Database) and `source` (sibling-path / git / image), gathers structural metadata, reads optional symlinked codemap graphs + OpenAPI specs + git history to propose flows, writes `services.yaml` + `flows.yaml` + compose + seed skeletons. Never silently overwrites committed flows. |
| `task-regression-scenario`   | **Scaffold a Playwright scenario.** Resolves a named flow from `flows.yaml`, infers `kind: api \| browser \| mixed` from the flow's services and steps, emits `scenarios/<kind>/<flow>.spec.ts` with idempotent setup, golden-path assertions, negative-path stubs, and data-factory imports. Lint + `npx playwright test --list` dry-run. User reviews before commit.       |

### When to use which

| You want to... | Use |
| --- | --- |
| Stand up `.regression/` for the first time | `/task-regression-discover` |
| Refresh `services.yaml` / `flows.yaml` after sibling-repo changes | `/task-regression-discover` (run manually after pulls; no hooks in v1) |
| Add a new scenario for a flow that already exists in `flows.yaml` | `/task-regression-scenario "<flow-name>"` |
| Run the full regression suite locally | `/task-regression` |
| Run a subset (smoke, one tag) | `/task-regression --grep @smoke` |
| Run in CI against pinned image digests | `/task-regression --profile pinned-images` |

## Atomic Skills

Atomic skills are hidden from the slash menu (`user-invocable: false`) and composed by the workflow skills above.

| Skill                              | Description                                                                                                                                                                                                                                                                              |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regression-service-inventory`     | Role-based structural Q&A (Frontend / Backend / Database). Builds `services.yaml` from user-declared metadata: `source` (sibling-path / git / image), HTTP port, healthcheck command, env vars, `depends_on`, DB engine + version + initial-schema source. The only place `stack-detect` is allowed - and only as a *suggestion source* for Dockerfile defaults. |
| `regression-flow-extract`          | Authoring-time flow suggester. Reads symlinked sibling `.codemap/graph.json` files, OpenAPI specs in declared service paths, and recent git history to propose ranked flows typed `api \| browser \| mixed`. Output is human-reviewed and frozen into `flows.yaml`; never read at runtime.   |
| `regression-compose-build`         | Emits `docker-compose.regression.yml` with healthchecks, named volumes, isolated network, and two profiles (`local-build` for sibling-path / git sources, `pinned-images` for `image` sources). Profile selection: `--profile` flag -> env var -> `CI=true` auto-detect -> `local-build` default. |
| `regression-seed-strategy`         | Per-engine seed patterns. Writes seed templates keyed by Database `engine` (postgres / mysql / mariadb / mongodb / sqlserver / sqlite / etc.). Seeds apply directly to the DB container via engine-native tooling (`psql`, `mysql`, `mongoimport`, `sqlcmd`, `sqlite3`), bypassing the backend's migration tool. |
| `regression-scenario-author`       | Playwright scenario authoring template. `kind: api \| browser \| mixed`. Golden path + at least one explicit negative path (self-check fails if absent). Idempotent setup, data-factory imports, bounded read-after-write retry (max 5s, 200ms backoff). Page Object Model for browser flows. |
| `regression-runner`                | Ephemeral run lifecycle. `npm ci` if `package-lock.json` changed -> clone/update `git`-sourced services in `local-build` -> `docker compose -p regression-<runId> up -d --build --wait` -> apply seeds in order -> `npx playwright test --reporter=junit,line` -> collect reports -> teardown. Trap-guarded `down -v --remove-orphans` on Ctrl+C. |
| `regression-data-isolation`        | Prevents "passes locally, fails in CI". Per-run compose project name (`regression-<runId>`), ephemeral named volumes, deterministic seed ordering, frozen wall-clock (`TZ` env + freezing libs), unique tenant/user IDs derived from `run-id`.                                              |
| `regression-report-format`         | JUnit XML normalization + Markdown verdict. Produces `reports/<runId>/summary.md` with pass/fail/skip counts, per-flow verdict, top failure clusters (collapses N scenarios failing with the same root error into one entry), and links to traces/videos/screenshots.                          |
| `regression-flakiness-triage`      | Classifies each failure into 4 buckets: `real bug \| flake \| infra down \| seed drift`. Emits bucket counts at the top of `summary.md`. If the `flake` ratio exceeds threshold, explicitly tells the user "this suite is rotting, fix infra/seeds first; don't chase the assertions yet." |
| `regression-env-vars`             | Env-var plumbing for sensitive compose configuration: never commit values, always reference `${VAR}`, ship `.env.example`, document overrides via the gitignored `docker-compose.override.yml`. Suggests 1Password / Doppler / GCP Secret Manager patterns. |

## Skill Dependency Index

| Workflow                     | Atomic skills used                                                                                                                                                                                                                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-regression-discover`   | `behavioral-principles`, `stack-detect` (suggestion-only), `regression-service-inventory`, `regression-flow-extract`, `regression-compose-build`, `regression-seed-strategy`, `regression-env-vars`                                                                          |
| `task-regression-scenario`   | `behavioral-principles`, `regression-scenario-author`                                                                                                                                                                                                                                  |
| `task-regression`            | `behavioral-principles`, `regression-data-isolation`, `regression-runner`, `regression-report-format`, `regression-flakiness-triage`                                                                                                                                                   |

`behavioral-principles` and `stack-detect` live in the `core` plugin (required). `regression-flow-extract` reads `codemap-schema` / `codemap-query` opportunistically when sibling `.codemap/` symlinks are present, but never requires the `codemap` plugin to be installed.

## Usage Examples

**First-time discover (polyrepo layout):**

```
~/work/
  gateway-api/        # service repo
  order-service/      # service repo
  payment-service/    # service repo
  autotest/           # this is where you run the commands

cd ~/work/autotest
/task-regression-discover
```

Walks you through declaring each service's role and `source`, gathers structural metadata, scans optional symlinked codemap graphs + OpenAPI specs + recent git history to propose flows, and writes `.regression/services.yaml` + `flows.yaml` + `docker-compose.regression.yml` + seed skeletons. Diff is shown for confirmation before any file lands.

**Scaffold a scenario for a named flow:**

```
/task-regression-scenario "checkout-order"
```

Reads the `checkout-order` entry from `flows.yaml`, infers `kind` from the services touched (UI + API -> `mixed`), and writes `.regression/scenarios/mixed/checkout-order.spec.ts` with idempotent setup, golden-path assertions, and a negative-path stub. Run `npx playwright test --list` to confirm it parses; edit, then commit.

**Headline run (local development):**

```
/task-regression
```

Mints a per-run ID, `docker compose -p regression-<runId> ... up -d --build --wait`, applies seeds in order, runs all Playwright scenarios, classifies failures, writes `reports/<runId>/summary.md`, tears down with `down -v --remove-orphans`. Exits non-zero only on real-bug failures.

**Targeted run with the smoke subset:**

```
/task-regression --grep @smoke
```

Same lifecycle, but Playwright only picks up scenarios tagged `@smoke`. Useful for pre-push checks.

**CI invocation (prose, no YAML generator):**

Run `/task-regression --profile pinned-images` from the test repo's root in your CI job. The `pinned-images` profile uses the `image:` references in `services.yaml` (registry digests recommended - no `latest` tags), skips local build, and reproduces the exact images shipped through your release pipeline. Cache `.regression/node_modules` keyed on `package-lock.json` hash. Upload `reports/<runId>/` as a CI artifact. Fail the job on non-zero exit. No CI YAML template ships with the plugin - the lifecycle is short enough that hand-wiring per CI provider stays readable.

## Maintenance hooks - deferred

**v1 ships no hooks.** The autotest repo sits outside every service repo, so a hook installed inside the autotest repo can only observe events in the autotest repo itself - it cannot fire on commits in sibling `gateway-api/`, `order-service/`, etc. But those sibling-side commits (new endpoint, new env var, removed route, changed Dockerfile, swapped DB engine) are exactly what should trigger rediscovery.

The right long-term shape is a *companion* install in each service repo that writes a small `.regression-hints.json` marker the autotest repo picks up on the next `/task-regression-discover`. That's two installation surfaces, two skills to maintain, and the heuristics for "what counts as regression-relevant" are unproven.

**For now: rerun `/task-regression-discover` manually after sibling-repo pulls.** The polyrepo rhythm already involves multi-repo `git pull`s; adding one explicit rerun-discover step is acceptable.

**v2 candidate:** a separate `regression-hooks` companion plugin teams install per service repo, gated by data on which signals actually warrant rediscovery.

## Requirements

- **Docker** with `docker compose` v2 (the `docker compose` subcommand, not legacy `docker-compose`).
- **Node 20+** and `npx` on PATH inside the test repo. Python / Ruby / Go / .NET projects need Node 20+ in `.regression/` even though the app is in a different language - this is the only Node touchpoint; the app stays in its own language. Same pattern as `codemap` requiring Python on non-Python projects.
- **git** on PATH (for `git`-sourced services and discovery-time history scanning).
- The `core` plugin installed in the same test repo (`behavioral-principles`, `stack-detect`).
- **Optional:** sibling service repos' `.codemap/graph.json` symlinked under `.regression/.cache/codemap/<service>/graph.json` to enrich discovery-time flow suggestions. Never required, never read at runtime.

## License

Same as the parent marketplace.
