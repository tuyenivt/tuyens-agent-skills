---
name: frontend-form-handling
description: Frontend form patterns - validation, error display, multi-step forms, dirty tracking, submission handling. Adapts to detected stack (React Hook Form, Formik, VeeValidate, Angular Reactive Forms, etc.).
metadata:
  category: frontend
  tags: [frontend, forms, validation, multi-step, submission, dirty-tracking, multi-stack]
user-invocable: false
---

# Frontend Form Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building forms with validation requirements
- Implementing multi-step wizards or complex form flows
- Reviewing form UX patterns (error display, dirty tracking, submission handling)
- Choosing a form library for the project

## Rules

- Every form input must have a visible label - never use placeholder as the only label
- Validation must run on blur for individual fields and on submit for the full form - not on every keystroke
- Error messages must be specific ("Password must be at least 8 characters"), not generic ("Invalid input")
- Server-side validation errors must be displayed inline next to the relevant field
- Forms must prevent double submission (disable button + show loading state during submit)
- Dirty tracking must warn users before navigating away from unsaved changes
- Multi-step forms must preserve state across steps and allow backward navigation without data loss

---

## Patterns

### Form Library Selection

| Library                | Framework | Best For                                         |
| ---------------------- | --------- | ------------------------------------------------ |
| React Hook Form        | React     | Performance-focused, uncontrolled inputs         |
| Formik                 | React     | Controlled inputs, simpler mental model          |
| VeeValidate            | Vue       | Composition API integration, Zod/Yup support     |
| FormKit                | Vue       | Opinionated, accessible forms with theming       |
| Angular Reactive Forms | Angular   | Built-in, type-safe, observable-based            |
| Native HTML            | Any       | Simple forms (1-3 fields, no complex validation) |

Use a schema validation library (Zod, Yup, Valibot) for validation rules - share schemas between client and server.

### Validation Strategy

**Bad** - Validate on every keystroke:

```
// Fires validation on every character typed
<input onChange={(e) => {
  setValue(e.target.value)
  validate(e.target.value)  // "P" -> "Pa" -> "Pas" -> error shown immediately
}} />
```

Problem: Shows errors while the user is still typing, creating a frustrating experience.

**Good** - Validate on blur, re-validate on change after first error:

```
// Show error only after user leaves the field
// Once an error is shown, re-validate on change so it clears immediately when fixed
<input
  onBlur={() => validateField("email")}
  onChange={(e) => {
    setValue(e.target.value)
    if (fieldHasError("email")) validateField("email")  // re-validate only if already showing error
  }}
/>
```

### Error Display

**Field-level errors:**

- Display directly below the input field
- Use `aria-describedby` to associate error with input
- Use red color AND an icon/prefix (not color alone)
- Clear the error as soon as the user fixes it

**Form-level errors (server errors):**

- Display at the top of the form in an error summary
- Include links to the specific fields with errors
- Use `role="alert"` for the error summary
- Move focus to the error summary on submission failure

```html
<!-- Accessible error display -->
<label for="email">Email</label>
<input
  id="email"
  type="email"
  aria-invalid="true"
  aria-describedby="email-error"
/>
<p id="email-error" role="alert">Please enter a valid email address</p>
```

### Submission Handling

```
1. User clicks submit
2. Disable submit button, show loading indicator
3. Run client-side validation
4. If invalid: show errors, re-enable button, focus first error field
5. If valid: send request to server
6. On success: show success feedback, redirect or reset form
7. On server error: map server field errors to form fields, show error summary, re-enable button
8. On network error: show retry option, re-enable button, preserve form data
```

**Bad** - No double-submit protection:

```
<button onClick={submitForm}>Submit</button>
```

**Good** - Protected submission:

```
<button
  onClick={submitForm}
  disabled={isSubmitting}
  aria-busy={isSubmitting}
>
  {isSubmitting ? "Submitting..." : "Submit"}
</button>
```

### Multi-Step Forms (Wizards)

**State management:**

- Store all step data in a single form state object (not per-step state)
- Validate each step's fields on "Next" before advancing - validate only the current step's fields (React Hook Form: `trigger(["field1", "field2"])`; Angular: validate the nested `FormGroup` for that step)
- Allow "Back" navigation without losing entered data
- Show step progress indicator with step labels

**Navigation pattern:**

