---
name: rails-activerecord-patterns
description: ActiveRecord patterns for Rails 7.2+: N+1 prevention, scopes, counter_cache, locking, async queries, MySQL/PostgreSQL features.
metadata:
  category: backend
  tags: [ruby, rails, activerecord, mysql, postgresql, performance]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing model associations and scopes
- Fixing N+1 queries (Bullet flags, slow index endpoints)
- Choosing dependent options, counter_cache placement
- Choosing optimistic vs pessimistic locking, or `with_lock` under MySQL `REPEATABLE READ`
- Adding DB-specific columns (MySQL JSON / functional indexes; PG JSONB / arrays / partial indexes)

For chunked-transaction shape inside batches, memory safety, OOM mitigations, see `rails-batch-processing-patterns`.
For advisory locks, leader election, isolation tiers, see `rails-db-locking-patterns`.
For pool sizing across Puma/Sidekiq/CLI vs `max_connections`, see `rails-connection-pool-sizing`.

## Rules

- Default associations to lazy loading; eager load explicitly per query
- Never `default_scope` - infects every query
- Always set `dependent:` on `has_many` / `has_one`
- Use `enum` with explicit integer mapping for status fields
- Parameterized queries only - never string interpolation
- Use `find_each` / `in_batches` for large datasets - never `.all.each`
- Prefer `exists?` over `any?`, `size` over `count` on loaded associations
- Lock by primary key only with `with_lock` / `lock!` on MySQL `REPEATABLE READ` - non-PK scans gap-lock ranges

## Patterns

### N+1 Detection and Fix

Bad - one query per user:

```ruby
User.all.each { |u| puts u.orders.count }
```

Good - eager loading variants:

```ruby
User.includes(:orders)                                  # separate query (default)
User.preload(:orders)                                   # always separate (safe with complex scopes)
User.eager_load(:orders).where(orders: { status: :active }) # LEFT OUTER JOIN (needed for WHERE on assoc)
```

Surface lazy loading in development:

```ruby
# config/environments/development.rb
config.active_record.strict_loading_by_default = true   # raises on lazy load (Rails 6.1+)

# Gemfile (development group)
gem "bullet"
```

### Scopes and Enum

Bad - `default_scope` infects every query:

```ruby
default_scope { where(active: true) }
```

Good - explicit chainable scopes, explicit enum mapping prevents reordering bugs:

```ruby
class Order < ApplicationRecord
  enum :status, { pending: 0, confirmed: 1, processing: 2, shipped: 3, delivered: 4, cancelled: 5 }

  scope :active,    -> { where.not(status: :cancelled) }
  scope :for_user,  ->(id) { where(user_id: id) }
  scope :with_active_users, -> { joins(:user).merge(User.active) }
end
```

### Normalization

`normalizes` canonicalizes attributes on assignment (Rails 7.1+) - replaces hand-rolled `before_validation` for trim/downcase. Finder methods (`find_by`, `where`) apply normalization to lookup values.

```ruby
class User < ApplicationRecord
  normalizes :email, with: ->(e) { e.strip.downcase }
end
```

### Associations

`belongs_to` is required by default since Rails 5; pass `optional: true` only for genuinely nullable parents.

```ruby
class User < ApplicationRecord
  has_many :orders, dependent: :destroy
  has_many :order_items, through: :orders
  has_one  :profile, dependent: :destroy
end

class Order < ApplicationRecord
  belongs_to :user, counter_cache: true
  has_many :order_items, dependent: :destroy
  has_many :comments, as: :commentable, dependent: :destroy
end
```

**Dependent options:**

| Option                 | Behavior                  | Use When                                        |
| ---------------------- | ------------------------- | ----------------------------------------------- |
| `:destroy`             | Runs callbacks per child  | Children have their own dependents or callbacks |
| `:delete_all`          | Direct SQL, skips callbacks | Performance-critical, no child callbacks       |
| `:nullify`             | Sets FK to NULL           | Children can exist independently                |
| `:restrict_with_error` | Prevents parent deletion  | Children must not be orphaned                   |

### Query Optimization

```ruby
# Batch large datasets
Order.find_each(batch_size: 1000) { |o| process(o) }     # one record at a time
Order.in_batches(of: 1000) { |b| b.update_all(synced: true) } # relation per batch

# Pluck and select - skip AR object overhead
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

OrderRollup.upsert_all(rows,
  unique_by: :order_id,
  update_only: %i[total_cents updated_at])
```

Caveats: timestamps not auto-set unless in `rows`; validations and `before_save` don't run; serialized columns not coerced.

### Pessimistic Locking (`with_lock` / `lock!`)

`with_lock` issues `SELECT ... FOR UPDATE`. **On MySQL under default `REPEATABLE READ`, lock granularity is row + gap (next-key lock).** Non-unique-index range scans gap-lock the range, blocking inserts into the gap from other sessions - the #1 source of MySQL deadlocks in Sidekiq workloads.

Two rules under MySQL:

1. Lock by primary key only.
2. Keep the critical section short - no external calls, no `find_each`.

Bad - non-PK lock under MySQL RR:

```ruby
Order.where(customer_id: id).lock.each(&:close!)  # gap-lock cascade
```

Good - lock by PK:

```ruby
Order.transaction do
  order = Order.lock.find(order_id)               # WHERE id = ? FOR UPDATE
  order.update!(state: "closed")
end
```

For multiple rows, fetch IDs unlocked first:

```ruby
ids = Order.where(customer_id: id).pluck(:id)
ids.each_slice(100) do |batch|
  Order.transaction { Order.where(id: batch).lock.each(&:close!) }
end
```

