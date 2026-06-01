---
name: task-regression-discover
description: Build or refresh .regression/ workspace - services.yaml, flows.yaml, docker-compose.regression.yml, seeds/, .env.example. Role-based, polyrepo, idempotent.
metadata:
  category: testing
  tags: [regression, discovery, services, flows, compose, polyrepo]
  type: workflow
user-invocable: true
---

# Task: Regression Discover

One-shot, idempotent discovery workflow. Builds or refreshes the committed `.regression/` workspace from user-declared service roles. Codemap, OpenAPI specs, and git history are consulted only here, only as suggestion sources, and never at runtime.

`.regression/` is the single source of truth for `task-regression`. Once committed, the suite runs even if codemap drifts or vanishes.

## When to Use

- First-time adoption: scaffold `.regression/` in a dedicated test repo (e.g. `autotest/`) that sits outside every service repo.
- Topology change: new service, removed service, port shift, new env var, swapped DB engine, Dockerfile rewrite.
- After sibling-repo pulls when the user wants fresh flow suggestions.

**Not for:**
- Running the suite -> `task-regression`.
- Authoring a single Playwright scenario -> `task-regression-scenario`.
- Unit/integration tests -> `task-<stack>-test`.

## Inputs

| Input | Notes |
| --- | --- |
| `[path]` | Test repo root (default `.`). `.regression/` will live here. |
| `--refresh-flows` | Re-run flow extraction; surface additions to `flows.yaml` for review. Existing entries never silently overwritten. |
| `--services <list>` | Optional comma-separated names to scope inventory Q&A. Default: all declared. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Declare Services by Role

For each service the user wants in scope, gather:

- **Role:** `frontend` / `backend` / `database`. Services that don't fit (brokers, gateways, sidecars) are out of v1 scope - note them but exclude.
- **Source type:** `sibling-path` / `git` / `image`.
- **Source value:** relative path (`../order-service`), git URL, or pinned image ref (`ghcr.io/acme/svc@sha256:...`).

No auto-scan. The user names what is in scope. Surface this list back for confirmation before Step 3.

### Step 3 - Per-Service Structural Q&A

Use skill: `regression-service-inventory`.

For each declared service, gather role-specific structural metadata (port, healthcheck command, env vars, `depends_on`, database engine/version/initial-schema). For `image`-only services, suggest defaults from `docker image inspect`. For `sibling-path` services missing a Dockerfile, `regression-service-inventory` may invoke `stack-detect` as a suggestion source only - the user owns the final file.

Output: in-memory `services.yaml` candidate, validated against the schema in `regression-service-inventory`.

### Step 4 - Extract Cross-Service Flows

Use skill: `regression-flow-extract`.

Inputs in priority order: (a) symlinked sibling `.codemap/graph.json` files under `.regression/.cache/codemap/`; (b) OpenAPI specs in declared service paths; (c) recent git history (last 30 commits per sibling-path service). Emit ranked candidates each typed `api | browser | mixed`.

User accepts/rejects each candidate. Accepted candidates are appended to `flows.yaml`. Existing entries are never silently overwritten; show diff.

### Step 5 - Build Compose Scaffold

Use skill: `regression-compose-build`.

Emit `docker-compose.regression.yml` with healthchecks on every service, two profiles (`local-build`, `pinned-images`), one isolated bridge network, named volumes per database. If a file exists, show unified diff and ask: keep mine / take new / merge.

### Step 6 - Template Seeds

Use skill: `regression-seed-strategy`.

Write engine-appropriate seed templates under `.regression/seeds/00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`. Seeds apply directly to the DB container, bypassing the backend's migration tool. All templates use idempotent insert idioms and deterministic literal IDs.

### Step 7 - Plumb Env Vars

Use skill: `regression-env-vars`.

Write `.env.example` listing every `${VAR}` referenced in `services.yaml` / `docker-compose.regression.yml`. Document `docker-compose.override.yml` (gitignored) as the local override mechanism. No sensitive values land in committed files.

### Step 8 - Write Artifacts and Confirm

Persist under `.regression/`:

- `services.yaml` (new or replaced after diff)
- `flows.yaml` (additions only, per-entry confirmed in Step 4)
- `docker-compose.regression.yml` (after Step 5 diff)
- `seeds/**` (templates)
- `.env.example`
- `config.json` if missing (defaults: layout, parallelism, timeouts, ports, fail-fast=false)
- `.gitignore` recommendations surfaced (never auto-edited)

Show a final summary diff of all written/changed files. User confirms before the workflow exits.

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

## Flows accepted ({count})

- {flow-name} ({kind}): {entry} -> {hops} -> {observable}

## Flows surfaced but rejected ({count})

- {flow-name}: {reason}

## Artifacts written

| File | Status |
| --- | --- |
| `.regression/services.yaml` | new / updated (diff above) / unchanged |
| `.regression/flows.yaml` | +{N} entries / unchanged |
| `.regression/docker-compose.regression.yml` | new / updated / unchanged |
| `.regression/seeds/**` | {N} files / unchanged |
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

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: services declared by role + source; out-of-scope services noted; user confirmed list
- [ ] Step 3: `regression-service-inventory` gathered structural metadata for every declared service; no role auto-detected
- [ ] Step 4: `regression-flow-extract` ran with available inputs; ranked candidates surfaced; user accepted/rejected each; existing `flows.yaml` never overwritten silently
- [ ] Step 5: `regression-compose-build` emitted both profiles with healthchecks; diff shown before overwrite
- [ ] Step 6: `regression-seed-strategy` templated seeds per engine; idempotent idioms used; deterministic IDs
- [ ] Step 7: `regression-env-vars` wrote `.env.example`; no sensitive values committed
- [ ] Step 8: all artifacts written under `.regression/`; final diff confirmed by user; `.gitignore` additions surfaced, not auto-applied

## Avoid

- Auto-detecting service roles from filesystem layout. The user declares roles.
- Reading codemap, OpenAPI, or git history at runtime. Discovery-time only.
- Silently overwriting committed `services.yaml` / `flows.yaml`. Always diff and confirm.
- Inventing endpoint names when no evidence source exists. Emit a skeleton candidate flagged as such.
- Writing Dockerfiles into sibling service repos without explicit confirmation.
- Committing `:latest` image refs. Pin by digest.
- Inline secrets in `services.yaml` or `docker-compose.regression.yml`. Always `${ENV_VAR}`.
- Scaffolding `.regression/` inside a service repo. The workspace lives in a dedicated test repo.
