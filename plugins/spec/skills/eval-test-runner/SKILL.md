---
name: eval-test-runner
description: Detect project test command from the stack, run it, parse output into a structured pass / fail / coverage record for SDD evaluation.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, testing, test-runner]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

# Eval - Test Runner

> Composed by `task-spec-evaluate`. Single source of truth for "run the project's tests" inside SDD. Not for routine local runs, CI, or test generation.

## Rules

- Test command comes from `stack-detect` output or an explicit override - never guessed from filenames.
- Capture both stdout and stderr (many runners report failures to stderr).
- Default timeout 300s, max 1800s. Timeout is its own status, not `fail`.
- Never modify source, config, or lockfiles to make tests pass. Never auto-install dependencies.
- This atomic is a measurement, not a fixer. Counts and exit code only; the scorer interprets impact.

## Inputs

`test_command` (override), `timeout_seconds` (default 300, max 1800), `test_filter` (pass-through, e.g. `-k`, `--match`).

## Test Command Selection

| Stack signal                       | Default command                                   | Parser           |
| ---------------------------------- | ------------------------------------------------- | ---------------- |
| Java + Maven                       | `./mvnw -B test`                                  | Surefire XML     |
| Java/Kotlin + Gradle               | `./gradlew --no-daemon test`                      | Gradle stdout    |
| .NET                               | `dotnet test --logger "trx"`                      | trx XML          |
| Python + pytest                    | `pytest -q --tb=short`                            | pytest stdout    |
| Python + Django                    | `python manage.py test --verbosity=2`             | Django stdout    |
| Node + npm                         | `npm test -- --reporter=json`                     | JSON stream      |
| Node + pnpm / yarn                 | `pnpm test` / `yarn test`                         | runner stdout    |
| Go                                 | `go test ./... -json`                             | go test JSON     |
| Rust                               | `cargo test --no-fail-fast`                       | cargo stdout     |
| PHP/Laravel                        | `php artisan test`                                | PHPUnit stdout   |
| Ruby/Rails                         | `bin/rails test` or `bundle exec rspec`           | Minitest / RSpec |
| Frontend - Vitest                  | `vitest run --reporter=json`                      | Vitest JSON      |
| Frontend - Jest                    | `jest --json`                                     | Jest JSON        |
| Frontend - Angular/Karma           | `ng test --watch=false --browsers=ChromeHeadless` | Karma stdout     |
| Frontend - Playwright (e2e)        | Opt-in only - too slow for default                | Playwright JSON  |

No matching entry and no override -> `status: no-runner-detected`. Do not invent a command.

## Output Format

```yaml
test_run:
  command: <full command line>
  cwd: <working directory>
  status: pass | fail | timeout | no-runner-detected | error
  exit_code: <int or null>
  duration_seconds: <float>
  counts: { passed, failed, skipped, errored }
  failures:
    - name: <test id>
      message: <one-line summary>
      file: <path:line>          # when available
  coverage:                       # null when runner does not emit coverage (zero != null)
    lines_covered: <int>
    lines_total: <int>
    percent: <float>
  raw_output_excerpt: <last 30 lines, elided >2KB>
  notes: <parser fallback reasons, env caveats>
```

## Status Semantics

| Status               | Meaning                                                                                |
| -------------------- | -------------------------------------------------------------------------------------- |
| `pass`               | Exit 0 and parser reports zero failures/errors                                         |
| `fail`               | Non-zero exit or any failure/error                                                     |
| `timeout`            | Exceeded `timeout_seconds`. No verdict; user must extend or scope down                 |
| `no-runner-detected` | No matching stack entry and no override                                                |
| `error`              | Runner could not be invoked (binary missing, services unavailable, broken project)     |

## Edge Cases

- **No tests collected** (`0 passed, 0 failed`): status `pass`, `notes: "no tests collected"`. Scorer treats this as zero-coverage signal.
- **Flaky test**: no retry here - one run is one data point.
- **Tests require services** (DB, Redis): connection refused -> `error` with the missing dependency named in `notes`. Do not try to start services.
- **Monorepo**: caller passes explicit `test_command` per package; no workspace auto-discovery.
- **Output too large to parse**: still emit counts, truncate `raw_output_excerpt`, note the truncation.

## Avoid

- Conflating `timeout` with `fail`.
- Reporting `coverage: 0` when the runner did not emit coverage (use `null`).
- Auto-installing dependencies (`npm install`, `pip install`).
- Running E2E suites without explicit opt-in.
