---
name: frontend-accessibility
description: Audit and build UI for WCAG 2.1 AA - semantic HTML, ARIA, keyboard nav, focus management, color contrast, live regions.
metadata:
  category: frontend
  tags: [frontend, accessibility, a11y, wcag, aria, keyboard, screen-reader, nextjs]
user-invocable: false
---

# Frontend Accessibility

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or reviewing UI components for WCAG 2.1 AA compliance
- Specifying the accessible behaviour of a component before it is built
- Adding keyboard navigation or focus management to interactive elements
- Auditing pages before release

## Rules

Cite the WCAG criterion for every violation: in the `WCAG Criterion` column when emitting the audit block, in parentheses when mentioning one in prose. A Minor deviation that fails no success criterion writes `best practice (<source, e.g. ARIA in HTML>)` there.

- Use native HTML semantics first (`button`, `a`, `nav`, `dialog`); ARIA only when no native element fits (the First Rule of ARIA Use - cite 4.1.2 only when the name, role or value is missing or wrong)
- Every interactive element must be keyboard-operable (2.1.1) and have a visible focus indicator (2.4.7)
- Every form input must have a programmatically associated visible label (1.3.1, 3.3.2)
- Every image must have `alt` (decorative: `alt=""`) (1.1.1)
- Never convey information by color alone (1.4.1)
- Repeated controls need names that identify their target, alone or through programmatic context such as the product card around an "Add" button (2.4.6; 2.4.4 for links); identical bare names with no such context are a Minor best practice
- Dynamic content updates must be announced via live regions or focus management (4.1.3, 2.4.3)

---

## Patterns

### Semantic HTML First

```tsx
{/* Bad: not keyboard accessible, no role, no focus */}
<div className="btn" onClick={submit}>Submit</div>

{/* Good */}
<button type="submit">Submit</button>
```

### ARIA Usage

ARIA only when no native element provides the semantics. Never duplicate native roles (`role="button"` on `<button>`).

| Need               | Native       | ARIA Fallback                                       |
| ------------------ | ------------ | --------------------------------------------------- |
| Button             | `<button>`   | `role="button"` + `tabindex="0"` + keydown          |
| Dialog/modal       | `<dialog>`   | `role="dialog"` + `aria-modal="true"`               |
| Expandable section | `<details>`  | `aria-expanded` + `aria-controls`                   |
| Custom select      | `<select>`   | select-only `role="combobox"` opening `role="listbox"` + `role="option"` |
| Autocomplete       | `<datalist>` | `role="combobox"` + `aria-expanded` + `aria-controls` + `aria-activedescendant` |
| Multi-select combobox | (none)    | `role="combobox"` + `role="listbox"` with `aria-multiselectable="true"`; selected values as chip buttons named "Remove <value>" in a list labelled "Selected <things>" |
| Tabs               | (none)       | `role="tablist"` + `role="tab"` + `role="tabpanel"` |
| Data grid          | (none; `<table>` is static) | `role="grid"` on the `<table>` (its `tr`/`td` then map to row/gridcell; explicit roles only on a div grid), roving `tabindex`, arrows in two dimensions |
| Live update        | `<output>` (implicit `role="status"`, AT support uneven) | `aria-live="polite"` or `"assertive"` |

**Virtualized collections** (windowed grids, infinite lists) render a fraction of their rows, so the DOM count contradicts the real one. Declare the logical size - `aria-rowcount` / `aria-colcount` on the grid with `aria-rowindex` per row, or `aria-setsize` / `aria-posinset` on list items - or assistive technology announces "3 of 30" for a 50,000-row collection. Keep focus valid when the window scrolls: move focus with the item, never leave it on a recycled node.

Key rules:
- `aria-label` overrides visible text; prefer `aria-labelledby` referencing the visible label
- Never put `aria-hidden="true"` on focusable elements (creates ghost focus targets)

### Keyboard Navigation

