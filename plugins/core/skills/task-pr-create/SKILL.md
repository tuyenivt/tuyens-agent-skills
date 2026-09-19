---
name: task-pr-create
description: Generate PR title and description from a git diff: summary, risk level, test plan, linked context for reviewers.
metadata:
  category: code
  tags: [pull-request, pr-description, git, collaboration, documentation]
  type: workflow
user-invocable: true
---

# PR Description Generator

Turns a git diff into a reviewer-ready PR description: title, summary, risk, test plan, linked context. Emits the description in chat for the user to paste; writes no file and does not open or submit the PR.

## When to Use

- After finishing a feature, fix, or refactor branch, before opening the PR
- When the diff is large and reviewers need a clear summary
- When you want a consistent format without writing it by hand

**Not for:** code-quality review (`task-code-review`).

## Inputs

| Input                | Required | Source                                          |
| -------------------- | -------- | ----------------------------------------------- |
| Git diff / file list | Yes      | `git diff <base>...HEAD`                        |
| Commit messages      | Yes      | `git log <base>..HEAD --oneline --no-merges`    |
| Ticket reference     | No       | Branch name, commit message, or user-supplied   |
| ADR references       | No       | Commit messages, or a `docs/adr/` or `docs/decisions/` file the diff touches |
| Related PRs          | No       | Commit messages or user-supplied                |

The base branch is detected in Step 2. A user-stated base (e.g., a stacked PR against `phase-01`) overrides detection; otherwise the user does not supply it unless detection fails.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Resolve Branch and Base

Establish `(base_ref, head_ref)` before any diff is read. PR creation runs against the current feature branch only.

1. **Resolve head:** `head_ref = HEAD`; `current_branch = git rev-parse --abbrev-ref HEAD`.
2. **Reject trunk and detached heads:** if `current_branch` is `main`, `master`, `develop`, or `trunk` (case-insensitive), or the branch `git symbolic-ref --short refs/remotes/origin/HEAD` names with its `origin/` prefix stripped, stop:

   ```text
   You are on `<current_branch>`, a trunk branch. Nothing scoped to describe.
   Switch to your feature branch and re-run.
   ```

   A detached `HEAD` (`current_branch` prints `HEAD`) also stops - check out the feature branch first.

