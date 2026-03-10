---
name: task-design-diagram
description: Generate architecture diagrams (C4, sequence, data flow, deployment) as Mermaid or PlantUML code from a design description, design doc, or task-design-architecture output.
metadata:
  category: architecture
  tags: [architecture, diagram, c4, mermaid, plantuml, visualization, documentation]
  type: workflow
user-invocable: true
---

# Architecture Diagram Generator

## Purpose

Produce commit-ready diagram code from architecture descriptions or existing design documents:

- **C4 model hierarchy** - Context, Container, Component levels with correct C4 semantics
- **Sequence diagrams** - key flows across system boundaries
- **Data flow diagrams** - how data moves through the system, including async paths
- **Deployment diagrams** - infrastructure topology and runtime dependencies
- **Docs-repo native** - outputs embeddable Mermaid blocks or standalone PlantUML files; no code required

This skill produces diagram code only. It does not modify existing files unless asked.

## When to Use

- After running `task-design-architecture` to produce visual documentation of the design
- When an existing design doc or ADR needs a diagram to clarify structure
- When onboarding team members who need a visual system map
- When preparing architecture review materials for leadership or cross-team communication
- When updating diagrams after a system change

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

### Step 1 - Read Source Material

Read the provided design document, ADR, or description. Extract:

- **Systems and actors** - who and what interacts with this system
- **Components and containers** - the deployable or logical units
- **Flows** - request paths, event flows, batch jobs
- **Data stores** - databases, caches, queues, external storage
- **External dependencies** - third-party services, APIs, identity providers

If source material is a file path, read it. If it references `task-design-architecture` output, parse the component table, boundary contracts, and communication model sections.

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

**Rules for C4 Context:**

- Show only: the target system, its users/actors, and direct external systems
- Do not show internal components - that is C4 Container level
- Every relationship must have a direction and a brief label

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

**Rules for C4 Container:**

- Show major deployable units (services, databases, queues, frontends)
- Include the technology stack for each container
- Do not show internal module structure - that is C4 Component level

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

**Rules for C4 Component:**

- Scope to a single container; show its internal modules/components
- Each component should map to a bounded responsibility (not a file or class)

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

**Rules for Sequence:**

- Use `autonumber` for numbered steps
- Use `-->>` for responses, `->>` for requests
- Use `--)` for async messages (fire-and-forget)
- Include `activate`/`deactivate` for long-running operations if it adds clarity
- Show error paths with `alt`/`else` blocks when they are architecturally significant

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

**Rules for Data Flow:**

- Use `LR` (left-to-right) for pipeline flows, `TD` (top-down) for hierarchical flows
- Use `[(name)]` for databases, `([name])` for queues/topics, `[name]` for services
- Group related components with `subgraph`
- Show async paths distinctly with dashed lines: `-->|async|`

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

**Rules for Deployment:**

- Use nested subgraphs for cloud provider > region > VPC > subnet hierarchy
- Show replication/redundancy with instance counts in labels
- Show external traffic entry points at the top

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

## Rules

- Never invent components not present in or strongly implied by the source material
- Every element in the diagram must be traceable to the source
- State assumptions explicitly in Diagram Notes, not silently in the diagram
- Keep diagrams at one level of abstraction - do not mix C4 Context and Container in the same diagram
- Mermaid syntax must be valid and render without modification in standard tools
- Omit legend blocks unless the diagram uses non-standard notation

## Self-Check

- [ ] Every actor, system, container, and relationship is traceable to the source material
- [ ] Diagram stays at a single abstraction level
- [ ] Diagram Notes states scope and assumptions
- [ ] Mermaid/PlantUML syntax is valid (no unclosed blocks, no invalid aliases)
- [ ] Async paths are visually distinct from sync paths
- [ ] C4 diagrams use correct C4 element types (Person, System, Container, Component)

## Avoid

- Mixing C4 levels in one diagram
- Adding systems or components not present in the source to make the diagram look complete
- Showing implementation details (classes, methods, DB tables) in Context or Container diagrams
- Using generic labels ("Service A", "Database 1") when names are available in the source
- Producing diagrams that require proprietary tooling to render
