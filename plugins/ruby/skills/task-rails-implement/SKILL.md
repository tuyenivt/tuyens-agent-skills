---
name: task-rails-implement
description: Implement a multi-layer Rails feature end-to-end - migrations, models, services, controllers, serializers, Sidekiq jobs, and RSpec tests. Use for new features requiring coordinated layers; not for single-file fixes (use task-rails-debug).
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. The preamble decides between modes (`no-spec`, `spec-only`, `spec+plan`, `full-spec`); follow its contract - skip GATHER (and DESIGN, when `plan.md` is present) and treat the spec as the source of truth. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

## When to Use

- Implementing a new Rails feature end-to-end (migration -> model -> service -> controller -> tests)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate with REST API, persistence, authorization, and test coverage
- Any daily coding task that requires coordinated generation of multiple Rails layers

Not for:

- Single-file bug fixes or debugging (use `task-rails-debug`)
- Pure view-only changes with no model/controller/service work (edit views directly; consult `rails-view-templates` for engine-specific patterns)
- Database-only migrations without application code

## Edge Cases

- **Partial input**: If the user provides only a feature name without details, ask for entity fields, relationships, and operations before proceeding to design.
- **No background jobs**: If the feature does not require async processing, skip Sidekiq job generation. Do not generate empty job files.
- **Existing models**: If the user references a model that already exists, read the existing model and extend it rather than creating a new one. Skip migration if no schema change is needed.
- **Referenced model doesn't exist**: If the feature has a relationship to a model not yet in the codebase (e.g., `belongs_to :product`), ask the user whether to generate the referenced model or assume it already exists.
- **API-only app**: If the project inherits from `ActionController::API`, skip CSRF configuration, session-based auth patterns, and the views step.
- **Server-rendered app**: If the project has views beyond mailers (e.g., `app/views/<resources>/`) and inherits from `ActionController::Base`, generate views in the project's existing template engine (ERB / HAML / Slim - detect from Gemfile and existing `.slim`/`.haml`/`.erb` files). Use skill: `rails-view-templates` for engine-specific escaping, partials, fragment caching, and Turbo/Stimulus wiring. Match the existing engine - never introduce a new one as a side effect.
- **State machine transitions**: Feature has explicit status transitions (e.g., pending -> confirmed -> shipped). Generate transition validation in the service layer and enum with explicit integer mapping.
- **Inventory/counter operations**: Feature decrements or increments a counter on another model. Wrap in a transaction with the status change; dispatch jobs after commit.
- **Backfill or maintenance task**: Feature requires populating a new column on existing rows, or a recurring maintenance/report job. Use skill: `rails-rake-task-patterns` to generate a thin rake task that delegates to a service, with dry-run and production confirmation guards.

## Rules

- Business logic in service objects, not controllers or models - controllers only delegate and render
- Strong params in every controller - never `params.permit!` or `params.to_unsafe_h`
- Serializers for all API responses - never render raw ActiveRecord objects
- Enum fields use Rails enum with explicit integer mapping (`pending: 0, active: 1`)
- Transactions for multi-model mutations via `ActiveRecord::Base.transaction`
- Sidekiq dispatch timing: always call `.perform_async` AFTER the DB transaction commits, never inside it. If the job fires before commit, the worker may read stale data or a row that does not exist yet
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Workflow

### STEP 1 - DETECT STACK AND GATHER REQUIREMENTS (MANDATORY)

Use skill: `stack-detect` to confirm the project is Rails and identify framework versions, database, and project layout conventions.

Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main models? (fields, relationships, constraints)
3. Are there external integrations? (payment APIs, email, third-party services)
4. Are background jobs needed? (async processing, notifications, scheduled tasks)
5. Does the feature need authorization? (admin-only, owner-only, public)
6. Are there status transitions? (e.g., order: pending -> confirmed -> shipped -> delivered)

If the user provides only a brief description without answering all questions, infer reasonable defaults and present them for confirmation. If the user provides a ticket or spec, extract the answers from it.

