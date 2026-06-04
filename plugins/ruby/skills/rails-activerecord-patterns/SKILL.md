---
name: rails-activerecord-patterns
description: ActiveRecord patterns for Rails 7.2+: N+1 prevention, scopes, enum, locking, callbacks, async queries, MySQL/PostgreSQL features.
metadata:
  category: backend
  tags: [ruby, rails, activerecord, mysql, postgresql, performance]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing associations, scopes, enums
- Fixing N+1 queries (Bullet flags, slow index endpoints)
- Choosing dependent options, counter_cache placement
- Choosing optimistic vs pessimistic locking
- Placing callbacks: `after_save` vs `after_commit`
- Adding DB-specific columns (MySQL JSON / functional indexes; PG JSONB / arrays / partial indexes)

## Rules

- Lazy load by default; eager load explicitly per query.
- Never `default_scope` - infects every query including joins from unrelated models.
- `dependent:` is required on every `has_many` / `has_one`.
- `enum` with explicit integer mapping - positional shorthand shifts when entries reorder.
- Parameterized queries only - never string interpolation.
- `find_each` / `in_batches` for large datasets - never `.all.each`.
- `exists?` over `any?`; `size` over `count` on loaded associations.
- `update!` over `update_attribute` (latter skips validations).
- Pessimistic lock by PK only; keep the critical section short and free of network calls. Side-effect callbacks: see `rails-transaction-patterns`.

## Patterns

### N+1 fix

```ruby
# Bad - one query per user
User.all.each { |u| u.orders.count }

# Good - eager load
User.includes(:orders)                                       # separate query (default)
User.preload(:orders)                                        # always separate (safe with scopes)
User.eager_load(:orders).where(orders: { status: :active })  # LEFT OUTER JOIN when WHERE on assoc
```

Surface lazy loads in dev: `config.active_record.strict_loading_by_default = true` and `gem "bullet"`.

### Scopes and enum

```ruby
class Order < ApplicationRecord
  enum :status, { pending: 0, confirmed: 1, processing: 2, shipped: 3, delivered: 4, cancelled: 5 }

  scope :active,   -> { where.not(status: :cancelled) }
  scope :for_user, ->(id) { where(user_id: id) }
end
```

### Associations and `dependent:`

`belongs_to` is required by default; pass `optional: true` only for genuinely nullable parents.

| Option                 | Behavior                    | Use when                                        |
| ---------------------- | --------------------------- | ----------------------------------------------- |
| `:destroy`             | Runs callbacks per child    | Children have their own dependents or callbacks |
| `:delete_all`          | Direct SQL, skips callbacks | Performance-critical, no child callbacks        |
| `:nullify`             | Sets FK to NULL             | Children can exist independently                |
| `:restrict_with_error` | Prevents parent deletion    | Children must not be orphaned                   |

### Normalization (Rails 7.1+)

Replaces hand-rolled `before_validation` for trim/downcase; also applied to lookup values in `find_by` / `where`.

```ruby
normalizes :email, with: ->(e) { e.strip.downcase }
```

### Callbacks

Reserve callbacks for invariants tied to the row (normalization, derived columns, audit). For side effects (jobs, email, external sync), use `after_commit` so the worker sees a persisted row. Full hook table, `requires_new`, and the `with_lock` + callback + network deadlock pitfall live in `rails-transaction-patterns`.

### Query optimization

```ruby
Order.find_each(batch_size: 1000) { |o| process(o) }
Order.in_batches(of: 1000) { |b| b.update_all(synced: true) }

User.where(active: true).pluck(:email)        # skip AR object overhead
User.select(:id, :name, :email)

User.where(email: x).exists?                  # LIMIT 1
user.orders.size                              # uses counter_cache if available
```

`find_each` / `in_batches` ignore custom `ORDER BY` and force `ORDER BY id ASC`. If order matters, paginate with explicit `where("id > ?", cursor)`.

### Bulk inserts and upserts

`create!` in a loop fires one INSERT plus all callbacks per row. For trusted data, `insert_all` / `upsert_all` issue one multi-row statement and run 50-100x faster - but skip callbacks/validations, don't auto-set timestamps, and don't coerce serialized columns.

