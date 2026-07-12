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

Resolve a question against `.codemap/graph.json` first (cheap, structured), open 1-3 specific files only when source detail is needed. 1-3 sentence answer with citations.

## When to Use

You don't yet know which entity matters and want a short answer with citations.

- "How does the payment flow work?"
- "Which handlers touch the `orders` table?"
- "What calls `authenticate`?"
- "Where is the JWT signing key configured?"

**Not for:** structured deep-dive on one entity (`task-codemap-explain`); change/refactor/review (`task-*` skills); onboarding overview (`task-codemap-guide`).

## Inputs

| Input | Notes |
| --- | --- |
| `$ARGUMENTS` | The question, in English. Required. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Load Codemap

Use skill: `codemap-schema` (shape). Use skill: `codemap-query` (traversal patterns, resolution rules, caps, freshness check, large-graph access).

1. Missing `.codemap/graph.json` -> suggest `/task-codemap` and stop.
2. Run the `codemap-query` freshness check; warn but proceed when stale.
3. Load `graph.json` and `guides.json`.
4. Sparse-graph guard: `nodes.length < 10` -> warn that the graph is sparse and may not cover the codebase; suggest checking `.codemap/config.json#scope` and `.codemap/.codemapignore`. Proceed.

### Step 3 - Classify the Question

First, two guards:

- **Compound question** ("which handlers write X **and** is any missing Y"): split into sub-questions, run each against the rows below, then compose one answer. The "1-3 sentence" lead still applies to the headline; per-item detail goes in Evidence.
- **Out of scope** - the graph is structural (nodes/edges/layers), not a metrics store. Questions needing data the schema can't represent (test-coverage %, latency, runtime values, line counts) cannot be answered from the graph. Say so plainly and suggest the real tool (coverage report, profiler); do **not** synthesize a number from `tested_by` edges or similar. Never fabricate.

| Shape | Query plan |
| --- | --- |
| "What/where is X" | Resolve X; render summary, file:line, fan-in/out. |
| "What calls X" / "What uses X" | Incoming `calls`/`uses`/`imports`. |
| "What does X call/use" | Outgoing edges. |
| "How does flow Y work" | Match Y in `guides.json`; else BFS from an entrypoint. |
| "Which handlers/services touch table Y" | `codemap-query` "Handlers that touch table T" pattern. Filter to `writes_to` when the question says "write". |
| "Where is Y configured" | `config` nodes via `configures` edge to Y, or filter `config` by tag/name. |
| "What's the impact if I change X" | `codemap-query` "Impact of change" pattern. |
| "List all endpoints/tables/services" | Filter by type. |
| "Why does X depend on Y" | Shortest path X -> Y; render the chain. |
| "Is X missing Y" (negative existence) | Answer from edges where decisive; when judged from source, caveat that absence-in-read != absence-in-system (e.g., global middleware off-screen). |

No match -> extract entities, resolve each, walk neighborhoods, summarize.

### Step 4 - Execute

1. Resolve named entities per `codemap-query` resolution rules.
2. Walk per the chosen pattern; obey `codemap-query` caps and traversal rules.
3. Read source only when needed - smallest possible ranges from `node.lineRange`. Cap 3 files, 200 lines each.

### Step 5 - Render

Use the Output Format template. Answer leads in 1-3 sentences. Cite node IDs + `file:line-line`. Empty/silent graph -> say "not in the graph", propose next steps (grep, sync).

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

Stale variant of the freshness footer (use the canonical `codemap-query` format verbatim):

```
> Codemap built from commit abc1234 (12 commits behind HEAD, 9 days old). Run `/task-codemap` to sync.
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
- [ ] Step 2: graph loaded; freshness warning when stale; sparse-graph warning when applicable
- [ ] Step 3: compound split when needed; out-of-scope declared (not fabricated); classified to a query plan, or fallback noted
- [ ] Step 4: entities resolved per `codemap-query`; caps respected; reads minimal
- [ ] Step 5: answer leads, evidence cites IDs + file:line; freshness footer chosen correctly
- [ ] No invented IDs, paths, or line numbers

## Avoid

- Reading source before querying the graph.
- Returning raw JSON.
- Inventing edges when the graph is silent.
- Synthesizing a metric (coverage %, latency) the schema doesn't store - declare it out of scope instead.
- Reading whole files when `lineRange` is precise.
- Answering high-stakes questions (PII handlers, auth scope) on a stale graph without warning.
