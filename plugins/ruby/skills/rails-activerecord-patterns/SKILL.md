---
name: rails-activerecord-patterns
description: ActiveRecord patterns for Rails 7.2+: N+1 prevention, scopes, counter_cache, batch processing, connection pooling, PostgreSQL features.
metadata:
  category: backend
  tags: [ruby, rails, activerecord, postgresql, performance]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing model associations and scopes for a new feature
- Fixing N+1 queries flagged by Bullet or log analysis
- Optimizing slow list/index endpoints with eager loading
- Adding PostgreSQL-specific columns (JSONB, arrays, partial indexes)
- Reviewing batch processing for large dataset operations
- Choosing dependent options and counter_cache placement

## Rules

- Default all associations to lazy loading - eager load explicitly per query
- Never use `default_scope` - it infects every query and is hard to override
- Always set `dependent:` on `has_many` and `has_one` associations
- Use `enum` with explicit integer mapping for status fields
- Use parameterized queries for all user input - never string interpolation
- Use `find_each` or `in_batches` for iterating large datasets - never `.all.each`
- Prefer `exists?` over `any?` and `size` over `count` on loaded associations
- Add `strict_loading` in development to surface lazy loading violations early

## Patterns

### N+1 Detection and Fix

Bad - fires a query per user:

```ruby
users = User.all
users.each { |u| puts u.orders.count }
```

Good - `includes` eager loads with separate query:

```ruby
users = User.includes(:orders).all
```

Good - `preload` always uses separate queries (safe with complex scopes):

```ruby
users = User.preload(:orders).all
```

Good - `eager_load` uses LEFT OUTER JOIN (needed for WHERE on association):

```ruby
users = User.eager_load(:orders).where(orders: { status: :active })
```

Good - `strict_loading` raises if lazy loading happens:

```ruby
user = User.strict_loading!.first
user.orders # => ActiveRecord::StrictLoadingViolationError

# Application-wide in development (Rails 6.1+)
# config/environments/development.rb
config.active_record.strict_loading_by_default = true
```

**Bullet gem** for N+1 detection in development:

```ruby
# Gemfile
gem "bullet", group: :development

# config/environments/development.rb
Bullet.enable = true
Bullet.alert = true
Bullet.rails_logger = true
```

### Scopes and Enum

Bad - using `default_scope`:

```ruby
class Order < ApplicationRecord
  default_scope { where(active: true) } # infects ALL queries
end
```

Good - explicit chainable scopes:

```ruby
class Order < ApplicationRecord
  # Explicit integer mapping prevents reordering bugs
  enum :status, { pending: 0, confirmed: 1, processing: 2, shipped: 3, delivered: 4, cancelled: 5 }

  scope :active, -> { where.not(status: :cancelled) }
  scope :recent, -> { order(created_at: :desc) }
  scope :for_user, ->(user_id) { where(user_id: user_id) }
  scope :fulfillable, -> { where(status: :confirmed) }

  # merge for cross-model scopes
  scope :with_active_users, -> { joins(:user).merge(User.active) }
end
```

### Normalization

Use `normalizes` to canonicalize attributes on assignment - replaces hand-rolled `before_validation` callbacks for trim/downcase patterns:

```ruby
class User < ApplicationRecord
  normalizes :email, with: ->(email) { email.strip.downcase }
  normalizes :phone, with: ->(p) { p.gsub(/\D/, "") }
end

User.normalize_value_for(:email, " A@B.COM ") # => "a@b.com"
```

Finder methods (`find_by`, `where`) apply normalization to the lookup value, so `User.find_by(email: " A@B.COM ")` matches the stored row.

### Associations

`belongs_to` is required by default since Rails 5 (`config.active_record.belongs_to_required_by_default = true`). Pass `optional: true` only for genuinely nullable parents - do not add it reflexively.

Bad - missing dependent option and counter_cache:

```ruby
class User < ApplicationRecord
  has_many :orders # no dependent - orphaned records on delete
end
```

Good - complete association setup:

```ruby
class User < ApplicationRecord
  has_many :orders, dependent: :destroy
  has_many :order_items, through: :orders
  has_one :profile, dependent: :destroy
end

class Order < ApplicationRecord
  belongs_to :user, counter_cache: true
  has_many :order_items, dependent: :destroy
  has_many :products, through: :order_items

  # Polymorphic - use sparingly, consider STI or dedicated tables
  has_many :comments, as: :commentable, dependent: :destroy
end

class OrderItem < ApplicationRecord
  belongs_to :order
  belongs_to :product
end
```

**Dependent options:**

| Option                 | Behavior                     | Use When                                        |
| ---------------------- | ---------------------------- | ----------------------------------------------- |
| `:destroy`             | Runs callbacks on each child | Children have their own dependents or callbacks |
| `:delete_all`          | Skips callbacks, direct SQL  | Performance-critical, no child callbacks needed |
| `:nullify`             | Sets FK to NULL              | Children can exist independently                |
| `:restrict_with_error` | Prevents parent deletion     | Children must not be orphaned                   |

### Query Optimization

Bad - loads entire table into memory:

```ruby
Order.all.each { |o| process(o) }
```

Good - batch processing for large datasets:

