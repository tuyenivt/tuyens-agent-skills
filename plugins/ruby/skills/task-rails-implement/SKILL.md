---
name: task-rails-implement
description: Implement a Rails feature end-to-end: migrations, models, services, controllers, serializers, Sidekiq jobs, RSpec tests.
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. Follow its mode contract; skip GATHER (and DESIGN when `plan.md` exists). Never edit spec artifacts; surface conflicts as proposed amendments.

## When to Use

- Implementing a new Rails feature end-to-end (migration -> model -> service -> controller -> tests)
- Scaffolding a CRUD or domain-specific resource with production-ready patterns
- Adding a new aggregate with REST API, persistence, authorization, and tests

Not for: single-file bug fixes (`task-rails-debug`), view-only changes (edit + consult `rails-view-templates`), DB-only migrations.

## Edge Cases

- **Partial input** -> ask for entity fields, relationships, operations before design
- **No background jobs** -> skip Sidekiq generation
- **Existing models** -> read and extend; skip migration if no schema change
- **Referenced model doesn't exist** -> ask whether to generate it or assume it exists
- **API-only app** (`ActionController::API`) -> skip CSRF, sessions, views
- **Server-rendered app** (views beyond mailers + `ActionController::Base`) -> generate views in the existing engine (ERB/HAML/Slim from Gemfile + existing files). Use `rails-view-templates`. Never introduce a new engine
- **State transitions** -> service-layer transition validation + enum with explicit integer mapping
- **Counter / inventory operations** -> transaction with status change; dispatch jobs after commit
- **Backfill / maintenance task** -> use `rails-rake-task-patterns` for a thin rake task delegating to a service

## Rules

- Business logic in service objects, not controllers or models
- Strong params in every controller; never `params.permit!` or `to_unsafe_h`
- Serializers for all API responses; never raw AR objects
- Enum fields with explicit integer mapping (`pending: 0, active: 1`)
- Multi-model mutations in `ActiveRecord::Base.transaction`
- Sidekiq `.perform_async` **after** transaction commits, never inside
- Present design for approval before generating code

## Workflow

### Step 1 - Detect Stack, Gather Requirements

Use skill: `stack-detect`. Ask:

1. Feature description and primary use case
2. Main models (fields, relationships, constraints)
3. External integrations (payments, email, third parties)
4. Background jobs needed?
5. Authorization rules (admin / owner / public)
6. Status transitions

If user gives a brief description, infer defaults and confirm. If they reference a ticket or spec, extract answers from it.

### Step 2 - Design (Approval Gate)

Use skill: `rails-activerecord-patterns` for associations/scopes. Use skill: `rails-service-objects` for service layer.

Present:
- Entity model: fields, types, constraints, enum mapping
- Associations + `dependent:` options
- Service methods, transaction boundaries, Sidekiq dispatch points
- Endpoints (method, URI, status codes, request/response shapes)
- Authorization rules

File tree:

```
app/
  models/order.rb
  services/fulfill_order.rb
  controllers/api/v1/orders_controller.rb      # API
  serializers/order_serializer.rb              # API
  views/orders/index.html.{slim,haml,erb}      # server-rendered
  components/order_card_component.rb           # server-rendered, when reused
  policies/order_policy.rb
  jobs/shipment_notification_job.rb            # if needed
spec/
  models/order_spec.rb
  services/fulfill_order_spec.rb
  policies/order_policy_spec.rb
  requests/api/v1/orders_spec.rb
  components/order_card_component_spec.rb      # server-rendered
  jobs/shipment_notification_job_spec.rb
  factories/orders.rb
db/migrate/xxx_create_orders.rb
```

Only generate code after user approves.

### Step 3 - Database

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG). Generate migrations with:
- Indexes on FK and frequently-filtered columns
- Partial indexes on status columns for non-terminal states
- Proper decimal precision/scale for monetary fields
- `null: false` + defaults where appropriate
- One structural concern per migration

