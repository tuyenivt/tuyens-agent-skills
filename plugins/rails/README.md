# Tuyen's Agent Skills - Ruby on Rails

Claude Code plugin for Ruby on Rails projects.

## Stack

- Rails 7+/8
- Ruby 3.2+
- RSpec
- Sidekiq
- PostgreSQL
- ActiveRecord

## Requirements

- Claude Code >= 2.0.0
- Ruby 3.2+
- Rails 7+/8
- PostgreSQL

## Installation

Install the core plugin first, then the Rails plugin:

```
/plugin install core@tuyens-agent-skills
/plugin install rails@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/rails/skills" "$HOME/.codex/skills/tuyens-agent-skills-rails-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-rails-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/rails/skills"
```

## Agents

| Agent                        | Description                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rails-architect`            | Ruby on Rails architect for Rails 7+/8, ActiveRecord, service objects, and API design. Designs features, creates endpoints, structures models, and makes architecture decisions. |
| `rails-tech-lead`            | Rails tech lead for code review, architecture decisions, and engineering standards. Reviews Rails code for conventions, performance, security, and test coverage.                |
| `rails-reliability-engineer` | Rails reliability engineer for incident analysis in Rails/Sidekiq/PostgreSQL environments. Debugging, postmortem, release planning.                                              |

## Workflow Skills

| Skill                          | Description                                                                                                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rails-new`               | Create a new Rails resource. Generates migration, model, service object, controller, serializer, routes, FactoryBot factory, and RSpec tests.                    |
| `task-rails-implement-feature` | End-to-end Rails feature implementation. Generates migrations, models, services, controllers, serializers, Sidekiq jobs, and comprehensive RSpec tests.          |
| `task-rails-debug`             | Debug Rails errors. Paste a stack trace, Rails log, Sidekiq error, or RSpec failure. Classifies, identifies root cause, suggests fix, and recommends prevention. |

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

### Create a new resource

```
/task-rails-new
> Resource: Order
> Attributes: total:decimal, status:string, customer:references
> Operations: full CRUD
> API-only: yes
```

Generates: migration, model, service object, controller, serializer, routes, factory, model spec, request spec.

### Implement a feature

```
/task-rails-implement-feature
> Feature: Add order fulfillment workflow
> Models: Order, Fulfillment, ShipmentTracking
> Background jobs: yes (notify warehouse, send tracking email)
> Auth: Pundit (only order owner and admins)
```

Generates full implementation with migrations, models, services, controllers, Sidekiq jobs, Pundit policies, and RSpec tests.
