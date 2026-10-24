---
name: domain-runtime-evidence
description: "Fetch Datadog and error-tracker evidence for one surface: callers, volume, latency, error rate, spans, branches, monitors, deploys; paste fallback."
metadata:
  category: domain
  tags: [domain, datadog, traces, apm, monitors, deploys, runtime-evidence]
user-invocable: false
---

# Domain Runtime Evidence

> Load `Use skill: domain-kb-layout` first and read at least its Rules and these Patterns sections: Flow card (Where to watch, Edge branches, Runtime). It owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Turns the tracing tool's and the error tracker's view of one surface into the eight named blocks `domain-flow-trace` corroborates a card with. Aggregate over a window, never a single incident. Every block is fetched, shaped from a paste, or reads `unavailable - <reason>`; nothing is estimated.

## When to Use

- `task-domain-sync` Trace pass, once per flow trigger, when `CLAUDE.md` `## Observability` names a tracing or error tool and its MCP server is reachable
- `task-domain-ask` showing live numbers for a flow
- Standalone: one surface named by the user, or a paste of the tool's output to be shaped into blocks

## Inputs

| Input     | Required | Notes                                                                                                                                 |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Surface   | yes      | The APM service name and the surface as the code registers it (`orders-api`, `POST /api/orders/:id/refund`, or `ReconcileRefundsJob`); for a ui screen trigger, the card's hop 1 (its first backend route) under the `Services:` name the hop-1 repo's tracing initialisation sets, passed by the caller (`unknown` when it passes none, which makes every tracing-sourced block `unavailable - service unknown`) |
| Branches  | no       | The card's Edge branches rows, each with its guard and the log message string or exception name the guard emits, read by the caller at the row's `Enforced at`; that string is the search marker; absent when no card exists yet or its Edge branches table holds only the `none - <evidence>` row              |
| Tracing   | yes      | `Tracing:` from `CLAUDE.md` `## Observability`; `none` is accepted                                                                    |
| Errors    | yes      | `Errors:` from `CLAUDE.md` `## Observability`; `none` is accepted                                                                     |
| Window    | no       | Days; default `window` in `_index/sync-state.json`, else 30                                                                           |
| Paste     | no       | Text the user copied from the tool; parsed into the blocks it can fill, the rest `unavailable - not in paste`                          |

## Rules

