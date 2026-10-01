---
name: domain-behavioral-analysis
description: "Mine git history per repo: hotspots by churn and size, temporal coupling of co-changing files, knowledge map of authors, recent-risk flows."
metadata:
  category: domain
  tags: [domain, git, hotspots, churn, temporal-coupling, knowledge-map, debt]
user-invocable: false
---

# Domain Behavioral Analysis

> Load `Use skill: domain-kb-layout` first: it owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Reads each repository's history, read-only, and turns it into the evidence tables `debt/register.md`, `debt/recent-risk.md`, and the sizing section of `task-domain-ask` consume: where change concentrates, which files change together, and who holds the knowledge. Every number is computed from git; nothing is estimated.

## When to Use

- `task-domain-sync` Analyse pass
- `task-domain-ask` sizing a ticket: the files a change drags along and who to involve
- Standalone: one or more repos named by the user

## Inputs

| Input         | Required | Notes                                                                                                                       |
| ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| Repos         | yes      | `repos/<repo>/` directories, each a git checkout, each with its scope: the `include=` part of its `Scope` cell from `CLAUDE.md` `## Repos` with table escapes removed (`\|` is `|`), `all` when absent |
| Window        | no       | Days; default `window` in `_index/sync-state.json`, else 30; anchored at the wall-clock date of the run                     |
| Reverse index | no       | `_index/file-to-flow.json`; a file it does not map, or every file when it is absent, reads `unmapped` in `Flows`              |
| Cards         | no       | The `**Monitors:**` line and the frontmatter `ranked_by` of every flow card, the line split on `; `, each entry read up to its ` - `; absent, `Monitor` reads `unknown - cards not supplied` |
| Targets       | no       | Files a ticket would change (sizing); adds the `## Drag-along` and `## Who to involve` sections |

## Rules

- **Paths are root-relative** before any lookup: every path git prints is prefixed with `repos/<repo>/`. Every command runs with `-c core.quotePath=false`.
- **Scope filters output, never arguments.** An `include=<regex>` scope is applied by keeping only the repo-relative paths the regex matches in each command's output; `all` keeps every path. Percentiles, coupling, and modules are computed over in-scope files only, and the scope is printed next to the exclusions.
- **Exclusions are fixed, apply at any depth, and are printed:** `vendor/`, `node_modules/`, `dist/`, `build/`, `generated/`, `*.lock`, `*.min.*`, `*.snap`, `*.generated.*`, `*.sum`, `db/schema.rb`, binary files, and submodule gitlinks (a path the line-count command does not list is dropped from every table). Merge commits are skipped. Renames are not followed, and the header says so. A shallow clone (`rev-parse --is-shallow-repository` prints `true`) is left out of the history tables and named in the header.
- **Hotspot score = commits times lines.** Commits is the count over the whole history touching the file; lines is the current line count. Row every file whose `Register` is `yes`, plus the rest of the top ten per repo by score, grouped by repo in input order and sorted by score descending, ties by commits then path; `Register` is `yes` when the file has at least 5 commits and its commits and lines are both at or above the repo's 90th percentile (nearest rank, over in-scope tracked files with at least one commit, after exclusions).
- **Temporal coupling** is a pair of currently tracked files changed in the same commit at least 5 times, over the whole history, counting only commits that touch 30 in-scope files or fewer, where the shared count is at least 30 percent (raw) of the commits of the lower-churn file, which is written as File B (the later path when both have equal churn); `Share of B's commits` is a whole percent. A pair is excluded when one file's basename carries a test marker as a whole word part (`_test`, `_spec`, `test_`, `.test`, `.spec`, a `Test` or `Spec` suffix) and the other's basename equals it with the marker and extensions removed. `Flows` is the union of both files' flows.
- **Knowledge map** groups files by module: `<root>/<dir>` for a file at least two levels under `app/`, `src/`, `lib/`, `internal/`, `cmd/`, `pkg/` (`app/services/x.rb` -> `app/services`), the file's directory under a `src/main/<lang>/` or `src/test/<lang>/` root, otherwise the top-level directory; a file at the repo root or directly under a special root forms no module. `Module` is repo-relative. Every module is listed. Share is the author's distinct commits over the module's distinct commits, a single point when it is at or above 80 percent raw, shown rounded. The top three authors per module are listed, ties going to the author with the newest commit; `Single point` is `yes` on the top author's row only, and a module with fewer than 5 distinct commits is listed but never rated `yes`. `Flows` is the union of the flows of the module's files.
- **Recent risk** lists every flow whose mapped files were touched by 3 or more distinct commits in the window, counted across every repo the flow spans. `Monitor` is the first monitor on the flow's card, `none` when that line starts `none`, `unknown` when it starts `unknown` or `unavailable` or the cards were not supplied (`unknown - cards not supplied`). A commit that touches an unmapped in-scope file counts toward the summary's unmapped line, whatever else it touches; unmapped files are never rowed. The window is the commits whose `%cs` date is after the run date minus the window days (a 30-day window ending 2026-10-01 starts 2026-09-02), filtered from the window log's output; test and spec files are excepted from the unmapped line, as in the layout's Unmapped changes.
- **Sizing.** With Targets, `## Drag-along` rows every file coupled to a target by the coupling rule, its share being the shared commits over the drag-along file's own commits; `## Who to involve` lists each top author once with every module, target, or drag-along file they lead (a file with no module by its own top author; a target with no history reads `none - no history`).
- **Nothing inferred about people.** Authors are named as git records them (`%an`, no mailmap); no role, team, or availability is assumed.

