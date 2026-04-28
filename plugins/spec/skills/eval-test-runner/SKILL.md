---
name: eval-test-runner
description: Detect the project's test command from the stack, run it, and parse the output into a structured pass/fail/coverage record. Composed by `task-spec-evaluate` to feed the scorer. Opt-in - only invoked when the user runs an evaluation explicitly or via `task-spec-orchestrate --with-evaluation`.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, testing, test-runner]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

# Eval - Test Runner

> This atomic is composed by `task-spec-evaluate` - do not invoke directly. It runs project tests via shell and emits a structured result; consuming workflows use the result alongside spec coverage and review verdicts to score an orchestration run.

## When to Use

- Inside `task-spec-evaluate` after orchestration has produced code and tests
- When the user explicitly asks to "run the evaluation" or "score this implementation"
- When `task-spec-orchestrate` is invoked with `--with-evaluation` and reaches the evaluation step

**Not for:** Routine local test runs (those are the user's job), CI orchestration, generating tests (that's `task-code-test`), running tests as part of the `test` agent step in orchestration (that agent invokes its stack's standard test command directly without this atomic).

## Rules

- Detection MUST come from `stack-detect` output - do not infer the test command from filenames or guesswork
- Always run from the project root unless the stack convention requires a subdirectory (e.g., monorepo workspace)
- Capture **both** stdout and stderr - many test runners write failures to stderr
- Time-box the run: default **300 seconds**, configurable up to **1800**. A timeout produces `status: timeout`, not `failed` - they are different signals
- Never modify source code, configuration, or lockfiles to make tests pass - if tests cannot run, surface the reason; do not fix it
- The atomic does not interpret pass/fail in business terms - it reports raw counts and an exit code; the scorer maps that to spec impact

## Inputs

| Input             | Source                                                                                |
| ----------------- | ------------------------------------------------------------------------------------- |
| Detected stack    | `stack-detect` output (language, framework, package manager)                          |
| `test_command`    | Optional override. If omitted, derived from the table below                           |
| `timeout_seconds` | Optional, default 300, max 1800                                                       |
| `test_filter`     | Optional - pass-through to the runner (e.g., `--match`, `-k`, `-run`) for scoped runs |

## Test Command Selection

| Stack signal                                 | Default test command                                   | Output parser    |
| -------------------------------------------- | ------------------------------------------------------ | ---------------- |
| Java + Maven (`pom.xml`)                     | `./mvnw -B test` (or `mvn -B test`)                    | Surefire XML     |
| Java/Kotlin + Gradle                         | `./gradlew --no-daemon test`                           | Gradle stdout    |
| .NET (`*.csproj`, `*.sln`)                   | `dotnet test --logger "trx"`                           | trx XML          |
| Python (`pytest.ini`, `pyproject` w/ pytest) | `pytest -q --tb=short`                                 | pytest stdout    |
| Python (Django)                              | `python manage.py test --verbosity=2`                  | Django stdout    |
| Node + npm (`package.json` test script)      | `npm test -- --reporter=json`                          | JSON stream      |
| Node + pnpm                                  | `pnpm test`                                            | runner stdout    |
| Node + yarn                                  | `yarn test`                                            | runner stdout    |
| Go (`go.mod`)                                | `go test ./... -json`                                  | go test JSON     |
| Rust (`Cargo.toml`)                          | `cargo test --no-fail-fast`                            | cargo stdout     |
| PHP/Laravel (`artisan`)                      | `php artisan test`                                     | PHPUnit stdout   |
| Ruby/Rails (`Gemfile`, `bin/rails`)          | `bin/rails test` or `bundle exec rspec`                | Minitest / RSpec |
| Frontend - Vitest config present             | `vitest run --reporter=json`                           | Vitest JSON      |
| Frontend - Jest config present               | `jest --json`                                          | Jest JSON        |
| Frontend - Karma/Angular                     | `ng test --watch=false --browsers=ChromeHeadless`      | Karma stdout     |
| Frontend - Playwright (e2e)                  | NOT run by default - too slow; require explicit opt-in | Playwright JSON  |

If the stack has no entry, abort with `status: no-runner-detected`. Do not invent a command.

## Run Procedure

1. Resolve the test command from the table or the override.
2. Run with the configured timeout. Capture stdout, stderr, exit code, wall-clock duration.
3. Parse output using the parser appropriate to the runner:
   - Counts: `passed`, `failed`, `skipped`, `errored`
   - Per-test entries (when available): `name`, `status`, `duration_ms`, `failure_message`
   - Coverage (when available): `lines_covered`, `lines_total`, `percent`
4. If parsing fails, fall back to exit-code-only mode: `passed = exit==0 ? "unknown-pass" : 0`, include raw output excerpt in `notes`.

## Output Format

```yaml
test_run:
  command: <full command line executed>
  cwd: <working directory>
  status: pass | fail | timeout | no-runner-detected | error
  exit_code: <integer or null>
  duration_seconds: <float>
  counts:
    passed: <int>
    failed: <int>
    skipped: <int>
    errored: <int>
  failures:
    - name: <test identifier>
      message: <one-line failure summary>
      file: <path:line, if available>
  coverage:
    lines_covered: <int or null>
    lines_total: <int or null>
    percent: <float or null>
  raw_output_excerpt: <last 30 lines of combined stdout/stderr - elided if >2KB>
  notes: <freeform - parser fallback reasons, environment caveats>
```

## Status Semantics

| Status               | Meaning                                                                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `pass`               | Exit 0, parser confirms zero failures and zero errors                                                                                         |
| `fail`               | Exit non-zero OR parser reports any failure/error                                                                                             |
| `timeout`            | Run exceeded `timeout_seconds`. Distinct from `fail` because the system did not get a verdict; the user must extend the timeout or scope down |
| `no-runner-detected` | Stack has no entry in the selection table and no override was provided                                                                        |
| `error`              | Runner could not be invoked at all (binary missing, dependency install required, broken project state)                                        |

## Handling Edge Cases

- **No tests exist yet:** runners typically report `0 passed, 0 failed`. Report status `pass` but include `notes: "no tests collected"`. The scorer treats this as zero-coverage signal, not a passing run.
- **Flaky test on retry:** this atomic does NOT retry. A single run is one data point. The scorer or user decides whether to re-invoke.
- **Coverage data missing:** report `coverage: null` rather than zero. Zero is a real value; missing is different.
- **Monorepo with multiple test commands:** the caller must pass an explicit `test_command` per package; the atomic does not auto-discover workspaces.
- **Tests require services (DB, Redis):** if the runner errors with connection refused, status is `error` with a `notes` line naming the missing dependency. Do not try to start services.
- **Output too large to parse fully:** still emit counts; truncate `raw_output_excerpt` to the tail; flag `notes: "output truncated for parsing"`.

## Avoid

- Running tests without a detected stack or explicit override - silent guessing produces meaningless scores
- Modifying tests, source, or config to make a run succeed - the atomic is a measurement, not a fixer
- Conflating `timeout` with `fail` - they prompt different user actions
- Reporting coverage as `0` when the runner did not emit coverage - use `null`
- Auto-installing dependencies (`npm install`, `pip install`) - the project is the user's; surface the gap instead
- Running E2E suites by default - they are slow and environment-sensitive; require explicit opt-in

## Notes

- The atomic shells out to invoke the project's test runner, which is the only place in the `spec` plugin that executes external commands. This is intentional and opt-in: it only runs when the user explicitly invokes evaluation.
- Parser implementations live in the runner ecosystem (Surefire reports, JSON reporters); this skill prescribes which parser to use, not how to implement it. Claude reads the output following the parser's known schema.
- Single source of truth for the test command: this atomic. Other skills that need to "run the tests" should compose this atomic, not duplicate the table above.
