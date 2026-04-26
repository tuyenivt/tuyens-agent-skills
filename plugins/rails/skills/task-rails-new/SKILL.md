---
name: task-rails-new
description: Scaffold a multi-layer Rails feature end-to-end - migrations, models, services, controllers, serializers, Sidekiq jobs, and RSpec tests. Use for new features requiring coordinated layers; not for single-file fixes (use task-rails-debug).
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
- Pure frontend changes or view-only work
- Database-only migrations without application code

## Edge Cases

- **Partial input**: If the user provides only a feature name without details, ask for entity fields, relationships, and operations before proceeding to design.
- **No background jobs**: If the feature does not require async processing, skip Sidekiq job generation. Do not generate empty job files.
- **Existing models**: If the user references a model that already exists, read the existing model and extend it rather than creating a new one. Skip migration if no schema change is needed.
- **Referenced model doesn't exist**: If the feature has a relationship to a model not yet in the codebase (e.g., `belongs_to :product`), ask the user whether to generate the referenced model or assume it already exists.
- **API-only app**: If the project inherits from `ActionController::API`, skip CSRF configuration and session-based auth patterns.
- **State machine transitions**: Feature has explicit status transitions (e.g., pending -> confirmed -> shipped). Generate transition validation in the service layer and enum with explicit integer mapping.
- **Inventory/counter operations**: Feature decrements or increments a counter on another model. Wrap in a transaction with the status change; dispatch jobs after commit.

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
  controllers/api/v1/orders_controller.rb  # API controller
  serializers/order_serializer.rb          # Response serializer
  policies/order_policy.rb                 # Pundit policy
  jobs/shipment_notification_job.rb        # Sidekiq job (if needed)
spec/
  models/order_spec.rb
  services/fulfill_order_spec.rb
  policies/order_policy_spec.rb
  requests/api/v1/orders_spec.rb
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

### STEP 6 - CONTROLLERS

Strong params, pagination on list endpoints, delegate all business logic to services. Map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 422         |
| RecordNotFound       | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| Forbidden            | 403         |

### STEP 7 - SERIALIZERS

Response shaping for all API responses. Separate serializers per resource. Never return raw ActiveRecord objects from endpoints.

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
- [ ] All layers generated: migration, model, service object, controller, serializer, Pundit policy, tests
- [ ] Strong params in controller; business logic in service objects; serializers for all API responses
- [ ] Enum fields use explicit integer mapping; `dependent:` set on all associations
- [ ] Sidekiq jobs dispatched after DB transaction commit, not inside it
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
