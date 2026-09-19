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
- Severity mapping: Critical = security/data-loss exposure; High = active correctness bug or a set-but-not-applied flag tied to a reported symptom; Medium = latent footgun; Low = harmless redundancy; Informational = explicit setting matching the baseline; Divergent-by-design = a deliberate, documented departure needing no action.
- Evidence not provided (env files, models): state "not provided" in that section - never silently omit it.

## Patterns

### A. Versioned defaults baseline

`config.load_defaults <version>` in `config/application.rb` sets defaults cumulatively up to that version. Canonical table: [Versioned default values](https://guides.rubyonrails.org/configuring.html#versioned-default-values) (unpinned - the 8.0 block matters for apps on 8.0).

Attribute each flag to the block that actually introduced it. `active_job.enqueue_after_transaction_commit` and `config.yjit` are **7.2**; `load_defaults 8.0` adds exactly three - `active_support.to_time_preserves_timezone = :zone`, `action_dispatch.strict_freshness = true`, `Regexp.timeout`. So an app at `load_defaults 7.2` already has the first two and lacks only the 8.0 three. Later blocks (8.1 onward) keep accruing; read the version map for the Rails actually installed rather than assuming the newest block you know.

Enumerate only flags in effect for this project (`load_defaults` + explicit overrides in `config/application.rb` and `config/environments/*.rb`), not every framework flag. Apps pinned at 5.x/6.x usually do so deliberately because raising it touches every component at once - not a defect.

### B. Implicit per-model and per-controller behaviour

Hidden defaults invisible from the call site:

- **Association side effects on save**: `belongs_to ... touch:`, `accepts_nested_attributes_for` with assigned attributes, and callbacks reading `self.<association>` all force association loads during save. `has_many ... autosave:` does so only when the association is *already* instantiated - its callbacks read `association.target`, which is `[]` when unloaded, so it issues no query on its own. When multiple converge on one model, emit a synthesis line tying them to the observed symptom.
- **Missing `inverse_of:` under `load_defaults <= 6.1`**: `has_many_inversing` (6.1, unscoped) and `automatic_scope_inversing` (7.0, scoped) close this. Apps at 6.1 with scoped associations re-fetch the parent on traversal.
- **`default_scope`**: applied to every query through the model, including association loads. Invisible at the call site.
- **`serialize` without a coder**: the pre-7.1 default coder is YAML (an RCE vector on untrusted data); with `default_column_serializer = nil` (7.1) a coderless `serialize` raises at load.
- **`attr_readonly`**: pre-7.1 silently filters the column out of UPDATE; with `raise_on_assign_to_attr_readonly = true` (7.1) it raises `ActiveRecord::ReadonlyAttributeError` on assignment **to a persisted record**. Assignment on a new record stays legal - that is the point of `attr_readonly`, set-at-create.
- **`ApplicationController` `before_action` chain**: Devise, Pundit, and custom filters fire on every action unless skipped.
- **Autoloading (Zeitwerk)**: `autoload_paths` / `eager_load_paths` additions, `autoload_lib(ignore:)`, and anything under `lib/` decide which constants resolve and when. The failure is environment-shaped: with `eager_load = true` a missing path fails at boot - including in Sidekiq, which boots through `config/environment.rb` and so eager-loads exactly as the web tier does. Any process whose env leaves `eager_load = false` (development, test, rake tasks not covered by `rake_eager_load`) instead resolves lazily and raises `NameError` only on the first code path that needs the constant. Report the paths, and which processes eager-load.

### C. `new_framework_defaults_*.rb` initializer-timing footgun

The 7.x upgrade flow generates `config/initializers/new_framework_defaults_7_X.rb` with each flip commented out, to be enabled one at a time before bumping `load_defaults`.

**Three AR flags are silent no-ops when set in this initializer** because their values are copied out of `config.active_record` during boot, before `config/initializers` run - they are module-level `ActiveRecord.*` attributes, not `Base` class attributes that wait for `on_load`. Set them in `config/application.rb` (or eagerly inside `ActiveSupport.on_load(:active_record) { ... }`):

- `config.active_record.has_many_inversing` ([rails#45683](https://github.com/rails/rails/issues/45683))
- `config.active_record.automatic_scope_inversing` ([rails#46208](https://github.com/rails/rails/issues/46208))
- `config.active_record.run_after_transaction_callbacks_in_order_defined` ([rails#52098](https://github.com/rails/rails/issues/52098))

`config.active_support.cache_format_version` is a fourth: the `:initialize_cache` bootstrap builds `Rails.cache` before `config/initializers/*` runs, so setting it there is a silent no-op (the generated template's own comment says to set it in `config/application.rb`).

If the initializer exists and any of these four lines is uncommented there, report `Footgun: initializer-timing` regardless of stated intent. Other AR/AS flags work from the initializer; report `Footgun: none`.

### D. Environment-specific overrides

`config/environments/{development,test,production,staging}.rb` can flip behaviour per-env. Failure mode: a correctness- or security-affecting flag is set in one env in a way that hides bugs from another. Recurring examples:

- `strict_loading_by_default = true` in development/test only - N+1s raise for developers and pass silently in production (no `load_defaults` version turns this on, so `false` everywhere is the baseline, not a divergence)
- `active_job.queue_adapter = :async` in development masks the enqueue-inside-transaction race (the job runs before COMMIT) unless `active_job.enqueue_after_transaction_commit` is in effect (a 7.2 default - read its value rather than assuming), plus the Redis/JSON round-trip. It does *not* mask ActiveJob serialization errors - the async adapter serializes eagerly at enqueue
- `eager_load = true` in production only surfaces autoload bugs after deploy
- Worker processes are the third environment nobody writes down: Sidekiq loads the same `production.rb` but with its own concurrency, its own pool (`RAILS_MAX_THREADS` vs `concurrency` - `rails-connection-pool-sizing`), and (usually) `eager_load` behaviour set by the same flag - divergences between the web and worker tiers belong in this section even though there is no `config/environments/worker.rb`; cite the manifest or `sidekiq.yml` line as the `File:`

Report any env-only override that affects correctness, security, or production behaviour as `Footgun: env-only` in Findings - any framework's flag, not only AR/AJ (`raise_on_open_redirects`, `force_ssl`), when the audited files set it.

### E. Nice-to-have cherry-picks (Rails 6.1 onward)

Individual flips adoptable without bumping `load_defaults`; the 7.2 and 8.0 flags in Pattern A are cherry-picked the same way. **Never required; acceptance is per-project.** Most are framework defaults at the version in the `From` column - listing them here means the audited app's pinned `load_defaults` is below that version, so it does not have them yet. The one marked "manual opt-in" is never a default at any version.

| Cherry-pick | From (on by default at this load_defaults and above) | Consider if | Risk | Where |
| ----------- | ------------------------------------ | ----------- | ---- | ----- |
| `active_record.automatic_scope_inversing = true` | 7.0 | Hot serializers/decorators/child callbacks traverse scoped associations; APM shows redundant parent SELECTs | Low | `application.rb` (initializer-timing) |
| `active_record.raise_on_assign_to_attr_readonly = true` | 7.1 | Any `attr_readonly` declarations | Low | initializer |
| `active_record.run_after_transaction_callbacks_in_order_defined = true` | 7.1 | Multiple `after_commit` per model AND reverse-order has caused a bug, OR gems with their own `after_commit` chains. (Baseline pre-7.1 behavior: `after_commit` fires in *reverse* declaration order.) | Medium | `application.rb` (initializer-timing) |
| `active_record.partial_inserts = false` | 7.0 | Schema cleanup involving DB defaults, `ignored_columns` use, or Rails as sole source of truth for defaults | Low - audit `db/schema.rb`. Static column defaults are safe (Rails reads them into `column_defaults` and inserts them); the risk is *expression* defaults (`now()`, `gen_random_uuid()`) that Rails cannot evaluate and would insert as `NULL` | initializer |
| `active_record.default_column_serializer = nil` | 7.1 | Any `serialize` declarations without explicit coder; YAML deserialization is a known RCE vector | Medium | initializer |
| `active_support.cache_format_version = 7.1` | 7.1 | Cache size/hit rate matters AND a cold-cache rollout window is acceptable | Low | `application.rb` (initializer-timing - the `:initialize_cache` bootstrap builds `Rails.cache` before `config/initializers/*` runs, so setting it there is a silent no-op) |
| `action_dispatch.cookies_same_site_protection = :strict` | 6.1 sets `:lax`; `:strict` is never a default (manual opt-in) | Public app with no cross-site auth flows | Medium | env config |

**Surgical alternative to `automatic_scope_inversing`**: add explicit `inverse_of:` (both sides) to the specific scoped associations in hot loops. Zero risk, no `application.rb` change. Skip for polymorphic `belongs_to` and for `:through` (set on the source associations). Candidates: `rg -nP "has_(many|one)\s+:\w+,\s*->" app/models`.

Two matching rules: when a "Consider if" symptom matches a flag *already in effect*, the flag isn't the fix - route to the surgical alternative (or deeper diagnosis) instead. When an AND-condition is only half-evidenced, still list the Suggestion but name the unmet condition in `Consider if`.

## Output Format

When the request includes symptoms ("update fires N queries", "callbacks run out of order"), open with a Diagnosis section before Findings - one line per symptom naming the finding(s) that explain it. Every section appears in the report: an examined section with zero entries reads `none found`; an unexamined one reads `not provided` (Rules) - the two are never conflated. The synthesis line may span models when behaviours on several models converge on one symptom.

```
## Implicit Configuration Audit

Rails version: {from Gemfile.lock}

config.load_defaults: {version from config/application.rb:NN | none - the call is absent, pre-5.0 defaults apply}

Target load_defaults: {the upgrade target when the request names one - list the flags every block between the pinned version and the target adds | n/a}

## Diagnosis (only when symptoms were reported)

- Symptom: {as reported} -> {finding/behaviour entries that explain it | "not explained by implicit config" + the evidence that would settle it}

Every reported symptom gets a line, including the ones nothing here explains - an unexplained symptom is a result, and silently dropping it reads as "audited and clean". When the code path a symptom names was not provided, say so on that line rather than guessing at it.

## Findings (baseline state)

- Flag: {any config key - `config.active_record.X`, `config.active_job.X`, `config.autoload_paths`, ...}
  Source: {file:line OR "default at load_defaults <version>"}
  Current value: {effective value; append "textually <other>" when set-but-not-applied}
  Modern default: {value at the newest load_defaults the installed Rails offers - name that version}
  Severity: {Critical | High | Medium | Low | Informational | Divergent-by-design (deliberate, documented, no action)}
  Why it matters: {one sentence}
  Footgun: {none | initializer-timing | env-only | not provided (the initializer or env file is outside the evidence)}

An env-only flag is reported here with `Footgun: env-only`, and again in Environment Overrides with the per-env values - the two sections answer different questions and the duplication is intended.

## Implicit Per-Model / Per-Controller Behaviours

- Path: {app/models|app/controllers/<file>.rb:NN | config/application.rb:NN (autoload-path)}
  Behaviour: {touch | autosave | nested-attributes | default_scope | inverse_of-missing | callback-touches-association | validation-touches-association | attr_readonly | serialize-without-coder | before_action-chain | autoload-path}
  Effect: {one sentence}

`inverse_of-missing` is reported only where it still bites at the app's pinned `load_defaults`: `has_many_inversing` (6.1) closes it for unscoped associations, `automatic_scope_inversing` (7.0) for scoped ones.

When multiple behaviours on one model converge, append a synthesis line: "Behaviours X, Y, Z explain the N extra queries observed at <controller>#<action>."

## Environment Overrides

- File: {config/environments/<env>.rb:NN | config/sidekiq.yml:NN | deploy manifest:NN (worker-tier divergence)}
  Flag: {full path}
  Value: {value}
  Concern: {why this env-only flip matters}

## Suggestions (acceptance per-project)

Not defects, not defaults. Each entry stands alone; skipping is fine.

- Flag: {flag, or `inverse_of:` on <Model#association> for the surgical alternative}
  From version: {6.1 | 7.0 | 7.1 | 7.2 | 8.0 | manual opt-in (never a default)}
  Consider if: {condition}
  Risk: {Low | Medium | High}
  Where to set: {application.rb | initializer | env config | model}
  Rationale: {one sentence}
```

## Avoid

- Recommending `config.load_defaults <newer>` as a single change - never right for a mature app
- Enumerating every default in the canonical table
- Trusting an uncommented line in `new_framework_defaults_*.rb` without the initializer-timing check
- Confusing "update loads associations" with a `load_defaults` problem when the cause is `touch:` / `autosave:` / nested-attributes / a callback (see `rails-activerecord-patterns`)
