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

Ask one question. Resolves against `.codemap/graph.json` first (cheap, structured), opens 1-3 specific files only when source detail is needed.

## When to Use

For questions about the system - you don't know yet which entity matters, and you want a 1-3 sentence answer with citations.

- "How does the payment flow work?"
- "Which handlers touch the `orders` table?"
- "What calls `authenticate`?"
- "Where is the JWT signing key configured?"

**Not for:**
- Structured deep-dive on one entity -> `task-codemap-explain`.
- Make a change / refactor / review -> respective `task-*` skills.
- Onboarding overview -> `task-codemap-guide`.

## Inputs

| Input | Notes |
| --- | --- |
| `$ARGUMENTS` | The question, in English. Required. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

1. Confirm `.codemap/graph.json` exists. Missing -> suggest `/task-codemap` and stop.
2. Apply the freshness rule from `codemap-query` (Freshness check). Warn but proceed when stale.
3. Load `graph.json` and `guides.json`.
4. **Sparse-graph check:** if `nodes.length < 10`, warn explicitly that the graph is sparse and may not yet cover the codebase. Suggest verifying `.codemap/config.json#scope` and `.codemap/.codemapignore`. Proceed anyway.

Use skill: `codemap-schema` for shape. Use skill: `codemap-query` for traversal and the freshness rule.

### Step 3 - Classify the Question

| Shape | Query plan |
| --- | --- |
| "What/where is X" | Resolve X; render summary, file:line, fan-in/out. |
| "What calls X" / "What uses X" | Incoming `calls`/`uses`/`imports`. |
| "What does X call/use" | Outgoing edges. |
| "How does flow Y work" | Match Y in `guides.json`; else BFS from an entrypoint. |
| "Which handlers/services touch Y" | Reverse BFS from Y over `reads_from`/`writes_to`/`calls`. |
| "Where is Y configured" | `config` nodes via `configures` edge to Y, or filter `config` by tag/name. |
| "What's the impact if I change X" | Reverse BFS depth 3 over `imports`/`calls`/`uses`. |
| "List all endpoints/tables/services" | Filter by type. |
| "Why does X depend on Y" | Shortest path X -> Y; render the chain. |

No match -> extract entities, resolve each to nodes, walk neighborhoods, summarize.

### Step 4 - Execute

1. Resolve named entities per `codemap-query`.
2. Walk the graph with the chosen pattern.
3. Cap at 50 nodes; summarize top-N by relevance.
4. Read source only when needed - smallest possible ranges from `node.lineRange`. Cap 3 files, 200 lines each.

### Step 5 - Render

- Lead with the answer in 1-3 sentences.
- Follow with **Evidence**: node IDs + `file:line-line` ranges.
- Flows render as numbered lists.
- "Not in the graph" -> say so and suggest next steps (grep, sync).

### Step 6 - Stale-Graph Footer

If Step 2 warned, append:

```
> Codemap built from commit abc1234 (12 commits behind HEAD). Run `/task-codemap` to sync.
```

## Output Format

```markdown
**Answer:** [1-3 sentences]

**Evidence:**

- `function:internal/auth/login.go:Authenticate` - `internal/auth/login.go:42-87` - validates credentials, issues JWT, writes audit log
- `function:internal/auth/jwt.go:Sign` - `internal/auth/jwt.go:14-31` - signs with HS256 using env key

**Flow (when applicable):**

1. `endpoint:POST /login` -> `function:internal/handler/auth.go:Login` (entry)
2. -> `function:internal/service/auth.go:Authenticate` (service)
3. -> `function:internal/auth/jwt.go:Sign` (infra)

> Codemap freshness: in sync with HEAD.
```

Empty or partial:

```markdown
**Answer:** No `calls` edges to `Authenticate` recorded. Likely causes:
1. Reflection / DI runtime wiring (graph doesn't capture).
2. The graph is stale.

**Suggested next steps:**
- `/task-codemap` to sync, then re-ask.
- `Grep "Authenticate(" --type go`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: graph loaded; freshness warning when applicable
- [ ] Step 3: classified to a query plan, or fallback noted
- [ ] Step 4: entities resolved; results capped; reads minimal
- [ ] Step 5: answer leads, evidence cites IDs + file:line
- [ ] Step 6: stale footer when applicable
- [ ] No invented IDs, paths, or line numbers

## Avoid

- Reading source before querying the graph.
- Returning raw JSON.
- Inventing edges when the graph is silent.
- Reading whole files when `lineRange` is precise.
- Answering high-stakes questions (PII handlers, auth scope) on a stale graph without warning.
