# Tuyen's Agent Skills - Ruby / Ruby on Rails

Claude Code plugin for Ruby / Ruby on Rails projects.

## Stack

- Rails 7.2+
- Ruby 3.4+
- RSpec
- Sidekiq
- MySQL 8.0+ (primary), PostgreSQL 17+ (supported)
- ActiveRecord

## Agents

| Agent                        | Description                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-architect`            | Rails 7.2+ architect - ActiveRecord, service objects, API design. Designs features, models, endpoints, and architecture decisions.                                                |
| `rails-tech-lead`            | Rails 7.2+ quality gate - code review, architectural compliance, refactoring guidance, and doc standards across PRs.                                                              |
| `rails-security-engineer`    | OWASP Top 10 for Rails, Devise/JWT auth review, Pundit authorization audit, strong parameters, dependency vulnerability scan.                                                    |
| `rails-performance-engineer` | ActiveRecord N+1 detection, query tuning, Sidekiq throughput, caching strategy, profiling with rack-mini-profiler.                                                               |
| `rails-test-engineer`        | RSpec strategies, FactoryBot fixtures, Shoulda-matchers, Sidekiq testing, VCR/WebMock, and test pyramid design.                                                                  |

## Workflow Skills

| Skill                             | Agent                        | Description                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rails-implement`            | `rails-architect`            | End-to-end Rails feature implementation. Generates migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests.                                                                                                                                                                                                                                                  |
| `task-rails-debug`                | `rails-architect`            | Debug Rails errors. Paste a stack trace, Rails log, Sidekiq error, or RSpec failure. Classifies, identifies root cause, suggests fix, and recommends prevention.                                                                                                                                                                                                                                         |
| `task-rails-review`               | `rails-tech-lead`            | Rails-specific staff-level code review umbrella: 10 steps covering risk, correctness, architecture, code hygiene, and maintainability, with Rails idioms (Zeitwerk, callback abuse, fat controllers, AR-in-API, service-object boundaries). Spawns Rails perf/security/observability subagents for extra scopes. Delegate of `task-code-review` when stack is Rails. Runs standalone with full PR/branch resolution. |
| `task-rails-review-perf`          | `rails-performance-engineer` | Rails-specific performance review: ActiveRecord N+1, query plans, Sidekiq throughput, caching, rendering hotspots. Delegate of `task-code-review-perf` when stack is Rails.                                                                                                                                                                                                                              |
| `task-rails-review-security`      | `rails-security-engineer`    | Rails-specific security review: strong params, Devise/JWT, Pundit/CanCanCan, mass assignment, Rails-aware OWASP Top 10. Delegate of `task-code-review-security` when stack is Rails.                                                                                                                                                                                                                     |
| `task-rails-review-observability` | `rails-tech-lead`            | Rails-specific observability review: `ActiveSupport::Notifications`, `query_log_tags`, `lograge`/`semantic_logger`, Sidekiq middleware tracing, Rack correlation IDs, error-tracker gem wiring. Delegate of `task-code-review-observability` when stack is Rails.                                                                                                                                        |
| `task-rails-test`                 | `rails-test-engineer`        | Rails-specific test strategy and scaffolding: RSpec, FactoryBot traits, Shoulda-matchers, Pundit policy specs, Sidekiq job specs. Delegate of `task-code-test` when stack is Rails.                                                                                                                                                                                                                      |
| `task-rails-refactor`             | `rails-tech-lead`            | Rails-specific refactor planning: fat models / controllers, callback abuse, missing service objects, scope sprawl, concern soup, polymorphic sprawl. Test-coverage gate + step-by-step independently committable plan. Delegate of `task-code-refactor` when stack is Rails.                                                                                                                             |

## Atomic Skills

