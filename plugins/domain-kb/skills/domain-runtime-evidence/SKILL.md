---
name: domain-runtime-evidence
description: Fetch Datadog evidence for one surface over a window: callers, volume, latency, error rate, spans, branches, monitors, deploys; paste fallback.
metadata:
  category: domain
  tags: [domain, datadog, traces, apm, monitors, deploys, runtime-evidence]
user-invocable: false
---

# Domain Runtime Evidence

Turns the observability tool's view of one surface into the eight named blocks `domain-flow-trace` corroborates a card with. Aggregate over a window, never a single incident. Every block is fetched, shaped from a paste, or reads `unavailable - <reason>`; nothing is estimated.

## When to Use

- `task-domain-sync` Trace pass, once per flow trigger, when `AGENTS.md` `## Observability` names a tool and its MCP server is reachable
- `task-domain-ask` and `task-domain-explain` showing live numbers for a flow
- Standalone: one surface named by the user, or a paste of the tool's output to be shaped into blocks

## Inputs

| Input     | Required | Notes                                                                                                                                 |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Surface   | yes      | The APM service name and the surface as the code registers it (`orders-api`, `POST /api/orders/:id/refund`, or `ReconcileRefundsJob`); for a ui screen trigger, the first backend hop |
| Branches  | no       | The card's Edge branches rows, each with its guard and the log message or span the guard produces; absent on a first trace              |
| Tool      | yes      | `Tool:` from `AGENTS.md` `## Observability`                                                                                            |
| Window    | no       | Days; default `window` in `_index/sync-state.json`, else 30                                                                           |
| Paste     | no       | Text the user copied from the tool; parsed into the blocks it can fill, the rest `unavailable - not in paste`                          |

## Rules

- **A paste wins.** With a paste, every block comes from it whatever `Tool` says, and the summary line reads `source paste`. Without one, Datadog through its MCP server is the only fetch path: any other tool name, `none`, or a Datadog MCP that is absent or fails makes every block `unavailable - <reason>` after one attempt per block. No REST calls, no credentials read from files.
- **The surface is mapped to the tool's names before any query**, and the mapping is written in the summary line: the resource is found by searching the service's resources for the route path or the job name (a Rails route appears as `Controller#action` with the path in `http.route`; a job as its class name), and the operation name is the service's request or job operation (`rack.request`, `express.request`, `sidekiq.job`). A surface no resource matches makes every block `unavailable - no resource matches <surface> on <service>`.
- **Blocks are named exactly** `callers`, `volume`, `latency`, `error_rate`, `spans`, `branches`, `monitors`, `deploys`, in that order, every one present.
- **Aggregate, not anecdote.** `volume`, `latency`, `error_rate` cover the whole window from trace metrics on the operation and resource. `callers`, `spans`, and `branches` come from retained traces, whose retention is shorter than the window; the blocks state the days they cover, and a `no` in `branches` means not seen in retained traces, nothing more.
- **`spans` is the hop view.** The representative trace is the one whose duration is nearest the p50 in the covered days; its spans are listed only where the service changes from the previous span, so the list compares hop for hop with a card's hop list. Distinct boundary sequences seen across retained traces are listed after it.
- **Callers are names the tool gives**, upstream services from the trace search facet with their span counts; when only the service dependency map answers, names are listed with `count unavailable`. No caller is guessed from paths.
- **Nothing invented.** A block the tool cannot answer reads `unavailable - <reason>`; a paste that lacks a block reads `unavailable - not in paste`; `branches` without a Branches input reads `unavailable - no card branches supplied`.
- **Read-only.** No monitor is muted, no dashboard written, no deploy triggered.

## Patterns

### What each block asks the tool

| Block      | Datadog source                                                                          | Emitted as                                                                  |
| ---------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| callers    | Trace search on the service and resource, faceted by upstream service                   | one `{service}: {n} spans` line per caller                                  |
| volume     | Trace metric hits on the operation and resource over the window                         | `{n} per day ({n} in {window}d)`                                            |
| latency    | Trace metric duration p50 and p95 on the operation and resource                         | `p50 {ms} / p95 {ms}`                                                       |
| error_rate | Trace metric errors over hits on the operation and resource                             | `{percent}`                                                                 |
| spans      | Trace search, the representative trace, then boundary sequences across retained traces  | numbered `service: operation resource {duration}` boundary spans, then one line per sequence seen |
| branches   | Span and log search for each branch's guard marker in retained traces                   | `{branch}: {yes \| no}` per branch                                          |
| monitors   | Monitors list filtered by the service and the resource                                  | `{name}: {state}` per monitor                                               |
| deploys    | Deployment events or `version` tag changes for the service in the window                | `{date} {version or sha}` per deploy                                        |

Bad - a block filled from what such a service usually shows, in a shape the contract does not use:

```
volume - about 2000 per day
```

Good - fetched, or honestly missing, in the contract's shape:

```
- **volume:** 1834 per day (55020 in 30d)
- **deploys:**
  - unavailable - no deployment events for orders-api in 30d
```

### Paste mode

A paste is shaped, never reinterpreted: numbers are copied as written with their units, spans are numbered in the order pasted, and the paste's own window and end date, when it states them, replace the input Window and are named in the summary line.

## Output Format

```
- **Runtime evidence:** {service} {surface} -> {resource} ({operation}), {n}d ending {date}, source {datadog mcp | paste}
- **callers:** ({n}d retained)
  - {service}: {n} spans | {service}: count unavailable | none - no upstream caller seen | unavailable - <reason>
- **volume:** {n} per day ({n} in {window}d) | unavailable - <reason>
- **latency:** p50 {ms} / p95 {ms} | unavailable - <reason>
- **error_rate:** {percent} | unavailable - <reason>
- **spans:** ({n}d retained)
  1. {service: operation resource duration}
  - sequences seen: {service -> service -> service} | unavailable - <reason>
- **branches:** ({n}d retained)
  - {branch}: {yes | no} | unavailable - <reason>
- **monitors:**
  - {name}: {OK | Alert | Warn | No Data | Skipped | Ignored | Unknown} | none - no monitor names this resource | unavailable - <reason>
- **deploys:**
  - {date} {version or sha} | none - no deploy in {window}d | unavailable - <reason>
```

`{date}` is today for a fetch and the paste's end date for a paste. `{resource}` and `{operation}` read `unmapped` when no resource matched, and every block then carries the same `unavailable` reason. A list block with nothing to list carries exactly one line, the `none` or `unavailable` form.

## Avoid

- Filling a block from memory of typical numbers
- Treating one incident's trace as the representative sequence
- Calling any endpoint or tool other than the Datadog MCP server
- Listing every span of a trace instead of the service-boundary spans
- Marking a branch `no` because the guard was not searched for
