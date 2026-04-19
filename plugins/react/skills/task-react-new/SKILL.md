---
name: task-react-new
description: End-to-end React feature implementation workflow - component tree, state management, API integration, routing, styling, accessibility, and tests for React 19+ / Next.js / Vite projects.
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, feature, implementation, workflow, components, hooks, testing]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Implement React Feature

## When to Use

- Implementing a new React feature end-to-end (components, state, data fetching, routing, tests)
- Scaffolding a complete page or feature module with production-ready patterns
- Adding a new user-facing flow with API integration and form handling
- Any daily frontend coding task that requires coordinated generation of multiple React layers

**Not for**: Single-component changes, bug fixes (use `task-react-debug`), or refactoring without new functionality.

**Edge cases**:

- **Partial input**: If the user provides only a feature name without details, ask for components needed, data requirements, user interactions, and routing before proceeding to design.
- **No API**: If the feature is purely UI (e.g., static page, settings toggle), skip data fetching and API integration steps; generate only components, state, styling, and tests.
- **Existing components**: If the user references components that already exist, read them and extend or compose with them rather than creating duplicates.
- **Vite project**: If stack-detect identifies Vite instead of Next.js, skip Server Components and Server Actions; use client-side routing (React Router) and client-side data fetching patterns.
- **No forms**: If the feature has no form inputs, skip the form handling step entirely.

## Rules

- TypeScript strict mode - no `any` types, no type assertions without justification
- Function components only - no class components
- Named exports for components; default exports only for route pages (Next.js convention)
- Server Components by default in Next.js App Router - add `"use client"` only when the component needs hooks, event handlers, or browser APIs
- Custom hooks must start with `use` and encapsulate a single concern
- Props must be typed with interfaces (not inline types) for components with more than 2 props
- Colocate tests with components (`ComponentName.test.tsx` next to `ComponentName.tsx`)
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run typecheck and lint after all files are generated

## Workflow

STEP 1 - DETECT: Use skill: `stack-detect` to determine framework (Next.js App Router vs Vite + React Router), TypeScript config, styling approach, state management library, and test framework.

STEP 2 - GATHER: Requirements - feature name, user stories, components needed, data sources (API endpoints), user interactions, routing needs, form inputs, accessibility requirements.

STEP 3 - DESIGN: Use skill: `react-component-patterns` + `react-routing-patterns`. Propose component tree with responsibility breakdown (Server vs Client Components if Next.js), file structure, and routing. Present for user approval before generating code.

STEP 4 - STATE: Use skill: `react-state-patterns` + `frontend-state-management`. Identify state categories (local, shared, global, server, URL, form) and assign ownership to components or stores.

STEP 5 - DATA: Use skill: `react-data-fetching` + `frontend-api-integration`. Define data fetching strategy - query keys, cache invalidation, loading/error states, optimistic updates if needed.

STEP 6 - COMPONENTS: Use skill: `react-hooks-patterns` + `react-styling-patterns`. If Next.js: Use skill: `react-nextjs-patterns`. Generate components with proper hook usage, styling, and Server/Client Component boundaries.

STEP 7 - FORMS: Use skill: `frontend-form-handling` (if feature has forms). Implement form validation, error display, submission handling, and dirty tracking.

STEP 8 - A11Y: Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA compliance - semantic HTML, keyboard navigation, ARIA attributes, focus management.

STEP 9 - TESTS: Use skill: `react-testing-patterns` + `frontend-testing-patterns`. Generate component tests (React Testing Library), hook tests, integration tests (MSW), and identify critical paths for e2e.

STEP 10 - VALIDATE: Run `npx tsc --noEmit` + lint + test. Present file list, component tree, and test count.

## Self-Check

- [ ] Stack detected and framework identified (STEP 1)
- [ ] Requirements gathered - components, data sources, interactions, routing documented (STEP 2)
- [ ] Component tree designed with Server/Client boundaries and approved by user (STEP 3)
- [ ] State management categorized and assigned - no duplicated state, server state separated (STEP 4)
- [ ] Data fetching uses TanStack Query or framework-appropriate library with loading/error/empty states (STEP 5)
- [ ] Components use proper hooks, styling approach, and TypeScript types (STEP 6)
- [ ] Forms have validation, error display, submission protection, and dirty tracking if applicable (STEP 7)
- [ ] Accessibility audit passed - semantic HTML, keyboard accessible, ARIA attributes correct (STEP 8)
- [ ] Tests cover components, hooks, integration with MSW, and critical user flows (STEP 9)
- [ ] TypeScript compiles with no errors; lint passes; tests pass (STEP 10)

## Output Format

Present a checklist of generated files:

```markdown
## Generated Files

### Components

- [ ] `{path}/{ComponentName}.tsx`
- [ ] `{path}/{ComponentName}.test.tsx`

### Hooks (if custom hooks created)

- [ ] `{path}/use{HookName}.ts`
- [ ] `{path}/use{HookName}.test.ts`

### Types

- [ ] `{path}/types.ts`

### API / Data

- [ ] `{path}/{queryName}.ts` (query functions)

## Component Tree

{ComponentName} (Server | Client)
├── {ChildA} (Server | Client)
│ └── {ChildB} (Client)
└── {ChildC} (Client)

## State Map

| State        | Category   | Owner       | Mechanism                             |
| ------------ | ---------- | ----------- | ------------------------------------- |
| {state name} | {category} | {component} | {useState / Zustand / TanStack Query} |

## Tests

- Component tests: {count}
- Hook tests: {count}
- Integration tests: {count}
- E2E candidates: {list of critical paths}
```

## Avoid

- Using `any` type or suppressing TypeScript errors
- Class components or legacy patterns (componentDidMount, etc.)
- Putting `"use client"` on every component in a Next.js project
- Fetching data in useEffect without a data-fetching library
- Storing server state in Zustand/Redux (use TanStack Query)
- Inline styles instead of the project's styling approach
- Skipping loading, error, or empty states on data-fetching components
- Tests that assert implementation details (internal state, method calls)
- Generating code before the design is approved
