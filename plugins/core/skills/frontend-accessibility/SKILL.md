---
name: frontend-accessibility
description: WCAG 2.1 AA compliance - semantic HTML, ARIA, keyboard navigation, focus management, color contrast, screen reader testing. Adapts to detected frontend framework.
metadata:
  category: frontend
  tags: [frontend, accessibility, a11y, wcag, aria, keyboard, screen-reader, multi-stack]
user-invocable: false
---

# Frontend Accessibility

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building new UI components or pages
- Reviewing existing components for accessibility compliance
- Adding keyboard navigation or focus management to interactive elements
- Ensuring WCAG 2.1 AA compliance before release

## Rules

- Every interactive element must be keyboard accessible - no mouse-only interactions
- Every form input must have a visible, programmatically associated label
- Every image must have an `alt` attribute - decorative images use `alt=""`
- Color must not be the only means of conveying information
- Focus must be visible and follow a logical order
- ARIA is a last resort - use native HTML elements first (`button`, `nav`, `dialog`, not `div` with `role`)
- Dynamic content updates must be announced to screen readers via live regions or focus management

---

## Patterns

### Semantic HTML First

**Bad** - Div-based interactive elements:

```html
<div class="btn" onclick="submit()">Submit</div>
<div class="nav">
  <div class="nav-item" onclick="navigate('/')">Home</div>
</div>
```

Problem: Not keyboard accessible, no role announced, no focus management.

**Good** - Native semantic elements:

```html
<button type="submit">Submit</button>
<nav aria-label="Main navigation">
  <a href="/">Home</a>
</nav>
```

### ARIA Usage

Use ARIA only when no native HTML element provides the semantics needed:

| Need               | Use Native Element | ARIA Fallback (only if native is impossible)        |
| ------------------ | ------------------ | --------------------------------------------------- |
| Button             | `<button>`         | `role="button"` + `tabindex="0"` + keydown          |
| Navigation         | `<nav>`            | `role="navigation"`                                 |
| Dialog/modal       | `<dialog>`         | `role="dialog"` + `aria-modal="true"`               |
| Tab interface      | None exists        | `role="tablist"` + `role="tab"` + `role="tabpanel"` |
| Live update        | None exists        | `aria-live="polite"` or `aria-live="assertive"`     |
| Expandable section | `<details>`        | `aria-expanded` + `aria-controls`                   |

**Key ARIA rules:**

- Never use `role="button"` on a `<button>` - it already has the role
- `aria-label` overrides visible text - use `aria-labelledby` to reference visible labels
- `aria-hidden="true"` removes the element from the accessibility tree entirely - never use on focusable elements

### Keyboard Navigation

Every interactive component must support keyboard operation:

| Component | Expected Keys                                            |
| --------- | -------------------------------------------------------- |
| Button    | Enter, Space to activate                                 |
| Link      | Enter to follow                                          |
| Menu      | Arrow keys to navigate, Enter to select, Escape to close |
| Dialog    | Escape to close, Tab trapped within dialog               |
| Tabs      | Arrow keys to switch tabs, Tab to enter/exit tab list    |
| Combobox  | Arrow keys to navigate, Enter to select, Escape to close |
| Checkbox  | Space to toggle                                          |

### Focus Management

**Focus trapping** - Modals and dialogs must trap focus:

```
// When dialog opens:
1. Save the previously focused element
2. Move focus to the first focusable element in the dialog
3. Trap Tab/Shift+Tab within the dialog
4. On close: restore focus to the saved element
```

**Focus restoration** - After dynamic content changes:

- Deleted item in list: move focus to the next item, or the previous if last
- Route change in SPA: move focus to the main content heading or skip-link target
- Toast/notification dismissed: return focus to the trigger

**Skip links** - Provide "Skip to main content" link as the first focusable element:

```html
<a href="#main-content" class="sr-only focus:not-sr-only"
  >Skip to main content</a
>
```

### Color and Contrast

- **Text contrast**: Minimum 4.5:1 for normal text, 3:1 for large text (18px+ or 14px+ bold)
- **UI component contrast**: Minimum 3:1 against adjacent colors for interactive elements and their states
- **Do not rely on color alone**: Use text labels, icons, or patterns alongside color (e.g., error states need both red color and an error icon/text)

### Forms

- Every input must have a visible `<label>` associated via `for`/`id` or wrapping
- Required fields must be indicated both visually and programmatically (`aria-required="true"` or `required`)
- Error messages must be associated with their input (`aria-describedby` pointing to the error element)
- Error messages must be announced (via `aria-live` region or by moving focus to the error summary)
- Group related inputs with `<fieldset>` and `<legend>`

### Dynamic Content

- Toast notifications: use `role="status"` or `aria-live="polite"`
- Urgent alerts: use `role="alert"` or `aria-live="assertive"` - use sparingly
- Loading states: announce with `aria-busy="true"` on the updating region, or use `aria-live` to announce completion
- Infinite scroll: provide a "Load more" button alternative; announce new content count

## Stack-Specific Guidance

After loading stack-detect, apply accessibility patterns using the tools and conventions of the detected ecosystem:

- **React**: Use `jsx-a11y` ESLint plugin, `<Fragment>` to avoid extra wrapper divs, `useId()` for stable `id`/`for` pairing, React's `<dialog>` support or Radix/Headless UI for accessible primitives
- **Vue**: Use `vue-a11y` ESLint plugin, Headless UI Vue or Radix Vue for accessible primitives, `<Teleport>` for modal focus management
- **Angular**: Use Angular CDK a11y module (`FocusTrap`, `LiveAnnouncer`, `FocusMonitor`), Angular Material components (accessible by default), `cdkTrapFocus` directive for modals

If the detected stack is unfamiliar, apply the universal patterns above and recommend the user consult their framework's accessibility documentation.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## Accessibility Assessment

**Stack:** {detected language / framework}
**Standard:** WCAG 2.1 AA

### Audit Results

| Issue                    | WCAG Criterion | Severity          | Element/Component      |
| ------------------------ | -------------- | ----------------- | ---------------------- |
| {description}            | {e.g., 1.1.1}  | {Critical | Major | Minor} | {component or selector} |

### Recommendations

- {recommendation with rationale and code example}

### No Issues Found

{State explicitly if accessibility is adequate - do not omit this section silently}
```

---

## Avoid

- Using `div` or `span` for interactive elements instead of `button`, `a`, `input`
- Adding ARIA attributes to elements that already have native semantics (redundant ARIA)
- Using `tabindex` values greater than 0 (breaks natural tab order)
- Hiding focus indicators (`outline: none`) without providing a visible alternative
- Using `aria-hidden="true"` on focusable elements (creates ghost focus targets)
- Relying on color alone to indicate state (errors, success, active)
- Using `placeholder` as a substitute for `<label>` (disappears on input, poor contrast)
- Auto-focusing elements on page load without user intent (disorienting for screen reader users)
- Using `title` attribute as the only accessible name (not reliably announced)
