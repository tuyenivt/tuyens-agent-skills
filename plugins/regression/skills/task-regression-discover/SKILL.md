---
name: task-regression-discover
description: Build or refresh .regression/ workspace - services.yaml, flows.yaml, compose, seeds, .env.example. Role-based polyrepo discovery, idempotent.
metadata:
  category: testing
  tags: [regression, discovery, services, flows, compose, polyrepo]
  type: workflow
user-invocable: true
---

# Task: Regression Discover

One-shot, idempotent discovery. Builds or refreshes the committed `.regression/` workspace from user-declared service roles. Codemap, OpenAPI specs, and git history are consulted only here, only as suggestion sources, and never at runtime.

`.regression/` is the single source of truth for `task-regression`. Once committed, the suite runs even if codemap drifts or vanishes.

## When to Use

- First-time adoption: scaffold `.regression/` in a dedicated test repo (e.g. `autotest/`) sitting outside every service repo.
- Topology change: service added/removed, port shift, new env var, swapped DB engine, Dockerfile rewrite.
- After sibling-repo pulls when fresh flow suggestions are wanted.

**Not for:**
- Running the suite -> `task-regression`.
- Authoring a single Playwright scenario -> `task-regression-scenario`.
- Unit/integration tests -> `task-<stack>-test`.

## Inputs

| Input | Notes |
| --- | --- |
| `[path]` | Test repo root (default `.`). `.regression/` lives here. |
| `--refresh-flows` | Re-run flow extraction. Existing entries never silently overwritten. Conflict handling described in Step 4. |
| `--services <list>` | Comma-separated names. **Scopes Step 3 inventory Q&A only.** Step 4 flow extraction always runs across all services (flows are cross-service by definition). |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Declare Services in Scope

For each service the user wants under test, gather:

- **Role:** `frontend` / `backend` / `database`. Decide by **what the service does at runtime**, not by name: any HTTP/JSON application service is `backend` even if named `*-gateway` / `*-api`. Brokers (Kafka, RabbitMQ), caches (Redis), search indexes, network proxies / service-mesh gateways are out of v1 scope - note them, exclude them.
- **Source type:** `sibling-path` / `git` / `image`.
- **Source value:** relative path (`../order-service`), git URL + ref, or pinned image digest (`ghcr.io/acme/svc@sha256:...`).

Surface the in-scope list back for confirmation before Step 3.

**Out-of-scope dependents.** If an in-scope backend's env references an excluded service (e.g. `REDIS_URL`), ask the user explicitly: (a) re-declare the dependency as one of the three roles, (b) keep the env var as an external reference satisfied at run time, or (c) drop the dependency for regression scope. Record the decision in the report.

**Async sinks.** After the in-scope service list is confirmed, ask: "Does any in-scope service publish to a Kafka topic, write to S3, send outbound email, POST to an external webhook, or enqueue to SQS, that you want the suite to assert on?" For each yes, gather `kind` / `target` / `consumerGroup` (kafka) / `notes`; record under `services.yaml#sinks:`. Without this prompt, async-sink flows fall through silently (`regression-scenario-author` Rule 9 deflects to HTTP/DB assertions). Sinks are consumed by `regression-sink-asserter` at scenario time.

### Step 3 - Per-Service Structural Q&A

Use skill: `regression-service-inventory`.

For each declared service (scoped by `--services` if provided), gather role-specific structural metadata - port, healthcheck command, env vars, `depends_on`, database engine/version/initial-schema. `regression-service-inventory` owns the `services.yaml` schema; this workflow consumes its output.

For `image`-only services, suggestions come from `docker image inspect`; the user confirms.
For `sibling-path` services missing a Dockerfile, `regression-service-inventory` may invoke `stack-detect` *as a suggestion source* - the user owns the final file. The skill never silently writes into a sibling repo.

Output: in-memory `services.yaml` candidate, validated against the inventory schema.

### Step 4 - Extract Cross-Service Flows

Use skill: `regression-flow-extract`.

Inputs in priority order; fall through silently when a tier is absent:

1. Symlinked sibling `.codemap/graph.json` files under `.regression/.cache/codemap/`.
2. OpenAPI specs in declared service paths.
3. Recent git history (last 30 commits per sibling-path service).

If all three are absent, emit one skeleton candidate per backend tagged `evidence: skeleton`; do not invent endpoint names.

For each ranked candidate, the user accepts or rejects. Accepted candidates are appended to `flows.yaml`. **Conflict handling for `--refresh-flows`:** when a new candidate matches an existing flow by name but differs in `hops` or `observableOutcome` (e.g. renamed endpoint), surface as a *change candidate* with three explicit choices: replace in place, mark the old entry stale and add the new alongside, or skip. Default: surface and stop; never silently overwrite.

### Step 5 - Build Compose Scaffold

Use skill: `regression-compose-build`.

Emits `docker-compose.regression.yml` with healthchecks on every service, two profiles (`local-build`, `pinned-images`), an isolated bridge network, and named volumes per database.