PostgreSQL has no gap-lock equivalent; the lock-by-PK and short-section discipline still applies for clarity.

### Optimistic Locking

Add a `lock_version` column for low-contention concurrent updates (e.g., two admins editing one order). Rails bumps it on every update and raises `ActiveRecord::StaleObjectError` if another writer beat this one.

```ruby
add_column :orders, :lock_version, :integer, null: false, default: 0
```

Choose pessimistic for short read-then-write critical sections; optimistic when conflicts are rare and retry is cheap. **For hot rows with frequent contention, optimistic produces `StaleObjectError` storms - use pessimistic by PK instead.**

### Association Side Effects on Save

`update`/`save` can load associations the action body never references. The cause is *declarative* (in the model file or initializer), not visible in the controller. When N+1-like queries appear on an update action and `.includes` "fixes" it without you wanting those associations in scope, the real fix is one of these:

- **`belongs_to :parent, touch: true`** - saving the child touches the parent's `updated_at`. The parent is loaded to be touched, even if the action only changed a child column.
- **`has_many :children, autosave: true`** (explicit, or implicit via `accepts_nested_attributes_for :children`) - parent save iterates and saves children, triggering association load. `accepts_nested_attributes_for` loads the collection even when params omit nested attributes.
- **Callback that references an association**: `before_save`/`after_save`/`after_commit` reading `self.linked_model` forces a load at save time.
- **Missing `inverse_of` combined with `has_many_inversing` / `automatic_scope_inversing` off** (the `load_defaults` 6.1-era state). Traversing back to the parent re-queries instead of reusing the in-memory object.

Bad - controller "fix" papering over an autosave side effect:

```ruby
# OrdersController#update
def update
  @order = Order.includes(:line_items, :shipping_address).find(params[:id])  # only to suppress N+1
  @order.update!(order_params)                                               # only changes order.status
end
```

Good - identify and remove the source instead:

```ruby
# Option A: drop unneeded autosave/touch
class Order < ApplicationRecord
  has_many :line_items                          # no autosave: true unless params include line_items
  belongs_to :shipping_address                  # no touch: true unless cache invalidation needs it
end

# Option B: keep the side effect, ensure inverse_of so the load is one query, not N
class Order < ApplicationRecord
  has_many :line_items, inverse_of: :order
end

# Option C: when the side effect is needed only sometimes, scope it
order.update!(order_params)                     # default path: no preload
order.line_items.reload if reprice_needed       # explicit, scoped to the case

# Option D: when a callback needs the FK but not the record, pass the FK directly
# Bad - loads shipping_address every save:
#   after_commit { WarehouseJob.perform_later(self.shipping_address.id) }
# Good - uses the FK already in memory, no SELECT:
#   after_commit { WarehouseJob.perform_later(self.shipping_address_id) }
```

For an audit of the implicit-configuration state (including `has_many_inversing`, `automatic_scope_inversing`, and `new_framework_defaults_*.rb` footguns), use `rails-implicit-config-audit`.

### Async Queries with `load_async`

For dashboards fetching several independent queries, `load_async` runs them on a background pool so wall clock is the slowest, not the sum:

```ruby
@recent_orders = Order.recent.limit(10).load_async
@top_products  = Product.top_sellers.limit(5).load_async
@open_tickets  = Ticket.open.load_async
```

Each async query holds an extra connection from the executor pool - cross-reference `rails-connection-pool-sizing`. Don't use inside transactions (the async thread can't see uncommitted state).

### Database-specific features

#### MySQL 8.0+ (InnoDB)

```ruby
add_column :orders, :metadata, :json, null: false
add_index :users, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_users_tier"

Order.where("JSON_CONTAINS(metadata, ?)", { source: "web" }.to_json)
Order.where("metadata->>'$.source' = ?", "web")

add_index :products, :description, type: :fulltext
Product.where("MATCH(description) AGAINST(? IN NATURAL LANGUAGE MODE)", "ergonomic chair")
```

No native array column type; no partial indexes (`where:` clause). Closest to partial: functional index on a `CASE` expression - rarely worth it. Slow-query inspection: `performance_schema.events_statements_summary_by_digest`.

#### PostgreSQL

```ruby
add_column :orders, :metadata, :jsonb, default: {}, null: false
add_index :orders, :metadata, using: :gin

Order.where("metadata @> ?", { source: "web" }.to_json)

add_column :users, :tags, :string, array: true, default: []
User.where("'admin' = ANY(tags)")

add_index :orders, :created_at, where: "status IN (0, 1, 2)", name: "idx_active_orders"
```

Slow-query inspection: `pg_stat_statements` extension.

For migration safety per adapter, see `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

## Output Format

```
Pattern: {N+1 Fix | Scope | Association | Batch | Locking | DB Feature}
Model: {model name}
Adapter: {MySQL | PostgreSQL}
Change: {description}
Queries: {before} -> {after} (estimated)
```

## Avoid

- `default_scope` - infects all queries
- N+1 in serializers - preload before serializing
- `.includes` papering over `touch:` / `autosave:` / `accepts_nested_attributes_for` / callback side effects on save - remove the source or set `inverse_of` instead
- `.all.each` on large tables - use `find_each`
- `with_lock` / `lock!` on a non-PK scan under MySQL `REPEATABLE READ` - gap-lock cascade
- Optimistic locking on hot contended rows - `StaleObjectError` storms; use pessimistic by PK
- Callbacks for business logic - use service objects
- `update_attribute` - skips validations; use `update!`
- String interpolation in queries - SQL injection
- Missing `dependent:` on `has_many` - orphaned records
- Enum without explicit integer mapping - values shift when entries reorder
