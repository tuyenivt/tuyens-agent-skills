---
name: task-rails-implement-feature
description: "End-to-end Rails feature implementation. Generates migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests from a feature description."
agent: rails-architect
---

STEP 1 — GATHER: feature description, affected models, external integrations, background jobs, auth rules

STEP 2 — DESIGN: propose models/migrations/services/controllers/routes/jobs, present for approval
  Load: rails-activerecord-patterns, rails-service-objects

STEP 3 — DATABASE: load rails-migration-safety, generate migrations

STEP 4 — MODELS: generate/update with associations and validations

STEP 5 — SERVICES: load rails-service-objects, generate service objects
  If Sidekiq needed: load rails-sidekiq-patterns

STEP 6 — CONTROLLERS: strong params, pagination, delegate to services

STEP 7 — SERIALIZERS: response shaping

STEP 8 — SECURITY: load rails-security-patterns, Pundit policies

STEP 9 — TESTS: load rails-testing-patterns
  Model specs, service specs, request specs, factory with traits, Sidekiq job specs

STEP 10 — VALIDATE: bundle exec rspec && bundle exec rubocop

OUTPUT: file list, endpoint summary, test count