| Skill                         | Description                                                                                                                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-activerecord-patterns` | ActiveRecord optimization: N+1 prevention, scopes, enum with integer mapping, associations with dependent options, counter_cache, batch processing, MySQL/PostgreSQL features, locking. |
| `rails-implicit-config-audit` | Audit hidden Rails configuration: `load_defaults` 6.1 baseline, `new_framework_defaults_*.rb` initializer-timing footguns, per-model `touch:`/`autosave:`/`inverse_of`/callback side effects, env overrides, curated 7.0-7.2 cherry-pick suggestions. |
| `rails-migration-safety`      | Zero-downtime Rails migrations: MySQL 8.0 online/instant DDL, invisible indexes, gh-ost; PG concurrent indexes via sibling skill.                                                  |
| `rails-postgresql-migration-safety` | Zero-downtime Rails/PostgreSQL migrations: concurrent indexes, validate-false check constraints, pg_advisory_lock, lock_timeout, large tables.                              |
| `rails-connection-pool-sizing` | Connection pool sizing for Rails: Puma + Sidekiq + console budget vs DB max_connections, deploy spikes, RDS Proxy / ProxySQL / PgBouncer.                                         |
| `rails-db-locking-patterns`   | Database locking for Rails: GET_LOCK / pg_advisory_lock leader election, lock-hold discipline, isolation tiers, deadlock avoidance.                                                |
| `rails-work-splitter-patterns` | Splitting batch work across Rake/Sidekiq: modulo shards, SKIP LOCKED cursors, shards-table, rake fan-out with leader lock and push_bulk.                                          |
| `rails-batch-processing-patterns` | Batch processing for Rails: chunked transactions, memory-safe iteration, jemalloc, pluck cursors, GC.compact, WorkerKiller, MySQL undo log.                                    |
| `rails-testing-patterns`      | RSpec testing: model specs, service specs, Pundit policy specs, request specs, FactoryBot with state traits, Sidekiq testing, VCR/WebMock, shared examples.                        |
| `rails-security-patterns`     | Rails security: strong parameters, Devise/JWT, Pundit authorization with role-based policies, CSRF, XSS, SQL injection, Rack::Attack, Rails credentials.                           |
| `rails-sidekiq-patterns`      | Sidekiq job patterns: idempotency guards, post-transaction dispatch, retry strategy, queue priority, error handling, job versioning, monitoring.                                   |
| `rails-service-objects`       | Service object patterns: extraction criteria, .call interface, Result objects, input validation, transaction boundaries, post-commit dispatch, composition.                        |
| `rails-rake-task-patterns`    | Rake task patterns: thin orchestrators delegating to services, idempotency/resumability, batch processing, dry-run and production confirmation, structured logging, RSpec testing. |
| `rails-view-templates`        | View-layer patterns for ERB / HAML / Slim: per-engine escaping rules, helper vs presenter vs ViewComponent boundaries, partials and layouts, fragment caching, Turbo Frames/Streams + Stimulus wiring, Slim-specific traps (`==` unescape, attribute Ruby evaluation, indentation scope). |
| `rails-http-client-patterns`  | External HTTP integration with Faraday + Retriable: client-class wrappers, explicit timeouts, idempotency-aware retries with bounded budgets, domain error taxonomy (transient vs permanent), circuit-breaker posture, and boundary-stubbed tests with WebMock / VCR.                     |
| `rails-code-explain`          | Request lifecycle (middleware, filters, controllers), AR callbacks/scopes/transactions, ActiveJob, ActionCable, concerns, Zeitwerk autoload - injected into `task-code-explain`. |
| `rails-onboard-map`           | Gemfile, Rails version, environment configs, AR + migrations, ActiveJob backend, ActionCable wiring, asset pipeline (importmap/jsbundling/Propshaft) - injected into `task-onboard`. |
| `rails-overengineering-review` | Necessity review: validations duplicating DB constraints (FK / NOT NULL / UNIQUE / enum), defensive guards on impossible states, service objects / Result types / base classes wrapping trivial logic. Includes "when redundancy is justified" (form UX, system boundaries, 3+ call sites). Composed into `task-rails-review` Step 7 (Code Hygiene). |
| `rails-transaction-patterns`  | Transaction boundary discipline: nested transactions and `requires_new`, savepoints, `after_save` vs `after_commit`, `after_commit_everywhere` for dispatch, isolation levels, deadlock/serialization-failure retry. |
| `rails-concurrency-patterns`  | Ruby 3.x concurrency in Rails: `load_async`, `Concurrent::Promises`, `Fiber::Scheduler` and the `async` gem, `Ractor` for CPU work, GVL implications, connection-pool discipline across threads/fibers. |
| `rails-actioncable-patterns`  | ActionCable for Rails 7.2: channel auth via `identified_by`, subscription authorization (IDOR prevention), `turbo_stream_from` scope security, Redis vs PG adapter, fan-out batching, channel and broadcast testing. |
| `rails-exception-handling`    | Application-wide rescue strategy: `ApplicationController#rescue_from` ladder, domain error taxonomy (`ApplicationError::*`), `Result` vs raise, Sidekiq retry propagation, SDK-error translation at boundaries, single-source reporting via `Rails.error`. |
| `rails-active-storage-patterns` | Active Storage on Rails 7.2: direct upload to S3/GCS, content-type/size validation with magic-byte sniffing, libvips variants, background variant warming, `purge_later` semantics, orphan blob cleanup, migration from CarrierWave/Paperclip. |

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
