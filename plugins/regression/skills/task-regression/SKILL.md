---
name: task-regression
description: Run the outside-in regression suite end-to-end - build, up, wait healthy, seed, Playwright run, report, teardown. Ephemeral compose project, real-bug gating.
metadata:
  category: testing
  tags: [regression, playwright, docker-compose, e2e, orchestration]
  type: workflow
user-invocable: true
---

# Task: Regression

Headline workflow. Brings up the user-declared services in an ephemeral compose project, seeds the database directly, runs every Playwright scenario from `.regression/scenarios/`, classifies failures, writes a verdict, and tears the world down with `down -v --remove-orphans`.

Runtime depends only on `.regression/`. No codemap, OpenAPI, or sibling-repo metadata is read here. If `.regression/` is missing or stale, the workflow refers the user to `/task-regression-discover`.

## When to Use

- Local pre-PR check that no cross-service flow regressed.
- CI on a branch or release candidate (use `--profile pinned-images` for reproducibility).
- After a sibling-repo pull when the user wants verification against current code (`--profile local-build`).
- Smoke subset before a deploy gate (`--grep @smoke`).

**Not for:**
- Scaffolding the workspace -> `task-regression-discover`.
- Authoring a new scenario -> `task-regression-scenario`.
- Unit/integration tests -> `task-<stack>-test`.

## Inputs

| Input | Notes |
| --- | --- |
| `--profile <local-build\|pinned-images>` | Compose profile. Default resolution: flag, then env `REGRESSION_PROFILE`, then CI auto-detect (`CI=true` -> `pinned-images`), else `local-build`. |
| `--grep <tag>` | Forwarded to Playwright (e.g. `@smoke`, `@checkout`). Default: run all scenarios. |
| `--keep-up` | Debug only. Skip teardown so the user can inspect containers. Exits with a warning naming the project to clean up manually. |
| `--workers <N>` | Override Playwright workers. Default: from `.regression/playwright.config.ts`. |
| `--retries <N>` | Override Playwright retries. Default: 0 (retries hide bugs; explicit opt-in only). |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

Confirm in order; on any failure, stop with the named remediation:

1. `docker version` and `docker compose version` succeed.
2. `.regression/services.yaml`, `flows.yaml`, `docker-compose.regression.yml`, `playwright.config.ts`, `package.json` all present. If missing -> nudge to `/task-regression-discover`.
3. Required env vars (from `.env.example`) resolvable from environment or `.env`. List any missing names; do not print their values.
4. Required host ports are free if `services.yaml` declares any host port mappings. Default config has none.
5. **No codemap read.** Runtime does not consult `.codemap/`, OpenAPI files, or sibling repos.

### Step 3 - Resolve Compose Profile

Apply precedence:

1. `--profile` flag.
2. `REGRESSION_PROFILE` env var.
3. CI auto-detect: `CI=true` -> `pinned-images`.
4. Default: `local-build`.

Surface the resolved profile and source in the run header.

### Step 4 - Data Isolation Setup

Use skill: `regression-data-isolation`.

Mint `run-id` (timestamp + short random suffix). Compose project name becomes `regression-<runId>`. Volumes are project-scoped and disposable. Time-sensitive scenarios get `TZ=UTC` and a frozen wall-clock baseline matching `.regression/seeds/` constants. Per-scenario tenant/user IDs derive from `run-id` to keep parallel CI matrices hermetic.

### Step 5 - Run Lifecycle

Use skill: `regression-runner`.

The runner orchestrates the full lifecycle. Install a trap before this step so Ctrl+C / abnormal exit still triggers teardown in Step 8:

1. Ensure `.regression/node_modules` is present (`npm ci` if missing or if `package-lock.json` changed since last install).
2. For `git`-sourced services under `local-build`: clone/update into `.regression/.cache/<service>`.
3. `docker compose -p regression-<runId> -f docker-compose.regression.yml --profile <profile> up -d --build --wait`. `--wait` plus per-service `condition: service_healthy` is the only startup gate; no `sleep`.
4. Apply seeds in lexicographic order (`00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`) using the engine-native command from `regression-seed-strategy`. Fail-fast flags (`-v ON_ERROR_STOP=1` / `-b` / equivalent) required.
5. `npx playwright test --reporter=junit,line` from `.regression/`, forwarding `--grep` and `--workers` / `--retries` if provided.
6. On scenario failure: continue running remaining scenarios. No fail-fast. Collect JUnit XML, traces, videos, screenshots into `.regression/reports/<runId>/`.

