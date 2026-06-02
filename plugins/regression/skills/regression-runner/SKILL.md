---
name: regression-runner
description: Ephemeral run lifecycle for outside-in regression. npm ci, compose up --wait, seed in order, playwright test, collect all failures, always teardown with down -v.
metadata:
  category: testing
  tags: [regression, runner, docker-compose, lifecycle, ci]
user-invocable: false
---

# Regression Runner

> Inputs: env vars from `regression-data-isolation` (`REGRESSION_RUN_ID`, `TZ`) plus `REGRESSION_PROFILE` and forwarded Playwright args (`REGRESSION_PW_ARGS`). Seed apply commands come from `regression-seed-strategy`.

Per-run lifecycle: install deps, sync `git` sources under `local-build`, `up --wait`, seed in order, run Playwright, collect every failure, tear down with `-v` regardless. Never fail-fast. Never sleeps.

## When to Use

- Inside `task-regression` after `regression-data-isolation` minted the run-id.
- Never during discover / scenario authoring.

## Rules

1. **Env-var inputs only.** No flag parsing inside this skill. Inputs:

   | Variable | Set by | Used for |
   | --- | --- | --- |
   | `REGRESSION_RUN_ID` | `regression-data-isolation` | derives `PROJECT` and report path |
   | `REGRESSION_PROFILE` | `task-regression` | `--profile <profile>` on compose up |
   | `REGRESSION_PW_ARGS` | `task-regression` | extra args forwarded to `playwright test` (`--grep`, `--workers`, `--retries`) |
   | `TZ=UTC` | this skill exports | frozen clock |

2. **`npm ci` skip via stamp file.** Run `npm ci` when `node_modules/.install-stamp` is missing OR older than `package-lock.json`. After a successful `ci`, `touch node_modules/.install-stamp`. First run never has the stamp - that *is* the skip condition firing correctly.
3. **Health-gated startup.** `docker compose ... up -d --wait`. Pass `--build` only under `local-build`; under `pinned-images` `--build` is a no-op for image-only services and surfaces as a warning if any compose entry has a `build:` context in that profile. Never `sleep`.
4. **Seed in byte-wise lexicographic order.** `find ... | LC_ALL=C sort`. Apply per-engine via `regression-seed-strategy`. First seed error aborts the run with exit code `3` *before* Playwright is invoked; teardown still runs.
5. **Run-all-collect-all.** Playwright runs to completion even when scenarios fail. No `--max-failures`. No fail-fast.
6. **Teardown always.** `trap` on `EXIT INT TERM`. `down -v --remove-orphans`. Idempotent: a manual `down` already having cleaned up is fine. Ctrl+C must not leak volumes.
7. **Reports under `reports/<runId>/`.** JUnit XML + line log + traces + videos + screenshots.
8. **`git` sources cloned/updated under `local-build` only** into `.regression/.cache/<service>` at `services.yaml#source.ref`. `git fetch --depth=1 origin <ref> && git -C ... reset --hard FETCH_HEAD`; never `merge` / `pull`. Under `pinned-images`, git-sourced entries do not appear in the active compose set, so no sync.

## Patterns

### Canonical lifecycle script

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${REGRESSION_RUN_ID:?run-id not set; call regression-data-isolation first}"
: "${REGRESSION_PROFILE:?profile not set}"
PROJECT="regression-${REGRESSION_RUN_ID}"
REPORTS=".regression/reports/${REGRESSION_RUN_ID}"
PW_ARGS="${REGRESSION_PW_ARGS:-}"
mkdir -p "$REPORTS"
export TZ=UTC

teardown() {
  echo "[runner] tearing down $PROJECT"
  docker compose -p "$PROJECT" -f .regression/docker-compose.regression.yml \
    --profile "$REGRESSION_PROFILE" down -v --remove-orphans 2>/dev/null || true
}
trap teardown EXIT INT TERM

# 1. deps
( cd .regression && \
  if [ ! -f node_modules/.install-stamp ] || [ package-lock.json -nt node_modules/.install-stamp ]; then \
    npm ci && touch node_modules/.install-stamp; \
  fi )

# 2. git-sourced services (local-build only). sync-git-sources.sh is shipped with this skill;
#    contract: read services.yaml, for each source.type==git clone or fetch+reset --hard to source.ref.
if [ "$REGRESSION_PROFILE" = "local-build" ]; then
  .regression/scripts/sync-git-sources.sh
