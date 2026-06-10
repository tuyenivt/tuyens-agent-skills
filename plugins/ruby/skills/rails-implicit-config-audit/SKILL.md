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

- Workflow needs the set of Rails defaults actually in effect
- Symptom looks like "magic": update spawns unexpected queries, callbacks fire out of order, assignments silently no-op
- Onboarding; before any Rails major-version upgrade

## Rules

- The declared `load_defaults` version is the contract the app was written against. Report state; never call 6.1 "wrong".
- Findings inventory the *current state*. Suggestions are optional cherry-picks from 7.0+. Keep them in separate output sections.
- Cite `file:line` on every Finding, Suggestion, and per-model/env entry.
- `Current value` is the *effective* value; when a flag is textually set but not applied (initializer-timing), state both.
- Severity mapping: Critical = security/data-loss exposure; High = active correctness bug or a set-but-not-applied flag tied to a reported symptom; Medium = latent footgun; Low = harmless redundancy; Informational = explicit setting matching the baseline.
- Evidence not provided (env files, models): state "not provided" in that section - never silently omit it.

## Patterns

### A. Versioned defaults baseline

`config.load_defaults <version>` in `config/application.rb` sets defaults cumulatively up to that version. Canonical table: [Versioned default values](https://guides.rubyonrails.org/v7.2/configuring.html#versioned-default-values).

Enumerate only flags in effect for this project (`load_defaults` + explicit overrides in `config/application.rb` and `config/environments/*.rb`), not every framework flag. Apps pinned at 5.x/6.x usually do so deliberately because raising it touches every component at once - not a defect.

### B. Implicit per-model and per-controller behaviour

Hidden defaults invisible from the call site:

- **Association side effects on save**: `belongs_to ... touch:`, `has_many ... autosave:`, `accepts_nested_attributes_for`, callbacks reading `self.<association>`. Each forces association loads during save. When multiple converge on one model, emit a synthesis line tying them to the observed symptom.
- **Missing `inverse_of:` under `load_defaults <= 6.1`**: `has_many_inversing` (6.1, unscoped) and `automatic_scope_inversing` (7.0, scoped) close this. Apps at 6.1 with scoped associations re-fetch the parent on traversal.
- **`default_scope`**: applied to every query through the model, including association loads. Invisible at the call site.
- **`attr_readonly`**: pre-7.1 silently filters the column out of UPDATE; with `raise_on_assign_to_attr_readonly = true` (7.1) it raises on assignment.
- **`ApplicationController` `before_action` chain**: Devise, Pundit, and custom filters fire on every action unless skipped.

### C. `new_framework_defaults_*.rb` initializer-timing footgun

The 7.x upgrade flow generates `config/initializers/new_framework_defaults_7_X.rb` with each flip commented out, to be enabled one at a time before bumping `load_defaults`.

**Three AR flags are silent no-ops when set in this initializer** because AR reads them at `on_load(:active_record)` time, before initializers run. Set them in `config/application.rb` (or eagerly inside `ActiveSupport.on_load(:active_record) { ... }`):

- `config.active_record.has_many_inversing` ([rails#45683](https://github.com/rails/rails/issues/45683))
- `config.active_record.automatic_scope_inversing` ([rails#46208](https://github.com/rails/rails/issues/46208))
- `config.active_record.run_after_transaction_callbacks_in_order_defined` ([rails#52098](https://github.com/rails/rails/issues/52098))

If the initializer exists and any of these three lines is uncommented there, report `Footgun: initializer-timing` regardless of stated intent. All other AR/AS flags work from the initializer; report `Footgun: none`.

### D. Environment-specific overrides

`config/environments/{development,test,production,staging}.rb` can flip behaviour per-env. Failure mode: a correctness- or security-affecting flag is set in one env in a way that hides bugs from another. Recurring examples:

- `strict_loading_by_default = false` in development hides N+1s before prod
- `active_job.queue_adapter = :async` in development masks Sidekiq serialization bugs
- `eager_load = true` in production only surfaces autoload bugs after deploy

Report any env-only override that affects correctness, security, or production behaviour as `Footgun: env-only` in Findings.

### E. Nice-to-have cherry-picks (Rails 7.0 - 7.2)

Individual flips adoptable without bumping `load_defaults`. **Never required, never defaults; acceptance is per-project.** Offer only when symptoms match "Consider if".

| Cherry-pick | From | Consider if | Risk | Where |
| ----------- | ---- | ----------- | ---- | ----- |
| `active_record.automatic_scope_inversing = true` | 7.0 | Hot serializers/decorators/child callbacks traverse scoped associations; APM shows redundant parent SELECTs | Low | `application.rb` (initializer-timing) |
| `active_record.raise_on_assign_to_attr_readonly = true` | 7.1 | Any `attr_readonly` declarations | Low | initializer |
| `active_record.run_after_transaction_callbacks_in_order_defined = true` | 7.1 | Multiple `after_commit` per model AND reverse-order has caused a bug, OR gems with their own `after_commit` chains. (Baseline pre-7.1 behavior: `after_commit` fires in *reverse* declaration order.) | Medium | `application.rb` (initializer-timing) |
| `active_record.partial_inserts = false` | 7.0 | Schema cleanup involving DB defaults, `ignored_columns` use, or Rails as sole source of truth for defaults | Low - audit `db/schema.rb`; DB defaults without matching `attribute ... default:` would insert `NULL` | initializer |
| `active_record.default_column_serializer = nil` | 7.1 | Any `serialize` declarations without explicit coder; YAML deserialization is a known RCE vector | Medium | initializer |
| `active_support.cache_format_version = 7.1` | 7.1 | Cache size/hit rate matters AND a cold-cache rollout window is acceptable | Low | initializer |
| `action_dispatch.cookies_same_site_protection = :strict` | 7.0 (manual opt-in) | Public app with no cross-site auth flows | Medium | env config |

**Surgical alternative to `automatic_scope_inversing`**: add explicit `inverse_of:` (both sides) to the specific scoped associations in hot loops. Zero risk, no `application.rb` change. Skip for polymorphic `belongs_to` and for `:through` (set on the source associations). Candidates: `rg -nP "has_(many|one)\s+:\w+,\s*->" app/models`.

Two matching rules: when a "Consider if" symptom matches a flag *already in effect*, the flag isn't the fix - route to the surgical alternative (or deeper diagnosis) instead. When an AND-condition is only half-evidenced, still list the Suggestion but name the unmet condition in `Consider if`.

## Output Format

When the request includes symptoms ("update fires N queries", "callbacks run out of order"), open with a Diagnosis section before Findings - one line per symptom naming the finding(s) that explain it. The synthesis line may span models when behaviours on several models converge on one symptom.

```
## Implicit Configuration Audit

Rails version: {from Gemfile.lock}
config.load_defaults: {version from config/application.rb:NN}

## Diagnosis (only when symptoms were reported)

- Symptom: {as reported} -> {finding/behaviour entries that explain it}

## Findings (baseline state)

- Flag: {config.active_record.X}
  Source: {file:line OR "default at load_defaults <version>"}
  Current value: {effective value; append "textually <other>" when set-but-not-applied}
  Modern default: {value at Rails 7.2}
  Severity: {Critical | High | Medium | Low | Informational}
  Why it matters: {one sentence}
  Footgun: {none | initializer-timing | env-only}

## Implicit Per-Model / Per-Controller Behaviours

- Path: {app/models/<file>.rb:NN}
  Behaviour: {touch | autosave | nested-attributes | default_scope | inverse_of-missing | callback-touches-association | attr_readonly | serialize-without-coder}
  Effect: {one sentence}

When multiple behaviours on one model converge, append a synthesis line: "Behaviours X, Y, Z explain the N extra queries observed at <controller>#<action>."

## Environment Overrides

- File: {config/environments/<env>.rb:NN}
  Flag: {full path}
  Value: {value}
  Concern: {why this env-only flip matters}

## Suggestions (acceptance per-project)

Not defects, not defaults. Each entry stands alone; skipping is fine.

- Flag: {flag}
  From version: {7.0 | 7.1 | 7.2}
  Consider if: {condition}
  Risk: {Low | Medium | High}
  Where to set: {application.rb | initializer | env config}
  Rationale: {one sentence}
```

## Avoid

- Recommending `config.load_defaults <newer>` as a single change - never right for a mature app
- Enumerating every default in the canonical table
- Trusting an uncommented line in `new_framework_defaults_*.rb` without the initializer-timing check
- Confusing "update loads associations" with a `load_defaults` problem when the cause is `touch:` / `autosave:` / nested-attributes / a callback (see `rails-activerecord-patterns`)
