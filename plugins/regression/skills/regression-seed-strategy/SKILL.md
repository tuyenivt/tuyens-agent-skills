---
name: regression-seed-strategy
description: Per-engine database seeding for outside-in regression. Postgres / MySQL / MariaDB / MongoDB / SQL Server / SQLite. Seeds apply directly, bypassing the backend's migration tool.
metadata:
  category: testing
  tags: [regression, seeds, database, fixtures, idempotent]
user-invocable: false
---

# Regression Seed Strategy

Seeds run *after* every healthchecked service is up and *before* Playwright executes. Each run starts from an identical, deterministic state. Seeds bypass the backend's migration tool - the plugin only ever talks to the database directly.

## When to Use

- During `task-regression-discover` to template the seed files.
- During `task-regression` to apply them.

## Rules

1. **Per-engine native tooling.** Postgres uses `psql`, MySQL/MariaDB use `mysql`, MongoDB uses `mongoimport` / `mongosh`, SQL Server uses `sqlcmd`, SQLite uses `sqlite3`. No ORMs.
2. **Idempotent.** Every seed file must be safe to run twice in a row. `INSERT ... ON CONFLICT DO NOTHING`, `INSERT IGNORE`, `MERGE`, or upserts.
3. **Ordered.** Files apply in lexicographic order: `00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`. Number prefixes are mandatory.
4. **Deterministic IDs.** No `gen_random_uuid()` at seed time. UUIDs are literal constants in seed files so scenarios can target them.
5. **No production data.** Seed data is synthetic, named `acme-test-*` or similar. The plugin's authoring step prompts the user to confirm.
6. **Schema first, data second.** Schema lives in `initialSchema` (from `services.yaml`); data lives in `.regression/seeds/`.

## Patterns

### Seeds directory shape

```
.regression/seeds/
  00-init/
    01-schema.sql              # only if initialSchema.type == sql-dump and the user wants it under seeds/
  10-domain/
    01-tenants.sql
    02-users.sql
    03-products.sql
  20-fixtures/
    01-orders.sql              # cross-references domain rows by literal UUID
  99-final/
    01-flags.sql               # feature flags, defaults, settings
```

### Per-engine application snippet (used by `regression-runner`)

```bash
# postgres
docker compose -p $PROJECT exec -T db psql -U postgres -d app -v ON_ERROR_STOP=1 < .regression/seeds/<file>.sql

# mysql/mariadb
docker compose -p $PROJECT exec -T db mysql -uroot -p"$MYSQL_ROOT_PASSWORD" app < .regression/seeds/<file>.sql

# mongodb (JSON files)
docker compose -p $PROJECT exec -T db mongoimport --db app --collection <name> --file /seeds/<file>.json --jsonArray

# sqlserver
docker compose -p $PROJECT exec -T db /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -d app -b -i /seeds/<file>.sql

# sqlite
docker compose -p $PROJECT exec -T db sqlite3 /data/app.db < .regression/seeds/<file>.sql
```

`-v ON_ERROR_STOP=1` / `-b` / equivalent fail-fast flags are required on every engine.

### Idempotent insert idioms

| Engine     | Idempotent insert idiom                                          |
| ---------- | ---------------------------------------------------------------- |
| postgres   | `INSERT INTO t (...) VALUES (...) ON CONFLICT (id) DO NOTHING;`  |
| mysql      | `INSERT IGNORE INTO t (...) VALUES (...);`                       |
| mariadb    | `INSERT IGNORE INTO t (...) VALUES (...);`                       |
| mongodb    | `db.t.updateOne({ _id }, { $setOnInsert: {...} }, { upsert: true })` |
| sqlserver  | `MERGE t USING (VALUES (...)) AS s (...) ON t.id = s.id WHEN NOT MATCHED THEN INSERT (...) VALUES (...);` |
| sqlite     | `INSERT OR IGNORE INTO t (...) VALUES (...);`                    |

### Initial schema sourcing

From `services.yaml#services[].initialSchema`:

| `type`       | Where the plugin gets the schema                                                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `sql-dump`   | Read the referenced file (typically `<service>/db/schema.sql`). Copy into `.regression/seeds/00-init/01-schema.sql` and apply first.                                                       |
| `migrations` | Reference the directory but do not parse migration syntax. Apply by mounting the directory into the DB container and running the engine's runner, OR by executing each file in order via the per-engine snippet above. User picks. |
| `none`       | Backend creates schema on first boot. Seeds wait for the backend to become healthy, then run. `regression-runner` enforces ordering.                                                       |

When `initialSchema.type` is `none`, the runner *must* not start applying seeds until the backend healthcheck passes, because the schema doesn't exist yet.

### Cross-referenced fixture example (postgres)

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

The Playwright scenario can target `33333333-...` directly because the IDs are constants.

### Time freezing for time-sensitive data

If seed rows have created_at / due_at / expires_at, use a single fixed `'2026-01-01T00:00:00Z'` baseline so scenarios assert exact values. Pair with `TZ=UTC` at compose level. See `regression-data-isolation` for the runner-side time setup.

## Output Format

`.regression/seeds/<NN>-<phase>/<NN>-<topic>.<ext>` files, plus a one-page `.regression/seeds/README.md` documenting the apply order, the engine, and how to add a new fixture.

## Avoid

- **Running app migrations from the seeder.** Migrations are the app's concern; seeds talk directly to the DB.
- **Non-deterministic IDs.** No `gen_random_uuid()`, no `NOW()`, no `auto_increment` without explicit values.
- **Non-idempotent inserts.** Re-running must not duplicate rows.
- **Production exports.** Even "scrubbed" production data leaks PII patterns. Synthesize fresh.
- **One mega-file.** Split by phase and topic so failures point at a specific table.
