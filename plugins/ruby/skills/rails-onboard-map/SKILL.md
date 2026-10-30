---
name: rails-onboard-map
description: Rails onboarding signals: Gemfile, Rails version, env configs, AR migrations, ActiveJob, ActionCable, asset pipeline.
metadata:
  category: backend
  tags: [onboarding, codebase-map, rails, ruby, bundler]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-onboard` when the detected stack is Rails.

## When to Use

Project has `Gemfile` + `config/application.rb` and the host workflow needs Rails-specific orientation.

## Rules

- Ruby version from `.ruby-version` (or `.tool-versions` / `mise.toml` - asdf and mise read those first), else `Gemfile.lock`'s `RUBY VERSION` (exact; Bundler writes it when the Gemfile declares `ruby`), else the Gemfile `ruby` line (`ruby "3.4.1"`, `ruby file: ".ruby-version"`, or a constraint - say so); none of them -> `not pinned` in a whole app (an observation, not the missing-signal sentinel); `not in evidence` in a declared slice, plus the check. Rails from `Gemfile.lock` (lock is authoritative). No lockfile: fall back to the `Gemfile` constraint, say which source you used, and note that the resolved version is unverified.
- Database from `config/database.yml` `adapter:` (`mysql2` or `trilogy`; or `DATABASE_URL`), with the server version when declared; migration work routes to `rails-migration-safety`. Multiple databases declared (primary + queue/cache/cable/replica) get named individually.
- ActiveJob backend from `config.active_job.queue_adapter` in `config/application.rb`, every `config/environments/*.rb` and `config/initializers/*.rb` (`Rails.application.config.active_job.queue_adapter =` / `ActiveJob::Base.queue_adapter =`), plus any per-class `self.queue_adapter` in `app/jobs/` - Rails 8 sets `:solid_queue` only in `production.rb`; a value set only in `application.rb` applies to every environment - reported per environment. `:async` (the default) is in-memory and unsafe in production. When a queue gem is installed but none of those sources configures it, report the contradiction and the verification step. Jobs that include `Sidekiq::Job` directly bypass the adapter - state that as a fact, not a contradiction.
- `config.api_only = true`: report "none (API-only)" for asset/JS/views sections instead of omitting them.
- Asset pipeline: Propshaft (default for new apps since Rails 8.0; an opt-in gem on 7.x) or Sprockets (the default on 7.0-7.2). JS: importmap (Rails 7+ default), jsbundling-rails, or in upgraded apps Shakapacker / vite_ruby; CSS: tailwindcss-rails, dartsass-rails, cssbundling-rails, or the asset pipeline. These are independent axes.
- A declared-but-absent component is a contradiction worth reporting, not a blank: RSpec in the Gemfile with no `spec/`, a queue gem with no jobs, `api_only` with no controllers, docs naming infrastructure the config lacks. Report the declaration, the absence, and the check that settles it.
- Credentials: without `config/master.key` (or `RAILS_MASTER_KEY`) credential reads return nil; boot fails only under `config.require_master_key = true`, a `fetch` / bang read, or production's `secret_key_base`. Per-environment keys live in `config/credentials/<env>.key`.
- The advice baseline is Rails 8.1+; older apps are reported as-is - the version gap is context (and a hotspot when `load_defaults` lags the installed version), never a defect list.
- Missing signals use one sentinel pair. The tree given is the whole app unless the request says it is a slice. In a whole app, a signal that should be present and isn't is `absent`, plus the check that confirms it; in a declared slice it is `not in evidence`, plus the check to run. Never guess. A tree declared whole that lacks core Rails files (`bin/`, `config/environments/`, `config/routes.rb`, a referenced class) stays whole: each gap is `absent`, and the set of them is one Contradictions line.

## Patterns

### Key files

| Location                                                | Purpose                                                  |
| ------------------------------------------------------- | -------------------------------------------------------- |
| `Gemfile` / `Gemfile.lock`                              | Gems + `ruby "x.y.z"`; lock authoritative                |
| `.ruby-version`                                         | Ruby pin                                                 |
| `bin/rails` / `bin/setup` / `bin/dev`                   | CLI; setup script; dev server - the generated 8.1 `bin/dev` execs `bin/rails server`; a jsbundling / cssbundling / dartsass / tailwind installer replaces it with foreman + `Procfile.dev` |
| `config/application.rb`                                 | App-wide config (autoload, timezone, ActiveJob, `load_defaults`) |
| `config/environments/`, `config/initializers/`          | Per-env config; boot-time setup (alphabetical)           |
| `config/routes.rb`                                      | Routes                                                   |
| `config/database.yml` / `cable.yml` / `storage.yml`     | DB / ActionCable / ActiveStorage backends                |
| `config/credentials.yml.enc` + `master.key`             | Encrypted credentials (per-env: `config/credentials/<env>.*`) |
| `db/schema.rb` or `db/structure.sql`, `db/migrate/`     | Schema, migrations. `structure.sql` = SQL-format dump (DB features `:ruby` can't express); needs the DB client installed for `db:schema:load` |

### Bootstrap path

1. Toolchain (rbenv/chruby from `.ruby-version`; asdf/mise from `.tool-versions` or `mise.toml`)
2. Local services first - the database must be up before setup creates it: `compose.yml`, `compose.yaml`, `docker-compose.yml`, `docker-compose.yaml` or `.devcontainer/compose.yaml` (DB, Redis, MailCatcher)
3. `bundle install`; if `package.json` present, install with the manager the lockfile names (`yarn.lock` -> yarn, `package-lock.json` -> npm, `pnpm-lock.yaml` -> pnpm, `bun.lock` / `bun.lockb` -> bun)
4. `bin/setup` - an 8.0+ generated one execs `bin/dev` at the end unless passed `--skip-server`; read the script - or `bin/rails db:prepare` (`bundle exec rails db:prepare` with no `bin/`; tests then run as `bundle exec rspec`, or `bundle exec rails test` on Minitest)
5. Run `bin/dev` when present, else `bin/rails server`; with no `bin/` at all, `bundle exec rails server`
6. Verify `http://localhost:3000` (or the `port` in `config/puma.rb` / `PORT`); health `/up` **only when `config/routes.rb` declares it** - the 7.1 generator writes that route for new apps only, so an upgraded app 404s. Otherwise use the closest route you can verify

No compose file under any of those names and no documented service setup ("ask Dave for the dump"): flag the bootstrap gap explicitly as a first-week risk - don't paper over it with generic steps.

### Package layout

- **Layer-package (default)**: `app/{controllers,models,services,jobs}/` by stereotype.
- **Domain-package**: `app/domains/<context>/`, `app/packs/` or root-level `packs/<name>/`, often with Packwerk (`package.yml` per pack).
- **Mixed**: domain packs beside legacy `app/services/` - new code in a pack, legacy stays.

### Risk hotspots

Rows keyed on a gem/config signal appear only when the evidence shows it; code-smell rows (`permit!`, `update_column(s)` / `update_all`, callback abuse) always appear with the grep to run - a grep that ran and found nothing is a row marked `no observed hit`; a grep not run is a row marked `not assessed: <grep>` (injected: on `Not assessed:`) with the command.

| Area                            | Signal                                                                        | Follow-up skill                    |
| ------------------------------- | ----------------------------------------------------------------------------- | ---------------------------------- |
| N+1 queries                     | `bullet` in Gemfile; `includes` missing in collection views                   | `rails-activerecord-patterns`      |
| Implicit config                 | `load_defaults` < installed Rails version; `new_framework_defaults_*.rb`; `touch:`/`autosave:` | `rails-implicit-config-audit` |
| Unmaintained gems               | EOL/abandoned gems (paperclip, etc.) - migrate before touching their domain   | (gem-specific)                     |
| Packwerk boundaries             | `package.yml` packs - check `bin/packwerk check` runs in CI                   | -                                  |
| Callback abuse                  | Heavy `after_save` business logic - grep below                                | `rails-transaction-patterns`       |
| `update_columns` / `update_all` | Bypass callbacks/validations - grep below                                     | -                                  |
| `permit!`                       | Mass assignment escape hatch in controllers - grep below                      | `rails-security-patterns`          |
| Connection pool                 | A process's threads (Sidekiq concurrency) above its `database.yml` `max_connections` (`pool` before 8.1), or Solid Queue `threads` above the queue database's `max_connections` minus 2; the fleet total vs the MySQL server's `max_connections` variable | `rails-connection-pool-sizing` |
| ActionCable                     | `async` adapter in production `cable.yml`; `disable_request_forgery_protection` | `rails-actioncable-patterns`     |
| Locking                         | MySQL `REPEATABLE READ` long transactions and gap locks; advisory locks; Redis locks guarding DB writes | `rails-db-locking-patterns` |
| Worker memory                   | jemalloc / `MALLOC_ARENA_MAX=2` / WorkerKiller                                | `rails-batch-processing-patterns`  |
| Zeitwerk / credentials          | Constant-loading bugs at boot; a missing key under `require_master_key`       | -                                  |

The code-smell greps, carried verbatim into their rows:

```bash
rg -n 'after_(save|create|update|commit)' app/models
rg -nw 'update_columns?|update_all' app lib
rg -n 'permit!|to_unsafe_h' app/controllers
```

### First-PR safe zones

Safe: new RESTful route + controller + view; new field with safe-default migration; new spec; new rake task.

Avoid for a first PR: initializers (run once at boot); existing migrations (never edit - add new); shared concerns; Devise/Warden config.

## Output Format

Inject into `task-onboard`'s report, which owns the section order and envelope: Stack and Tooling -> `## Stack` (extra rows), Contradictions -> `## Common Pitfalls` "Docs that contradict the code" (a config-vs-config contradiction too), Local Bootstrap -> `## Local Quickstart`, Architecture Map -> `## Architecture`, Conventions -> `## Key Patterns and Conventions`, Risk Hotspots -> `## Tech Debt and Risk Hotspots` (an observed hit is a finding at its `file:line`; a code-smell grep that ran with no hit is a `no observed hit: <grep>` item there; a grep not run goes on that section's `Not assessed:` line with the command), First-PR Safe Zones and Avoid for First PR -> those subsections (up to 3 each). Invoked standalone, the eight area names below are `##` headings in this order, each a bullet list except Risk Hotspots, which is a table.

- **Stack and Tooling:** Ruby, Rails, DB (with the migration-safety skill it routes to), ActiveJob backend per environment, ActionCable adapter (production `cable.yml`), Active Storage service (or none), JS pipeline, asset pipeline, test framework (RSpec/Minitest), authentication (Devise, JWT, `has_secure_password`, an app-local scheme, `absent`, or `not in evidence` - name what is there rather than forcing one of two gems), authorization (Pundit, CanCanCan, Action Policy, an app-local check, `absent`, or `not in evidence`), lint stack (RuboCop/Standardrb), deploy target (Kamal `config/deploy.yml`, a Kubernetes manifest, `absent`, or `not in evidence`). Authentication lists every scheme present with where each is used (Devise for web sessions, JWT for the API) - several are often deliberate. Any value the evidence lacks takes the Rules' sentinel plus its check.
- **Contradictions:** one line each - a declared-but-absent component, a queue gem no environment configures, infrastructure declared in docs but absent from config, code that references a table, column or class the schema or tree lacks (code-vs-schema drift) - with the check that settles it. `none` when the evidence is consistent (standalone only; injected, the Common Pitfalls bullet is omitted). A Rails version read from the Gemfile without a lock is marked on the version value, not here. A defect inside scoped code (a signature check done wrong, a committed secret, a gem used but undeclared) is not a contradiction: it is a Risk Hotspots row. A contradiction that is also a hotspot (a `redis` cable adapter in production `cable.yml` with no Redis in compose or docs) is filed once, here; the hotspot row points to it. Two schedulers for one task (`config/schedule.yml` and a CronJob manifest) are a config-vs-config contradiction, filed here.
- **Local Bootstrap:** the Bootstrap path steps as they apply here - local services (the compose file, or `first-week risk: undocumented service setup`), setup command, run command (plus the worker command when the queue backend runs its own process: `bundle exec sidekiq`, `bin/jobs` - `bundle exec rake solid_queue:start` with no `bin/`), test command (`bundle exec rspec` / `bin/rails test`), default port, health path if one is routed, credentials key requirement.
- **Architecture Map:** controller/model/view counts (concrete classes; the `Application*` base classes and `Current` are not counted); concerns; services; jobs/mailers/channels, with the scheduler and its config file (sidekiq-cron `config/schedule.yml`, Solid Queue `recurring.yml`, a CronJob manifest); package layout (layer / domain / mixed). An `app/` tree that is absent is reported as such, with `config/routes.rb` as the only map.
- **Conventions:** strong params; service-object pattern; serializer layer (Blueprinter/jbuilder/AMS); factories / fixtures and spec layout.
- **Risk Hotspots:** two kinds, both required. Gem- and config-signal rows appear only when the evidence shows them. Code-smell rows (`permit!`, `update_column(s)` / `update_all`, callback abuse) always appear, each carrying its grep from the block above, because absence of evidence is not evidence here - `no observed hit` when the grep ran empty, `not assessed: <grep>` when it did not run (the injected form moves that to `Not assessed:`). A hotspot you actually observed that matches no listed row still gets a row - name it and cite `file:line`; its follow-up skill is the sibling that owns the concern (jobs: `rails-sidekiq-patterns`, or `rails-solid-stack-patterns` for Solid Queue / Cache / Cable config, rescue: `rails-exception-handling`, auth or a committed secret: `rails-security-patterns`, transactions: `rails-transaction-patterns`, idempotency or service shape: `rails-service-objects`, uploads or a storage move: `rails-active-storage-patterns`, suite health - flaky specs, a slow profile, factories: `rails-testing-patterns`) or `-`. Standalone, this section is a table with the Patterns table's three columns plus a Location column (`file:line`; the file alone for an absent setting; `no observed hit` or `not assessed: <grep>` for the greps), rows ordered by blast radius within the scope-first ordering (by blast radius alone when no `Scope:` line was given): an observed hit before `no observed hit` before `not assessed`, then a signal every request or job crosses (config, a base class, the pool) before a single file, ties in the Patterns table's row order.
- **First-PR Safe Zones:** up to 3, from the Patterns list, scoped to observed structure - if a listed zone doesn't exist in this app (no `app/views/` in an API-only service, no `spec/`), name a zone that does rather than proposing one that doesn't.
- **Avoid for First PR:** up to 3, from the Patterns list, scoped the same way.

Scope: default to the whole app. When the reader is joining to own one area, name it in task-onboard's `**Scope focus:**` header (standalone: a `Scope:` line first) and order every section with that area first (the Risk Hotspots table: scoped rows in blast-radius order, then the context-only rows in the same order), marking the rest "context only" - the sections themselves do not change, and every slot is still filled; a section with nothing scoped says so in one line. Greps stay app-wide.

## Avoid

- Skipping JS pipeline detection or conflating it with the asset pipeline.
- Listing every gem - focus on architecture-changing ones.