fi

# 3. compose up; --build only under local-build
BUILD_FLAG=""
[ "$REGRESSION_PROFILE" = "local-build" ] && BUILD_FLAG="--build"
docker compose -p "$PROJECT" -f .regression/docker-compose.regression.yml \
  --profile "$REGRESSION_PROFILE" up -d $BUILD_FLAG --wait

# 4. seed in order; fail-fast on first error
SEED_EXIT=0
while IFS= read -r f; do
  echo "[runner] seeding $f"
  .regression/scripts/apply-seed.sh "$PROJECT" "$f" || { SEED_EXIT=3; break; }
done < <(find .regression/seeds -type f \( -name '*.sql' -o -name '*.json' \) | LC_ALL=C sort)
if [ "$SEED_EXIT" -ne 0 ]; then
  exit "$SEED_EXIT"            # trap runs teardown
fi

# 5. Playwright run-all. Output respects playwright.config.ts's `outputFolder`;
#    typical default is `test-results/`. JUnit goes wherever the reporter writes.
set +e
( cd .regression && npx playwright test --reporter=junit,line $PW_ARGS ) \
  | tee "$REPORTS/line.log"
TEST_EXIT=$?
set -e

# 6. collect artifacts
cp -r .regression/test-results/* "$REPORTS/" 2>/dev/null || true
# JUnit reporter writes to the path configured in playwright.config.ts (default: `results.xml`)
cp .regression/results.xml "$REPORTS/junit.xml" 2>/dev/null || true

exit "$TEST_EXIT"               # trap runs teardown
```

### Why each piece exists

- `trap` on `EXIT INT TERM`: Ctrl+C must not leak volumes. `EXIT` makes the trap fire on `set -e` aborts too. Idempotent teardown means firing twice (e.g. `INT` then `EXIT`) is harmless.
- `--wait` + healthcheck-gated `depends_on`: no `sleep` race.
- `--build` only under `local-build`: image-only services never need a build context; passing `--build` to pinned-images would force-rebuild any stray `build:` entry, defeating the reproducibility point of the profile.
- `find ... | LC_ALL=C sort`: filesystem ordering differs macOS vs Linux.
- Stamp file: `npm ci` is reproducible but not idempotent; the stamp encodes "did we install for this lockfile already".
- `set +e` around `playwright test`: a failing scenario must not abort report collection.
- Seed fail-fast with exit `3`: a broken schema produces meaningless test verdicts. Distinct from Playwright's exit code so callers can distinguish "seed failed" from "tests failed".
- `down -v --remove-orphans`: forgotten volumes carry yesterday's data into today's run.
- `npm ci` not `npm install`: `install` mutates the lockfile.
- `git fetch --depth=1 && reset --hard`: `merge` on the runner produces a state that exists nowhere else.

### Selective runs

`task-regression --grep @smoke` is forwarded to Playwright via `REGRESSION_PW_ARGS="--grep @smoke"`. The runner itself does not interpret tags.

### Shipped scripts

`regression-runner` ships with two helper scripts under `.regression/scripts/`:

- `sync-git-sources.sh` - reads `services.yaml`, syncs git-sourced services. Idempotent.
- `apply-seed.sh "$PROJECT" "$FILE"` - dispatches per-engine apply command from `regression-seed-strategy`.

Discover writes these on first scaffold; they are committed in `.regression/scripts/`. No other skill owns them.

### What this skill does not do

- Mint `run-id` (`regression-data-isolation`).
- Format the summary (`regression-report-format`).
- Classify failures (`regression-flakiness-triage`).
- Build the compose file (`regression-compose-build`).
- Define seed apply commands (`regression-seed-strategy`).

## Output Format

```
.regression/reports/<runId>/
  junit.xml
  line.log
  traces/             # retain-on-failure (config)
  videos/             # retain-on-failure (config)
  screenshots/        # on failure (config)
```

Exit code: `0` = green, Playwright's non-zero = test failures, `3` = seed failure, `137` = SIGKILL. Teardown runs regardless.

## Avoid

- `sleep` for readiness.
- `npm install` (use `npm ci`).
- `up` without `-d --wait`.
- `--build` under `pinned-images`.
- `down` without `-v`.
- Skipping the trap.
- Fail-fast on test runs (always finish, classify after).
- Reading or writing under sibling repo paths (git sources go in `.regression/.cache/`).
