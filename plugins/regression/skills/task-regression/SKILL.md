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

Headline workflow. Brings up the user-declared services in an ephemeral compose project, seeds the database directly, runs every Playwright scenario under `.regression/scenarios/`, classifies failures, writes a verdict, and tears the world down with `down -v --remove-orphans`.

Runtime reads `.regression/` only. No codemap, no OpenAPI, no sibling-repo metadata. If `.regression/` is missing or stale, point the user at `/task-regression-discover`.

## When to Use

- Local pre-PR check that no cross-service flow regressed.
- CI on a branch / release candidate (`--profile pinned-images` for reproducibility).
- Sibling-repo verification after a pull (`--profile local-build`).
- Smoke subset before a deploy gate (`--grep @smoke`).

**Not for:**
- Scaffolding the workspace -> `task-regression-discover`.
- Authoring a scenario -> `task-regression-scenario`.
- Unit/integration tests -> `task-<stack>-test`.

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| `--profile <local-build\|pinned-images>` | resolved via Step 3 | Compose profile. |
| `--grep <tag>` | run all | Forwarded verbatim to Playwright. |
| `--workers <N>` | from `playwright.config.ts` | CLI flag overrides config. |
| `--retries <N>` | `0` | Forwarded verbatim. Default `0`; retries hide bugs. |
| `--keep-up` | off | Skip teardown on normal exit. Trap on `INT`/`TERM` still fires. |
| `--include-deprecated` | off | Run flows with `status: deprecated`. Default: skip them. Stale flows always run but surface as warnings in the report. |
| `--rerun-failed <runId>` | off | Read `.regression/runs/<runId>/triage.json` and re-run only the failing scenario titles via `--grep`. Mutually exclusive with `--grep`. |
| `--matrix-key <key>` | unset | Suffix for the report dir (`reports/<runId>__<key>/`) so sharded/matrix CI jobs do not overwrite each other. Defaults to `default` when `SHARD_INDEX` is set without `--matrix-key`. |
| `--annotations <gh\|gl\|none>` | `none` | Emit CI-native annotations alongside `summary.md`. `gh` -> GitHub `::error file=...,line=...::` to stderr. `gl` -> GitLab `code-quality.json`. Forwarded to `regression-report-format` via `REGRESSION_ANNOTATIONS`. |
| `--pr-comment` | off | After the report writes, post / update a sticky PR comment via `regression-pr-comment`. Requires `GH_TOKEN` / `GITLAB_TOKEN` and `REGRESSION_PR_REF`. |

**Working directory.** The user invokes from the test repo root (the directory containing `.regression/`). All paths below are relative to that root. Never `cd .regression && ...`; the workflow always uses `.regression/` as a prefix and runs `npx playwright test` from that subdirectory via `( cd .regression && npx playwright test ... )`.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

Use skill: `regression-preflight`.

In order; the first failure stops with the named remediation:

1. `docker version` and `docker compose version` succeed.
2. `.regression/services.yaml`, `.regression/flows.yaml`, `.regression/docker-compose.regression.yml`, `.regression/playwright.config.ts`, `.regression/package.json` all exist. Any missing -> "run `/task-regression-discover`".
3. `regression-preflight`: `docker info`, disk space at docker root, declared host port availability. Aggregated failures with named exit codes 20-22.
4. Required env vars (names declared in `.regression/.env.example`) resolvable. Resolution order: process env, then `.regression/.env`. List missing names only; never log values.
5. **No codemap/OpenAPI/sibling-repo read.**

The post-`up --wait` clock-skew check (`regression-preflight` exit code 23) fires inside Step 6 after the runner reports services healthy, not here.

### Step 2.5 - Resolve --rerun-failed (only when set)

When `--rerun-failed <runId>` is set, read `.regression/runs/<runId>/triage.json`. Missing -> abort with `task-regression: triage.json for run <runId> not found; cannot rerun-failed.` Compute the set of failing flow names (verdicts `real-bug` and `flake`) and pass them as `--grep '^(name1|name2|...)$'` to Playwright via `REGRESSION_PW_ARGS`. Mutually exclusive with `--grep`; both present -> abort.

### Step 3 - Resolve Compose Profile

Precedence (first hit wins):

1. `--profile` flag
2. `REGRESSION_PROFILE` env var
3. `CI=true` -> `pinned-images`
4. `local-build`

Surface the resolved profile and its source (`flag` / `env` / `ci-detect` / `default`) in the report header.

### Step 4 - Mint Run ID and Project Name

Use skill: `regression-data-isolation`.

Outputs `REGRESSION_RUN_ID`, sets compose project name to `regression-<runId>`, names ephemeral volumes, fixes `TZ=UTC`, and derives per-scenario tenant/user IDs from `run-id`. Two concurrent runs cannot collide on either the project name or scoped IDs.

### Step 5 - Install Teardown Trap

Install before any `docker compose up` so abnormal exits cannot leak containers/volumes. Trap fires on `EXIT`, `INT`, `TERM`. If `--keep-up` is set, the trap disarms only the `EXIT` (normal-success) path; `INT`/`TERM` still tear down so Ctrl+C is never a leak.

### Step 6 - Run Lifecycle

Use skill: `regression-runner`.

The runner does, in order:

