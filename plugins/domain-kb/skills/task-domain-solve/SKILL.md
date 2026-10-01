---
name: task-domain-solve
description: "Turn a ticket or problem into a cited analysis file and a self-contained implementation super-prompt, stack-detected per target repo."
metadata:
  category: domain
  tags: [domain, knowledge-base, solve, ticket, analysis, super-prompt, implementation-plan]
  type: workflow
user-invocable: true
---

# Domain Solve

Reads a ticket or problem statement against both layers of the knowledge base, writes an analysis of what is happening and why, pushes back where the ask is unclear or wrong, and writes one prompt another agent can run end to end in the target repo: skills to invoke, rules to respect, steps, tests, a delegated self-review, and a stop before commit. It writes two files and changes nothing in `repos/`.

## When to Use

- A ticket, bug report, or feature ask needs to become an implementation plan grounded in the documented flows and rules
- A problem statement needs its root cause or constraints named before anyone writes code

**Not for:** answering a question or sizing a ticket without a plan (`task-domain-ask`); implementing the change itself, which the super-prompt's runner does; building the knowledge base (`task-domain-sync`).

## Inputs

| Input            | Required | Notes                                                                                                                                      |
| ---------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Text or `--in <file>` | yes | The ticket or problem, inline or read from the file; a bare tracker URL is not fetched, the workflow asks for the text and stops           |
| `--out <file>`   | no       | The analysis path; default `tmp/<name>-out.md`, `<name>` being the `--in` file name without its extension, or `solve` for inline text       |
| `--prompt <file>` | no      | The super-prompt path; default `tmp/<name>-prompt.md` on the same rule                                                                     |
| `--base <branch>` | no      | The base branch for the runner's branch, diff, and PR draft; default per Step 4                                                            |
| `--repo <name>`  | no       | The target repo under `repos/`; absent, inferred in Step 4                                                                                 |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate the knowledge base and its configuration

Use skill: `domain-kb-layout` for every path, section, and empty form named below. A text that is only a tracker URL stops with `paste the ticket text - URLs are not fetched`. The root is the working directory. `_index/sync-state.json` recording `in_progress` stops with `sync interrupted at {command}:{pass} - run task-domain-sync to finish`. The generated layer exists when `sync-state.json` records a `sha`, the curated layer when any curated folder holds a Markdown file; with neither, stop with `no knowledge base here - run task-domain-sync init or import`; with one, the console's Layers line names it. Read `CLAUDE.md` `## Solve` (every key; a missing section, key, or `unknown - set in CLAUDE.md ## Solve` value takes the default this workflow states, and the console's Defaults line names it), `## Precedence`, `## Audience` (`Language:` default `en`; the first code is the language of both files), and `## Repos`; read `--in` when given.

### Step 3 - Retrieve and fact-check

Split the text into items, one per distinct change it asks for (its numbered items when it has them). For each item retrieve the flows it touches (through the inventories, the glossary, the cards' Story lines, and `_index/file-to-flow.json`) with their state changes, side effects, Rules, and Failure modes; the register rows whose `Signal` starts `coupling` on files those flows share; the `contracts/` callers (`consumers/` docs when `contracts/` does not exist); and every curated doc naming the item's surfaces, entities, or terms, `patterns/` included, searched in every Audience language.

Every cited `file:line` is read at the repo's checkout `HEAD` (which may be ahead of the card's `sources`): `verified`, `moved` (same code at another line), or `gone`; a curated citation takes its ATLAS `## Citation drift` status when listed there. A `gone` citation is not evidence but a documentation gap naming the stale card or doc. A curated doc is `documented` when `active`, `inferred` when `draft`, and replaced by its `superseded_by` target when `deprecated`. A card row and a doc that disagree are a documentation gap, settled by `## Precedence` (an unranked folder sits below generated cards; a `verified` or `moved` card citation outranks any doc). A surface no card and no doc covers is `not found in docs`.

Size each item, the largest whose condition holds: `S` for one flow and no coupling row; `M` for two or three flows, or one coupling row; `L` for four or more flows, or two or more coupling rows; `L - new surface` when no flow matches; an item that contradicts a `documented` rule moves up one size (`L` stays `L`). The ticket's size is its largest item's, `L - new surface` ranking above `L`.

### Step 4 - Target repo, base, and stack

