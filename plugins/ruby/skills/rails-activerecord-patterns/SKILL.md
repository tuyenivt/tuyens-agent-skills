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
- Choosing optimistic vs pessimistic locking under MySQL `REPEATABLE READ`
- Placing callbacks: `after_save` (in-transaction) vs `after_commit` (post-commit)
- Adding DB-specific columns (MySQL JSON / functional indexes; PG JSONB / arrays / partial indexes)

## Rules

- Default associations to lazy loading; eager load explicitly per query
- Never `default_scope` - infects every query
- Always set `dependent:` on `has_many` / `has_one`
- `enum` with explicit integer mapping - positional shorthand shifts when entries reorder
- Parameterized queries only - never string interpolation
- `find_each` / `in_batches` for large datasets - never `.all.each`
- `exists?` over `any?`; `size` over `count` on loaded associations
- Side-effect callbacks (jobs, mail, HTTP) in `after_commit`, never `after_save`
- Under MySQL `REPEATABLE READ`: lock by primary key only, no network calls inside the critical section
- Use `update!` over `update_attribute` - the latter skips validations

## Patterns

### N+1 Detection and Fix

```ruby
# Bad - one query per user
User.all.each { |u| u.orders.count }

# Good - eager load variants
User.includes(:orders)                                          # separate query (default)
User.preload(:orders)                                           # always separate (safe with complex scopes)
User.eager_load(:orders).where(orders: { status: :active })     # LEFT OUTER JOIN (WHERE on assoc)
```

Surface lazy loads in dev: `config.active_record.strict_loading_by_default = true` (Rails 6.1+) and `gem "bullet"`.

### Scopes and Enum

```ruby
class Order < ApplicationRecord
  enum :status, { pending: 0, confirmed: 1, processing: 2, shipped: 3, delivered: 4, cancelled: 5 }

  scope :active,   -> { where.not(status: :cancelled) }
  scope :for_user, ->(id) { where(user_id: id) }
end
```

`default_scope { where(active: true) }` infects every query, including joins from unrelated models - the #1 source of "why is this query so weird" debugging.

### Associations and `dependent:`

`belongs_to` is required by default since Rails 5; pass `optional: true` only for genuinely nullable parents.

| Option                 | Behavior                    | Use When                                        |
| ---------------------- | --------------------------- | ----------------------------------------------- |
| `:destroy`             | Runs callbacks per child    | Children have their own dependents or callbacks |
| `:delete_all`          | Direct SQL, skips callbacks | Performance-critical, no child callbacks        |
| `:nullify`             | Sets FK to NULL             | Children can exist independently                |
| `:restrict_with_error` | Prevents parent deletion    | Children must not be orphaned                   |

### Normalization (Rails 7.1+)

`normalizes` canonicalizes attributes on assignment - replaces hand-rolled `before_validation` for trim/downcase. Applied to lookup values in `find_by` / `where`.

```ruby
normalizes :email, with: ->(e) { e.strip.downcase }
```

### Callbacks: `after_save` vs `after_commit`

Reserve callbacks for invariants tied to the row itself (normalization, derived columns, audit). For side effects (jobs, email, external sync), use `after_commit` so the worker sees a persisted row. For the full hook selection table and the lock-hold pitfall (`with_lock` + callback + network call -> `Lock wait timeout` storms), use skill: `rails-transaction-patterns`.

### Query Optimization

```ruby
# Batch
Order.find_each(batch_size: 1000) { |o| process(o) }
Order.in_batches(of: 1000) { |b| b.update_all(synced: true) }

# Skip AR object overhead
User.where(active: true).pluck(:email)
User.select(:id, :name, :email)

# Existence and counts
User.where(email: x).exists?  # LIMIT 1
user.orders.size              # uses counter_cache if available
```

`find_each` / `in_batches` ignore custom `ORDER BY` and force `ORDER BY id ASC`. If order matters, use explicit `where("id > ?", cursor)` chunks.

### Bulk Inserts and Upserts

