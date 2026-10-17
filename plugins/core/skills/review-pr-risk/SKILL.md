---
name: review-pr-risk
description: Score PR risk from diff signals: cross-module, schema, API, security, size, missing tests. Heuristic framing for code review.
metadata:
  category: review
  tags: [risk-assessment, pull-request, change-analysis]
user-invocable: false
---

# PR Risk Analysis

> Load `Use skill: stack-detect` first to determine the project stack (used to recognise file roles; its block is never emitted - this skill's output is the block below and nothing else).

## When to Use

- First step in any code review to frame scope and attention
- Triaging review priority across multiple PRs
- Deciding whether a PR needs extra reviewers, tests, or splitting

If no diff exists yet (architecture proposal, migration plan), use `review-change-risk` instead.

## Rules

- Heuristic, not a guarantee. Use as framing, not a gate.
- Run before line-by-line review, on `git diff <base>...<head>` (three dots: the changes since the merge base, so commits that landed on the base after the branch point fire nothing).
- When unsure whether a signal fired, count it as fired. This resolves ambiguous triggers (whether a generated file counts toward size, whether a helper module is a distinct domain), not the level itself - the ladder is deterministic once the signals are fixed, and a numeric threshold is read exactly (480 lines does not trigger `> 500`). Every signal is read from the diff; nothing outside it (author history, ticket context) fires one.

## Patterns

### Risk Signals

| Signal                         | Weight | Trigger                                                     |
| ------------------------------ | ------ | ----------------------------------------------------------- |
| Cross-module changes           | High   | 2+ distinct domain modules/packages - layers of one feature (model + service + controller) count as one; a feature is the set of files serving one user-facing capability, so a new worker, a new outbox, and a new endpoint for the same capability are still one |
| Shared state mutation          | High   | Global state, singletons, shared caches                     |
| Database/schema changes        | High   | Migrations, index changes, entity modifications; note `destructive` when a drop, rename, narrowing type change, or backfill hits an existing table |
| Public API changes             | High   | Endpoint signatures, request/response contracts             |
| Transaction boundary changes   | High   | New/modified transaction scope or isolation level           |
| Security-adjacent changes      | High   | Auth, authorization, input validation, crypto               |
| Async/event flow changes       | Medium | New publishers, listeners, message handlers                 |
| Config or feature flag changes | Medium | Application properties, environment config, CI/CD pipelines, flag default flips (code reading a flag is not one) |
| Dependency changes             | Medium | New libraries, version bumps in a manifest or lockfile (in-repo packages included), external service integrations |
| PR size (lines changed)        | Medium | > 500 added plus deleted lines across production files; a rename counts only its edited lines |
| Missing test changes           | Medium | A production change with no test file added or modified in the diff - counts per PR, not per path |

### Classification

Signals are counted over production files only - production means everything except tests, docs, and comments, so config, CI/CD, and infrastructure files count. A change confined to tests, docs, or comments fires no signal. Use the detected stack to recognize file roles - what counts as a migration, config, or test file in this ecosystem; with `Language: unknown`, recognize them by path and name (migrations: `migrations/`, `db/migrate/`; tests: `test/`, `tests/`, `spec/`, `__tests__/`, `test_*.*`, `*_test.*`, `*.test.*`, `*.spec.*`, `*_spec.*`; config and CI: `*.yml`, `*.yaml`, `*.toml`, environment files, `.github/workflows/`; a path matching a test pattern is a test file whatever its extension). Then apply top-down - first match wins. Same signals in, same level out.

- **Critical** - 2+ High signals, OR the Database/schema signal fired as `destructive` (a drop, rename, narrowing type change, or backfill against an existing table in a production file - a migration file that also creates new tables still counts)
- **High** - exactly one High signal
- **Medium** - 1+ Medium signals, no High signals
- **Low** - no signal fired (including a diff confined to tests, docs, or comments)

## Output Format

Callers parse the `Risk Level:` line. The block is `Risk Level:` and `Signals:`, plus `Action:` when a mapping fires, plus a leading `PR:` line only when triaging several PRs. Blank lines between fields.

```
PR: {identifier}                                    {only when triaging multiple PRs}

Risk Level: {Low | Medium | High | Critical}

Signals: {comma-separated, each fired signal once, in Risk Signals table order, as its Signal name plus a short cause in parentheses; the schema signal reads `Database/schema changes (destructive: <statement>)` when it escalated; or `none ({why nothing fired})` when nothing fired}

Action: {require additional reviewer | split PR | add tests before merge}    {omitted when no mapping fires}
```

`Action:` maps from what fired, first match wins: Critical level -> `require additional reviewer`; size signal -> `split PR`; missing-test signal -> `add tests before merge`; otherwise omit the line. A single-PR run omits the `PR:` line; a triage run emits one block per PR, ordered Critical first down to Low, more fired signals first within a level, remaining ties in input order - the order is the review queue.

### Example

```
Risk Level: Critical

Signals: Public API changes (POST /orders request schema), Security-adjacent changes (auth scope on the same endpoint)

Action: require additional reviewer
```

## Avoid

- Letting Low risk become an excuse to skip review
- Conflating risk level with code quality
