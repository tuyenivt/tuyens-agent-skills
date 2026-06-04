---
name: regression-seed-strategy
description: Per-engine database seeding for outside-in regression. Postgres / MySQL / MariaDB / MongoDB / SQL Server / SQLite. Seeds apply directly, bypassing the backend's migration tool.
metadata:
  category: testing
  tags: [regression, seeds, database, fixtures, idempotent]
user-invocable: false
---

# Regression Seed Strategy

Seeds run after every service is healthy and before Playwright executes. Each run starts from an identical, deterministic state. Seeds talk to the database directly, never through the backend.

## When to Use

- During `task-regression-discover` to template seed files.
- During `task-regression` to apply them (called by `regression-runner` via `.regression/scripts/apply-seed.sh`).

## Rules

1. **Per-engine native tooling.** Postgres `psql`, MySQL/MariaDB `mysql`, MongoDB `mongosh` (not `mongoimport` - upserts need `$setOnInsert`), SQL Server `sqlcmd`, SQLite `sqlite3`. No ORMs.
2. **Idempotent.** Every seed must be safe to apply twice. Use engine-native upsert idioms (table below). Re-running cannot duplicate rows.
3. **Lexicographic order.** Phase directories `00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`. Numeric prefixes mandatory. Byte-wise sort.
4. **Deterministic IDs.** No `gen_random_uuid()`, no `NOW()`, no auto-increment without explicit values. Literal UUIDs and constants.
5. **No production data.** Synthetic only (`acme-test-*`). The discover workflow prompts the user to confirm.
6. **Schema source determined by inventory.** `services.yaml#initialSchema.type` is one of `sql-dump` / `migrations` / `none`. The applier reads that, the user does not pick at apply time.
7. **Migrations are the app's responsibility.** When `initialSchema.type: migrations`, the backend service applies them on startup; seeds wait for the backend healthcheck before running. Seeds never invoke Flyway / Liquibase / Alembic.
8. **Single transport per engine.** Each engine uses one apply mechanism: SQL engines stream via `docker exec -T ... < file` (host-side stdin redirection, no mount); MongoDB requires `mongosh --file` against a script the runner copies into the container with `docker cp` before invocation. The runner does not mix transports.
9. **Service name and DB name come from `services.yaml`.** Never literal `db` / `app`. `apply-seed.sh` resolves the compose service name (the database service's `name:`) and the engine-specific DB name (`POSTGRES_DB` / `MYSQL_DATABASE` / `MARIADB_DATABASE` / `MSSQL_DB` / mongodb URI path) from inventory at startup. Hardcoded names are a Rule-9 violation and fail the writer.

## Patterns

### Initial schema modes

| `type` | What `regression-runner` does | Who owns the schema |
| --- | --- | --- |
| `sql-dump` | Copies the referenced file (e.g. `../api/db/schema.sql`) to `.regression/seeds/00-init/01-schema.sql`. It applies in phase order like any other seed. | User. |
| `migrations` | Does nothing schema-related. The backend service runs its own migrations on first boot. Seeds wait on backend healthcheck (per Rule 7) before running. | The backend. |
| `none` | Backend creates schema lazily on first request. Seeds wait on backend healthcheck. | The backend. |

For `migrations` and `none`, `00-init/` is empty - no schema applies from this skill.

### Apply commands (one per engine)

The runner invokes `.regression/scripts/apply-seed.sh "$PROJECT" "$FILE"`; the script reads `.regression/services.yaml` once at top to resolve, for each `role: database` entry: the service `name` (compose service name -> `$DB_SVC`), `engine`, and the engine-specific DB name from `env:` (`POSTGRES_DB` / `MYSQL_DATABASE` / `MARIADB_DATABASE` / `MSSQL_DB` / mongodb URI path). When multiple databases are declared, dispatch is by extension AND by per-seed-file frontmatter or path convention (`seeds/<db-svc>/...`); the inventory writer rejects multi-DB inventories that do not adopt the directory convention.

```bash
# postgres - stdin transport
docker compose -p "$PROJECT" exec -T "$DB_SVC" \
  psql -U "${POSTGRES_USER:-postgres}" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 < "$FILE"

# mysql / mariadb - stdin transport. --abort-source-on-error gives fail-fast on multi-statement files.
docker compose -p "$PROJECT" exec -T "$DB_SVC" \
  mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --abort-source-on-error "$MYSQL_DATABASE" < "$FILE"
# MariaDB official image: use $MARIADB_ROOT_PASSWORD + $MARIADB_DATABASE (legacy aliases MYSQL_* also accepted in v11+).

# sqlite - stdin transport
docker compose -p "$PROJECT" exec -T "$DB_SVC" \
  sqlite3 "${SQLITE_PATH:-/data/app.db}" ".bail on" < "$FILE"

# sqlserver - cp + exec because sqlcmd reads from a file path, not stdin
docker cp "$FILE" "$(docker compose -p "$PROJECT" ps -q "$DB_SVC")":/tmp/seed.sql
docker compose -p "$PROJECT" exec -T "$DB_SVC" \
  /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -d "$MSSQL_DB" -b -i /tmp/seed.sql

# mongodb - cp + exec; mongosh runs a JS file containing upsert statements
docker cp "$FILE" "$(docker compose -p "$PROJECT" ps -q "$DB_SVC")":/tmp/seed.js
docker compose -p "$PROJECT" exec -T "$DB_SVC" \
  mongosh --quiet "${MONGO_URI:-mongodb://localhost:27017/$MONGO_DB}" --file /tmp/seed.js
```

`$DB_SVC`, `$POSTGRES_DB`, `$MYSQL_DATABASE`, `$MARIADB_DATABASE`, `$MSSQL_DB`, `$MONGO_DB` are populated by `apply-seed.sh` from `services.yaml` - never hardcoded literals.

Fail-fast flags per engine: `psql -v ON_ERROR_STOP=1`, `mysql --abort-source-on-error`, `sqlite3 .bail on`, `sqlcmd -b`, `mongosh` (default - exits non-zero on uncaught script errors).

### Idempotent insert idioms

| Engine | Idempotent insert |
| --- | --- |
| postgres | `INSERT INTO t (...) VALUES (...) ON CONFLICT (id) DO NOTHING;` |
| mysql / mariadb | `INSERT IGNORE INTO t (...) VALUES (...);` |
| mongodb | `db.t.updateOne({ _id }, { $setOnInsert: {...} }, { upsert: true });` |
| sqlserver | `MERGE t USING (VALUES (...)) AS s (...) ON t.id = s.id WHEN NOT MATCHED THEN INSERT (...) VALUES (...);` |
| sqlite | `INSERT OR IGNORE INTO t (...) VALUES (...);` |

### Cross-referenced fixture (postgres)

```sql
-- 10-domain/02-users.sql
INSERT INTO users (id, email, tenant_id) VALUES
  ('11111111-1111-4111-8111-111111111111', 'alice@acme-test.local', '22222222-2222-4222-8222-222222222222')
ON CONFLICT (id) DO NOTHING;

-- 20-fixtures/01-orders.sql
INSERT INTO orders (id, user_id, status) VALUES
  ('33333333-3333-4333-8333-333333333333', '11111111-1111-4111-8111-111111111111', 'confirmed')
ON CONFLICT (id) DO NOTHING;
```

Scenarios reference `33333333-...` directly.

### MongoDB upsert (the file mongosh runs)

```js
// 20-fixtures/01-orders.js
db.orders.updateOne(
  { _id: "order-33333333" },
  { $setOnInsert: { userId: "user-11111111", status: "confirmed" } },
  { upsert: true }
);
```

Mongo seeds are `.js` files (mongosh scripts), not `.json`. The skill does not use `mongoimport`.

### Time-frozen seed data

If rows have `created_at` / `expires_at`, use the literal `'2026-01-01T00:00:00Z'` baseline so scenarios assert exact values. Container `TZ=UTC` (set in compose by `regression-data-isolation`).

### Phase guidance

- `00-init/` - schema (only when `initialSchema.type: sql-dump`).
- `10-domain/` - core entities (tenants, users, products).
- `20-fixtures/` - cross-referenced rows for scenarios.
- `99-final/` - flags, settings, defaults read at boot.

## Output Format

`.regression/seeds/<NN>-<phase>/<NN>-<topic>.<ext>` files (`.sql` for SQL engines, `.js` for MongoDB) plus `.regression/seeds/README.md` documenting: engine in use, apply order, fail-fast flag in effect, and how to add a fixture.

`README.md` template:

```markdown
# Seeds

Engine: {postgres | mysql | mariadb | mongodb | sqlserver | sqlite}
Fail-fast flag: {ON_ERROR_STOP=1 | --abort-source-on-error | .bail on | -b | mongosh default}
Apply order: byte-wise lexicographic across phase dirs.

## Adding a fixture

1. Pick a phase dir.
2. Number-prefix the filename (`05-...` to land before `10-domain/01-...`).
3. Use literal IDs; refer to them from scenarios.
4. Use the engine's idempotent insert idiom (see regression-seed-strategy).
```

## Avoid

- Running app migrations from the seeder.
- Non-deterministic IDs.
- Non-idempotent inserts.
- Production exports (even "scrubbed").
- One mega-file.
- `mongoimport` (does not upsert via `$setOnInsert`).
- Mixing transports for one engine.
