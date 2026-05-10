---
name: task-design-diagram
description: "Generate Mermaid or PlantUML architecture diagrams (C4 context/container/component, sequence, data flow, deployment) from a design doc."
metadata:
  category: architecture
  tags: [architecture, diagram, c4, mermaid, plantuml, visualization, documentation]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Architecture Diagram Generator

## Purpose

Produce commit-ready Mermaid or PlantUML diagram code from architecture descriptions or design docs - C4 (Context/Container/Component), sequence, data flow, or deployment. Outputs diagram code only; does not modify files unless asked.

## When to Use

- After `task-design-architecture` to add visual documentation
- When a design doc, ADR, or onboarding material needs a diagram
- When preparing architecture review materials

## Inputs

| Input           | Required | Description                                                                                        |
| --------------- | -------- | -------------------------------------------------------------------------------------------------- |
| Source material | Yes      | Design description, design doc path, ADR, or `task-design-architecture` output                     |
| Diagram type    | No       | C4-context, C4-container, C4-component, sequence, data-flow, deployment - see Type Selection below |
| Format          | No       | `mermaid` (default) or `plantuml`                                                                  |
| Focus scope     | No       | Specific system, service, or flow to diagram if source covers multiple                             |
| Output target   | No       | Inline markdown block (default) or standalone file path                                            |

## Type Selection

If the user has not specified a diagram type, ask:

> What do you need the diagram for?
>
> - **C4 Context** - show the system and who/what interacts with it (users, external systems)
> - **C4 Container** - show the major deployable units inside the system (services, databases, queues)
> - **C4 Component** - show modules or components inside one container
> - **Sequence** - show the order of interactions for a specific flow (request, event, job)
> - **Data flow** - show how data moves through the system including async and batch paths
> - **Deployment** - show the infrastructure topology (hosts, regions, networking)

If the source material makes the appropriate type obvious (e.g., a sequence-described flow clearly wants a sequence diagram), skip the question and proceed.

## Workflow

### Step 0 - Detect Stack and Format Preference

Use skill: `stack-detect`

Check if the consuming project's documentation tooling has a format preference (Mermaid for GitHub/GitLab, PlantUML for Confluence/enterprise). Use this to inform Step 2.

### Step 1 - Read Source Material

Read the provided design document, ADR, or description. Extract:

- **Systems and actors** - who and what interacts with this system
- **Components and containers** - the deployable or logical units
- **Flows** - request paths, event flows, batch jobs
- **Data stores** - databases, caches, queues, external storage
- **External dependencies** - third-party services, APIs, identity providers

If source material is a file path, read it. If it references `task-design-architecture` output, parse the component table, boundary contracts, and communication model sections.

### Step 1.5 - Resolve Input Gaps

Before generating, verify the source material is sufficient:

- **Missing component names**: If the source uses generic labels ("4 microservices") without naming them, ask the user for names before generating. Do not invent names.
- **Ambiguous diagram type**: If diagram type remains unclear after the Type Selection prompt and the user defers, default to C4 Container with a note explaining the choice.
- **Large scope**: If the source describes more than 12 elements at one level, offer to split into multiple diagrams or suggest a higher abstraction level.

### Step 2 - Select Format

Default: `mermaid` (embeds in GitHub, GitLab, and most markdown renderers without tooling).

Use `plantuml` when:

- User requests it explicitly
- The diagram type has richer PlantUML support (C4 with icons, deployment with network topology)

### Step 3 - Generate Diagram

#### C4 Context Diagram (Mermaid)

```
C4Context
  title System Context - {System Name}

  Person(alias, "Label", "Description")
  System(alias, "Label", "Description")
  System_Ext(alias, "Label", "Description")
  SystemDb_Ext(alias, "Label", "Description")

  Rel(from, to, "Label", "Protocol")
  Rel_Back(from, to, "Label")
```

**Rules**: target system + actors + direct external systems only. No internal components. Every relationship has a direction and label.

#### C4 Container Diagram (Mermaid)

```
C4Container
  title Container Diagram - {System Name}

  Person(alias, "Label", "Description")

  System_Boundary(sys, "System Name") {
    Container(alias, "Label", "Technology", "Description")
    ContainerDb(alias, "Label", "Technology", "Description")
    ContainerQueue(alias, "Label", "Technology", "Description")
  }

  System_Ext(alias, "Label", "Description")

  Rel(from, to, "Label", "Protocol/Technology")
```

