---
name: review-pr-risk
description: Score PR risk from diff signals: cross-module, schema, API, security, size, missing tests. Heuristic framing for code review.
metadata:
  category: review
  tags: [risk-assessment, pull-request, change-analysis]
user-invocable: false
---

# PR Risk Analysis

> Load `Use skill: stack-detect` first to determine the project stack (used to recognise file roles).

## When to Use

- First step in any code review to frame scope and attention
- Triaging review priority across multiple PRs
- Deciding whether a PR needs extra reviewers, tests, or splitting

If no diff exists yet (architecture proposal, migration plan), use `review-change-risk` instead.

## Rules

- Run before line-by-line review, on `git diff <base>...<head>` (three dots: changes since the merge base, so later base commits fire nothing); a pasted diff with no git metadata is read as-is - size counts the `+`/`-` lines inside `@@` hunks, not the `---`/`+++` header pair before each file's first hunk (a deleted SQL comment `-- x` reads `--- x` and counts), each file in full - its triage identifier the caller's label, else `PR <n>` by input position.
- When unsure whether a signal fired, count it as fired. This resolves ambiguous triggers (a generated file toward size, a helper module as a distinct domain), never the level - the ladder is deterministic once the signals are fixed, and a numeric threshold is read exactly (480 lines does not trigger `> 500`). Every signal is read from the diff; nothing outside it (author history, ticket context) fires one.

## Patterns

### Risk Signals

| Signal                         | Weight | Trigger                                                     |
| ------------------------------ | ------ | ----------------------------------------------------------- |
| Cross-module changes           | High   | 2+ distinct domain modules/packages - layers of one feature (model + service + controller) count as one; a feature is the set of files serving one user-facing capability, so a new worker, a new outbox, and a new endpoint for the same capability are still one; a separately versioned shared library and its consumer are two |
| Shared state mutation          | High   | A runtime write to state shared across requests or processes (a global or module-level variable, a singleton's fields, a shared cache or session store); a value set once at import or construction (a client timeout, a logger binding) is not one                     |
| Database/schema changes        | High   | Migrations, index changes, entity modifications; note `destructive` when a drop, rename, narrowing type change, backfill, or `NOT NULL` column without a default hits an existing table |
| Public API changes             | High   | Endpoint signatures, request/response contracts             |
| Transaction boundary changes   | High   | New/modified transaction scope or isolation level           |
| Security-adjacent changes      | High   | Auth, authorization, input validation, crypto, personal data handling (logging it included) |
| Async/event flow changes       | Medium | New publishers, listeners, message handlers                 |
| Config or feature flag changes | Medium | Application properties, environment config, CI/CD pipelines, infrastructure manifests (`Dockerfile`, `*.tf`, Helm charts, Kubernetes manifests), flag default flips (code reading a flag is not one; a constant in code is not config) |
| Dependency changes             | Medium | New libraries, version bumps in a manifest or lockfile (in-repo packages included), external service integrations |
| PR size (lines changed)        | Medium | > 500 added plus deleted lines across production files per `git diff --numstat` (binary `-	-` rows add none; a binary rename included; a rename row - `old => new`, or `dir/{old => new}` when the paths share a prefix or suffix, `R<score>` in `--name-status` - counts only its edited lines, pass `-M` when `diff.renames` is off, while a rename git does not detect shows as `D` + `A` rows and counts in full) |
| Missing test changes           | Medium | A production change beyond comment lines or a pure reformat, with no test file added or modified in the diff - counts per PR, not per path |

### Classification

Signals are counted over production files only - every file except tests and docs, so config, CI/CD, and infrastructure count. A change confined to tests or docs fires no signal; a change confined to comment lines or a pure reformat of production files (whitespace, import order, no token change) fires at most PR size, and only past `> 500`. Use the detected stack to recognize file roles; with `Language: unknown`, recognize them by path and name (migrations: `migrations/`, `db/migrate/`, `db/migration/`, `db/changelog/`, `alembic/versions/`; tests: a path segment `test/`, `tests/`, `spec/`, `__tests__/`, `*.Tests/` (case-insensitive) or a name `test_*.*`, `*_test.*`, `*.test.*`, `*.spec.*`, `*_spec.*`, `conftest.py`; docs: a path segment `docs/` or a name `*.md`, `*.rst`, `*.adoc` (a manifest such as `requirements.txt` is not a doc); config and CI: `*.yml`, `*.yaml`, `*.toml`, `*.properties`, `*.ini`, `*.conf`, environment files, `.github/workflows/` - a package manifest or lockfile (`pyproject.toml`, `Cargo.toml`, `pubspec.yaml`, `pnpm-lock.yaml`) fires Dependency changes for a dependency edit and Config for any other edit; a path matching a test pattern is a test file even under a migration directory, and any other path under a migration directory is a migration file, whatever its extension). Then apply top-down - first match wins.

- **Critical** - 2+ High signals, OR the Database/schema signal fired as `destructive` (per its table row, in a production file - a migration file that also creates new tables still counts)
- **High** - exactly one High signal
- **Medium** - 1+ Medium signals, no High signals
- **Low** - no signal fired (including a diff confined to tests or docs, or to comment lines or a pure reformat under the size threshold)

## Output Format

Callers parse the `Risk Level:` line. The block is `Risk Level:` and `Signals:`, plus `Action:` when a mapping fires, plus a leading `PR:` line only when triaging several PRs. Blank lines between fields.

```
PR: {identifier}                                    {only when triaging multiple PRs}

Risk Level: {Low | Medium | High | Critical}

Signals: {comma-separated, each fired signal once, in Risk Signals table order, as its Signal name plus a short cause in parentheses, the cause opening `unsure:` when the unsure rule fired it; the schema signal reads `Database/schema changes (destructive: <statement>)` when it escalated; or `none ({why nothing fired})` when nothing fired}

Action: {require additional reviewer | split PR | add tests before merge}    {omitted when no mapping fires}
```

`Action:` maps from what fired, first match wins: Critical level -> `require additional reviewer`; size signal -> `split PR`; missing-test signal -> `add tests before merge`; otherwise omit the line. A triage run emits one block per PR, ordered Critical first down to Low, more fired signals first within a level, remaining ties in input order - the order is the review queue.

## Avoid

- Conflating risk level with code quality
