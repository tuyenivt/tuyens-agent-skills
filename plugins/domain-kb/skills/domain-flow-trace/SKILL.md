---
name: domain-flow-trace
description: "Trace one business flow end to end across service repos from its trigger: sequence, state changes, side effects, rules, edge branches, failure modes."
metadata:
  category: domain
  tags: [domain, flow, trace, business-flow, reverse-engineering, cross-service]
user-invocable: false
---

# Domain Flow Trace

> Load `Use skill: domain-kb-layout` first: it owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Follows one real business action from its trigger through every service, write, and side effect until nothing else happens, and emits the flow card `domain-kb-layout` defines. Code is the source of every hop; a runtime trace, when one is reachable, corroborates.

## When to Use

- `task-domain-sync` building or regenerating a flow card
- `task-domain-sync` corroborating a written card: corroborate mode takes the card and the runtime blocks and emits only the fields Step 7 lists for it
- Standalone: one trigger named by the user; the card is emitted inline, never written

## Inputs

| Input              | Required | Notes                                                                                                                                                  |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Trigger            | yes      | A surface (`METHOD /path`, a screen path, a job or schedule name, a webhook path, a topic), or an existing `<capability>/<flow>` id to re-trace          |
| Capability         | yes      | The capability id, or `proposed: <name>` when the caller has none                                                                                       |
| Repos              | yes      | The `repos/<repo>/` directories in scope, each with the stack note from `_index/sync-state.json` (standalone with no sync state: read from the repo's manifest, `Gemfile`, `package.json`, `go.mod`, `pyproject.toml`, `pom.xml`, `build.gradle(.kts)`, `pubspec.yaml`, else `unknown stack`); the note tells Step 1 where the framework registers routes, jobs and listeners |
| KB root            | no       | Generated: `ledger/rules.md`, `debt/register.md`, `contracts/`, and the flow's existing card when one exists; curated: `rules/`, `specs/`, `context/`, `incidents/`, `adr/`, `consumers/`; the generated part is absent on a fresh `init` |
| Surface inventory  | no       | `surfaces/<repo>.md`; Step 2 looks there first for the route or consumer behind a URL, client name or topic, and searches the repos only when it has no answer |
| Observability      | no       | `Tracing:` and `Errors:` from `CLAUDE.md` `## Observability`; both default `none`                                                                       |
| Runtime evidence   | no       | Blocks named `callers`, `volume`, `latency`, `error_rate`, `spans`, `branches`, `monitors`, `deploys` for the trigger's surface (the first backend hop for a ui screen), as `domain-runtime-evidence` emits them; a raw paste is first shaped into the blocks by Use skill: `domain-runtime-evidence` in paste mode; `monitors` adds to Where to watch, `deploys` adds Recent changes rows; `spans` lists service-boundary calls, compared to the hop list; `branches` is fetched whenever a card exists (a re-trace or corroborate mode), from that card's Edge branches, each passed with the log message its path emits, read from the code at its `Enforced at` |
| Window             | no       | Days for Recent changes and trace corroboration; default is `window` in `_index/sync-state.json`, else 30                                                |
| Audience language  | no       | The `Language:` list from `CLAUDE.md` `## Audience`; the second code, when listed, is the second Story sentence's language                             |

## Rules

- **A flow is one trigger to quiescence.** Synchronous calls and message hops stay in the flow, across repos, and so does an external system's callback (a `webhook in`) that completes a hop this flow started: the external hop is followed by the callback hop. A later pickup by a schedule, a human action, or a callback that starts a new business action is a new trigger and a separate flow, named under Related by its trigger surface and never inlined.
- **A hop is a surface crossed between services or external systems**, never a class or function inside one process and never a database write, which is a State changes row; the surface string is the full path composed from every statement that contributes to it (namespace, mount, prefix) in the framework's own parameter syntax (`POST /api/orders/:id/refund`), the string the surface inventory holds; App Router route groups `(x)` and `@slot` folders are not path segments, `_private` and intercepting `(.)x` folders are not routes, and a Next.js server action is not a surface: its hop is the backend call it makes, and an action that only writes its own database makes no hop. Every hop cites the registration line as `file:line`, root-relative under `repos/`; a hop to an external system cites the client call. A hop the code implies but cannot pin (dynamic dispatch, config-driven routing) is `(unverified)`; a client whose base URL is an env var is pinned when a route in another repo matches its path. A hop that leaves the repos in scope is `(external - not in repos)`; the flow continues past it only through a response or a callback that shapes the next hop. A message channel is one hop, named `<event type or topic>: <publisher> -> <consumer>` and cited at the consumer's binding; its surface for matching is the part before the colon. A hop registered in two files (route and mount) cites the registration line; the other file joins `files`.
- **Follow the writes, not the returns.** The flow ends when the last state change and side effect has landed, including async consumers in other repos. Every branch on the path that leads to further hops is traced to quiescence and rendered as `branch a` / `branch b` sub-items of the hop where the path forks; a `branches` block showing a branch never fired does not shorten the trace, since incidents come from the branches traces do not show. A published message with no consumer in any repo is a side effect whose target reads `consumer not in repos`.
- **Rules, guards, and edge branches are disjoint.** A rule is a policy condition on business data (who, how much, when, where, which plan) that changes the outcome, one row per condition. A transition guard, an idempotency check, or an already-done check belongs only in the State changes `Guard` column. An edge branch is a path taken rarely: error handling, retry, compensation, feature flag, legacy fallback, partial failure. The entry point's own checks are the one exception: the entity state and the authentication or permission it requires are Preconditions, and their rejection paths are edge branches; neither is also a Rule or a Guard.
- **Confidence comes from evidence in scope.** `documented` when a comment, test name, in-repo spec, or a curated `rules/`, `specs/`, `context/`, or `adr/` file at the KB root states the reason, the `Rationale` cell ending with that source's path or `file:line` in parentheses; `inferred` when the reason follows from the code shape (a limit matching a provider's documented cap); `unknown` otherwise, including a comment that only cites a ticket. `domain-rationale-chain` may later upgrade a row through commit and PR history; this atomic never guesses.
- **Quirk is `yes`** when a rule has `unknown` rationale, contradicts a document in scope, hardcodes a business constant with no named source, or sits under a `TODO`, `FIXME`, `HACK`, `workaround`, or `legacy` marker.
- **`verified_by_trace` is `true` only when the `spans` block's boundary calls match the hops of the path that trace took**, in order; branches the trace did not take are not compared. A hop matches the callee's entry span (its client span is the same hop); the entry hop of a ui screen or schedule matches the first service's entry span. A trace that differs (a hop missing, or an extra boundary call such as a retry the code does not make) keeps `false` and adds a `trace differs` Debt row citing the first differing hop.
- **Nothing invented.** Monitors, dashboards, error-tracker captures, and job names are cited from files, or from the observability tool's own list marked `(from observability tool)`; log queries are built from the log message strings the code emits; anything else reads `unknown - not discoverable from the repos`.
- **Debt lists only what the trace evidenced:** a swallowed error, a write outside the transaction that needed it, a boundary hop with no monitor, a missing containment on a hop, `trace differs`, an unreachable precondition, a contract mismatch (a response value, status, or event one side sends that the other does not handle). No general code review. Each row reads `D-n: class: severity: category: finding - file:line - trade-off made - cost today`, the class being the layout's phrase for the item above, `severity` `high` when the finding can lose or duplicate a money movement or a customer-visible write, `medium` when it can lose a signal or delay recovery, `low` otherwise, `category` `correctness` for a swallowed error, a write outside transaction, an unreachable precondition, or a contract mismatch, `operational` for a missing monitor or containment or `trace differs`, the trade-off the code or history shows (`none recorded` otherwise), and the cost the observable consequence.
- **Ids persist.** A rule row keeps the id its prior card or the ledger gives it when its enforcement site (file plus text) persists, then when its text alone persists; a debt row keeps the register id of a prior row with the same `Location` file (line ignored) and the same class; any other row is `R-new` or `D-new` for the consuming workflow to number. This atomic never writes the card.

