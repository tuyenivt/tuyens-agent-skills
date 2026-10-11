---
name: rails-activerecord-patterns
description: ActiveRecord patterns for Rails 7.2+ on MySQL 8.0: N+1 prevention, scopes, enum, locking, callbacks, async queries, JSON/fulltext.
metadata:
  category: backend
  tags: [ruby, rails, activerecord, mysql, performance]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing associations, scopes, enums
- Fixing N+1 queries (Bullet flags, slow index endpoints)
- Choosing dependent options, counter_cache placement
- Choosing optimistic vs pessimistic locking
- Placing callbacks: `after_save` vs `after_commit`
- Adding MySQL-specific columns and indexes (JSON, functional, multi-valued, fulltext)

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
- A read-modify-write on a column another process also writes *requires* a lock (or an atomic `UPDATE ... SET col = col + ?`); it is not a style choice. Optimistic vs pessimistic is the choice: `lock_version` when conflicts are rare and a retry is cheap, `with_lock` when the row is hot enough that `StaleObjectError` would storm. The atomic UPDATE (`update_counters`) fits when the new value depends on no check; a check (`reserved + n <= on_hand`) needs the lock, or the check folded into the UPDATE's `WHERE` with the affected-row count read back.

## Patterns

### N+1 fix

```ruby
# Bad - one query per user
User.all.each { |u| u.orders.map(&:total_cents).sum }

# Good - eager load
User.includes(:orders)                                       # separate query (default)
User.preload(:orders)                                        # always separate (safe with scopes)
User.eager_load(:orders).merge(Order.active)                 # LEFT OUTER JOIN when WHERE on assoc
# ^ filters parents too: users with no active order drop out, and the loaded `orders`
#   holds only active rows. "All users, their active orders": has_many :active_orders,
#   -> { active }, class_name: "Order"; then User.preload(:active_orders)
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
| `:delete_all` (`has_one`: `:delete`) | Direct SQL, skips callbacks | Performance-critical, no child callbacks |
| `:nullify`             | Sets FK to NULL             | Children can exist independently                |
| `:restrict_with_error` | Prevents parent deletion    | Children must not be orphaned                   |

Options chain: a `:destroy` cascade stops at a grandchild association using `:restrict_with_error` (deleting Customer destroys Subscriptions - which fails if any Subscription has Invoices). A `has_many` destroys its children with `destroy!`, so the parent's `destroy` raises `ActiveRecord::RecordNotDestroyed` and rolls back; a `has_one` child's abort makes the parent's `destroy` return `false`. Trace the full cascade before choosing; `:nullify` on the restricting level is the usual escape.

`counter_cache` is declared on the `belongs_to` side (`belongs_to :user, counter_cache: true`) with an integer column on the parent (`users.orders_count`, `null: false, default: 0`). On an existing table, declare it `counter_cache: { active: false }` (7.2+) so reads keep counting rows, backfill with `User.reset_counters(id, :orders)` in a data task, then drop `active: false`; from then on `user.orders.size` reads the column with no query. Turning it on before the backfill makes `size` return the column's 0 default.

A state-scoped counter (`open_shipment_count`) is a Denormalized Counter: one writer - the state-change code - issues an atomic `UPDATE ... SET col = col + 1` (or `- 1`) in the same transaction, and a recompute task (`COUNT(*) ... WHERE state = ?`) corrects drift.

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

`find_each` / `in_batches` discard a custom `ORDER BY` (a logged warning, or a raise under `error_on_ignored_order`) and batch on the primary key; `order: :asc | :desc` picks the direction. For any other order, Rails 8.0 adds a `cursor:` option that batches on arbitrary columns (`in_batches(cursor: [:shop_id, :id])`); on 7.2 hand-roll a composite keyset in the expanded form MySQL can range-scan - `where("shop_id > ? OR (shop_id = ? AND id > ?)", last_shop_id, last_shop_id, last_id).order(:shop_id, :id).limit(n)` - over columns that are unique together.

### Bulk inserts and upserts

`create!` in a loop fires one INSERT plus all callbacks per row. `insert_all` / `upsert_all` issue one multi-row statement and run 50-100x faster - but skip validations, callbacks, and model-level `attribute ... default:` values. Type casting and serialization still apply (values go through `type_for_attribute`, so `enum` and `serialize` behave), and timestamps are set: `record_timestamps` follows the model config, on by default. Untrusted input (CSV, API payloads) must be validated/coerced before the call - instantiate-and-`validate` (or a form object) per row, then feed the clean `attributes` to the bulk call; DB constraints are the only remaining guard. Slice into batches of 1-5K rows to bound statement size and undo-log growth.

```ruby
rows.each_slice(2_000) { |batch| OrderRollup.insert_all(batch) }
rows.each_slice(2_000) { |batch| OrderRollup.upsert_all(batch, update_only: %i[total_cents updated_at]) }   # ON DUPLICATE KEY UPDATE
```

MySQL rejects `unique_by:` and `returning:` (both raise `ArgumentError`): the upsert conflicts on *any* unique index of the table, the primary key included, so a table with two unique keys can update a row other than the one you meant - keep one unique key per upsert target, or split the write: `insert_all` the new rows (duplicates skipped) and `update_all` the existing ones by the intended key. With no `returning:`, re-read ids by the unique key after the insert. Every upsert row that hits a duplicate still consumes an `AUTO_INCREMENT` value, so a high-churn upsert table burns ids - `bigint` keys absorb it.

### Pessimistic locking

```ruby
# with_lock opens its own transaction - the default for single-record critical sections
order = Order.find(order_id)
order.with_lock { order.update!(status: :cancelled) }

