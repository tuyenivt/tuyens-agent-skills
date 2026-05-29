---
name: task-rails-implement
description: Implement a Rails feature end-to-end - migration, model, service, controller, serializer/views, Sidekiq, Pundit, RSpec.
agent: rails-architect
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

### Step 3 - Spec-Aware Mode

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists: use skill `spec-aware-preamble`. Follow its mode contract; skip Step 4 (and Step 5 when `plan.md` exists). Never edit spec artifacts; surface conflicts as proposed amendments.

### Step 4 - Gather Requirements

Ask:
1. Feature description and primary use case
2. Main models (fields, types, relationships, constraints)
3. External integrations (payments, email, third parties)
4. Background jobs needed?
5. Authorization rules (admin / owner / public)
6. Status transitions

If user gives a brief description, infer defaults and confirm. Edge cases:
- Referenced model doesn't exist - ask whether to generate or assume
- Partial input - ask for entity fields, relationships, operations before design

### Step 5 - Design (Approval Gate)

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
spec/{models,services,policies,requests,jobs,components}/...
db/migrate/<ts>_create_orders.rb
```

**Generate code only after user approves.**

### Step 6 - Migrations

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG).

- Indexes on FK and frequently-filtered columns; partial indexes for non-terminal status
- `null: false` + defaults where appropriate; decimal precision/scale on monetary fields
- One structural concern per migration

### Step 7 - Models

- Associations with explicit `dependent:` on `has_many`/`has_one`
- Validations (presence, numericality, inclusion); avoid `default_scope`
- `enum` with explicit integer mapping (`pending: 0, active: 1`)
- Chainable scopes; `counter_cache` where count queries appear

### Step 8 - Services

Use skill: `rails-service-objects`.

- `.call` returning `Result`; input validated in `initialize`
- Multi-model mutations in `ActiveRecord::Base.transaction`
- External API calls **outside** the transaction
- Sidekiq dispatch **after** commit

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

If Sidekiq needed: use skill `rails-sidekiq-patterns`. If a rake/backfill task is needed: use skill `rails-rake-task-patterns`.

### Step 9 - External HTTP Clients

Skip if no external APIs. Otherwise: use skill `rails-http-client-patterns`. Generate a dedicated `app/clients/<name>_client.rb` with explicit timeouts, JSON middleware + `:raise_error`, idempotency-aware retries (cap 2-3; Sidekiq handles longer waits), a domain error taxonomy translated from Faraday/HTTP errors. Services rescue **domain** errors only; tests stub at the boundary (WebMock unit / VCR integration).

### Step 10 - Controllers

Strong params; pagination on list endpoints; delegate business logic to services. Domain error -> HTTP:

| Domain Error         | HTTP |
| -------------------- | ---- |
| Validation failure   | 422  |
| RecordNotFound       | 404  |
| Conflict (duplicate) | 409  |
| Unauthenticated      | 401  |
| Forbidden            | 403  |

**API versioning:** new APIs under `/api/v1/...`; for existing apps, match the convention.

**Idempotency keys** for non-GET write endpoints whose effect must not duplicate on retry (payments, orders, refunds). Controller forwards `Idempotency-Key` header; service short-circuits on replay (see `rails-service-objects`).

### Step 11 - Serializers (API only)

Skip for server-rendered. Otherwise: one serializer per resource; never `render json: @model`. Library: match the project convention (`alba`, `jsonapi-serializer`, `active_model_serializers`, `blueprinter`). New Rails 7.2+ default: `alba`.

### Step 12 - Views (server-rendered only)

Skip for API-only. Use skill `rails-view-templates`. **Match the existing engine** (ERB/HAML/Slim) - never introduce a new one.

Generate only what the feature needs: `index`/`show`/`new`/`edit`, `_form` partial, `_<resource>` collection partial, ViewComponents for reusable UI, Turbo Frames keyed by `dom_id(record)`, Stimulus controllers (no inline `<script>`), fragment caching for collections (>~20 items) with `belongs_to :parent, touch: true`.

Escape every user-controlled value; no `.html_safe` on user input. Intentional HTML (markdown bodies, rich text): `sanitize` with explicit tag/attribute allowlist - the allowlist is the trust boundary even after `Commonmarker`/`Redcarpet`/`Kramdown`.

### Step 13 - Security

Use skill: `rails-security-patterns`.

- Pundit policies per resource with role-based access
- `after_action :verify_authorized` (+ `verify_policy_scoped` on index)
- `rescue_from Pundit::NotAuthorizedError` in `ApplicationController`

### Step 14 - Tests

Use skill: `rails-testing-patterns`.

- Model: associations, validations, scopes, enums (shoulda-matchers)
- Service: one example per `Result` outcome; side effects asserted
- Policy: per `(role, action)` with `permit_action`
- Request: happy + unauthorized + validation-error per action
- Job: idempotency + bounded retry (if applicable)
- ViewComponent (server-rendered): `render_inline` per state; user strings escaped
- Factories: traits per status/state

### Step 15 - Validate

Run `bundle exec rspec` and `bundle exec rubocop`. Fix failures before presenting output.

## Output Format

```markdown
## Files Generated
[grouped by layer: migrations, models, services, controllers, serializers/views, policies, jobs, clients, tests]

## Endpoints
| Method | Path                       | Request      | Response                   | Status |
| ------ | -------------------------- | ------------ | -------------------------- | ------ |
| POST   | /api/v1/orders             | OrderParams  | OrderSerializer            | 201    |
| POST   | /api/v1/orders/:id/fulfill | -            | OrderSerializer            | 200    |

## Sidekiq Jobs (if any)
| Job                     | Queue   | Trigger               | Retry |
| ----------------------- | ------- | --------------------- | ----- |
| ShipmentNotificationJob | mailers | After order fulfilled | 5     |

## Tests
[N] specs passing - [spec files and example counts]

## Migrations
[file name; tables, indexes, constraints]
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed (API-only vs server-rendered, view engine, serializer lib)
- [ ] Step 3: spec-aware mode honored when applicable
- [ ] Step 4: requirements gathered
- [ ] Step 5: design approved before generating code
- [ ] Step 6: migrations include indexes on FKs and filtered columns; one concern per migration
- [ ] Step 7: enum with explicit integer mapping; `dependent:` set; no `default_scope`
- [ ] Step 8: services use Result; multi-model writes in transaction; Sidekiq + external calls outside/after
- [ ] Step 9: external APIs go through a dedicated client with timeouts, idempotency retries, domain taxonomy
- [ ] Step 10: strong params; list endpoints paginated; domain-to-HTTP mapping applied; idempotency keys for write endpoints
- [ ] Step 11: serializers used for every API response (or skipped for server-rendered)
- [ ] Step 12: views in existing engine; user input escaped; Turbo Frames use `dom_id`; intentional HTML via `sanitize` allowlist (or skipped for API)
- [ ] Step 13: Pundit policies; `verify_authorized` / `verify_policy_scoped`
- [ ] Step 14: model + service + policy + request + job + component specs; factories have traits
- [ ] Step 15: `rspec` and `rubocop` pass

## Avoid

- Generating code before design approval
- `.perform_async` or external API calls inside a DB transaction
- `render json: @model` without a serializer
- Business logic in controllers or model callbacks
- `params.permit!` / `to_unsafe_h`
- `default_scope`
- Enum without explicit integer mapping
- Skipping pagination on list endpoints
- Missing `dependent:` on `has_many`/`has_one`
- Introducing a new view engine when one already exists
- Missing Pundit policy specs