## Patterns

### Step 0 - Name, id, frontmatter, Story

- **Name**: the business action in stakeholder words, verb first (`Refund an order`, `Ship a print job`); for a callback trigger, the action the callback completes. **Id**: kebab-case, object then action (`order-refund`, `print-job-ship`). A re-trace keeps the existing id, `aliases` (union), `priority`, and the `## Notes` section verbatim; a new flow gets `priority: 0` and `ranked_by: unranked`.
- **Frontmatter**: `sources` as `repo@` plus the first 7 characters of `git rev-parse HEAD` in every repo a hop cites, and every citation read at that checkout, never at a recorded sync `sha`; `synced` today; `freshness: current`; `capability` from the input, or the proposed name; `files` as the Files on path list below.
- **Story**: one sentence naming the actors and the business outcome, no service, endpoint or table names; a second sentence in the second Audience language on the same line when one is listed.

### Step 1 - Resolve the trigger to its entry point

| Kind          | Where the entry point is                                                                                                                 |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| ui screen     | The screen's data calls in the frontend repo (fetch, client, server action, form action), then the backend route each call hits; the Surface is the screen path as the router registers it (`/orders/[id]/refund`) |
| public api    | The route registration, then its handler; an auth check of any form (middleware, inline token compare) is named in Preconditions, and its rejection path is an edge branch |
| internal api  | Same as public api; the caller repo is found by the URL or client name in the other repos                                                  |
| schedule      | The scheduler definition (cron table, scheduler config, annotation), then the job class or function                                        |
| webhook in    | The route, its signature or secret check, then the handler                                                                                 |
| message       | The consumer or listener bound to the topic or queue, then its handler                                                                     |