### STEP 2 - DESIGN (MANDATORY APPROVAL GATE)

Use skill: `rails-activerecord-patterns` for association/scope design. Use skill: `rails-service-objects` for service layer design. Propose the implementation layers and present for user approval before generating code.

Design decisions to present:

- Entity model with fields, types, constraints, and enum definitions
- Associations and dependent options
- Service methods with transaction boundaries and Sidekiq dispatch points
- Endpoints (method, URI, status codes, request/response shapes)
- Authorization rules (who can do what)

Present a file tree showing what will be generated:

```
app/
  models/order.rb                          # ActiveRecord model
  services/fulfill_order.rb                # Service object
  controllers/api/v1/orders_controller.rb  # API controller (or controllers/orders_controller.rb for server-rendered)
  serializers/order_serializer.rb          # Response serializer (API only)
  views/orders/index.html.{slim,haml,erb}  # Server-rendered only - matches project engine
  views/orders/show.html.{slim,haml,erb}   #   "
  views/orders/_form.html.{slim,haml,erb}  #   "
  components/order_card_component.rb       # ViewComponent (server-rendered, when reused)
  policies/order_policy.rb                 # Pundit policy
  jobs/shipment_notification_job.rb        # Sidekiq job (if needed)
spec/
  models/order_spec.rb
  services/fulfill_order_spec.rb
  policies/order_policy_spec.rb
  requests/api/v1/orders_spec.rb
  components/order_card_component_spec.rb  # ViewComponent spec (server-rendered)
  jobs/shipment_notification_job_spec.rb
  factories/orders.rb
db/migrate/xxx_create_orders.rb
```

Only generate code after user approves design.

### STEP 3 - DATABASE

Use skill: `rails-migration-safety`. Generate migrations with:

- Indexes on foreign key columns and frequently-filtered columns
- Partial indexes on status columns for non-terminal states
- Proper decimal precision/scale for monetary fields
- `null: false` and defaults where appropriate
- Separate migration for each structural concern (create table, add index, add FK)

### STEP 4 - MODELS

Generate/update models with:

- Associations with explicit `dependent:` options on all `has_many`/`has_one`
- Validations (presence, numericality, inclusion)
- `enum` with explicit integer mapping (e.g., `enum :status, { pending: 0, confirmed: 1 }`)
- Chainable scopes for common queries
- `counter_cache` where count queries are expected
- `belongs_to` with `counter_cache: true` on the child side

### STEP 5 - SERVICES

Use skill: `rails-service-objects`. Generate service objects with:

- `.call` interface returning `Result` objects
- Input validation in `initialize` via `validate_inputs!`
- `ActiveRecord::Base.transaction` wrapping multi-model mutations
- Sidekiq dispatch AFTER the transaction block, never inside it

```ruby
# CORRECT: dispatch after commit
def call
  ActiveRecord::Base.transaction do
    @order.update!(status: :processing, fulfilled_at: Time.current)
    decrement_inventory
  end
  # After commit - worker will find the row
  ShipmentNotificationJob.perform_async(@order.id)
  Result.success(@order.reload)
end
```

If Sidekiq needed: Use skill: `rails-sidekiq-patterns`

If a rake task is needed for backfill, recurring maintenance, or ops-triggered work: Use skill: `rails-rake-task-patterns`. Generate the task as a thin shell that delegates to the service.

### STEP 5.5 - EXTERNAL HTTP CLIENTS

Skip this step if the feature does not call external APIs. Otherwise: Use skill: `rails-http-client-patterns`. For each external integration generate a dedicated client class under `app/clients/` with:

- Faraday connection with explicit `open_timeout` / `timeout`, JSON request/response middleware, `:raise_error`, redacted logger
- Retriable + idempotency-aware retry only on idempotent verbs (or `POST` with an `Idempotency-Key`); cap in-process retries at 2-3 and let Sidekiq handle longer waits
- Domain error taxonomy (`TransientError` / `PermanentError` / `RateLimitError` / `AuthError` / `NotFoundError` / `ValidationError`) translated from Faraday exceptions and HTTP statuses
- Services consume the client and rescue **domain** errors (never `Faraday::Error`); transient errors propagate so Sidekiq can retry, permanent errors become `Result.failure`
- Tests stub at the boundary - WebMock for client unit specs, VCR cassettes for service/request specs that exercise the full integration; VCR config filters tokens and idempotency keys

