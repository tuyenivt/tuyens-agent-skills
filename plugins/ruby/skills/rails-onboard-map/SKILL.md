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

Project has `Gemfile` + `config/application.rb` and the host workflow needs Rails-specific orientation.

## Rules

- Ruby version from `.ruby-version` (fallback `Gemfile`); Rails from `Gemfile.lock` (lock is authoritative). No lockfile: fall back to the `Gemfile` constraint, say which source you used, and note that the resolved version is unverified.
- Database from `config/database.yml` `adapter:` (or `DATABASE_URL`). PG -> route to `rails-postgresql-migration-safety`; MySQL/MariaDB -> `rails-migration-safety`. When neither is in evidence, report it as not in evidence with that check and defer the routing - the two migration skills are mutually exclusive ("load that instead, never both"), so guessing sends the reader to the wrong one. Multiple databases declared (primary + queue/cache/replica) get named individually.
- ActiveJob backend from `config.active_job.queue_adapter`. `:async` (default) is in-memory and unsafe in production. When a queue gem is installed but no adapter is configured, report the contradiction and the verification step (jobs may include `Sidekiq::Job` directly, bypassing ActiveJob).
- `config.api_only = true`: report "none (API-only)" for asset/JS/views sections instead of omitting them; serving falls back to `bin/rails server` when `bin/dev` is absent.
- Asset pipeline: Propshaft (default for new apps since Rails 8.0; an opt-in gem on 7.x) or Sprockets (the default on 7.0-7.2). JS handling: importmap (Rails 7+ default), jsbundling-rails, cssbundling-rails. These are independent axes.
- A declared-but-absent component is a contradiction worth reporting, not a blank: RSpec in the Gemfile with no `spec/`, a queue gem with no jobs, `api_only` with no controllers. Report the declaration, the absence, and the check that settles it.
- Missing `config/master.key` (or `RAILS_MASTER_KEY`) blocks boot whenever `credentials.yml.enc` is read.
- The advice baseline is Rails 7.2+; older apps are reported as-is - the version gap is context (and a hotspot when `load_defaults` lags the installed version), never a defect list.
- Signals the Output Format requires but the evidence doesn't show (lint stack, auth gem): report "not in evidence" plus the check to run - never guess.

## Patterns

### Key files

