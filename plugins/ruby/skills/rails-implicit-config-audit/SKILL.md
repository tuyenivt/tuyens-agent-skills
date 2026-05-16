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

- A workflow needs to know which Rails defaults are actually in effect
- A symptom looks like "magical behaviour" - update spawns unexpected queries, callbacks fire in unexpected order, assignments silently no-op
- Onboarding a Rails codebase; before any Rails major-version upgrade

## Rules

- The project's declared `load_defaults` version is the contract the app was written against. Report state; do not call 6.1 wrong.
- Findings and Suggestions are separate output sections with different contracts. Findings inventory the *current state*. Suggestions are cherry-picks from 7.0+ that are *never required*.
- Cite source location (`file:line`) on every Finding, Suggestion, and per-model/env entry.

## Patterns

### A. Versioned defaults baseline

`config.load_defaults <version>` in `config/application.rb` sets defaults cumulatively up to the named version. For the full canonical table, see [Configuring Rails Applications - Versioned default values](https://guides.rubyonrails.org/v7.2/configuring.html#versioned-default-values). Read that table; report on what the project actually runs.

The audit's job: enumerate the flags currently in effect (from `load_defaults` and explicit overrides in `config/application.rb` and `config/environments/*.rb`), not every flag in the framework. Apps pinned at 5.x or 6.x typically keep `load_defaults` there because raising it touches every component at once - that's a deliberate engineering choice, not a defect.

### B. Implicit per-model and per-controller behaviour

These behave like hidden defaults to anyone reading an action body:

- **Association side effects on save**: `belongs_to ... touch:`, `has_many ... autosave:`, `accepts_nested_attributes_for`, callbacks reading `self.<association>`. Each causes association loads during save the controller never asked for. When multiple converge (touch + autosave + nested + callback on one model), report them together with a one-line synthesis tying them to the observed symptom.
- **Missing `inverse_of:` under `load_defaults <= 6.1`**: `has_many_inversing` was added in 6.1 (handles unscoped); `automatic_scope_inversing` was added in 7.0 (handles scoped). Apps on 6.1 with scoped associations re-fetch the parent on traversal.
- **`default_scope`**: applied to every query through the model, including association loads. Invisible from the action body.
- **`attr_readonly`**: pre-7.1, silently filters the column out of UPDATE. Post-7.1 with `raise_on_assign_to_attr_readonly = true`, raises on assignment.
- **`ApplicationController` `before_action` chain**: Devise, Pundit, custom middleware fire on every action unless explicitly skipped.

### C. `new_framework_defaults_*.rb` initializer-timing footgun

When Rails 7.x adds a new default, the upgrade flow generates `config/initializers/new_framework_defaults_7_X.rb` with each flip commented out. The intent: uncomment one at a time, ship, then eventually bump `load_defaults`.

**Three AR flags do not take effect when set in this initializer** because AR reads them at `on_load(:active_record)` time, before initializers run. Setting them there is a silent no-op. They must be set in `config/application.rb` (or eagerly inside `ActiveSupport.on_load(:active_record) { ... }`):

- `config.active_record.has_many_inversing` ([rails#45683](https://github.com/rails/rails/issues/45683))
- `config.active_record.automatic_scope_inversing` ([rails#46208](https://github.com/rails/rails/issues/46208))
- `config.active_record.run_after_transaction_callbacks_in_order_defined` ([rails#52098](https://github.com/rails/rails/issues/52098))

If `new_framework_defaults_7_X.rb` exists AND one of those three lines is uncommented in that file, report `Footgun: initializer-timing` regardless of what the team believes is enabled.

All other AR/AS flags (including `partial_inserts`, `raise_on_assign_to_attr_readonly`, `default_column_serializer`, `cache_format_version`) work correctly from the initializer. Report them with `Footgun: none`.

### D. Environment-specific overrides

`config/environments/{development,test,production,staging}.rb` can flip behaviour per-environment. The recurring failure mode: a security- or correctness-affecting flag is set in *one* env in a way that hides bugs from another. Common cases:

- `strict_loading_by_default = false` in development hides N+1s before prod
- `active_job.queue_adapter = :async` in development masks Sidekiq serialization bugs
- `eager_load = true` in production only surfaces autoload bugs after deploy

Report any env-only override of a flag that affects correctness, security, or production behaviour.

### E. Nice-to-have cherry-picks (Rails 7.0 - 7.2)

Individual flag flips that can be adopted without bumping `load_defaults`. **Not required, not defaults of any sort. Acceptance is per-project.** Offer only when the project's symptoms match the "Consider if" condition. Skipping any of them is a valid stance.

| Cherry-pick | From | Consider if | Risk | Where to set |
| ----------- | ---- | ----------- | ---- | ------------ |
| `active_record.automatic_scope_inversing = true` | 7.0 | Hot serializers / decorators / child callbacks traverse scoped associations and APM shows redundant parent SELECTs | Low | `application.rb` (initializer-timing) |
| `active_record.raise_on_assign_to_attr_readonly = true` | 7.1 | Any `attr_readonly` declarations exist | Low | initializer |
| `active_record.run_after_transaction_callbacks_in_order_defined = true` | 7.1 | Multiple `after_commit` per model AND reverse order has caused a bug, OR gems with their own `after_commit` chains | Medium | `application.rb` (initializer-timing) |
| `active_record.partial_inserts = false` | 7.0 | Planning schema cleanup that involves DB-side defaults, OR using `ignored_columns` to phase out columns, OR want Rails as sole source of truth for column defaults | Low - audit `db/schema.rb` first; DB defaults without a matching `attribute ... default:` would start inserting `NULL` | initializer |
| `active_record.default_column_serializer = nil` | 7.1 | Any `serialize` declarations without an explicit coder; YAML deserialization is a known RCE vector | Medium | initializer |
| `active_support.cache_format_version = 7.1` | 7.1 | Cache size or hit rate matters AND a cold-cache rollout window is acceptable | Low | initializer |
| `action_dispatch.cookies_same_site_protection = :strict` | manual | Public app with no cross-site auth flows | Medium | env config |

**Surgical alternative to `automatic_scope_inversing`**: instead of the global flag, add explicit `inverse_of:` to the specific scoped associations that show up in hot loops. Zero risk (naming exactly what the inverse is), no `application.rb` change. Declare it on both sides. Skip for polymorphic `belongs_to` (Rails can't use `inverse_of:` there) and for `:through` (set it on the source associations). Find candidates with `rg -nP "has_(many|one)\s+:\w+,\s*->" app/models`, cross-reference against serializer / view / decorator loops.

## Output Format

```
## Implicit Configuration Audit

Rails version: {from Gemfile.lock}
config.load_defaults: {version from config/application.rb:NN}

## Findings (baseline state)

- Flag: {config.active_record.X}
  Source: {file:line OR "default at load_defaults <version>"}
  Current value: {value}
  Modern default: {value at Rails 7.2}
  Severity: {Critical | High | Medium | Low | Informational}
  Why it matters: {one sentence}
  Footgun: {none | initializer-timing | env-only}

## Implicit Per-Model / Per-Controller Behaviours

- Path: {app/models/<file>.rb:NN}
  Behaviour: {touch | autosave | nested-attributes | default_scope | inverse_of-missing | callback-touches-association | attr_readonly}
  Effect: {one sentence}

When multiple behaviours on one model converge, append a synthesis line: "Behaviours X, Y, Z explain the N extra queries observed at <controller>#<action>."

## Environment Overrides

- File: {config/environments/<env>.rb:NN}
  Flag: {full path}
  Value: {value}
  Concern: {why this env-only flip matters}

## Suggestions (nice-to-have, acceptance per-project)

Not defects. Not recommended by default. Each entry stands on its own; skipping is fine.

- Flag: {flag}
  From version: {7.0 | 7.1 | 7.2}
  Consider if: {condition}
  Risk: {Low | Medium | High}
  Where to set: {application.rb | initializer | env config}
  Rationale: {one sentence}
```

## Avoid

- Recommending `config.load_defaults <newer>` as a single change - never the right answer for a mature app
- Enumerating every default in the canonical table; report only what the project actually runs or overrides
- Trusting a flag is enabled because it's uncommented in `new_framework_defaults_*.rb` without checking the initializer-timing list
- Confusing "update loads associations" with a `load_defaults` problem when the cause is `touch:` / `autosave:` / nested-attributes / a callback (cross-reference `rails-activerecord-patterns`)
