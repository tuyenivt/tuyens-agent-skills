---
name: eval-test-runner
description: Run the project's test suite via stack-detected command; parse pass/fail/coverage/timeout into a structured SDD eval record.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, testing, test-runner]
user-invocable: false
---

# Eval - Test Runner

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

Composed by `task-spec-evaluate` to produce one measurement of the test suite. One invocation, one data point.

## Rules

- Command comes from the selection table or an explicit `test_command` override; never guess from filenames.
- Read-only: no installs, no source/config/lockfile edits, no service startup.
- `timeout` is its own status; do not retry to filter flakes.
- Counts come from the runner's machine-readable output (XML/JSON) when available, else stdout parsing.
- When `notes` records a truncation or fallback, use the literal tokens `truncated`, `no-tests-collected`, `parser-fallback`, `missing-dependency` so downstream skills key off them.

## Inputs

| Field             | Default                            | Notes                                                         |
| ----------------- | ---------------------------------- | ------------------------------------------------------------- |
| `test_command`    | from selection table               | Override wins; override also disables slow-stack escalation   |
| `timeout_seconds` | 300 (slow stacks 900; hard cap 1800)| -                                                            |
| `test_filter`     | none                               | Pass-through to runner (`-k`, `--match`, `--testNamePattern`) |

**Slow-stack signal** (set `timeout_seconds: 900` unless overridden): `pom.xml`/`build.gradle*` lists `testcontainers`; `karma.conf.*` or `playwright.config.*` exists; Django settings reference a non-SQLite default DB and tests are not run with `--keepdb`.

## Test Command Selection

Read `stack-detect.Test framework` first; fall back to file signals below.

| Stack signal                  | Command                                                  |
| ----------------------------- | -------------------------------------------------------- |
| Java + Maven                  | `./mvnw -B test`                                         |
| Java/Kotlin + Gradle          | `./gradlew --no-daemon test`                             |
| .NET                          | `dotnet test --logger trx`                               |
| Python + pytest               | `pytest -ra --tb=short --no-header`                      |
| Python + Django               | `python manage.py test --verbosity=2`                    |
| Node + npm                    | `npm test`                                               |
| Node + pnpm                   | `pnpm test`                                              |
| Node + yarn                   | `yarn test`                                              |
| Go                            | `go test ./... -json`                                    |
| Rust                          | `cargo test --no-fail-fast`                              |
| PHP + Laravel                 | `php artisan test`                                       |
| Ruby + RSpec                  | `bundle exec rspec`                                      |
| Ruby + Minitest               | `bin/rails test`                                         |
| Frontend + Vitest             | `vitest run --reporter=json`                             |
| Frontend + Jest               | `jest --json`                                            |
| Frontend + Angular/Karma      | `ng test --watch=false --browsers=ChromeHeadless`        |

Playwright/Cypress e2e: skip unless caller passes `test_command`. No match and no override -> `status: no-runner-detected`.

**Ruby disambiguation**: prefer RSpec when `Gemfile.lock` (or, if absent, `Gemfile`) declares `rspec-rails`; else Minitest. When both gems are declared, prefer the runner whose `*_spec.rb` / `*_test.rb` files are more recently modified; record choice in `notes`.

**Windows/Git Bash**: shell wrappers (`./mvnw`, `./gradlew`, `bin/rails`) run via Git Bash. If only `.cmd`/`.bat` variants ship, classify as `error` (binary missing) - never substitute. Use `python` if on PATH, else fall back to `py`; record in `notes`.

## Counts and Coverage Sources

- Java/Maven: `target/surefire-reports/TEST-*.xml`; coverage from `target/site/jacoco/jacoco.xml`.
- Gradle: `build/test-results/test/*.xml`; coverage from `build/reports/jacoco/test/jacocoTestReport.xml`.
- .NET: trx under `TestResults/`; coverage from `coverage.cobertura.xml` if `--collect:"XPlat Code Coverage"` set by override.
- pytest: stdout summary line; coverage from `.coverage` only if `pytest-cov` invoked by override. `N deselected` counts as `skipped` when `test_filter` is set.
- Go `-json`: count only events where `Test` is set AND `Action in {pass, fail, skip}`. Package-level events (no `Test`) are ignored. Coverage requires `-coverprofile` override.
- JSON reporters (Vitest, Jest): `numTotalTests`, `numFailedTests`, `coverageMap` if present.

If the runner emits no coverage data, `coverage: null` (never `0`).

## `failures[].file` Derivation

First that resolves wins:
1. File path from runner report (XML/JSON `file` or `location`).
2. Source path from a fully-qualified class name (`com.acme.UserService` -> `src/main/java/com/acme/UserService.java`; also `src/main/kotlin/...`; multi-module Gradle `*/src/main/java/...`) if the file exists.
3. For Python: prefer runner-reported `file:line`; do not derive from module names.
4. Otherwise omit the field.

## Status Semantics

| Status               | Trigger                                                                       |
| -------------------- | ----------------------------------------------------------------------------- |
| `pass`               | Exit 0 and zero failures/errors with >=1 test collected                       |
| `no-tests-collected` | Exit 0 and runner reports 0 collected; `notes` MUST include `no-tests-collected` |
| `fail`               | Non-zero exit or any failure/error reported                                   |
| `timeout`            | Wall clock exceeded `timeout_seconds`                                         |
| `no-runner-detected` | No table match and no override                                                |
| `error`              | Runner could not be invoked (binary missing, services unavailable, OOM)       |

Tests needing services (DB, Redis, Docker) that fail to connect: `error` with `missing-dependency` in `notes`.

## Output Format

```yaml
test_run:
  command: <full command line>
  cwd: <working directory>
  status: pass | no-tests-collected | fail | timeout | no-runner-detected | error
  exit_code: <int or null>
  duration_seconds: <float>
  counts: { passed: <int>, failed: <int>, skipped: <int>, errored: <int> }
  failures:
    - name: <test id>             # required; downstream skills key off this
      message: <one-line summary>
      file: <path:line>           # omit when not derivable
  coverage:                       # null when runner emitted none
    lines_covered: <int>
    lines_total: <int>
    percent: <float>
  raw_output_excerpt: <last 2KB of stdout+stderr; prepend "... [truncated] " when cut>
  notes: <one or more tokens from {truncated, no-tests-collected, parser-fallback, missing-dependency:<name>}, plus free text>
```

## Avoid

- Inventing a test command when no stack entry matches.
- Auto-installing dependencies or starting services to make a run succeed.
- Multi-package monorepo iteration - one invocation runs one command; the workflow loops.
