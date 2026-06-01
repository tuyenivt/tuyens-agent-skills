---
name: regression-service-inventory
description: Role-based structural Q&A for outside-in regression. Builds .regression/services.yaml from declared Frontend / Backend / Database services.
metadata:
  category: testing
  tags: [regression, services, inventory, docker, polyrepo]
user-invocable: false
---

# Regression Service Inventory

> Stack-agnostic. Do not run `stack-detect` to classify roles. `stack-detect` may only be invoked as a suggestion source for Dockerfile defaults when a `sibling-path` service has no Dockerfile.

Builds `.regression/services.yaml` by asking the user to declare each service's role and structural metadata. The plugin never auto-detects roles or frameworks - the user names what is in scope.

## When to Use

- During `task-regression-discover`, after the user has listed the services they want under test.
- When refreshing inventory after a topology change (new service, removed service, new env var, port change).

## Rules

1. **One role per service.** Every service is exactly one of: `frontend`, `backend`, `database`. Services that are none of these (brokers, gateways, sidecars) are out of v1 scope.
2. **User-declared, not detected.** Source type, port, healthcheck command, env vars, depends_on, and (for databases) engine are user input. Suggestions are allowed; assumptions are not.
3. **Healthcheck is required for every service.** No healthcheck = no entry. A regression run that races startup is worse than no run.
4. **Pin by digest, not tag, for `image` sources.** `ghcr.io/acme/svc@sha256:...`, not `:latest` or `:v1`.
5. **No secrets in `services.yaml`.** Env values referencing secrets use `${ENV_VAR}` form; the actual value lives in `.env` or `docker-compose.override.yml`.

## Patterns

### Role decision table

| User answer to "what does it do?"                                       | Role          |
| ----------------------------------------------------------------------- | ------------- |
| Serves a UI on an HTTP port; tests drive it through a browser           | `frontend`    |
| Exposes an HTTP API; depends on a database; not a UI                    | `backend`     |
| Stateful container holding data; engine is one of postgres/mysql/etc.   | `database`    |
| Something else (broker, gateway, search index, cache)                   | Out of scope  |

### `services.yaml` shape

```yaml
services:
  - name: web
    role: frontend
    source: { type: sibling-path, path: ../web }
    ports: [3000]
    healthcheck: { cmd: ["CMD", "curl", "-fsS", "http://localhost:3000/healthz"], interval: 5s, timeout: 3s, retries: 30 }
    env:
      - { name: API_BASE_URL, value: http://api:8080 }
    depends_on: [api]

  - name: api
    role: backend
    source: { type: sibling-path, path: ../api }
    ports: [8080]
    healthcheck: { cmd: ["CMD", "curl", "-fsS", "http://localhost:8080/healthz"], interval: 5s, timeout: 3s, retries: 30 }
    env:
      - { name: DATABASE_URL, value: "${DATABASE_URL}" }
    depends_on: [db]

  - name: db
    role: database
    source: { type: image, ref: "postgres@sha256:..." }
    engine: postgres
    version: "16"
    ports: [5432]
    healthcheck: { cmd: ["CMD-SHELL", "pg_isready -U postgres"], interval: 5s, timeout: 3s, retries: 30 }
    env:
      - { name: POSTGRES_PASSWORD, value: "${POSTGRES_PASSWORD}" }
      - { name: POSTGRES_DB, value: app }
    initialSchema: { type: sql-dump, path: ../api/db/schema.sql }
    # or: { type: migrations, runner: psql, path: ../api/db/migrations }
    # or: { type: none }   # backend creates schema on first boot
```

### Structural Q&A per role

For each service the user names:

**Frontend Service**
- Source: `sibling-path` / `git` / `image`?
- HTTP port?
- Healthcheck command? (HTTP probe like `curl -fsS http://localhost:<port>/healthz`)
- Env vars the container needs at runtime? (typically `API_BASE_URL`)
- What backend(s) does it talk to? (writes `depends_on`)
- If `sibling-path` and no Dockerfile in the repo: offer to suggest one (`Use skill: stack-detect`), but the user owns the final file.

**Backend Service**
- Same first four as Frontend.
- What database(s) does it talk to? (writes `depends_on`)
- `DATABASE_URL` (or equivalent) - reference as `${...}`, never inline.

**Database**
- Engine: postgres / mysql / mariadb / mongodb / sqlserver / sqlite / other.
- Version (major.minor or exact tag).
- Port.
- Healthcheck command appropriate to engine (see engine cheat-sheet below).
- Initial schema source: `sql-dump` path / `migrations` path + runner / `none`.
- Seed scope: per-test-run wipe via `down -v` (default) or persistent volume (discouraged).

### Engine healthcheck cheat-sheet

| Engine       | Healthcheck command                                          |
| ------------ | ------------------------------------------------------------ |
| postgres     | `pg_isready -U $POSTGRES_USER`                              |
| mysql/mariadb| `mysqladmin ping -h 127.0.0.1 -u root -p$MYSQL_ROOT_PASSWORD`|
| mongodb      | `mongosh --quiet --eval "db.adminCommand('ping').ok"`        |
| sqlserver    | `/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $SA_PASSWORD -Q "SELECT 1"` |
| sqlite       | n/a - file-based; covered by app healthcheck                |

### Dockerfile-defaults suggestion (sibling-path only, optional)

When a sibling-path service has no Dockerfile and the user accepts a suggestion:

1. `Use skill: stack-detect` on the service path.
2. Emit a multi-stage Dockerfile draft (build + runtime) appropriate to the detected stack.
3. Write it to `<service>/Dockerfile` only with explicit user confirmation. Otherwise output to `.regression/.cache/suggested-dockerfiles/<service>.Dockerfile` for the user to copy in.

The plugin never silently writes into a sibling repo.

## Output Format

`services.yaml` (committed). Self-validating - the writer rejects entries missing required fields with a row-by-row diff.

## Avoid

- **Auto-detecting roles.** A Python repo could be frontend (Streamlit), backend (FastAPI), or both - the user knows; the directory layout does not.
- **Skipping healthchecks.** A `sleep 30` workaround belongs in the user's worst dreams, not in this plugin.
- **Inline secrets** in `services.yaml`. Always `${ENV_VAR}`.
- **`:latest` image refs.** Reproducibility dies on the next image push.
- **Multiple roles per service.** Split the service or omit it from regression scope.
