---
name: ops-observability-fetch
description: Fetch oncall evidence from observability tools via MCP - issues, metrics, logs, traces, deploys, monitors. Sentry/Datadog/Honeycomb-aware; falls back to paste-mode.
metadata:
  category: ops
  tags: [oncall, observability, evidence, mcp, sentry, datadog]
user-invocable: false
---

# Ops Observability Fetch

Transport-agnostic evidence gathering for oncall workflows. Detects available MCP servers (Sentry, Datadog, Honeycomb, New Relic, Grafana), parses tool URLs from user input, and returns normalized evidence blocks. When no MCP server is available, prints the exact paste prompt the consuming workflow needs.

## When to Use

Called by oncall workflows that need live evidence: error events, metric series, log windows, deploy events, monitor states, traces. Not for code-review observability skills (those lint instrumentation, not data).

## Capabilities

| Capability       | Inputs                                        | Returns                                          |
| ---------------- | --------------------------------------------- | ------------------------------------------------ |
| `fetch_issue`    | issue ID or URL                               | `error_event` (message, stack, release, tags, first/last seen, count, affected users) |
| `query_metrics`  | metric name(s), time window, filters          | `metric_series` (points, baseline delta, anomaly flag) |
| `query_logs`     | service, time window, filters / correlation ID | `log_window` (lines with timestamp, level, message, correlation IDs present) |
| `list_deploys`   | service(s), time window                       | `deploy_event[]` (timestamp, commit, author, environment) |
| `fetch_monitor`  | monitor ID or URL                             | `monitor_state` (status, threshold, current value, last triggered) |
| `fetch_trace`    | trace ID or URL                               | `trace` (spans, durations, errors, services traversed) |

## Rules

- **Detect once per workflow invocation.** Cache the detection result; do not re-probe between steps.
- **URL recognition runs before asking for paste.** If the user input contains a recognizable URL, extract IDs and call the matching capability automatically.
- **Always normalize.** Consuming skills read the evidence blocks below, never raw MCP output. Strip vendor envelopes.
- **State the source on every block.** `Source: sentry-mcp | datadog-mcp | user-paste | unavailable`.
- **Never invent data.** If a capability is unavailable AND the user did not paste, return `unavailable` with the exact paste prompt - do not synthesize plausible values.
- **Time window is required for all queries except `fetch_issue` / `fetch_monitor` / `fetch_trace`** (which carry their own context).

## Patterns

### Transport Detection

Probe in this order, stop at first hit per capability:

| Capability      | Sentry MCP tools (typical)              | Datadog MCP tools (typical)                       | Others                                |
| --------------- | --------------------------------------- | ------------------------------------------------- | ------------------------------------- |
| `fetch_issue`   | `mcp__sentry__get_issue`, `get_event`   | -                                                 | Honeycomb `get_trace_by_id`           |
| `query_metrics` | -                                       | `mcp__datadog__query_metrics`, `get_metric`       | Grafana, New Relic NRQL               |
| `query_logs`    | -                                       | `mcp__datadog__search_logs`, `get_log_events`     | Loki, CloudWatch                      |
| `list_deploys`  | `get_releases`                          | `mcp__datadog__list_deployments`, deploy events   | GitHub Releases MCP                   |
| `fetch_monitor` | -                                       | `mcp__datadog__get_monitor`                       | PagerDuty MCP                         |
| `fetch_trace`   | -                                       | `mcp__datadog__get_trace`, APM                    | Honeycomb, Jaeger                     |

Tool names vary by MCP server version. Match by **prefix and verb**, not exact name. If multiple servers expose the same capability (e.g., logs in both Datadog and Loki), prefer the one named in project `CLAUDE.md` under `## Observability`; otherwise ask once.

### URL Recognition

| Pattern                                                              | Capability + extraction                                    |
| -------------------------------------------------------------------- | ---------------------------------------------------------- |
| `sentry.io/organizations/{org}/issues/{id}` (or `{org}.sentry.io/...`) | `fetch_issue(id)`                                          |
| `app.datadoghq.{com,eu}/monitors/{id}`                               | `fetch_monitor(id)`                                        |
| `app.datadoghq.{com,eu}/logs?query=...&from_ts=...&to_ts=...`        | `query_logs(filters, window)` - parse query + timestamps   |
| `app.datadoghq.{com,eu}/apm/trace/{traceId}`                         | `fetch_trace(traceId)`                                     |
| `app.datadoghq.{com,eu}/dashboard/...` (and other dashboards)        | Do not auto-fetch; ask user which metric to query          |

Self-hosted variants (`sentry.{company}.com`, `datadog.{company}.internal`) follow the same path patterns - match on path, not host.

### Fallback to Paste-Mode

When MCP is unavailable and no URL was provided, emit the exact prompt the user should paste back, naming the tool and the minimum fields. Example:

```
Source: unavailable
Need: error event for the failing request.
Paste from Sentry (or your error tracker):
  - issue/event ID or URL
  - first stack frame
  - release tag, environment
  - first_seen / last_seen
```

Do not list every optional field - keep it to the diagnostic minimum.

## Output

Each block carries `Source:` and only the fields the capability returned. Consumers parse by block type, not field order.

```
### error_event
Source: {sentry-mcp | user-paste | unavailable}
ID: {issue or event id}
Message: {short title}
Stack (top frame): {file:line - function}
Release: {tag or "unknown"}
Environment: {prod/staging/...}
First seen: {ISO timestamp}
Last seen: {ISO timestamp}
Event count: {N}
Affected users: {N or "unknown"}
Tags: {key=value, ...}

### metric_series
Source: {datadog-mcp | user-paste | unavailable}
Metric: {name}
Window: {start} to {end}
Filters: {scope, e.g., service:checkout env:prod}
Points: {timestamp=value, ...} OR {summary: p50=.., p99=.., max=..}
Baseline delta: {+N% vs prior 7d, or "no baseline"}
Anomaly: {yes/no - threshold crossed}

### log_window
Source: {datadog-mcp | user-paste | unavailable}
Service: {name}
Window: {start} to {end}
Filters: {query string}
Correlation IDs present: {yes/no/partial}
Lines: {count returned, total matched}
Sample:
  {timestamp} {level} {message}
  ...

### deploy_event
Source: {datadog-mcp | sentry-mcp | user-paste | unavailable}
Timestamp: {ISO}
Service: {name}
Commit: {sha}
Author: {name or "unknown"}
Environment: {prod/staging/...}

### monitor_state
Source: {datadog-mcp | user-paste | unavailable}
ID: {monitor id}
Name: {monitor name}
Status: {OK | Alert | Warn | No Data}
Threshold: {expression}
Current value: {value}
Last triggered: {ISO or "never in window"}

### trace
Source: {datadog-mcp | honeycomb-mcp | user-paste | unavailable}
Trace ID: {id}
Duration: {ms}
Services traversed: {a -> b -> c}
Error spans: {N, with service:operation list}
Slowest span: {service:operation, {ms}}
```

## Avoid

- Re-probing transport for every capability call - cache once per workflow
- Auto-fetching from dashboard URLs without confirming which metric the user means
- Mixing vendor field names into the output - normalize or omit
- Returning a half-filled block instead of `Source: unavailable` with a paste prompt
- Calling this from `task-*-review-observability` skills - those lint instrumentation code, not live data