### Step 6 - Format Report

Use skill: `regression-report-format`.

Normalize JUnit XML and emit `.regression/reports/<runId>/summary.md` with pass/fail/skip counts, per-flow verdict, top failure clusters, and links to traces. Failure clusters collapse identical root errors into a single entry with N occurrences.

### Step 7 - Triage Failures

Use skill: `regression-flakiness-triage` (only if there are failures).

Classify each failure into: `real bug` / `flake` / `infra` / `data drift`. Counts go at the top of `summary.md`. If `flake` ratio exceeds threshold, the report says "this suite is rotting, fix infra/seeds first" instead of demanding assertion fixes.

### Step 8 - Teardown

Always runs - install a trap at Step 5 so this fires on Ctrl+C and abnormal exit.

- Default: `docker compose -p regression-<runId> down -v --remove-orphans`. Volumes go with the project.
- `--keep-up`: skip teardown; print the project name and the exact `down -v --remove-orphans` command for the user to run later. Emit a loud warning.

### Step 9 - Exit Code

Exit non-zero iff at least one failure is classified `real bug` after Step 7. `flake` / `infra` / `data drift` failures are surfaced loudly in the report but do not fail the run. CI consumers gate on exit code; the report tells the human what to fix.

## Output Format

```markdown
# Regression Run Report

**Run ID:** regression-{runId}
**Profile:** {local-build | pinned-images} (source: {flag | env | CI auto-detect | default})
**Grep:** {tag or "all"}
**Started:** {ISO timestamp}
**Duration:** {wall-clock}

## Verdict

| Bucket | Count |
| --- | --- |
| Passed | {N} |
| Real bugs | {N} |
| Flakes | {N} |
| Infra failures | {N} |
| Data drift | {N} |
| Skipped | {N} |

**Exit code:** {0 | non-zero}  ({"clean" | "{N} real-bug failures"})

## Lifecycle

| Phase | Result | Wall-clock |
| --- | --- | --- |
| Preflight | pass | <1s |
| `npm ci` | skipped / ran | {N}s |
| Compose up --wait | {N} services healthy | {N}s |
| Seed | {N} files applied | {N}s |
| Playwright | {N} scenarios | {N}s |
| Report | summary.md written | <1s |
| Teardown | down -v --remove-orphans | {N}s |

## Top failure clusters

1. {root error excerpt} - {N} occurrences - {flow names}
2. ...

## Artifacts

- `.regression/reports/{runId}/summary.md`
- `.regression/reports/{runId}/junit.xml`
- `.regression/reports/{runId}/traces/`

## Next

- Real bugs: open issues against the owning services.
- Flakes: see `regression-flakiness-triage` notes in summary.md.
- `--keep-up` used? Clean up: `docker compose -p regression-{runId} down -v --remove-orphans`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: docker available, `.regression/` complete, required env vars present, host ports free; no codemap read attempted
- [ ] Step 3: profile resolved with precedence honored; source surfaced in report header
- [ ] Step 4: `regression-data-isolation` minted run-id, project name, ephemeral volumes, time freeze
- [ ] Step 5: `regression-runner` brought services up with `--wait` and healthcheck gating (no sleep); seeds applied in order with fail-fast; Playwright executed with junit reporter; failures did not abort remaining scenarios
- [ ] Step 6: `regression-report-format` produced `summary.md` with clusters, per-flow verdict, trace links
- [ ] Step 7: `regression-flakiness-triage` classified every failure; rotting-suite warning surfaced if flake ratio breaches threshold
- [ ] Step 8: teardown ran via trap even on failure or Ctrl+C; `--keep-up` printed cleanup command
- [ ] Step 9: exit non-zero iff any `real bug` failures remain after triage

## Avoid

- Reading codemap, OpenAPI, or sibling repos at runtime. `.regression/` is the only source of truth.
- `sleep`-based startup gating. Use `--wait` plus `condition: service_healthy`.
- Shared or persistent volumes across runs. Per-run project name + `down -v` keeps runs hermetic.
- Fail-fast on first scenario failure. Run all, report all.
- Default-on retries. They hide bugs; require explicit opt-in.
- Failing the exit code on `flake` / `infra` / `data drift`. Only `real bug` failures gate CI.
- Skipping teardown on success. Volumes leak across runs and break parallel matrices.
- Leaving containers up after `--keep-up` without printing the exact cleanup command.
- Running app migrations from the seeder. Seeds bypass the backend; talk to the DB directly.
- Logging resolved env var values. Names only.
