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

Reads a ticket or problem statement against both layers of the knowledge base, writes an analysis of what is happening and why, pushes back where the ask is unclear or wrong, and writes one prompt another agent can run end to end in the target repo: skills to invoke, rules to respect, steps, tests, a delegated self-review, and a stop before commit. It writes up to two files and changes nothing in `repos/`.

## When to Use

- A ticket, bug report, or feature ask needs to become an implementation plan grounded in the documented flows and rules
- A problem statement needs its root cause or constraints named before anyone writes code

**Not for:** answering a question or sizing a ticket without a plan (`task-domain-ask`); implementing the change itself, which the super-prompt's runner does; building the knowledge base (`task-domain-sync`).

## Inputs

| Input            | Required | Notes                                                                                                                                      |
| ---------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Text or `--in <file>` | yes | The ticket or problem, inline or read from the file; a bare tracker URL is not fetched, the workflow asks for the text and stops           |
| `--out <file>`   | no       | The analysis path; default `tmp/<name>-out.md`, `<name>` being the `--in` file name without its extension, or `solve` for inline text; `tmp/<name>-out-<repo>.md` when `--repo` is given |
| `--prompt <file>` | no      | The super-prompt path; default `tmp/<name>-prompt.md` on the same rule (`tmp/<name>-prompt-<repo>.md`)                                                                     |
| `--base <branch>` | no      | The base branch for the runner's branch, diff, and PR draft; default per Step 4                                                            |
| `--repo <name>`  | no       | The target repo under `repos/`; absent, inferred in Step 4                                                                                 |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate the knowledge base and its configuration

Use skill: `domain-kb-layout` for every path, section, and empty form named below; read its Rules and the Patterns sections Curated layer, CLAUDE.md, Flow card, Ledger, playbook, contracts, debt, surfaces, and Indexes. No text and no `--in`, or an `--in` file that does not exist, stops with `no ticket text - paste it or pass --in <file>`; a text that is only a tracker URL stops with `paste the ticket text - URLs are not fetched`. The root is the working directory. `_index/sync-state.json` recording a non-null `in_progress` stops with `sync interrupted at {command}:{pass} - run task-domain-sync to finish`. The generated layer exists when `sync-state.json` records a `sha`, the curated layer when any curated folder holds a Markdown file; with neither, stop with `no knowledge base here - run task-domain-sync init or import`; with one, the console's Layers line names it. Read `CLAUDE.md` `## Solve` (the keys this workflow names, any other key ignored; a missing section, key, or `unknown - set in CLAUDE.md ## Solve` value takes the default this workflow states, and the console's Defaults line names it; a key that is set is never a default, whatever its value resolves to), `## Precedence` (absent, as on a curated-only root: the layout's scaffold text applies), `## Audience` (`Language:` default `en`; the first code is the language of both files), and `## Repos`; read `--in` when given.

### Step 3 - Retrieve and fact-check

Split the text into items, one per distinct change it asks for (its numbered items when it has them). For each item retrieve the flows it touches, the cards whose Trigger, hops, entities, or Story the item's surfaces and terms name (found through the inventories, the glossary, the cards' Story lines, and `_index/file-to-flow.json`; a flow that only shares files with them is a coupling candidate, not a touched flow), with their state changes, side effects, Rules, and Failure modes; the register rows whose `Signal` starts `coupling` and whose `Location` names a file of a touched flow; the `contracts/` callers (`consumers/` docs when `contracts/` does not exist); and every curated doc naming the item's surfaces, entities, or terms, `patterns/` included, searched in every Audience language.

