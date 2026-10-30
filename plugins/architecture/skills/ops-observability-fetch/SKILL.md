---
name: ops-observability-fetch
description: Fetch oncall evidence - issues, metrics, logs, traces, deploys, monitors - via observability MCPs. Normalizes into blocks; falls back to paste-mode.
metadata:
  category: ops
  tags: [oncall, observability, evidence, mcp, sentry, datadog]
user-invocable: false
---

# Ops Observability Fetch

Transport-agnostic evidence gathering for oncall workflows. Detects available MCP servers, parses tool URLs, emits normalized evidence blocks. Falls back to paste prompts when no transport is available.

## Capabilities and URL Recognition

| Capability      | Emits block     | Inputs                              | URL pattern (auto-fetch trigger)                                                          |
| --------------- | --------------- | ----------------------------------- | ----------------------------------------------------------------------------------------- |
| `fetch_issue`   | `error_event`   | issue ID or URL                     | a Sentry issue path `/issues/{numeric id}` on `{org}.sentry.io` or `sentry.io/organizations/{org}/...`, or the regional API forms `us.sentry.io/api/0/organizations/{org}/issues/{id}/` and org-less `us.sentry.io/api/0/issues/{id}/` (also `de.`) |
| `fetch_monitor` | `monitor_state` | monitor ID or URL                   | a Datadog `/monitors/{id}` path on any site host                                          |
| `fetch_trace`   | `trace`         | trace ID or URL                     | a Datadog `/apm/trace/{id}` path on any Datadog site host, or a trace path on a host the project's `## Observability` section names for tracing |
| `query_logs`    | `log_window`    | service, window, filters / corr. ID | a Datadog `/logs?query=...&from_ts=...&to_ts=...` path (extract query + window)            |
| `query_metrics` | `metric_series` | metric name(s), window, filters     | none - metrics require a named metric                                                      |
| `list_deploys`  | `deploy_event`  | service(s), window                  | none                                                                                       |

**Host forms.** Datadog sites vary by region and several carry no `app.` label - `app.datadoghq.com`, `app.datadoghq.eu`, `us3`, `us5`, `ap1`, `ap2` under `.datadoghq.com`, and `app.ddog-gov.com`, plus custom org sub-domains on the same site domains. Sentry's browser-facing issue URLs are `{org}.sentry.io/...` or `sentry.io/organizations/{org}/...`; its regional `us.` and `de.` hosts are API domains: `/api/0/organizations/{org}/issues/{id}/` carries the org and the deprecated `/api/0/issues/{id}/` does not - treat both as valid, and for the org-less form ask for the org slug as for a short ID.