1. `npm ci` in `.regression/` if `node_modules/` is missing or `package-lock.json` changed.
2. Sync `git`-sourced services into `.regression/.cache/<service>` at the ref declared in `services.yaml#source.ref` (mandatory for git sources; discovery rejects entries without it). Only under `local-build`; under `pinned-images`, git-sourced entries are skipped (the profile selects `image:` variants instead).
3. `docker compose -p regression-<runId> -f .regression/docker-compose.regression.yml --profile <profile> up -d --build --wait`. `--wait` plus per-service `condition: service_healthy` is the only startup gate. No `sleep`.
4. Apply seeds in lexicographic order (`00-init/`, `10-domain/`, `20-fixtures/`, `99-final/`) via the engine-native command from `regression-seed-strategy`. Fail-fast (`-v ON_ERROR_STOP=1` / `-b` / equivalent).
5. `( cd .regression && npx playwright test --reporter=junit,line )`. Forward `--grep`, `--workers`, `--retries` if provided. Continue on failure; no fail-fast.
6. Collect JUnit XML, traces, videos, screenshots into `.regression/reports/<runId>/`.

### Step 7 - Format Report

Use skill: `regression-report-format`.

Normalizes JUnit and triage output into `.regression/reports/<runId>/summary.md` with pass/fail/skip counts, per-flow verdict, failure clusters (collapsed by `(error-class, top-3-stack-frames)`), trace links, and a header surfacing the resolved profile + its source from Step 3.

### Step 8 - Triage Failures

Use skill: `regression-flakiness-triage` (only if there are failures).

Owns the classification (`real-bug` / `flake` / `infra` / `seed-drift`) and the rotting-suite threshold. Counts land at the top of `summary.md`.

### Step 9 - Teardown

Driven by the trap from Step 5:

- Default: `docker compose -p regression-<runId> down -v --remove-orphans`. Volumes go with the project.
- `--keep-up`: normal-exit teardown skipped. Print the project name and the exact cleanup command. Trap remains armed on `INT`/`TERM`.

### Step 10 - Exit Code

Exit non-zero iff Step 8 produced at least one `real-bug` verdict. `flake` / `infra` / `seed-drift` exit zero but are surfaced loudly in the report. CI gates on exit code; the report tells the human what to fix.

## Output Format

```markdown
# Regression Run Report

**Run ID:** regression-{runId}
**Profile:** {local-build | pinned-images} (source: {flag | env | ci-detect | default})
**Grep:** {tag or "all"}
**Started:** {ISO timestamp}
**Duration:** {wall-clock}

## Verdict

| Bucket | Count |
| --- | --- |
| Passed | {N} |
| Real bugs | {N} |
| Flakes | {N} |
| Infra | {N} |
| Seed-drift | {N} |
| Skipped | {N} |

**Exit code:** {0 | 1}  ({"clean" | "{N} real-bug failures"})

## Lifecycle

| Phase | Result | Wall-clock |
| --- | --- | --- |
| Preflight | pass | <1s |
| `npm ci` | skipped / ran | {N}s |
| Compose up --wait | {N} services healthy | {N}s |
| Seed | {N} files applied | {N}s |
| Playwright | {N} scenarios | {N}s |
| Report | summary.md written | <1s |
| Teardown | down -v --remove-orphans / skipped (--keep-up) | {N}s |

## Top failure clusters

1. {root error excerpt} - {N} occurrences - {flow names}
2. ...

## Artifacts

- `.regression/reports/{runId}/summary.md`
- `.regression/reports/{runId}/junit.xml`
- `.regression/reports/{runId}/traces/`

## Next

- Real bugs: open issues against the owning services.
- Flakes / infra / seed-drift: see triage section of summary.md.
- `--keep-up` set? Cleanup: `docker compose -p regression-{runId} down -v --remove-orphans`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: docker available; `.regression/` complete; `regression-preflight` cleared codes 20-22; env vars resolvable (process env, then `.regression/.env`); no codemap/OpenAPI/sibling-repo read.
- [ ] Step 2.5: when `--rerun-failed` set, triage.json loaded, failing flow names extracted, mutual exclusion with `--grep` enforced.
- [ ] Step 3: profile resolved with documented precedence; source recorded for the report header.
- [ ] Step 4: `regression-data-isolation` minted run-id and project name; volumes ephemeral; `TZ=UTC`; per-scenario IDs derived.
- [ ] Step 5: trap armed before Step 6; under `--keep-up` only `EXIT` is disarmed.
- [ ] Step 6: `regression-runner` ran with `--wait` + healthcheck gating (no `sleep`); git sources synced at the declared ref under `local-build` and skipped under `pinned-images`; seeds applied in order with fail-fast; Playwright executed with junit + line reporters; `--grep` / `--workers` / `--retries` forwarded verbatim; failures did not abort remaining scenarios.
- [ ] Step 7: `regression-report-format` produced `summary.md` with clusters, per-flow verdict, trace links, profile + source in header.
- [ ] Step 8: `regression-flakiness-triage` classified every failure; rotting-suite warning surfaced if its threshold was breached.
- [ ] Step 9: teardown fired via the trap (or normal-exit skipped under `--keep-up` with cleanup command printed).
- [ ] Step 10: exit non-zero iff at least one `real-bug` failure remained after Step 8.

## Avoid

- Reading codemap, OpenAPI, or sibling repos at runtime.
- `sleep`-based startup gating.
- Shared / persistent volumes across runs.
- Fail-fast on first scenario failure.
- Default-on retries.
- Failing the exit code on anything but `real-bug`.
- Skipping teardown on success (without `--keep-up`).
- `--keep-up` without printing the cleanup command, or without leaving the `INT`/`TERM` trap armed.
- Running app migrations from the seeder.
- Logging resolved env-var values.
