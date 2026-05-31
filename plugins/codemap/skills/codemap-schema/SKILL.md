---
name: codemap-schema
description: Canonical codemap graph schema - 12 node types, 14 edge types, 6 layer enum, JSON shapes. Loaded by every task-codemap-* workflow.
metadata:
  category: core
  tags: [codemap, schema, knowledge-graph, contract]
user-invocable: false
---

# Codemap Schema

Single source of truth for the `.codemap/graph.json` artifact. Every codemap workflow loads this skill before producing or consuming graph data.

## When to Use

- Producing graph nodes/edges in `task-codemap` (both full-build and sync modes).
- Reading graph data in `task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`.
- Validating an existing graph (via `codemap-validate`).

## Rules

1. **Schema is a contract.** Field names, enums, and ID format below are exact. Producers and consumers must conform.
2. **IDs are stable and globally unique.** Rebuild yields the same ID for the same logical entity (`file:<path>`, `function:<path>:<name>`, `class:<path>:<name>`).
3. **No node without a `summary`.** One sentence in English. If unknown, write `unknown - source not introspectable` rather than empty.
4. **No edge without both endpoints in the graph.** Dangling edges are dropped at merge.
5. **Closed enums.** `type`, `complexity`, `layer` use only the values listed below. Producers that need a new value must extend this skill, not invent locally.
6. **English only.** All `summary`, `tags`, `name` fields are English regardless of source language.

## Patterns

