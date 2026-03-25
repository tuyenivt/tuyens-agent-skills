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

| Skill                         | Description                                                                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-activerecord-patterns` | ActiveRecord optimization: N+1 prevention, scopes, associations, counter_cache, find_each, connection pooling, PostgreSQL features.          |
| `rails-migration-safety`      | Safe migration patterns: strong_migrations gem, zero-downtime DDL, reversible migrations, data migration separation, large table operations. |
| `rails-testing-patterns`      | RSpec testing: model specs, request specs, system specs, FactoryBot, shoulda-matchers, Sidekiq testing, VCR/WebMock.                         |
| `rails-security-patterns`     | Rails security: strong parameters, Devise/JWT, Pundit authorization, CSRF, XSS, SQL injection, Rack::Attack, Rails credentials.              |
| `rails-sidekiq-patterns`      | Sidekiq job patterns: idempotency, retry strategy, queue priority, error handling, job versioning, monitoring.                               |
| `rails-service-objects`       | Service object patterns: when to extract, naming, Result objects, input validation, error handling, composition.                             |

## Usage Examples

### Implement a feature

```
/task-rails-new
> Feature: Add order fulfillment workflow
> Models: Order, Fulfillment, ShipmentTracking
> Background jobs: yes (notify warehouse, send tracking email)
> Auth: Pundit (only order owner and admins)
```

Generates full implementation with migrations, models, services, controllers, Sidekiq jobs, Pundit policies, and RSpec tests.
