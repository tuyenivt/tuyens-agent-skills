---
name: regression-compose-build
description: Emit docker-compose.regression.yml from services.yaml - healthchecks, two profiles (local-build, pinned-images), isolated net, named volumes.
metadata:
  category: testing
  tags: [regression, docker-compose, infrastructure, polyrepo]
user-invocable: false
---

# Regression Compose Build

> Schema owner: `regression-service-inventory`. This skill consumes `services.yaml` and emits compose; it does not invent fields, defaults, or values absent from inventory.

Generates the committed `docker-compose.regression.yml`. Re-emit on `task-regression-discover` re-runs; show a unified diff before any overwrite.

## When to Use

- During `task-regression-discover` after `services.yaml` lands.
- When the user explicitly asks to regenerate compose after editing `services.yaml`.

## Rules

1. **Two profiles, profile-gated services.** `local-build` consumes `sibling-path` / `git` sources; `pinned-images` consumes `image` sources. Same file. A service with only one source type appears in only one profile - that is correct.
2. **Healthchecks pulled verbatim from `services.yaml`.** No healthcheck in inventory = the writer rejects the entry. The writer does not invent commands, intervals, retries, or `curl` / `pg_isready` defaults.
3. **No host port mappings by default.** Tests speak over the compose network. Host ports only with explicit user opt-in in inventory.
4. **Named volumes only, one per database.** Per-run isolation comes from the compose project name in `regression-runner`. Volume name uses `<db-service-name>-data` (e.g. `db-data`, `analytics-db-data`).
5. **One isolated bridge network** named `regression-net`. No `network_mode: host`.
6. **Compose v2 required.** Healthcheck-conditional `depends_on` is v2; `name:` top-level is v2.3.3+. Stated, not silently assumed.
7. **Reference env values as `${VAR}` only.** Inventory carries the names; the writer does not interpolate, default, or hardcode values.
8. **Diff before overwrite.** Unified-diff against the existing file; ask `keep mine / take new / merge`. Default: keep mine. Without an authored-by marker the writer cannot tell hand-edits from prior emits - it always treats the existing file as authoritative until the user picks.
9. **Optional resource caps.** When `services.yaml#services[].resources` is present, emit `mem_limit: <N>m` and `cpus: '<F>'` for that service. Omitted by default; nothing emitted means no cap. Recommended on shared CI runners.

## Patterns

### File skeleton

The writer emits this shape; every field below comes from `services.yaml` except the literals `name`, `networks`, and `volumes.<n>-data`.

```yaml
name: regression                          # overridden per run by -p regression-<runId>
networks:
  regression-net: { driver: bridge }
volumes:
  db-data: {}                             # one per database service, named <svc>-data

services:
  web:                                    # frontend with sibling-path source
    profiles: [local-build]
    build: { context: ../web, dockerfile: Dockerfile }
    healthcheck: { ... }                  # verbatim from services.yaml#services[].healthcheck
    environment: { ... }                  # verbatim from services.yaml#services[].env
    depends_on:
      api: { condition: service_healthy }
    networks: [regression-net]

  web-image:                              # same service with image source -> separate entry
    profiles: [pinned-images]
    image: ghcr.io/acme/web@sha256:...
    healthcheck: { ... }
    environment: { ... }
    depends_on:
      api-image: { condition: service_healthy }
    networks: [regression-net]

  db:                                     # databases use image only; no -image suffix
    image: postgres@sha256:...
    healthcheck: { ... }
    environment: { ... }
    volumes: [db-data:/var/lib/postgresql/data]
    networks: [regression-net]
    # no profiles key -> participates in BOTH profiles
```

### Dual-source naming

A frontend / backend declared with BOTH a `sibling-path` / `git` source AND an `image` ref in inventory becomes two compose entries: `<name>` (local-build) and `<name>-image` (pinned-images). Service-to-service references inside the same profile use the same-profile name.

### Database participation in both profiles

A service with no `profiles:` key participates in every active profile. Databases are declared without `profiles:` so a single `db` entry serves both `local-build` and `pinned-images` runs - no rebuild of Postgres per profile.

### `depends_on` health-gating

Always `condition: service_healthy`. Never `service_started`. Paired with the runner's `up --wait`, this is the only startup gate - no `sleep`.

### What this skill never emits

- `restart: unless-stopped` (we want clean failures, not respawn loops).
- `tmpfs`, `cap_add`, `privileged` (out of v1 scope).
- Dockerfiles (`regression-service-inventory` owns Dockerfile suggestions).
- Default env values or computed URLs (`postgres://...@db:5432/app` is composed in `services.yaml`, not here).

## Output Format

`.regression/docker-compose.regression.yml`. Plus a "Skipped fields" report block listing any `services.yaml` field the writer does not support, so users see what was dropped rather than silently rewritten.

## Avoid

- `network_mode: host`. Breaks isolation; breaks parallel runs.
- Host port mappings by default.
- `restart` policies.
- `service_started` dependencies.
- Anonymous volumes (cannot be cleaned reliably by `down -v`).
- Single-profile files. The local / CI split is the whole point.
