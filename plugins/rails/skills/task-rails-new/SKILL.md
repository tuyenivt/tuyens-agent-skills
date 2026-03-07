---
name: task-rails-new
description: "End-to-end Rails feature implementation. Generates migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests from a feature description."
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

## Success Criteria

A well-executed feature implementation passes all of these. Use as a self-check before presenting to the user.

### Completeness

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service object, controller, serializer, tests
- [ ] Validated with `bundle exec rspec` and `bundle exec rubocop`

### Rails Correctness

- [ ] Strong params defined in the controller - no mass-assignment vulnerabilities
- [ ] Business logic in service objects - not in controllers or models
- [ ] Serializers used for all API responses - no raw `to_json` on ActiveRecord objects
- [ ] Pundit policies applied for authorization - not ad-hoc `current_user` checks in controllers
- [ ] RSpec tests cover model specs, service specs, and request specs with factory traits

### Staff-Level Signal

- [ ] Migration includes indexes for foreign keys and frequently filtered columns
- [ ] List endpoints include pagination (Kaminari or Pagy)
- [ ] If Sidekiq used, job idempotency is included
- [ ] File list, endpoint summary, and test count presented to user

## After This Skill

If the output needed significant adjustment - business logic ended up in controllers or models, Pundit policies were missing, or serializers were skipped - run `/task-skill-feedback` to log what changed and why.
