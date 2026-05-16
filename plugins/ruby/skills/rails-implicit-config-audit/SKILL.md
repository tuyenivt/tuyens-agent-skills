---
name: rails-implicit-config-audit
description: Audit hidden Rails configuration: load_defaults version map, new_framework_defaults footguns, implicit AR/AJ/Zeitwerk/callback behaviour.
metadata:
  category: backend
  tags: [ruby, rails, configuration, load_defaults, convention-over-configuration, audit]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- A workflow needs to know which Rails defaults are actually in effect (`config.load_defaults`, per-component overrides, env-specific flips)
- A symptom looks like "magical behaviour" - update spawns unexpected queries, callbacks fire in unexpected order, assignments silently no-op, deploys break after a column drop
- Onboarding a Rails codebase and you want an inventory of convention-over-configuration knobs the project depends on
- Before any Rails major-version upgrade

## Rules

- The project is **correctly configured at its declared `load_defaults` version**. Audit reports the *state*, it does not declare 6.1 wrong.
- Two output sections, never mixed:
  - **Findings** = baseline state inventory (covers 5.0 -> 6.1 era). These are facts about what the app is running with.
  - **Suggestions** = curated cherry-picks from 7.0 -> 7.2. Always tagged `nice-to-have, acceptance per-project`. Never promoted to findings or required fixes.
- Cite source location for every claim: `config/application.rb:NN`, `config/initializers/new_framework_defaults_X_Y.rb:NN`, `config/environments/<env>.rb:NN`, or model/controller path.
- When `new_framework_defaults_*.rb` is present, check both whether flags are uncommented AND whether each flag is one of the known *initializer-timing-affected* flags (see Patterns).
- Never recommend bumping `load_defaults` itself. Recommend individual cherry-picks instead.

## Patterns

### A. Versioned defaults baseline (Rails 6.1 cap)

`config.load_defaults 6.1` is the realistic baseline this skill audits. Apps that started on 5.x or 6.x typically keep `load_defaults` pinned because raising it touches every component at once. 5.0-6.0 flips (Zeitwerk autoloader, per-form CSRF, authenticated cookie encryption, etc.) are inherited and assumed in effect; they predate any meaningful audit decision and the project would not boot correctly without them.

Read `config/application.rb` for the `config.load_defaults <version>` line. That single call sets all defaults cumulatively up to the named version. Then read every `config.active_record.*`, `config.active_job.*`, `config.action_controller.*`, `config.active_support.*` line in `config/application.rb` and `config/environments/*.rb` - these are explicit overrides on top of the baseline.

Key 6.1 defaults the audit reports on:

| Flag | Default at 6.1 | Why it matters |
| ---- | -------------- | -------------- |
| `config.active_record.has_many_inversing` | `true` | Rails infers `inverse_of` automatically for `has_many`. Without it, `parent.children.first.parent` reloads. Connects directly to "update spawns extra queries" symptoms. |
| `config.active_record.legacy_connection_handling` | `false` | Modern role-based connection handling (required for multi-DB). |
| `config.active_storage.track_variants` | `true` | Variants persisted instead of recomputed. |
| `config.action_dispatch.cookies_same_site_protection` | `:lax` | SameSite=Lax default on cookies. |
| `config.active_support.cache_format_version` | `7.0` (in 6.1) | Marshal-based compact cache entries. |
| `config.active_support.hash_digest_class` | `OpenSSL::Digest::SHA1` | SHA1 for cache keys, etag, etc. (Raised to SHA256 in 7.0 - listed as a cherry-pick.) |

