---
name: regression-runner
description: Ephemeral run lifecycle for outside-in regression. npm ci, compose up --wait, seed in order, playwright test, collect all failures, always teardown with down -v.
metadata:
  category: testing
  tags: [regression, runner, docker-compose, lifecycle, ci]
user-invocable: false
---

# Regression Runner

> Load `Use skill: regression-data-isolation` for `run-id` minting and the compose project naming contract. Load `Use skill: regression-seed-strategy` for the per-engine seed apply commands.

Owns the per-run lifecycle: install deps, clone git sources if needed, `up --wait`, seed in order, run Playwright, collect every failure, tear down with `-v` no matter what. Never fails fast; never sleeps.

## When to Use

- Inside `task-regression` after `regression-data-isolation` has minted the `run-id`.
- Never during `task-regression-discover` or `task-regression-scenario`. This skill executes; the discover/scenario skills only author.

## Rules

1. **Inputs are env vars.** `PROJECT` (= `regression-<runId>`), `REGRESSION_PROFILE` (`local-build` | `pinned-images`), `REGRESSION_RUN_ID`. No flag parsing inside this skill.
2. **`npm ci` only.** Never `npm install`. Runs in `.regression/` and is skipped only when `node_modules/` exists and `package-lock.json` is unchanged since last install.
3. **Health-gated startup.** `docker compose ... up -d --build --wait`. Never `sleep`. Never `up -d` without `--wait`.
4. **Seed in lexicographic order.** Walk `.regression/seeds/**` sorted, apply each via the engine-specific command from `regression-seed-strategy`. Stop the run on first seed error (real failure, not a flake).
5. **Run-all-collect-all.** Playwright runs to completion even when scenarios fail. No `--max-failures`. No fail-fast.
6. **Teardown always.** Bash `trap` on `EXIT` `INT` `TERM` runs `docker compose -p $PROJECT down -v --remove-orphans`. Ctrl+C must not leak volumes.
7. **Reports under `reports/<runId>/`.** JUnit XML + line output + traces + videos + screenshots collected before teardown.
8. **`git`-sourced services are cloned/updated before `up`.** Under `.regression/.cache/<service>`. `git fetch --depth=1 && git reset --hard <ref>`; never merge.

## Patterns

### Env-var inputs

| Variable              | Set by                                | Example                          | Used for                                                       |
| --------------------- | ------------------------------------- | -------------------------------- | -------------------------------------------------------------- |
| `REGRESSION_RUN_ID`   | `regression-data-isolation`           | `20260601T101530-a7f3c2`         | Minted once per run; consumed by data factory and report path. |
| `PROJECT`             | this skill, from `REGRESSION_RUN_ID`  | `regression-20260601T101530-a7f3c2` | `docker compose -p $PROJECT`                                  |
| `REGRESSION_PROFILE`  | `task-regression`                     | `local-build` / `pinned-images`  | `--profile <profile>` on `compose up`                          |
| `TZ`                  | this skill, always                    | `UTC`                            | Frozen clock contract; consumed by every container             |

### Lifecycle script (the canonical shape)

```bash
set -euo pipefail
: "${REGRESSION_RUN_ID:?run-id not set; call regression-data-isolation first}"
: "${REGRESSION_PROFILE:?profile not set}"
PROJECT="regression-${REGRESSION_RUN_ID}"
REPORTS=".regression/reports/${REGRESSION_RUN_ID}"
mkdir -p "$REPORTS"
export TZ=UTC

teardown() {
  echo "[runner] tearing down $PROJECT"
  docker compose -p "$PROJECT" -f .regression/docker-compose.regression.yml \
    --profile "$REGRESSION_PROFILE" down -v --remove-orphans || true
}
trap teardown EXIT INT TERM

# 1. deps
( cd .regression && \
  if [ ! -d node_modules ] || [ package-lock.json -nt node_modules/.install-stamp ]; then \
    npm ci && touch node_modules/.install-stamp; \
  fi )

# 2. git-sourced services (local-build only)
if [ "$REGRESSION_PROFILE" = "local-build" ]; then
  # for each services.yaml entry with source.type == git:
  #   .regression/.cache/<name> ; clone if absent, fetch+reset --hard otherwise
  python3 .regression/scripts/sync-git-sources.py
fi

# 3. compose up - healthcheck gated, never sleeps
docker compose -p "$PROJECT" -f .regression/docker-compose.regression.yml \
  --profile "$REGRESSION_PROFILE" up -d --build --wait

# 4. seed in lexicographic order
for f in $(find .regression/seeds -type f \( -name '*.sql' -o -name '*.json' \) | sort); do
  echo "[runner] seeding $f"
  # delegate to regression-seed-strategy per-engine snippet
  .regression/scripts/apply-seed.sh "$PROJECT" "$f"
done

# 5. run all - never fail-fast
set +e
( cd .regression && npx playwright test --reporter=junit,line ) \
  | tee "$REPORTS/line.log"
TEST_EXIT=$?
set -e

# 6. collect artifacts (Playwright already wrote junit.xml + traces under .regression/test-results)
cp -r .regression/test-results/* "$REPORTS/" 2>/dev/null || true
cp .regression/results.xml "$REPORTS/junit.xml" 2>/dev/null || true

# 7. teardown runs via trap; exit with Playwright's status
exit "$TEST_EXIT"
```

