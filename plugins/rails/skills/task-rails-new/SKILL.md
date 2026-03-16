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

## Rules

- Business logic in service objects, not controllers or models - controllers only delegate and render
- Strong params in every controller - never `params.permit!` or `params.to_unsafe_h`
- Serializers for all API responses - never render raw ActiveRecord objects
- Enum fields use Rails enum with explicit integer mapping (`pending: 0, active: 1`)
- Transactions for multi-model mutations via `ActiveRecord::Base.transaction`
- Sidekiq dispatch timing: always call `.perform_async` AFTER the DB transaction commits, never inside it. If the job fires before commit, the worker may read stale data or a row that doesn't exist yet
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

STEP 1 - GATHER: Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main models? (fields, relationships, constraints)
3. Are there external integrations? (payment APIs, email, third-party services)
4. Are background jobs needed? (async processing, notifications, scheduled tasks)
5. Does the feature need authorization? (admin-only, owner-only, public)
6. Are there status transitions? (e.g., order: pending -> confirmed -> shipped -> delivered)

If the user provides only a brief description without answering all questions, infer reasonable defaults and present them for confirmation. If the user provides a ticket or spec, extract the answers from it.

STEP 2 - DESIGN: Use skill: `rails-activerecord-patterns` for association/scope design. Use skill: `rails-service-objects` for service layer design. Propose the implementation layers and present for user approval before generating code.

Present a file tree showing what will be generated:

```
app/
  models/order.rb                    # ActiveRecord model
  services/create_order.rb           # Service object
  controllers/api/v1/orders_controller.rb  # API controller
  serializers/order_serializer.rb    # Response serializer
  policies/order_policy.rb           # Pundit policy
  jobs/order_confirmation_job.rb     # Sidekiq job (if needed)
spec/
  models/order_spec.rb
  services/create_order_spec.rb
  requests/api/v1/orders_spec.rb
  jobs/order_confirmation_job_spec.rb
  factories/orders.rb
db/migrate/xxx_create_orders.rb
```

STEP 3 - DATABASE: Use skill: `rails-migration-safety`. Generate migrations with indexes on foreign keys and frequently-filtered columns. For list endpoints, add indexes that support the default sort order.

STEP 4 - MODELS: Generate/update with associations, validations, scopes, and `enum` with explicit integer mapping. Include `counter_cache` where count queries are expected. Use `dependent: :destroy` or `:restrict_with_error` on all `has_many`.

STEP 5 - SERVICES: Use skill: `rails-service-objects`. Generate service objects with `.call` interface and Result objects. Key patterns:

- Transaction boundary: wrap multi-model mutations in `ActiveRecord::Base.transaction`
- Sidekiq dispatch: call `.perform_async` after the transaction block, not inside it

```ruby
# CORRECT: dispatch after commit
def call
  order = nil
  ActiveRecord::Base.transaction do
    order = build_order
    order.save!
    update_inventory(order)
  end
  # After commit - worker will find the row
  OrderConfirmationJob.perform_async(order.id)
  Result.success(order)
end
```

If Sidekiq needed: Use skill: `rails-sidekiq-patterns`

STEP 6 - CONTROLLERS: Strong params, pagination on list endpoints, delegate all business logic to services. Map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 422         |
| RecordNotFound       | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| Forbidden            | 403         |

STEP 7 - SERIALIZERS: Response shaping for all API responses. Separate serializers per resource. Never return raw ActiveRecord objects from endpoints.

STEP 8 - SECURITY: Use skill: `rails-security-patterns`. Pundit policies for authorization. `after_action :verify_authorized` in controllers. Scoped queries via `policy_scope`.

STEP 9 - TESTS: Use skill: `rails-testing-patterns`. Generate:

- Model specs (associations, validations, scopes with shoulda-matchers)
- Service specs (business logic, error cases, Result object assertions)
- Request specs (happy path + error cases for each status code)
- Factory with traits for each status/variation
- Sidekiq job specs (if applicable)

STEP 10 - VALIDATE: Run `bundle exec rspec` and `bundle exec rubocop`. Fix any failures before presenting output.

## Output

```markdown
## Files Generated

[grouped file list by layer: models, services, controllers, serializers, policies, jobs, tests, migrations]

## Endpoints

| Method | Path               | Request      | Response                   | Status |
| ------ | ------------------ | ------------ | -------------------------- | ------ |
| POST   | /api/v1/orders     | OrderParams  | OrderSerializer            | 201    |
| GET    | /api/v1/orders     | query params | Paginated[OrderSerializer] | 200    |
| GET    | /api/v1/orders/:id | -            | OrderSerializer            | 200    |
| PATCH  | /api/v1/orders/:id | OrderParams  | OrderSerializer            | 200    |
| DELETE | /api/v1/orders/:id | -            | -                          | 204    |

## Sidekiq Jobs (if any)

| Job | Queue | Trigger | Retry |
| --- | ----- | ------- | ----- |

## Tests

[X] specs passing - [list spec files and count per file]

## Migration

[migration file name and what it creates: tables, indexes, constraints]
```

## Avoid

- Dispatching Sidekiq `.perform_async` inside a DB transaction (worker races the commit)
- Rendering raw ActiveRecord objects from endpoints (use serializers)
- Business logic in controllers or model callbacks (use service objects)
- `params.permit!` or `to_unsafe_h` (mass assignment vulnerability)
- `default_scope` on models (infects all queries, use explicit scopes)
- Using bare string fields for status without `enum`
- Skipping pagination on list endpoints
- Generating code before user approves the design

## Self-Check

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service object, controller, serializer, Pundit policy, tests
- [ ] Strong params in controller; business logic in service objects; serializers for all API responses
- [ ] Sidekiq jobs dispatched after DB transaction commit, not inside it
- [ ] Pundit policies applied; RSpec covers model, service, and request specs
- [ ] `bundle exec rspec` and `bundle exec rubocop` pass
- [ ] Migration includes indexes; list endpoints paginated; output template filled
