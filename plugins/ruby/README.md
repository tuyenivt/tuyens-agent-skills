# Tuyen's Agent Skills - Ruby / Ruby on Rails

Claude Code plugin for Ruby / Ruby on Rails projects.

## Stack

- Rails 7.2+
- Ruby 3.4+
- RSpec
- Sidekiq
- PostgreSQL
- ActiveRecord

## Agents

| Agent                        | Description                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-architect`            | Ruby on Rails architect for Rails 7.2+, ActiveRecord, service objects, and API design. Designs features, creates endpoints, structures models, and makes architecture decisions. |
| `rails-tech-lead`            | Rails tech lead for code review, refactoring guidance, doc standards, and engineering standards. Reviews Rails code for conventions, performance, security, and test coverage.   |
| `rails-security-engineer`    | OWASP Top 10 for Rails, Devise/JWT auth review, Pundit authorization audit, strong parameters, dependency vulnerability scan.                                                    |
| `rails-performance-engineer` | ActiveRecord N+1 detection, query tuning, Sidekiq throughput, caching strategy, profiling with rack-mini-profiler.                                                               |
| `rails-test-engineer`        | RSpec strategies, FactoryBot fixtures, Shoulda-matchers, Sidekiq testing, VCR/WebMock, and test pyramid design.                                                                  |

## Workflow Skills

| Skill                             | Agent                        | Description                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rails-implement`            | `rails-architect`            | End-to-end Rails feature implementation. Generates migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests.                                                                                                                                                                                                                                                  |
| `task-rails-debug`                | `rails-architect`            | Debug Rails errors. Paste a stack trace, Rails log, Sidekiq error, or RSpec failure. Classifies, identifies root cause, suggests fix, and recommends prevention.                                                                                                                                                                                                                                         |
| `task-rails-review`               | `rails-tech-lead`            | Rails-specific staff-level code review umbrella: Phases A-E (risk, correctness, architecture, AI quality, maintainability) with Rails idioms (Zeitwerk, callback abuse, fat controllers, AR-in-API, service-object boundaries). Spawns Rails perf/security/observability subagents for extra scopes. Delegate of `task-code-review` when stack is Rails. Runs standalone with full PR/branch resolution. |
| `task-rails-review-perf`          | `rails-performance-engineer` | Rails-specific performance review: ActiveRecord N+1, query plans, Sidekiq throughput, caching, rendering hotspots. Delegate of `task-code-review-perf` when stack is Rails.                                                                                                                                                                                                                              |
| `task-rails-review-security`      | `rails-security-engineer`    | Rails-specific security review: strong params, Devise/JWT, Pundit/CanCanCan, mass assignment, Rails-aware OWASP Top 10. Delegate of `task-code-review-security` when stack is Rails.                                                                                                                                                                                                                     |
| `task-rails-review-observability` | `rails-tech-lead`            | Rails-specific observability review: `ActiveSupport::Notifications`, `query_log_tags`, `lograge`/`semantic_logger`, Sidekiq middleware tracing, Rack correlation IDs, error-tracker gem wiring. Delegate of `task-code-review-observability` when stack is Rails.                                                                                                                                        |
| `task-rails-test`                 | `rails-test-engineer`        | Rails-specific test strategy and scaffolding: RSpec, FactoryBot traits, Shoulda-matchers, Pundit policy specs, Sidekiq job specs. Delegate of `task-code-test` when stack is Rails.                                                                                                                                                                                                                      |
| `task-rails-refactor`             | `rails-tech-lead`            | Rails-specific refactor planning: fat models / controllers, callback abuse, missing service objects, scope sprawl, concern soup, polymorphic sprawl. Test-coverage gate + step-by-step independently committable plan. Delegate of `task-code-refactor` when stack is Rails.                                                                                                                             |

## Atomic Skills

| Skill                         | Description                                                                                                                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-activerecord-patterns` | ActiveRecord optimization: N+1 prevention, scopes, enum with integer mapping, associations with dependent options, counter_cache, batch processing, PostgreSQL features.           |
| `rails-migration-safety`      | Safe migration patterns: strong_migrations gem, concurrent indexes, partial indexes, zero-downtime column operations, data migration separation, large table strategies.           |
| `rails-testing-patterns`      | RSpec testing: model specs, service specs, Pundit policy specs, request specs, FactoryBot with state traits, Sidekiq testing, VCR/WebMock, shared examples.                        |
| `rails-security-patterns`     | Rails security: strong parameters, Devise/JWT, Pundit authorization with role-based policies, CSRF, XSS, SQL injection, Rack::Attack, Rails credentials.                           |
| `rails-sidekiq-patterns`      | Sidekiq job patterns: idempotency guards, post-transaction dispatch, retry strategy, queue priority, error handling, job versioning, monitoring.                                   |
| `rails-service-objects`       | Service object patterns: extraction criteria, .call interface, Result objects, input validation, transaction boundaries, post-commit dispatch, composition.                        |
| `rails-rake-task-patterns`    | Rake task patterns: thin orchestrators delegating to services, idempotency/resumability, batch processing, dry-run and production confirmation, structured logging, RSpec testing. |
| `rails-view-templates`        | View-layer patterns for ERB / HAML / Slim: per-engine escaping rules, helper vs presenter vs ViewComponent boundaries, partials and layouts, fragment caching, Turbo Frames/Streams + Stimulus wiring, Slim-specific traps (`==` unescape, attribute Ruby evaluation, indentation scope). |
| `rails-http-client-patterns`  | External HTTP integration with Faraday + Retriable: client-class wrappers, explicit timeouts, idempotency-aware retries with bounded budgets, domain error taxonomy (transient vs permanent), circuit-breaker posture, and boundary-stubbed tests with WebMock / VCR.                     |
| `rails-code-explain`          | Request lifecycle (middleware, filters, controllers), AR callbacks/scopes/transactions, ActiveJob, ActionCable, concerns, Zeitwerk autoload - injected into `task-code-explain`. |
| `rails-onboard-map`           | Gemfile, Rails version, environment configs, AR + migrations, ActiveJob backend, ActionCable wiring, asset pipeline (importmap/jsbundling/Propshaft) - injected into `task-onboard`. |

## Usage Examples

### Implement a feature

```
/task-rails-implement
> Feature: Add order fulfillment workflow
> Models: Order, OrderItem, Product (inventory)
> Background jobs: yes (shipment notification after fulfillment)
> Auth: Pundit (only order owner and admins can view; only admins can fulfill)
> Status transitions: pending -> confirmed -> processing -> shipped -> delivered
```

Generates full implementation with migrations, models, services, controllers, Sidekiq jobs, Pundit policies, and RSpec tests (model, service, policy, request, job specs).