`create!` in a loop fires one INSERT plus all callbacks per row. For trusted data, `insert_all` / `upsert_all` issue a single multi-row statement, skip callbacks/validations, and run 50-100x faster.

```ruby
OrderRollup.insert_all(rows, returning: %w[id])
OrderRollup.upsert_all(rows, unique_by: :order_id, update_only: %i[total_cents updated_at])
```

Caveats: timestamps not auto-set unless in `rows`; validations and `before_save` don't run; serialized columns not coerced.

### Pessimistic Locking

`SELECT ... FOR UPDATE`. Two forms, equivalent except for transaction scope:

```ruby
# Form A: with_lock opens its own transaction
order = Order.find(order_id)
order.with_lock { order.update!(state: "closed") }

# Form B: explicit transaction, lock as part of the find
Order.transaction do
  order = Order.lock.find(order_id)   # WHERE id = ? FOR UPDATE
  order.update!(state: "closed")
end
```

Don't wrap `with_lock` in an outer `Model.transaction` - redundant and confusing.

**MySQL under default `REPEATABLE READ`: lock granularity is row + gap (next-key lock).** Non-unique-index range scans gap-lock the range, blocking inserts - the #1 source of MySQL deadlocks in Sidekiq workloads. Lock by PK; keep the critical section short.

For multiple rows, fetch IDs unlocked first, then lock per-ID:

```ruby
ids = Order.where(customer_id: id).pluck(:id)
ids.each_slice(100) do |batch|
  Order.transaction { Order.where(id: batch).lock.each(&:close!) }
end
```

For high-contention nightly jobs, fan out from one orchestrator to N per-record Sidekiq workers - each worker locks one row by PK in its own short transaction. See `rails-sidekiq-patterns` for the dispatch shape.

PostgreSQL has no gap-lock equivalent; the lock-by-PK and short-section discipline still applies for clarity.

### Optimistic Locking

Add `lock_version` for low-contention concurrent updates. Rails bumps it on every update and raises `ActiveRecord::StaleObjectError` when another writer beat this one.

```ruby
add_column :orders, :lock_version, :integer, null: false, default: 0
```

For hot rows with frequent contention, optimistic produces `StaleObjectError` storms - use pessimistic by PK instead.

### Association Side Effects on Save

`update`/`save` can load associations the action body never references. The cause is declarative (model file or initializer), not in the controller. When `.includes` "fixes" an N+1 on an update action without you wanting those associations in scope, find and remove the source:

- `belongs_to :parent, touch: true` - saving the child touches the parent's `updated_at`
- `has_many :children, autosave: true` (explicit or via `accepts_nested_attributes_for`) - parent save iterates children
- Callback reading `self.<association>` - forces a load at save time. Use `self.foo_id` not `self.foo.id` when only the FK is needed
- Missing `inverse_of` under `load_defaults <= 6.1` (no `has_many_inversing`)

For an audit of implicit-config state, use `rails-implicit-config-audit`.

### Async Queries with `load_async`

For dashboards fetching several independent queries, `load_async` runs them on a background pool so wall clock is the slowest, not the sum:

```ruby
@recent_orders = Order.recent.limit(10).load_async
@top_products  = Product.top_sellers.limit(5).load_async
```

Each async query holds an extra connection (cross-reference `rails-connection-pool-sizing`). Don't use inside transactions - the async thread can't see uncommitted state.

### Database-specific features

#### MySQL 8.0+ (InnoDB)

```ruby
add_column :orders, :metadata, :json, null: false
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"

Order.where("JSON_CONTAINS(metadata, ?)", { source: "web" }.to_json)
add_index :products, :description, type: :fulltext
```

No native array column; no partial indexes. Slow-query inspection: `performance_schema.events_statements_summary_by_digest`.

#### PostgreSQL

```ruby
add_column :orders, :metadata, :jsonb, default: {}, null: false
add_index :orders, :metadata, using: :gin
add_column :users, :tags, :string, array: true, default: []
add_index :orders, :created_at, where: "status IN (0, 1, 2)", name: "idx_active_orders"
```

Slow-query inspection: `pg_stat_statements`.

Per-adapter migration safety: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

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