3. **Detect base:** a user-stated base overrides detection - resolve it (`origin/<name>` then local, each via `git rev-parse --verify --quiet`; if neither resolves, say so and ask for the branch to be fetched or named differently - do not fall back to a trunk), record the resolved form (`origin/<name>` when remote) as `base_ref`, and skip item 4. A base named mid-workflow (answering item 4's question) resolves through this same path. Otherwise if `git symbolic-ref --short refs/remotes/origin/HEAD` prints a name and `git rev-parse --verify --quiet` confirms it (a dangling `origin/HEAD` prints a name whose branch no longer exists), use that short form. Otherwise probe every trunk name (`main`, `master`, `develop`, `trunk`) via `git rev-parse --verify --quiet refs/remotes/origin/<name>` then `refs/heads/<name>`; a name resolving in both forms counts once, remote form preferred; record the short form (`origin/<name>` or `<name>`) as `base_ref`.
4. **Use or ask** (probe path only - a symbolic-ref or user-stated base is used directly): exactly one distinct trunk name resolved -> use it. More than one (e.g., gitflow with both `main` and `develop`), or none -> ask the user. Do not pick silently; the wrong base pulls unrelated commits into the diff. The question lists the resolved candidates, offers no default, and states why picking wrong matters; when none resolved, it says so and asks for a base branch or ref by name.

Record `base_ref` for Step 4 and print it in one line before the description (`Base: origin/main (origin/HEAD)`, naming the source: user-stated, `origin/HEAD`, or trunk probe).

### Step 3 - Detect Stack

Use skill: `stack-detect` to inform test commands in the test plan (e.g., `./gradlew test`, `pytest`, `go test ./...`).

### Step 4 - Gather Context

Run or accept:

1. `git diff <base_ref>...HEAD`
2. `git log <base_ref>..HEAD --oneline --no-merges` (two dots - branch commits only; the three-dot form would include base-side commits once the base advances, polluting ticket extraction and the summary)
3. `current_branch` from Step 2
4. `git diff <base_ref>...HEAD --name-only`

If the diff is empty, stop and tell the user. If `git status --porcelain` lists anything (ignored files never appear), warn before emitting the description:

   ```text
   Uncommitted work is not described: <n> tracked path(s) with changes, <m> untracked. Commit or stash first if it belongs in this PR.
   ```

Extract from above:

- **Tickets:** `PROJ-123` and `#123` mentions, and `closes #` / `fixes #` / `resolves #` closing directives, in branch or commits - only a stated directive becomes `Closes`; a bare mention renders `Refs #<n>`
- **ADRs:** `ADR-`, `docs/adr/`, `docs/decisions/` mentions
- **Related PRs:** `PR #`, `pull/`, sibling branch names in commits

### Step 5 - Classify Risk

Use skill: `review-pr-risk`. Condense its output into the Risk section of the Output Format:

- `Risk Level:` + `Signals:` become `**[Low | Medium | High | Critical]** - [1-2 sentence rationale]`
- If it emits `Action:` (`require additional reviewer` | `split PR` | `add tests before merge`), append it verbatim as its own paragraph under the Risk line: `Suggested action: [action]`. Never drop it.

### Step 6 - Write the PR Description

Compose using the Output Format below.

**Title:**
- Imperative ("Add", "Fix", "Refactor") - not "Added" / "Adding"
- Under 72 characters counting the type prefix, not the `## ` marker; no ticket number (goes in body)
- Format: `<type>: <What changed>` where type is lowercase `feat`, `fix`, `refactor`, `perf`, `build`, `ci`, `style`, `revert`, `chore`, `docs`, or `test`, and the description starts with a capitalized imperative verb
- Mixed concerns: pick the type of the dominant user-facing change (a bugfix wrapped in refactoring is `fix`)

**Summary:**
- Explain the *why* (problem, motivation) more than the *what* (mechanics)
- Up to 5 bullets, each starting with a verb; proportional to the diff (a trivial change needs one)
- If the *why* is not inferable from diff, commits, ticket, or a requirement document the branch or commits name, or the stated motivation contradicts what the diff does, ask the user - do not invent it; when the user cannot say, open the Summary (after any `Stacked on` line) with the line `Motivation: not stated by the author.` and describe only the what
- Reference ticket/ADR inline only if essential context
- Stacked PR (a user-stated base that is not a trunk name - `main`, `master`, `develop`, `trunk`, or the branch `origin/HEAD` names): open the Summary with the standalone line `Stacked on <branch>.` (bare branch name - remote prefix stripped; before the bullets) so reviewers set the right merge target

**Test Plan:**
- Concrete, runnable steps. Include the exact test command for the detected stack when production code changed (production code = anything shipping or configuring runtime/build behavior; prose and assets alone are docs-only, needing only a relevant verification step such as a render or build check). Where several commands wrap the same tool, use the one the repo documents (`CONTRIBUTING.md`, `README`, a `Makefile` target); with nothing documented, use the detected build tool's runner form (`uv run pytest`, `bundle exec rspec`, the package manager's runner - `npx vitest`, `pnpm vitest`, `yarn vitest`, `bun run vitest` - or `./gradlew test`) over the bare tool. When `stack-detect` reports the test framework `unknown`, derive a build or verification command from its `Build tool` field (`mix compile`, `cargo build`, `zig build`); when that is `unknown` too, the runnable line is the one manual step that proves the change (a `curl` of the changed route, a render), marked `no test or build tool discoverable`.
- Manual verification for UI/API changes; migration steps when applicable.
- New infrastructure dependency (Redis, DB, broker): include the setup step (e.g., `docker compose up -d redis`); new usage of existing infra (a new queue) gets its worker/consumer config step instead.

**Deployment Notes:** include only when deployment-time implications exist - new infrastructure dependency, config change, behavior change to existing endpoints, feature flag, or a migration that cannot apply as written (it references an object the repo does not define) - stated as a deployment fact, not a review finding. A new library that changes runtime behavior (a scheduler, a background worker) counts via the behavior it introduces.

**Checklist:** include an item when the diff touches something it could plausibly violate; omit the rest. A retained item is a claim you are making - do not tick what the diff does not support.

### Step 7 - Surface Linked Context

