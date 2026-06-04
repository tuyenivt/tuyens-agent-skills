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
| `task-regression-scenario`   | **Scaffold a Playwright scenario.** Two modes: pass an existing flow name from `flows.yaml`, or pass `--from <text-or-path>` with a QA ticket / incident summary / user report - the workflow drafts a new `flows.yaml` entry (no fabricated endpoints, evidence required), then emits `scenarios/<kind>/<flow>.spec.ts` with golden + negative paths. Lint + `npx playwright test --list` dry-run. User reviews before commit. |
| `task-regression-plan`       | **Export a human-readable test plan.** Read-only join of `flows.yaml` + `scenarios/**/*.spec.ts` into one Markdown document at `.regression/test-plan.md`. Per-flow: entry, steps, expected outcome, negative cases, evidence, and a coverage column (`covered` / `no-spec` / `kind-mismatch` / `orphan`). Group by flow kind, service, or none. Surfaces `<USER FILL>` markers as gaps. Never mutates anything. |

### When to use which

| You want to... | Use |
| --- | --- |
| Stand up `.regression/` for the first time | `/task-regression-discover` |
| Refresh `services.yaml` / `flows.yaml` after sibling-repo changes | `/task-regression-discover` (run manually after pulls; no hooks in v1) |
| Add a new scenario for a flow that already exists in `flows.yaml` | `/task-regression-scenario "<flow-name>"` |
| Add a regression guard from a QA ticket / incident report / user story | `/task-regression-scenario --from "<narrative>"` or `--from <file-path>` |
| Export a readable test plan for QA / release / audit (with coverage column) | `/task-regression-plan` |
| Run the full regression suite locally | `/task-regression` |
| Run a subset (smoke, one tag) | `/task-regression --grep @smoke` |
| Run in CI against pinned image digests | `/task-regression --profile pinned-images` |

## Atomic Skills

Atomic skills are hidden from the slash menu (`user-invocable: false`) and composed by the workflow skills above.

### Core lifecycle and inventory

| Skill                              | Description                                                                                                                                                                                                                                                                              |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regression-service-inventory`     | Role-based structural Q&A (Frontend / Backend / Database). Builds `services.yaml` from user-declared metadata: `source`, HTTP port, healthcheck, env vars, `depends_on`, DB engine + version + initial-schema source, optional resource caps, optional async `sinks`. The only place `stack-detect` is allowed - and only as a suggestion source for Dockerfile defaults. |
| `regression-flow-extract`          | Authoring-time flow suggester and schema owner of `flows.yaml`. Reads symlinked sibling `.codemap/graph.json` files, OpenAPI specs, and recent git history to propose ranked flows. Schema fields: `name`, `kind`, `direction`, `owner` (required), `status` (active/deprecated/stale), `entryPoint`, `hops`, `observableOutcome`, `evidence`, `flowLabels`, `checks`, `latencyBudget`, `clock`, `archetype`, `sinks`, `a11y`, `securityHeaders`. |
| `regression-compose-build`         | Emits `docker-compose.regression.yml` with healthchecks, named volumes, isolated network, two profiles (`local-build`, `pinned-images`), optional resource caps, and optional sink containers (Kafka, Mailhog, Minio, OTel collector, webhook listener). |
| `regression-seed-strategy`         | Per-engine seed patterns. Writes seed templates keyed by Database `engine` (postgres / mysql / mariadb / mongodb / sqlserver / sqlite). Seeds apply via engine-native tooling (`psql`, `mysql`, `mongosh`, `sqlcmd`, `sqlite3`), bypassing the backend's migration tool. DB service name and DB name resolve from `services.yaml`, never literals. |
| `regression-scenario-author`       | Playwright scenario authoring template. `kind: api \| browser \| mixed` + `direction: default \| inverted`. Golden + at least one explicit negative path. Idempotent setup, bounded `pollUntil`, POM for browser flows. Reads `checks:` and delegates to check atomics. |
| `regression-runner`                | Ephemeral run lifecycle. `npm ci` (Node-version-keyed stamp) -> sync git sources -> `docker compose up -d --build --wait` -> clock-skew check -> seed in order -> Playwright -> capture `compose.log` -> scrub -> teardown with trap. Matrix/shard-suffixed report dirs. |
| `regression-data-isolation`        | Prevents "passes locally, fails in CI". Per-run compose project name (`regression-<runId>`), ephemeral named volumes, deterministic seed ordering, frozen `TZ`, unique tenant/user IDs derived from `run-id`. |
| `regression-report-format`         | JUnit XML normalization + Markdown verdict. `summary.md` with `## Verdict`, `## Counts` (including `BudgetViolations`), `## Per-Flow` (Owner column), `## Failure Clusters`, `## Trend`, `## Performance`, `## Run Metadata`. Optional GH / GitLab annotations. |
| `regression-flakiness-triage`      | Classifies each failure into 4 buckets: `real bug \| flake \| infra down \| seed drift`. Emits bucket counts at the top of `summary.md`. Rotting-suite gate. |
| `regression-env-vars`             | Env-var plumbing for sensitive compose configuration: never commit values, always reference `${VAR}`, ship `.env.example`, gitignored `docker-compose.override.yml`. Scenario-side secrets via `fixtures/secrets.ts` (allow-list). |
| `regression-preflight`            | Host-side gating: `docker info`, free disk at docker root, declared host port availability, post-`up` host/container clock skew. Stable exit codes 20-23. |