### STEP 6 - CONTROLLERS

Strong params, pagination on list endpoints, delegate all business logic to services. Map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 422         |
| RecordNotFound       | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| Forbidden            | 403         |

**API versioning.** New API endpoints go under a versioned namespace (`/api/v1/...` or via `Accept: application/vnd.app.v1+json` header). For an existing app, follow the project's established convention rather than introducing a new one. When the feature is the first API endpoint, default to URL-based versioning (`namespace :api do; namespace :v1 do; ...`) - it's the most discoverable and tooling-friendly choice.

**Idempotency keys for write endpoints.** For non-GET endpoints whose effect must not duplicate on client retry (payments, orders, refunds, "create" actions where the client retries on network blip), accept an `Idempotency-Key` header and short-circuit on replay. See `rails-service-objects` for the service-side pattern; the controller forwards the header:

```ruby
def create
  result = ChargeCustomer.new(
    order: order,
    idempotency_key: request.headers["Idempotency-Key"]
  ).call
  # ...
end
```

The header is required by Stripe-style integrations and is what makes "POST is not idempotent" survivable in practice.

### STEP 7 - SERIALIZERS (API endpoints)

Skip this step if the feature has no JSON endpoints. Otherwise: response shaping for all API responses. Separate serializers per resource. Never return raw ActiveRecord objects from endpoints.

Detect the project's serializer library before generating files. In order of preference for new Rails 7.2+ projects:

1. **Existing convention** - if the project already uses one (`alba`, `jsonapi-serializer`, `active_model_serializers`, `blueprinter`), match it.
2. **No existing serializer** - default to `alba` (fast, JSON:API-optional, actively maintained). Add `gem "alba"` and generate `app/serializers/<resource>_serializer.rb` extending `Alba::Resource`.

Never return `render json: @order` directly - always pipe through the chosen serializer so response shape is explicit and stable.

### STEP 7.5 - VIEWS (server-rendered features)

Skip this step if the feature is API-only (controllers inherit from `ActionController::API`, or no view files beyond mailers exist).

Use skill: `rails-view-templates`. Detect the project's template engine from the Gemfile (`slim-rails`, `haml-rails`, or none for ERB) and existing `app/views/**/*.{slim,haml,erb}` files. **Match the existing engine** - never convert engines as a side effect of feature work.

Generate:

- `index`, `show`, `new`, `edit` views in the detected engine (skip whichever the feature does not need)
- `_form.html.<ext>` shared form partial used by `new` and `edit`
- `_<resource>.html.<ext>` collection-item partial when index renders a list
- ViewComponents in `app/components/` for non-trivial reusable UI (status badges, action menus) - prefer ViewComponent over a helper for any logic touching three or more attributes
- Turbo Frame wrapping with `dom_id(record)` for any list-item view that should support per-row updates without full reload
- Stimulus controllers for any client-side interactivity (do not use inline `<script>` tags)
- Fragment caching with Russian-doll keys (`cache record do ... end`) when the partial is rendered in a collection of more than ~20 items, paired with `belongs_to :parent, touch: true` on child models so cache invalidates on writes

Layout slots: when the feature needs page-specific JS, sidebar content, or a custom page title, use `content_for :slot_name do ... end` in the view and `= yield :slot_name` in `app/views/layouts/application.html.<ext>`. Do not add inline `<script>` tags or hand-roll layout overrides.

Escaping checklist - verify before generating:

- Default escaped output (`=` in ERB/Slim, `=` in HAML) for every interpolated user-controlled value
- No `.html_safe` on user input anywhere - use `sanitize` with an explicit allowlist if HTML rendering is required
- In Slim specifically: no `==` (unescape) on user data; quote string-literal attribute values to prevent attribute-side Ruby evaluation