## Patterns

### Commands

Run each with `git -C repos/<repo> -c core.quotePath=false`; `EXCL` is the exclusion list as any-depth glob pathspecs (`':(exclude,glob)**/vendor/**'`, `':(exclude,glob)**/*.lock'`, `':(exclude,glob)**/db/schema.rb'` and so on; without `glob` magic a leading `**/` misses the repo root), and every output path is filtered by the scope.

```
log --no-merges --format=%x00%H%x09%an --name-only -- . EXCL                      # churn, coupling, knowledge map
log --no-merges --format=%x00%h%x09%cs%x09%an --name-only -- . EXCL                 # window, filtered on %cs
grep -I -c '' -- . EXCL                                                          # lines per text file: path:count
```

The window is filtered on `%cs`, not `--since`, which compares at the current time of day. `grep -I` skips binary files and gitlinks; an empty file has no count and no row.

Bad - a hotspot claimed from size alone:

```
| repos/orders/app/models/order.rb | 1 | 900 | 900 | yes | unmapped |
```

Good - churn and size both high, the score ranked, the register flag set by percentile:

```
| repos/orders/app/services/refund_service.rb | 5 | 62 | 310 | yes | payments/order-refund |
```

### Register rows

This skill is the only source of `hotspot`, `single point of knowledge`, and `coupling` rows in `debt/register.md`; they are register-only classes that cards never carry. The consuming workflow turns every `Register: yes` hotspot, every `Single point: yes` author row, and every coupling pair into a register row: `Id` is `D-new`; `Location` is `file:1`, the module as `repos/<repo>/<module>`, or `A with B`; `Signal` is the class with its numbers; `Severity` is `high` when the row's flows include one whose card `ranked_by` is `moves money`, else `medium` (`medium` when cards were not supplied); `Category` is `architecture`; `Trade-off made` is `none recorded`; `Cost today` is the observable consequence (change concentrates here; one person holds it; a change to A drags B); `Fix` is the structural change that would spread it; `Detection` is the monitor or review gate that would catch the next change there, `none` when there is none; `Doc` is left `none` for the Link pass; `Flows` is the row's flows.

## Output Format

```
- **Repos:** {repo, repo}
- **Window:** {n} days, ending {date}
- **Scope:** {repo: all | include=<regex> ({n} files in, {n} out)}, ...
- **Excluded:** {the fixed list}
- **Unmapped changes in window:** {n} commits over {n} files
- **Thresholds:** coupling 5 shared commits and 30 percent; knowledge concentration 80 percent; register at the 90th percentile of commits and lines, 5 commits at least; single point needs a module with 5 commits; coupling ignores commits touching more than 30 files
- **Limits:** renames not followed{; shallow: <repo>, <repo>}

## Hotspots

| File | Commits | Lines | Score | Register | Flows |
| ---- | ------- | ----- | ----- | -------- | ----- |

## Temporal coupling

| File A | File B | Shared commits | Share of B's commits | Flows |
| ------ | ------ | -------------- | -------------------- | ----- |

## Knowledge map

| Repo | Module | Author | Commits | Share | Single point | Flows |
| ---- | ------ | ------ | ------- | ----- | ------------ | ----- |

## Recent risk

| Flow | Commits ({window}d) | Monitor | Risk |
| ---- | ------------------- | ------- | ---- |

## Drag-along                                          {only with Targets}

| Target | File | Shared commits | Share of the file's commits |
| ------ | ---- | -------------- | --------------------------- |

## Who to involve                                       {only with Targets}

- {author} - {module} ({share} of its commits)
```

`Register` and `Single point` are `{yes | no}`; `Share` is a whole percent. `Risk` is `{high | medium | low}`: `high` when Monitor starts `none` or `unknown`, `medium` with a monitor and 5 or more commits, `low` otherwise. An empty table keeps its header and one row whose first cell reads `none - <evidence>` and whose other cells are empty. The consuming workflow copies Recent risk into `debt/recent-risk.md` unchanged.

## Avoid

- Ranking by size or by churn alone
- Reporting a coupling pair below either threshold, or a test with its subject
- Naming a team or role for an author the history only names by commits
- Estimating a number git can compute
- Computing a percentile over files the repo's scope excludes