### Coverage checks (opt-in per flow via `checks:`)

| Skill                                | Description                                                                                                                                                                                  |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regression-contract-check`          | OpenAPI / JSON Schema body-shape assertions. `checks: [contract]`. Cached schema under `.regression/fixtures/contracts/`. Mismatch is `real-bug`. |
| `regression-perf-check`              | Per-flow `latencyBudget.p95Ms` enforcement. `checks: [perf]`. Rolling p95 over last 10 runs; OVER status surfaces in report but does NOT block exit. |
| `regression-a11y-check`              | Playwright + axe scan for browser flows. `checks: [a11y]`. WCAG 2.1 AA default. Per-flow `a11y.disable:` suppression. Failure = `real-bug`. |
| `regression-security-headers-check`  | CSP / HSTS / X-Frame / Referrer-Policy / Permissions-Policy assertions. `checks: [security-headers]`. Structural compare, `at-least-as-strict-as` semantics. |
| `regression-observability-check`     | Asserts OTel spans, structured log lines, metric deltas. `checks: [otel-span:<name>]` / `log:<key>` / `metric:<name>`. Spins up an OTel collector in compose. |

### Async / time-travel / archetypes

| Skill                       | Description                                                                                                                                  |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `regression-sink-asserter`  | Asserts on Kafka topics, S3 buckets, SMTP outboxes (Mailhog), outbound webhooks, SQS queues declared under `services.yaml#sinks`. |
| `regression-clock-advance`  | App-side clock advance for cron / scheduled-job tests. Three mechanisms: `libfaketime`, `restart-env`, `admin-endpoint`. Per-scenario reset. |
| `regression-flow-archetypes`| Prebuilt patterns: `oauth-callback`, `signed-upload`, `feature-flag-matrix`, `idempotency-key-retry`, `rate-limit-429`, `cache-invalidation`, `tenant-isolation-cross-read`. |
| `regression-fixture-factory`| Typed builder pattern: `scopedOrder({ status, amount })`, `scopedTenant({ plan })`. Pure builders, no I/O, idempotent within a run. |

### CI / governance

| Skill                       | Description                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `regression-pr-comment`     | Sticky PR / MR comment with verdict + counts + top-3 clusters. GitHub (`gh`) and GitLab (`glab`) backends; one sticky per matrix key. |
| `regression-artifact-scrub` | PII / PCI scrubbing of traces, videos, screenshots, `compose.log` before CI upload. Playwright `mask` selectors + pattern redaction. Opt-in via `config.json#scrub.enabled`. |