Match on host and path together: path alone would claim `/issues/{id}` URLs belonging to GitLab, Jira and every internal tracker. For self-hosted Sentry, which can live on any hostname, take the whole Sentry path shape (`/organizations/{org}/issues/{id}`) as the signal: emit the block with `Tool:` omitted; when a Sentry transport serves it, write `Tool: sentry` and ask no vendor question; otherwise close it with `Paste prompt (no transport):` and add a trailing `Question:` confirming the vendor. A URL that matches a path shape but fails the host test (a tracker's `/issues/{id}`) gets a `Note:` and no block. Datadog is SaaS-only and has no self-hosted form.

**Sentry short IDs** (`PROJ-123`, `FRONTEND-3D` - the uppercased project slug, which may itself contain hyphens, plus an alphanumeric suffix) already encode the project, so only the org slug is missing. With no URL to carry it, take the org slug from the project's `## Observability` section; where that is absent too, emit the block unavailable, ask for the slug in the trailing notes, and fetch once answered.

**Dashboard URLs** (`*/dashboard/*`, Grafana's `/d/{uid}/...`) are never auto-fetched - they aggregate many tiles. A dashboard URL anchors no block on its own: ask which metric or panel in the trailing notes and emit the resulting `metric_series` once answered; its time range, when the URL carries one, fills that block's `Window`. Where the consumer separately asked for `metric_series`, that request still gets its block, unavailable with `Needs:` naming what is still missing (metric name, window); when the consumer already named the metric, the dashboard URL contributes only its time range (where it carries one and no window was given) and otherwise becomes a `Note:`.

## Rules

- **Detect transport once per invocation, per vendor; do not narrate the probe.** Partial availability is normal: fetch via available transports, paste-prompt the rest.
- **URL recognition runs before asking for paste.** If input contains a recognized URL, auto-fetch. Parse IDs and windows out of URLs even when the transport is unavailable - they belong in the unavailable block.
- **Never invent values.** A field the source returned empty stays `unknown`; a field it did not return is omitted; a capability that cannot be fetched produces an unavailable block closed by its `Needs:` or `Paste prompt` line.
- **Source tag uses roles, not vendor names:** `mcp` (any MCP transport), `user-paste`, `unavailable`. `unavailable` covers every reason the data did not arrive - no transport, a missing required parameter, or a call that errored or timed out - and the block's closing line says which. A call that succeeded and returned nothing is `mcp` with an empty result, not `unavailable`: an empty log window or deploy list is evidence of absence and must not be re-requested from the user. Name the vendor in the block's `Tool:` line when the serving transport, a URL host, the project's `## Observability` section, or the paste names it; omit the line otherwise - proximity to another vendor's URL is not a source. When the user later pastes the requested data, re-emit the block normalized with `Source: user-paste`, carrying the fields the paste supplied plus the input-parsed fields (ID, service, window) and any computed `Total in window`; a pasted time without seconds is padded with `:00`, and one without a date takes the latest date that places it inside the block's Window, else the latest date that does not place it after the current time, so every timestamp is full ISO; `Z` is appended only when the paste states UTC, and an unstated zone stays zone-less with a trailing `Question:` asking for it. Values the input text itself states beyond identifiers and scope (an event count, a first-seen time) are a paste too: the block is `Source: user-paste` carrying them.
- **Emit every block the consumer asked for** - as unavailable when it cannot be fetched, even when the input gives no anchor for it - **plus blocks the input directly anchors** - one block per capability/target, deduplicated across the two sets. Anchors: a recognized URL, or an explicit ID, metric name, or service+window in the request text. Nothing else - no speculative padding.
- **Block order:** consumer-requested blocks first in requested order, then input-anchored extras in input order.
- **Output starts with the first block.** No preamble, no transport narration. After the last block come the notes, in input order, one line each: `Question:` for a parameter still needed (org slug, metric name, window, which dashboard panel), a vendor to confirm, or the time zone of a pasted timestamp, `Note:` for a URL that produced no block for any other reason. One line per URL, not two - a dashboard URL is a `Question:` while the metric is unnamed and a `Note:` once it is named. A block missing several parameters lists them all on one `Needs:` line and asks one `Question:`.
- **Window required** for `query_metrics`, `query_logs`, `list_deploys`. Resolve relative windows ("last 48h") against the current time, convert epoch-ms URL parameters, and display ISO timestamps. A missing window is a missing parameter: ask for it in the notes. Other capabilities carry their own context.
- **`list_deploys` emits one `deploy_event` block per deploy**, newest first, grouped by service in requested order and capped at 5 per service, with `Total in window: {N}` on the first block when the cap bites; a fetched empty list emits one block carrying only `Source`, `Tool`, `Service`, `Window` and `Total in window: 0`. Unavailable mode emits one block per requested service carrying the service and whatever window is known, its paste prompt requesting that service's list. The same cap and `Total in window` line apply when that list is pasted. Where the consumer named no service, or no window can be resolved from the request, that missing parameter takes precedence and the block asks for it.

## Transport Detection

Read the available MCP tool names and match them to capabilities by what they do, not by a fixed name. The namespace segment is the user's own server key in their MCP config (`sentry-remote`, `dd`, `obs`), so a prefix like `mcp__sentry__*` is a hint, never a test - a correctly installed server under another key must still be found. Tool names differ by vendor: Sentry exposes issue lookups such as `find_issues` and `get_issue_details`; Honeycomb exposes `run_query` and `list_datasets`; Grafana exposes `query_prometheus` and `query_loki_logs`. Map whatever exists onto the six capabilities.

Deploy data hides under release and event names rather than a "deploys" tool: Sentry exposes release lookups, Datadog exposes software-delivery and event search. Look for those before concluding `list_deploys` has no transport. Where none exists, it resolves to an unavailable `deploy_event` block plus a paste prompt, since a CI or release API is the other place deploy data lives.

If two transports expose the same capability, prefer the one named in the project's `CLAUDE.md` under `## Observability`; otherwise ask once.

## Unavailable Blocks and Paste Prompts

When a capability cannot be fetched, emit the block with `Source: unavailable`, any fields parseable from the input (ID, window, service, filters), and one closing line. Which closing line depends on why:

- **A required parameter is missing** (metric name, org slug, window) - a `Needs:` line naming every missing parameter, and the matching question in the trailing notes. Ask for the parameter even when no transport is connected: it is the cheaper answer, it may resolve the block outright, and it is what the caller must supply either way. Do not also ask for a paste in this branch.
- **Everything needed is present but the fetch cannot happen** - no transport, or the call failed - a `Paste prompt (no transport | call failed: <error>):` line naming the tool when known, else the source kind ("your deploy history for ledger-svc"), and the block's minimum fields from the table below. The user supplies the data.

| Block           | Minimum paste fields                                                              |
| --------------- | --------------------------------------------------------------------------------- |
| `error_event`   | message, top stack frame, first_seen/last_seen, event count, release              |
| `metric_series` | metric name, window, points (`ts=value` series, or `p50/p99/max` summary - either) |
| `log_window`    | service, window, 10-30 representative lines with timestamps                       |
| `deploy_event`  | timestamp, service, commit sha for each deploy in the window                      |
| `monitor_state` | name, status, threshold, current value, last triggered                            |
| `trace`         | trace ID, services traversed, error span count, slowest span                      |

Derived fields (`Baseline delta`, `Anomaly`) are computed, never requested from the user: when a transport is available, fetch the same-length series from 7 days earlier as the baseline to compute them; with no baseline to compare against, write `Baseline delta: no baseline` and `Anomaly: unknown - no baseline`. With a baseline, `Anomaly: yes` when the window departs from it by more than the threshold the consumer or the project's `## Observability` section states, `unknown - no threshold` when none is stated, and `no` otherwise. Unavailable and user-paste blocks carry neither field, since nothing was fetched to derive them from.

A block can carry a parsed value and still need another. Examples, for the input `acme.sentry.io/issues/6630114/` plus an `app.datadoghq.com/dashboard/...` URL and "orders-api error rate over the last hour", with no transport connected - a no-transport block and a missing-parameter block whose window was resolved from the stated range:

```
### error_event
Source: unavailable
Tool: sentry
ID: 6630114
Paste prompt (no transport): From Sentry issue 6630114, paste: message, top stack frame, first seen / last seen, event count, release.

### metric_series
Source: unavailable
Tool: datadog
Filters: service:orders-api
Window: 2026-09-03T13:31:00Z to 2026-09-03T14:31:00Z
Needs: metric name

Question: which metric should I pull for orders-api error rate? The dashboard URL aggregates many tiles, so I cannot pick one from it.
```

## Output

Each block carries `Source:`, `Tool:` (omit when the vendor is unknown), and only the fields the capability returned or the paste requires. Consumers parse by block type. Where an invocation produces no block at all - the input anchored nothing and the consumer requested nothing - emit the notes alone, so the caller still sees what was asked. In `log_window`, `Correlation IDs present` reads `partial` when IDs are present on some lines or components and absent on others, and `Lines` carries `; truncated at tool cap` only when a cap was hit.

```
### error_event
Source: {mcp | user-paste | unavailable}
Tool: {sentry | rollbar | bugsnag | ...}
ID: {issue or event id}
Message: {short title}
Stack (top frame): {file:line - function}
Release: {tag}
Environment: {prod/staging/...}
First seen / Last seen: {ISO timestamps}
Event count: {N}
Affected users: {N}
Tags: {key=value, ...}

### metric_series
Source: {mcp | user-paste | unavailable}
Tool: {datadog | grafana | newrelic | ...}
Metric: {name}
Window: {start} to {end}
Filters: {scope}
Points: {ts=value, ...} OR {p50=.., p99=.., max=..}
Baseline delta: {+N% vs same window 7d earlier | no baseline}
Anomaly: {yes | no | unknown - no threshold | unknown - no baseline}

### log_window
Source: {mcp | user-paste | unavailable}
Tool: {datadog | cloudwatch | loki | splunk | ...}
Service: {name}
Window: {start} to {end}
Filters: {query string, percent-decoded}
Correlation IDs present: {yes | no | partial}
Lines: {count returned} of {total matched}{; truncated at tool cap}
Sample: {10-30 representative lines: timestamp level message}

### deploy_event
Source: {mcp | user-paste | unavailable}
Tool: {datadog | sentry | gh-releases | ci | ...}
Service: {name}
Window: {start} to {end}
Total in window: {N}
Timestamp: {ISO}
Commit: {sha}
Author: {name}
Environment: {prod/staging/...}

### monitor_state
Source: {mcp | user-paste | unavailable}
Tool: {datadog | ...}
ID: {monitor id}
Name: {monitor name}
Status: {OK | Alert | Warn | No Data | Skipped | Ignored | Unknown}
Threshold: {expression}
Current value: {value}
Last triggered: {ISO}

### trace
Source: {mcp | user-paste | unavailable}
Tool: {datadog-apm | honeycomb | jaeger | ...}
Trace ID: {id}
Duration: {ms}
Services traversed: {a -> b -> c}
Error spans: {N, with service:operation list}
Slowest span: {service:operation, {ms}}

{closing line, unavailable blocks only - exactly one:}
Needs: {every missing parameter, comma-separated}

Paste prompt ({no transport | call failed: <error>}): From {target}, paste: {the block's minimum paste fields}

{trailing notes after the last block, input order, one line each, never two for one URL:}
Question: {parameter still needed, vendor to confirm, or time zone of a pasted timestamp}

Note: {URL that produced no block, and why}
```

Omit fields the capability did not return. `Total in window` appears on the first `deploy_event` block when the cap bites and on the single block of a fetched empty list. Unavailable blocks keep only `Source`, `Tool`, input-parsed fields, and their closing `Paste prompt (...):` or `Needs:` line.

## Avoid

- Narrating the transport probe or listing every MCP namespace checked
- Re-requesting from the user a window or list that a working transport returned empty
