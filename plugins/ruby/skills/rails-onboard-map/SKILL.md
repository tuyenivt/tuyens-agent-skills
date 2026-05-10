---
name: rails-onboard-map
description: Rails onboarding map: Gemfile, bundler, Rails version, env configs, AR migrations, ActiveJob, ActionCable, asset pipeline.
metadata:
  category: backend
  tags: [onboarding, codebase-map, rails, ruby, bundler]
user-invocable: false
---

# Rails Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Ruby on Rails.

## When to Use

- A workflow needs Rails-specific orientation: Gemfile, Rails version, environment config layout, ActiveJob backend, ActionCable wiring, asset pipeline / Vite / Webpacker / esbuild.
- Project has `Gemfile`, `config/application.rb`, and `bin/rails`.

## Rules

- Identify Ruby version (`.ruby-version`, `Gemfile`'s `ruby "..."` line) and Rails version (`Gemfile.lock` first) before describing layout.
- Identify the database (`config/database.yml`); migration patterns differ between Postgres and SQLite/MySQL.
- Identify the ActiveJob backend (`config/application.rb` `config.active_job.queue_adapter`); :async (default) is in-memory and unsafe for prod.
- Identify the asset/JS pipeline: importmap (Rails 7+ default), jsbundling-rails (esbuild/rollup/webpack), cssbundling-rails, propshaft (modern), or sprockets (legacy).

## Patterns

### Build / Tooling Inventory

| File                | What it tells you                                                                  |
| ------------------- | ---------------------------------------------------------------------------------- |
| `Gemfile`           | Gems and `ruby "x.y.z"` line                                                       |
| `Gemfile.lock`      | Locked versions; trust this over Gemfile for actual installs                       |
| `bin/rails`         | Rails CLI entry; use `bin/rails` not system `rails`                                |
| `bin/setup`         | Setup script; runs migrations, seeds, etc.                                         |
| `bin/dev`           | Foreman-driven dev runner (Rails 7+); reads `Procfile.dev`                         |
| `Procfile.dev`      | Lists processes started by `bin/dev` (web, worker, asset watcher)                  |
| `.ruby-version`     | Ruby version pin                                                                   |
| `config/database.yml` | DB config per environment                                                        |
| `config/cable.yml`  | ActionCable backend (async, redis)                                                  |
| `config/storage.yml` | ActiveStorage services (local, s3, gcs)                                            |

### Bootstrap Path

1. Ruby toolchain: rbenv/asdf/chruby; install version from `.ruby-version`.
2. Bundler: `bundle install`.
3. Yarn / npm install if there is a `package.json` (jsbundling-rails or full Webpacker).
4. Database: `bin/rails db:create db:migrate db:seed` (or `bin/setup` if it exists).
5. Local services: `compose.yml` for Postgres/Redis/MailCatcher; or system installs.
6. Run: `bin/dev` (Rails 7+ Procfile.dev) or `bin/rails server` (legacy).
7. Verify: open `http://localhost:3000`; health check usually `/up` (Rails 7.1+) or custom.

### Key File Inventory

| Location                          | Purpose                                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------- |
| `config/application.rb`           | Application-wide config (autoload paths, time zone, generators, ActiveJob backend)       |
| `config/environments/`            | Per-env config (`development.rb`, `test.rb`, `production.rb`)                            |
| `config/initializers/`            | One-time setup at boot; ordered alphabetically                                            |
| `config/routes.rb`                | Route definitions                                                                          |
| `config/credentials.yml.enc` + `master.key` | Encrypted credentials                                                          |
| `config/database.yml`             | DB config                                                                                  |
| `db/schema.rb` or `db/structure.sql` | Current schema                                                                          |
| `db/migrate/`                     | Migrations (`YYYYMMDDHHMMSS_*.rb`)                                                        |
| `app/controllers/`                | Controllers, ApplicationController                                                         |
| `app/models/`                     | Models                                                                                     |
| `app/views/`                      | View templates (ERB, Slim, Haml)                                                           |
| `app/jobs/`                       | ActiveJob classes                                                                           |
| `app/mailers/` + `app/views/<mailer>/` | Mailers                                                                              |
| `app/channels/`                   | ActionCable channels                                                                       |
| `app/javascript/`                 | JS entrypoint(s) for jsbundling/Vite                                                       |
| `app/assets/`                     | Sprockets/Propshaft static assets                                                          |
| `lib/`                            | Custom non-Rails code (autoloaded if added to autoload paths)                              |
| `test/` or `spec/`                | Minitest or RSpec tests                                                                    |

### Package Layout Convention

Check which the project uses before describing the architecture:

- **Rails default (layer-package)**: the canonical layout - `app/controllers/`, `app/models/`, `app/views/`, `app/services/`, `app/jobs/`, `app/mailers/`, `app/channels/`. Files grouped by stereotype; an `Order`-related concern is spread across `app/controllers/orders_controller.rb`, `app/models/order.rb`, `app/services/order_fulfillment.rb`, `app/jobs/order_notification_job.rb`. Matches Rails generators (`bin/rails g model`, `g controller`, `g job` all drop into stereotype directories). The default for nearly every Rails app
- **Domain-package (`app/domains/<bounded_context>/` or `app/packs/`)**: feature-package equivalent adopted by larger Rails codebases trying to enforce module boundaries - `app/domains/orders/{controllers/, models/, services/, jobs/}` keeps an entire bounded context in one tree. Often paired with [Packwerk](https://github.com/Shopify/packwerk) for compile-time boundary enforcement (each pack has its own `package.yml` declaring public API and dependencies) or with [Rails Engines](https://guides.rubyonrails.org/engines.html) where each engine is a gem in `engines/<name>/`. Common in Shopify-style large apps; uncommon below ~200 models. New code goes in the domain pack; cross-domain reads go through the pack's public API, not direct AR access
- **Mixed (mid-migration)**: `app/domains/orders/` (domain-package) sits next to a legacy `app/services/order_processor.rb` (layer-package). When you find both, the project is mid-migration to packwerk / domain packs; new code goes in the domain pack, edits to legacy code stay in place until a planned move. Confirm direction with the team before adding files - generators still default to layer-package locations and the output may need manual relocation. Look for `package.yml` files under `app/domains/*/` to confirm packwerk is in use; absence means the domain split is convention-only and easier to violate accidentally

### Conventions

- **MVC plus concerns:** controllers/concerns and models/concerns hold mixins.
- **Service objects:** common in mature Rails apps; usually `app/services/` (autoload path may need adding).
- **Form objects, query objects, presenters:** patterns layered on top of MVC for complex UIs.
- **Strong params** for mass assignment.
- **RSpec or Minitest:** check `Gemfile` for `rspec-rails` vs `minitest`.
- **FactoryBot or fixtures:** check `Gemfile` and `spec/factories` or `test/fixtures`.
- **Sidekiq, Solid Queue (Rails 8 default), DelayedJob, GoodJob:** check `Gemfile` and `config.active_job.queue_adapter`.
- **Devise** for authentication (often); confirm in `Gemfile`. Pundit/CanCan for authorization.
- **Standardrb / RuboCop** for style enforcement.

### Risk Hotspots Specific to Rails

- **N+1 queries** - missing `includes`/`eager_load` in collection-rendering views; `bullet` gem indicates active monitoring (see `rails-activerecord-patterns`)
- **Callback abuse** - heavy `after_save` logic implicitly fires across the app (see `rails-code-explain`)
- **`update_columns` / `update_all`** bypass callbacks and validations
- **Mass assignment with `permit!`** in controllers (see `rails-security-patterns`)
- **Devise filter inheritance** - `authenticate_user!` in ApplicationController affects every subclass
- **Sidekiq concurrency vs DB pool** - Sidekiq concurrency must be ≤ DB `pool` per process, or workers stall (see `rails-sidekiq-patterns`)
- **CSRF** - disabled on API controllers; verify it isn't disabled on session-based controllers
- **Zeitwerk eager load at production boot** - any constant-loading bug surfaces at deploy time
- **`config/credentials.yml.enc`** requires `master.key`; missing key blocks boot

### First-PR Safe Zones

- Adding a new RESTful route + controller action + view.
- Adding a new field to a model with a migration that has a safe default.
- Adding a new test in spec/test directory.
- Adding a new Rake task in `lib/tasks/`.

Riskier:

- Initializers - run once at boot; bug = won't start.
- Existing migrations - never edit; create a new migration to alter.
- Concerns shared across many models/controllers.
- Devise/Warden config and auth flow.

### Ecosystem Currency

- Ruby 3.3+ standard; 3.4 latest, 3.2 minimum for modern Rails.
- Rails 7.2+ for new projects; Rails 8.0 introduces Solid Queue, Solid Cache, Solid Cable.
- Importmap-rails default in Rails 7+; jsbundling-rails (esbuild) common for richer JS.
- Propshaft replacing Sprockets for asset pipeline (Rails 8 default).
- Solid Queue replacing Sidekiq in some new projects (no Redis required).

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Ruby version, Rails version, DB, ActiveJob backend, JS pipeline, asset pipeline, test framework, auth gem, lint/style stack.

**Local Bootstrap:** `bin/setup` if present, `bundle install`, `bin/rails db:setup`, `bin/dev`, default port, health-check path.

**Architecture Map:** controllers/models/views file counts, concerns directories, service objects directory if present, jobs/mailers/channels.

**Conventions:** strong params usage, service object pattern, test framework, FactoryBot vs fixtures, queue backend.

**Risk Hotspots:** N+1 detection (bullet), callback patterns, Devise filter inheritance, Sidekiq vs pool sizing, Zeitwerk autoload boundaries.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Rails 5/6 patterns as current
- Skipping the JS pipeline detection - importmap vs jsbundling vs webpacker have different bootstrap commands
- Listing every gem in Gemfile - focus on the ones that change architecture
- Missing the master.key requirement for credentials
- Recommending Sprockets patterns when project uses Propshaft
- Ignoring Solid Queue/Cache/Cable in Rails 8 projects
