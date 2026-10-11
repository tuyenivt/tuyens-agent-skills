---
name: rails-implicit-config-audit
description: Audit hidden Rails configuration: load_defaults version map, new_framework_defaults footguns, implicit AR/AJ/Zeitwerk/callback behaviour.
metadata:
  category: backend
  tags: [ruby, rails, configuration, load_defaults, convention-over-configuration, audit]
user-invocable: false
---

> Load `Use skill: stack-detect` first to confirm Rails; the report reads the exact Rails version from `Gemfile.lock`, which stack-detect does not supply.

## When to Use

- Workflow needs the set of Rails defaults actually in effect
- Symptom looks like "magic": update spawns unexpected queries, callbacks fire out of order, assignments silently no-op
- Onboarding; before any Rails major-version upgrade

## Rules

- The declared `load_defaults` version is the contract the app was written against. Report state; never call 6.1 "wrong".
- Findings inventory the *current state*. Suggestions are optional cherry-picks from 6.1 onward (Pattern E). Keep them in separate output sections.
- Cite `file:line` on every Finding, Suggestion, and per-model/env entry.
- `Current value` is the *effective* value; when a flag is textually set but not applied (initializer-timing), state both.
- Severity mapping: Critical = security/data-loss exposure (`action_cable.disable_request_forgery_protection = true`, `use_yaml_unsafe_load = true`); High = active correctness bug or a set-but-not-applied flag tied to a reported symptom; Medium = latent footgun; Low = harmless redundancy; Informational = explicit setting matching the baseline; Divergent-by-design = a deliberate, documented departure needing no action. Findings are listed in that severity order.
- Evidence not provided (env files, models): state "not provided" in that section - never silently omit it.

## Patterns

### A. Versioned defaults baseline