The target is `--repo`, else the repo holding the most cited `file:line` among the changes the items touch; when repos tie, or no change has a citation, the workflow lists the candidate repos and asks, and continues only once answered. Every other repo with a change is an `Other repos` entry for its own `--repo` run. The base is `--base`, else the target's tracked `branch` in `sync-state.json` (the `## Repos` `Branch` cell), else `## Solve` `Base branch`, else `main`; the base ref is `origin/{base}` when `git -C repos/<target> rev-parse --verify --quiet origin/{base}` succeeds, else `{base}`. Use skill: `stack-detect` applied to `repos/<target>/` (its instruction files and marker-file table there, not the root); the block is surfaced only through the analysis's `**Stack:**` line as `{Language} / {Framework}, tests: {Test framework}, db: {Database}`. It runs here, not as Step 2, because the target is known only after retrieval.

### Step 5 - Analyse

Fill the analysis sections from the retrieved rows and docs only: the observed behaviour and the hop or rule producing it, cited; the flows; the constraints (`documented` rules quoted with doc path or ledger id, callers, incidents on the path, governing `patterns/` docs); the gaps in their three forms. A root cause the rows do not confirm takes the `unconfirmed:` form. Nothing is inferred from how such systems usually work.

### Step 6 - Pushback

Only when warranted: one entry per concern in the template's shape, naming the ticket item it concerns. A `rule-violation` is a change that breaks a documented rule the ticket does not set out to change, and cites the rule; a ticket that sets out to change a rule is not one, and its pushback names the rule's doc as needing the same change; a `mistaken-assumption` quotes the ticket line and the row that contradicts it. An item whose requested change is `unclear` or a `rule-violation` is blocked: the super-prompt does not implement it and lists it under Constraints; a `mistaken-assumption` about the cause blocks nothing, since the plan follows the analysed cause. When every item is blocked, no super-prompt is written: the console's Prompt line reads `not written - every item is blocked on owner` and Next reads `answer the pushback questions, then run task-domain-solve again`.

### Step 7 - Write the analysis

Write `--out` in the analysis shape, creating its directory when absent.

### Step 8 - Write the super-prompt

Write `--prompt` per the super-prompt contract. Repo file paths in it are relative to `repos/{target}`; knowledge-base docs and cards are cited by root-relative path and quoted inline; the `## Solve` `PR draft path` (default `tmp/pr.md`) is resolved against the knowledge-base root and written absolute. Skills to invoke: the `## Solve` `Implement skill` and `Test skill` when set, then `core` atomics by what the change touches (`core:backend-db-migration` for a schema change, `core:backend-idempotency` for a retried or webhook-driven write, `core:backend-transaction-patterns` for a write that moves money or spans services, `core:backend-api-guidelines` and `core:ops-backward-compatibility` for a route, request, or response change, `core:ops-release-safety` for a change behind a flag or with a rollout, any other `core` atomic whose concern the change names), at most five in total, each with a one-line reason; when `Implement skill` or `Test skill` is unset, the section adds `defaults used - set CLAUDE.md ## Solve to name project skills`. The `## Solve` `Review skill` reviews committed code, so the runner never invokes it; section 10 names it as the user's step after committing, and omits the line when it is unset. The `Conventions file`, a path from the knowledge-base root written repo-relative in the prompt, is the first file to read and binding; unset, the line reads `no conventions file configured`; set but absent from the repo, `conventions file not found: <path>`. The `Test command` is copied verbatim; unset, the section reads `test command not configured - use the framework's default runner` and names the `Test framework` from Step 4.

## Output Format

Console:

```
## Domain solve