**Profile population.** Each service contributes to whichever profile its `source.type` supports. `sibling-path` / `git` populate `local-build`; `image` populates `pinned-images`. A service with only one source type appears in only one profile - the other profile excludes it silently; this is expected. Services declared with both an `image` ref and a `sibling-path` / `git` source appear in both profiles per the inventory schema (`regression-service-inventory` owns the multi-source shape).

If `docker-compose.regression.yml` already exists, show unified diff and ask: keep mine / take new / merge.

### Step 6 - Template Seeds

Use skill: `regression-seed-strategy`.

Writes engine-appropriate seed templates under `.regression/seeds/00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`. Seeds apply directly to the DB container, bypassing the backend's migration tool. Templates use idempotent insert idioms and deterministic literal IDs.

**Initial schema responsibility.** The backend may own schema via Flyway / Liquibase / Alembic / etc. `regression-seed-strategy` resolves the initial-schema mode (`sql-dump` / `migrations` / `none`) from `services.yaml`; this workflow does not duplicate that logic. If no `database` role was declared, skip this step entirely and record the skip in the report.

### Step 7 - Plumb Env Vars

Use skill: `regression-env-vars`.

Writes `.env.example` listing every `${VAR}` referenced in `services.yaml` / `docker-compose.regression.yml`. Documents `docker-compose.override.yml` (gitignored) as the local override mechanism. No sensitive values land in committed files.

### Step 8 - Write Artifacts and Confirm

Persist under `.regression/`:

- `services.yaml` (new or replaced after diff)
- `flows.yaml` (additions / change candidates resolved per Step 4)
- `docker-compose.regression.yml` (after Step 5 diff)
- `seeds/**` (templates; skipped if no database role)
- `.env.example`
- `config.json` if missing (defaults: layout, parallelism, timeouts, fail-fast=false)

Surface `.gitignore` recommendations - never auto-edit. Show a final summary diff of all written / changed files. User confirms before the workflow exits.

## Output Format

```markdown
# Regression Discover Report

**Mode:** {first-time scaffold | refresh}
**Generated at:** {ISO timestamp}
**Workspace:** .regression/

## Services

| Name | Role | Source | Engine | Port | Healthcheck |
| --- | --- | --- | --- | --- | --- |
| web | frontend | sibling-path ../web | - | 3000 | curl /healthz |
| api | backend | sibling-path ../api | - | 8080 | curl /healthz |
| db | database | image postgres@sha256:... | postgres 16 | 5432 | pg_isready |

## Out-of-scope dependencies recorded

- {name}: {decision - re-declare / external / dropped}

## Flows accepted ({count})

- {name} ({kind}): {entry} -> {hops} -> {observable}

## Flows surfaced but rejected / changed ({count})

- {name}: {reason} ({skeleton | change candidate resolved as <choice>})

## Artifacts written

| File | Status |
| --- | --- |
| `.regression/services.yaml` | new / updated (diff above) / unchanged |
| `.regression/flows.yaml` | +{N} entries / unchanged |
| `.regression/docker-compose.regression.yml` | new / updated / unchanged |
| `.regression/seeds/**` | {N} files / skipped (no database role) / unchanged |
| `.regression/.env.example` | new / updated |
| `.regression/config.json` | new / unchanged |

## Recommended .gitignore additions

```
.regression/reports/
.regression/runs/
.regression/.cache/
.regression/docker-compose.override.yml
.regression/.env
```

## Next

- `/task-regression-scenario "<flow-name>"` to scaffold a Playwright scenario.
- `/task-regression` to run the suite end-to-end.
- Re-run `/task-regression-discover --refresh-flows` after sibling pulls.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: roles assigned by runtime behavior (not by name); excluded services noted; out-of-scope dependents resolved with recorded decision; async sinks prompted and recorded under `services.yaml#sinks`; user confirmed the in-scope list.
- [ ] Step 3: `regression-service-inventory` gathered structural metadata for every in-scope service (scoped to `--services` if provided); no role auto-detected.
- [ ] Step 4: `regression-flow-extract` ran across all services with available evidence tiers; skeletons emitted when no inputs; change candidates surfaced with explicit choice for any name-collision; `flows.yaml` never overwritten silently.
- [ ] Step 5: `regression-compose-build` emitted both profiles with healthchecks; per-source-type profile population honored; diff shown before overwrite.
- [ ] Step 6: `regression-seed-strategy` templated seeds per engine with idempotent idioms and deterministic IDs - or skipped because no database role was declared.
- [ ] Step 7: `regression-env-vars` wrote `.env.example`; no sensitive values committed.
- [ ] Step 8: all artifacts persisted under `.regression/`; final diff confirmed by user; `.gitignore` additions surfaced, never auto-applied.

## Avoid

- Auto-detecting service roles from filesystem layout. The user declares roles.
- Reading codemap / OpenAPI / git history at runtime. Discovery-time only.
- Silently overwriting committed `services.yaml` / `flows.yaml`. Always diff and confirm.
- Inventing endpoint names. Emit a skeleton candidate tagged `evidence: skeleton`.
- Writing Dockerfiles into sibling service repos without explicit confirmation.
- Committing `:latest` image refs. Pin by digest.
- Inline secrets in `services.yaml` or `docker-compose.regression.yml`. Always `${ENV_VAR}`.
- Scaffolding `.regression/` inside a service repo.