Every cited `file:line` is read at the repo's checkout `HEAD` with `git -C repos/<repo> show HEAD:<path>`, `<path>` repo-relative with the `repos/<repo>/` prefix stripped (which may be ahead of the card's `sources`, and never includes an uncommitted change): `verified` when the row's condition, write, or call is on that line, `moved` when it sits at another line of the file, `gone` when it is not in the file; a curated citation takes its ATLAS `## Citation drift` status when listed there (the section absent is the no-row case). A `gone` citation is not evidence but a documentation gap naming the stale card or doc. A curated doc is `documented` when `active`, `inferred` when `draft` or when it has no frontmatter, and cited only together with its `superseded_by` target, whose status counts, when `deprecated`; a rule is `documented` when its ledger `Confidence` is `documented` or an `active` `rules/` doc states it. A generated file's `## Notes` text, and code read in a file no row cites, is a lead to follow, never evidence: a cause found there is `unconfirmed:`. A card row and a doc that disagree are a documentation gap, settled by `## Precedence` as written (an unranked folder sits below generated cards and equal to the other unranked folders; the scaffold text ranks a card citation above any doc, and a `gone` one is no citation). A surface no card and no doc covers is `not found in docs`.

Size each item, the largest whose condition holds: `S` for one flow and no coupling row; `M` for two or three flows, or one coupling row; `L` for four or more flows, or two or more coupling rows; `L - new surface` when no flow matches, or the item adds a trigger, outbound call, or message no inventory row lists; an item that contradicts a `documented` rule, a ticket that sets out to change it included, moves up one size (`L` stays `L`). The ticket's size is its largest item's, `L - new surface` ranking above `L`.

### Step 4 - Target repo, base, and stack

