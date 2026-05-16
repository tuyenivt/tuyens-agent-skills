---
name: rails-onboard-map
description: Rails onboarding map: Gemfile, bundler, Rails version, env configs, AR migrations, ActiveJob, ActionCable, asset pipeline.
metadata:
  category: backend
  tags: [onboarding, codebase-map, rails, ruby, bundler]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the detected stack is Rails.

## When to Use

- A workflow needs Rails-specific orientation: Gemfile, Rails version, env config layout, ActiveJob backend, ActionCable wiring, asset pipeline.
- Project has `Gemfile`, `config/application.rb`, `bin/rails`.

## Rules

- Identify Ruby version (`.ruby-version`, `Gemfile`'s `ruby "..."`) and Rails version (`Gemfile.lock` first).
- Identify the database (`config/database.yml`): MySQL/MariaDB, PostgreSQL, or SQLite. **Default to MySQL when ambiguous** - migration safety, locking, and isolation guidance differ materially. When PG is detected, load `rails-postgresql-migration-safety` instead of `rails-migration-safety`.
- Identify the ActiveJob backend (`config/application.rb` `config.active_job.queue_adapter`); `:async` (default) is in-memory and unsafe for prod.
- Identify the asset/JS pipeline: importmap (Rails 7+ default), jsbundling-rails, cssbundling-rails, propshaft (modern), or sprockets (legacy).

## Patterns

### Build / Tooling Inventory

| File                    | What it tells you                                             |
| ----------------------- | ------------------------------------------------------------- |
| `Gemfile`               | Gems and `ruby "x.y.z"` line                                  |
| `Gemfile.lock`          | Locked versions; trust this over Gemfile                      |
| `bin/rails`             | Rails CLI entry; use `bin/rails` not system `rails`           |
| `bin/setup`             | Setup script; runs migrations, seeds                          |
| `bin/dev`               | Foreman-driven dev runner (Rails 7+); reads `Procfile.dev`    |
| `Procfile.dev`          | Processes started by `bin/dev` (web, worker, asset watcher)   |
| `.ruby-version`         | Ruby version pin                                              |
| `config/database.yml`   | DB config per environment                                     |
| `config/cable.yml`      | ActionCable backend                                           |
| `config/storage.yml`    | ActiveStorage services                                        |

### Bootstrap Path

1. Ruby toolchain: rbenv/asdf/chruby; install version from `.ruby-version`
2. `bundle install`
3. `yarn install` if `package.json` present (jsbundling/Webpacker)
4. `bin/rails db:create db:migrate db:seed` (or `bin/setup`)
5. Local services: `compose.yml` for Postgres/Redis/MailCatcher
6. Run: `bin/dev` (Rails 7+) or `bin/rails server` (legacy)
7. Verify: `http://localhost:3000`; health check `/up` (Rails 7.1+)

### Key File Inventory

| Location                          | Purpose                                                              |
| --------------------------------- | -------------------------------------------------------------------- |
| `config/application.rb`           | App-wide config (autoload paths, time zone, ActiveJob backend)       |
| `config/environments/`            | Per-env config                                                       |
| `config/initializers/`            | One-time setup at boot; ordered alphabetically                       |
| `config/routes.rb`                | Route definitions                                                    |
| `config/credentials.yml.enc` + `master.key` | Encrypted credentials                                      |
| `db/schema.rb` or `db/structure.sql` | Current schema                                                    |
| `db/migrate/`                     | Migrations                                                           |
| `app/{controllers,models,views,jobs,mailers,channels}/` | Stereotype directories                          |
| `app/javascript/`                 | JS entrypoint(s)                                                     |
| `app/assets/`                     | Sprockets/Propshaft static assets                                    |
| `lib/`                            | Custom non-Rails code (autoloaded if added to autoload paths)        |

### Package Layout Convention

- **Rails default (layer-package)**: `app/{controllers,models,services,jobs}/` - files grouped by stereotype. Default for nearly every Rails app.
- **Domain-package (`app/domains/<bounded_context>/` or `app/packs/`)**: feature-package adopted by larger codebases - keeps a bounded context in one tree. Often paired with [Packwerk](https://github.com/Shopify/packwerk) (each pack has `package.yml` declaring public API and dependencies). Common in Shopify-style large apps.
- **Mixed (mid-migration)**: `app/domains/orders/` next to legacy `app/services/order_processor.rb`. New code goes in the domain pack; edits to legacy stay in place. Look for `package.yml` to confirm packwerk is in use.

### Conventions

- **MVC plus concerns**: `controllers/concerns/` and `models/concerns/` hold mixins
- **Service objects**: usually `app/services/` (autoload path may need adding)
- **Form objects, query objects, presenters**: layered patterns
- **Strong params** for mass assignment
- **RSpec or Minitest**: check `Gemfile`
- **FactoryBot or fixtures**: check `spec/factories` or `test/fixtures`
- **Sidekiq / Solid Queue / DelayedJob / GoodJob**: check `config.active_job.queue_adapter`
- **Devise** + **Pundit/CanCan** for auth
- **Standardrb / RuboCop** for style

### Risk Hotspots

| Area                              | What to check                                        | Skill                          |
| --------------------------------- | ---------------------------------------------------- | ------------------------------ |
| N+1 queries                       | `bullet` gem in Gemfile, `includes` in collection views | `rails-activerecord-patterns` |
| Implicit config (load_defaults)   | `config.load_defaults <= 6.1`, `new_framework_defaults_*.rb` flips, `touch:` / `autosave:` / `accepts_nested_attributes_for`, missing `inverse_of` | `rails-implicit-config-audit` |
| Callback abuse                    | Heavy `after_save` business logic                    | `rails-code-explain`           |
| `update_columns` / `update_all`   | Bypass callbacks/validations                         | -                              |
| `permit!` mass assignment         | Audit controllers                                    | `rails-security-patterns`      |
| Devise filter inheritance         | `authenticate_user!` in ApplicationController        | -                              |
| Connection pool sizing            | Sidekiq concurrency vs `max_connections`             | `rails-connection-pool-sizing` |
| MySQL `REPEATABLE READ`           | Long transactions, gap-lock cascades                 | `rails-db-locking-patterns`    |
| Worker memory growth              | jemalloc / `MALLOC_ARENA_MAX=2` / `WorkerKiller`     | `rails-batch-processing-patterns` |
| CSRF                              | Disabled on session-based controllers                | -                              |
| Zeitwerk eager load               | Constant-loading bug surfaces at boot                | -                              |
| `master.key`                      | Missing key blocks boot                              | -                              |

### First-PR Safe Zones

Safe:
- New RESTful route + controller action + view
- New field on a model with a safe-default migration
- New test in spec/test
- New rake task in `lib/tasks/`

Riskier:
- Initializers - run once at boot; bug = won't start
- Existing migrations - never edit; create a new one
- Concerns shared across many models/controllers
- Devise/Warden config and auth flow

### Ecosystem Currency

- Ruby 3.3+ standard, 3.4 latest, 3.2 minimum for modern Rails
- Rails 7.2+ for new projects; Rails 8.0 introduces Solid Queue, Solid Cache, Solid Cable
- Importmap-rails default in Rails 7+; jsbundling-rails common for richer JS
- Propshaft replacing Sprockets (Rails 8 default)
- Solid Queue replacing Sidekiq in some new projects (no Redis required)

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Ruby version, Rails version, DB, ActiveJob backend, JS pipeline, asset pipeline, test framework, auth gem, lint stack.

**Local Bootstrap:** `bin/setup` if present, `bundle install`, `bin/rails db:setup`, `bin/dev`, default port, health-check path.

**Architecture Map:** controllers/models/views file counts, concerns directories, service objects directory, jobs/mailers/channels.

**Conventions:** strong params, service object pattern, test framework, FactoryBot vs fixtures, queue backend.

**Risk Hotspots:** filtered to actual gemset; cross-reference relevant skills.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Rails 5/6 patterns as current
- Skipping JS pipeline detection - importmap vs jsbundling vs webpacker have different bootstrap commands
- Listing every gem in Gemfile - focus on architecture-changing ones
- Missing the master.key requirement
- Recommending Sprockets when project uses Propshaft
- Ignoring Solid Queue/Cache/Cable in Rails 8 projects