### Step 4 - Models

- Associations with explicit `dependent:` on `has_many` / `has_one`
- Validations (presence, numericality, inclusion)
- `enum` with explicit integer mapping
- Chainable scopes for common queries
- `counter_cache` where count queries are expected
- `belongs_to` with `counter_cache: true` on the child

### Step 5 - Services

Use skill: `rails-service-objects`.

- `.call` returning `Result`
- Input validation in `initialize`
- `ActiveRecord::Base.transaction` for multi-model mutations
- External API calls **outside** the transaction
- Sidekiq dispatch **after** the transaction

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

If Sidekiq needed: use skill `rails-sidekiq-patterns`. If a rake task is needed: use skill `rails-rake-task-patterns`.

### Step 5.5 - External HTTP Clients

Skip if no external APIs. Otherwise: use skill `rails-http-client-patterns`. Generate a dedicated client class under `app/clients/` with:

- Faraday connection: explicit `open_timeout` / `timeout`, JSON middleware, `:raise_error`, redacted logger
- Idempotency-aware retries on idempotent verbs (or POST with `Idempotency-Key`); cap at 2-3, let Sidekiq handle longer waits
- Domain error taxonomy translated from Faraday exceptions and statuses
- Services rescue **domain** errors (never `Faraday::Error`); transient propagate to Sidekiq, permanent become `Result.failure`
- Tests stub at the boundary (WebMock unit / VCR integration)

### Step 6 - Controllers

Strong params; pagination on list endpoints; delegate business logic to services. Domain error -> HTTP:

| Domain Error         | HTTP |
| -------------------- | ---- |
| Validation failure   | 422  |
| RecordNotFound       | 404  |
| Conflict (duplicate) | 409  |
| Unauthorized         | 401  |
| Forbidden            | 403  |

**API versioning.** New API endpoints under a versioned namespace (`/api/v1/...` or via `Accept` header). For existing apps, follow the established convention. First API endpoint: default to URL-based versioning - most discoverable.

**Idempotency keys for write endpoints.** For non-GET endpoints whose effect must not duplicate on retry (payments, orders, refunds, "create" actions), accept `Idempotency-Key` header. The controller forwards it; the service short-circuits on replay (see `rails-service-objects`):

```ruby
def create
  result = ChargeCustomer.new(
    order: order,
    idempotency_key: request.headers["Idempotency-Key"]
  ).call
end
```

### Step 7 - Serializers (API)

Skip if no JSON endpoints. Otherwise: separate serializer per resource; never `render json: @model`.

Library detection:
1. Existing project convention (`alba`, `jsonapi-serializer`, `active_model_serializers`, `blueprinter`) - match it
2. No existing serializer: default to `alba` for new Rails 7.2+ projects (fast, JSON:API-optional, actively maintained)

### Step 7.5 - Views (server-rendered)

Skip for API-only. Otherwise: use skill `rails-view-templates`. Detect engine from Gemfile + existing `.slim`/`.haml`/`.erb` files. **Match the existing engine.**

