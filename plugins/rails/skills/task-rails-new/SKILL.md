---
name: task-rails-new
description: "Create a new Rails resource. Generates migration, model, service object, controller, serializer, routes, FactoryBot factory, and RSpec tests (model + request specs). Full CRUD with pagination."
agent: rails-architect
---

STEP 1 — GATHER (interactive):

- Resource name (singular: Order, Payment)
- Attributes with types (total:decimal, status:string, customer:references)
- Associations (belongs_to, has_many)
- Operations: full CRUD or subset
- API-only or full-stack?
- Background jobs needed?

STEP 2 — MIGRATION:
Load skill: rails-migration-safety

- Generate migration with indexes on foreign keys, status columns
- Add DB-level constraints (NOT NULL, check constraints)

STEP 3 — MODEL:
Load skill: rails-activerecord-patterns

- Validations mirroring DB constraints
- Associations with proper dependent options
- Scopes for common queries
- enum with Rails 7+ syntax

STEP 4 — SERVICE OBJECT:
Load skill: rails-service-objects

- Create{Resource} service
- Result object pattern

STEP 5 — CONTROLLER:

- Strong parameters
- Pagination (Pagy preferred)
- Delegates to service objects
- API-only: JSON responses

STEP 6 — SERIALIZER:

- Only expose necessary fields
- Nested associations opt-in

STEP 7 — ROUTES:

- resources :orders under /api/v1 namespace (API) or root (full-stack)

STEP 8 — TESTS:
Load skill: rails-testing-patterns

- FactoryBot factory with traits
- Model spec: validations, associations, scopes
- Request spec: all endpoints, error cases, auth
- Service spec: success/failure paths

STEP 9 — VALIDATE:
bundle exec rspec && bundle exec rubocop

OUTPUT: file checklist with paths
