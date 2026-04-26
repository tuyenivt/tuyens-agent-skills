# Tuyen's Agent Skills - Spec

Spec-Driven Development (SDD) plugin for Claude Code. Produces persistent per-feature artifacts under `.specs/<feature-slug>/` (`spec.md`, `clarifications.md`, `plan.md`, `tasks.md`, `analysis.md`, `checklist.md`) so requirements, plans, and task lists survive across sessions instead of living only in chat. The pipeline mirrors [GitHub Spec Kit](https://github.com/github/spec-kit): `constitution -> specify -> clarify -> plan -> tasks -> analyze -> implement` plus an optional `checklist`.

Depends only on the `core` plugin.

## Why SDD

The other plugins in this marketplace are a menu of independent workflows (`task-debug`, `task-code-review`, `task-spring-new`, ...). They take chat input, run, and emit chat output - the "spec" lives only in the user's head between commands. The `spec` plugin adds the missing glue: a linear pipeline whose phases produce named artifacts that the next phase consumes. Once a feature has a `spec.md` and `plan.md`, downstream stack workflows (`task-spring-new`, `task-react-new`, etc.) can consume them directly and skip their own gather/design phases.

## Artifact Convention

```
.specs/
  constitution.md            # optional, project-level (one per repo)
  <feature-slug>/
    spec.md                  # problem, users, stories, acceptance criteria, NFRs
    clarifications.md        # appended Q&A from clarify passes
    plan.md                  # architecture, data model, API, alternatives, risks
    tasks.md                 # ordered implementation tasks (data -> service -> API -> tests)
    analysis.md              # cross-artifact consistency report
    checklist.md             # requirements-quality checklist
    handoffs/                # (later phase) per-step agent handoff envelopes
    evaluation.md            # (later phase) test + spec coverage scoring
```

`.specs/` is chosen to mirror `.claude/` - it is unambiguously machine-managed. The `constitution.md` is project-wide (one per repo); every other artifact is per-feature. Slug derivation, path resolution, and lazy directory creation are handled by the `spec-artifact-paths` atomic so the convention is single-sourced.

## Operating Modes

Each workflow runs in one of two modes, decided by the `speckit-detect` atomic:

- **Speckit-installed** - when `.specify/` exists in the project (or Spec Kit owns artifacts), our workflow delegates to the corresponding `/speckit.*` command and acts as a thin pre/post-processor that injects this marketplace's atomics (`nfr-specification`, `tradeoff-analysis`, `review-blast-radius`, `behavioral-principles`) into the speckit flow. Spec Kit owns the artifacts.
- **Standalone** - when Spec Kit is not installed, our workflow drives the pipeline itself using the `.specs/<slug>/` artifact convention above.

Detection is evidence-based (marker files plus optional CLI presence on `$PATH`); see `speckit-detect` for the full decision table.

## Workflow Skills

Ten workflow skills covering the SDD pipeline, multi-agent orchestration, and post-implementation evaluation. (Scaffold in progress; skills land incrementally.)

| Skill                    | Description                                                                                           |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| `task-spec-constitution` | Generate or update `.specs/constitution.md` from existing standards skills + repo `CLAUDE.md`         |
| `task-spec-specify`      | Elicit requirements; write `spec.md` (problem, users, stories, acceptance criteria, NFRs)             |
| `task-spec-clarify`      | Re-read `spec.md`, surface ambiguities, append answers to `clarifications.md`, update `spec.md`       |
| `task-spec-plan`         | Read `spec.md` + `clarifications.md`; produce `plan.md` (architecture, data model, API, alternatives) |
| `task-spec-tasks`        | Read `plan.md`; produce ordered `tasks.md` (data -> service -> API -> tests)                          |
| `task-spec-analyze`      | Cross-check `spec <-> plan <-> tasks` for missing acceptance criteria, untested stories, gaps         |
| `task-spec-implement`    | Read `tasks.md`; delegate per-task to existing stack workflows in `--spec` mode; mark tasks complete  |
| `task-spec-checklist`    | Generate a requirements-quality checklist (clarity, testability, conflict-freeness) from `spec.md`    |

## Atomic Skills

Nine atomic skills provide focused patterns used by spec workflows and spec-aware consumers. Hidden from the slash menu (`user-invocable: false`).

| Skill                    | Description                                                                                                                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `speckit-detect`         | Detect whether Spec Kit is installed (`.specify/` directory or `speckit` CLI on `$PATH`); choose mode                                                                                                                    |
| `spec-artifact-paths`    | Resolve `.specs/<slug>/*` paths, derive slugs, create directories on first write                                                                                                                                         |
| `spec-review`            | Audit `spec.md` for unmeasurable acceptance criteria, missing NFR coverage, conflicting requirements                                                                                                                     |
| `spec-aware-preamble`    | Detect whether the current feature has `.specs/<slug>/` artifacts; emit a mode (`no-spec`, `spec-only`, `spec+plan`, `full-spec`) for stack workflows to branch on, replacing GATHER/DESIGN with spec-as-source-of-truth |
| `agent-handoff-contract` | Define the YAML envelope every agent step writes to `.specs/<slug>/handoffs/<NN>-<step>-<agent>.md` during orchestrated multi-agent runs - the filesystem is the orchestration bus                                       |
| `fix-loop-controller`    | Read the handoff directory after each step and decide loop / proceed / pause-for-amendment / escalate; enforces the iteration cap (default 3, hard cap 5)                                                                |
| `eval-test-runner`       | Detect the project's test command from the stack, run it with a timeout, parse output into structured pass/fail/coverage counts                                                                                          |
| `eval-spec-coverage`     | Map every acceptance criterion and NFR in `spec.md` to test/code evidence; emit per-criterion verdicts (covered / uncovered / violated / out-of-scope-drift)                                                             |
| `eval-scorer`            | Aggregate test, coverage, and review signals into a single 0-100 score plus `pass` / `needs-fix` / `fail` status; hard-fail signals (drift, AC violation) override the weighted score                                    |

## Spec-Aware Workflow Contract

Once a feature has artifacts under `.specs/<slug>/`, downstream workflows in other plugins can consume them. The contract:

> If a `spec.md` (and optionally `plan.md`, `tasks.md`) exists for the current feature, the workflow reads it first and skips its own GATHER/DESIGN phase. If not, the workflow behaves as it does today.

In practice this means stack workflows (`task-spring-new`, `task-python-new`, `task-react-new`, ...) gain an optional `--spec <slug>` mode. When invoked from `task-spec-implement`, they run in this mode and skip re-eliciting requirements. Beyond the `task-*-new` family, the same pattern extends to `task-code-test` (generate tests from acceptance criteria), `task-code-review` (cross-check the diff against the spec), `task-pr-create` (use spec summary as PR description), and `task-debug` (distinguish spec violations from spec gaps).

When a spec-aware workflow finds a proposed change that conflicts with an NFR or touches an out-of-scope item, it must **stop and surface the conflict** rather than silently proceeding. Spec is the source of truth; the discipline is what keeps that from becoming lip service.

## Cross-Plugin Integration (Soft Suggestions)

`spec` deliberately depends only on `core`, so installing this plugin never forces `architecture` or `delivery` to come along. When a user does have those plugins installed, spec workflows offer soft suggestions rather than hard dependencies:

- `task-spec-plan` may suggest invoking `task-adr-create` (in `architecture`) for high-impact decisions captured during planning, but never calls it directly.
- `task-spec-tasks` performs its own task breakdown using core atomics (`review-change-risk`, `review-blast-radius`, `dependency-impact-analysis`, `ops-backward-compatibility`, `backend-db-migration`, `ops-feature-flags`); it does not call `task-scope-breakdown` (in `delivery`). The user may run `task-scope-breakdown` separately for sprint-level planning.

The pattern: detect whether the other workflow is available, suggest it, let the user opt in.

## Usage

Typical standalone-mode flow for a new feature:

```
/task-spec-specify "User profile avatar upload"
  -> writes .specs/user-profile-avatar-upload/spec.md

/task-spec-clarify user-profile-avatar-upload
  -> appends to clarifications.md, updates spec.md

/task-spec-plan user-profile-avatar-upload
  -> writes plan.md

/task-spec-tasks user-profile-avatar-upload
  -> writes tasks.md

/task-spec-implement user-profile-avatar-upload
  -> runs each task via the appropriate stack workflow in --spec mode
```

In speckit-installed projects, the same commands delegate to `/speckit.specify`, `/speckit.clarify`, etc., with our atomics injected as pre/post-processors.