| Location                                                | Purpose                                                  |
| ------------------------------------------------------- | -------------------------------------------------------- |
| `Gemfile` / `Gemfile.lock`                              | Gems + `ruby "x.y.z"`; lock authoritative                |
| `.ruby-version`                                         | Ruby pin                                                 |
| `bin/rails` / `bin/setup` / `bin/dev`                   | CLI; setup script; Foreman runner (reads `Procfile.dev`) |
| `config/application.rb`                                 | App-wide config (autoload, timezone, ActiveJob, `load_defaults`) |
| `config/environments/`, `config/initializers/`          | Per-env config; boot-time setup (alphabetical)           |
| `config/routes.rb`                                      | Routes                                                   |
| `config/database.yml` / `cable.yml` / `storage.yml`     | DB / ActionCable / ActiveStorage backends                |
| `config/credentials.yml.enc` + `master.key`             | Encrypted credentials; missing key blocks boot           |
| `db/schema.rb` or `db/structure.sql`, `db/migrate/`     | Schema, migrations. `structure.sql` = SQL-format dump (DB features `:ruby` can't express); needs the DB client installed for `db:schema:load` |
| `app/{controllers,models,views,jobs,mailers,channels}/` | Stereotype directories                                   |
| `app/javascript/`, `lib/`                               | JS entrypoint; non-Rails code                            |

### Bootstrap path

1. Toolchain (rbenv/asdf/chruby) from `.ruby-version`
2. `bundle install`; if `package.json` present, install with the manager the lockfile names (`yarn.lock` -> yarn, `package-lock.json` -> npm, `pnpm-lock.yaml` -> pnpm, `bun.lock` / `bun.lockb` -> bun)
3. `bin/setup` or `bin/rails db:create db:migrate db:seed`
4. Local services from `compose.yml`, `compose.yaml` or `docker-compose.yml` (DB, Redis, MailCatcher)
5. Run `bin/dev` (7+) or `bin/rails server`
6. Verify `http://localhost:3000`; health `/up` **only when `config/routes.rb` declares it** - the 7.1 generator writes that route for new apps only, so an upgraded app 404s. Otherwise use the closest route you can verify

No compose file under any of those names and no documented service setup ("ask Dave for the dump"): flag the bootstrap gap explicitly as a first-week risk - don't paper over it with generic steps.

### Package layout

- **Layer-package (default)**: `app/{controllers,models,services,jobs}/` grouped by stereotype.
- **Domain-package**: `app/domains/<context>/` or `app/packs/`; often paired with [Packwerk](https://github.com/Shopify/packwerk) (`package.yml` per pack).
- **Mixed**: domain packs alongside legacy `app/services/`. New code in pack; legacy stays.

### Risk hotspots

Rows keyed on a gem/config signal appear only when the evidence shows it; code-smell rows (`permit!`, `update_column(s)`, callback abuse) are grep checks - include them with the grep to run when no code evidence was provided.

| Area                            | Signal                                                                        | Follow-up skill                    |
| ------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------- |
| N+1 queries                     | `bullet` in Gemfile; `includes` missing in collection views                   | `rails-activerecord-patterns`      |
| Implicit config                 | `load_defaults` < installed Rails version; `new_framework_defaults_*.rb`; `touch:`/`autosave:` | `rails-implicit-config-audit` |
| Unmaintained gems               | EOL/abandoned gems (paperclip, etc.) - migrate before touching their domain   | (gem-specific)                     |
| Packwerk boundaries             | `package.yml` packs - check `bin/packwerk check` runs in CI                   | -                                  |
| Callback abuse                  | Heavy `after_save` business logic                                             | -                                  |
| `update_columns` / `update_all` | Bypass callbacks/validations                                                  | -                                  |
| `permit!`                       | Mass assignment escape hatch in controllers                                   | `rails-security-patterns`          |
| Connection pool                 | Sidekiq concurrency vs DB `max_connections`                                   | `rails-connection-pool-sizing`     |
| MySQL `REPEATABLE READ`         | Long transactions, gap locks                                                  | `rails-db-locking-patterns`        |
| Worker memory                   | jemalloc / `MALLOC_ARENA_MAX=2` / WorkerKiller                                | `rails-batch-processing-patterns`  |
| Zeitwerk / `master.key`         | Constant-loading bugs at boot; missing key blocks boot                        | -                                  |

### First-PR safe zones

Safe: new RESTful route + controller + view; new field with safe-default migration; new spec; new rake task.
Riskier: initializers (run once at boot); existing migrations (never edit - add new); shared concerns; Devise/Warden config.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Ruby, Rails, DB, ActiveJob backend, JS pipeline, asset pipeline, test framework (RSpec/Minitest), authentication (Devise, JWT, `has_secure_password`, an app-local scheme, or none in evidence - name what is there rather than forcing one of two gems), authorization (Pundit/CanCanCan/none), lint stack (RuboCop/Standardrb).

**Local Bootstrap:** `bin/setup` (or `bundle install` + `bin/rails db:setup`); `bin/dev`; default port; health path if one is routed; `master.key` requirement.

**Architecture Map:** controller/model/view counts; concerns; services; jobs/mailers/channels; package layout (layer / domain / mixed).

**Conventions:** strong params; service-object pattern; serializer layer (Blueprinter/jbuilder/AMS); test framework + factories; queue backend (Sidekiq/Solid Queue/GoodJob).

**Risk Hotspots:** two kinds, both required. Gem- and config-signal rows appear only when the evidence shows them. Code-smell rows (`permit!`, `update_column(s)`, callback abuse) always appear, each carrying the grep to run, because absence of evidence is not evidence here. A hotspot you actually observed that matches no listed row still gets a row - name it and cite `file:line`. Cross-reference follow-up skills.

**First-PR Safe Zones:** scoped to observed structure - if a listed zone doesn't exist in this app (no `app/controllers/` in an API-only service, no `spec/`), name a zone that does rather than proposing one that doesn't.

Scope: default to the whole app. When the reader is joining to own one area, say so in a `Scope:` line under the title and order every section with that area first, marking the rest "context only" - the sections themselves do not change.

## Avoid

- Treating Rails 5/6 patterns as current; baseline is 7.2+.
- Skipping JS pipeline detection or conflating it with the asset pipeline.
- Listing every gem - focus on architecture-changing ones.
- Recommending Sprockets when project uses Propshaft.
- Reporting `:async` ActiveJob adapter as production-suitable.
