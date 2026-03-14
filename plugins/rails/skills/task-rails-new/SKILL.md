---
name: task-rails-new
description: End-to-end Rails feature implementation workflow. Generates all layers: migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests. Use for new features requiring multiple coordinated layers. Not for single-file fixes or isolated bug fixes (use task-rails-debug for errors).
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - GATHER: feature description, affected models, external integrations, background jobs, auth rules

STEP 2 - DESIGN: propose models/migrations/services/controllers/routes/jobs, present for approval
Load: rails-activerecord-patterns, rails-service-objects

STEP 3 - DATABASE: load rails-migration-safety, generate migrations

STEP 4 - MODELS: generate/update with associations and validations

STEP 5 - SERVICES: load rails-service-objects, generate service objects
If Sidekiq needed: load rails-sidekiq-patterns

STEP 6 - CONTROLLERS: strong params, pagination, delegate to services

STEP 7 - SERIALIZERS: response shaping

STEP 8 - SECURITY: load rails-security-patterns, Pundit policies

STEP 9 - TESTS: load rails-testing-patterns
Model specs, service specs, request specs, factory with traits, Sidekiq job specs

STEP 10 - VALIDATE: bundle exec rspec && bundle exec rubocop

OUTPUT: file list, endpoint summary, test count

## Self-Check

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service object, controller, serializer, tests
- [ ] Strong params in controller; business logic in service objects; serializers for all API responses
- [ ] Pundit policies applied; RSpec covers model, service, and request specs
- [ ] `bundle exec rspec` and `bundle exec rubocop` pass
- [ ] Migration includes indexes; list endpoints paginated; file list and test count presented