When the repo ships a PR template - GitHub: `pull_request_template.md` or `PULL_REQUEST_TEMPLATE.md` in the root, `.github/`, or `docs/`, or a `PULL_REQUEST_TEMPLATE/` directory in any of those three places (use its only file, else the one the user names - GitHub selects these only by query parameter); GitLab: `.gitlab/merge_request_templates/Default.md` (or the only file there) - map this description's content into that template's sections and order; a section the template lacks is inserted where its nearest neighbour sits (Risk directly before the house's testing section, Linked Context last); a house What/Why pair takes the Summary's what-bullets and why-bullets respectively, and no content this Output Format requires is dropped. A house checklist keeps its own item wording, still subject to the retain-only-what-the-diff-could-violate rule; add this format's items only where the house has no equivalent. The house template governs headings and their order - including where Risk and the title sit, overriding Output Constraints on order alone; this format governs what each section must contain.


Add a **Linked Context** section only if at least one of: ticket reference, ADR reference, related PR. If none found, omit entirely - no empty placeholders. `Closes #<n>` is for a repository issue number named by a closing directive, and auto-closes only when the PR merges into the default branch - on a stacked PR, or for a bare mention, write `Refs #<n>`; a tracker key renders as `Ticket: <ID>`, linked `[ID](url)` when a tracker URL is known and bare otherwise.

## Output Format

```markdown
## [feat | fix | refactor | perf | build | ci | style | revert | chore | docs | test]: [imperative description - the line after `## `, type prefix included, stays under 72 characters]

### Summary

Stacked on [bare branch name, remote prefix stripped].   {standalone line before the bullets, only when the user-stated base is not a trunk name}

Motivation: not stated by the author.   {standalone line, only when the user could not supply the why}

- [Why this change was needed / problem solved]
- [What changed at a high level - domain, layer, component]
- [Notable design decision or tradeoff]

### Risk

**[Low | Medium | High | Critical]** - [1-2 sentence rationale]

Suggested action: [`require additional reviewer` | `split PR` | `add tests before merge`]   {only when `review-pr-risk` emitted `Action:`}

### Test Plan

- [ ] Run tests: `[stack-appropriate command]`
- [ ] [Manual verification step 1 - e.g., "POST /api/v1/orders returns 201"]
- [ ] [Manual verification step 2]
- [ ] [Migration step if applicable - e.g., "Run `./gradlew flywayMigrate` on staging before deploy"]

### Deployment Notes                    {only when a deployment-time implication exists}

- [deployment-time consideration]

### Checklist                           {only items the diff could plausibly violate}

- [ ] Tests added or updated for new behavior
- [ ] No secrets, tokens, or PII introduced
- [ ] Migration is reversible
- [ ] Breaking API changes documented

### Linked Context                      {only when a ticket, ADR, or related PR exists}

Closes #[issue number - from a stated closing directive, on a PR into the default branch; otherwise `Refs #<n>`]

Ticket: [tracker key, linked as `[ID](url)` when a tracker URL is known, bare otherwise]

ADR: [ADR title or path]

Related: [`#<number>` for a PR, or the bare branch name]
```

## Output Constraints

- Title is the first line with `##` prefix - not a separate field
- Emit raw Markdown; never wrap the description in a code fence
- Atomic outputs (detection block, risk block) stay internal - the description is the only emission besides mandated warnings and questions
- Risk appears before Test Plan
- Omit sections with no content
- No line-by-line diff description - orient reviewers, do not duplicate the diff
- Test plan includes at least one runnable command for the detected stack when production code changed (or, with no discoverable tool, the one manual step that proves the change)
- Total description under 400 words - counting every prose line (Summary bullets, the Risk rationale, Test Plan manual steps, Deployment Notes, checklist item text, Linked Context) and excluding headings, commands, code, and checkbox markers; over budget, trim Summary bullets first, then Linked Context prose, then manual Test Plan steps beyond the first two, then checklist items - never Risk, the test command, or Deployment Notes

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: branch and base resolved; trunk-branch and detached HEAD rejected; user-stated base honored, else auto-detected or asked when ambiguous
- [ ] Step 3: stack detected; reflected in the test plan command when production code changed
- [ ] Step 4: diff and commits gathered against resolved `base_ref`, not hardcoded `main`; empty diff stopped; uncommitted work warned about before the description
- [ ] Step 5: risk classification present with rationale; `Action:` from `review-pr-risk` carried over if emitted
- [ ] Step 6: title imperative, under 72 chars, type-prefixed; summary explains the *why* more than the *what*; test plan has a runnable command (or the one manual proof) when production code changed
- [ ] Step 7: house PR template mapped when one ships, nothing required dropped; Linked Context only when real references exist; nothing invented
- [ ] Empty sections omitted; total under 400 words

## Avoid

- Inventing ticket IDs, ADR titles, PR references, or motivations not found in git context
- Duplicating the diff in the summary - orient, do not re-describe
- Vague test plans ("test it works") instead of concrete commands
- Personal opinions about code quality - this is documentation, not review
- Empty placeholder sections (Linked Context with no content)
- Adding a second inline risk rating after Step 5's classification
