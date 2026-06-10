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

Target code is in a Rails 7.2+ app and the host workflow needs Rails-specific lifecycle, callback, transaction, autoload, or job signals.

## Rules

- Name the layer first: controller, model, mailer, job, channel, service, concern, initializer.
- Controllers: list `before_action`/`around_action` chain in execution order - registration order: superclass filters first (including those added by concern `included` blocks), then subclass, minus `skip_before_action` removals; an `around_action` wraps every later filter plus the action. Note short-circuits (`render`/`redirect_to`/`head`).
- When run standalone (no host workflow), emit the four Output Format sections as headings.
- Models: surface callbacks, validations, transaction scope. Always distinguish `after_save` (rolls back with parent) from `after_commit` (fires after outermost commit).
- Concerns are mixins, not isolated modules - name the including class.

## Patterns

### Request lifecycle

`Rack middleware -> Routes -> Controller#action -> View / JSON -> Response`

- Middleware order from `config/application.rb` and `config/environments/*.rb`; `Rack::Attack`, logging, Warden live here.
- `resources :foo` -> 7 RESTful routes; nesting changes param names; `constraints:` filters requests.
- Strong params (`params.require(:x).permit(...)`) is the input contract. `permit!` bypasses it.

### ActiveRecord callbacks

| Callback                          | Fires                              | Note                                       |
| --------------------------------- | ---------------------------------- | ------------------------------------------ |
| `before_validation`               | Before validators                  | Normalization                              |
| `before_save` / `before_create`   | Before INSERT/UPDATE               |                                            |
| `after_save`                      | Inside txn, pre-commit             | Rolls back atomically with parent          |
| `after_commit`                    | After outermost txn commits        | Use for non-DB side effects (jobs, APIs)   |
| `after_{create,update}_commit`    | Event-filtered `after_commit`      |                                            |
| `before_destroy`                  | Before DELETE                      | `dependent: :delete_all` skips callbacks   |

Business logic in `after_save` is implicit invocation - any save anywhere triggers it (including no-op re-saves; `saved_change_to_x?` guards prevent that, and dirty state resets before `after_commit` runs in some paths). Flag as a gotcha. A raise inside a pre-commit callback aborts the save and rolls back, surfacing from `save!`; a raise in `after_commit` propagates but the data is already committed. Pre-7.1, multiple `after_commit` on one model fire in *reverse* declaration order. A job enqueued from a pre-commit callback **outlives a rollback** - the Redis push isn't transactional, so rolled-back rows still produce jobs (ghost emails / `RecordNotFound` retries).

### Transactions

- `ActiveRecord::Base.transaction { }`; nesting -> savepoints; `requires_new: true` for independent inner commit/rollback.
- `save!` raises - rescue **outside** the block. `RecordInvalid` fails *before* any SQL (rescuable mid-transaction); `RecordNotUnique` / `Deadlocked` fail at the DB and may poison the open transaction.
- `update_columns` / `update_all` bypass validations and callbacks.

### N+1

`User.all.each { |u| u.posts }` -> one query per user. Fix with `includes(:posts)` (preload) or `eager_load(:posts)` (LEFT JOIN). Serializers calling associations hide N+1; `bullet` flags in dev.

### Zeitwerk

Filename matches constant: `app/services/orders/processor.rb` -> `Orders::Processor`. Errors surface lazily in dev, eagerly at boot in production.

### Concerns

`include Mod` adds instance methods; `included { }` runs at include time; `extend ActiveSupport::Concern` enables `class_methods do`. Concerns shared across many classes create implicit coupling - surface the including class.

### ActiveJob / Sidekiq

Two enqueue APIs with different arg semantics: `perform_later` (ActiveJob) serializes AR records via GlobalID and re-fetches on perform; `perform_async` (raw Sidekiq) takes only JSON-primitive args - pass IDs, the job re-fetches explicitly. Sidekiq's default 25 retries can mask transient bugs - see `rails-sidekiq-patterns`. Each Sidekiq thread holds one DB connection; never wrap `find_each` in `Model.transaction` - see `rails-connection-pool-sizing`, `rails-batch-processing-patterns`.

### ActionCable / Active Storage / Devise / Pundit

- ActionCable: channels in `app/channels/`; identify in `ApplicationCable::Connection#connect`; `subscribed` should authorize and `reject`; no HTTP session sharing by default.
- Active Storage: `has_one_attached :x` adds polymorphic associations; variants are lazy; direct upload bypasses the Rails server.
- Devise: `authenticate_user!` raises/redirects; `current_user` is session-backed; Warden lives in middleware.
- Pundit: `authorize record` resolves `<Record>Policy#<action>?` and raises `NotAuthorizedError` (403 path) - distinct from a scoped find (`current_user.orders.find`) raising `RecordNotFound` (404 path). Both gates often coexist in one action; name which fires first.

## Output Format

Inject into `task-code-explain` sections. The field lists below are menus of signals, not mandatory fields - include what the target code exhibits, omit the rest:

**Flow Context:** layer; controller filter chain in execution order (incl. inherited + concerns); model callbacks/validations that fire; job enqueue point, backend, retry policy.

**Non-Obvious Behavior:** `update_columns`/`update_all` bypassing callbacks; `dependent: :delete_all` skipping callbacks; `after_commit` vs `after_save` rollback semantics; Zeitwerk filename/constant mismatches; N+1 in serializers/views; `permit!`; ActionCable not sharing session; inherited filters.

**Key Invariants:** Zeitwerk filename = constant; job args GlobalID-serializable; strong params required for mass assignment; DB pool >= in-process thread count.

**Change Impact:** new callback -> fires on every save; rename class -> rename file; new `before_action` -> applies to every action unless filtered; `dependent:` change -> changes callback firing; modify concern -> every including class affected.

## Avoid

- Describing a controller action without listing active filters.
- Treating `update_columns` and `update` as equivalent.
- Listing callbacks without naming when they fire or their rollback semantics.
- Confusing `authenticate_user!` (raises/redirects) with `user_signed_in?` (boolean).
