---
name: angular-nx-patterns
description: Nx monorepo for Angular - project tags + enforce-module-boundaries, library taxonomy, nx affected, generators, project.json, nx graph.
metadata:
  category: frontend
  tags: [angular, nx, monorepo, module-boundaries, library, generators, affected, workspace]
user-invocable: false
---

# Angular Nx Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Working in or onboarding an Angular Nx workspace (`nx.json`, `apps/`, `libs/`)
- Deciding where a new feature, UI component, data-access service, or util belongs
- Reviewing import boundaries, tag rules, or generator output
- Wiring CI to use `nx affected` instead of building the world

## Rules

- Every project (app or lib) declares `tags` in `project.json`. No tags = boundary rule fails open.
- `@nx/enforce-module-boundaries` is enabled in the root ESLint config; violations are blocking.
- Apps are leaves - they may import any allowed lib but nothing imports apps.
- Library type drives allowed dependencies: `feature` -> `feature`/`ui`/`data-access`/`util`; `ui` -> `ui`/`util`; `data-access` -> `data-access`/`util`; `util` -> `util`.
- Cross-feature imports go through a library's public `index.ts` only - never deep imports.
- New libs created with `nx g @nx/angular:library`, not by hand-rolling folders.

## Patterns

### Library Taxonomy

| Type          | Tag                    | Purpose                                            | May import           |
| ------------- | ---------------------- | -------------------------------------------------- | -------------------- |
| `feature`     | `type:feature`         | Smart components, route configs, business flows    | feature, ui, data-access, util |
| `ui`          | `type:ui`              | Dumb/presentational components, design system      | ui, util             |
| `data-access` | `type:data-access`     | HttpClient services, state services, NgRx stores   | data-access, util    |
| `util`        | `type:util`            | Pure functions, models, constants, validators      | util                 |

Scope tag (`scope:orders`, `scope:billing`, `scope:shared`) sits alongside type tag. `scope:shared` is importable by anything; named scopes import only their own scope + shared.

### `project.json` with Tags

```json
{
  "name": "orders-feature-cart",
  "tags": ["type:feature", "scope:orders"],
  "projectType": "library",
  "sourceRoot": "libs/orders/feature-cart/src",
  "targets": {
    "build": { "executor": "@nx/angular:ng-packagr-lite", "options": {...} },
    "test":  { "executor": "@nx/vite:test" },
    "lint":  { "executor": "@nx/eslint:lint" }
  }
}
```

### `enforce-module-boundaries` Rule

```json
// .eslintrc.json (root)
{
  "rules": {
    "@nx/enforce-module-boundaries": ["error", {
      "enforceBuildableLibDependency": true,
      "allow": [],
      "depConstraints": [
        { "sourceTag": "type:feature",     "onlyDependOnLibsWithTags": ["type:feature", "type:ui", "type:data-access", "type:util"] },
        { "sourceTag": "type:ui",          "onlyDependOnLibsWithTags": ["type:ui", "type:util"] },
        { "sourceTag": "type:data-access", "onlyDependOnLibsWithTags": ["type:data-access", "type:util"] },
        { "sourceTag": "type:util",        "onlyDependOnLibsWithTags": ["type:util"] },
        { "sourceTag": "scope:orders",     "onlyDependOnLibsWithTags": ["scope:orders", "scope:shared"] },
        { "sourceTag": "scope:billing",    "onlyDependOnLibsWithTags": ["scope:billing", "scope:shared"] },
        { "sourceTag": "scope:shared",     "onlyDependOnLibsWithTags": ["scope:shared"] }
      ]
    }]
  }
}
```

Violations: a `type:ui` lib importing a `type:data-access` lib, a `scope:orders` lib importing `scope:billing`, an app imported by a lib.

### Generators

```bash
# Library types map to generator flags
nx g @nx/angular:library libs/orders/feature-cart --tags=type:feature,scope:orders --standalone
nx g @nx/angular:library libs/orders/ui-line-item   --tags=type:ui,scope:orders --standalone
nx g @nx/angular:library libs/orders/data-access    --tags=type:data-access,scope:orders
nx g @nx/angular:library libs/shared/util-currency  --tags=type:util,scope:shared --buildable
```

Generators wire `project.json`, `tsconfig` paths, lint, test, and add the lib to `tsconfig.base.json` `paths`.

### Publishable vs Buildable

| Kind            | Use                                                          | Flag                  |
| --------------- | ------------------------------------------------------------ | --------------------- |
| Local (default) | Internal-only lib; imported via TS path alias                | (none)                |
| Buildable       | Compiles to its own `dist/`; enables incremental builds, can be cached separately, prerequisite for `enforceBuildableLibDependency` | `--buildable`         |
| Publishable     | Will be published to npm; produces an Angular Package Format bundle | `--publishable --importPath=@org/util-currency` |

A non-buildable lib cannot be imported by a buildable lib - `enforceBuildableLibDependency` blocks it.

### `nx affected` in CI

```bash
# CI compares against the merge base
nx affected -t lint test build --parallel=4
nx affected -t e2e --base=origin/main --head=HEAD
```

CI must set `NX_BASE` and `NX_HEAD` (or pass `--base`/`--head`); otherwise `affected` resolves to "everything" and you lose the speedup.

### `nx graph` for Orientation

```bash
nx graph                       # interactive web view of the dependency graph
nx graph --file=graph.json     # static export
nx graph --focus=orders-feature-cart   # subgraph around one project
```

Use to verify a boundary rule is doing what you think, or to find unintended fan-in to a "util" lib that should not have any.

### Executors vs Builders

Nx wraps Angular's `@angular-devkit/build-angular` builders into executors (`@nx/angular:application`, `@nx/angular:ng-packagr-lite`). Targets configured under `project.json` `targets` use the executor name. `angular.json` lives at the workspace root only as a compatibility shim - new projects use `project.json`.

### `project.json` vs `angular.json`

| File            | Owns                                          |
| --------------- | --------------------------------------------- |
| `nx.json`       | Workspace plugins, target defaults, named inputs, cache |
| `project.json`  | Per-project targets (build, test, lint, e2e)  |
| `angular.json`  | Legacy single-project workspaces only; in Nx, a thin pointer or absent |
| `tsconfig.base.json` | Path aliases for every lib (`@org/orders/feature-cart`) |

### Standalone-First in Nx

Angular 17+ standalone-first generators in Nx 17+: `nx g @nx/angular:library --standalone` produces a lib with no `NgModule`. Apps generated with `--standalone` use `provideRouter` + `bootstrapApplication` in `main.ts`.

## Output Format

```
## Nx Workspace Notes

**Nx version:** {detected}
**Workspace layout:** apps + libs | standalone app

### Library Placement

| Proposed lib | Type | Scope | Tags | Generator command |
| ------------ | ---- | ----- | ---- | ----------------- |

### Boundary Findings

| File | Violation | Rule |
| ---- | --------- | ---- |

### Recommendations

- {recommendation}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Untagged projects - boundary rules fail open
- Deep imports across libs (`@org/orders/feature-cart/src/lib/internal/...`) - import through `index.ts`
- Putting a `type:data-access` service inside a `type:ui` lib because "it was easier"
- One mega `type:feature` lib that contains the entire app - split by route or domain
- CI running `nx run-many` for everything when `nx affected` would build only what changed
- Editing `angular.json` in an Nx workspace - the source of truth is `project.json`
- Manually creating libs by copying folders - generators handle tsconfig paths, lint config, and tags atomically
