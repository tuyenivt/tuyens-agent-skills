---
name: python-migration-safety
description: "Zero-downtime migration patterns for Alembic and Django. Covers lock_timeout, NOT NULL via NOT VALID constraints, concurrent index creation, expand-contract column renames, data migration separation, and multi-release deploy sequencing."
metadata:
  category: backend
  tags: [python, alembic, django, migrations, postgresql, zero-downtime]
user-invocable: false
---

## ALEMBIC (FastAPI/SQLAlchemy)

- Auto-generation: `alembic revision --autogenerate -m "description"`
- Review every auto-generated migration - never trust blindly
- Zero-downtime DDL: same universal rules (nullable first, CONCURRENTLY indexes, never rename columns directly)
- Separate data migrations from schema migrations (use separate revision)
- `op.execute()` for raw SQL when needed (e.g., CREATE INDEX CONCURRENTLY)
- Downgrade function: always implement, test in CI
- Online migration for large tables: batch updates in a Celery task
- **Always set `lock_timeout`** before DDL to fail fast instead of blocking other queries

```python
# Schema migration - add nullable column first
def upgrade():
    op.execute(sa.text("SET lock_timeout = '2s'"))
    op.add_column("orders", sa.Column("tracking_number", sa.String(100), nullable=True))

def downgrade():
    op.drop_column("orders", "tracking_number")
```

```python
# Separate data migration - backfill in batches using keyset pagination (NOT WHERE col IS NULL LIMIT N)
def upgrade():
    conn = op.get_bind()
    last_id = 0
    while True:
        result = conn.execute(
            sa.text("""
                UPDATE orders SET tracking_number = 'LEGACY-' || id::text
                WHERE tracking_number IS NULL AND id > :last_id
                ORDER BY id LIMIT 1000
            """),
            {"last_id": last_id},
        )
        if result.rowcount == 0:
            break
        # Advance cursor to avoid re-scanning processed rows
        row = conn.execute(sa.text(
            "SELECT MAX(id) FROM orders WHERE tracking_number LIKE 'LEGACY-%' AND id > :last_id"
        ), {"last_id": last_id}).scalar()
        last_id = row or last_id + 1000

def downgrade():
    op.execute(sa.text("UPDATE orders SET tracking_number = NULL WHERE tracking_number LIKE 'LEGACY-%'"))
```

```python
# CREATE INDEX CONCURRENTLY (requires non-transactional migration)
def upgrade():
    op.execute(sa.text("CREATE INDEX CONCURRENTLY ix_orders_status ON orders (status)"))

# In env.py, configure: context.configure(..., transaction_per_migration=True)
# For CONCURRENTLY, the migration must run outside a transaction
```

## DJANGO MIGRATIONS

- makemigrations + migrate workflow
- RunSQL for custom DDL (e.g., CREATE INDEX CONCURRENTLY)
  - requires `atomic = False` on the Migration class
- SeparateDatabaseAndState for complex operations
- RunPython for data migrations (separate from schema migrations)
- Zero-downtime: same rules as Alembic
- Squash migrations periodically: squashmigrations command

```python
# Django data migration
from django.db import migrations

def backfill_tracking_numbers(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    batch_size = 1000
    while Order.objects.filter(tracking_number__isnull=True).exists():
        ids = list(
            Order.objects.filter(tracking_number__isnull=True)
            .values_list("id", flat=True)[:batch_size]
        )
        Order.objects.filter(id__in=ids).update(
            tracking_number=models.functions.Concat(models.Value("LEGACY-"), models.F("id"))
        )

class Migration(migrations.Migration):
    dependencies = [("orders", "0002_add_tracking_number")]
    operations = [
        migrations.RunPython(backfill_tracking_numbers, migrations.RunPython.noop),
    ]
```

```python
# CREATE INDEX CONCURRENTLY in Django
class Migration(migrations.Migration):
    atomic = False  # Required for CONCURRENTLY
    dependencies = [("orders", "0003_backfill_tracking")]
    operations = [
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY ix_orders_status ON orders_order (status);",
            reverse_sql="DROP INDEX ix_orders_status;",
        ),
    ]
```

## POSTGRESQL 11+ SHORTCUT: NOT NULL WITH DEFAULT

PostgreSQL 11+ can add a `NOT NULL` column with a constant `DEFAULT` as a metadata-only operation (no table rewrite). This is simpler than the 4-step approach when a default value is acceptable:

```python
# Alembic - single migration, metadata-only on PG 11+
def upgrade():
    op.execute(sa.text("SET lock_timeout = '2s'"))
    op.add_column("orders", sa.Column(
        "tracking_number", sa.String(100),
        nullable=False, server_default="PENDING",
    ))

def downgrade():
    op.drop_column("orders", "tracking_number")
```

If a constant default is NOT acceptable (values must be computed per row), use the 4-step pattern below.

