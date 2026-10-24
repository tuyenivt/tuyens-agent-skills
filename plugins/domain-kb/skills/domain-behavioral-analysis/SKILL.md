---
name: domain-behavioral-analysis
description: "Mine git history per repo: hotspots by churn and size, temporal coupling of co-changing files, knowledge map of authors, recent-risk flows."
metadata:
  category: domain
  tags: [domain, git, hotspots, churn, temporal-coupling, knowledge-map, debt]
user-invocable: false
---

# Domain Behavioral Analysis

> Load `Use skill: domain-kb-layout` first and read at least its Rules and these Patterns sections: Flow card (Where to watch), Generated-file frontmatter, CLAUDE.md (`## Repos`), Indexes, Stale marking, and the Ledger, playbook, contracts, debt, surfaces entry for `debt/register.md` and `debt/recent-risk.md`. It owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Reads each repository's history, read-only, and turns it into the evidence tables `debt/register.md`, `debt/recent-risk.md`, and the sizing section of `task-domain-ask` consume: where change concentrates, which files change together, and who holds the knowledge. Every number is computed from git; nothing is estimated.

## When to Use

- `task-domain-sync` Analyse pass
- `task-domain-ask` sizing a ticket: the files a change drags along and who to involve
- Standalone: one or more repos named by the user

## Inputs

| Input         | Required | Notes                                                                                                                       |
| ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| Repos         | yes      | `repos/<repo>/` directories, each a git checkout, each with its scope: the `include=` part of its `Scope` cell from `CLAUDE.md` `## Repos` with table escapes removed (`\|` read as a pipe), `all` when absent; standalone, the scope the user names, else that cell |
| Window        | no       | Days; default `window` in `_index/sync-state.json`, else 30; anchored at the wall-clock date of the run                     |
| Reverse index | no       | `_index/file-to-flow.json`; a file it does not map, or every file when it is absent, reads `unmapped` in `Flows`; a file's flows, and a union over several files, are written sorted by id and joined with `, `; a union lists `unmapped` only when none is mapped |
| Cards         | no       | The `**Monitors:**` line of every flow card, split on `; `, each entry read up to its ` - ` or ` (from`, with the flow's `ranked_by` from `_index/priority.json` (`unranked` when the file does not list it); absent, `Monitor` reads `unknown - cards not supplied` |
| Targets       | no       | Root-relative files a ticket would change (sizing); adds the `## Drag-along` and `## Who to involve` sections |

## Rules