| Component        | Expected Keys                                                |
| ---------------- | ------------------------------------------------------------ |
| Button           | Enter or Space to activate                                   |
| Checkbox         | Space to toggle; Enter submits the form, it does not toggle  |
| Link             | Enter to follow                                              |
| Menu/Combobox    | Arrows to navigate, Enter to select, Escape to close; in a combobox, typing filters the options (a bare listbox's type-ahead jumps instead) |
| Dialog           | Escape to close, Tab trapped within                          |
| Tabs             | Arrows to switch, Tab to enter/exit                          |
| Listbox          | Up/Down, Home/End, type-ahead; Space or Shift+Arrow selects in a multi-select (Enter/Escape belong to the combobox that opens it) |
| Grid             | Arrows in both axes, Home/End for row ends, Ctrl+Home/End for grid ends; one Tab stop for the whole grid |

### Focus Management

Modals/dialogs (2.4.3; trap must be escapable per 2.1.2). A native `<dialog>` opened with
`showModal()` does all four: it focuses the `autofocus` element (else the first focusable), inerts the
rest of the page and restores focus on close - set `autofocus` when that default is wrong (a
destructive button first). Hand-rolled dialogs owe all four:
1. Save previously focused element
2. Move focus to the first focusable in the dialog
3. Trap Tab/Shift+Tab within the dialog
4. On close, restore focus to the saved element

After dynamic changes: move focus to next item (deletion) or trigger (toast dismissed).

Client navigation (`next/link`, `router.push`) is announced by Next's built-in route announcer, which reads `document.title`, else the first `<h1>`, and announces only when that text changes - two routes sharing a title navigate with no announcement. Give every route a unique, descriptive title through the Metadata API (`metadata` / `generateMetadata`) (2.4.2); a shared or missing title is the defect, not a missing hand-rolled focus move.

Provide a "Skip to main content" link as the first focusable element.

### Color and Status

- Text contrast: 4.5:1 normal, 3:1 large - large means 18pt/24px+, or 14pt/18.66px+ bold (1.4.3)
- UI component contrast: 3:1 against adjacent colors (1.4.11)
- Compute the ratio when both colors are declared in code (classes, tokens - Tailwind palette classes count, their values are fixed); when either depends on rendered context - a photo, a background set outside the files in scope - list it under Not assessed rather than guessing a row
- Over an image, gradient, or translucent overlay there is no single background color: measure the worst pixel behind the text box - the darkest for dark text, the lightest for light text, since that is where the ratio collapses - after compositing the overlay. Passing against the overlay's nominal color while failing over the photo behind it is the usual way a hero section ships broken; a solid scrim or a text-shaped backdrop fixes it.
- Never use color alone for state - pair with text/icon (1.4.1)

```jsx
{/* Bad: color-only success */}
<button style={{color: success ? "green" : "red"}}>Add to Cart</button>

{/* Good: the state is carried by text and an icon, not colour alone (1.4.1),
    and the change is announced (4.1.3). role="status" already implies aria-live="polite". */}
<button onClick={addToCart}>Add to Cart</button>
<p role="status" className={status === "failed" ? "text-red-700" : "text-green-700"}>
  {status === "added" && <><CheckIcon aria-hidden="true" /> In your cart</>}
  {status === "failed" && <><AlertIcon aria-hidden="true" /> Could not add</>}
</p>
{/* status: "idle" | "added" | "failed" - idle renders an empty region, so nothing claims failure before a try */}
```

### Forms

- Visible `<label>` associated via `htmlFor`/`id` or wrapping
- Required: both visual indicator and `required`/`aria-required="true"`
- Errors associated with input via `aria-describedby`; announce via `aria-live` or focus the error summary
- Group related inputs with `<fieldset>` + `<legend>`

### Dynamic Content

- Toasts: `role="status"` or `aria-live="polite"`
- Urgent alerts: `role="alert"` or `aria-live="assertive"` (use sparingly)
- Loading: `aria-busy="true"` on the updating region
- One live region per announcement stream; debounce rapid updates (a result count while typing) so only the settled value is announced
- Infinite scroll: provide a "Load more" button alternative (2.1.1)

## Next.js Bindings

- Lint: `eslint-config-next` enables only 6 `jsx-a11y` rules, all at `warn` (`alt-text`, ARIA props and roles); add `eslint-plugin-jsx-a11y`'s `recommended` flat config for the interactive-element and label rules (`<div onClick>`, unlabeled inputs). `next lint` is removed and `next build` no longer lints, so the rules run only where something invokes `eslint` (a script, CI, the editor) against a flat `eslint.config.*`
- `useId()` for label and description pairing
- Radix or Headless UI for accessible primitives (Radix ships no combobox - use Headless UI `Combobox` or React Aria for autocompletes)

---

## Output Format

When building, apply Rules and Patterns as constraints and emit the code alone - the block below is the audit deliverable, never a self-assessment of code just written. When auditing, emit the block; invoked standalone, order rows Critical first; within a band, file order (the order the input lists the files; ascending line within a file). Consuming workflow skills depend on this structure.

Severity: Critical = blocks task completion for a user relying on a keyboard, assistive technology, or sufficient contrast; Major = significant barrier with a workaround; Minor = friction or best-practice deviation.

A row is one criterion failing one way: a dialog missing both its role and its focus trap is two rows, because each cites a different criterion and takes its own fix, while the same criterion failing the same way on several elements is one row listing them all.

```
## Accessibility Assessment

**Stack:** {Framework and Language as a display name (`Next.js 16.3 / TypeScript` for stack-detect's `React (Next.js)`) - the major.minor from the owning app's `package.json` (`^16.3.0` -> 16.3); with no `tsconfig.json`, the extensions of the files in scope decide JS vs TS, overriding stack-detect's Language; in a monorepo, the app owning the reviewed code; `unknown` for a part that is inconclusive}

**Standard:** WCAG 2.1 AA

### Audit Results

| Issue         | WCAG Criterion | Severity                   | Element/Component       |
| ------------- | -------------- | -------------------------- | ----------------------- |
| {description} | {e.g., 1.1.1}  | {Critical \| Major \| Minor} | {component or selector} |

### Recommendations

- {recommendation with rationale and code example}

### Not assessed

- {anything the input never showed or that could not be verified from it - a contrast ratio needing the rendered pixels, a component whose markup is produced by an external call, a file named in scope but not provided. A statement of missing input, never a guessed issue. Omit this section when nothing applies}

Notes: {observations outside this skill's concern, each naming the owning concern; omit when none}

### No Issues Found

{Emit this section only when Audit Results is empty, and state explicitly that accessibility is adequate. When issues were found, omit it entirely}
```

A clean run emits **Stack**, **Standard**, an empty Audit Results table, `Recommendations` when any apply, `Not assessed` when anything went unverified, and `No Issues Found`; only the issue rows are omitted. `Not assessed` is independent of whether any issue was found.

Design-phase requests (no code yet): keep the same structure, but read the `Issue` column as the required behaviour for the planned component, with Element/Component naming the planned element. Severity rates the impact of shipping without that behaviour, which makes most rows Critical or Major. Order by severity when invoked standalone; within a band, put the behaviours a framework primitive supplies for free last, so the ordering still separates what needs design attention from what comes with the library. `No Issues Found` never applies in this mode - there is no code to call adequate - so omit it.

---

## Avoid

- `div`/`span` for interactive elements instead of `button`, `a`, `input`
- Redundant ARIA on elements that already have native semantics
- `tabindex > 0` (breaks natural tab order)
- Hiding focus indicators (`outline: none`) without a visible replacement
- `aria-hidden="true"` on focusable elements
- Color-only state, `placeholder` as the only label, `title` as the only accessible name
- Auto-focusing on page load without user intent
