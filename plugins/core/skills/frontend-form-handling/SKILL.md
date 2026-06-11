---
name: frontend-form-handling
description: Apply frontend form patterns - validation, error display, multi-step forms, dirty tracking, submission handling. Adapts to detected stack.
metadata:
  category: frontend
  tags: [frontend, forms, validation, multi-step, submission, dirty-tracking, multi-stack]
user-invocable: false
---

# Frontend Form Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building forms with validation
- Implementing multi-step wizards
- Reviewing form UX (errors, dirty tracking, submission)
- Choosing a form library

## Rules

- Every input has a visible label; placeholder is never the only label
- Validate on blur per field, on submit for the whole form; re-validate on change once a field shows an error
- Error messages are specific ("Password must be at least 8 characters"), never "Invalid input"
- Server validation errors map back to the originating field inline
- Prevent double submission (disable submit button + show loading state)
- Warn before navigation when the form is dirty
- Multi-step forms preserve state across steps; backward nav never destroys data
- Never persist sensitive fields (card data, CVV, SSN) to local/session storage

---

## Patterns

### Form Library Selection

| Library                | Best For                                         |
| ---------------------- | ------------------------------------------------ |
| React Hook Form + Zod  | React: performance, uncontrolled inputs, schema  |
| VeeValidate + Zod      | Vue: Composition API, schema validation          |
| Angular Reactive Forms | Angular: type-safe FormGroup/FormControl         |
| Native HTML            | Trivial forms (1-3 fields, no complex rules)     |

Share a schema (Zod, Yup, Valibot) between client and server so validation rules don't drift.

### Validation Timing

```
// Bad: validates on every keystroke - errors shown while typing
<input onChange={e => { setValue(e.target.value); validate(e.target.value) }} />

// Good: validate on blur; once a field has an error, re-validate on change so it clears as soon as fixed
<input
  onBlur={() => validateField("email")}
  onChange={e => {
    setValue(e.target.value)
    if (fieldHasError("email")) validateField("email")
  }}
/>
```

### Async Validation

For server-checked fields (username availability, coupon codes):

- Trigger on blur or debounced input (300-500ms), never per keystroke
- Discard stale responses (AbortController or request sequence token) so an old result never overwrites a newer one
- Submit awaits pending async validators - keep the button in loading state rather than racing the check
- Show a pending indicator on the field while checking

### Error Display

Field-level:
- Display directly below the input
- `aria-describedby` linking input to error
- Pair red color with an icon or prefix (never color alone)
- Clear the error as soon as the user fixes the input

Form-level (server errors):
- Error summary at the top with `role="alert"`
- Include links to each errored field
- Move focus to the summary on submission failure
- Translate server field names to client names (snake_case to camelCase, nested paths); errors with no matching field stay in the summary

```html
<label for="email">Email</label>
<input id="email" type="email" aria-invalid="true" aria-describedby="email-error" />
<p id="email-error" role="alert">Please enter a valid email address</p>
```

### Submission Flow

1. Disable submit button, show loading state
2. Run client validation; on failure, show errors and focus the first errored field
3. Send request
4. Success: feedback, redirect or reset
5. Server error: map field errors back to inputs, show summary, re-enable button
6. Network error: show retry option, preserve form data, re-enable button

```
<button onClick={submit} disabled={isSubmitting} aria-busy={isSubmitting}>
  {isSubmitting ? "Submitting..." : "Submit"}
</button>
```

### Multi-Step Forms

- Single form-state object across steps (not per-step state)
- "Next" validates only the current step's fields (e.g., RHF `trigger(["field"])`; Angular nested `FormGroup`; VeeValidate per-step schema)
- "Back" preserves all data without re-validating
- Review step lists entered data with per-section "Edit" links
- For long forms: save draft to localStorage on step change; restore with a "Resume?" prompt; clear on success

### Sensitive Field Handling

Payment, identity, PCI data require extra care:

- **Tokenize**: use provider widgets (Stripe Elements, Braintree Drop-in) so raw card data stays in their iframe, never in your form state or server
- **Never persist**: exclude sensitive fields from any draft persistence; clear them from form state on navigation
- **Use proper `autocomplete`**: `cc-number`, `cc-exp`, `cc-csc` so browsers autofill securely; never prefill from your own storage

### Dirty Tracking

```
// Browser nav (close tab, back/forward)
useEffect(() => {
  if (!isDirty) return
  const handler = e => e.preventDefault()
  window.addEventListener("beforeunload", handler)
  return () => window.removeEventListener("beforeunload", handler)
}, [isDirty])

// SPA route changes: use the router's guard (React Router blocker, Vue Router beforeRouteLeave, Angular CanDeactivate)
```

### Schema-Based Validation

```
// Shared schema - used both client and server
const userSchema = z.object({
  email: z.string().email("Please enter a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
})

// Client
const form = useForm({ resolver: zodResolver(userSchema) })

// Server
const parsed = userSchema.safeParse(req.body)
```

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: React Hook Form + Zod resolver; `useActionState` for Server Action forms (React 19+/Next.js)
- **Vue**: VeeValidate + Zod, or FormKit for opinionated accessible forms
- **Angular**: Typed Reactive Forms, custom validators, `CanDeactivate` for dirty tracking

For unknown stacks, apply universal patterns and point the user to the framework's form docs.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## Form Handling Assessment

**Stack:** {detected language / framework}
**Form library:** {detected or recommended library}
**Validation library:** {detected or recommended schema library}

### Form Design

| Form        | Fields  | Validation        | Multi-step | Dirty Tracking |
| ----------- | ------- | ----------------- | ---------- | -------------- |
| {form name} | {count} | {client + server | client only | server only | none} | {Yes | No} | {Yes | No} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if form handling is adequate - do not omit this section silently}
```

Severity: High = data loss, security exposure, or blocked/duplicate submission; Medium = broken validation or error-display UX; Low = polish (timing, focus, copy).

---

## Avoid

- Placeholder as the only label
- Validating on every keystroke
- Generic errors like "Invalid input" or "Error"
- Allowing double submission (no disable during submit)
- Losing form data on navigation without warning
- Client-only validation without server enforcement
- Resetting the entire form on a single field's server error
- Multi-step forms that drop data on "Back"
- Showing all validation errors on page load
- Persisting sensitive data (card numbers, CVV, SSN) to local/session storage
- Handling raw card data in form state instead of using provider tokenization
