---
name: react-styling-patterns
description: React styling patterns - Tailwind CSS (primary), CSS Modules, styled-components, responsive design, design tokens, dark mode, and component library integration.
metadata:
  category: frontend
  tags: [react, styling, tailwind, css-modules, styled-components, responsive, dark-mode]
user-invocable: false
---

# React Styling Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a styling approach for a React project
- Implementing responsive design, dark mode, or design tokens
- Reviewing styling patterns for consistency and maintainability
- Integrating component libraries (Radix, Headless UI, shadcn/ui)

## Rules

- Use the project's established styling approach - do not mix paradigms without good reason
- Tailwind CSS is the primary recommendation for new projects
- Responsive design must be mobile-first (min-width breakpoints)
- Dark mode must use CSS custom properties or Tailwind's `dark:` variant - not conditional class logic in every component
- Component variants must use a systematic approach (cva, cn utility) - not string concatenation
- Never use inline styles for anything except truly dynamic values (computed positions, animations)
- Styling must not break accessibility (sufficient contrast, visible focus indicators)

## Patterns

### Styling Approach Selection

| Approach          | When to Use                                     | Server Components | Tree Shaking |
| ----------------- | ----------------------------------------------- | ----------------- | ------------ |
| Tailwind CSS      | New projects, rapid development, design systems | Yes               | Yes          |
| CSS Modules       | Scoped styles, minimal tooling, team preference | Yes               | Yes          |
| styled-components | Existing codebase, dynamic styling              | No (Client only)  | Partial      |
| Vanilla Extract   | Type-safe CSS, zero-runtime                     | Yes               | Yes          |

### Tailwind CSS Patterns

**Class name management with cn utility:**

```tsx
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Usage: merge base + conditional + override classes
function Button({ variant, className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "rounded-lg px-4 py-2 font-medium transition-colors",
        variant === "primary" && "bg-blue-600 text-white hover:bg-blue-700",
        variant === "secondary" &&
          "bg-gray-100 text-gray-900 hover:bg-gray-200",
        className, // allow overrides from parent
      )}
      {...props}
    />
  );
}
```

**Component variants with cva:**

```tsx
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2",
  {
    variants: {
      variant: {
        primary: "bg-blue-600 text-white hover:bg-blue-700",
        secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200",
        destructive: "bg-red-600 text-white hover:bg-red-700",
        ghost: "hover:bg-gray-100",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

function Button({ variant, size, className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
```

### Responsive Design

Mobile-first with Tailwind breakpoints:

```tsx
// Mobile-first: base styles are mobile, breakpoints add larger screen styles
<div
  className="
  flex flex-col gap-4          // mobile: stack vertically
  md:flex-row md:gap-6         // tablet: side by side
  lg:gap-8                     // desktop: more spacing
"
>
  <aside
    className="
    w-full                     // mobile: full width
    md:w-64 md:shrink-0        // tablet+: fixed sidebar
  "
  >
    <Sidebar />
  </aside>
  <main className="flex-1 min-w-0">{children}</main>
</div>
```

### Dark Mode

**Tailwind dark mode (class strategy):**

```tsx
// tailwind.config.ts
export default {
  darkMode: "class", // toggle via class on <html>
  // ...
};

// Component: use dark: variant
function Card({ children }: { children: ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      {children}
    </div>
  );
}

// Theme toggle
function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <button onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}>
      {theme === "light" ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}
```

### CSS Modules

```tsx
// Button.module.css
.button {
  border-radius: 0.5rem;
  padding: 0.5rem 1rem;
  font-weight: 500;
}

.primary {
  background-color: var(--color-primary);
  color: white;
}

.secondary {
  background-color: var(--color-gray-100);
  color: var(--color-gray-900);
}

// Button.tsx
import styles from "./Button.module.css"

function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return (
    <button
      className={`${styles.button} ${styles[variant]} ${className || ""}`}
      {...props}
    />
  )
}
```

### Design Tokens

Centralize design values as CSS custom properties:

```css
/* globals.css */
:root {
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-surface: #ffffff;
  --color-text: #111827;
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
}

.dark {
  --color-primary: #3b82f6;
  --color-primary-hover: #60a5fa;
  --color-surface: #111827;
  --color-text: #f9fafb;
}
```

### Component Library Integration (shadcn/ui)

```tsx
// shadcn/ui components are copied into your project (not a dependency)
// Customize via CSS variables and cn utility

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

function LoginForm() {
  return (
    <Card className="w-96">
      <CardHeader>
        <CardTitle>Sign In</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-4">
          <Input type="email" placeholder="Email" />
          <Input type="password" placeholder="Password" />
          <Button className="w-full">Sign In</Button>
        </form>
      </CardContent>
    </Card>
  );
}
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Styling Architecture

**Stack:** {detected framework}
**Styling approach:** {Tailwind CSS | CSS Modules | styled-components}
**Component library:** {shadcn/ui | Radix | Headless UI | None}

### Design Tokens

| Token Category | Source                           |
| -------------- | -------------------------------- |
| Colors         | {CSS vars | Tailwind config}     |
| Spacing        | {Tailwind default | custom}      |
| Typography     | {font families and scale}        |
| Dark mode      | {class strategy | media query}   |

### Component Variants

| Component | Variants                           | Approach        |
| --------- | ---------------------------------- | --------------- |
| Button    | primary, secondary, destructive    | cva + cn        |
| Card      | default, outlined                  | cn              |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Mixing multiple styling paradigms in the same project without clear boundaries
- Inline styles for static values (use classes or CSS variables)
- String concatenation for conditional classes (use cn/clsx utility)
- Desktop-first responsive design (mobile-first is the standard)
- Hardcoded color values instead of design tokens or Tailwind classes
- styled-components in Server Components (requires `"use client"`, adds runtime JS)
- Using `!important` to override styles (indicates specificity issues - fix the cascade)
- Creating custom CSS when the component library already provides the component
