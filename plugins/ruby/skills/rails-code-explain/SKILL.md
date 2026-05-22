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

- A workflow needs Rails-specific signals: request lifecycle, controller filters, AR callbacks, transaction scope, autoload boundaries, ActionCable, ActiveJob
- Target code is in a Rails app

## Rules

- Identify the layer first: controller, model, mailer, job, channel, service, concern, initializer
- Controllers: list filters in execution order - they can short-circuit (`render`/`redirect_to`/`head`)
- Models: surface callbacks, `validates_*`, transaction boundaries; identify `after_commit` vs `after_save` rollback semantics
- Concerns: identify the including class - they are mixins, not isolated modules

## Patterns

### Request Lifecycle

```
Rack middleware -> Routes -> Controller#action -> View / JSON -> Response
```

- **Middleware** (`config/application.rb`): order matters; `Rack::Attack`, request logging, Warden/Devise live here
- **Routes**: `resources :foo` -> 7 RESTful routes; nested routes change parameter names; `constraints:` filter requests
- **Filters**: `before_action :authenticate_user!` runs unless `only:`/`except:`; `skip_before_action` removes inherited filters
- **Action**: Strong params is the input contract
- **View / JSON**: ERB, Jbuilder, serializers (`alba`, `jsonapi-serializer`, `active_model_serializers`)

### ActiveRecord Callbacks

| Callback                                     | When                                | Note                                              |
| -------------------------------------------- | ----------------------------------- | ------------------------------------------------- |
| `before_validation`                          | Before validators                   | Normalization                                     |
| `before_save` / `before_create`              | Before INSERT / UPDATE              |                                                   |
| `after_save`                                 | Inside transaction, before commit   | Rolls back atomically with parent                 |
| `after_commit`                               | After outermost transaction commits | Use for non-DB side effects (jobs, emails, APIs)  |
| `after_create_commit` / `after_update_commit`| Variants filtered by event          |                                                   |
| `before_destroy`                             | Before DELETE                       | `dependent: :destroy` cascades; `:delete_all` skips|

**Callback abuse:** business logic in `after_save` creates implicit invocation - changing a record anywhere triggers side effects. Surface as a gotcha.

### Transactions

- `ActiveRecord::Base.transaction { }` opens a transaction; nested use savepoints; `requires_new: true` commits/rolls back inner independently
- `save!` raises on failure; rescue **outside** the block
- `update_columns` / `update_all` bypass validations and callbacks - common gotcha when an "update" silently skips logic
- `after_commit` fires after the **outermost** transaction, not the inner

### N+1

- `User.all.each { |u| u.posts }` -> one query per user. Fix with `User.includes(:posts)` (separate query) or `User.eager_load(:posts)` (single LEFT JOIN)
- `bullet` flags N+1 in development
- `to_json` on a serializer calling associations is a hidden N+1 source

### Zeitwerk (Rails 6+)

- Filenames match class/module names: `app/services/order_processor.rb` -> `OrderProcessor`
- Namespaced: `app/services/orders/processor.rb` -> `Orders::Processor`
- Autoload errors surface lazily in dev, eagerly at boot in production

### Concerns

- `include MyConcern` is a Ruby mixin: methods become instance methods, `included { }` runs at include time
- `extend ActiveSupport::Concern` enables `class_methods do { }` and reliable `included` blocks
- Concerns shared across many classes create implicit coupling

### ActiveJob

- `MyJob.perform_later(arg)` enqueues; `perform_now` runs synchronously
- Arguments must be serializable; AR records are GlobalID-serialized (re-fetched on perform); custom objects need explicit serialization
- Default Sidekiq retry is 25 - can mask transient bugs. See `rails-sidekiq-patterns`

### ActionCable

- Channels in `app/channels/`; user identified via `connect` on `ApplicationCable::Connection`
- `subscribed`/`unsubscribed` hooks; `stream_from "name"` subscribes
- `ActionCable.server.broadcast("name", data)` publishes
- Cable connections do not share session/cookie state with HTTP by default

### Strong Params

- `params.require(:user).permit(:name, :email)`
- `permit!` allows everything - dangerous
- Nested: `permit(profile_attributes: [:bio])` with `accepts_nested_attributes_for`

### Devise / Warden (when present)

- `authenticate_user!` redirects/raises if not authenticated
- `current_user` lazily evaluates the session
- Warden lives in middleware

### Active Storage

- `has_one_attached :avatar` adds polymorphic associations
- Variants generated lazily
- Direct upload bypasses the Rails server (signed URL)

### Sidekiq, Batches, Pools

When explained code involves Sidekiq, long batches, or `load_async`:
- Each Sidekiq thread holds one DB connection. See `rails-connection-pool-sizing`
- Ruby GC + glibc malloc cause RSS climb. See `rails-batch-processing-patterns`
- Never wrap `find_each` in `Model.transaction`; chunk transactions. See `rails-batch-processing-patterns`

## Output Format

Inject signals into `task-code-explain` sections:

**Flow Context:**
- Layer (controller / model / job / channel / concern)
- Controllers: filter chain in execution order, including filters from concerns and ApplicationController
- Models: callbacks and validations that fire
- Jobs: enqueue point, backend, retry policy

**Non-Obvious Behavior:**
- `update_columns` / `update_all` bypassing validations and callbacks
- `dependent: :delete_all` skipping callbacks
- `after_commit` vs `after_save` rollback semantics
- Zeitwerk filename/constant mismatches
- N+1 in serializers or views
- `permit!` on params
- ActionCable not sharing session
- Inherited filters from ApplicationController

**Key Invariants:**
- Filenames match class names for Zeitwerk
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
- Confusing Devise `authenticate_user!` (raises/redirects) with `user_signed_in?` (boolean)