- **Paths are root-relative** before any lookup: every path git prints is prefixed with `repos/<repo>/`. Every command runs with `-c core.quotePath=false`; a path git still quotes (one holding a control character, a double quote, or a backslash; C-style escapes, octal included) is unquoted before use, and the line-count output splits at its last `:`. History is read at each repo's checkout, the working tree as it stands.
- **Scope filters output, never arguments.** An `include=<regex>` scope is applied by keeping only the repo-relative paths the regex matches in each command's output; `all` keeps every path. Percentiles, coupling, and modules are computed over in-scope files only, and the scope is printed next to the exclusions.
- **Exclusions are fixed, apply at any depth, and are printed:** `vendor/`, `node_modules/`, `dist/`, `build/`, `generated/`, `*.lock`, `package-lock.json`, `pnpm-lock.yaml`, `npm-shrinkwrap.json`, `*.min.*`, `*.snap`, `*.generated.*`, `*.sum`, `db/schema.rb`, binary files, symlinks, and submodule gitlinks (a path the line-count command does not list, a deleted or empty file included, and a path no non-merge commit touches, one only a merge commit added, are dropped from every table, every module count, and the summary's unmapped line). Merge commits are skipped. Renames are not followed (`--no-renames`: a renamed file's commits stay with each path), and the header says so. A repo with no history of its own (`git -C repos/<repo> rev-parse --show-toplevel` is not that directory, an uninitialised submodule, or `rev-parse --verify -q HEAD` fails, an unborn HEAD) is left out of the history tables and the unmapped line, its Scope entry reads `{repo}: no history - not analysed`, and it is named under `Limits`; that check runs first, since inside an uninitialised submodule every `rev-parse` answers for the root; a shallow clone (`rev-parse --is-shallow-repository` prints `true`) is then left out the same way, as `{repo}: shallow - not analysed`.
- **Hotspot score = commits times lines.** Commits is the count over the whole history touching the file; lines is the current line count. Row every file whose `Register` is `yes`, plus the rest of the top ten per repo by score, grouped by repo in input order and sorted by score descending, ties by commits descending then path; `Register` is `yes` when the file has at least 5 commits and its commits and lines are both at or above the repo's 90th percentile (nearest rank, over the in-scope files the tables keep).
- **Temporal coupling** is a pair of files the tables keep, changed in the same commit at least 5 times, over the whole history, counting only commits whose churn-log entry lists 30 or fewer paths after the scope filter (the one 30-file cap; the log's own paths, deleted ones included), where the shared count is at least 30 percent (raw) of the lower-churn file's commits counted over those same commits, that file being File B (the later path when both are equal); `Share of B's commits` is a whole percent. A pair is excluded when one file's basename carries a test marker as a whole word part (`_test`, `_spec`, `test_`, `.test`, `.spec`, a `Test` or `Spec` suffix) and the other's basename, both compared without extensions, equals it with the marker removed, or when the two basenames are equal and one file sits under a `test`, `tests`, `spec`, or `__tests__` directory. `Flows` is the union of both files' flows; rows sort by shared commits descending, then File A path, then File B path.
- **Knowledge map** groups files by module: a file at the repo root, directly under `app/`, `src/`, `lib/`, `internal/`, `cmd/`, `pkg/`, or directly under a `src/main/<x>/` or `src/test/<x>/` segment at any depth, forms no module; otherwise the module is the file's directory, the directories above the segment included, when its path has a `src/main/<x>/` or `src/test/<x>/` segment at any depth, `<x>` any directory name (`svc/src/main/java/com/acme/orders/Refund.java` -> `svc/src/main/java/com/acme/orders`), else `<root>/<dir>` for a file inside a subdirectory of `app/`, `src/`, `lib/`, `internal/`, `cmd/`, `pkg/` (`app/services/x.rb` -> `app/services`), else the top-level directory. `Module` is repo-relative. Every module is listed, rows grouped by repo in input order, then by module path, then by share descending. Share is the author's distinct commits over the module's distinct commits, a single point when it is at or above 80 percent raw, shown as a whole percent. The top three authors per module are listed, ties going to the author with the newest `%cs`, then author name ascending, rows of equal share in that same order; `Single point` is `yes` on the top author's row only, and a module with fewer than 5 distinct commits is listed but never rated `yes`. `Flows` is the union of the flows of the module's files.
- **Recent risk** lists every flow whose mapped files were touched by 3 or more distinct commits in the window, counted across every repo the flow spans. `Monitor` is the first monitor on the flow's card, `none` when that line starts `none`, `unknown` when it starts `unknown` or `unavailable` or the cards were not supplied (`unknown - cards not supplied`). A commit that touches an unmapped in-scope file the line-count command lists counts toward the summary's unmapped line, whatever else it touches; unmapped files are never rowed; rows sort by commits descending, then flow id. The window is the commits whose `%cs` date is after the run date minus the window days (a 30-day window ending 2026-10-01 starts 2026-09-02), filtered from the window log's output; test and spec files are excepted from the unmapped line, as in the layout's Unmapped changes; with no reverse index the line reads `n/a - no reverse index`.
- **Sizing.** With Targets, `## Drag-along` rows every file coupled to a target by the coupling rule, its share being the shared commits over the drag-along file's own commits, both counted as for coupling and written as a whole percent, and a target with no coupled file one row `| {target} | none - no coupled file | | |`; `## Who to involve` lists each top author once with every module (written `repos/<repo>/<module>`, so modules of different repos never collide) a target or drag-along file sits in that they lead (a file with no module by its own top author), and a target with no history in the tables (no non-merge commit, or a path the tables do not keep) as `- none - no history: {target}`. Drag-along rows sort by target, then shared commits descending, then file path; Who to involve by author name, each author's modules and files by path.
- **Nothing inferred about people.** Authors are named as git records them (`%an`, no mailmap); no role, team, or availability is assumed.

## Patterns

### Commands

Run each with `git -C repos/<repo> -c core.quotePath=false`; `EXCL` is the exclusion list as any-depth glob pathspecs (`':(exclude,glob)**/vendor/**'`, `':(exclude,glob)**/*.lock'`, `':(exclude,glob)**/db/schema.rb'` and so on; without `glob` magic a leading `**/` misses the repo root), and every output path is filtered by the scope.

```
log --no-merges --no-renames --full-history --format=%x00%H%x09%an%x09%cs --name-only -- . EXCL   # churn, coupling, knowledge map
log --no-merges --no-renames --full-history --format=%x00%h%x09%cs --name-only -- . EXCL          # window, filtered on %cs
grep --no-color --no-recurse-submodules -I -c '' -- . EXCL                                    # lines per text file: path:count
```

The window is filtered on `%cs`, not `--since`, which compares at the current time of day. `-I` skips binary files; with `--no-recurse-submodules` (overriding a `submodule.recurse` config) `git grep` lists no gitlink, no file inside a submodule, and no symlink; an empty file has no count and no row.

Bad - a hotspot claimed from size alone:

```
| repos/orders/app/models/order.rb | 1 | 900 | 900 | yes | unmapped |
```

Good - churn and size both high, the score ranked, the register flag set by percentile:

```
| repos/orders/app/services/refund_service.rb | 5 | 62 | 310 | yes | payments/order-refund |
```

### Register rows

This skill is the only source of `hotspot`, `single point of knowledge`, and `coupling` rows in `debt/register.md`; they are register-only classes that cards never carry. The consuming workflow turns every `Register: yes` hotspot, every `Single point: yes` author row, and every coupling pair into a register row: `Id` is the prior register row's id per the layout's Ids rule (same `Location`, same `Signal` class), else `D-new`; `Location` is `file:1`, the module as `repos/<repo>/<module>`, or `A with B` with the two paths in path order; `Signal` is the class with its numbers; `Severity` is `high` when the row's flows include one whose `ranked_by` in `_index/priority.json` is `moves money`, else `medium` (`medium` when cards were not supplied); `Category` is `architecture`; `Trade-off made` is `none recorded`; `Cost today` is the observable consequence (change concentrates here; one person holds it; a change to A drags B); `Fix` is the structural change that would spread it (`split <file> by responsibility`, `share <module> across authors`, `extract the seam between <A> and <B>`); `Detection` is the first monitor on the card of the row's first flow (`Flows` sorted by id), `none` when that line starts `none`, `unknown` when it starts `unknown` or `unavailable` or the cards were not supplied, `none - no card` when the row's `Flows` is `unmapped`; `Doc` is left `none` for the Link pass; `Flows` is the row's flows.

## Output Format

```
- **Repos:** {repo, repo}
- **Window:** {n} days, ending {date}
- **Scope:** {repo: all ({n} files) | repo: include=<regex> ({n} files in, {n} out) | repo: shallow - not analysed | repo: no history - not analysed}, ...
- **Excluded:** {the fixed list}
- **Unmapped changes in window:** {{n} commits over {n} files | n/a - no reverse index}
- **Thresholds:** coupling 5 shared commits and 30 percent; knowledge concentration 80 percent; register at the 90th percentile of commits and lines, 5 commits at least; single point needs a module with 5 commits; coupling counts only commits touching 30 or fewer in-scope paths
- **Limits:** renames not followed{; shallow: <repo>, <repo>}{; no history: <repo>, <repo>}

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

- {author} - {module | file} ({share} percent of its commits){, {module | file} ({share} percent of its commits)}
- none - no history: {target}                            {only for a target with no history}
```

`Register` and `Single point` are `{yes | no}`; `Share`, `Share of B's commits`, and a drag-along share are whole percents, rounded half up (`62.5` -> `63`), written without a `%` sign; a Who to involve share is the author's Knowledge map `Share` for a module and, for a file with no module, the author's distinct commits over the file's, a whole percent rounded the same way, the top author picked by the Knowledge map's tie-breaks. `Risk` is `{high | medium | low}`: `high` when Monitor starts `none` or `unknown`, `medium` with a monitor and 5 or more commits, `low` otherwise. An empty table keeps its header and one row whose first cell reads `none - <evidence>` and whose other cells are empty. The Scope line's file counts are tracked (`git ls-files`) in-scope files after the exclusions and drops the tables apply, so the counts and the percentile population are one set; `out` counts the tracked files the regex does not match that the exclusions and drops would keep, judged on the commands' output before the scope filter. The consuming workflow copies Recent risk into `debt/recent-risk.md` unchanged.

## Avoid

- Ranking by size or by churn alone
- Naming a team or role for an author the history only names by commits