`config.load_defaults <version>` in `config/application.rb` sets defaults cumulatively up to that version. Canonical table: [Versioned default values](https://guides.rubyonrails.org/configuring.html#versioned-default-values) (unpinned - the 8.0 block matters for apps on 8.0).

Attribute each flag to the block that actually introduced it. `active_job.enqueue_after_transaction_commit` and `config.yjit` are **7.2** (on 8.0 the app-wide enqueue setting gives way to a per-job class attribute); `load_defaults 8.0` adds exactly three - `active_support.to_time_preserves_timezone = :zone`, `action_dispatch.strict_freshness = true`, `Regexp.timeout`. So an app at `load_defaults 7.2` already has the first two and lacks only the 8.0 three. Later blocks (8.1 onward) keep accruing; read the version map for the Rails actually installed rather than assuming the newest block you know.

Enumerate only flags in effect for this project (`load_defaults` + explicit overrides in `config/application.rb`, `config/environments/*.rb` and `config/initializers/*.rb`, `new_framework_defaults_*.rb` included), not every framework flag. Apps pinned at 5.x/6.x usually do so deliberately because raising it touches every component at once - not a defect.

### B. Implicit per-model and per-controller behaviour

Hidden defaults invisible from the call site:

- **Association side effects on save**: `belongs_to ... touch:`, `accepts_nested_attributes_for` with assigned attributes, and callbacks reading `self.<association>` all force association loads during save. `has_many ... autosave:` does so only when the association is *already* instantiated - its callbacks read `association.target`, which is `[]` when unloaded, so it issues no query on its own. When several converge on one symptom (across models if need be), emit a synthesis line tying them to it.
- **Required `belongs_to` validation**: the presence check loads the parent on every save of the child; `belongs_to_required_validates_foreign_key = false` (7.1) checks it only when the foreign key is nil or changed - no parent SELECT on an unchanged key. An explicit `belongs_to_required_by_default = false` (often per environment) turns the requirement off whatever `load_defaults` says - an explicit `validates :parent, presence: true` then is the only check.
- **Missing `inverse_of:` on scoped associations**: simple unscoped pairs have inverted automatically since 4.1 at every `load_defaults` (custom options like `foreign_key:` can defeat detection); `automatic_scope_inversing` (7.0) closes the scoped gap, so apps below 7.0 re-fetch the parent when traversing a scoped association. `has_many_inversing` (6.1) is a different flag: assigning a `belongs_to` also adds the record to the inverse `has_many` target.
- **`default_scope`**: applied to every query through the model, including association loads. Invisible at the call site.
- **Callback side effects**: an `after_save` / `after_create` that enqueues, broadcasts or calls out runs inside the transaction and fires per row on every callback-running save path (`update_columns`, `update_all`, `insert_all`, `delete_all` skip it) - invisible at the call site.
- **`serialize` without a coder**: the pre-7.1 default coder is YAML, loaded with `safe_load` and `yaml_column_permitted_classes` since the CVE-2022-32224 fix - an RCE vector only with `use_yaml_unsafe_load = true`; with `default_column_serializer = nil` (7.1) a coderless `serialize` raises at load.
- **`attr_readonly`**: pre-7.1 silently filters the column out of UPDATE; with `raise_on_assign_to_attr_readonly = true` (7.1) it raises `ActiveRecord::ReadonlyAttributeError` on assignment **to a persisted record**. Assignment on a new record stays legal - that is the point of `attr_readonly`, set-at-create.
- **`ApplicationController` `before_action` chain**: Devise, Pundit, and custom filters fire on every action unless skipped.
- **Autoloading (Zeitwerk)**: `autoload_paths` / `eager_load_paths` additions, `autoload_lib(ignore:)`, and anything under `lib/` decide which constants resolve and when. The failure is environment-shaped: with `eager_load = true` a missing path fails at boot - including in Sidekiq, which boots through `config/environment.rb` and so eager-loads as the web tier does unless it runs under a different `RAILS_ENV`. Any process whose env leaves `eager_load = false` (development, test outside CI - the generated `test.rb` eager-loads when `ENV["CI"]` is set - and rake tasks not covered by `rake_eager_load`) instead resolves lazily and raises `NameError` only on the first code path that needs the constant. Report the paths, and which processes eager-load.

### C. `new_framework_defaults_*.rb` initializer-timing footgun

`rails app:update` generates `config/initializers/new_framework_defaults_<version>.rb` (versioned since 5.1, so `_6_1`, `_7_0` ... `_8_0`) with each flip commented out, to be enabled one at a time before bumping `load_defaults`.

**Three AR flags are silent no-ops when set in this initializer** - a load-order problem: their values are copied out of `config.active_record` when `ActiveRecord::Base` loads, and something usually loads it before `config/initializers` run (callback order is also fixed as each callback is declared). Set them in `config/application.rb`:

- `config.active_record.has_many_inversing` ([rails#45683](https://github.com/rails/rails/issues/45683))
- `config.active_record.automatic_scope_inversing` ([rails#46208](https://github.com/rails/rails/issues/46208))
- `config.active_record.run_after_transaction_callbacks_in_order_defined` ([rails#52098](https://github.com/rails/rails/issues/52098))

`config.active_support.cache_format_version` is a fourth: the `:initialize_cache` bootstrap builds `Rails.cache` before `config/initializers/*` runs, so setting it there is a silent no-op (the generated template's own comment says to set it in `config/application.rb`).

If the initializer exists and any of these four lines is uncommented there, report `Footgun: initializer-timing` regardless of stated intent. Other AR/AS flags work from the initializer; report `Footgun: none`.

### D. Environment-specific overrides

`config/environments/{development,test,production,staging}.rb` can flip behaviour per-env. Failure mode: a correctness- or security-affecting flag is set in one env in a way that hides bugs from another. Recurring examples:

- `strict_loading_by_default = true` in development/test only - every lazy association load raises for developers and passes silently in production (no `load_defaults` version turns this on, so `false` everywhere is the baseline, not a divergence)
- `active_job.queue_adapter = :inline` in development masks the enqueue-inside-transaction race - the job runs on the same thread and connection and sees the uncommitted rows; `:async` surfaces it only intermittently (its own thread and connection). Active Job `perform_later` / `deliver_later` can be deferred to commit by `enqueue_after_transaction_commit` (7.2+, set per job class - read the app's setting; `deliver_later` follows `ActionMailer::MailDeliveryJob`, which inherits `ActiveJob::Base`, not `ApplicationJob`); Sidekiq-native `perform_async` is not, unless the app enables `Sidekiq.transactional_push!` (6.5+; below Rails 7.2 it needs the `after_commit_everywhere` gem). `:async` does *not* mask ActiveJob serialization errors - it serializes eagerly at enqueue
- `eager_load = true` in production only surfaces autoload bugs after deploy
- Worker processes are the third environment nobody writes down: Sidekiq loads the same `production.rb` but with its own concurrency, its own pool (`RAILS_MAX_THREADS` vs `concurrency` - `rails-connection-pool-sizing`), and (usually) `eager_load` behaviour set by the same flag - divergences between the web and worker tiers belong in this section even though there is no `config/environments/worker.rb`; cite the manifest or `sidekiq.yml` line as the `File:`

Report any env-only override that affects correctness, security, or production behaviour as `Footgun: env-only` in Findings - any framework's flag, not only AR/AJ (`raise_on_open_redirects`, `force_ssl`), when the audited files set it.

### E. Nice-to-have cherry-picks (Rails 6.1 onward)

Individual flips adoptable without bumping `load_defaults`; the 7.2 and 8.0 flags in Pattern A are cherry-picked the same way, except that on 8.0+ enqueue-after-commit is set per job, not app-wide, and `Regexp.timeout` is a Ruby global, not a `config.` flag. **Never required; acceptance is per-project.** Most are framework defaults at the version in the `From` column - listing them here means the audited app's pinned `load_defaults` is below that version, so it does not have them yet. The one marked "manual opt-in" is never a default at any version.

| Cherry-pick | From (on by default at this load_defaults and above) | Consider if | Risk | Where |
| ----------- | ------------------------------------ | ----------- | ---- | ----- |
| `active_record.automatic_scope_inversing = true` | 7.0 | Hot serializers/decorators/child callbacks traverse scoped associations; APM shows redundant parent SELECTs | Low | `application.rb` (initializer-timing) |
| `active_record.raise_on_assign_to_attr_readonly = true` | 7.1 | Any `attr_readonly` declarations | Low | initializer |
| `active_record.run_after_transaction_callbacks_in_order_defined = true` | 7.1 | Multiple `after_commit` per model AND reverse-order has caused a bug, OR gems with their own `after_commit` chains. (Baseline pre-7.1 behavior: `after_commit` fires in *reverse* declaration order.) | Medium | `application.rb` (initializer-timing) |
| `active_record.partial_inserts = false` | 7.0 | Schema cleanup involving DB defaults, `ignored_columns` use, or Rails as sole source of truth for defaults | Low - Rails skips an unchanged column with a DB default *function* (`CURRENT_TIMESTAMP`, 8.0.13+ expression defaults such as `(uuid())`), so those keep their DB default; every other column is inserted from the cached `column_defaults`, so a static default changed in the DB while old processes still run (a rolling deploy) inserts the stale value | initializer |
| `active_record.belongs_to_required_validates_foreign_key = false` | 7.1 | Saves of a child with a required `belongs_to` show a parent SELECT | Low | initializer |
| `active_record.default_column_serializer = nil` | 7.1 | Any `serialize` declarations without explicit coder - an RCE vector only under `use_yaml_unsafe_load = true`, otherwise a load-time error once a coder is required | Medium | initializer |
| `active_support.cache_format_version = 7.1` | 7.1 | Cache size/hit rate matters AND a cold-cache rollout window is acceptable | Low | `application.rb` (initializer-timing - the `:initialize_cache` bootstrap builds `Rails.cache` before `config/initializers/*` runs, so setting it there is a silent no-op) |
| `action_dispatch.cookies_same_site_protection = :strict` | 6.1 sets `:lax`; `:strict` is never a default (manual opt-in) | Public app with no cross-site auth flows | Medium | env config |

**Surgical alternative to `automatic_scope_inversing`**: add explicit `inverse_of:` (both sides) to the specific scoped associations in hot loops. Low risk - the child's parent becomes the shared in-memory object, and a wrong name raises `InverseOfAssociationNotFoundError` - and no `application.rb` change. Skip for polymorphic `belongs_to` and for `:through` (set on the source associations). Candidates: `rg -nP "has_(many|one)\s+:\w+,\s*->" app/models`.

Two matching rules: when a "Consider if" symptom matches a flag *already in effect*, the flag isn't the fix - route to the surgical alternative (or deeper diagnosis) instead. When an AND-condition is only half-evidenced, still list the Suggestion but name the unmet condition in `Consider if`.

## Output Format

The report is the template below, sections in this order. Diagnosis exists only when the request reports symptoms ("update fires N queries", "callbacks run out of order"): one line per reported symptom, the ones nothing here explains included - an unexplained symptom is a result, and dropping it reads as "audited and clean"; a symptom whose code path was not provided says so on its line. Upgrade Delta exists only when the request names a target `load_defaults`. Every other section always appears: an examined section with zero entries reads `none found`, an unexamined one `not provided` (Rules) - never conflated. Each entry is a bullet with its fields as sub-bullets, so the fields render one per line. An env-only flag appears in Findings with `Footgun: env-only` and again in Environment Overrides with the per-env values - the sections answer different questions. `inverse_of-missing` is reported only where it still bites: scoped associations below 7.0, and at any version associations whose options (`foreign_key:`, `:through`) defeat automatic detection. Findings list flags in effect (set explicitly or by the pinned `load_defaults`); a newer block's flag the app lacks is a Suggestion, not a Finding. When several behaviours converge on one symptom, the Behaviours section ends with one synthesis line naming them and the symptom; it may span models, and names the controller action only when that code was provided.

```
## Implicit Configuration Audit

- Rails version: {from Gemfile.lock}
- config.load_defaults: {version from config/application.rb:NN | none - the call is absent, pre-5.0 defaults apply}
- Target load_defaults: {version the request names | n/a}

## Diagnosis {only when symptoms were reported}

- Symptom: {as reported} -> {finding/behaviour entries that explain it | not explained by implicit config - {the evidence that would settle it}}

## Upgrade Delta {only when a target is named}

1. {step in adoption order: a gem bump, then one flag per deploy (`new_framework_defaults_<version>.rb`, except the four Pattern C flags, which go in `config/application.rb`), then the `load_defaults` bump last} - {flag, the block that adds it, what to verify before the next step}

## Findings (baseline state)

- Flag: {any config key - `config.active_record.X`, `config.active_job.X`, `config.autoload_paths`, ...}
  - Source: {file:line | default at load_defaults <version> (config/application.rb:NN)}
  - Current value: {effective value}{; textually <other>}
  - Modern default: {value at the newest load_defaults the installed Rails offers, naming that version | n/a - not a load_defaults flag}
  - Severity: {Critical | High | Medium | Low | Informational | Divergent-by-design}
  - Why it matters: {one sentence}
  - Footgun: {none | initializer-timing | env-only | not provided}

## Implicit Per-Model / Per-Controller Behaviours

- Path: {app/models|app/controllers/<file>.rb:NN | config/application.rb:NN | config/environments/<env>.rb:NN | config/initializers/<file>.rb:NN}
  - Behaviour: {touch | autosave | nested-attributes | default_scope | inverse_of-missing | callback-touches-association | callback-side-effect | validation-touches-association | attr_readonly | serialize-without-coder | before_action-chain | autoload-path}
  - Effect: {one sentence}

Synthesis: {Behaviours X, Y, Z explain {symptom}{ at <controller>#<action>}} {only when several behaviours converge on one symptom}

## Environment Overrides

- File: {config/environments/<env>.rb:NN | config/sidekiq.yml:NN | deploy manifest:NN}
  - Flag: {full path}
  - Value: {value}
  - Concern: {why this env-only flip matters}

## Suggestions (acceptance per-project)

Not defects, not defaults. Each entry stands alone; skipping is fine.

- Flag: {flag, or `inverse_of:` on <Model#association> for the surgical alternative}
  - Source: {file:line the suggestion applies to}
  - From version: {6.1 | 7.0 | 7.1 | 7.2 | 8.0 | manual opt-in (never a default) | n/a - model change}
  - Consider if: {condition}
  - Risk: {Low | Medium | High}
  - Where to set: {application.rb | initializer | env config | model}
  - Rationale: {one sentence}
```

## Avoid

- Recommending `config.load_defaults <newer>` as a single change - never right for a mature app
- Enumerating every default in the canonical table
- Trusting an uncommented line in `new_framework_defaults_*.rb` without the initializer-timing check
- Confusing "update loads associations" with a `load_defaults` problem when the cause is `touch:` / `autosave:` / nested-attributes / a callback (see `rails-activerecord-patterns`)