```
1. Step indicator: [1. Contact] -> [2. Address] -> [3. Review] -> [4. Confirm]
2. "Next" validates current step fields only
3. "Back" preserves all data, does not re-validate
4. "Review" step shows all entered data with "Edit" links per section
5. Final submit sends all accumulated data
```

**Persistence:**

- For long forms: save draft to localStorage/sessionStorage on each step change
- Restore from storage on page reload with a "Resume where you left off?" prompt
- Clear storage on successful submission
- **Sensitive fields (payment, PCI, SSN):** Never persist to localStorage or sessionStorage. Use payment provider tokenization (Stripe Elements, Braintree Drop-in) so raw card data never enters your form state. Clear sensitive field values from the form state object when navigating away from that step.

### Sensitive Field Handling

Forms that collect payment, identity, or other sensitive data require additional precautions:

- **Tokenize, do not store:** Use payment provider embedded widgets (Stripe Elements, Braintree Drop-in, PayPal buttons) that handle card data in their own iframe - raw card numbers should never touch your form state or your server
- **Exclude from persistence:** When persisting multi-step form data to localStorage, explicitly omit sensitive fields. Only persist non-sensitive steps (personal info, address) and re-collect sensitive input if the user returns
- **Clear on navigation:** When the user navigates away from a step containing sensitive fields, clear those values from the form state object
- **Autocomplete attributes:** Use appropriate `autocomplete` values (`cc-number`, `cc-exp`, `cc-csc`) to help browsers autofill securely, but never prefill these from your own storage

### Dirty Tracking

Warn users before they lose unsaved changes:

```
// Detect unsaved changes
const isDirty = formState.isDirty  // from form library

// Browser navigation (back/forward, close tab)
useEffect(() => {
  if (isDirty) {
    const handler = (e) => { e.preventDefault() }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }
}, [isDirty])

// SPA navigation (route change)
// Use router's navigation guard (React Router blocker, Vue Router beforeRouteLeave, Angular CanDeactivate)
```

### Schema-Based Validation

Share validation schemas between client and server:

```
// Shared schema (e.g., Zod)
const userSchema = z.object({
  email: z.string().email("Please enter a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  name: z.string().min(1, "Name is required"),
})

// Client: used by form library's resolver
const form = useForm({ resolver: zodResolver(userSchema) })

// Server: used for request validation
const parsed = userSchema.safeParse(req.body)
```

## Stack-Specific Guidance

After loading stack-detect, apply form patterns using the libraries and idioms of the detected ecosystem:

- **React**: React Hook Form + Zod resolver (primary), Formik + Yup for simpler cases, `useActionState` for Server Action forms (React 19+/Next.js)
- **Vue**: VeeValidate + Zod (primary), FormKit for opinionated accessible forms, `useField`/`useForm` composables
- **Angular**: Reactive Forms with typed FormGroup/FormControl, built-in validators + custom validators, `CanDeactivate` guard for dirty tracking

If the detected stack is unfamiliar, apply the universal patterns above and recommend the user consult their framework's form documentation.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## Form Handling Assessment

**Stack:** {detected language / framework}
**Form library:** {detected or recommended library}
**Validation library:** {detected or recommended schema library}

### Form Design

| Form                | Fields | Validation        | Multi-step | Dirty Tracking |
| ------------------- | ------ | ----------------- | ---------- | -------------- |
| {form name}         | {count}| {client + server} | {Yes | No} | {Yes | No}     |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description of form handling issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if form handling is adequate - do not omit this section silently}
```

---

## Avoid

- Using placeholder text as the only label (disappears on input, poor accessibility)
- Validating on every keystroke (frustrating UX, shows errors while user is still typing)
- Generic error messages like "Invalid input" or "Error" (unhelpful, user cannot fix the issue)
- Allowing double submission (no button disable during submit)
- Losing form data on navigation without warning (dirty tracking missing)
- Client-only validation without server validation (security risk, can be bypassed)
- Resetting the entire form on a single field's server error (data loss)
- Multi-step forms that lose data on "Back" navigation (broken UX)
- Showing all validation errors on page load before user interaction (overwhelming)
- Persisting sensitive form data (payment card numbers, CVV, SSN) to localStorage or sessionStorage (PCI compliance violation)
- Handling raw card data in your form state instead of using payment provider tokenization (Stripe Elements, Braintree)
