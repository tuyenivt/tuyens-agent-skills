---
name: rails-code-explain
description: Rails code explanation signals: request lifecycle, AR callbacks/transactions, ActiveJob, Zeitwerk, ActionCable, concerns.
metadata:
  category: backend
  tags: [explanation, code-understanding, rails, activerecord, ruby]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Composed by `task-code-explain` when the detected stack is Rails.

## When to Use

- Workflow needs Rails-specific signals: request lifecycle, controller filters, AR callbacks, transaction scope, autoload, ActionCable, ActiveJob
- Target code lives in a Rails app

## Rules

- Identify the layer first: controller, model, mailer, job, channel, service, concern, initializer
- Controllers: list filters in execution order; note short-circuits (`render`/`redirect_to`/`head`)
- Models: surface callbacks, validations, transaction boundaries; distinguish `after_commit` vs `after_save` rollback semantics
- Concerns: name the including class - they are mixins, not isolated modules

## Patterns

### Request Lifecycle

`Rack middleware -> Routes -> Controller#action -> View / JSON -> Response`

- Middleware order is set in `config/application.rb`; `Rack::Attack`, logging, Warden live here
- `resources :foo` -> 7 RESTful routes; nested routes change param names; `constraints:` filters requests
- `before_action` filters run unless skipped with `only:`/`except:`/`skip_before_action` (inherited from `ApplicationController`)
- Strong params (`params.require(:x).permit(...)`) is the input contract; `permit!` allows everything (dangerous)

### ActiveRecord Callbacks

| Callback                                      | When                                | Note                                               |
| --------------------------------------------- | ----------------------------------- | -------------------------------------------------- |
| `before_validation`                           | Before validators                   | Normalization                                      |
| `before_save` / `before_create`               | Before INSERT/UPDATE                |                                                    |
| `after_save`                                  | Inside transaction, pre-commit      | Rolls back atomically with parent                  |
| `after_commit`                                | After outermost transaction commits | Non-DB side effects (jobs, emails, APIs)           |
| `after_create_commit` / `after_update_commit` | Event-filtered variants             |                                                    |
| `before_destroy`                              | Before DELETE                       | `dependent: :destroy` cascades; `:delete_all` skips |

Business logic in `after_save` is implicit invocation - any save anywhere triggers it. Surface as a gotcha.

### Transactions

- `ActiveRecord::Base.transaction { }`; nested -> savepoints; `requires_new: true` commits/rolls back inner independently
- `save!` raises on failure - rescue **outside** the block
- `update_columns` / `update_all` bypass validations and callbacks
- `after_commit` fires after the **outermost** transaction

### N+1

`User.all.each { |u| u.posts }` -> one query per user. Fix: `includes(:posts)` (preload, separate query) or `eager_load(:posts)` (single LEFT JOIN). `to_json` on serializers calling associations is a hidden N+1 source; `bullet` flags in dev.

### Zeitwerk (Rails 6+)

Filenames match constants: `app/services/orders/processor.rb` -> `Orders::Processor`. Errors surface lazily in dev, eagerly at boot in production.

### Concerns

`include MyConcern` is a mixin - methods become instance methods, `included { }` runs at include time. `extend ActiveSupport::Concern` enables `class_methods do`. Concerns shared across many classes create implicit coupling.

### ActiveJob, ActionCable, Storage, Auth

- ActiveJob: `perform_later` enqueues, `perform_now` runs synchronously. Args must be serializable; AR records are GlobalID-serialized (re-fetched on perform). Sidekiq default retry is 25 - can mask transient bugs (see `rails-sidekiq-patterns`).
- ActionCable: channels in `app/channels/`; identify user in `ApplicationCable::Connection#connect`; `stream_from`/`server.broadcast`. No HTTP session/cookie sharing by default.
- Active Storage: `has_one_attached :x` adds polymorphic associations; variants are lazy; direct upload bypasses the Rails server.
- Devise: `authenticate_user!` redirects/raises; `current_user` lazily reads session; `user_signed_in?` is the boolean. Warden lives in middleware.

### Sidekiq / Batches / Pools

When code involves Sidekiq, long batches, or `load_async`:
- Each Sidekiq thread holds one DB connection (`rails-connection-pool-sizing`)
- RSS climbs from GC + glibc malloc (`rails-batch-processing-patterns`)
- Never wrap `find_each` in `Model.transaction`; chunk transactions (`rails-batch-processing-patterns`)

## Output Format

Inject into `task-code-explain` sections:

**Flow Context:** layer; controller filter chain in execution order (incl. inherited from concerns + `ApplicationController`); model callbacks/validations that fire; job enqueue point, backend, retry policy.

**Non-Obvious Behavior:** `update_columns`/`update_all` bypassing callbacks; `dependent: :delete_all` skipping callbacks; `after_commit` vs `after_save` rollback semantics; Zeitwerk filename/constant mismatches; N+1 in serializers/views; `permit!`; ActionCable not sharing session; inherited filters.

**Key Invariants:** Zeitwerk filename = constant; job args GlobalID-serializable; strong params required for mass assignment; DB pool >= in-process thread count.

**Change Impact:** new callback -> fires on every save; rename class -> rename file; new `before_action` -> applies to every action unless filtered; change `dependent:` -> changes callback firing; modify concern -> every including class affected.

## Avoid

- Describing controller actions without listing active filters
- Treating `update_columns` and `update` as equivalent
- Glossing over `after_commit` vs `after_save` rollback semantics
- Listing callbacks without naming when they fire
- Confusing `authenticate_user!` (raises/redirects) with `user_signed_in?` (boolean)
