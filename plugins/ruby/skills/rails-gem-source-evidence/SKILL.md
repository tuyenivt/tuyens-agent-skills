---
name: rails-gem-source-evidence
description: Settle gem and Rails behaviour claims from installed source - bundle info path, locked version, load_defaults; cite file:line or mark unverified.
metadata:
  category: backend
  tags: [ruby, rails, gems, bundler, evidence, verification]
user-invocable: false
---

## When to Use

- A finding, fix or design rests on what a gem or Rails itself does: a default timeout, a retry rule, a callback order, a version-gated default
- Two sources disagree about framework behaviour (a guide, a changelog, a knowledge-base rule, another reviewer)
- Triage of behaviour that changed across a gem or Rails upgrade

## Rules

- The installed source at the locked version is the evidence. Guides, changelogs, upgrade notes and recall are leads to the line to read, never the citation.
- Read the version the app runs: the `Gemfile.lock` entry, inside the app's own bundle.
- A version-gated default follows `config.load_defaults`, not the installed Rails version - an app on the 8.1 gem with `load_defaults 6.1` runs 6.1 defaults.
- One probe, then the ladder.
- A claim the ladder cannot settle is published as unverified, never asserted, never dropped.

## Patterns

### Locate the source

```bash
grep -n "^    <gem> (" Gemfile.lock                 # the locked version
bundle info <gem> --path                           # its directory in the app's bundle
grep -rn --include='*.rb' "<method or option>" "$(bundle info <gem> --path)"   # the gem root: engines keep code under app/ too
```

Rails is several gems - probe the one that owns the behaviour (`activerecord`, `actionpack`, `activejob`, `activesupport`, `railties`), not `rails`. When the app's bundle lives in a running container, run the probe there (`docker compose exec <service> bundle info <gem> --path`); the host may hold other versions.

### Evidence ladder

| Rung | Source |
| ---- | ------ |
| 1 | The installed gem, at the path the probe printed - a directory with no `lib/` there (empty, or executables only) is a default gem at Ruby's own version: read `RbConfig::CONFIG["rubylibdir"]` |
| 2 | The gem's upstream repository, or a checkout of it, at the locked version's tag, when the probe fails and the tag is reachable |
| 3 | Neither readable - the claim stays unverified |

A claim that something is absent (no default, no retry) cites the definition that would hold it - the options struct, the `load_defaults` method - and says no line assigns it.

### Version-gated defaults

The values each `load_defaults` version sets are one method in the installed `railties`: `lib/rails/application/configuration.rb`, `load_defaults`, one `when` branch per version. Read three things, in order, before stating a default:

1. `config.load_defaults <version>` in `config/application.rb` - the branches up to that version apply
2. Explicit overrides in `config/application.rb`, `config/environments/*.rb` and `config/initializers/*.rb`, `new_framework_defaults_*.rb` included (`rails-implicit-config-audit` owns which of those take effect)
3. The gem's own fallback when no branch and no override sets the key

```
# Bad - recalled, and true only at load_defaults 7.1+
"after_commit callbacks run in the order they are defined"

# Good - the branch read, then the app's pin
Gem claim: after_commit callbacks run in the order they are defined - does not hold

Gem evidence: railties <locked version> - lib/rails/application/configuration.rb:<line> - `active_record.run_after_transaction_callbacks_in_order_defined = true` - set only in the "7.1" branch

Gem evidence: config/application.rb:<line> - `config.load_defaults 6.1` - the "7.1" branch never runs for this app

Gem evidence: activerecord <locked version> - lib/active_record.rb:<line> - `self.run_after_transaction_callbacks_in_order_defined = false` - the fallback; no file under config/ assigns the key, so the callbacks run in reverse order
```

## Output Format

One block per claim - a statement that bundles separable claims gets a block for each: the verdict, then one evidence line per line read. A claim that rests on two gems carries a line for each, the app's own pin or override carries an app-file line, and a part left unread carries the rung 3 line. The verdict states only what the lines read establish. A construct spanning several lines cites its range (`:335-342`) and quotes the deciding line. A review passes the block to its verify step, and a claim with any unread part publishes with `_(unverified: gem source not read - <reason>)_`; a build or triage places it beside the decision it supports.

```
Gem claim: {the claim as stated} - {holds | does not hold | holds in part - <the part that holds; the rest does not hold or is unread> | unverified}

Gem evidence: {<gem> <locked version> - <path in gem>:<line or range> - `<quoted line>` - <what it shows> | <gem> <locked version> - upstream tag <tag> - <path>:<line or range> - `<quoted line>` - <what it shows> | <app file>:<line or range> - `<quoted line>` - <what it shows> | unverified: gem source not read - <reason>}
```

## Avoid

- Hunting through `vendor/bundle`, `~/.gem` or `gem env` paths by trial and error instead of the one probe
- Starting a container or installing a bundle to make the probe work
- Reading a neighbouring version because it is easier to find - it settles nothing