### Top-level shape

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-05-30T12:00:00Z",
  "gitCommitHash": "abc1234",
  "rootPath": ".",
  "stack": { "language": "Go", "framework": "Gin", "stackType": "backend" },
  "nodes": [ ... ],
  "edges": [ ... ],
  "layers": [ ... ]
}
```

### Node schema

```json
{
  "id": "function:src/auth/login.ts:authenticate",
  "type": "function",
  "name": "authenticate",
  "filePath": "src/auth/login.ts",
  "lineRange": [42, 87],
  "summary": "Validates credentials, issues a JWT, and writes an audit log entry.",
  "tags": ["auth", "jwt", "audit"],
  "complexity": "moderate",
  "layer": "service"
}
```

Field rules:

| Field | Required for | Notes |
| --- | --- | --- |
| `id` | all | Format `<type>:<path>[:<name>]`. Stable across rebuilds. |
| `type` | all | One of the 12 node types below. |
| `name` | all | Symbol name for code; file basename for files; short label for non-code. |
| `filePath` | all code nodes, config, document | Relative to repo root, forward slashes. Omit for abstract `concept`/`service`/`schema` nodes. |
| `lineRange` | `function`, `class`, `endpoint` | `[startLine, endLine]`, 1-based, inclusive. |
| `summary` | all | One sentence, English. |
| `tags` | all | 2-5 short kebab-case tags. |
| `complexity` | code nodes | `simple` / `moderate` / `complex`. Optional for non-code. |
| `layer` | assigned in step 6 of build | One of the 6 layer values. Omit until layer-assignment phase. |

### Node type enum (12)

| Type | Meaning | Example |
| --- | --- | --- |
| `file` | Source file | `src/auth/login.ts` |
| `function` | Free function or method | `authenticate()` |
| `class` | Class, struct, interface, trait | `UserRepository` |
| `module` | Logical grouping (package, namespace, folder cluster) | `auth/` |
| `concept` | Domain concept with no single source location | `JWT`, `Idempotency Key` |
| `config` | Configuration file or block | `application.yml`, `next.config.ts` |
| `document` | Documentation file | `README.md`, `ARCHITECTURE.md` |
| `service` | External or internal deployed service | `Stripe API`, `Notification Service` |
| `endpoint` | HTTP route, gRPC method, GraphQL resolver, CLI command | `POST /login` |
| `table` | Database table or collection | `users`, `audit_logs` |
| `schema` | Data contract (OpenAPI schema, JSON schema, protobuf message) | `UserDTO` |
| `resource` | Infra resource (queue, topic, bucket, cron) | `email-queue` |

### Edge schema

```json
{
  "source": "<sourceNodeId>",
  "target": "<targetNodeId>",
  "type": "calls",
  "weight": 0.7
}
```

Field rules:

| Field | Required | Notes |
| --- | --- | --- |
| `source`, `target` | yes | Must reference existing node IDs. |
| `type` | yes | One of the 14 edge types below. |
| `weight` | optional | 0.0-1.0. Defaults to 1.0. Use to encode relative strength. |

### Edge type enum (14)

| Type | Meaning |
| --- | --- |
| `imports` | Source imports/requires target |
| `exports` | Source declares target as its public surface |
| `calls` | Function source invokes function target |
| `extends` | Class source extends class/interface target |
| `implements` | Class source implements interface target |
| `uses` | Source uses target without a tighter category (DI, instantiation, type reference) |
| `depends_on` | Module/service-level dependency |
| `reads_from` | Source reads from data target (table, schema, config) |
| `writes_to` | Source writes to data target |
| `tested_by` | Source code/function is tested by target file/function |
| `documents` | Document target describes source |
| `configures` | Config source configures target |
| `routes_to` | Endpoint source routes to handler target |
| `belongs_to` | Node source is owned by container target (function -> file, file -> module) |

### Layer enum (6)

Default values. Stack-detect may override the human-readable label via the `codemap-layer-patterns` table, but the enum slugs remain stable.

| Layer | Meaning |
| --- | --- |
| `entry` | Bootstrap, CLI entry, server start, route registration |
| `api` | HTTP/gRPC/GraphQL surface - controllers, handlers, routers |
| `service` | Use-case, application services, business orchestration |
| `domain` | Pure domain model, entities, value objects, invariants |
| `data` | Repositories, ORM mappings, DAOs, raw queries, migrations |
| `infra` | External integrations, queue clients, observability, config loading |

A node may have at most one `layer`. Nodes with no clear layer (e.g., docs, generated code) omit the field.

### Guides shape (`.codemap/guides.json`)

```json
{
  "schemaVersion": 1,
  "guides": [
    {
      "name": "request-lifecycle",
      "title": "Request lifecycle: login -> JWT",
      "depth": "basic",
      "steps": [
        { "order": 1, "nodeId": "endpoint:POST /login", "narration": "..." },
        { "order": 2, "nodeId": "function:src/auth/login.ts:authenticate", "narration": "..." }
      ]
    }
  ]
}
```

Guides reference node IDs that must exist in `graph.json`. `depth` is `basic` (5-8 steps, headline-only) or `full` (10-20 steps, with narration on internals).

### Meta shape (`.codemap/meta.json`)

```json
{
  "schemaVersion": 1,
  "builtAt": "2026-05-30T12:00:00Z",
  "gitCommitHash": "abc1234",
  "analyzedFiles": 412,
  "version": "0.1.0"
}
```

### Config shape (`.codemap/config.json`)

```json
{
  "schemaVersion": 1,
  "autoUpdate": false,
  "scope": null
}
```

`scope: null` means full repo; otherwise a relative subdirectory path.

## Output Format

This skill produces no artifact directly. It defines the contract that consuming skills must follow when writing or reading the graph.

When a workflow references a node ID in its output, format it exactly as it appears in `graph.json` (e.g., ``function:src/auth/login.ts:authenticate``). Backtick-wrap IDs so users can grep them.

## Avoid

- Inventing node or edge types outside the enums. Extend the schema in this skill instead.
- Embedding source code in `summary`. Summaries describe intent in one sentence; the code is in the file.
- Generating `id` values that include line numbers - line numbers change every refactor and break stability.
- Producing edges to node IDs you have not also produced - merge will silently drop them and you will lose information.
- Adding free-form fields. If the field is not in the schema, do not write it.
