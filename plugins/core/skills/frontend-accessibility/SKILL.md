---
name: frontend-accessibility
description: Audit and build UI for WCAG 2.1 AA - semantic HTML, ARIA, keyboard nav, focus management, color contrast, screen reader testing.
metadata:
  category: frontend
  tags: [frontend, accessibility, a11y, wcag, aria, keyboard, screen-reader, multi-stack]
user-invocable: false
---

# Frontend Accessibility

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or reviewing UI components for WCAG 2.1 AA compliance
- Adding keyboard navigation or focus management to interactive elements
- Auditing pages before release

## Rules

Cite the WCAG criterion in parentheses when reporting a violation.

- Use native HTML semantics first (`button`, `a`, `nav`, `dialog`); ARIA only when no native element fits (4.1.2)
- Every interactive element must be keyboard-operable (2.1.1) and have a visible focus indicator (2.4.7)
- Every form input must have a programmatically associated visible label (1.3.1, 3.3.2)
- Every image must have `alt` (decorative: `alt=""`) (1.1.1)
- Never convey information by color alone (1.4.1)
- Dynamic content updates must be announced via live regions or focus management (4.1.3, 2.4.3)

---

## Patterns

### Semantic HTML First

```html
<!-- Bad: not keyboard accessible, no role, no focus -->
<div class="btn" onclick="submit()">Submit</div>

<!-- Good -->
<button type="submit">Submit</button>
```

### ARIA Usage

ARIA only when no native element provides the semantics. Never duplicate native roles (`role="button"` on `<button>`).

| Need               | Native       | ARIA Fallback                                       |
| ------------------ | ------------ | --------------------------------------------------- |
| Button             | `<button>`   | `role="button"` + `tabindex="0"` + keydown          |
| Dialog/modal       | `<dialog>`   | `role="dialog"` + `aria-modal="true"`               |
| Expandable section | `<details>`  | `aria-expanded` + `aria-controls`                   |
| Custom select      | `<select>`   | `role="listbox"` + `role="option"`                  |
| Autocomplete       | `<datalist>` | `role="combobox"` + `aria-expanded` + `aria-controls` + `aria-activedescendant` |
| Tabs               | (none)       | `role="tablist"` + `role="tab"` + `role="tabpanel"` |
| Live update        | (none)       | `aria-live="polite"` or `"assertive"`               |

Key rules:
- `aria-label` overrides visible text; prefer `aria-labelledby` referencing the visible label
- Never put `aria-hidden="true"` on focusable elements (creates ghost focus targets)

### Keyboard Navigation

| Component        | Expected Keys                                                |
| ---------------- | ------------------------------------------------------------ |
| Button/Checkbox  | Enter/Space to activate or toggle                            |
| Link             | Enter to follow                                              |
| Menu/Combobox    | Arrows to navigate, Enter to select, Escape to close         |
| Dialog           | Escape to close, Tab trapped within                          |
| Tabs             | Arrows to switch, Tab to enter/exit                          |
| Listbox          | Arrows, Enter, Escape, type-ahead                            |

### Focus Management

Modals/dialogs (2.4.3; trap must be escapable per 2.1.2):
1. Save previously focused element
2. Move focus to first focusable in dialog
3. Trap Tab/Shift+Tab within dialog
4. On close, restore focus to saved element

After dynamic changes: move focus to next item (deletion), main heading (SPA route change), or trigger (toast dismissed).

Provide a "Skip to main content" link as the first focusable element.

### Color and Status

- Text contrast: 4.5:1 normal, 3:1 large (18px+ or 14px+ bold) (1.4.3)
- UI component contrast: 3:1 against adjacent colors (1.4.11)
- Never use color alone for state - pair with text/icon (1.4.1)

```jsx
{/* Bad: color-only success */}
<button style={{color: success ? "green" : "red"}}>Add to Cart</button>

{/* Good: status announced */}
<button onClick={addToCart}>Add to Cart</button>
<span role="status" aria-live="polite">{statusMessage}</span>
```

### Forms

- Visible `<label>` associated via `for`/`id` or wrapping
- Required: both visual indicator and `required`/`aria-required="true"`
- Errors associated with input via `aria-describedby`; announce via `aria-live` or focus the error summary
- Group related inputs with `<fieldset>` + `<legend>`

### Dynamic Content

- Toasts: `role="status"` or `aria-live="polite"`
- Urgent alerts: `role="alert"` or `aria-live="assertive"` (use sparingly)
- Loading: `aria-busy="true"` on the updating region
- Infinite scroll: provide a "Load more" button alternative

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms. Common bindings:

- **React**: `jsx-a11y` ESLint plugin, `useId()` for label pairing, Radix or Headless UI for accessible primitives
- **Vue**: `vue-a11y` ESLint plugin, Radix Vue or Headless UI Vue, `<Teleport>` for modals
- **Angular**: Angular CDK `a11y` module (`FocusTrap`, `LiveAnnouncer`, `cdkTrapFocus`), Angular Material

For unknown stacks, apply the universal patterns and point the user to the framework's a11y docs.

---

## Output Format

Consuming workflow skills depend on this structure.

Severity: Critical = blocks task completion for keyboard or assistive-technology users; Major = significant barrier with a workaround; Minor = friction or best-practice deviation.

```
## Accessibility Assessment

**Stack:** {detected language / framework}
**Standard:** WCAG 2.1 AA

### Audit Results

| Issue         | WCAG Criterion | Severity                   | Element/Component       |
| ------------- | -------------- | -------------------------- | ----------------------- |
| {description} | {e.g., 1.1.1}  | {Critical | Major | Minor} | {component or selector} |

### Recommendations

- {recommendation with rationale and code example}

### No Issues Found

{If no issues: state explicitly that accessibility is adequate. If issues found: "See Audit Results." Never omit this section silently}
```

Design-phase requests (no code yet): keep the same structure; Audit Results rows list required behaviors for the planned component, with Element/Component naming the planned element.

---

## Avoid

- `div`/`span` for interactive elements instead of `button`, `a`, `input`
- Redundant ARIA on elements that already have native semantics
- `tabindex > 0` (breaks natural tab order)
- Hiding focus indicators (`outline: none`) without a visible replacement
- `aria-hidden="true"` on focusable elements
- Color-only state, `placeholder` as the only label, `title` as the only accessible name
- Auto-focusing on page load without user intent