```ruby
OrderRollup.insert_all(rows, returning: %w[id])
OrderRollup.upsert_all(rows, unique_by: :order_id, update_only: %i[total_cents updated_at])
```

### Pessimistic locking

```ruby
# with_lock opens its own transaction - don't wrap in an outer Model.transaction
order = Order.find(order_id)
order.with_lock { order.update!(state: "closed") }

# Or lock as part of the find inside an explicit transaction
Order.transaction do
  order = Order.lock.find(order_id)  # WHERE id = ? FOR UPDATE
  order.update!(state: "closed")
end
```

**MySQL default `REPEATABLE READ`: row + gap (next-key) locks.** Non-unique-index range scans gap-lock the range and block inserts - the #1 source of MySQL deadlocks in Sidekiq workloads. Lock by PK; keep the critical section short. PostgreSQL has no gap-lock equivalent; same discipline still applies.

For multiple rows, fetch IDs unlocked first, then lock per-ID:

```ruby
ids = Order.where(customer_id: id).pluck(:id)
ids.each_slice(100) do |batch|
  Order.transaction { Order.where(id: batch).lock.each(&:close!) }
end
```

For high-contention nightly jobs, fan out from one orchestrator to N per-record Sidekiq workers - each locks one row by PK in its own short transaction (see `rails-sidekiq-patterns`).

### Optimistic locking

Add `lock_version` for low-contention concurrent updates. Rails bumps it on every update and raises `ActiveRecord::StaleObjectError` when another writer beat this one.

```ruby
add_column :orders, :lock_version, :integer, null: false, default: 0
```

Hot rows produce `StaleObjectError` storms - use pessimistic by PK instead.

### Implicit association loads on save

`update`/`save` can load associations the action body never references. Source is declarative, not in the controller. When `.includes` "fixes" an N+1 on an update action without you wanting those associations in scope, remove the source:

- `belongs_to :parent, touch: true` - saving the child touches the parent
- `has_many :children, autosave: true` (explicit or via `accepts_nested_attributes_for`) - parent save iterates children
- Callback reading `self.<association>` - forces a load at save time. Use `self.foo_id`, not `self.foo.id`, when only the FK is needed
- Missing `inverse_of` under `load_defaults <= 6.1` (no `has_many_inversing`)

For an audit of implicit-config state, see `rails-implicit-config-audit`.

### Async queries (`load_async`)

For dashboards with several independent queries, wall clock becomes the slowest, not the sum:

```ruby
@recent_orders = Order.recent.limit(10).load_async
@top_products  = Product.top_sellers.limit(5).load_async
```

Each async query holds an extra connection (see `rails-connection-pool-sizing`). Never use inside transactions - the async thread can't see uncommitted state.

### DB-specific columns and indexes

```ruby
# MySQL 8.0+ (InnoDB) - JSON, functional index, fulltext
add_column :orders, :metadata, :json, null: false
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"
add_index :products, :description, type: :fulltext
# No native array, no partial index. Slow-query: performance_schema.events_statements_summary_by_digest.

# PostgreSQL - jsonb, GIN, array, partial index
add_column :orders, :metadata, :jsonb, default: {}, null: false
add_index :orders, :metadata, using: :gin
add_column :users, :tags, :string, array: true, default: []
add_index :orders, :created_at, where: "status IN (0, 1, 2)", name: "idx_active_orders"
# Slow-query: pg_stat_statements.
```

Migration safety for these operations: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

## Output Format

```
Pattern: {N+1 Fix | Scope | Association | Callback | Batch | Locking | DB Feature}
Model: {name}
Adapter: {MySQL | PostgreSQL}
Change: {description}
Queries: {before} -> {after}
```

## Avoid

- N+1 in serializers - preload before serializing
- `.includes` papering over `touch:` / `autosave:` / callback side effects - remove the source or add `inverse_of`
- Non-PK `lock` on MySQL `REPEATABLE READ` - gap-lock cascade
- Optimistic locking on hot rows - `StaleObjectError` storms
- Callbacks for business logic - use service objects
- Missing `dependent:` on `has_many` - orphaned records