- **Problem:** {one line}
- **Layers:** {both | generated only | curated only}
- **Repo:** repos/{target} @ {base ref}
- **Other repos:** {repo - the change it needs, ... | none}
- **Flows:** {<capability>/<flow>, ...}
- **Docs:** {curated paths | none - not found in docs}
- **Size:** {S | M | L | L - new surface} - {reason, with each item's size}
- **Pushback:** {n} items ({n} ticket items blocked)
- **Skills:** {skill, skill, ...}
- **Defaults:** {each `## Solve` key that fell back, with the value used | none}
- **Analysis:** {--out path}
- **Prompt:** {--prompt path | not written - every item is blocked on owner}
- **Next:** {run the prompt in repos/{target}; it stops before commit | answer the pushback questions, then run task-domain-solve again}
```

Analysis file (`--out`):

```markdown
# Analysis: {ticket title or first line}

- **Stack:** {Language} / {Framework}, tests: {Test framework}, db: {Database}
- **Repo:** repos/{target}
- **Size:** {S | M | L | L - new surface} - {reason}

## What is happening and why

{prose, every claim cited as `(<capability>/<flow> <section> - file:line ({verified | moved}))` or `(doc <path> <section>)`}

## Services and flows

| Flow | Trigger | Repos | Changes on this path |
| ---- | ------- | ----- | -------------------- |

## Root cause or constraints

- {rule or constraint} - {doc path | ledger R-n | card row} ({verified | moved | n/a})
- unconfirmed: {suspected cause} - {what would confirm it}

## Callers and coupling

- {contracts/<caller> or consumers/<name> - surfaces used | register D-n - files dragged}

## Documentation gaps

- not found in docs: {what}
- stale: {card or doc} - {file:line} gone
- drift: {doc path} says {doc text}; {card row} ({verified | moved}) says {card text}

## Pushback

- **Category:** {unclear | mistaken-assumption | gap | security | performance | rule-violation | blast-radius | other}
  - **Item:** {n}{ - blocked}
  - **Evidence:** {doc path or row | judgment call - needs owner confirmation}
  - **Question for owner:** {question}
  - **Impact if ignored:** {sentence}
```

A list section with nothing to list reads `- none - <evidence>` (`- none - no caller or coupling row`, `- none - every surface is documented`, `- none - the docs settle every concern`); a table keeps its header and one `none - <evidence>` row.

Super-prompt file (`--prompt`): the file is the prompt. No fence wraps it, no heading names it a prompt, and it holds exactly these eleven numbered sections in order, each a `## {n}. {Title}` heading:

1. **Role and repository**: the runner works in `repos/{target}` on a new branch off `{base ref}`, as an engineer on this system, and changes no other repo.
2. **Skills to invoke**: at most five `Use skill:` lines with a one-line reason each, chosen per Step 8, with the defaults line when it applies; the section 3 Stack line is the stack-detect result these skills ask for.
3. **Context**: the `**Stack:**` line; the conventions line; the files the change touches; every domain rule the change must respect, quoted with its doc path or ledger id; every `patterns/` doc that governs the code, by its rule.
4. **Current state**: the behaviour today, from the analysis, cited.
5. **Requirements**: the change as ordered steps, each with its acceptance check; when the analysis states the root cause as unconfirmed, the first step is a failing test that reproduces it.
6. **Tests**: mandatory; the `Test framework` from Step 4; the files to add or change; cases for the happy path, each new branch, authorization, and regression guards for the incidents named; the test command line; existing suites must pass.
7. **Self review**: delegate a review to a fresh subagent, passing inline the ticket, the constraints, the acceptance criteria, `git diff {base ref}` (the uncommitted working tree against the base), and the full text of every untracked file `git ls-files --others --exclude-standard` lists; when the change touches auth, secrets, or money, the reviewer checks authorization, secret handling, and amount integrity by name; findings labelled `[Must]` or `[Recommend]`; every `[Must]` fixed and tests re-run; no review file written.
8. **Constraints**: what must not change (contracts callers depend on, rules with `documented` confidence, tables outside the ticket), and each blocked item as `blocked on owner: item {n} - {question}`.
9. **Acceptance criteria**: tests green, the named skills invoked, the self review completed with no open `[Must]`, the PR draft written.
10. **Stop before commit**: never `git commit`, `git push`, or open a PR; once the section 11 draft is written, report the files changed, the commands run, that `repos/{target}` is left on the new branch with uncommitted changes (the next `task-domain-sync` skips its bump until it is back on its tracked branch with a clean tree), and, when `## Solve` names a `Review skill`, `after committing, run {Review skill}`.
11. **PR draft**: written once to `{PR draft path}`, line 1 `# [{ticket id}] {summary}` (`# {summary}` when the text names no ticket id), then `## Summary` and `## Test Plan`, nothing else.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; URL-only, `in_progress`, and no-KB stops checked; layers named; `## Solve`, `## Precedence`, `## Audience`, `## Repos` read with every fallback recorded
- [ ] Step 3: items split; flows, changes, coupling, callers, and curated docs retrieved in every Audience language; citations read at the checkout and marked, `gone` kept out of evidence; precedence applied; items and ticket sized
- [ ] Step 4: target resolved, tie asked, other repos listed; base resolved in the stated order; `stack-detect` run over `repos/<target>/` and surfaced only through the `**Stack:**` line
- [ ] Step 5: analysis written from retrieved rows and docs only, unconfirmed root causes stated, gaps listed
- [ ] Step 6: pushback items only where warranted, each with the four fields; blocked items identified
- [ ] Step 7: analysis file written at `--out` in the stated shape, empty sections in the `none` form
- [ ] Step 8: super-prompt written with the eleven sections; repo-relative paths, absolute PR draft path; skills in the stated order, at most five, the Review skill only in section 10; conventions and test command forms; review over the working tree; blocked items under Constraints; nothing under `repos/` changed

## Avoid

- Naming any skill outside `core` and this plugin unless `CLAUDE.md` `## Solve` names it
- Filling the stack, test command, or conventions from what such repos usually use instead of `stack-detect` and `## Solve`
- Letting the prompt invoke a review or PR workflow that needs a commit
- Writing pushback for a concern the docs already settle
