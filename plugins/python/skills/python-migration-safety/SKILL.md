---
name: python-migration-safety
description: "Safe migration patterns for Python. Alembic (FastAPI) and Django migrations. Zero-downtime DDL, migration ordering, data migration separation, rollback strategy with PostgreSQL."
user-invocable: false
---

## ALEMBIC (FastAPI/SQLAlchemy)

- Auto-generation: `alembic revision --autogenerate -m "description"`
- Review every auto-generated migration — never trust blindly
- Zero-downtime DDL: same universal rules (nullable first, CONCURRENTLY indexes,
  never rename columns directly)
- Separate data migrations from schema migrations (use separate revision)
- op.execute() for raw SQL when needed (e.g., CREATE INDEX CONCURRENTLY)
- Downgrade function: always implement, test in CI
- alembic.ini: prepend_sys_path, sqlalchemy.url from env var
- Online migration for large tables: batch updates in a Celery task

```python
# Schema migration — add nullable column first
def upgrade():
    op.add_column("orders", sa.Column("tracking_number", sa.String(100), nullable=True))

def downgrade():
    op.drop_column("orders", "tracking_number")
```

```python
# Separate data migration — backfill in batches
def upgrade():
    conn = op.get_bind()
    while True:
        result = conn.execute(
            sa.text("""
                UPDATE orders SET tracking_number = 'LEGACY-' || id::text
                WHERE tracking_number IS NULL
                LIMIT 1000
            """)
        )
        if result.rowcount == 0:
            break

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

## SHARED

- CI validation: migrate up -> migrate down -> migrate up (must be clean)
- Never mix DDL and DML in same migration
- Anti-patterns:
  - ❌ Auto-generated migrations without review
  - ❌ Data in schema migrations
  - ❌ Removing columns without removing code references first