A `<capability>/<flow>` id resolves to the existing card's Trigger. `Actor` is who or what initiates; `Preconditions` are the entity state and permissions the entry point requires. A precondition no code in scope produces (a state nothing transitions to) is marked `(no producer in repos)` and gets a Debt row.

### Step 2 - Walk the hops

From the entry point: handler -> writes (ORM, repository, raw SQL) -> outbound calls (HTTP clients, SDKs, publishes, mail, files). For each outbound call or publish, find the receiving route or consumer in the other repos by URL path, client name, or topic (surface inventory first), and continue there. Render the Sequence as a Mermaid `sequenceDiagram` with one participant per service or external system and each arrow labelled with the surface, then the numbered hop list with citations and markers; `Hops` in the summary counts its numbered items, the entry hop included and branch sub-items not.

Bad - hops named by layer, an in-process step counted as a hop:

```
1. orders-api -> OrderService
2. OrderService -> payments-api
```

Good - hops named by surface, cited, in-process steps absent:

```
1. POST /api/orders/:id/refund - repos/orders/config/routes.rb:5
2. POST /payments/refunds - repos/payments/src/routes/refunds.ts:9
3. POST /v2/refunds - repos/payments/src/gateway/client.ts:17 (external - not in repos)
```

### Step 3 - Collect state changes and side effects

A state change is a write to a column that names a lifecycle (`status`, `state`, a phase flag), a row creation for a lifecycle entity (`From` is `new`), or a row deletion (`To` is `deleted`); its guard is the condition the code checks before writing. A side effect is anything that leaves the domain's databases: webhook out, event, email, third-party call, file; `When` is the condition on the path under which it fires. Both tables cite the line that performs the write or send.

### Step 4 - Extract rules and edge branches

Walk every conditional on the path once and sort it:

| Condition tests                                        | Goes to                       |
| ------------------------------------------------------ | ----------------------------- |
| Business data: who, how much, when, where, which plan  | Rules, one row per condition  |
| Entity state, idempotency key, already done            | State changes `Guard` only    |
| Error, timeout, retry, compensation, partial failure   | Edge branches                 |
| Feature flag, legacy fallback, migration toggle        | Edge branches                 |
| Nil or type guard with no business outcome             | Neither                       |

A rule's `Id` follows the Ids persist rule; every card row has `Kind` `code` and `Doc` `none`, which the consuming workflow's Link pass fills from `rules/`. Rationale evidence: comments on the enforcing lines, the tests that exercise them, specs in the repos, and the curated `rules/`, `specs/`, `context/`, and `adr/` docs at the KB root. Edge branches fill `Exercised in traces` from the `branches` block, `unavailable` without it; the column header carries the days the block covered, the window without it.

### Step 5 - Where to watch

Sources, in order: monitor definitions in the repos (Terraform, monitors JSON or YAML, alert rules), the error tracker's initialisation and the capture calls, message strings, or alert rules on the path, dashboard definitions, the log message strings on the path (the log query is built from them and the service name), the APM service names from tracing config, with the resource from the runtime evidence's summary mapping when supplied, else `resource unknown - not discoverable from the repos`. An errors-half `monitors` line is appended to the Error tracker line as `; alert rules: <name> (from observability tool)`. Each cited by path. Monitors and Error tracker each take exactly one of the layout's shapes. Monitors: the names found, each `- file:line`, plus `<name> (from observability tool)` for a monitor the `monitors` block names that no file defines (one a file defines adds nothing), the `none` and `unknown` forms applying only when neither files nor the tool name one; `none - no monitor definition in the repos (tracing: <tool> configured, run task-domain-sync with its MCP connected to list monitors)` when `Tracing:` names a tool and no file defines a monitor for the flow; `unknown - no tracing tool configured` when `Tracing:` is `none` and no file defines one. Error tracker: `<tool> - <init file:line>; captures on this path: <strings - file:line | none>` when `Errors:` names a tool and a service on the path initialises it, `<tool> - no init in <services on the path>; captures on this path: none` when none does (another service's init is not cited), `none - no error tracker configured` when `Errors:` is `none`. A line never mixes `unknown` with a tool name.

### Step 6 - Failure modes

