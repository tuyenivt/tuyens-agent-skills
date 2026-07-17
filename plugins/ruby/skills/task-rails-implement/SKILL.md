---
name: task-rails-implement
description: Implement a Rails feature end-to-end - migration, model, service, controller, serializer/views, Sidekiq, Pundit, RSpec.
agent: rails-engineer
metadata:
  category: backend
  tags: [ruby, rails, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## When to Use

- New Rails feature end-to-end (migration -> model -> service -> controller -> tests)
- New aggregate with REST API, persistence, authorization, tests
- Scaffolding a domain resource with production-ready patterns

Not for: single-file bug fixes (`task-rails-debug`), view-only edits (use `rails-view-templates`), migration-only changes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Identify Ruby/Rails version, DB (MySQL/PG), API-only vs server-rendered (presence of `views/` beyond mailers, `ActionController::Base` vs `API`), serializer library, view engine (ERB/HAML/Slim).

### Step 3 - Gather Requirements

Ask:
1. Feature description and primary use case
2. Main models (fields, types, relationships, constraints)
3. External integrations (payments, email, third parties)
4. Background jobs needed?
5. Authorization rules (admin / owner / public)
6. Status transitions

Ask-vs-infer threshold: brief-but-unambiguous requests get inferred defaults, confirmed at the design gate (one round trip). Ask first only when a missing decision changes the schema or endpoints (entity fields, relationships, who approves what). Edge cases:
- Referenced model doesn't exist - ask whether to generate or assume
- Partial input - ask for entity fields, relationships, operations before design

### Step 4 - Design (Approval Gate)

Use skill: `rails-activerecord-patterns` (associations, scopes, enums). Use skill: `rails-service-objects` (interface, transactions, Result).

Present:
- Entity model: fields, types, constraints, enum integer mapping
- Associations + `dependent:` options
- Service methods, transaction boundaries, Sidekiq dispatch points
- Endpoints (method, URI, status, request/response shapes)
- Authorization rules per action
- File tree (only files this feature touches)

Example tree:

```
app/
  models/order.rb
  services/fulfill_order.rb
  controllers/api/v1/orders_controller.rb   # API
  serializers/order_serializer.rb           # API
  views/orders/{index,show,_form}.html.<ext> # server-rendered
  components/order_card_component.rb        # server-rendered, reusable UI
  policies/order_policy.rb
  jobs/shipment_notification_job.rb         # if needed
  clients/shipment_api_client.rb            # if external API
config/routes.rb                            # routes diff
spec/{models,services,policies,requests,jobs,components}/...
db/migrate/<ts>_create_orders.rb
```

**Generate code only after user approves.**

### Step 5 - Migrations

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG). One structural concern per migration. Indexes on FKs and frequently-filtered columns; partial indexes for non-terminal status; `null: false` + defaults where appropriate. Monetary values: integer cents columns (`amount_cents`) by default; `decimal` precision/scale only when matching an existing project convention.

### Step 6 - Models

Use skill: `rails-activerecord-patterns`. Apply its rules: explicit `dependent:` on `has_many`/`has_one`, `enum` with integer mapping, chainable scopes, `counter_cache` where count queries appear, no `default_scope`.

File uploads: use skill `rails-active-storage-patterns` *here* (attachment declarations, validations, direct-upload decision) - it also shapes the migration (Step 5) and form (Step 11); don't defer it to Step 12.

### Step 7 - Services

Use skill: `rails-service-objects`. Use skill: `rails-transaction-patterns` for boundary discipline (`after_commit` dispatch, nested transactions). If Sidekiq needed: use skill `rails-sidekiq-patterns`. If a rake/backfill task is needed: use skill `rails-rake-task-patterns`.

Canonical shape (no external calls in the flow):

```ruby
def call
  ActiveRecord::Base.transaction do
    @order.update!(status: :processing, fulfilled_at: Time.current)
    decrement_inventory
  end
  ShipmentNotificationJob.perform_async(@order.id)  # post-commit
  Result.success(@order.reload)
end
```

When externals enter the flow, `rails-service-objects`' ordering arbitrates: abort-critical calls (charge) go *before* the transaction with an idempotency key; deferrable/flaky systems move to a post-commit Sidekiq job whose own service applies the same call-before-txn rule internally.

Cross-row invariants (per-user caps, quotas): enforce in the service under a row lock, with a DB backstop where expressible - a model validation alone races.

Time-based behavior (expiry, retention windows): owned here too - a cron-invoked rake task (`rails-rake-task-patterns`) or scheduled job; name the trigger in the design.

### Step 8 - External HTTP Clients

Skip if no external APIs. Otherwise: use skill `rails-http-client-patterns`. Generate a dedicated `app/clients/<name>_client.rb` with explicit timeouts, JSON middleware + `:raise_error`, idempotency-aware retries (cap 2-3; Sidekiq handles longer waits), a domain error taxonomy translated from Faraday/HTTP errors. Services rescue **domain** errors only; tests stub at the boundary (WebMock unit / VCR integration).

If the feature fans out across two or more external services on the same request or job, use skill `rails-concurrency-patterns` to pick the primitive (`load_async`, `Concurrent::Promises`, `async` gem, or Sidekiq fan-out).

### Step 9 - Controllers

