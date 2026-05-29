---
name: python-migration-safety
description: "Zero-downtime DB migrations for Alembic and Django: lock_timeout, NOT VALID constraints, CONCURRENTLY indexes, expand-contract, deploy sequencing."
metadata:
  category: backend
  tags: [python, alembic, django, migrations, postgresql, zero-downtime]
user-invocable: false
---

# Migration Safety

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Creating or reviewing Alembic (FastAPI/SQLAlchemy) or Django migrations
- Planning zero-downtime schema changes under rolling deploys
- Adding enums, indexes, or constraints to existing tables

## Rules

- Review every auto-generated migration before applying
- Set `lock_timeout` before DDL in production to fail fast instead of blocking queries
- Separate data migrations from schema migrations (separate revision)
- Add columns nullable, backfill, then enforce NOT NULL
- Build indexes on large tables with `CREATE INDEX CONCURRENTLY` (outside a transaction)
- Never rename a column in one deploy - use expand-contract
- Multi-step zero-downtime patterns deploy across multiple releases, not one
- CI must validate: migrate up -> migrate down -> migrate up (clean)
- Always implement and test the downgrade (Alembic) or `reverse_sql` (Django)

## Patterns

### Alembic vs Django Operations

| Action                  | Alembic                                          | Django                                                       |
| ----------------------- | ------------------------------------------------ | ------------------------------------------------------------ |
| Generate from diff      | `alembic revision --autogenerate -m "..."`       | `manage.py makemigrations`                                   |
| Custom SQL              | `op.execute(sa.text("..."))`                     | `migrations.RunSQL("...", reverse_sql="...")`                |
| Data migration          | `op.get_bind().execute(...)` in separate rev     | `migrations.RunPython(forwards, reverse)`                    |
| Apply                   | `alembic upgrade head`                           | `manage.py migrate`                                          |
| Non-transactional (DDL) | `transaction_per_migration=True` in `env.py`     | `atomic = False` on `Migration` class                        |
| Squash                  | manual                                           | `manage.py squashmigrations` (mark data ops `elidable=True`) |

### Add Column Safely

Single-rev for nullable add; separate rev for backfill:

```python
# Alembic - schema only
def upgrade():
    op.execute(sa.text("SET lock_timeout = '2s'"))
    op.add_column("orders", sa.Column("tracking_number", sa.String(100), nullable=True))
```

### PG 11+ Shortcut: NOT NULL with Constant DEFAULT

Adding a `NOT NULL` column with a constant `DEFAULT` is metadata-only on PG 11+ (no rewrite). Prefer this when a default is acceptable:

```python
def upgrade():
    op.execute(sa.text("SET lock_timeout = '2s'"))
    op.add_column("orders", sa.Column(
        "tracking_number", sa.String(100),
        nullable=False, server_default="PENDING",
    ))
```

If values must be computed per row, use the 4-step pattern below.

### NOT NULL on Large Table (No Constant Default)

Direct `ALTER COLUMN SET NOT NULL` takes a full table lock. Use `CHECK ... NOT VALID` + `VALIDATE CONSTRAINT` across four separate migrations and releases:

```python
# Step 1: add nullable column
op.add_column("orders", sa.Column("shipping_address", sa.String(500), nullable=True))

# Step 2: backfill in batches using keyset pagination
last_id = 0
while True:
    res = conn.execute(sa.text("""
        UPDATE orders SET shipping_address = 'UNKNOWN'
        WHERE id IN (
            SELECT id FROM orders
            WHERE shipping_address IS NULL AND id > :last_id
            ORDER BY id LIMIT 1000
        ) RETURNING id
    """), {"last_id": last_id})
    ids = [r[0] for r in res]
    if not ids: break
    last_id = max(ids)

# Step 3: add CHECK ... NOT VALID (no lock on existing rows)
op.execute(sa.text(
    "ALTER TABLE orders ADD CONSTRAINT orders_shipping_nn "
    "CHECK (shipping_address IS NOT NULL) NOT VALID"
))

# Step 4: VALIDATE (ShareUpdateExclusiveLock, concurrent reads/writes ok)
op.execute(sa.text("ALTER TABLE orders VALIDATE CONSTRAINT orders_shipping_nn"))
```

Django equivalent: each step is a `Migration` with `atomic = False` using `RunSQL` (steps 1, 3, 4) or `RunPython` (step 2). Use `apps.get_model("orders", "Order")` inside `RunPython` and check `schema_editor.connection.alias` in multi-DB setups.

### CREATE INDEX CONCURRENTLY

Must run outside a transaction. If the build fails (e.g., unique violation), an `INVALID` index remains - drop it before retrying.

```python
# Alembic: env.py -> context.configure(..., transaction_per_migration=True)
op.execute(sa.text("CREATE INDEX CONCURRENTLY ix_orders_status ON orders (status)"))
```

```python
# Django
class Migration(migrations.Migration):
    atomic = False
    operations = [migrations.RunSQL(
        "CREATE INDEX CONCURRENTLY ix_orders_status ON orders_order (status);",
        reverse_sql="DROP INDEX ix_orders_status;",
    )]
```

### Enum Changes (PostgreSQL)

`ALTER TYPE ... ADD VALUE IF NOT EXISTS 'refunded'` is safe and non-transactional. Removing or renaming a value is not supported - create a new type, migrate the column, drop the old type (expand-contract).

### Column Rename (Expand-Contract)

Never rename directly. Across releases: (1) add new nullable column, (2) backfill, (3) app writes both / reads new, (4) verify, (5) stop writing old, (6) drop old column. Drops always follow code removal.

### Deploy Sequencing

| Change Type    | Order                                                            |
| -------------- | ---------------------------------------------------------------- |
| Add column     | Migration -> code uses it                                        |
| Drop column    | Code stops referencing -> migration drops                        |
| Add NOT NULL   | Add nullable -> backfill -> NOT VALID -> VALIDATE (4 releases)   |
| Rename column  | Expand-contract over multiple releases                           |
| Add index      | Migration first (additive); CONCURRENTLY on large tables         |
| Add enum value | Migration first -> code writes new value                         |

### Edge Cases

- **Alembic `--autogenerate` misses**: renames (drops + adds), `CheckConstraint` text changes, enum value changes, custom types. Always review.
- **Django `squashmigrations`**: cannot optimize `RunSQL`/`RunPython`; mark completed data migrations `elidable=True`.

## Output Format

```
## Migration Plan

### Schema Changes
| Change | Type | Table | Column | Safe Order |
|--------|------|-------|--------|------------|

### Indexes
| Index | Table | Columns | CONCURRENTLY |
|-------|-------|---------|--------------|

### Deploy Sequence
1. [Release N: migration / code change]
2. ...

### Rollback Plan
[Downgrade / reverse_sql notes]
```

## Avoid

- `WHERE col IS NULL LIMIT N` backfill loops (re-scans the same rows; use keyset pagination)
- Running all steps of a multi-step migration in one deployment (race conditions)
- Dropping columns before code stops referencing them
- Removing enum values without the multi-step type migration
- `CREATE INDEX` (non-concurrent) on large tables