One row per hop, plus one per transaction block (`transaction do`, `BEGIN`, a transactional decorator) on the path, whose failure is the database refusing the write. Use skill: `failure-propagation-analysis` in `what-if` mode once per hop, and once per transaction block on a database other services share, assuming the far side is unavailable: a synchronous callee timing out, a consumer stopped, an external system returning 5xx, a database refusing connections; its Propagation Path compresses into `What breaks`, its Shared Resources into `First check` (the receiving side's log line when it reports none), and its Containment Assessment becomes a `missing containment` Debt row when the containment it names is absent. Its own envelope is not emitted. `User sees` is what the caller or user observes at the entry point when that hop fails, read from the error handling on the path. A hop whose callee only rejects (a validation fails, it returns 4xx) is filled from the code alone. `Detected by` cites exactly one Step 5 monitor name (preferred when both cover the hop), one Error tracker capture string, `none - no monitor covers this hop` when Step 5 names some but none for this hop, or repeats the Monitors line's `none` or `unknown` form; a capture string is cited only when the Error tracker line lists it.

### Step 7 - Contract and runtime

Contract, only when Kind is `public api` or `webhook in`: `Request` from the parameters the handler reads and validates, `Response` from what it renders, `Errors` from the status codes it returns and when, `Idempotency` from the key it reads and the lookup it performs, with the lookup's time bound as the window, `<key> - unbounded` when the lookup has none, and `none - no key read` when the handler reads no key; `Callers` from `contracts/` when it exists, then external callers the `callers` block names, marked `(external - from traces)`.

Runtime, always: `callers`, `volume`, `latency`, `error_rate` blocks fill the four lines; the `spans` block is compared to the hop list for `verified_by_trace`; a caller in the `callers` block that matches no repo in scope is added as `<name> (external - from traces)` to Contract `Callers`, or, when the card has no Contract, marked so on its Runtime `Callers` entry. Corroborate mode emits only these fields, each labelled with its section, for the consumer to mark onto the card: the four Runtime lines, Contract `Callers` additions, `Exercised in traces` cells, `verified_by_trace`, Where to watch `<name> (from observability tool)` monitor lines, Recent changes rows `| {date} | deploy {version or sha} | deploy | none |`, a `trace differs` Debt row, and the summary's `Verified by trace` line; it reads code only for the citation a `trace differs` row needs. Absent blocks: every Runtime line `unavailable - not requested` when no evidence was asked for, `unavailable - <reason>` when the fetch failed; `verified_by_trace: false`; summary `Verified by trace: unavailable`.

### Step 8 - Recent changes, debt, how to see it, related

Recent changes: read-only `git -C repos/<repo> log --since=<window start>` over each repo's files on the path, repo-relative, one row per commit or PR, plus one row per `deploys` entry in the window with `Source` `deploy`. Debt: per the scope and Ids persist rules. How to see it: the screen routes on the path, the job class or schedule name, the log message strings in the order they fire, the tables and columns Step 3 named. Related: the flows this one hands off to (new triggers found in Step 2) and the flow that produces its precondition state, each by `<capability>/<flow>` when a card whose Trigger Surface equals the whole surface string exists, else `flow to trace: <kind>: <surface>`; the rules by id (a new rule by its rule text); `doc: <path>` for every curated `rules/`, `specs/`, `context/`, `incidents/`, and `adr/` file whose text names a surface, entity state, or rule on the path; and `consumer: consumers/<name>.md` for every `(external - not in repos)` target or `(external - from traces)` caller that has a doc of that name.

## Output Format

The flow card exactly as `domain-kb-layout` defines it (frontmatter through `## Notes`), then this summary block.

```
- **Flow trace:** {capability}/{flow-id}
- **Trigger:** {kind}: {surface}
- **Hops:** {n} ({n} unverified, {n} external)
- **Repos touched:** {repo, repo}
- **Verified by trace:** {yes | no | unavailable}
- **Files on path:**
  - {repos/<repo>/<path>}
```

Corroborate mode emits instead one block per field that has something to mark, in the order Step 7 lists them:

```
### {Section}: {field}

{the field's value, in the card's shape}
```

`Files on path` lists every repo file any section cites, once each, wiring and registration files included and KB-root files excluded; it is also the card's `files` list. `{capability}` reads `proposed: <name>` when the input was proposed, so the consumer adds it to the capability set before writing. `Verified by trace` is `yes` for `verified_by_trace: true`, `no` when evidence was present and differed, `unavailable` when no `spans` block was supplied.

## Avoid

- Tracing by call graph alone and stopping at the first publish, leaving the async consumers untraced
- Inlining a scheduled pickup or a later human action as more hops of the same flow
- Counting an in-process call as a hop, or naming a hop by its class instead of its surface
- Listing a transition guard as a business rule, or a business condition as an edge branch
- Setting `verified_by_trace: true` because a trace exists for the service, without matching spans to hops
- Filling How to see it or Where to watch from what such systems usually have rather than from files in the repos
- Writing an Error tracker line that names a tool and reads `unknown` in the same breath, or a `Detected by` that cites a capture the line does not list
