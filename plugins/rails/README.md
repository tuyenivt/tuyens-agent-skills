# Tuyen's Agent Skills - Ruby on Rails

Claude Code plugin for Ruby on Rails projects.

## Stack

- Rails 7+/8
- Ruby 3.2+
- RSpec
- Sidekiq
- PostgreSQL
- ActiveRecord

## Agents

| Agent                        | Description                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-architect`            | Ruby on Rails architect for Rails 7+/8, ActiveRecord, service objects, and API design. Designs features, creates endpoints, structures models, and makes architecture decisions. |
| `rails-tech-lead`            | Rails tech lead for code review, refactoring guidance, doc standards, and engineering standards. Reviews Rails code for conventions, performance, security, and test coverage.   |
| `rails-reliability-engineer` | Rails reliability engineer for incident analysis, runbook standards in Rails/Sidekiq/PostgreSQL environments. Debugging, postmortem, release planning.                           |
| `rails-security-engineer`    | OWASP Top 10 for Rails, Devise/JWT auth review, Pundit authorization audit, strong parameters, dependency vulnerability scan.                                                    |
| `rails-performance-engineer` | ActiveRecord N+1 detection, query tuning, Sidekiq throughput, caching strategy, profiling with rack-mini-profiler.                                                               |
| `rails-test-engineer`        | RSpec strategies, FactoryBot fixtures, Shoulda-matchers, Sidekiq testing, VCR/WebMock, and test pyramid design.                                                                  |
| `rails-sprint-planner`       | Sprint allocation for Rails features with Sidekiq/large-table migration complexity awareness.                                                                                    |

## Workflow Skills

| Skill              | Description                                                                                                                                                      |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rails-new`   | End-to-end Rails feature implementation. Generates migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests.          |
| `task-rails-debug` | Debug Rails errors. Paste a stack trace, Rails log, Sidekiq error, or RSpec failure. Classifies, identifies root cause, suggests fix, and recommends prevention. |

## Atomic Skills

| Skill                         | Description                                                                                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rails-activerecord-patterns` | ActiveRecord optimization: N+1 prevention, scopes, enum with integer mapping, associations with dependent options, counter_cache, batch processing, PostgreSQL features. |
| `rails-migration-safety`      | Safe migration patterns: strong_migrations gem, concurrent indexes, partial indexes, zero-downtime column operations, data migration separation, large table strategies. |
| `rails-testing-patterns`      | RSpec testing: model specs, service specs, Pundit policy specs, request specs, FactoryBot with state traits, Sidekiq testing, VCR/WebMock, shared examples.              |
| `rails-security-patterns`     | Rails security: strong parameters, Devise/JWT, Pundit authorization with role-based policies, CSRF, XSS, SQL injection, Rack::Attack, Rails credentials.                 |
| `rails-sidekiq-patterns`      | Sidekiq job patterns: idempotency guards, post-transaction dispatch, retry strategy, queue priority, error handling, job versioning, monitoring.                         |
| `rails-service-objects`       | Service object patterns: extraction criteria, .call interface, Result objects, input validation, transaction boundaries, post-commit dispatch, composition.              |

## Usage Examples

### Implement a feature

```
/task-rails-new
> Feature: Add order fulfillment workflow
> Models: Order, OrderItem, Product (inventory)
> Background jobs: yes (shipment notification after fulfillment)
> Auth: Pundit (only order owner and admins can view; only admins can fulfill)
> Status transitions: pending -> confirmed -> processing -> shipped -> delivered
```

Generates full implementation with migrations, models, services, controllers, Sidekiq jobs, Pundit policies, and RSpec tests (model, service, policy, request, job specs).