### Why each piece exists

| Decision                              | Failure mode it prevents                                                  |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `trap teardown EXIT INT TERM`         | Ctrl+C leaks named volumes, breaking the next run with stale data.        |
| `--wait` on `up`                      | Race between Playwright start and backend readiness -> flaky 5xx.         |
| `find ... \| sort` for seeds          | Filesystem ordering differs between Linux and macOS -> non-deterministic. |
| `set +e` around `playwright test`     | A failing scenario must not abort report collection.                      |
| `down -v --remove-orphans`            | Forgotten volumes carry yesterday's tenant rows into today's run.         |
| `npm ci`, not `npm install`           | `install` mutates `package-lock.json`; `ci` is reproducible.              |
| `git fetch --depth=1 && reset --hard` | A `merge` on the runner can produce a state that exists nowhere else.     |

### Bad / good

```bash
# BAD: races backend startup
docker compose up -d && sleep 30 && npx playwright test

# GOOD: health-gated
docker compose -p "$PROJECT" up -d --build --wait
npx playwright test
```

```bash
# BAD: fail-fast hides 9 of 10 failures
npx playwright test --max-failures=1

# GOOD: collect everything, classify after
set +e; npx playwright test; TEST_EXIT=$?; set -e
```

```bash
# BAD: teardown skipped on Ctrl+C -> next run picks up stale volumes
docker compose up -d --wait
npx playwright test
docker compose down -v

# GOOD: trap-guarded teardown
trap 'docker compose -p "$PROJECT" down -v --remove-orphans' EXIT INT TERM
```

### `git`-source sync rules

For each `services.yaml` entry where `source.type == git`:

1. If `.regression/.cache/<name>` does not exist: `git clone --depth=1 --branch <ref> <url> .regression/.cache/<name>`.
2. Else: `git -C .regression/.cache/<name> fetch --depth=1 origin <ref> && git -C ... reset --hard FETCH_HEAD`.
3. Never `git pull`. Never `git merge`. The cache mirrors the declared ref exactly.

Only runs under `local-build` profile - `pinned-images` reads from a registry and never needs sources.

### Selective runs

`task-regression --grep @smoke` forwards as `npx playwright test --grep @smoke`. The runner itself does not interpret tags; Playwright does.

### What this skill does not do

- Mint the `run-id` (that is `regression-data-isolation`).
- Format the markdown summary (that is `regression-report-format`).
- Classify failures (that is `regression-flakiness-triage`).
- Build the compose file (that is `regression-compose-build`).

## Output Format

The runner emits to stdout/stderr and writes:

```
.regression/reports/<runId>/
  junit.xml
  line.log
  traces/             # retain-on-failure
  videos/             # retain-on-failure
  screenshots/        # on failure
```

Exit code is Playwright's exit code (0 = all pass, non-zero = at least one failure). Teardown runs regardless.

## Avoid

- **`sleep` to wait for readiness.** Always `--wait` + healthchecks.
- **`npm install` in CI.** Use `npm ci`.
- **`up` without `-d --build --wait`.** Foreground hangs the runner; missing build skips local code; missing wait races startup.
- **`down` without `-v`.** Stale volumes turn the next run into a debugging session for yesterday's data.
- **Skipping the trap.** Any non-trapped exit path leaks containers and volumes.
- **`--max-failures` / fail-fast flags.** You learn one failure instead of ten.
- **Reading or writing under sibling repo paths.** `git`-sourced services land under `.regression/.cache/`, never `../<service>`.
