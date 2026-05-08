---
name: rails-code-explain
description: Ruby on Rails framework signals for code explanation - request lifecycle through middleware and controllers, ActiveRecord callbacks and transactions, ActiveJob workers, Zeitwerk autoloading, ActionCable, and concern composition. Used by task-code-explain to explain Rails code with stack-aware gotchas.
metadata:
  category: backend
  tags: [explanation, code-understanding, rails, activerecord, ruby]
user-invocable: false
---

# Rails Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Ruby on Rails.

## When to Use

- A workflow needs Rails-specific signals: request lifecycle, controller filters, AR callbacks, transaction scope, autoload boundaries, ActionCable channels, ActiveJob workers.
- The target code is in a Rails app (`config/application.rb`, `Gemfile` with `rails`).

## Rules

- Identify the layer first: controller, model, mailer, job, channel, service object, concern, or initializer. Each has different lifecycle and gotchas.
- For controllers, list `before_action`/`around_action`/`after_action` filters in execution order before describing the action - filters can short-circuit (`render`/`redirect_to`/`head`) and prevent the action from running.
- For models, identify all callbacks (`before_save`, `before_create`, `after_commit`, `before_destroy`, etc.) and any `validates_*` declarations - these run on every save and are a common source of "why is this slow?" or "why does X happen even when I don't ask for it".
- Surface AR transaction boundaries explicitly - which methods open transactions, which `after_commit` hooks fire only after commit (not after_save).
- For concerns, identify the included class so the code's actual scope is visible; concerns are mixins, not isolated modules.

## Patterns

### Request Lifecycle

```
Rack middleware -> Routes (config/routes.rb) -> Controller#action -> View / JSON -> Response
```

For each layer, what to flag:

- **Middleware** (`config/application.rb` `config.middleware`, also Rack apps mounted in routes.rb): order matters; `Rack::Attack`, request logging, Warden/Devise auth all live here.
- **Routes**: `resources :foo` generates 7 RESTful routes; nested routes change parameter names; constraints (e.g., `constraints: { format: :json }`) filter requests.
- **Controller filters**: `before_action :authenticate_user!` (Devise) runs before every action unless `only:`/`except:` excludes. `skip_before_action` removes inherited filters.
- **Action**: Strong params (`params.require(:x).permit(:y, :z)`) is the input contract.
- **View / JSON**: ERB templates, Jbuilder, or serializers (ActiveModel::Serializer, fast_jsonapi).

### ActiveRecord Callbacks

| Callback           | When it fires                                     | What to flag                                                                                                                  |
| ------------------ | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `before_validation` | Before validators                               | Useful for normalization (downcase email, strip whitespace)                                                                   |
| `before_save`      | Before INSERT or UPDATE                            | Runs on both creates and updates                                                                                              |
| `before_create`    | Before INSERT only                                 |                                                                                                                               |
| `after_save`       | Inside the transaction, before commit              | Side effects here roll back if the outer transaction fails                                                                    |
| `after_commit`     | After the transaction commits                      | Use for non-DB side effects (enqueue jobs, send emails, hit external APIs); guaranteed not to fire on rollback                |
| `after_create_commit` / `after_update_commit` | Variant of `after_commit` filtered by event |                                                                                                                               |
| `before_destroy`   | Before DELETE                                      | `dependent: :destroy` cascades trigger callbacks on every child; `dependent: :delete_all` skips callbacks (faster, less safe) |

**Callback abuse pattern:** business logic in `after_save` instead of service objects creates implicit invocation - changing a record anywhere triggers side effects. Surface this as a gotcha.

### Transactions

- `ActiveRecord::Base.transaction { }` opens a transaction. Nested transactions use savepoints by default (since Rails 4) but `requires_new: true` is required to actually commit/rollback the inner separately.
- `save!` raises on validation/constraint failure inside a transaction; rescue **outside** the block, not inside.
- `update_columns(...)` and `update_all(...)` bypass validations and callbacks. Common gotcha when an "update" is silently skipping logic.
- `after_commit` hooks fire after the **outermost** transaction commits, not after the inner transaction.

### N+1 Queries

- `User.all.each { |u| u.posts }` issues one query per user. Fix with `User.includes(:posts)` (separate query) or `User.eager_load(:posts)` (single LEFT JOIN).
- `bullet` gem (when present) flags N+1 in development. Check for it in `Gemfile`.
- `to_json` on a serializer that calls `belongs_to`/`has_many` is a hidden N+1 source; flag in serializer review.

### Zeitwerk Autoloading (Rails 6+)