```ruby
# find_each - yields one record at a time
Order.find_each(batch_size: 1000) { |order| process(order) }

# in_batches - yields ActiveRecord::Relation batches
Order.in_batches(of: 1000) { |batch| batch.update_all(synced: true) }
```

Bad - loading full objects when only values needed:

```ruby
emails = User.where(active: true).map(&:email)
```

Good - pluck returns raw arrays without AR object overhead:

```ruby
emails = User.where(active: true).pluck(:email)
```

Good - select only needed columns:

```ruby
User.select(:id, :name, :email)
```

Good - use `exists?` and `size` over `any?` and `count`:

```ruby
User.where(email: "a@b.com").exists?  # stops at first match
user.orders.size   # uses counter_cache if available
user.orders.count  # always hits DB
```

### Connection Pooling

```ruby
# config/database.yml
production:
  pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>
```

**Formula:** `pool = Puma workers x threads`

- 3 workers x 5 threads = 15 pool
- PgBouncer for multiplexing when pool > 20
- Monitor with `ActiveRecord::Base.connection_pool.stat`

### Bulk Inserts and Upserts

`create!` in a loop fires one INSERT per row plus all callbacks/validations. For trusted data (imports, denormalization, materialized rollups), `insert_all` and `upsert_all` issue a single multi-row INSERT and skip callbacks/validations - 50-100x faster on hot paths.

Bad - one round-trip per row:

```ruby
rows.each { |attrs| OrderRollup.create!(attrs) }
```

Good - one statement, returns inserted ids:

```ruby
OrderRollup.insert_all(rows, returning: %w[id])

# Upsert by unique key (requires unique index on the conflict column)
OrderRollup.upsert_all(
  rows,
  unique_by: :order_id,
  update_only: %i[total_cents updated_at]
)
```

Caveats: timestamps are not auto-set unless you include them in `rows`; validations and `before_save` callbacks do not run; serialized columns are not coerced. Use deliberately on data you have already validated.

### Optimistic Locking

When two requests can update the same row concurrently (e.g., two admins editing one order), add a `lock_version` integer column. Rails bumps it on every update and raises `ActiveRecord::StaleObjectError` if another writer beat this one - the loser retries with fresh state instead of silently overwriting.

```ruby
# Migration
add_column :orders, :lock_version, :integer, null: false, default: 0

# Usage
order = Order.find(id)
order.update!(status: :processing) # bumps lock_version
# Concurrent update on a stale order raises ActiveRecord::StaleObjectError
```

For pessimistic locking (block other readers/writers until commit), use `with_lock` - issues `SELECT ... FOR UPDATE`:

```ruby
order.with_lock do
  order.update!(total: recompute_total)
end
```

Pessimistic locking is correct for short critical sections that read-then-write the same row. Optimistic locking is correct when conflicts are rare and you can afford to retry.

### Async Queries with `load_async`

For dashboards and screens that fetch several independent queries, `load_async` runs them on a background thread pool so the request-time wall clock is the slowest query, not the sum:

```ruby
class DashboardController < ApplicationController
  def show
    @recent_orders = Order.recent.limit(10).load_async
    @top_products  = Product.top_sellers.limit(5).load_async
    @open_tickets  = Ticket.open.load_async
    # All three queries run concurrently; ERB awaits each as it's referenced
  end
end
```

Configure the thread pool in `config/application.rb`: `config.active_record.async_query_executor = :global_thread_pool`. Do not use inside a transaction (the async thread cannot see uncommitted state).

### `find_each` and Ordering

`find_each` and `in_batches` ignore any custom `ORDER BY` and force `ORDER BY id ASC` so the cursor advances safely. If your code depends on `order(:created_at)`, batching will silently drop it. Use `in_batches` over a date-keyed scope, or process in chunks via explicit `where("id > ?", cursor)` if order matters.

### PostgreSQL Features

```ruby
# JSONB with GIN index
class AddMetadataToOrders < ActiveRecord::Migration[7.2]
  def change
    add_column :orders, :metadata, :jsonb, default: {}, null: false
    add_index :orders, :metadata, using: :gin
  end
end

# Query JSONB
Order.where("metadata @> ?", { source: "web" }.to_json)

# Array columns
add_column :users, :tags, :string, array: true, default: []
User.where("'admin' = ANY(tags)")

# Partial indexes - index only relevant rows (e.g., non-terminal statuses)
add_index :orders, :created_at, where: "status IN (0, 1, 2)", name: "idx_active_orders"

# EXPLAIN ANALYZE in console
ActiveRecord::Base.connection.execute("EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 1")
```

## Output Format

When applying ActiveRecord patterns, document each optimization:

```
Pattern: {N+1 Fix | Scope | Association | Batch Processing | Query Optimization | PostgreSQL Feature}
Model: {model name}
Change: {description of what was changed}
Queries: {before} -> {after} (estimated)
```

## Avoid

- `default_scope` - infects all queries, use explicit scopes instead
- N+1 in serializers - always preload associations before serializing
- `.all.each` on large tables - loads entire table into memory, use `find_each`
- Callbacks for business logic - use service objects instead
- `update_attribute` - skips validations, use `update!`
- String interpolation in queries - SQL injection risk, use parameterized queries
- Missing `dependent:` on `has_many` - orphaned records on parent deletion
- Enum without explicit integer mapping - column values shift when entries are reordered