## Skill Dependency Index

| Workflow                     | Atomic skills used                                                                                                                                                                                                                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-regression-discover`   | `behavioral-principles`, `stack-detect` (suggestion-only), `regression-service-inventory`, `regression-flow-extract`, `regression-compose-build`, `regression-seed-strategy`, `regression-env-vars` |
| `task-regression-scenario`   | `behavioral-principles`, `regression-scenario-author` (delegates to `regression-contract-check`, `regression-perf-check`, `regression-a11y-check`, `regression-security-headers-check`, `regression-observability-check`, `regression-sink-asserter`, `regression-clock-advance`, `regression-flow-archetypes`, `regression-fixture-factory` per `checks:` / `archetype:` / `sinks:` / `clock:` on the flow) |
| `task-regression-plan`       | `behavioral-principles` (read-only consumer of `flows.yaml` shape from `regression-flow-extract`) |
| `task-regression`            | `behavioral-principles`, `regression-preflight`, `regression-data-isolation`, `regression-runner`, `regression-artifact-scrub`, `regression-report-format`, `regression-flakiness-triage`, optionally `regression-pr-comment` |

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

**Scaffold from a QA ticket or incident report (from-story mode):**

```
/task-regression-scenario --from "INC-2026-04-12: a user retried POST /payments with the same idempotency key and the wallet was debited twice. Fix landed in payment-service on 2026-04-14."
```

Or from a file:

```
/task-regression-scenario --from ./tickets/INC-2026-04-12.md
```

The workflow parses the narrative, validates every referenced service against `services.yaml` (never invents new ones), drafts a `flows.yaml` entry with `<USER FILL>` markers for anything the story didn't state (no fabricated endpoint paths), requires at least one `evidence:` citation (ticket ID, incident date, reporter), and asks for `accept` / `edit` / `reject` before appending to `flows.yaml`. Then scaffolds the matching `.spec.ts` with golden + negative paths derived from the story's failure mode. Resolve the `<USER FILL>` markers and commit.

**Export a test plan (QA / release / audit):**

```
/task-regression-plan
```

Joins `.regression/flows.yaml` with `.regression/scenarios/**/*.spec.ts` and writes `.regression/test-plan.md` - per-flow entry / steps / expected outcome / negative cases / evidence / coverage status (`covered` / `no-spec` / `kind-mismatch` / `orphan`), grouped by flow kind. Read-only - never mutates flows, scenarios, or sibling repos. Pass `--group-by service` to group by entry-point service, or `--out path/to/plan.md` to write elsewhere.

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

## First 10 minutes (worked example)

```bash
# 1. Sibling layout - autotest sits next to the service repos.
$ ls ~/work
gateway-api  order-service  payment-service  autotest
$ cd ~/work/autotest

# 2. Install plugins from the marketplace.
$ claude plugin install core@tuyens-agent-skills --scope project
$ claude plugin install regression@tuyens-agent-skills --scope project

# 3. Discover - declare three services, answer Q&A.
$ claude /task-regression-discover
> ... (interactive) ...
Workspace .regression/ written:
  services.yaml      (3 services: gateway-api, order-service, payment-service + db)
  flows.yaml         (5 candidates accepted; 2 deferred)
  docker-compose.regression.yml
  seeds/00-init/01-schema.sql
  seeds/10-domain/01-tenants.sql
  .env.example

# 4. Inspect the proposed plan before running anything.
$ claude /task-regression-plan
.regression/test-plan.md written. Coverage: 0/5 covered, 5/5 no-spec.

# 5. Scaffold one scenario.
$ claude /task-regression-scenario "checkout-order"
.regression/scenarios/mixed/checkout-order.spec.ts written.
tsc --noEmit: pass. playwright --list: 2 tests discovered.

# 6. Set required env vars.
$ cp .regression/.env.example .regression/.env
$ vi .regression/.env   # fill POSTGRES_PASSWORD, JWT_SIGNING_KEY