## NOT NULL CONSTRAINT ON LARGE TABLES (Zero-Downtime, No Default)

Direct `ALTER COLUMN SET NOT NULL` acquires a full table lock. Use NOT VALID + VALIDATE CONSTRAINT for large tables:

```python
# Alembic - 4-step zero-downtime NOT NULL on large table

# Step 1: Add nullable column
def upgrade():
    op.add_column("orders", sa.Column("shipping_address", sa.String(500), nullable=True))

# Step 2 (separate migration): Backfill existing rows in batches
def upgrade():
    conn = op.get_bind()
    while True:
        result = conn.execute(sa.text("""
            UPDATE orders SET shipping_address = 'UNKNOWN'
            WHERE shipping_address IS NULL LIMIT 1000
        """))
        if result.rowcount == 0:
            break

# Step 3 (separate migration): Add CHECK constraint with NOT VALID (skips existing rows, no lock)
def upgrade():
    op.execute(sa.text(
        "ALTER TABLE orders ADD CONSTRAINT orders_shipping_address_not_null "
        "CHECK (shipping_address IS NOT NULL) NOT VALID"
    ))

# Step 4 (separate migration): Validate existing rows (ShareUpdateExclusiveLock - concurrent reads/writes allowed)
def upgrade():
    op.execute(sa.text(
        "ALTER TABLE orders VALIDATE CONSTRAINT orders_shipping_address_not_null"
    ))
```

Django equivalent (each step is a separate migration with `atomic = False`):

```python
# Step 3 - add NOT VALID constraint
class Migration(migrations.Migration):
    atomic = False
    operations = [
        migrations.RunSQL(
            "ALTER TABLE orders_order ADD CONSTRAINT orders_shipping_nn "
            "CHECK (shipping_address IS NOT NULL) NOT VALID;",
            reverse_sql="ALTER TABLE orders_order DROP CONSTRAINT orders_shipping_nn;",
        ),
    ]

# Step 4 - validate (separate migration)
class Migration(migrations.Migration):
    atomic = False
    operations = [
        migrations.RunSQL(
            "ALTER TABLE orders_order VALIDATE CONSTRAINT orders_shipping_nn;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
```

## DEPLOY SEQUENCING

The multi-step patterns above must be deployed across multiple releases, not all at once:

1. **Release 1**: Add nullable column migration + backfill migration. Deploy. Existing app code ignores the new column.
2. **Release 2**: Update app code to read/write the new column. Deploy. Both old and new code work because the column is nullable.
3. **Release 3**: Add NOT VALID constraint migration. Deploy.
4. **Release 4**: VALIDATE constraint migration. Deploy.

For column removal, reverse the order: remove code references first (Release 1), then drop the column (Release 2).

## ENUM CHANGES (PostgreSQL)

Adding enum values is safe; removing or renaming is not.

```python
# Alembic - add enum value (safe, non-transactional)
def upgrade():
    op.execute(sa.text("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'refunded'"))

# Removing enum values requires creating a new type and migrating (expand-contract)
```

## COLUMN RENAMES (Expand-Contract)

Never rename a column directly. Use expand-contract:

1. Add new column (nullable)
2. Backfill new column from old column
3. Update app code to write to both columns, read from new
4. Deploy, verify
5. Stop writing to old column
6. Drop old column in a later migration

## EDGE CASES

- **`CREATE INDEX CONCURRENTLY` failure**: If a concurrent index build fails (e.g., unique violation), it leaves an `INVALID` index behind. Check with `\d tablename` and drop the invalid index before retrying.
- **Alembic `--autogenerate` misses**: Autogenerate does not detect: table/column renames (generates drop + add), changes to `CheckConstraint` text, enum value changes, or custom types. Always review generated migrations.
- **Django `squashmigrations` with `RunSQL`/`RunPython`**: Squashed migrations cannot auto-optimize `RunSQL` or `RunPython` operations - they are preserved as-is. Mark completed data migrations with `elidable=True` so squash can remove them.
- **Multi-database migrations**: If using Django with multiple databases, `RunPython` operations must check `schema_editor.connection.alias` to avoid running against the wrong database.

## SHARED

- CI validation: migrate up -> migrate down -> migrate up (must be clean)
- Never mix DDL and DML in same migration
- Always set `lock_timeout` before DDL statements in production migrations
- Anti-patterns:
  - ❌ Auto-generated migrations without review
  - ❌ Data in schema migrations
  - ❌ Removing columns without removing code references first
  - ❌ `ALTER COLUMN SET NOT NULL` directly on tables with millions of rows (full table lock)
  - ❌ `WHERE col IS NULL LIMIT N` backfill loops (O(n^2) - use keyset pagination instead)
  - ❌ Running all multi-step migrations in a single deployment (race conditions with app code)
  - ❌ DDL without `SET lock_timeout` (can block other queries indefinitely)