- **A paste wins.** With a paste, every block comes from it whatever `Tracing` and `Errors` say, and the summary line reads `source paste`. Without one, Datadog through its MCP server is the only tracing fetch path: any other tracing tool name, `none`, a Datadog MCP the session lists no tool for (absent: nothing is attempted), or one that fails makes every tracing-sourced block `unavailable - <reason>`, after one attempt per block when the server is present (a block whose own fetch fails reads `unavailable - <reason>` while the fetched blocks keep their values, and the summary `source` reads `datadog mcp` when any block was fetched) (another tool: `unavailable - <tool> not supported (Datadog MCP only)`; `Tracing: none`: `unavailable - no tracing tool configured`; no Datadog MCP tool listed: `unavailable - Datadog MCP not connected`). The error tracker through its own MCP server is the only errors fetch path: `Errors: none` (`unavailable - no error tracker configured`), a tool with no MCP (`unavailable - <tool> MCP not connected`), a connected MCP listing no tool for the half (`unavailable - <tool> MCP has no {issue | alert-rule} tool`), or a failing MCP makes the errors half of `monitors` and the errors suffix of `error_rate` `unavailable - <reason>`; the summary `errors` reads `<tool> mcp` when either half reads anything other than an `unavailable` form (`unavailable - errors are for <other service>` and `unavailable - alert rules are for <other service>` are such forms), else the reason both halves carry, `unavailable - <tool> MCP gave neither half for <service>` when their reasons differ (`source` likewise reads `unavailable - no tracing block fetched` when the blocks' reasons differ, `branches`' `no card branches supplied` reason left out of the comparison). No REST calls, no credentials read from files.
- **The surface is mapped to the tool's names before any query**, and the mapping is written in the summary line: a route's resource is found through its `http.route` tag (a Rails resource reads `Controller#action`, an Express resource `METHOD /route`), ignoring a `(.:format)` suffix; a job's resource is its class name, under the service its spans carry (found by that resource across the env's services when the web service has none); the operation is the service's entry operation for its integration (for example `rack.request`, `express.request`, `sidekiq.job`). Trace-metric queries filter on the tool's own tag value for the resource (its normalised form, read from the tag list the tool shows for the service), never on the raw string. A surface no resource matches makes every resource-scoped tracing block `unavailable - no resource matches <surface> on <service>`; `monitors` (matched by service name), `deploys`, and the error tracker's halves do not need the resource.
- **Blocks are named exactly** `callers`, `volume`, `latency`, `error_rate`, `spans`, `branches`, `monitors`, `deploys`, in that order, every one present.
- **Aggregate, not anecdote.** `volume`, `latency`, `error_rate` cover the whole window from trace metrics on the operation and resource. `callers`, `spans`, and `branches` come from retained traces, whose retention is shorter than the window; the blocks state the days they cover (`branches` the shorter of span and log retention), and a `no` in `branches` means not seen in retained data, nothing more.
- **`spans` is the hop view.** The representative trace is the one whose entry-span duration is nearest the `latency` block's p50 (the newest retained trace when `latency` is unavailable); it lists the entry span of each service (once per entry, so a callback into a service already seen is listed again) and every outbound client span to another service or an external system (HTTP, RPC, publish), in order and with repeats kept, so a retry shows; database and in-process spans are omitted. This list compares with a card's hop list. Distinct boundary sequences seen across retained traces are listed after it.
- **Callers are names the tool gives**: the services of the parent spans of the resource's entry spans in retained traces (a parent span carrying a client library's name, `faraday` or `net/http`, counts under the nearest ancestor span whose service is not a client library's, its base service), with their span counts (sampled, not traffic; `(from {n} returned spans)` when the tool cannot group); when only the service dependency map answers, names are listed with `count unavailable (service-level, from dependency map)`, since the map is per service, not per resource. No caller is guessed from paths; entry spans with no parent (a scheduled job, a consumer, or propagation off) read `none - no upstream caller in traces (entry spans have no parent)`.
- **The error tracker is mapped too**: its project is the one the DSN's project id or the sentry-cli config (`SENTRY_PROJECT`, the `.sentryclirc` `[defaults]` project, nothing else in that file) in the repos names, else the tool's project matching the service name; its issues are those whose transaction is the resource or the route (`Sidekiq/<JobClass>` for a Sidekiq worker); its alert rules are that project's. An issue or alert rule the paste or tool attributes to another service or transaction is not counted; each half is judged on its own: when every issue is, the `error_rate` suffix reads `unavailable - errors are for <other service>`, and when every alert rule is, the `monitors` errors line reads `unavailable - alert rules are for <other service> (errors)`.
- **One environment.** Every query is scoped to the production `env` (the env the service's monitors filter on, the one named `production` or `prod` when they filter on several, else the service's `env` tag value so named in the tool's tag list, else `unavailable - env not identified (<values seen>)`, which every tracing-sourced block then repeats; the error tracker's own when it differs, the `(errors env ...)` part absent when neither an errors fetch nor the paste's error-tracker data states an env; `unstated` when no tracing query answered), named in the summary line, so staging traffic never mixes in; a paste's env is the one it states, else `unstated in paste`.
- **Nothing invented.** A block the tool cannot answer reads `unavailable - <reason>`; a paste that lacks a block reads `unavailable - not in paste`, and one stating the data does not exist (tracing off) gives each block it would fill `unavailable - <what the paste states>`; `branches` without a Branches input reads `unavailable - no card branches supplied`; with one, every supplied branch gets its own line, `{branch}: unavailable - <reason>` when nothing could be searched.
- **Read-only.** No monitor is muted, no dashboard written, no deploy triggered.

## Patterns

### What each block asks the tool

| Block      | Datadog source                                                                          | Emitted as                                                                  |
| ---------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| callers    | Retained traces through the resource, grouped by the parent span's service              | one `{service}: {n} spans` line per caller                                  |
| volume     | Trace metric hits on the operation and resource over the window                         | `{n} per day ({n} in {window}d)`                                            |
| latency    | p50 and p95 of the latency distribution metric `trace.<operation>` on the resource, converted to ms (`trace.<operation>.duration` is a total, not a latency) | `p50 {n} ms / p95 {n} ms`                                                   |
| error_rate | Trace metric errors over hits on the operation and resource; the error tracker's distinct issues for the service and resource in the window | `{percent}`, then `; {n} unique errors in {window}d (errors)`, or `; unavailable - <reason> (errors)` when the error tool does not answer |
| spans      | Trace search, the representative trace, then boundary sequences across retained traces  | numbered `service: operation resource {duration}` boundary spans, then one line per sequence seen |
| branches   | Span and log search for each branch's guard marker in retained traces                   | `{branch}: {yes \| no}` per branch                                          |
| monitors   | Monitors whose query names the service, with or without the resource; the error tracker's alert rules for the project | `{name}: {state}` per monitor, then `{name}: {active \| disabled} (errors)` per issue alert and `{name}: {Resolved \| Warning \| Critical} (errors)` per metric alert |
| deploys    | Deployment events or `version` tag changes for the service in the window (tracing-sourced: Datadog only) | `{deploy date} {version or sha}` per deploy; `unavailable - no deploy events or version tag for <service>` when the service has neither |

Bad - a block filled from what such a service usually shows, in a shape the contract does not use:

```
volume - about 2000 per day
```

Good - honestly missing, in the contract's shape (no Datadog MCP tool listed, the Sentry MCP connected; an excerpt: `latency` reads like `volume`; `callers`, `spans`, and `branches` read `(unavailable)` over one `- unavailable - Datadog MCP not connected` line (`branches` without a Branches input: `- unavailable - no card branches supplied`; with one, `{branch}: unavailable - Datadog MCP not connected` per branch); `error_rate` and `monitors` keep their fetched `(errors)` halves):

```
- **Runtime evidence:** orders-api POST /api/orders/:id/refund, 30d ending 2026-10-24, env unstated (errors env production), source unavailable - Datadog MCP not connected, errors sentry mcp
- **volume:** unavailable - Datadog MCP not connected
- **deploys:**
  - unavailable - Datadog MCP not connected
```

### Paste mode

A paste is shaped, never reinterpreted: numbers are copied as written with their units (a count such as `3/30 runs` stays a count in the `error_rate` rate slot; latency alone is written in ms, a pasted `2.1 s` becoming `2100 ms`; a paste stating only one of p50 and p95 gives `latency` `unavailable - {p50 | p95} not in paste`, naming the missing one), a pasted sequence keeps its share or repeat note after it in parentheses, a pasted alert rule whose kind the paste does not state takes the form of the state it shows, and one whose state fits neither form reads `{name}: unavailable - kind not in paste (errors)`, spans are numbered in the order pasted and filtered to the boundary calls above, and the paste's own window and end date, when it states them, replace the input Window and are named in the summary line. A block header reads `({n}d in paste)` with the paste's stated retention or window, `(unavailable)` when it states neither; a paste stating no window keeps the input Window in the summary with `window unstated in paste` after it, and its `volume` reads `{n} in paste`. `volume` from a paste reads the pasted count over the pasted window (`44 in 30d`), the per-day figure only when pasted. A branch is `yes` when a pasted log or span line carries its guard's marker or names the same event in the paste's own words (an error-tracker issue line is neither), and the matched line follows the value as ` - "<line>"`; `no` when the paste's log or span lines were searched and none matches; `{branch}: unavailable - not in paste`, one line per supplied branch, when the paste holds no log or span lines to search.

## Output Format

```
- **Runtime evidence:** {service} {surface}{ -> {resource} ({operation}) | -> unmapped}, {n}d ending {date}{; window unstated in paste}, env {env}{ (errors env {env})}, source {datadog mcp | paste | unavailable - <reason>}, errors {<tool> mcp | paste | unavailable - <reason>}
- **callers:** {({n}d retained) | ({n}d in paste) | (unavailable)}{ (from {n} returned spans)}
  - {service}: {n} spans | {service}: count unavailable (service-level, from dependency map) | none - no upstream caller seen | none - no upstream caller in traces (entry spans have no parent) | unavailable - <reason>
- **volume:** {n} per day ({n} in {window}d) | {n} in {window}d | {n} in paste | unavailable - <reason>
- **latency:** p50 {n} ms / p95 {n} ms | unavailable - <reason>
- **error_rate:** {{percent} | {pasted count} | unavailable - <reason>}; {{n} unique errors in {window}d | unavailable - <reason>} (errors)
- **spans:** {({n}d retained) | ({n}d in paste) | (unavailable)}
  1. {service}: {operation} {resource} {duration}
  - sequences seen: {service -> service -> external system}{ (share or repeat note as pasted)}; {...} | unavailable - <reason>
- **branches:** {({n}d retained) | ({n}d in paste) | (unavailable)}
  - {branch}: {yes | no}{ - "<matched line>"} | {branch}: unavailable - <reason> | unavailable - <reason>
- **monitors:**
  - {name}: {OK | Alert | Warn | No Data | Skipped | Ignored | Unknown} | none - no monitor names this service or resource | unavailable - <reason>
  - {name}: {active | disabled} (errors) | {name}: {Resolved | Warning | Critical} (errors) | {name}: unavailable - kind not in paste (errors) | none - no alert rule in this project (errors) | unavailable - <reason> (errors)
- **deploys:**
  - {deploy date} {version or sha} | none - no deploy in {window}d | unavailable - <reason>
```

`{branch}` is the card's Edge branches `Branch` cell verbatim, and the value is the text after the `{branch}: ` prefix, the cell read verbatim, before any ` - "`. `none - no deploy` is written when the service has deploy events or a `version` tag but none in the window. `{date}` is today for a fetch and the paste's end date for a paste, the run date when the paste states none. `errors paste` is written only when the paste carries error-tracker data for the surface's service, `unavailable - errors are for <other service>` when it carries data for another service only, else `unavailable - not in paste`. The `-> {resource} ({operation})` part is written when a fetch mapped the surface or the paste names both, reads `-> unmapped` when no resource matched (every resource-scoped tracing block, all but `monitors` and `deploys`, then carries the same `unavailable` reason), and is absent when no tracing fetch was attempted and the paste names none. A list block with nothing to list carries exactly one line, the `none` or `unavailable` form (`spans` as `- unavailable - <reason>`; a paste saying a job has no callers gives whichever `none` form its words match); `monitors` carries one line per half at least, the errors half always suffixed `(errors)`; an issue alert takes the `active | disabled` form and a metric alert the `Resolved | Warning | Critical` form.

## Avoid

- Filling a block from memory of typical numbers