**Rules**: major deployable units only with technology stack labels. No internal module structure.

#### C4 Component Diagram (Mermaid)

```
C4Component
  title Component Diagram - {Container Name}

  Container_Boundary(c, "Container Name") {
    Component(alias, "Label", "Technology", "Description")
  }

  ContainerDb(alias, "DB Name", "Technology", "Description")
  Container_Ext(alias, "External Container", "Technology", "Description")

  Rel(from, to, "Label")
```

**Rules**: scope to one container; components map to bounded responsibilities, not files or classes.

#### Sequence Diagram (Mermaid)

```
sequenceDiagram
  autonumber
  actor User
  participant API as API Gateway
  participant Service as OrderService
  participant DB as PostgreSQL
  participant Queue as Kafka

  User->>API: POST /orders (request body)
  API->>Service: createOrder(command)
  Service->>DB: INSERT order (transaction)
  DB-->>Service: order_id
  Service--)Queue: OrderCreated event (async)
  Service-->>API: 201 Created + order_id
  API-->>User: 201 Created
```

**Rules**: `autonumber`; `->>` request, `-->>` response, `--)` async fire-and-forget. Use `alt`/`else` only for architecturally significant error paths.

#### Data Flow Diagram (Mermaid flowchart)

```
flowchart LR
  subgraph Ingestion
    A[API Gateway] --> B[OrderService]
  end

  subgraph Processing
    B --> C[(PostgreSQL)]
    B --> D([Kafka Topic: orders])
    D --> E[FulfillmentService]
    D --> F[NotificationService]
  end

  subgraph Storage
    E --> G[(FulfillmentDB)]
    F --> H[(NotificationDB)]
  end
```

**Rules**: `LR` for pipelines, `TD` for hierarchies. `[(db)]`, `([queue])`, `[service]`. Async paths use dashed `-->|async|`.

#### Deployment Diagram (Mermaid)

```
flowchart TD
  subgraph Cloud["AWS us-east-1"]
    subgraph VPC["VPC 10.0.0.0/16"]
      subgraph PublicSubnet["Public Subnet"]
        ALB[Application Load Balancer]
      end
      subgraph PrivateSubnet["Private Subnet"]
        ECS[ECS Cluster\nOrderService x3]
        RDS[(RDS PostgreSQL\nMulti-AZ)]
        MSK([MSK Kafka\n3 brokers])
      end
    end
    CF[CloudFront CDN]
  end

  Client([Client]) --> CF
  CF --> ALB
  ALB --> ECS
  ECS --> RDS
  ECS --> MSK
```

**Rules**: nested subgraphs for provider > region > VPC > subnet. Show instance counts in labels. External traffic entry at the top.

### Step 4 - Output

Produce the diagram code wrapped in the appropriate fenced block:

For inline markdown (default):

````markdown
```mermaid
{diagram code}
```
````

For standalone file output, write to the path specified and state the file path in the response.

After the diagram block, produce a brief **Diagram Notes** section:

```markdown
### Diagram Notes

- **Scope**: {what this diagram shows and what it deliberately omits}
- **Assumptions**: {anything inferred from source material that was not explicit}
- **Next level**: {which diagram type would show more detail - e.g., "See C4 Container for internal services"}
```

**Example Diagram Notes:**

- **Scope**: Shows the 4 deployable containers within the e-commerce system boundary; deliberately omits internal module structure and infrastructure details
- **Assumptions**: Product and Search services inferred as separate containers based on the source description mentioning "search endpoint"; not confirmed
- **Next level**: C4 Component diagram for OrderService would show internal modules (validation, pricing, fulfillment coordination)

## Rules

- Every element traceable to source; never invent components to "complete" the diagram
- Stay at one abstraction level (no Context/Container mixing)
- State assumptions in Diagram Notes, not silently in the diagram
- Mermaid/PlantUML syntax must render unmodified in standard tools

## Self-Check

- [ ] Every actor/system/container/relationship traces to source
- [ ] Single abstraction level; correct C4 element types
- [ ] Diagram Notes states scope and assumptions
- [ ] Syntax valid (no unclosed blocks, no invalid aliases)
- [ ] Async paths visually distinct from sync (sequence, data flow)

## Avoid

- Showing implementation details (classes, methods, tables) in Context or Container diagrams
- Generic labels ("Service A", "Database 1") when source names them
- Diagrams that need proprietary tooling to render
