---
name: regression-service-inventory
description: Role-based structural Q&A for outside-in regression. Builds .regression/services.yaml from declared Frontend / Backend / Database services.
metadata:
  category: testing
  tags: [regression, services, inventory, docker, polyrepo]
user-invocable: false
---

# Regression Service Inventory

> Schema owner for `.regression/services.yaml`. `regression-compose-build`, `regression-seed-strategy`, and `regression-runner` consume this contract. `stack-detect` may only be invoked as a *suggestion source* for Dockerfile defaults when a sibling-path service has no Dockerfile.

Builds `services.yaml` by asking the user to declare each service's role and structural metadata. The plugin never auto-detects roles.

## Rules

1. **One role per service.** `frontend` / `backend` / `database`. No others in v1.
2. **User-declared.** Source type, port, healthcheck, env vars, `depends_on`, engine. Suggestions allowed; silent assumptions not.
3. **Healthcheck required.** No healthcheck = the writer rejects the entry.
4. **Pin by digest.** `image:` source must include `@sha256:...`. The writer rejects `:latest` and bare tags. Applies to all roles including databases.
5. **No inline secret values.** Env values that look secret must use `${VAR}` form. Detection is structural: any `value:` containing a literal string of more than 12 characters that is not a URL, hostname, or boolean - and that is not wrapped in `${...}` - is flagged for the user to confirm. The skill does not ship a heuristic scanner; the user is the gate. A repo-level secret scanner (`gitleaks`, `trufflehog`) is recommended in the discover report.
6. **Sibling-path without Dockerfile is rejected by default.** The writer offers a `stack-detect`-sourced Dockerfile suggestion; if the user declines, the entry is removed from inventory rather than left in a not-buildable state.
7. **`resources:` are optional.** Omitted -> no cap. Recommended on shared CI runners where two suite runs may overlap. Honored by `regression-compose-build` only.
8. **`sinks:` is a top-level list of out-of-process targets the suite needs to assert on.** Brokers / buckets / outbound webhooks / mail-out. Always optional; populated by `task-regression-discover` when the user answers "do you have async sinks?". Consumed by `regression-sink-asserter`.

## Patterns

### Role decision

| What the service does | Role |
| --- | --- |
| Serves a UI on an HTTP port; tests drive through a browser | `frontend` |
| Exposes an HTTP/JSON API; not a UI | `backend` (includes `*-gateway` / `*-api` *applications*) |
| Stateful container holding data | `database` |
| Broker, cache, proxy / mesh gateway, search index | out of v1 scope |

### `services.yaml` schema (canonical, owned here)

```yaml
services:
  - name: <string>
    role: frontend | backend | database
    source:
      type: sibling-path | git | image
      path: <string>          # type=sibling-path
      url: <git-url>          # type=git
      ref: <git-ref>          # type=git, required
      ref: <image-ref>        # type=image, must include @sha256:
    ports: [<int>, ...]       # default empty (no host mapping)
    healthcheck:
      cmd: [<string>, ...]    # docker compose healthcheck syntax
      interval: <duration>    # default 5s
      timeout: <duration>     # default 3s
      retries: <int>          # default 30
    env:
      - { name: <NAME>, value: <literal-or-${VAR}> }
    depends_on: [<service-name>, ...]
    # database-only
    engine: postgres | mysql | mariadb | mongodb | sqlserver | sqlite
    version: <string>
    initialSchema:
      type: sql-dump | migrations | none
      path: <string>          # sql-dump / migrations only
    persistence: ephemeral | external   # default ephemeral; external -> isolation verifier scans
    # optional - per-service resource caps for shared-runner concurrency
    resources:
      memMb: <int>            # compose `mem_limit`, mapped to MiB
      cpus: <float>           # compose `cpus`
sinks:                        # optional - async sinks the suite asserts on (F-7)
  - name: <string>            # logical sink name (e.g. "orders-events")
    kind: kafka-topic | s3-bucket | webhook-out | smtp-out | sqs-queue
    target: <string>          # broker:topic, bucket name, URL pattern, mailhog hostname, queue ARN
    consumerGroup: <string>   # kafka only - this suite's consumer group name (run-id scoped)
    notes: <string>           # free-text; what this sink is for
```

Defaults (`5s` / `3s` / `30`, ephemeral persistence) apply when the field is omitted in user input; the writer records them in the emitted yaml so the file is self-describing.

### Per-role Q&A (the questions the writer asks)

**Frontend / Backend** - source type, port, healthcheck command, env vars, `depends_on`. For backends: which database(s); `DATABASE_URL` (or equivalent) using `${VAR}` references.

**Database** - engine, version, port, healthcheck (engine cheat-sheet below), `initialSchema` mode + path, persistence (default ephemeral).

For `sibling-path` services missing a Dockerfile: `Use skill: stack-detect` for a suggestion. Offer to write `<service>/Dockerfile` only on explicit yes; otherwise write `.regression/.cache/suggested-dockerfiles/<service>.dockerfile` and remove the inventory entry per Rule 6.

### Engine healthcheck cheat-sheet

| Engine | Command |
| --- | --- |
| postgres | `pg_isready -U $POSTGRES_USER` |
| mysql | `mysqladmin ping -h 127.0.0.1 -u root -p$MYSQL_ROOT_PASSWORD` |
| mariadb | `mariadb-admin ping -h 127.0.0.1 -u root -p$MARIADB_ROOT_PASSWORD` (MariaDB 11+; legacy `mysqladmin` + `MYSQL_ROOT_PASSWORD` still works on the official image) |
| mongodb | `mongosh --quiet --eval "db.adminCommand('ping').ok"` |
| sqlserver | `/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $SA_PASSWORD -Q "SELECT 1"` |
| sqlite | n/a - file-based; rely on the consuming backend's healthcheck |

### Writer behavior (the validation contract)

The writer rejects an entry and stops with a row-by-row diff when:

- Required field missing (`role`, `source`, `healthcheck`, and role-specific fields).
- `image:` source ref does not contain `@sha256:`.
- `git:` source missing `ref`.
- `sibling-path` source path does not resolve relative to the test repo root.
- `env.value` contains an inline value flagged by Rule 5 and the user did not confirm.
- Sibling-path Dockerfile suggestion declined per Rule 6.

The diff is printed to stdout in unified-diff format; the user fixes inputs and re-runs.

## Output Format

`.regression/services.yaml` (committed) plus a one-line skip summary per rejected entry. The schema in this file is the single source of truth for downstream skills.

## Avoid

- Auto-detecting roles from filesystem layout.
- Skipping healthchecks (`sleep` is not a substitute).
- Inline secrets in `services.yaml`.
- `:latest` image refs.
- Multiple roles per service.
- Leaving a not-buildable sibling-path entry.
