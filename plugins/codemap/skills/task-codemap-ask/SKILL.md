---
name: task-codemap-ask
description: Answer free-form questions about the codebase by querying the codemap graph plus targeted file reads. Like indexed RAG over your repo.
metadata:
  category: code
  tags: [codemap, ask, qa, knowledge-graph]
  type: workflow
user-invocable: true
---

# Task: Codemap Ask

Ask one question about the codebase. The skill resolves the question against the `.codemap/graph.json` first (cheap, instant, structured), then opens 1-3 specific files when source detail is needed.

## When to Use

For questions about the system - you don't know yet which entity matters, you want a 1-3 sentence answer with citations.

- "How does the payment flow work?"
- "Which handlers touch the `orders` table?"
- "What calls `authenticate`?"
- "Where is the JWT signing key configured?"
- "Show me the auth middleware chain."

**Not for:**
- A structured deep-dive on one specific file/function (callers + callees + data + tests + blast radius). Use `task-codemap-explain` - it produces a fixed-section report by default.
- "Make this change" - use `task-implement` or `task-code-refactor`.
- "Review this PR" - use `task-code-review`.
- Onboarding overview - play `task-codemap-guide --list` first; use `task-codemap-ask` for follow-ups.

## Inputs

| Input | Required | Notes |
| --- | --- | --- |
| `$ARGUMENTS` | Yes | The question, in English. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

1. Confirm `.codemap/graph.json` exists. If missing, suggest `task-codemap` and stop.
2. Check freshness: compare `meta.json#gitCommitHash` to current `git rev-parse HEAD`. If stale by more than ~10 commits or `meta.json#builtAt` older than 7 days, warn before answering. Do not block.
3. Load `graph.json` and `guides.json`.

Use skill: `codemap-schema` for shape.
Use skill: `codemap-query` for traversal patterns.

### Step 3 - Classify the Question

| Question shape | Query plan |
| --- | --- |
| "What/where is X" | Resolve X to a node ID; render summary, file:line, fan-in/out. |
| "What calls X" / "What uses X" | Reverse edges of type `calls`/`uses`/`imports` from X. |
| "What does X call/use" | Outgoing edges from X. |
| "How does flow Y work" | Find a guide matching Y in `guides.json`; otherwise BFS from an entrypoint. |
| "Which handlers/services touch Y" (table, queue, etc.) | Reverse BFS from Y over `reads_from`/`writes_to`/`calls`. |
| "Where is Y configured" | `config`-type nodes with `configures` edges to Y, or filter `config` nodes by tag/name. |
| "What's the impact if I change X" | Reverse BFS from X depth 3 over `imports`/`calls`/`uses`. |
| "List all endpoints/tables/services" | Filter nodes by type. |
| "Why does X depend on Y" | Shortest path from X to Y; render the chain. |

If the question doesn't fit any of these, fall back to: extract entities, resolve each to node IDs, walk neighborhoods, summarize.

### Step 4 - Execute the Query

1. Resolve referenced entities to node IDs per `codemap-query`'s resolution rules.
2. Walk the graph with the chosen pattern.
3. Cap results: more than 50 nodes summarized as top-N by relevance (fan-in or path-length).
4. If the answer requires actual source code (e.g., "show me the signing logic"), open the **smallest possible** ranges from the relevant `node.lineRange`s. Read at most 3 files; cap each read at 200 lines unless explicitly asked for more.

### Step 5 - Render

- Lead with the answer in 1-3 sentences.
- Follow with **Evidence**: node IDs and `file:line-line` references the user can click.
- When the question implies a flow, render the path as a numbered list.
- When the answer is "not in the graph", say so and offer the next steps (grep the source, `task-codemap` to sync).

### Step 6 - Stale-Graph Disclaimer

If freshness check in Step 2 flagged staleness, append a one-line note:

```
> Codemap built from commit abc1234 (12 commits behind HEAD). Run `/task-codemap` to sync.
```

## Output Format

```markdown
**Answer:** [1-3 sentence direct answer]

**Evidence:**

- `function:internal/auth/login.go:Authenticate` - `internal/auth/login.go:42-87` - validates credentials, issues JWT, writes audit log
- `function:internal/auth/jwt.go:Sign` - `internal/auth/jwt.go:14-31` - signs with HS256 using key from env

**Flow (if applicable):**

1. `endpoint:POST /login` -> `function:internal/handler/auth.go:Login` (entry)
2. -> `function:internal/service/auth.go:Authenticate` (service layer)
3. -> `function:internal/auth/jwt.go:Sign` (infra)
4. -> response with JWT

> Codemap freshness: in sync with HEAD.
```

When the answer is empty or partial:

```markdown
**Answer:** No `calls` edges to `Authenticate` recorded in the graph. Likely causes:
1. The function is only called via reflection / DI runtime wiring (graph doesn't capture).
2. The graph is stale.

**Suggested next steps:**
- Run `/task-codemap` to sync and re-ask.
- Grep the source: `Grep "Authenticate(" --type go`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph loaded; freshness checked; stale warning surfaced when applicable
- [ ] Step 3: question classified to a query plan, or fallback noted
- [ ] Step 4: entities resolved to node IDs; results capped to top-N when large; targeted file reads only when source detail needed
- [ ] Step 5: answer leads, evidence cites node IDs + file:line ranges
- [ ] Step 6: stale-graph disclaimer appended when applicable
- [ ] No invented node IDs, file paths, or line numbers

## Avoid

- Reading source code before querying the graph - the graph answers most questions for free.
- Returning raw JSON. Render as bullets, paths, flows.
- Inventing edges or nodes when the graph is silent. State the gap and offer next steps.
- Reading entire files when a node's `lineRange` tells you exactly which 40 lines to open.
- Answering high-stakes questions ("which handlers touch user PII?") on a stale graph without warning.
