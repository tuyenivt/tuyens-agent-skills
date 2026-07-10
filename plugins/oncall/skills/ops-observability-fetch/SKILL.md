---
name: ops-observability-fetch
description: Fetch oncall evidence (issues, metrics, logs, traces, deploys, monitors) via observability MCPs - Sentry/Datadog/Honeycomb/Grafana/etc. Normalizes output; falls back to paste-mode.
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
| `fetch_issue`   | `error_event`   | issue ID or URL                     | `*.sentry.io/.../issues/{id}` (numeric or short-ID - the URL host carries the org); a bare short-ID like `PROJ-123` with no URL needs org+project slugs |
| `fetch_monitor` | `monitor_state` | monitor ID or URL                   | `app.datadoghq.*/monitors/{id}`                                                           |
| `fetch_trace`   | `trace`         | trace ID or URL                     | `app.datadoghq.*/apm/trace/{id}` (or vendor equivalent)                                   |
| `query_logs`    | `log_window`    | service, window, filters / corr. ID | `app.datadoghq.*/logs?query=...&from_ts=...&to_ts=...` (extract query + window)           |
| `query_metrics` | `metric_series` | metric name(s), window, filters     | none (metrics require a named metric)                                                     |
| `list_deploys`  | `deploy_event`  | service(s), window                  | none                                                                                      |

**Dashboard URLs** (`*/dashboard/*`) are never auto-fetched - they aggregate many tiles. Ask which metric/panel (as a trailing note, see Rules).

**Self-hosted variants** (`sentry.{company}.com`, `datadog.{company}.internal`) match on path, not host.

## Rules

- **Detect transport once per invocation, per vendor; do not narrate the probe.** Partial availability is normal: fetch via available transports, paste-prompt the rest.
- **URL recognition runs before asking for paste.** If input contains a recognized URL, auto-fetch. Parse IDs and windows out of URLs even when the transport is unavailable - they belong in the unavailable block.
- **Never invent values.** Unknown fields stay `unknown`; missing transport produces an unavailable block with a paste prompt.
- **Source tag uses roles, not vendor names:** `mcp` (any MCP transport), `user-paste`, `unavailable`. Name the vendor in the block's `Tool:` line when relevant. When the user later pastes the requested data, re-emit the block normalized with `Source: user-paste`.
- **Emit every block the consumer asked for** - as unavailable when it cannot be fetched, even when the input gives no anchor for it - **plus blocks the input directly anchors** - one block per capability/target, deduplicated across the two sets. Anchors: a recognized URL, or an explicit ID, metric name, or service+window in the request text. Nothing else - no speculative padding.
- **Block order:** consumer-requested blocks first in requested order, then input-anchored extras in input order.
- **Output starts with the first block.** No preamble, no transport narration. Notes and questions (dashboard panel question, skipped/unrecognized URLs) go after the last block, one line each.
- **Window required** for `query_metrics`, `query_logs`, `list_deploys`. Resolve relative windows ("last 48h") against the current time, convert epoch-ms URL parameters, and display ISO timestamps. Other capabilities carry their own context.
- **`list_deploys` emits one `deploy_event` block per deploy** (newest first, cap 5, note the total when capped). Unavailable mode emits a single `deploy_event` block whose paste prompt requests the list.

## Transport Detection

Probe MCP tool namespaces by prefix and verb (`mcp__sentry__*`, `mcp__datadog__*`, `mcp__honeycomb__*`, etc.). Match capabilities to verbs (`get_issue`, `query_metrics`, `search_logs`, `get_monitor`, `get_trace`, `list_deployments`). If two transports expose the same capability, prefer the one named in the project's `CLAUDE.md` under `## Observability`; otherwise ask once.

## Unavailable Blocks and Paste Prompts

When a capability has no transport, emit the block with `Source: unavailable`, any fields parseable from the input - URL or request text (ID, window, service, filters) - and a one-line `Paste prompt:` naming the tool and the block's minimum fields from this table - nothing more:

| Block           | Minimum paste fields                                                              |
| --------------- | --------------------------------------------------------------------------------- |
| `error_event`   | message, top stack frame, first_seen/last_seen, event count, release              |
| `metric_series` | metric name, window, points (`ts=value` series, or `p50/p99/max` summary - either) |
| `log_window`    | service, window, 10-30 representative lines with timestamps                       |
| `deploy_event`  | timestamp, service, commit sha for each deploy in the window                      |
| `monitor_state` | name, status, threshold, current value, last triggered                            |
| `trace`         | trace ID, services traversed, error span count, slowest span                      |

Derived fields (`Baseline delta`, `Anomaly`) are computed, never requested from the user.

Example:

```
### error_event
Source: unavailable
Tool: sentry
ID: 6630114
Paste prompt: From Sentry issue 6630114, paste: message, top stack frame, first seen / last seen, event count, release.
```

## Output

Each block carries `Source:`, `Tool:` (omit when the vendor is unknown), and only the fields the capability returned or the paste requires. Consumers parse by block type.

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
Source: ...
Tool: {datadog | grafana | newrelic | ...}
Metric: {name}
Window: {start} to {end}
Filters: {scope}
Points: {ts=value, ...} OR {p50=.., p99=.., max=..}
Baseline delta: {+N% vs prior 7d | no baseline}
Anomaly: {yes/no}

### log_window
Source: ...
Tool: {datadog | cloudwatch | loki | splunk | ...}
Service: {name}
Window: {start} to {end}
Filters: {query string}
Correlation IDs present: {yes | no | partial (present on some lines/components, absent on others)}
Lines: {count returned} of {total matched}{; "truncated at tool cap" when a cap was hit}
Sample: {10-30 representative lines: timestamp level message}

### deploy_event
Source: ...
Tool: {datadog | sentry-releases | gh-releases | ...}
Timestamp: {ISO}
Service: {name}
Commit: {sha}
Author: {name}
Environment: {prod/staging/...}

### monitor_state
Source: ...
Tool: {datadog | pagerduty | ...}
ID: {monitor id}
Name: {monitor name}
Status: {OK | Alert | Warn | No Data}
Threshold: {expression}
Current value: {value}
Last triggered: {ISO}

### trace
Source: ...
Tool: {datadog-apm | honeycomb | jaeger | ...}
Trace ID: {id}
Duration: {ms}
Services traversed: {a -> b -> c}
Error spans: {N, with service:operation list}
Slowest span: {service:operation, {ms}}
```

Omit fields the capability did not return. Unavailable blocks keep only `Source`, `Tool`, input-parsed fields, and the `Paste prompt:` line.

## Avoid

- Narrating the transport probe or listing every MCP namespace checked
- Emitting blocks the consumer did not request and the input does not anchor
- Auto-fetching dashboard URLs without a named metric
- Filling unknown fields with plausible-looking values
- Re-probing transport between capability calls in the same invocation
- Dropping a recognized URL silently - fetch it, mark it unavailable, or note the skip after the blocks