# lock.find inside an explicit transaction - when the txn spans more than the locked row
Order.transaction do
  order = Order.lock.find(order_id)  # WHERE id = ? FOR UPDATE
  order.update!(status: :cancelled)
end
```

Retry on `ActiveRecord::Deadlocked` is the caller's job - pattern in `rails-transaction-patterns`.

**MySQL default `REPEATABLE READ`: row + gap (next-key) locks.** Non-unique-index range scans gap-lock the range and block inserts - the #1 source of MySQL deadlocks in Sidekiq workloads. Lock by PK; keep the critical section short.

For multiple rows, fetch IDs unlocked first, then lock in small PK batches - one transaction per slice, never one over the whole set:

```ruby
ids = Order.where(customer_id: id).order(:id).pluck(:id)   # one global lock order across workers
ids.each_slice(100) do |batch|
  Order.transaction { Order.where(id: batch).order(:id).lock.each(&:cancelled!) }
end
```

For high-contention nightly jobs, fan out from one orchestrator to N per-record Sidekiq workers - each locks one row by PK in its own short transaction (see `rails-work-splitter-patterns`).

### Optimistic locking

Add `lock_version` for low-contention concurrent updates. Rails bumps it on every update and raises `ActiveRecord::StaleObjectError` when another writer beat this one.

```ruby
add_column :orders, :lock_version, :integer, null: false, default: 0
```

Hot rows produce `StaleObjectError` storms - use pessimistic by PK instead.

### Implicit association loads on save

`update`/`save` can load associations the action body never references. Source is declarative, not in the controller. When `.includes` "fixes" an N+1 on an update action without you wanting those associations in scope, remove the source:

- `belongs_to :parent, touch: true` - saving the child touches the parent
- `has_many :children, autosave: true` (explicit or via `accepts_nested_attributes_for`) - parent save walks children *already loaded* and writes the dirty ones; it issues no load of its own, so it adds UPDATEs, not an N+1
- Callback reading `self.<association>` - forces a load at save time. Use `self.foo_id`, not `self.foo.id`, when only the FK is needed
- Missing `inverse_of` on a scoped association below `load_defaults 7.0` (7.0 turns on `automatic_scope_inversing`), or at any version where `foreign_key:` / `:through` defeats automatic inversion - simple unscoped pairs invert on their own

For an audit of implicit-config state, see `rails-implicit-config-audit`.

### Async queries (`load_async`)

For dashboards with several independent queries, wall clock becomes the slowest, not the sum - but only once an executor is configured. `config.active_record.async_query_executor` defaults to `nil` in Rails 7.2/8.0 and no `load_defaults` sets it, so without this line every `load_async` runs inline and buys nothing:

```ruby
config.active_record.async_query_executor = :global_thread_pool   # required prerequisite

