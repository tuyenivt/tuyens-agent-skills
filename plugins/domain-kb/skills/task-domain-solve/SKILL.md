---
name: task-domain-solve
description: Turn a ticket or problem into a cited analysis file and a self-contained implementation super-prompt, stack-detected per target repo.
metadata:
  category: domain
  tags: [domain, knowledge-base, solve, ticket, analysis, super-prompt, implementation-plan]
  type: workflow
user-invocable: true
---

# Domain Solve

Reads a ticket or problem statement against both layers of the knowledge base, writes an analysis of what is happening and why, pushes back where the ask is unclear or wrong, and writes one prompt another agent can run end to end in the target repo: skills to invoke, rules to respect, phases, tests, a delegated self-review, and a stop before commit. It writes two files and changes nothing in `repos/`.

## When to Use

- A ticket, bug report, or feature ask needs to become an implementation plan grounded in the documented flows and rules
- A problem statement needs its root cause or constraints named before anyone writes code

**Not for:** answering a question or sizing a ticket without a plan (`task-domain-ask`); implementing the change itself, which the super-prompt's runner does; building the knowledge base (`task-domain-sync`).

## Inputs

| Input            | Required | Notes                                                                                                                                      |
| ---------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Text or `--in <file>` | yes | The ticket or problem, inline or read from the file; a bare tracker URL is not fetched, the workflow asks for the text and stops           |
| `--out <file>`   | no       | The analysis path; default: `--in` with `-out` inserted before the extension in the same directory, or `tmp/solve-out.md` for inline text  |
| `--prompt <file>` | no      | The super-prompt path; default: `--in` with `-prompt` inserted before the extension, or `tmp/solve-prompt.md` for inline text              |
| `--base <branch>` | no      | The base branch for the diff and PR draft; default `Base branch` from `AGENTS.md` `## Solve`, else `main`                                  |
| `--repo <name>`  | no       | The target repo under `repos/`; absent, inferred from the flows the ticket touches; ambiguous (two repos share the changes), the workflow lists them and asks |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate the knowledge base and its configuration

The root is the working directory; both layers are located as `task-domain-ask` Step 2 does, and the workflow stops with `no knowledge base here - run task-domain-sync init or import` when neither exists. Read `AGENTS.md` `## Solve` (every key; a missing section or an `unknown - set in AGENTS.md ## Solve` value means the default applies and the report says so), `## Precedence`, `## Audience`, and `## Tech Stack` when present. Read `--in` when given; a tracker URL alone stops with `paste the ticket text - URLs are not fetched`.

### Step 3 - Target repo and stack

Resolve `--repo`, or infer it after Step 4 from the repo that owns the most changes the ticket touches; ask when two repos tie. Use skill: `stack-detect` applied to `repos/<target>/` (its marker-file table over that directory, not the root); the block is an input only, and the analysis surfaces it through its own `**Stack:**` line as `{Language} / {Framework}, tests: {Test framework}, db: {Database}`.

### Step 4 - Retrieve

Retrieve as `task-domain-ask`'s ticket shape does: the flows touched, their state changes and side effects, coupling rows, callers, and size signal, every citation read in the repo and marked `verified | moved | gone`; plus the hand-written `rules/`, `specs/`, `incidents/`, and `tech-debt/` docs naming the item's surfaces, entities, or terms, in every Audience language. A surface no card and no doc covers is `not found in docs`.

### Step 5 - Analyse

Write, from the retrieved rows and docs only: what is happening and why (the observed behaviour, the flow hop or rule that produces it, cited); the services and flows involved; the root cause or the constraints a change must satisfy (the rules with `Confidence: documented` quoted with their doc path or ledger id, the callers that would see the change, the incidents that touched the path); and the documentation gaps, each stated as `not found in docs: <what>`. Nothing is inferred from how such systems usually work.

### Step 6 - Pushback

Only when warranted; an empty block reads `- none`. One item per concern: `Category: {unclear | mistaken-assumption | gap | security | performance | rule-violation | blast-radius | other}`, `Evidence: {doc path or row | judgment call - needs owner confirmation}`, `Question for owner: {one question}`, `Impact if ignored: {one sentence}`. A `rule-violation` cites the rule; a `mistaken-assumption` quotes the ticket line and the row that contradicts it.

### Step 7 - Write the analysis

Write `--out` per the Output Format's analysis shape, creating its directory when absent.

### Step 8 - Write the super-prompt

Write `--prompt` per the Output Format's super-prompt contract. Skills are chosen in this order: the `## Solve` `Implement skill`, `Review skill`, and `Test skill` when set; otherwise `core` skills by topic (`core:task-code-review` always; `core:task-code-review-security` when the change touches auth, secrets, or money; `core:backend-db-migration` for a schema change; `core:backend-idempotency` for a retried or webhook-driven write; `core:ops-release-safety` for a change behind a flag or with a rollout; `core:task-pr-create` for the PR draft; any other `core` atomic whose concern the change names), at most five in total with a one-line reason each, and the prompt states `defaults used - set AGENTS.md ## Solve to name project skills` when no `## Solve` skill was set. The `Conventions file` is named as the first file to read and treated as binding; when unset the line reads `no conventions file configured`. The `Test command` is copied verbatim; when unset the phase says `test command not configured - use the framework's default runner` and names the framework from Step 3.

## Output Format

Console:

```
## Domain solve