- Filenames must match class/module names: `app/services/order_processor.rb` -> `OrderProcessor`.
- Namespaced classes: `app/services/orders/processor.rb` -> `Orders::Processor`.
- `app/lib/`, `app/services/`, etc. are autoload roots if added to `config.autoload_paths`.
- `Rails.autoloaders.main.eager_load_dirs` controls eager loading in production.
- Autoload errors surface only when the constant is referenced (in dev mode, lazily); production eager-loads at boot.

### Concerns

- `include MyConcern` is a Ruby mixin: methods become instance methods, `included { }` block runs at include time (often `has_many`, `validates`).
- `extend ActiveSupport::Concern` enables `class_methods do { }` and reliable `included` blocks.
- A concern can call `before_action` (in a controller concern) or `before_save` (in a model concern); these chain with the host class's filters.
- Concerns shared across many classes create implicit coupling - changing the concern affects every host.

### ActiveJob and Background Jobs

- `MyJob.perform_later(arg)` enqueues to the configured backend (Sidekiq, Resque, Solid Queue, Active Job inline in test).
- `perform_now` runs synchronously in the current process - usually only in tests.
- Job arguments must be serializable: AR records are GlobalID-serialized (re-fetched from DB on perform); custom objects need explicit serialization.
- Sidekiq middleware can wrap jobs (logging, error tracking, retry policies). Check `config/initializers/sidekiq.rb`.
- Retries: ActiveJob's `retry_on` and Sidekiq's default retry policy can mask transient bugs; failures retry up to 25 times by default in Sidekiq.

### ActionCable / WebSockets

- Channels live in `app/channels/`; identified user via `connect` method on `ApplicationCable::Connection`.
- `subscribed`/`unsubscribed` lifecycle hooks; `stream_from "name"` subscribes to broadcast streams.
- `ActionCable.server.broadcast("name", data)` from anywhere publishes to subscribers.
- Cable connections do not share session/cookie state with HTTP requests by default - explicit auth in `connect`.

### Strong Params and Mass Assignment

- `params.require(:user).permit(:name, :email)` is the standard contract.
- `permit!` allows everything - dangerous; flag if seen.
- Nested attributes: `permit(profile_attributes: [:bio, :avatar])` for `accepts_nested_attributes_for`.

### Devise / Warden Auth (when present)

- `authenticate_user!` is a `before_action` that redirects to login if not authenticated.
- `current_user` lazily evaluates the session; calling it inside views or models triggers session lookup.
- Warden lives in middleware; bypass via `:skip_authentication` is common in API-only controllers.

### Active Storage

- `has_one_attached :avatar` / `has_many_attached :images` adds polymorphic associations.
- Variants generated lazily on first access; first request after upload may be slow.
- Direct upload bypasses the Rails server (signed URL); inline upload goes through it.

### Sidekiq + Connection Pools

- Sidekiq concurrency (`config/sidekiq.yml`) determines worker thread count per process.
- Database connection pool (`config/database.yml`) must be >= Sidekiq concurrency, or workers wait for connections.
- Long-running queries in jobs starve the pool for other workers.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Layer (controller / model / job / channel / concern)
- For controllers: filter chain in execution order, including filters from concerns and ApplicationController
- For models: all callbacks and validations that fire
- For jobs: enqueue point, backend (Sidekiq/Solid Queue/etc.), retry policy

**Into "Non-Obvious Behavior":**

- `update_columns`/`update_all` bypassing validations and callbacks
- `dependent: :delete_all` skipping callbacks
- `after_commit` vs `after_save` rollback semantics
- Zeitwerk filename/constant mismatches
- N+1 patterns in serializers or views
- `permit!` on params
- ActionCable not sharing session by default
- Devise filters inherited from ApplicationController

**Into "Key Invariants":**

- Filenames must match class names for Zeitwerk
- Job arguments must be GlobalID-serializable (no raw objects)
- Strong params required for mass assignment
- DB connection pool must be >= Sidekiq concurrency

**Into "Change Impact Preview":**

- Adding a callback to a model: fires on every save anywhere in the codebase, including from rake tasks, console, jobs
- Renaming a class: must rename the file (Zeitwerk) and any explicit references
- Adding a `before_action`: applies to every action unless filtered with `only:`/`except:`
- Changing AR association `dependent:`: switches callback firing behavior on cascade
- Modifying a concern: every including class is affected

## Avoid

- Describing controller actions without listing the active filters
- Treating `update_columns` and `update` as equivalent
- Glossing over `after_commit` vs `after_save` - they have different rollback semantics
- Listing callbacks without naming when they fire (validation, save, create, commit)
- Recommending `bullet` without checking if it is in the Gemfile
- Confusing Devise `authenticate_user!` (raises/redirects) with `user_signed_in?` (boolean)
