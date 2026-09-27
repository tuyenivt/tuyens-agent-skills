---
name: domain-behavioral-analysis
description: Mine git history per repo: hotspots by churn and size, temporal coupling of co-changing files, knowledge map of authors, recent-risk flows.
metadata:
  category: domain
  tags: [domain, git, hotspots, churn, temporal-coupling, knowledge-map, debt]
user-invocable: false
---

# Domain Behavioral Analysis

Reads each repository's history, read-only, and turns it into the evidence tables `debt/register.md`, `debt/recent-risk.md`, and the sizing section of `task-domain-ask` consume: where change concentrates, which files change together, and who holds the knowledge. Every number is computed from git; nothing is estimated.

## When to Use

- `task-domain-sync` Analyse pass
- `task-domain-ask` sizing a ticket: the files a change drags along and who to involve
- Standalone: one or more repos named by the user

## Inputs

| Input         | Required | Notes                                                                                                                       |
| ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| Repos         | yes      | `repos/<repo>/` directories, each a git checkout                                                                            |
| Window        | no       | Days; default `window` in `_index/sync-state.json`, else 30; anchored at the wall-clock date of the run                     |
| Reverse index | no       | `_index/file-to-flow.json`; a file it does not map, or every file when it is absent, reads `unmapped` in `Flows`              |
| Cards         | no       | The `**Monitors:**` line of every flow card, split on `;`, each entry read up to its ` - `; absent, `Monitor` reads `unknown - cards not supplied` |

## Rules

- **Paths are root-relative** before any lookup: every path git prints is prefixed with `repos/<repo>/`.
- **Exclusions are fixed, apply at any depth, and are printed:** `vendor/`, `node_modules/`, `dist/`, `build/`, `generated/`, `*.lock`, `*.min.*`, `*.snap`, `*.generated.*`, `*.sum`, `db/schema.rb`. Merge commits are skipped. Every command below carries the same exclusions.
- **Hotspot score = commits times lines.** Commits is the count over the whole history touching the file; lines is the current line count. Row every file whose `Register` is `yes`, plus the rest of the top ten per repo by score, grouped by repo and sorted by score descending, ties by path; `Register` is `yes` when the file's commits and lines are both at or above the repo's 90th percentile (nearest rank, over tracked files with at least one commit, after exclusions).
- **Temporal coupling** is a pair of currently tracked files changed in the same commit at least 5 times, over the whole history, where the shared count is at least 30 percent (raw, before rounding) of the commits of the lower-churn file, which is written as File B. A pair whose basenames differ only by a `test`, `spec`, or `_test` affix is excluded. `Flows` is the union of both files' flows.
- **Knowledge map** groups files by module: `<root>/<dir>` for a file under `app/`, `src/`, `lib/`, `internal/`, `cmd/`, `pkg/` (`app/services`), otherwise the top-level directory; files at the repo root or directly under a special root form no module. `Module` is repo-relative. Share is the author's distinct commits over the module's distinct commits, tested raw at 80 percent and shown rounded; a tie at the top is not a single point. The top three authors per module are listed; `Single point` is `yes` on the top author's row only, and a module with fewer than 5 distinct commits is listed but never rated `yes`. A module's `Flows` for the register is the union of the flows of its files.
- **Recent risk** lists every flow whose files were touched by 3 or more distinct commits in the window. `Monitor` is the first monitor on the flow's card, `none` when that line starts `none`, `unknown` when it starts `unknown` or `unavailable` or the cards were not supplied. Files the reverse index does not map are summed in the summary block, never rowed.
- **Nothing inferred about people.** Authors are named as git records them; no role, team, or availability is assumed.

## Patterns

### Commands

Run each inside the repo (`cd repos/<repo>`); `EXCL` is the exclusion list as any-depth pathspecs (`':(exclude)**/vendor/**'`, `':(exclude)**/*.lock'` and so on).

```
git log --no-merges --format=%H --name-only -- . EXCL                                  # churn, coupling
git log --no-merges --since="<window> days ago" --format=%h%x09%cs%x09%an --name-only -- . EXCL   # window
git shortlog -sn --no-merges HEAD -- <module> EXCL                                     # knowledge map
git ls-files -z -- . EXCL | while IFS= read -r -d '' f; do printf '%s\t%s\n' "$(wc -l < "$f")" "$f"; done   # lines, one file per line
```

`--since` and `%cs` both use the committer date, so a commit is inside or outside the window consistently.

Bad - a hotspot claimed from size alone:

```
| repos/orders/db/schema.rb | 1 | 900 | 900 | no | unmapped |
```

Good - churn and size both high, the score ranked, the register flag set by percentile:

```
| repos/orders/app/services/refund_service.rb | 5 | 62 | 310 | yes | payments/order-refund |
```

### Register rows

This skill is the only source of `hotspot`, `single point of knowledge`, and `coupling` rows in `debt/register.md`; cards never carry them. The consuming workflow turns every `Register: yes` hotspot, every `Single point: yes` author row, and every coupling pair into a register row: `Location` is `file:1`, the module, or `A with B`; `Signal` is the class with its numbers; `Trade-off made` is `none recorded`; `Cost today` is the observable consequence (change concentrates here; one person holds it; a change to A drags B); `Fix` is the structural change that would spread it; `Detection` is the monitor or review gate that would catch the next change there, `none` when there is none; `Flows` is the row's flows.

## Output Format

```
- **Repos:** {repo, repo}
- **Window:** {n} days, ending {date}
- **Excluded:** {the fixed list}
- **Unmapped changes in window:** {n} commits over {n} files
- **Thresholds:** coupling 5 shared commits and 30 percent; knowledge concentration 80 percent; register at the 90th percentile of commits and lines

## Hotspots

| File | Commits | Lines | Score | Register | Flows |
| ---- | ------- | ----- | ----- | -------- | ----- |

## Temporal coupling

| File A | File B | Shared commits | Share of B's commits | Flows |
| ------ | ------ | -------------- | -------------------- | ----- |

## Knowledge map

| Repo | Module | Author | Commits | Share | Single point |
| ---- | ------ | ------ | ------- | ----- | ------------ |

## Recent risk

| Flow | Commits ({window}d) | Monitor | Risk |
| ---- | ------------------- | ------- | ---- |
```

`Register` and `Single point` are `{yes | no}`; `Share` is a whole percent. `Risk` is `{high | medium | low}`: `high` when Monitor is `none` or `unknown`, `medium` with a monitor and 5 or more commits, `low` otherwise. An empty table keeps its header and one row `none - <evidence>`. The consuming workflow copies Recent risk into `debt/recent-risk.md` unchanged.

## Avoid

- Ranking by size or by churn alone
- Reporting a coupling pair below either threshold, or a test with its subject
- Naming a team or role for an author the history only names by commits
- Estimating a number git can compute