Strong params; pagination on list endpoints; delegate business logic to services. Domain error -> HTTP:

| Domain Error         | HTTP |
| -------------------- | ---- |
| Validation failure   | 422  |
| RecordNotFound       | 404  |
| Conflict (duplicate) | 409  |
| Unauthenticated      | 401  |
| Forbidden            | 403  |

**API versioning:** new APIs under `/api/v1/...`; for existing apps, match the convention.

**Idempotency keys** for non-GET write endpoints whose effect must not duplicate on retry (payments, orders, refunds). Two valid mechanisms: row-creating endpoints forward the `Idempotency-Key` header backed by a unique index; state transitions on existing rows are replay-safe via a status guard under row lock (no header needed - there's no row to key). See `rails-service-objects`.

### Step 10 - Serializers (API only)

Skip for server-rendered. One serializer per resource; never `render json: @model`. Library: match the project convention (`alba`, `jsonapi-serializer`, `active_model_serializers`, `blueprinter`). No existing convention (Rails ships none): use `alba`.

### Step 11 - Views (server-rendered only)

Skip for API-only. Use skill `rails-view-templates`. **Match the existing engine** (ERB/HAML/Slim) - never introduce a new one. Generate only the files this feature needs (`index`/`show`/`new`/`edit`, `_form`, collection partial, ViewComponents, Turbo Frames keyed by `dom_id(record)`, Stimulus controllers, fragment caching for hot collections). Live in-place updates (`turbo_stream_from` + broadcasts): use skill `rails-actioncable-patterns` *here* for scope and broadcast hooks - don't defer it to Step 12. Intentional HTML via `sanitize` allowlist; never `.html_safe` on user input.

### Step 12 - Security + Exception Strategy

Use skill: `rails-security-patterns` (Pundit policies per resource, `verify_authorized` / `verify_policy_scoped`, strong params). Use skill: `rails-exception-handling` for the `ApplicationController#rescue_from` ladder and domain error taxonomy.

Public/token endpoints (shared links): the token *is* the capability - generate with `has_secure_token` (unguessable), serve through a read-only serializer, and skip Pundit with an explicit `skip_after_action :verify_authorized` + stated rationale.

- File uploads: `rails-active-storage-patterns` was loaded at Step 6; apply its serving/security rules here
- For ActionCable channels (custom channels, connection auth): use skill `rails-actioncable-patterns`

### Step 13 - Tests

Use skill: `rails-testing-patterns`. Cover:
- Model: associations, validations, scopes, enums
- Service: one example per `Result` outcome; side effects asserted
- Policy: per `(role, action)`
- Request: happy + unauthorized + validation-error per action
- Job: idempotency + bounded retry (if applicable)
- ViewComponent (server-rendered): `render_inline` per state
- Factories: traits per status/state

### Step 14 - Validate

Run `bundle exec rspec` and `bundle exec rubocop`. Fix failures before presenting output. If the environment can't execute them, say so explicitly, list the commands for the user to run, and report spec counts as "written, not executed" - never claim passes.

## Output Format

```markdown
## Files Generated
[grouped by layer: migrations, models, services, controllers, serializers/views, policies, jobs, clients, tests]

## Endpoints
| Method | Path                       | Request      | Response                   | Status |
| ------ | -------------------------- | ------------ | -------------------------- | ------ |
| POST   | /api/v1/orders             | OrderParams  | OrderSerializer            | 201    |
| POST   | /api/v1/orders/:id/fulfill | -            | OrderSerializer            | 200    |

(Server-rendered: Response column holds the view rendered or redirect target; Status 302/422.)

## Sidekiq Jobs (if any)
| Job                     | Queue   | Trigger               | Retry |
| ----------------------- | ------- | --------------------- | ----- |
| ShipmentNotificationJob | mailers | After order fulfilled | 5     |

## Tests
[N] specs passing - [spec files and example counts]
(If not executable in this environment: "[N] specs written, not executed" per Step 14.)

## Migrations
[file name; tables, indexes, constraints]
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed (API-only vs server-rendered, view engine, serializer lib)
- [ ] Step 3: requirements gathered
- [ ] Step 4: design approved before generating code
- [ ] Step 5: migration-safety skill consulted; one concern per migration; indexes on FKs/filters
- [ ] Step 6: `rails-activerecord-patterns` applied to models
- [ ] Step 7: services return `Result`; transactions and post-commit dispatch via `rails-transaction-patterns`
- [ ] Step 8: external APIs go through a dedicated client with timeouts and domain taxonomy
- [ ] Step 9: strong params, pagination, domain-to-HTTP mapping, idempotency keys on writes
- [ ] Step 10: serializer per resource (or skipped for server-rendered)
- [ ] Step 11: views in existing engine via `rails-view-templates` (or skipped for API)
- [ ] Step 12: Pundit policies + `rescue_from` ladder; Active Storage / ActionCable patterns when applicable
- [ ] Step 13: model + service + policy + request + job + component specs; factory traits
- [ ] Step 14: `rspec` and `rubocop` pass (or reported "written, not executed" when the environment can't run them)

## Avoid

- Generating code before design approval
- `.perform_async` / external API calls / mailers inside a DB transaction (dispatch via `after_commit`)
- `render json: @model` without a serializer
- Business logic in controllers or model callbacks
- Introducing a new view engine when one already exists