For the canonical full table including ActionMailer, ActionCable, ActiveJob, and ActiveStorage flips at every version, see [Configuring Rails Applications - Versioned default values](https://guides.rubyonrails.org/v7.2/configuring.html#versioned-default-values).

### B. Implicit per-model and per-controller behaviour

`load_defaults` is not the only source of invisible behaviour. These are configured per-model/per-controller and behave like hidden defaults to anyone reading the action body:

- **`belongs_to :x, touch: true`** - saving the child bumps the parent's `updated_at`. If `autosave: true` is also set on the inverse, the parent is *loaded* during the child's save to be touched. Common cause of "update on a model loads a seemingly unrelated association".
- **`has_many :children, autosave: true`** (or implicit via `accepts_nested_attributes_for :children`) - parent save iterates and saves children, triggering association load.
- **`accepts_nested_attributes_for`** - param-driven, loads the association even if the params don't include nested attributes (Rails reads to compare).
- **`inverse_of:`** - explicit `inverse_of` on associations lets Rails reuse in-memory objects across traversal. When missing AND `has_many_inversing` / `automatic_scope_inversing` is off, traversals re-query.
- **`default_scope`** - applies on every query through the model, including association loads. Hidden from controller/action code.
- **`attr_readonly`** - silently ignores assignments after create (prior to Rails 7.1) or raises (7.1+ if `raise_on_assign_to_attr_readonly` is on). Pure invisibility.
- **Callbacks that touch associations**: `before_save`, `before_validation`, `after_commit` that reference `self.association` cause loads at save time.
- **`ApplicationController` `before_action` chain**: Devise's `authenticate_user!`, Pundit's `verify_authorized` / `verify_policy_scoped`, custom audit middleware - all fire on every action unless explicitly skipped.

When multiple behaviours converge on a single symptom (e.g., an `update` action shows queries for several associations), report them together with an explicit *synthesis*: "behaviours X, Y, Z explain the N extra queries observed at <location>". Listing them in isolation forces the reader to do the assembly; the audit's job is to do it for them.

### C. `new_framework_defaults_*.rb` initializer-timing footgun

When Rails 7.x adds a new default, the upgrade flow creates `config/initializers/new_framework_defaults_7_X.rb` with the flips commented out. Uncomment them one at a time, ship, then eventually bump `load_defaults`.

**Several flags do not take effect when set in this initializer**, because the code that reads them runs at `on_load(:active_record)` time, *before* initializers. Setting them in the initializer is a silent no-op. They must be set in `config/application.rb` (or eagerly inside the initializer with `ActiveSupport.on_load(:active_record) { ... }`).

Known affected flags (audit must check):

- `config.active_record.has_many_inversing` ([rails#45683](https://github.com/rails/rails/issues/45683))
- `config.active_record.automatic_scope_inversing` ([rails#46208](https://github.com/rails/rails/issues/46208))
- `config.active_record.run_after_transaction_callbacks_in_order_defined` ([rails#52098](https://github.com/rails/rails/issues/52098))

Detection: if `new_framework_defaults_7_X.rb` exists AND one of these lines is uncommented in that file (not in `application.rb`), flag as `Footgun: initializer-timing` even if the team believes it is enabled.

**Flags NOT affected by the initializer-timing footgun** (safe to set in `new_framework_defaults_*.rb`): `partial_inserts`, `raise_on_assign_to_attr_readonly`, `default_column_serializer`, `cache_format_version`. When these appear uncommented in the initializer, report them as active with `Footgun: none`. The audit should make this distinction explicit so reviewers don't have to deduce it from absence.

### D. Environment-specific overrides

`config/environments/{development,test,production,staging}.rb` can flip behaviour per-environment. Common surprises:

- `config.eager_load = true` in production only - autoload bugs surface in prod, not dev
- `config.active_record.strict_loading_by_default = true` in development only - hides N+1s that ship to prod silently
- `config.active_job.queue_adapter = :async` (default) in development - jobs run in-process, masking serialization bugs
- `config.cache_classes` vs `config.enable_reloading` vs `config.eager_load` matrix per env
- `config.active_record.dump_schema_after_migration` flipped off in CI

Audit reports any env where a security- or correctness-affecting flag is overridden.

### E. Nice-to-have suggestions from Rails 7.0 - 7.2

These are **not** required and **not** evidence the project is misconfigured. They are individually cherry-pickable via `config.active_record.<flag> = ...` or equivalent, without bumping `load_defaults`. Offer only when the project's symptoms match the "consider if" condition. If a project skips them all, that is a valid stance.

| Cherry-pick | From | Consider if | Skip if | Risk | Where to set |
| ----------- | ---- | ----------- | ------- | ---- | ------------ |
| `config.active_record.automatic_scope_inversing = true` | 7.0 | Hot endpoints traverse scoped associations and APM shows redundant queries on update/save paths | No scoped associations OR low traffic | Low | `application.rb` (initializer timing footgun) |
| `config.active_record.raise_on_assign_to_attr_readonly = true` | 7.1 | You use `attr_readonly` and want silent persistence drops to fail loudly | No `attr_readonly` declarations | Low (only raises on already-broken code paths) | initializer is fine |
| `config.active_record.run_after_transaction_callbacks_in_order_defined = true` | 7.1 | Multiple `after_commit` callbacks per model and order has caused bugs | Single `after_commit` per model OR order has been audited | Medium (changes execution order of existing chains) | `application.rb` (initializer timing footgun) |
| `config.active_record.partial_inserts = false` | 7.0 | Planning to remove a column with a DB-side default | No imminent column drops | Low | initializer is fine |
| `config.active_record.default_column_serializer = nil` | 7.1 | You use `serialize` and want to force explicit serializer choice; YAML deserialization is a known RCE vector with untrusted input | All `serialize` calls already pass an explicit coder | Medium (audit `serialize` declarations first) | initializer is fine |
| `config.active_support.cache_format_version = 7.1` | 7.1 | Cache hit rate matters and you can tolerate a cold cache window during rollout | Hot path depends on the cache being warm at all times | Low | initializer is fine |
| `config.action_dispatch.cookies_same_site_protection = :strict` | n/a (manual hardening) | Public-facing app with no cross-site auth flows | App relies on cross-site cookies | Medium | env config |

Each suggestion is offered with risk + condition. Do not list them as defects.

## Output Format

```
## Implicit Configuration Audit

Rails version: {version from Gemfile.lock}
config.load_defaults: {version from config/application.rb:NN}

## Findings (baseline state)

Each finding describes a fact about how the app is currently configured. Findings are not defects unless paired with an explicit Severity.

- Flag: {full path, e.g., config.active_record.has_many_inversing}
  Source: {file:line OR "default at load_defaults <version>"}
  Current value: {value}
  Modern default: {value at Rails 7.2}
  Severity: {Critical | High | Medium | Low | Informational}
  Why it matters: {one sentence}
  Footgun: {none | initializer-timing | env-only | other}

## Implicit Per-Model / Per-Controller Behaviours

- Path: {app/models/<file>.rb:NN}
  Behaviour: {autosave | touch | nested-attributes | default_scope | inverse_of-missing | callback-touches-association | attr_readonly}
  Effect: {one sentence describing what runs invisibly}

## Environment Overrides

- File: {config/environments/<env>.rb:NN}
  Flag: {full path}
  Value: {value}
  Concern: {why this env-only flip is worth knowing}

## Suggestions (nice-to-have, acceptance per-project)

Note: these are individual flag flips from Rails 7.0-7.2, offered only when their value is clearly higher than the migration cost. They are NOT required, NOT recommended by default, and acceptance is per-project. Skip without justification is fine.

- Flag: {flag}
  From version: {7.0 | 7.1 | 7.2}
  Consider if: {project-specific condition}
  Skip if: {project-specific condition}
  Risk: {Low | Medium | High}
  Where to set: {application.rb | initializer | env config}
  Rationale: {one sentence}
```

## Avoid

- Presenting Suggestions as required fixes or as evidence the project is misconfigured
- Recommending `config.load_defaults <newer-version>` as a single change - never the right answer for a mature app
- Listing every default in the versioned table - report only what is actually in effect or overridden in this project
- Marking 6.1 baseline behaviour as a defect (it is the contract the app was written against)
- Trusting that a flag is enabled because it is uncommented in `new_framework_defaults_*.rb` - verify against the initializer-timing footgun list
- Confusing the symptom "update loads an association" with a `load_defaults` problem when the cause is `touch:` / `autosave:` / `accepts_nested_attributes_for` / a callback (cross-reference `rails-activerecord-patterns`)