@recent_orders = Order.recent.limit(10).load_async
@top_products  = Product.top_sellers.limit(5).load_async
@order_count   = Order.recent.async_count                          # async calculations, 7.1+ (async_sum, async_pluck ...); plain count/sum run inline
@order_count.value                                                 # an ActiveRecord::Promise - .value blocks for the number
```

The executor is process-global and bounded by `global_executor_concurrency` (default 4), so N async queries in one request cost at most 4 extra connections, not N (see `rails-connection-pool-sizing`). Inside an open transaction `load_async` silently degrades to foreground execution - no win, no correctness risk.

### DB-specific columns and indexes

```ruby
# MySQL 8.0 (InnoDB) - JSON column, functional index (8.0.13+; JSON_VALUE form 8.0.21+)
add_column :orders, :metadata, :json   # no literal DEFAULT on JSON; 8.0.13+ takes an expression: default: -> { "(JSON_OBJECT())" }
add_index :orders, "(JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)))", name: "idx_orders_tier"
Order.where("JSON_VALUE(metadata, '$.tier' RETURNING CHAR(50)) = ?", tier)   # repeat the indexed expression exactly

# Multi-valued index (8.0.17+) - the array-column substitute; serves MEMBER OF / JSON_CONTAINS / JSON_OVERLAPS
add_index :users, "(CAST(tags->'$' AS UNSIGNED ARRAY))", name: "idx_users_tags"
User.where("? MEMBER OF(tags->'$')", tag_id)

# Fulltext - the default parser splits on spaces; Japanese / Chinese / Korean text needs ngram
add_index :products, :description, type: :fulltext
execute "CREATE FULLTEXT INDEX idx_products_name_ngram ON products (name) WITH PARSER ngram"
Product.where("MATCH(name) AGAINST(? IN BOOLEAN MODE)", query)              # ngram tokens: ngram_token_size, default 2
```

A `json` column is already cast by the adapter - `serialize ..., coder: JSON` on one raises `ColumnNotSerializableError` and any other coder double-encodes; drop it. `schema.rb` keeps `type: :fulltext` but drops `WITH PARSER ngram`, so a database built from it silently uses the default parser - an ngram index needs `schema_format = :sql`.

No native array type and no partial index (`where:`) - use the multi-valued index above, and a composite or functional index for the partial-index case. Slow queries: the slow query log plus `performance_schema.events_statements_summary_by_digest` (`sys.statement_analysis` reads it ranked). Migration safety for these operations: `rails-migration-safety`.

## Output Format

One block per change, named by its pattern (a task spanning N+1 + Association emits two; three independent indexes are three DB Feature blocks). In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. In review or diagnosis mode each field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and its numbered finding explains the fix. A build-mode block holds corrected values only, and build mode still numbers findings for the pre-existing violations it touches. A request to design or change code is build mode; one that assesses or diagnoses code as it stands is review or diagnosis mode. In build mode, a pre-existing violation the change touches (positional enum, `default_scope`, missing `dependent:`) is a numbered finding too.

`Queries` carries query counts or formulas (`1 + 4N -> 4`; nest fan-outs as `1 + N + NM`), counted for N+1 Fix, Batch, Bulk Write and Implicit Load. A Counter Cache or Denormalized Counter states the read it removes (`1 + N -> 1`), Projection the payload change, Async Query the wall-clock change. It is `n/a` for greenfield and for changes whose point is correctness rather than query shape: Locking, Parameterization, DB Feature, Association, Scope, Enum, Normalization, Callback. `Denormalized Counter` covers a state-scoped or conditional counter (`open_shipment_count`), which `counter_cache:` cannot express - it counts every associated row (create, destroy, FK reassignment) with no condition.

```
Pattern: {N+1 Fix | Projection (pluck/select) | Scope | Enum | Association | Counter Cache | Normalization | Callback | Batch (read batching) | Bulk Write (insert_all / upsert_all) | Locking | Implicit Load | Async Query | Parameterization | Denormalized Counter | DB Feature}

Model: {name, or the models a cross-model pattern spans}

Adapter: {MySQL | n/a - adapter-independent | unknown - read config/database.yml}

Change: {description; a Denormalized Counter names the single writer and the recompute path}

Schema: {migration DDL in one line | none}

Queries: {before} -> {after} | n/a
```

## Avoid

- N+1 in serializers - preload before serializing
- `.includes` papering over `touch:` / callback loads - remove the source or add `inverse_of`
- Non-PK `lock` on MySQL `REPEATABLE READ` - gap-lock cascade
- Optimistic locking on hot rows - `StaleObjectError` storms
- Callbacks for business logic - use service objects
- Missing `dependent:` on an owning `has_many` / `has_one` - orphaned records
