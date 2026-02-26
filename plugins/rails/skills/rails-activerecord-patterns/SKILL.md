---
name: rails-activerecord-patterns
description: "ActiveRecord optimization for Rails 7+/8. N+1 prevention (includes/preload/eager_load), scopes, associations, counter_cache, find_each, connection pooling, PostgreSQL features."
user-invocable: false
---

## 1. N+1 Prevention

```ruby
# ❌ N+1 — fires a query per order
users = User.all
users.each { |u| puts u.orders.count }

# ✅ includes — eager loads with separate query
users = User.includes(:orders).all

# ✅ preload — always separate queries (safe with complex scopes)
users = User.preload(:orders).all

# ✅ eager_load — LEFT OUTER JOIN (needed for WHERE on association)
users = User.eager_load(:orders).where(orders: { status: :active })

# ✅ strict_loading! — raise if lazy loading happens
user = User.strict_loading!.first
user.orders # => ActiveRecord::StrictLoadingViolationError

# ✅ Application-wide strict loading (Rails 6.1+)
# config/environments/development.rb
config.active_record.strict_loading_by_default = true
```

**Bullet gem** — detects N+1 in development:

```ruby
# Gemfile
gem "bullet", group: :development

# config/environments/development.rb
Bullet.enable = true
Bullet.alert = true
Bullet.rails_logger = true
```

## 2. Scopes

```ruby
class Order < ApplicationRecord
  # ✅ Chainable scopes
  scope :active, -> { where(status: :active) }
  scope :recent, -> { order(created_at: :desc) }
  scope :for_customer, ->(customer_id) { where(customer_id: customer_id) }
  scope :total_above, ->(amount) { where("total > ?", amount) }

  # ✅ merge for cross-model scopes
  scope :with_active_customers, -> { joins(:customer).merge(Customer.active) }
end

# ❌ NEVER use default_scope — it infects every query and is hard to undo
```

## 3. Associations

```ruby
class User < ApplicationRecord
  has_many :orders, dependent: :destroy
  has_many :products, through: :orders
  has_one :profile, dependent: :destroy

  # ✅ counter_cache for count queries
  has_many :comments, counter_cache: true
end

class Order < ApplicationRecord
  belongs_to :user, counter_cache: true
  belongs_to :customer

  # ✅ has_many :through over has_and_belongs_to_many
  has_many :line_items, dependent: :destroy
  has_many :products, through: :line_items

  # Polymorphic — use sparingly, consider STI or dedicated tables
  has_many :comments, as: :commentable
end
```

**Dependent options:**

- `dependent: :destroy` — runs callbacks (safe, slower)
- `dependent: :delete_all` — skips callbacks (fast, no cascade)
- `dependent: :nullify` — sets FK to NULL
- `dependent: :restrict_with_error` — prevents deletion

## 4. Query Optimization

```ruby
# ✅ select — only load needed columns
User.select(:id, :name, :email)

# ✅ pluck — returns raw arrays, no AR objects
User.where(active: true).pluck(:email)
# => ["a@b.com", "c@d.com"]

# ✅ find_each / in_batches for large datasets
User.find_each(batch_size: 1000) { |user| process(user) }
User.in_batches(of: 1000) { |batch| batch.update_all(synced: true) }

# ✅ exists? over any? (stops at first match)
User.where(email: "a@b.com").exists?

# ✅ size over count on loaded associations (uses counter_cache or length)
user.orders.size  # uses counter_cache if available
user.orders.count # always hits DB
```

## 5. Connection Pooling

```ruby
# config/database.yml
production:
  pool: <%= ENV.fetch("RAILS_MAX_THREADS") { 5 } %>
```

**Formula:** `pool = Puma workers × threads`

- 3 workers × 5 threads = 15 pool
- PgBouncer for multiplexing when pool > 20
- Monitor with `ActiveRecord::Base.connection_pool.stat`

## 6. PostgreSQL Features

```ruby
# JSONB with GIN index
class AddMetadataToOrders < ActiveRecord::Migration[7.1]
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

# Partial indexes — index only relevant rows
add_index :orders, :created_at, where: "status = 'active'", name: "idx_active_orders"

# EXPLAIN ANALYZE in console
ActiveRecord::Base.connection.execute("EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'active'")
```

## 7. Anti-Patterns

- ❌ `default_scope` — infects all queries, use explicit scopes
- ❌ N+1 in serializers — always preload associations before serializing
- ❌ `.all.each` — loads entire table into memory, use `find_each`
- ❌ Callbacks for business logic — use service objects instead
- ❌ `update_attribute` — skips validations, use `update!`
- ❌ String interpolation in queries — SQL injection risk, use parameterized queries
