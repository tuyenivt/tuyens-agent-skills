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

- A workflow needs Rails-specific orientation: Gemfile, Rails version, env config, ActiveJob backend, ActionCable, asset pipeline
- Project has `Gemfile`, `config/application.rb`, `bin/rails`

## Rules

- Identify Ruby version (`.ruby-version`, `Gemfile`) and Rails version (`Gemfile.lock` first)
- Identify the database (`config/database.yml`): MySQL/MariaDB, PostgreSQL, or SQLite. **Default to MySQL when ambiguous.** When PG is detected, load `rails-postgresql-migration-safety` instead of `rails-migration-safety`
- Identify ActiveJob backend (`config.active_job.queue_adapter`); `:async` (default) is in-memory, unsafe for prod
- Identify asset/JS pipeline: importmap (Rails 7+ default), jsbundling-rails, cssbundling-rails, propshaft (modern), sprockets (legacy)

## Patterns

### Tooling Inventory

| File                    | What it tells you                                  |
| ----------------------- | -------------------------------------------------- |
| `Gemfile`               | Gems + `ruby "x.y.z"` line                          |
| `Gemfile.lock`          | Locked versions; trust over Gemfile                |
| `bin/rails`             | Rails CLI; use `bin/rails` not system `rails`       |
| `bin/setup`             | Setup script; migrations, seeds                     |
| `bin/dev`               | Foreman runner (Rails 7+); reads `Procfile.dev`     |
| `Procfile.dev`          | Processes started by `bin/dev` (web, worker, asset) |
| `.ruby-version`         | Ruby version pin                                    |
| `config/database.yml`   | DB config per environment                           |
| `config/cable.yml`      | ActionCable backend                                 |
| `config/storage.yml`    | ActiveStorage services                              |

### Bootstrap Path

1. Ruby toolchain: rbenv/asdf/chruby; install from `.ruby-version`
2. `bundle install`
3. `yarn install` if `package.json` present
4. `bin/rails db:create db:migrate db:seed` (or `bin/setup`)
5. Local services: `compose.yml` for Postgres/Redis/MailCatcher
6. Run: `bin/dev` (Rails 7+) or `bin/rails server` (legacy)
7. Verify: `http://localhost:3000`; health `/up` (Rails 7.1+)

### Key Files

| Location                                     | Purpose                                       |
| -------------------------------------------- | --------------------------------------------- |
| `config/application.rb`                      | App-wide config (autoload, timezone, ActiveJob)|
| `config/environments/`                       | Per-env config                                |
| `config/initializers/`                       | Boot-time setup; alphabetical order           |
| `config/routes.rb`                           | Routes                                        |
| `config/credentials.yml.enc` + `master.key`  | Encrypted credentials                         |
| `db/schema.rb` / `db/structure.sql`          | Current schema                                |
| `db/migrate/`                                | Migrations                                    |
| `app/{controllers,models,views,jobs,mailers,channels}/` | Stereotype directories              |
| `app/javascript/`                            | JS entrypoint(s)                              |
| `lib/`                                       | Custom non-Rails code                         |

### Package Layout

- **Rails default (layer-package)**: `app/{controllers,models,services,jobs}/` - grouped by stereotype
- **Domain-package (`app/domains/<context>/` or `app/packs/`)**: feature-package for larger codebases. Often paired with [Packwerk](https://github.com/Shopify/packwerk) (each pack has `package.yml`)
- **Mixed**: `app/domains/orders/` next to legacy `app/services/order_processor.rb`. New code in domain pack; edits to legacy stay

### Conventions

- MVC + concerns (`controllers/concerns/`, `models/concerns/`)
- Service objects usually in `app/services/`
- Form / query / presenter objects layered
- Strong params for mass assignment
- RSpec or Minitest (check Gemfile)
- FactoryBot or fixtures (check `spec/factories` or `test/fixtures`)
- Queue backend (`config.active_job.queue_adapter`): Sidekiq / Solid Queue / DelayedJob / GoodJob
- Devise + Pundit/CanCan for auth
- Standardrb / RuboCop for style

### Risk Hotspots

| Area                              | What to check                                       | Skill                               |
| --------------------------------- | --------------------------------------------------- | ----------------------------------- |
| N+1 queries                       | `bullet` in Gemfile, `includes` in collection views | `rails-activerecord-patterns`       |
| Implicit config                   | `config.load_defaults <= 6.1`, `new_framework_defaults_*.rb`, `touch:` / `autosave:` | `rails-implicit-config-audit` |
| Callback abuse                    | Heavy `after_save` business logic                   | `rails-code-explain`                |
| `update_columns` / `update_all`   | Bypass callbacks/validations                        | -                                   |
| `permit!` mass assignment         | Audit controllers                                   | `rails-security-patterns`           |
| Connection pool sizing            | Sidekiq concurrency vs `max_connections`            | `rails-connection-pool-sizing`      |
| MySQL `REPEATABLE READ`           | Long transactions, gap locks                        | `rails-db-locking-patterns`         |
| Worker memory growth              | jemalloc / `MALLOC_ARENA_MAX=2` / `WorkerKiller`    | `rails-batch-processing-patterns`   |
| CSRF                              | Disabled on session controllers                     | -                                   |
| Zeitwerk eager load               | Constant-loading bug surfaces at boot               | -                                   |
| `master.key`                      | Missing key blocks boot                             | -                                   |

### First-PR Safe Zones

Safe: new RESTful route + controller + view; new field with safe-default migration; new spec; new rake task.

Riskier: initializers (run once at boot); existing migrations (never edit; create new); concerns shared across many models/controllers; Devise/Warden config.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Ruby version, Rails version, DB, ActiveJob backend, JS pipeline, asset pipeline, test framework, auth gem, lint stack.

**Local Bootstrap:** `bin/setup` if present, `bundle install`, `bin/rails db:setup`, `bin/dev`, default port, health-check path.

**Architecture Map:** controllers/models/views file counts, concerns directories, services directory, jobs/mailers/channels.

**Conventions:** strong params, service object pattern, test framework, factories, queue backend.

**Risk Hotspots:** filtered to actual gemset; cross-reference relevant skills.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Rails 5/6 patterns as current
- Skipping JS pipeline detection
- Listing every gem in Gemfile - focus on architecture-changing ones
- Missing the master.key requirement
- Recommending Sprockets when project uses Propshaft
