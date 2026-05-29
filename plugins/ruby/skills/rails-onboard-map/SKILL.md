---
name: rails-onboard-map
description: Rails onboarding signals: Gemfile, Rails version, env configs, AR migrations, ActiveJob, ActionCable, asset pipeline.
metadata:
  category: backend
  tags: [onboarding, codebase-map, rails, ruby, bundler]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the detected stack is Rails.

## When to Use

- Workflow needs Rails-specific orientation: Gemfile, Rails version, env config, ActiveJob backend, ActionCable, asset pipeline
- Project has `Gemfile`, `config/application.rb`, `bin/rails`

## Rules

- Ruby version from `.ruby-version`/`Gemfile`; Rails version from `Gemfile.lock` (trust lock over Gemfile)
- Database from `config/database.yml`: MySQL/MariaDB, PostgreSQL, or SQLite. **Default to MySQL when ambiguous.** PG -> load `rails-postgresql-migration-safety` instead of `rails-migration-safety`
- ActiveJob backend from `config.active_job.queue_adapter`; `:async` (default) is in-memory, unsafe for prod
- Asset/JS pipeline: importmap (7+ default), jsbundling-rails, cssbundling-rails, propshaft (modern), sprockets (legacy)

## Patterns

### Key Files

| Location                                                | Purpose                                          |
| ------------------------------------------------------- | ------------------------------------------------ |
| `Gemfile` / `Gemfile.lock`                              | Gems + `ruby "x.y.z"`; lock is authoritative     |
| `.ruby-version`                                         | Ruby pin                                         |
| `bin/rails` / `bin/setup` / `bin/dev`                   | CLI; setup script; Foreman runner (reads `Procfile.dev`) |
| `config/application.rb`                                 | App-wide config (autoload, timezone, ActiveJob)  |
| `config/environments/`, `config/initializers/`          | Per-env config; boot-time setup (alphabetical)   |
| `config/routes.rb`                                      | Routes                                           |
| `config/database.yml` / `cable.yml` / `storage.yml`     | DB / ActionCable / ActiveStorage backends        |
| `config/credentials.yml.enc` + `master.key`             | Encrypted credentials (missing key blocks boot)  |
| `db/schema.rb` or `db/structure.sql`, `db/migrate/`     | Current schema, migrations                       |
| `app/{controllers,models,views,jobs,mailers,channels}/` | Stereotype dirs                                  |
| `app/javascript/`, `lib/`                               | JS entrypoint; non-Rails code                    |

### Bootstrap Path

1. Toolchain (rbenv/asdf/chruby) from `.ruby-version`
2. `bundle install`; `yarn install` if `package.json` present
3. `bin/setup` or `bin/rails db:create db:migrate db:seed`
4. Local services: `compose.yml` for Postgres/Redis/MailCatcher
5. Run: `bin/dev` (7+) or `bin/rails server` (legacy)
6. Verify: `http://localhost:3000`; health `/up` (7.1+)

### Package Layout

- **Layer-package (default)**: `app/{controllers,models,services,jobs}/` grouped by stereotype
- **Domain-package**: `app/domains/<context>/` or `app/packs/`; often paired with [Packwerk](https://github.com/Shopify/packwerk) (each pack has `package.yml`)
- **Mixed**: domain packs next to legacy `app/services/`. New code in pack; edits to legacy stay

### Conventions

MVC + concerns (`controllers/concerns/`, `models/concerns/`); service/form/query/presenter objects in `app/services/`; strong params for mass assignment; RSpec or Minitest with FactoryBot or fixtures; queue backend (Sidekiq/Solid Queue/GoodJob/DelayedJob); Devise + Pundit/CanCan; Standardrb or RuboCop.

### Risk Hotspots

| Area                            | What to check                                                                        | Skill                          |
| ------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------ |
| N+1 queries                     | `bullet` in Gemfile, `includes` in collection views                                  | `rails-activerecord-patterns`  |
| Implicit config                 | `config.load_defaults <= 6.1`, `new_framework_defaults_*.rb`, `touch:` / `autosave:` | `rails-implicit-config-audit`  |
| Callback abuse                  | Heavy `after_save` business logic                                                    | `rails-code-explain`           |
| `update_columns` / `update_all` | Bypass callbacks/validations                                                         | -                              |
| `permit!` mass assignment       | Audit controllers                                                                    | `rails-security-patterns`      |
| Connection pool sizing          | Sidekiq concurrency vs `max_connections`                                             | `rails-connection-pool-sizing` |
| MySQL `REPEATABLE READ`         | Long transactions, gap locks                                                         | `rails-db-locking-patterns`    |
| Worker memory growth            | jemalloc / `MALLOC_ARENA_MAX=2` / `WorkerKiller`                                     | `rails-batch-processing-patterns` |
| CSRF / Zeitwerk / `master.key`  | Disabled on session controllers; constant-loading bugs at boot; missing key blocks boot | -                           |

### First-PR Safe Zones

Safe: new RESTful route + controller + view; new field with safe-default migration; new spec; new rake task.
Riskier: initializers (run once at boot); existing migrations (never edit; add new); concerns shared across many models/controllers; Devise/Warden config.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Ruby, Rails, DB, ActiveJob backend, JS pipeline, asset pipeline, test framework, auth gem, lint stack.
**Local Bootstrap:** `bin/setup` (or `bundle install` + `bin/rails db:setup`); `bin/dev`; default port; health-check path.
**Architecture Map:** controllers/models/views counts; concerns; services; jobs/mailers/channels; package layout.
**Conventions:** strong params, service object pattern, test framework, factories, queue backend.
**Risk Hotspots:** filtered to actual gemset; cross-reference skills.
**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Rails 5/6 patterns as current
- Skipping JS pipeline detection
- Listing every gem in Gemfile - focus on architecture-changing ones
- Missing the `master.key` requirement
- Recommending Sprockets when project uses Propshaft
