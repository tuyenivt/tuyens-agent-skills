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
- `dependent:` is required on every `has_many` / `has_one` that owns its records. On a `has_many :through` it acts on the **join** records, not the target records (and the join model's source association must be a `belongs_to`), so a bare `through` is compliant as long as the direct `has_many` to the join model carries it.
- `enum` with explicit integer mapping - positional shorthand shifts when entries reorder.
- Parameterized queries only - never string interpolation.
- `find_each` / `in_batches` for large datasets - never `.all.each`.
- On unloaded relations, blockless `any?` and `exists?` both issue `SELECT 1 LIMIT 1`; `any? { }` with a block loads every row. On loaded associations: `size`/`any?` are free; `exists?`/`count` re-query.
- `update!` over `update_attribute` (latter skips validations).
- Pessimistic lock by PK only; keep the critical section short and free of network calls. Side-effect callbacks: see `rails-transaction-patterns`.
- A read-modify-write on a column another process also writes *requires* a lock (or an atomic `UPDATE ... SET col = col + ?`); it is not a style choice. Optimistic vs pessimistic is the choice: `lock_version` when conflicts are rare and a retry is cheap, `with_lock` when the row is hot enough that `StaleObjectError` would storm.

## Patterns

### N+1 fix

```ruby
# Bad - one query per user
User.all.each { |u| u.orders.map(&:total_cents).sum }

# Good - eager load
User.includes(:orders)                                       # separate query (default)
User.preload(:orders)                                        # always separate (safe with scopes)
User.eager_load(:orders).merge(Order.active)                 # LEFT OUTER JOIN when WHERE on assoc
```

Eager loading does not fix a per-row `count`: `u.orders.count` re-queries even on a loaded association (Rule above). That one needs `size`, or a `counter_cache`.

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

Options chain: a `:destroy` cascade halts when a grandchild association uses `:restrict_with_error` (deleting Customer destroys Subscriptions - which fails if any Subscription has Invoices). Trace the full cascade before choosing; `:nullify` on the restricting level is the usual escape.

`counter_cache` is declared on the `belongs_to` side (`belongs_to :user, counter_cache: true`) with an integer column on the parent (`users.orders_count`, `null: false, default: 0`). Backfill existing rows with `User.reset_counters(id, :orders)` in a data migration; from then on `user.orders.size` reads the column with no query.

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

Index endpoints computing per-row aggregates (`sum`, `count` per parent) at scale: aggregate in SQL (`Order.group(:customer_id).sum(:total_cents)`, or a `counter_cache` column) and paginate - preloading every child row moves the N+1 into memory.

`find_each` / `in_batches` discard a custom `ORDER BY` (logging "Scoped order is ignored, it's forced to be batch order") and batch on the primary key; `order: :asc | :desc` picks the direction. For any other order, Rails 8.0 adds a `cursor:` option that batches on arbitrary columns (`in_batches(cursor: [:shop_id, :id])`); on 7.2 hand-roll it with `where("id > ?", cursor)`.

### Bulk inserts and upserts

`create!` in a loop fires one INSERT plus all callbacks per row. `insert_all` / `upsert_all` issue one multi-row statement and run 50-100x faster - but skip validations, callbacks, and model-level `attribute ... default:` values. Type casting and serialization still apply (values go through `type_for_attribute`, so `enum` and `serialize` behave), and timestamps are set: `record_timestamps` follows the model config, on by default. Untrusted input (CSV, API payloads) must be validated/coerced before the call - instantiate-and-`validate` (or a form object) per row, then feed the clean `attributes` to the bulk call; DB constraints are the only remaining guard. Slice into batches of 1-5K rows to bound statement size and undo-log growth.

```ruby
rows.each_slice(2_000) { |batch| OrderRollup.insert_all(batch, returning: %w[id]) }
OrderRollup.upsert_all(rows, unique_by: :order_id, update_only: %i[total_cents updated_at])
```

`unique_by:` is PostgreSQL/SQLite-only - on MySQL it raises; drop it and MySQL upserts via `ON DUPLICATE KEY` against the table's unique indexes. `returning:` has the same support: PostgreSQL and SQLite (both answer `supports_insert_returning?`), MySQL raises.

### Pessimistic locking

```ruby
# with_lock opens its own transaction - the default for single-record critical sections
order = Order.find(order_id)
order.with_lock { order.update!(state: "closed") }

# lock.find inside an explicit transaction - when the txn spans more than the locked row
Order.transaction do
  order = Order.lock.find(order_id)  # WHERE id = ? FOR UPDATE
  order.update!(state: "closed")
end
```

Retry on `ActiveRecord::Deadlocked` is the caller's job - pattern in `rails-transaction-patterns`.

**MySQL default `REPEATABLE READ`: row + gap (next-key) locks.** Non-unique-index range scans gap-lock the range and block inserts - the #1 source of MySQL deadlocks in Sidekiq workloads. Lock by PK; keep the critical section short. PostgreSQL has no gap-lock equivalent; same discipline still applies.

For multiple rows, fetch IDs unlocked first, then lock in small PK batches - one transaction per slice, never one over the whole set:

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
- Missing `inverse_of` under `load_defaults < 6.1` (6.1 turns on `has_many_inversing`)

For an audit of implicit-config state, see `rails-implicit-config-audit`.

### Async queries (`load_async`)

For dashboards with several independent queries, wall clock becomes the slowest, not the sum - but only once an executor is configured. `config.active_record.async_query_executor` defaults to `nil` in Rails 7.2/8.0 and no `load_defaults` sets it, so without this line every `load_async` runs inline and buys nothing:

```ruby
config.active_record.async_query_executor = :global_thread_pool   # required prerequisite

@recent_orders = Order.recent.limit(10).load_async
@top_products  = Product.top_sellers.limit(5).load_async
@order_count   = Order.recent.async_count                          # async calculations, 7.1+ (async_sum, async_pluck ...); plain count/sum run inline
```

The executor is process-global and bounded by `global_executor_concurrency` (default 4), so N async queries in one request cost at most 4 extra connections, not N (see `rails-connection-pool-sizing`). Inside an open transaction `load_async` silently degrades to foreground execution - no correctness risk, just no win, so calling it there is pointless rather than dangerous.

### DB-specific columns and indexes

```ruby
# MySQL 8.0+ (InnoDB) - JSON, functional index (8.0.13+; JSON_VALUE form 8.0.21+), fulltext
add_column :orders, :metadata, :json, null: false
add_index :orders, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_orders_tier"
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

One block per pattern applied (a task spanning N+1 + Association emits two). In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Any field may carry `- GAP` with the observed non-compliant value. In build mode, a pre-existing violation the change touches (positional enum, `default_scope`, missing `dependent:`) is a numbered finding too.

```
Pattern: {N+1 Fix | Projection (pluck/select) | Scope | Enum | Association | Counter Cache | Normalization | Callback | Batch (read batching) | Bulk Write (insert_all / upsert_all) | Locking | Implicit Load | Async Query | Parameterization | Denormalized Counter | DB Feature}

Model: {name, or the models a cross-model pattern spans}

Adapter: {MySQL | PostgreSQL | SQLite | n/a - adapter-independent | unknown - read config/database.yml}

Change: {description; a Denormalized Counter names the single writer and the recompute path}

Schema: {migration DDL in one line | none}

Queries: {before} -> {after}   # query counts or formulas, e.g. "1 + 4N -> 4" (nest fan-outs as "1 + N + NM"). Write "n/a" for greenfield and for any change whose point is correctness rather than query shape - Locking, Parameterization, DB Feature, Association config, Scope, Enum, Normalization, Callback placement. A Counter Cache or Denormalized Counter states the read it removes ("1 + N -> 1"); Projection states the payload change and Async Query the wall-clock change instead of a count
```

`Denormalized Counter` covers a state-scoped or conditional counter (`open_shipment_count`, "currently active" tallies), which `counter_cache:` cannot express - it counts unconditional create/destroy only. Name the single writer and the recompute path.

## Avoid

- N+1 in serializers - preload before serializing
- `.includes` papering over `touch:` / `autosave:` / callback side effects - remove the source or add `inverse_of`
- Non-PK `lock` on MySQL `REPEATABLE READ` - gap-lock cascade
- Optimistic locking on hot rows - `StaleObjectError` storms
- Callbacks for business logic - use service objects
- Missing `dependent:` on `has_many` - orphaned records
