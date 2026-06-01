---
name: regression-compose-build
description: Emit .regression/docker-compose.regression.yml from services.yaml with healthchecks, two profiles (local-build, pinned-images), isolated network, named volumes.
metadata:
  category: testing
  tags: [regression, docker-compose, infrastructure, polyrepo]
user-invocable: false
---

# Regression Compose Build

> Load `Use skill: regression-service-inventory` for the `services.yaml` contract.

Generates the committed `docker-compose.regression.yml` from `services.yaml`. The compose file is the user's to edit; this skill re-emits it on `task-regression-discover` re-runs and shows a diff before overwriting.

## When to Use

- During `task-regression-discover` after `services.yaml` is committed.
- When the user explicitly asks to regenerate compose after editing `services.yaml`.

## Rules

1. **Two profiles in one file.** `local-build` uses `sibling-path` / `git` sources as build contexts; `pinned-images` uses `image` refs. Same file, profile-gated services.
2. **Healthchecks on every service.** Pulled from `services.yaml`. No exceptions.
3. **No host port mappings by default.** Services talk over the compose network. Host ports only on explicit user opt-in (test debugging).
4. **Named volumes only, per database.** Per-run isolation comes from the compose project name in `regression-runner`, not from volume names.
5. **Isolated network.** One project-scoped network. No `network_mode: host`.
6. **Show diff before overwrite.** Never silently replace a hand-edited file.
7. **All env values via `${ENV_VAR}` references.** No inline secrets.

## Patterns

### File structure

```yaml
name: regression                          # default project name; overridden per run by -p regression-<runId>

networks:
  regression-net: { driver: bridge }

volumes:
  db-data: {}                             # one per database service

services:
  # ---------- local-build profile ----------
  web:
    profiles: [local-build]
    build:
      context: ../web                     # sibling-path
      dockerfile: Dockerfile
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:3000/healthz"]
      interval: 5s
      timeout: 3s
      retries: 30
    environment:
      API_BASE_URL: http://api:8080
    depends_on:
      api: { condition: service_healthy }
    networks: [regression-net]

  # ---------- pinned-images profile ----------
  web-image:
    profiles: [pinned-images]
    image: ghcr.io/acme/web@sha256:...
    healthcheck: { test: [...], interval: 5s, timeout: 3s, retries: 30 }
    environment:
      API_BASE_URL: http://api-image:8080
    depends_on:
      api-image: { condition: service_healthy }
    networks: [regression-net]

  # ---------- backend (both profiles) ----------
  api:
    profiles: [local-build]
    build: { context: ../api, dockerfile: Dockerfile }
    healthcheck: { test: ["CMD", "curl", "-fsS", "http://localhost:8080/healthz"], interval: 5s, timeout: 3s, retries: 30 }
    environment:
      DATABASE_URL: "postgres://postgres:${POSTGRES_PASSWORD}@db:5432/app"
    depends_on:
      db: { condition: service_healthy }
    networks: [regression-net]

  api-image:
    profiles: [pinned-images]
    image: ghcr.io/acme/api@sha256:...
    healthcheck: { ... }
    environment: { DATABASE_URL: "..." }
    depends_on:
      db: { condition: service_healthy }
    networks: [regression-net]

  # ---------- database (shared across profiles) ----------
  db:
    image: postgres@sha256:...
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 30
    environment:
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
      POSTGRES_DB: app
    volumes:
      - db-data:/var/lib/postgresql/data
    networks: [regression-net]
```

### Naming rule for dual-profile services

A frontend or backend that has both a `sibling-path` / `git` source *and* an `image` ref gets two compose entries:
- `<name>` for `local-build`
- `<name>-image` for `pinned-images`

Service-to-service references inside the same profile use the profile's name. The plugin generates both consistently.

### Database services

Databases use `image` only (the engine's official image). No `local-build` variant - we never rebuild Postgres for a test run. One entry, both profiles see it.

### `depends_on` health-gating

Always `condition: service_healthy`. Never `service_started`. Combined with `docker compose up --wait`, this is how the runner avoids `sleep`.

### Diff-before-write

When `docker-compose.regression.yml` already exists:

1. Build the new file in memory.
2. Diff against the existing file (unified diff format).
3. Show the user the diff.
4. Ask: keep mine / take new / merge interactively. Default: keep mine.

### What this skill never does

- Add `restart: unless-stopped` (we want clean failures, not respawn loops).
- Add `tmpfs` or `cap_add` (out of scope for v1).
- Generate Dockerfiles. That's `regression-service-inventory`'s suggestion job.

## Output Format

`.regression/docker-compose.regression.yml` (committed). Plus a side note documenting any unsupported `services.yaml` field the user provided (the field is ignored, not silently rewritten).

## Avoid

- **Single-profile files.** The local/CI split is the whole point.
- **`network_mode: host`.** Breaks isolation; breaks parallel runs.
- **Host port mappings by default.** Tests run inside the network; no need.
- **`restart` policies.** A flaky service should fail the run, not loop.
- **`service_started` dependencies.** Use `service_healthy`.
- **Anonymous volumes.** Hard to wipe on `down -v` reliably.
