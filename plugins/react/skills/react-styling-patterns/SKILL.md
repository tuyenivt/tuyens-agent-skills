---
name: react-styling-patterns
description: "React styling: Tailwind, CSS Modules, styled-components, cva variants, design tokens, dark mode, responsive, RSC compatibility."
metadata:
  category: frontend
  tags: [react, styling, tailwind, css-modules, styled-components, responsive, dark-mode]
user-invocable: false
---

# React Styling Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a styling approach for a React/Next.js project
- Implementing responsive design, dark mode, or shared design tokens
- Reviewing component styling for consistency, RSC compatibility, accessibility
- Integrating headless component libraries (Radix, Headless UI, shadcn/ui)

## Rules

- Pick one primary approach per project. Mixing paradigms (Tailwind + styled-components in the same tree) is a code smell unless boundaries are documented.
- Conditional/variant classes go through `cn`/`clsx` + `cva`. No string concatenation, no ternary chains in JSX.
- Mobile-first responsive: base styles target mobile, breakpoint prefixes (`md:`, `lg:`) add larger-screen rules.
- Dark mode toggles a single root signal (Tailwind `dark:` class or CSS-vars on `.dark`). Components never branch on a theme prop.
- Design tokens live in one source: Tailwind `theme.extend` or CSS custom properties. Hex literals in components are a violation.
- Runtime CSS-in-JS (styled-components, emotion) requires `"use client"` and an SSR registry in Next.js App Router. Default to zero-runtime (Tailwind, CSS Modules, Vanilla Extract) for RSC.
- Inline `style={}` only for values JS must compute (drag positions, measured sizes). Static styling uses classes.
- Preserve focus rings and contrast. `outline-none` without a replacement `focus-visible:ring-*` is a defect.

## Patterns

### Approach Selection

| Approach          | Runtime | RSC-safe | Best fit                                     |
| ----------------- | ------- | -------- | -------------------------------------------- |
| Tailwind CSS      | none    | yes      | New projects, design systems, RSC-heavy apps |
| CSS Modules       | none    | yes      | Scoped styles, minimal tooling               |
| Vanilla Extract   | none    | yes      | Type-safe tokens, zero-runtime CSS-in-TS     |
| styled-components | runtime | no       | Legacy SPAs with heavy dynamic theming       |

### `cn` + `cva` for Variants

```tsx
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { cva, type VariantProps } from "class-variance-authority";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

const button = cva(
  "inline-flex items-center rounded-lg font-medium transition-colors focus-visible:ring-2",
  {
    variants: {
      variant: {
        primary: "bg-blue-600 text-white hover:bg-blue-700",
        secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200",
        destructive: "bg-red-600 text-white hover:bg-red-700",
      },
      size: { sm: "h-8 px-3 text-sm", md: "h-10 px-4", lg: "h-12 px-6" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof button>;

export function Button({ variant, size, className, ...props }: ButtonProps) {
  return <button className={cn(button({ variant, size }), className)} {...props} />;
}
```

`twMerge` resolves Tailwind conflicts so parent `className` can override; without it `px-4 px-6` keeps both.

### Responsive (mobile-first)

```tsx
// Bad - desktop styles as base, mobile overrides
<div className="flex-row gap-6 max-md:flex-col max-md:gap-4" />

// Good - mobile base, breakpoints add larger-screen rules
<div className="flex flex-col gap-4 md:flex-row md:gap-6 lg:gap-8" />
```

### Dark Mode

```tsx
// tailwind.config.ts
export default { darkMode: "class" };

// Component - no theme prop, no branching
function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-white text-gray-900 dark:bg-gray-900 dark:text-gray-100">
      {children}
    </div>
  );
}
```

Toggle by setting `class="dark"` on `<html>` once (e.g., `next-themes`). Avoid `useState`-driven theme branches per component.

### Design Tokens

Two valid sources -- pick one:

```ts
// Option A: Tailwind theme (preferred when Tailwind is the styling layer)
// tailwind.config.ts
theme: { extend: { colors: { brand: { 500: "#2563eb", 600: "#1d4ed8" } } } }
// Use: className="bg-brand-500"
```

```css
/* Option B: CSS custom properties (preferred when sharing tokens across apps,
   or when CSS Modules / styled-components is the styling layer) */
:root        { --color-brand: #2563eb; --color-surface: #ffffff; }
.dark        { --color-brand: #3b82f6; --color-surface: #111827; }
```

If both are needed (shared tokens across a Tailwind app and a non-Tailwind marketing site), define CSS vars as the source of truth and reference them from `tailwind.config.ts` (`colors: { brand: "var(--color-brand)" }`).

### CSS Modules

```tsx
// Button.module.css
.button { border-radius: var(--radius-md); padding: 0.5rem 1rem; }
.primary { background: var(--color-brand); color: #fff; }

// Button.tsx
import styles from "./Button.module.css";
import { cn } from "@/lib/cn";

export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return <button className={cn(styles.button, styles[variant], className)} {...props} />;
}
```

### styled-components in Next.js App Router

```tsx
// Bad - styled-components in an RSC; ships runtime to clients silently or FOUC.
// app/page.tsx (no "use client")
const Box = styled.div`color: red;`;

// Good - mark client + register on the server for SSR.
"use client";
import styled from "styled-components";
const Box = styled.div`color: red;`;
// Plus: app/registry.tsx implementing useServerInsertedHTML + ServerStyleSheet.
```

For new App Router code, prefer Tailwind or CSS Modules over CSS-in-JS.

## Output Format

```
## Styling Architecture

Stack: {detected framework}
Primary approach: {Tailwind | CSS Modules | Vanilla Extract | styled-components}
Component library: {shadcn/ui | Radix | Headless UI | None}
Token source: {Tailwind config | CSS variables | hybrid}
Dark mode: {class strategy | media query | none}

## Component Variants

| Component | Variants                        | Mechanism |
| --------- | ------------------------------- | --------- |
| Button    | primary, secondary, destructive | cva + cn  |

## Findings

- [Severity: High | Medium | Low] <one-line issue>
  Location: <file>:<line>
  Category: {Approach-Mix | Variant-Concat | Responsive-Direction | Dark-Mode-Branch | Token-Literal | Inline-Style | RSC-Incompat | A11y-Focus | Important-Override}
  Fix: <minimal correction>

## Recommendations

- <change with rationale>
```

## Avoid

- Inline `style={}` for static values, or hex literals where a token exists
- String concatenation / ternary chains for class composition (use `cn` + `cva`)
- Desktop-first responsive (`max-md:` as the primary direction)
- Per-component theme props or `useState`-driven dark mode branches
- styled-components or emotion in Server Components without `"use client"` + SSR registry
- `!important` to win specificity battles (fix the cascade or the variant order)
- `outline-none` without a `focus-visible` replacement
- Reimplementing primitives the headless library already ships (Dialog, Menu, Tooltip)
