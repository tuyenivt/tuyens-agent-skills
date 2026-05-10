---
name: rails-code-explain
description: Rails code explanation signals: request lifecycle, AR callbacks/transactions, ActiveJob, Zeitwerk autoloading, ActionCable, concerns.
metadata:
  category: backend
  tags: [explanation, code-understanding, rails, activerecord, ruby]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Ruby on Rails.

## When to Use

- A workflow needs Rails-specific signals: request lifecycle, controller filters, AR callbacks, transaction scope, autoload boundaries, ActionCable channels, ActiveJob workers.
- Target code is in a Rails app (`config/application.rb`, `Gemfile` with `rails`).

## Rules

- Identify the layer first: controller, model, mailer, job, channel, service object, concern, initializer.
- For controllers, list filters in execution order before describing the action - filters can short-circuit (`render`/`redirect_to`/`head`) and prevent the action from running.
- For models, identify all callbacks and `validates_*` declarations - they fire on every save.
- Surface AR transaction boundaries: which methods open transactions, which `after_commit` hooks fire only after commit.
- For concerns, identify the including class - concerns are mixins, not isolated modules.

## Patterns

### Request Lifecycle

```
Rack middleware -> Routes -> Controller#action -> View / JSON -> Response
```

Signals per layer:

- **Middleware** (`config/application.rb`, mounted Rack apps): order matters; `Rack::Attack`, request logging, Warden/Devise auth live here.
- **Routes**: `resources :foo` generates 7 RESTful routes; nested routes change parameter names; `constraints:` filter requests.
- **Filters**: `before_action :authenticate_user!` runs unless `only:`/`except:` excludes; `skip_before_action` removes inherited filters.
- **Action**: Strong params (`params.require(:x).permit(:y, :z)`) is the input contract.
- **View / JSON**: ERB, Jbuilder, or serializers (ActiveModel::Serializer, fast_jsonapi).

### ActiveRecord Callbacks

| Callback                          | When                                                       | Flag                                                    |
| --------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------- |
| `before_validation`               | Before validators                                           | Normalization (downcase, strip)                         |
| `before_save`                     | Before INSERT or UPDATE                                     | Runs on creates and updates                             |
| `before_create`                   | Before INSERT only                                          |                                                         |
| `after_save`                      | Inside transaction, before commit                          | Side effects roll back if outer transaction fails       |
| `after_commit`                    | After transaction commits                                   | Use for non-DB side effects (jobs, emails, APIs)        |
| `after_create_commit` / `after_update_commit` | Variant filtered by event                       |                                                         |
| `before_destroy`                  | Before DELETE                                              | `dependent: :destroy` cascades; `:delete_all` skips     |

**Callback abuse pattern:** business logic in `after_save` instead of service objects creates implicit invocation - changing a record anywhere triggers side effects. Surface as a gotcha.

### Transactions

- `ActiveRecord::Base.transaction { }` opens a transaction. Nested transactions use savepoints by default; `requires_new: true` to actually commit/rollback the inner separately.
- `save!` raises on failure inside a transaction; rescue **outside** the block.
- `update_columns(...)` and `update_all(...)` bypass validations and callbacks. Common gotcha when an "update" silently skips logic.
- `after_commit` hooks fire after the **outermost** transaction commits, not the inner.

### N+1 Queries

- `User.all.each { |u| u.posts }` issues one query per user. Fix with `User.includes(:posts)` (separate query) or `User.eager_load(:posts)` (single LEFT JOIN).
- `bullet` gem (when present) flags N+1 in development.
- `to_json` on a serializer that calls associations is a hidden N+1 source.

### Zeitwerk Autoloading (Rails 6+)

- Filenames must match class/module names: `app/services/order_processor.rb` -> `OrderProcessor`.
- Namespaced: `app/services/orders/processor.rb` -> `Orders::Processor`.
- Autoload errors surface lazily in dev, eagerly at boot in production.

### Concerns

- `include MyConcern` is a Ruby mixin: methods become instance methods, `included { }` block runs at include time.
- `extend ActiveSupport::Concern` enables `class_methods do { }` and reliable `included` blocks.
- Concerns shared across many classes create implicit coupling.

### ActiveJob and Background Jobs

- `MyJob.perform_later(arg)` enqueues to the configured backend. `perform_now` runs synchronously.
- Job arguments must be serializable: AR records are GlobalID-serialized (re-fetched on perform); custom objects need explicit serialization.
- Default Sidekiq retry is 25 - can mask transient bugs. Cross-reference `rails-sidekiq-patterns`.

### ActionCable

- Channels in `app/channels/`; user identified via `connect` on `ApplicationCable::Connection`.
- `subscribed`/`unsubscribed` hooks; `stream_from "name"` subscribes to broadcast streams.
- `ActionCable.server.broadcast("name", data)` publishes from anywhere.
- Cable connections do not share session/cookie state with HTTP by default.

### Strong Params and Mass Assignment

- `params.require(:user).permit(:name, :email)` is the standard contract.
- `permit!` allows everything - dangerous; flag if seen.
- Nested attributes: `permit(profile_attributes: [:bio])` for `accepts_nested_attributes_for`.

### Devise / Warden (when present)

- `authenticate_user!` redirects to login if not authenticated.
- `current_user` lazily evaluates the session.
- Warden lives in middleware; bypass via `:skip_authentication` is common in API-only controllers.

### Active Storage

- `has_one_attached :avatar` adds polymorphic associations.
- Variants generated lazily on first access.
- Direct upload bypasses the Rails server (signed URL).

### Sidekiq, batches, and pools

When the explained code involves Sidekiq, long-running batches, or `load_async`, flag the cross-cuts and defer to specialists:

- Connection pool: each Sidekiq thread holds one DB connection; deployment-wide total must stay under `max_connections`. See `rails-connection-pool-sizing`.
- Memory across batches: Ruby GC + glibc malloc fragmentation cause RSS climb in long workers. See `rails-batch-processing-patterns`.
- Transaction shape: never wrap `find_each` in `Model.transaction`; chunk transactions instead. See `rails-batch-processing-patterns`.

## Output Format

Inject signals into `task-code-explain` sections:

**Flow Context:**
- Layer (controller / model / job / channel / concern)
- Controllers: filter chain in execution order, including filters from concerns and ApplicationController
- Models: all callbacks and validations that fire
- Jobs: enqueue point, backend, retry policy

**Non-Obvious Behavior:**
- `update_columns`/`update_all` bypassing validations and callbacks
- `dependent: :delete_all` skipping callbacks
- `after_commit` vs `after_save` rollback semantics
- Zeitwerk filename/constant mismatches
- N+1 in serializers or views
- `permit!` on params
- ActionCable not sharing session
- Inherited filters from ApplicationController

**Key Invariants:**
- Filenames must match class names for Zeitwerk
- Job arguments must be GlobalID-serializable
- Strong params required for mass assignment
- DB pool >= in-process thread count

**Change Impact:**
- Adding a callback: fires on every save anywhere
- Renaming a class: must rename the file
- Adding `before_action`: applies to every action unless filtered
- Changing `dependent:`: switches callback firing behavior
- Modifying a concern: every including class is affected

## Avoid

- Describing controller actions without listing the active filters
- Treating `update_columns` and `update` as equivalent
- Glossing over `after_commit` vs `after_save` rollback semantics
- Listing callbacks without naming when they fire
- Recommending `bullet` without checking the Gemfile
- Confusing Devise `authenticate_user!` (raises/redirects) with `user_signed_in?` (boolean)