The target is `--repo`, else the repo holding the most cited `file:line` among the changes of the items Step 6 leaves unblocked (its blocking is settled on the retrieved rows before the target is chosen); when repos tie, or no change has a citation, the workflow lists the candidate repos and asks, and continues only once answered; when every item is blocked, no target is chosen, the Repo line reads `none - every item blocked`, and no Stack line is written. Every other repo with a change is an `Other repos` entry for its own `--repo` run, `(blocked)` when only blocked items touch it. A `--repo` with no directory under `repos/`, or an empty `repos/`, stops with `no repo to target - add repos/<name> and run task-domain-sync`. The base is `--base`, else the `## Repos` `Branch` cell, else the `branch` in `sync-state.json`, else `## Solve` `Base branch` (the scaffold writes `main` there, so the key is set on every scaffolded root and applies on one with no tracked branch), else `main` (a `.` resolves, per the layout, to the root's current branch); the base ref is `origin/{base}` when `git -C repos/<target> rev-parse --verify --quiet origin/{base}` succeeds, else `{base}`, and when neither resolves the workflow asks for `--base` and continues only once answered. The checkout state is read once: `git -C repos/<target> status --porcelain` listing anything but the `## Solve` `PR draft path` or its directory appends `(checkout dirty - commit or stash -u before running the prompt)` to the console's Repo line, and `HEAD` differing from `{base ref}` (`git -C repos/<target> rev-parse HEAD {base ref}`) appends `(checkout differs from the base - citations read at HEAD)`, both when both hold; a previous runner's uncommitted change is the usual cause of the first, unfetched or unpushed commits of the second. When the target's `sources` sha on the touched cards (the oldest when they differ) is behind `HEAD`, the Repo line also appends `(cards behind HEAD by {n} commits - run task-domain-sync)`, `n` from `git -C repos/<target> rev-list --count <sources sha>..HEAD`. Use skill: `stack-detect` applied to `repos/<target>/` (its instruction files and marker-file table there, not the root); the block is surfaced only through the `**Stack:**` line (the analysis header and the prompt's section 3) as `{Language} / {Framework}, tests: {Test framework}, db: {Database}`, with ` (## Repos says {Stack cell})` appended when the detected `Language` or `Framework` differs from the target's `## Repos` `Stack` cell. It runs here, not as Step 2, because the target is known only after retrieval.

### Step 5 - Analyse

Fill the analysis sections from the retrieved rows and docs only: the observed behaviour and the hop or rule producing it, cited; the flows; the constraints (`documented` rules quoted with doc path or ledger id, callers, incidents on the path, governing `patterns/` docs); the gaps in their three forms. A root cause the rows do not confirm takes the `unconfirmed:` form. Nothing is inferred from how such systems usually work.

### Step 6 - Pushback

Only when warranted: one entry per concern in the template's shape, naming the ticket item it concerns. A `rule-violation` is a change that breaks a documented rule the ticket does not set out to change, and cites the rule; a ticket that sets out to change a rule is not one, and its pushback (Category `gap`) names the rule's doc as needing the same change; a `mistaken-assumption` quotes the ticket line and the row that contradicts it. An item whose requested change is `unclear` or a `rule-violation` is blocked (its size still counts in the ticket's): the super-prompt does not implement it and lists it under Constraints; a `mistaken-assumption` about the cause blocks nothing, since the plan follows the analysed cause; every non-blocking entry is quoted under the super-prompt's Constraints as a caution. When every item is blocked, no super-prompt is written: the console's Prompt line reads `not written - every item is blocked on owner` and Next reads `answer the pushback questions, then run task-domain-solve again`.

### Step 7 - Write the analysis

Write `--out` in the analysis shape, creating its directory when absent.

### Step 8 - Write the super-prompt

Write `--prompt` per the super-prompt contract, creating its directory when absent. Repo file paths in it are relative to `repos/{target}`; knowledge-base docs and cards are cited by root-relative path and quoted inline; the `## Solve` `PR draft path` (default `tmp/pr.md`) is written as set, a relative path resolved by the runner against its working directory, the `repos/{target}` checkout, never against the knowledge-base root. A file of another repo is cited root-relative. Skills to invoke: the `## Solve` `Implement skill` and `Test skill` when set, then `core` atomics by what the change touches (`core:backend-db-migration` for a schema change, `core:backend-idempotency` for a retried or webhook-driven write, `core:backend-transaction-patterns` for a write that moves money or spans services, `core:backend-api-guidelines` and `core:ops-backward-compatibility` for a route, request, or response change, `core:ops-release-safety` for a change behind a flag or with a rollout, any other `core` atomic whose concern the change names), at most five in total, each with a one-line reason; when `Implement skill` or `Test skill` is unset, the section adds `defaults used - set CLAUDE.md ## Solve to name project skills`. The `Conventions file` is a path from the knowledge-base root: under `repos/{target}` it is written repo-relative and is the first file to read and binding; anywhere else in the knowledge base it is quoted inline in section 3 and binding; unset, the line reads `no conventions file configured`; set but absent, `conventions file not found: <path>` with the path as set. A `## Solve` value that names a path under another `repos/<repo>`, or an `Implement skill`, `Test skill`, or `Test command` from a stack or runner that is not the target's detected `Language`, `Framework`, or `Test framework`, is still used as set, and section 8 gains `caution: ## Solve {key} is set for {repo or stack}, not repos/{target} - confirm before running`. The `Test command` is copied verbatim; unset, the section reads `test command not configured - use the framework's default runner` and names the `Test framework` from Step 4 (`unknown`: `test runner unknown - find it in the repo`).

## Output Format

Console:

```
## Domain solve

- **Problem:** {one line}
- **Layers:** {both | generated only | curated only}
- **Repo:** repos/{target} @ {base ref}{ (checkout dirty - commit or stash -u before running the prompt)}{ (checkout differs from the base - citations read at HEAD)}{ (cards behind HEAD by {n} commits - run task-domain-sync)}
- **Other repos:** {repo - the change it needs{ (blocked)}, ... | none}
- **Flows:** {<capability>/<flow>, ... | none - no card matches}
- **Docs:** {curated paths | none - not found in docs}
- **Size:** {S | M | L | L - new surface} - {reason, with each item's size}
- **Pushback:** {n} entries ({n} ticket items blocked)
- **Skills:** {skill, skill, ... | none - no prompt written}
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
- **Other repos:** {repo - the change it needs{ (blocked)}, ... | none}
- **Size:** {S | M | L | L - new surface} - {reason}

## What is happening and why

{prose, every claim cited as `(<capability>/<flow> <section> - file:line ({verified | moved}))`, `(ledger R-n | register D-n | contracts/<caller>.md row{ - file:line ({verified | moved})})`, or `(doc <path> <section>{ - file:line ({verified | moved})})`}

## Services and flows

| Flow | Trigger | Repos | Changes on this path |
| ---- | ------- | ----- | -------------------- |

## Root cause or constraints

- {rule or constraint} - {doc path | ledger R-n | card row} ({verified | moved | n/a})
- unconfirmed: {suspected cause} - {what would confirm it}

## Callers and coupling

- {contracts/<caller>.md or consumers/<name>.md - surfaces used | register D-n - files dragged}

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

1. **Role and repository**: the runner works in `repos/{target}` on a new branch (kebab-case from the ticket id, else the summary) from the checkout's `HEAD` (`{HEAD sha}`, where the analysis read its citations), diffed against that commit and PR'd against `{base ref}`, created from a clean tree (`git status --porcelain` listing anything but `{PR draft path}` or its directory stops with `commit or stash -u the current change first`), as an engineer on this system, and changes no other repo.
2. **Skills to invoke**: at most five `Use skill:` lines with a one-line reason each, chosen per Step 8, with the defaults line when it applies; the section 3 Stack line is the stack-detect result these skills ask for.
3. **Context**: the `**Stack:**` line; the conventions line; the files the change touches; every domain rule the change must respect, quoted with its doc path or ledger id; every `patterns/` doc that governs the code, by its rule.
4. **Current state**: the behaviour today, from the analysis, cited.
5. **Requirements**: the change as ordered steps, each with its acceptance check; when the analysis states the root cause as unconfirmed, the first step is a failing test that reproduces it.
6. **Tests**: mandatory; the `Test framework` from Step 4; the files to add or change; cases for the happy path, each new branch, authorization, and regression guards for the incidents named; the test command line; existing suites must pass.
7. **Self review**: the generic checks of `core:task-code-review full`, applied to the uncommitted change (that workflow and its lenses review only committed branches, so none is invoked; a skill named below is read for its rules and applied by the reviewer itself, never invoked as a workflow). Delegate to a fresh subagent that loads `core:behavioral-principles` first and runs `core:stack-detect` in `repos/{target}`, passing inline the ticket, the section 5 requirements with their acceptance checks, the section 8 constraints, the section 3 Stack line and quoted rules, `git diff HEAD` (the uncommitted working tree against the commit the branch started from), and the full text of every untracked file `git ls-files --others --exclude-standard` lists, which count as added files; the reviewer reads any other working-tree file a finding needs. The reviewer applies, in order: `core:review-change-intent` with the section 5 requirements as the only requirement source (`Specified`; the ticket is context, not a source; a blocked item or another repo's work is outside this change and `Deferred`, never `Unmet`) and an empty commit log; `core:review-pr-risk` and `core:review-blast-radius`; correctness with `core:ops-resiliency`, plus `core:architecture-concurrency` for concurrent code and `core:backend-transaction-patterns` for a changed transaction scope or cross-boundary write, and a named finding for logic added or modified without tests; `core:backend-api-guidelines` and `core:ops-backward-compatibility` when the change touches a route, request, response, serializer, or published spec, `core:ops-backward-compatibility` alone for a migration or another non-API contract; `core:architecture-guardrail`, `core:complexity-review`, and `core:backend-coding-standards`; then the four lenses: performance (`core:backend-db-indexing`, and `core:backend-connection-pooling` when the change touches pool configuration or per-request connections), security (every OWASP Top 10 row of the table in `core:task-code-review-security`, each stated clean or with its finding, plus that skill's input, file, cloud-storage, and data-protection checks, and authorization, secret handling, and amount integrity by name when the change touches auth, secrets, or money), observability (`core:ops-observability`), and reliability (`core:backend-idempotency`, `core:failure-propagation-analysis` in `what-if` mode). A finding stands once its cited line is read in the working tree and holds there; findings are merged across checks and labelled `[Must]` when they risk incorrect behaviour, data loss, or a security hole (a missing test on a critical path included), `[Recommend]` otherwise, except a pre-existing defect the change neither introduced nor made reachable, which is `[Recommend]`, reported, and never applied; the runner applies any other `[Recommend]` whose fix stays within the section 8 constraints and the files the change touches, and leaves the rest; the reviewer returns its findings, the `Risk Level` and `Blast Radius` lines, and the OWASP row statements inline; every `[Must]` is fixed, in any file of the repo it needs within the section 8 constraints, the fixed lines re-checked, and the section 6 test command re-run (`not run - <reason>` when it cannot); a `[Must]` whose fix needs an owner's decision is reported in the section 10 line as `blocked on owner: review - {finding}` instead; no review file written.
8. **Constraints**: what must not change (contracts callers depend on, rules with `documented` confidence, tables outside the ticket), each blocked item as `blocked on owner: item {n} - {question}`, each `Other repos` entry as `out of this run: {repo} - {change}`, and each non-blocking pushback entry as `caution: item {n} - {impact}`.
9. **Acceptance criteria**: tests green, the named skills invoked, the self review completed with no open `[Must]` other than those blocked on owner, the PR draft written.
10. **Stop before commit**: never `git commit`, `git push`, or open a PR; once the section 11 draft is written, report the files changed, the commands run, that `repos/{target}` is left on the new branch with uncommitted changes (the next `task-domain-sync` skips its bump while the tree is dirty or off its tracked branch), the PR draft path as excluded from git and not part of the change, and `Review: section 7 self review - risk {Risk Level}, blast radius {Blast Radius}; {n} [Must] fixed, {k} [Must] blocked on owner (blocked on owner: review - {finding}, one each), {m} [Recommend] ({a} applied, {l} left: <one line each>)`, the review of this change before it is committed.
11. **PR draft**: written once to `{PR draft path}` (a relative path resolved against the runner's working directory, its directory created and the file path added to the file `git rev-parse --git-path info/exclude` names when the repo does not ignore it), line 1 `# [{ticket id}] {summary}` (the ticket's title, else one line; `# {summary}` when the text names no ticket id), then `## Summary` and `## Test Plan` (the test command, the cases added, and the run's result, `not run - <reason>` when it could not run), nothing else.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; no-text, URL-only, `in_progress`, and no-KB stops checked; layers named; `## Solve` (named keys only), `## Precedence`, `## Audience`, `## Repos` read with every fallback recorded
- [ ] Step 3: items split; touched flows, changes, coupling, callers, and curated docs retrieved in every Audience language; citations read at `HEAD` via `git show` and marked, `gone` kept out of evidence; precedence applied; items and ticket sized
- [ ] Step 4: target resolved, missing repo stopped, tie asked, other repos listed; base resolved in the stated order, unresolvable base asked; checkout state read and surfaced on the Repo line; `stack-detect` run over `repos/<target>/` and surfaced only through the `**Stack:**` line
- [ ] Step 5: analysis drafted from retrieved rows and docs only, unconfirmed root causes stated, gaps listed
- [ ] Step 6: pushback items only where warranted, each with the five fields; blocked items identified
- [ ] Step 7: analysis file written at `--out` in the stated shape, empty sections in the `none` form
- [ ] Step 8: super-prompt written with the eleven sections (or, every item blocked, not written and the console's Prompt, Skills, and Next forms used); repo-relative paths, PR draft path relative to the runner's working directory; skills in the stated order, at most five; section 10 reports the self review as the change's review; conventions and test command forms; the self review applies `task-code-review full`'s checks to the working tree; blocked items under Constraints; nothing under `repos/` changed

## Avoid

- Naming any skill outside `core` and this plugin unless `CLAUDE.md` `## Solve` names it
- Filling the stack, test command, or conventions from what such repos usually use instead of `stack-detect` and `## Solve`
- Letting the prompt invoke a review or PR workflow that needs a commit
- Writing pushback for a concern the docs already settle