**Intentional HTML rendering** (markdown bodies, rich-text comments, admin-curated copy): the field *is* HTML and must render as markup, not text. Escaped output (`=`) would show the raw tags. Use `sanitize` with an explicit tag/attribute allowlist - never `.html_safe` or `==`/`!=`/`raw`:

```slim
/ comment.body is user-submitted HTML (markdown rendered server-side or rich-text editor output)
.comment-body
  = sanitize comment.body, tags: %w[p br strong em a ul ol li blockquote code], attributes: %w[href]
```

For markdown pipelines (`Commonmarker`, `Redcarpet`, `Kramdown`), pass the rendered HTML through `sanitize` even when the renderer claims to be safe-mode - renderer config drifts and a single `raw_html: true` option re-opens XSS. The allowlist is the trust boundary, not the renderer.

### STEP 8 - SECURITY

Use skill: `rails-security-patterns`. Generate:

- Pundit policies for each resource with role-based access (admin, owner, other)
- `after_action :verify_authorized` in controllers
- Scoped queries via `policy_scope` for index actions
- `rescue_from Pundit::NotAuthorizedError` in ApplicationController

### STEP 9 - TESTS

Use skill: `rails-testing-patterns`. Generate:

- Model specs (associations, validations, scopes, enums with shoulda-matchers)
- Service specs (Result object success/failure, side effects, error cases)
- Policy specs (role-based access per action with `permit_action`)
- Request specs (happy path + error cases for each status code + authorization)
- ViewComponent specs (server-rendered features) - `render_inline` per state variant; assert rendered markup and that user-supplied strings are escaped
- Factory with traits for each status/state variation
- Sidekiq job specs with idempotency guard assertions (if applicable)

### STEP 10 - VALIDATE

Run `bundle exec rspec` and `bundle exec rubocop`. Fix any failures before presenting output.

## Output Format

```markdown
## Files Generated

[grouped file list by layer: models, services, controllers, serializers, policies, jobs, tests, migrations]

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

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service object, controller, serializer (API) or views (server-rendered), Pundit policy, tests
- [ ] For server-rendered features: views generated in the project's existing engine (Slim / HAML / ERB - never converted); user-data interpolation uses escaped output; no `.html_safe` on user input; Turbo Frame ids use `dom_id(record)`; intentional-HTML fields (markdown, rich-text) render via `sanitize` with an explicit tag/attribute allowlist; ViewComponent specs cover each state variant
- [ ] Strong params in controller; business logic in service objects; serializers for all API responses
- [ ] Enum fields use explicit integer mapping; `dependent:` set on all associations
- [ ] Sidekiq jobs dispatched after DB transaction commit, not inside it
- [ ] External APIs called through a dedicated client class with explicit timeouts, idempotency-aware retries, a domain error taxonomy, and boundary-stubbed tests (no live HTTP)
- [ ] Pundit policies with role-based access; `verify_authorized` / `verify_policy_scoped` in controllers
- [ ] RSpec covers model, service, policy, request, and job specs; factories have traits for each state
- [ ] `bundle exec rspec` and `bundle exec rubocop` pass
- [ ] Migration includes indexes on FKs and filtered columns; list endpoints paginated
- [ ] Output template filled with files, endpoints, jobs, tests, and migrations

## Avoid

- Generating code before requirements are gathered and design is approved
- Dispatching Sidekiq `.perform_async` inside a DB transaction (worker races the commit)
- Rendering raw ActiveRecord objects from endpoints (use serializers)
- Business logic in controllers or model callbacks (use service objects)
- `params.permit!` or `to_unsafe_h` (mass assignment vulnerability)
- `default_scope` on models (infects all queries, use explicit scopes)
- Enum without explicit integer mapping (values shift when entries reordered)
- Using bare string fields for status without `enum`
- Skipping pagination on list endpoints
- Missing Pundit policy specs (authorization bugs are among the most dangerous)
- Missing `dependent:` on `has_many`/`has_one` associations