# 7. Run the suite.
$ claude /task-regression
Preflight: pass. npm ci: ran (4s). Compose up: 4 healthy (12s).
Seed: 3 files applied. Playwright: 2 scenarios, 2 passed (8s).
.regression/reports/20260604T101530-a1b2c3/summary.md written.
**PASS** - All 2 scenarios green.
Teardown: containers gone, volumes gone, networks gone.
```

Total wall-clock: under 10 minutes including reading the report.

## Troubleshooting

| Symptom | Likely cause | Where to look |
| --- | --- | --- |
| Every run classified `seed-drift` | Mongo seeds named `.json` instead of `.js`, or seed files not under `00-init/`/`10-domain/`/`20-fixtures/`/`99-final/` | `regression-seed-strategy` (extension dispatch in `apply-seed.sh`); check `compose.log` for engine error |
| Every failure classified `infra` | Healthcheck command is wrong; container exits before `--wait` returns | `services.yaml#healthcheck` per service; `docker compose logs <svc>` in `compose.log` |
| `compose` hangs on "unhealthy" | App migrations slower than retries window allow | Increase `healthcheck.retries` or interval in `services.yaml`; or wait for migrations to complete on first boot |
| Same flaky scenario every run | True flake (async race in app) vs. test-side race (timing assertion too tight) | `regression-flakiness-triage` Rule 5 alternation table; bump `pollUntil` `timeoutMs` if test-side |
| `npm ci` runs every invocation | Node version changed between runs (nvm) - stamp now keyed on `node --version` | `regression-runner` Rule 2; check `.regression/node_modules/.install-stamp` first line vs current `node --version` |
| CI artifacts contain PII / real-looking emails | Scrub not enabled, or pattern catalog missing this PII shape | `regression-artifact-scrub` Rule 1 (mask selectors); add patterns under `config.json#scrub.patterns` |
| Reports overwriting each other in matrix CI | `--matrix-key` or `SHARD_INDEX` not set | `task-regression --matrix-key <key>` or export `SHARD_INDEX`; runner suffixes the report dir |
| `unknown check '<token>' in flow` | Typo in `flows.yaml#checks` | Valid tokens: `contract`, `perf`, `a11y`, `security-headers`, `otel-span:<name>`, `log:<key>`, `metric:<name>` |
| Clock-advance scenario leaves clock advanced | `afterEach` reset hook missing in the spec | `regression-clock-advance` Rule 4; add `test.afterEach(() => resetClock(svc))` |
| Sink assertion times out, no message received | Producer not pointed at the compose-network broker, or topic does not exist | `services.yaml#sinks` `target` resolves to broker:topic? Confirm via the broker's UI or `kafka-topics --list` in `compose.log` |
| Owner column shows `_unknown_` | Legacy flow without `owner:` field | `regression-flow-extract` Rule 9 requires `owner:`; add the team slug to the flow entry |

## CODEOWNERS / required-reviewer pattern

Recommend in the test repo's `.github/CODEOWNERS` (or GitLab's `CODEOWNERS`):

```
# .regression/* changes require QA review by default.
/.regression/                           @org/qa-platform

# Flow-prefix routing - per-team ownership without scattering CODEOWNERS lines.
/.regression/flows.yaml                 @org/qa-platform
/.regression/scenarios/**/checkout-*    @org/checkout-squad
/.regression/scenarios/**/payment-*     @org/payments-platform
/.regression/seeds/                     @org/qa-platform @org/dba

# Compose / runner / governance config.
/.regression/docker-compose.regression.yml  @org/qa-platform @org/devex
/.regression/config.json                    @org/qa-platform
```

The flow-level `owner:` field (`regression-flow-extract` Rule 9) is the per-flow source of truth; CODEOWNERS is the GitHub-mechanism enforcement. For routing without prefix conventions, generate a CODEOWNERS block from `flows.yaml#owner` per scenario directory (left as a project script - no atomic ships this).

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
