---
name: eval-test-runner
description: Run the project's test suite via stack-detected command; parse pass/fail/coverage/timeout into a structured SDD eval record.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, testing, test-runner]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

Composed by `task-spec-evaluate` to produce one measurement of the project's tests after implementation. One invocation, one data point. Not for routine dev loops, CI orchestration, or test generation.

## Rules

- Test command comes from the table below or an explicit `test_command` override. Never guess from filenames.
- Capture both stdout and stderr (many runners report failures to stderr).
- Read-only execution: no installs, no source/config/lockfile edits, no service startup.
- `timeout` is its own status, not `fail`. One run is one data point - do not retry flakes.
- Counts come from the runner's machine-readable output when available (XML/JSON), else stdout parsing.

## Patterns

### Inputs

| Field             | Default                          | Notes                                                         |
| ----------------- | -------------------------------- | ------------------------------------------------------------- |
| `test_command`    | from selection table             | Override wins over detection                                  |
| `timeout_seconds` | 300 (slow stacks below: 900)     | Hard cap 1800                                                 |
| `test_filter`     | none                             | Pass-through to runner (`-k`, `--match`, `--testNamePattern`) |

Slow-stack defaults (set `timeout_seconds: 900` unless overridden): Testcontainers-enabled Java/Kotlin, Karma, Playwright, Django with live DB.

### Test Command Selection

| Stack signal                  | Command                                                  |
| ----------------------------- | -------------------------------------------------------- |
| Java + Maven                  | `./mvnw -B test`                                         |
| Java/Kotlin + Gradle          | `./gradlew --no-daemon test`                             |
| .NET                          | `dotnet test --logger trx`                               |
| Python + pytest               | `pytest -q --tb=short`                                   |
| Python + Django               | `python manage.py test --verbosity=2`                    |
| Node + npm                    | `npm test`                                               |
| Node + pnpm                   | `pnpm test`                                              |
| Node + yarn                   | `yarn test`                                              |
| Go                            | `go test ./... -json`                                    |
| Rust                          | `cargo test --no-fail-fast`                              |
| PHP + Laravel                 | `php artisan test`                                       |
| Ruby + Rails (Minitest)       | `bin/rails test`                                         |
| Ruby + RSpec                  | `bundle exec rspec`                                      |
| Frontend + Vitest             | `vitest run --reporter=json`                             |
| Frontend + Jest               | `jest --json`                                            |
| Frontend + Angular/Karma      | `ng test --watch=false --browsers=ChromeHeadless`        |

Playwright/Cypress e2e: skip unless the caller passes an explicit `test_command`; they exceed even slow-stack timeouts. No match and no override -> `status: no-runner-detected`.

Disambiguation for Ruby: if both `spec/` and `test/` exist, prefer RSpec when `Gemfile.lock` lists `rspec-rails`, else Minitest.

### Counts and Coverage Sources

- Java/Maven: `target/surefire-reports/TEST-*.xml`. Coverage from `target/site/jacoco/jacoco.xml` if present.
- Gradle: `build/test-results/test/*.xml`. Coverage from `build/reports/jacoco/test/jacocoTestReport.xml`.
- .NET: trx file under `TestResults/`. Coverage from `coverage.cobertura.xml` if `--collect:"XPlat Code Coverage"` was added by override.
- pytest: stdout `=== N passed, N failed ===` line; coverage from `.coverage` only if `pytest-cov` was invoked by override.
- Go: parse `-json` stream (`Action: pass|fail|skip`); coverage requires `-coverprofile` override.
- JSON reporters (Vitest, Jest): parse `numTotalTests`, `numFailedTests`, `coverageMap` if present.

If the runner emits no coverage data, set `coverage: null`. Never substitute `0`.

### `failures[].file` Derivation

In order, first that resolves wins:
1. File path from the runner's report (XML/JSON `file` or `location`).
2. Source path derived from a fully-qualified class name (`com.acme.UserService` -> `src/main/java/com/acme/UserService.java`) if the file exists.
3. Omit the field.

### Truncation

`raw_output_excerpt`: last 30 lines of combined stdout+stderr, then truncate to 2KB if still larger. Record both cuts in `notes` when they fire.

### Status Semantics

| Status               | Trigger                                                                       |
| -------------------- | ----------------------------------------------------------------------------- |
| `pass`               | Exit 0 and zero failures/errors. Also when 0 tests collected (note it)        |
| `fail`               | Non-zero exit or any failure/error reported by the runner                     |
| `timeout`            | Wall clock exceeded `timeout_seconds`                                         |
| `no-runner-detected` | No table match and no override                                                |
| `error`              | Runner could not be invoked (binary missing, services unavailable, OOM)       |

Tests requiring services (DB, Redis, Docker) that fail to connect: `error`, name the missing dependency in `notes`. Do not start services.

## Output Format

```yaml
test_run:
  command: <full command line>
  cwd: <working directory>
  status: pass | fail | timeout | no-runner-detected | error
  exit_code: <int or null>
  duration_seconds: <float>
  counts: { passed: <int>, failed: <int>, skipped: <int>, errored: <int> }
  failures:
    - name: <test id>
      message: <one-line summary>
      file: <path:line>          # omit when not derivable
  coverage:                       # null when runner emitted none
    lines_covered: <int>
    lines_total: <int>
    percent: <float>
  raw_output_excerpt: <see Truncation>
  notes: <parser fallback, truncation, missing dependency, "no tests collected">
```

## Avoid

- Inventing a test command when no stack entry matches.
- Auto-installing dependencies or starting services to make a run succeed.
- Retrying a failed test to filter flakes.
- Multi-package monorepo iteration - one invocation runs one command; the workflow loops.