Generate:
- `index`, `show`, `new`, `edit` in the detected engine (skip what the feature doesn't need)
- `_form.html.<ext>` partial shared by `new`/`edit`
- `_<resource>.html.<ext>` collection-item partial when index renders a list
- ViewComponents in `app/components/` for reusable UI (status badges, action menus); prefer over a helper for any logic touching 3+ attributes
- Turbo Frame wrapping with `dom_id(record)` for per-row updates
- Stimulus controllers for client-side interactivity (no inline `<script>`)
- Fragment caching with Russian-doll keys (`cache record do ... end`) for collections >~20 items; pair with `belongs_to :parent, touch: true`
- Layout slots via `content_for :slot do ... end` and `= yield :slot`

Escaping checklist:
- Default escaped output for every user-controlled value
- No `.html_safe` on user input - use `sanitize` with explicit allowlist
- Slim: no `==` on user data; quote string-literal attribute values

**Intentional HTML rendering** (markdown bodies, rich-text comments) - the field *is* HTML and must render as markup:

```slim
.comment-body
  = sanitize comment.body, tags: %w[p br strong em a ul ol li blockquote code], attributes: %w[href]
```

For markdown pipelines (`Commonmarker`, `Redcarpet`, `Kramdown`), always pass rendered HTML through `sanitize` even if the renderer claims safe-mode. The allowlist is the trust boundary.

### Step 8 - Security

Use skill: `rails-security-patterns`.

- Pundit policies per resource with role-based access
- `after_action :verify_authorized` in controllers
- `policy_scope` for index actions
- `rescue_from Pundit::NotAuthorizedError` in `ApplicationController`

### Step 9 - Tests

Use skill: `rails-testing-patterns`.

- Model specs (associations, validations, scopes, enums with shoulda-matchers)
- Service specs (`Result` success/failure, side effects)
- Policy specs (role-based per action with `permit_action`)
- Request specs (happy + error paths + authorization)
- ViewComponent specs (server-rendered) - `render_inline` per state; assert user strings are escaped
- Factory traits per status/state
- Sidekiq specs with idempotency assertions (if applicable)

### Step 10 - Validate

Run `bundle exec rspec` and `bundle exec rubocop`. Fix failures before presenting output.

## Output Format

```markdown
## Files Generated

[grouped by layer: models, services, controllers, serializers, policies, jobs, tests, migrations]

## Endpoints

| Method | Path                       | Request      | Response                   | Status |
| ------ | -------------------------- | ------------ | -------------------------- | ------ |
| POST   | /api/v1/orders             | OrderParams  | OrderSerializer            | 201    |
| GET    | /api/v1/orders             | query params | Paginated[OrderSerializer] | 200    |
| GET    | /api/v1/orders/:id         | -            | OrderSerializer            | 200    |
| POST   | /api/v1/orders/:id/fulfill | -            | OrderSerializer            | 200    |

## Sidekiq Jobs (if any)

| Job                     | Queue   | Trigger               | Retry |
| ----------------------- | ------- | --------------------- | ----- |
| ShipmentNotificationJob | mailers | After order fulfilled | 5     |

## Tests

[X] specs passing - [list spec files and count per file]

## Migrations

[migration file name and what it creates: tables, indexes, constraints]
```

## Self-Check

- [ ] Requirements gathered, design approved before code
- [ ] All layers generated: migration, model, service, controller, serializer (API) or views (server-rendered), Pundit policy, tests
- [ ] Server-rendered: views in existing engine (never converted); user interpolation escaped; no `.html_safe` on user input; Turbo Frame ids use `dom_id`; intentional-HTML via `sanitize` with allowlist; ViewComponent specs per state
- [ ] Strong params; business logic in services; serializers for all API responses
- [ ] Enum with explicit integer mapping; `dependent:` set
- [ ] Sidekiq dispatched after DB commit
- [ ] External APIs through a dedicated client class with timeouts, idempotency-aware retries, domain taxonomy, boundary-stubbed tests
- [ ] Pundit policies; `verify_authorized` / `verify_policy_scoped`
- [ ] RSpec covers model, service, policy, request, job; factories have state traits
- [ ] `bundle exec rspec` and `bundle exec rubocop` pass
- [ ] Migration: indexes on FKs and filtered columns; list endpoints paginated
- [ ] Output template filled

## Avoid

- Generating code before requirements + design approval
- `.perform_async` inside a DB transaction
- External API calls inside a DB transaction
- Rendering raw AR objects from endpoints
- Business logic in controllers or model callbacks
- `params.permit!` / `to_unsafe_h`
- `default_scope`
- Enum without explicit integer mapping
- Skipping pagination on list endpoints
- Missing Pundit policy specs
- Missing `dependent:` on `has_many`/`has_one`