- **Problem:** {one line}
- **Repo:** {target} ({Language} / {Framework})
- **Flows:** {<capability>/<flow>, ...}
- **Docs:** {rules, specs, incidents, tech-debt paths | none - not found in docs}
- **Size:** {S | M | L | L - new surface} - {reason}
- **Pushback:** {n} items
- **Skills:** {skill, skill, ...} ({from ## Solve | defaults used})
- **Analysis:** {--out path}
- **Prompt:** {--prompt path}
- **Next:** run the prompt in repos/{target}; it stops before commit
```

Analysis file (`--out`):

```markdown
# Analysis: {ticket title or first line}

- **Stack:** {Language} / {Framework}, tests: {Test framework}, db: {Database}
- **Repo:** repos/{target}
- **Size:** {S | M | L | L - new surface} - {reason}

## What is happening and why

{prose, every claim cited as `(<capability>/<flow> <section> - file:line (verified))` or `(doc <path> <section>)`}

## Services and flows

| Flow | Trigger | Repos | Changes on this path |
| ---- | ------- | ----- | -------------------- |

## Root cause or constraints

- {rule or constraint} - {doc path | ledger R-n | card row} ({verified | moved | gone | n/a})

## Callers and coupling

- {contracts/<caller> - surfaces used | register D-n - files dragged | none}

## Documentation gaps

- not found in docs: {what}

## Pushback

- **Category:** {unclear | mistaken-assumption | gap | security | performance | rule-violation | blast-radius | other}
  - **Evidence:** {doc path or row | judgment call - needs owner confirmation}
  - **Question for owner:** {question}
  - **Impact if ignored:** {sentence}
```

Super-prompt file (`--prompt`): the file is the prompt. No fence wraps it, no heading names it a prompt, and it holds exactly these eleven numbered phases in order, each a `## {n}. {Title}` heading:

1. **Role and repository**: the runner works in `repos/{target}` on a branch off `{base}`, as an engineer on this system.
2. **Skills to invoke**: at most five `Use skill:` lines with a one-line reason each, chosen per Step 8, with the defaults line when it applies.
3. **Context**: the `**Stack:**` line; `Read first and treat as binding: {conventions file}`; the file paths the change touches; every domain rule the change must respect, quoted with its doc path or ledger id.
4. **Current state**: the behaviour today, from the analysis, cited.
5. **Requirements**: the change as ordered phases, each with its acceptance check.
6. **Tests**: mandatory; the framework from Step 3; the files to add or change; cases for the happy path, each new branch, authorization, and regression guards for the incidents named; the `Test command` verbatim; existing suites must pass.
7. **Self review**: delegate a full review to a fresh subagent, passing inline the ticket, the constraints, the acceptance criteria, and `git diff {base}...HEAD`; findings labelled `[Must] | [Recommend] | [Question]`; every `[Must]` fixed and tests re-run; no review file written.
8. **Constraints**: what must not change (contracts callers depend on, rules with `documented` confidence, tables outside the ticket).
9. **Acceptance criteria**: tests green, the named skills invoked, the review completed with no open `[Must]`, the PR draft written.
10. **Stop before commit**: never `git commit`, `git push`, or open a PR; report the files changed and the commands run.
11. **PR draft**: written once to `{PR draft path}` (default `tmp/pr.md`), line 1 `# [{ticket}] {summary}`, then `## Summary` and `## Test Plan`, nothing else.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: both layers located; `## Solve`, `## Precedence`, `## Audience`, `## Tech Stack` read; defaults named where a value was unset; URL-only input stopped
- [ ] Step 3: target repo resolved or inferred, ambiguity asked; `stack-detect` run over `repos/<target>/` and surfaced only through the `**Stack:**` line
- [ ] Step 4: flows, changes, coupling, callers, size, and hand-written docs retrieved in every Audience language; every citation read and marked; uncovered surfaces stated as `not found in docs`
- [ ] Step 5: analysis written from retrieved rows and docs only, with gaps stated
- [ ] Step 6: pushback items only where warranted, each with the four fields
- [ ] Step 7: analysis file written at `--out` in the stated shape
- [ ] Step 8: super-prompt written at `--prompt` with the eleven phases, skills chosen in the stated order and capped at five, conventions file and test command carried verbatim, stop-before-commit and PR draft phases present; nothing under `repos/` changed

## Avoid

- Naming any skill outside `core` and this plugin unless `AGENTS.md` `## Solve` names it
- Filling the stack, test command, or conventions from what such repos usually use instead of `stack-detect` and `## Solve`
- Wrapping the super-prompt in a fence or a heading that calls it a prompt
- Letting the prompt commit, push, or open a PR
- Writing pushback for a concern the docs already settle
