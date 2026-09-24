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
- Prevent double submission: disable the submit button and show a loading state once hydrated, and enforce it server-side (idempotency key or one-time token) for any form that must work before hydration
- Warn before navigation when the form is dirty and client JS is running; a form that must submit pre-hydration has no such warning and that is not a defect
- Multi-step forms preserve state across steps; backward nav never destroys data
- Never persist sensitive fields (card number, expiry, CVV/CVC, SSN, passwords) to local/session storage

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
2. Run client validation; on failure, re-enable the button, show errors and focus the first errored field
3. Send request
4. Success: feedback, redirect or reset
5. Server error: map field errors back to inputs, show summary, re-enable button
6. Network error: show retry option, preserve form data, re-enable button

```
<button onClick={submit} disabled={isSubmitting} aria-busy={isSubmitting}>
  {isSubmitting ? "Submitting..." : "Submit"}
</button>
```

### Field Arrays and Cross-Field Rules

Repeating groups (line items, contacts) use the library's array primitive - RHF `useFieldArray`, VeeValidate `FieldArray`, Angular `FormArray` - so each row keeps a stable key. Never index rows by array position for React keys: removing row 1 re-indexes everything below and the wrong inputs keep the wrong errors.

A rule spanning fields (totals against a cap, end date after start date, "at least one contact") has no single owning input, so it needs a home that is neither the field slot nor the server-error summary: render it at the boundary it constrains - under the array for a total, under the pair for a date range - with `role="alert"`, and validate it at the schema level (Zod `.refine`, or `.superRefine()` / `.check()` for multi-issue cases) so client and server agree.

Server errors on array paths (`items[3].amount`) map back by index to that row's input; when the index no longer exists because the user removed the row, the error goes to the summary.

### Multi-Step Forms

- Single form-state object across steps (not per-step state)
- "Next" validates only the current step's fields (e.g., RHF `trigger(["field"])`; Angular nested `FormGroup`; VeeValidate per-step schema)
- "Back" preserves all data without re-validating
- Review step lists entered data with per-section "Edit" links
- For long forms: save draft to localStorage on step change; restore with a "Resume?" prompt; clear on success

### Sensitive Field Handling

Payment, identity, PCI data require extra care:

- **Tokenize**: use provider widgets (Stripe Elements, Braintree Drop-in) so raw card data stays in their iframe, never in your form state or server. This is the default; the `autocomplete` guidance below applies only when you own the inputs
- **Never persist**: exclude sensitive fields from any draft persistence; clear them from form state when the user leaves the form (not between steps of the same wizard)
- **Use proper `autocomplete`**: on the rare form that does own its card fields, set `cc-number`, `cc-exp` and `cc-csc` so browsers autofill them; most users will still type the security code (only some browsers, Chrome among them, save it, and only on opt-in). With provider widgets these attributes live inside the provider's iframe and are not yours to set

### File Uploads

Decide when the bytes move, because everything else follows from it:

- **Upload on selection** (recommended for large or multiple files): each file uploads immediately to its own progress bar with cancel and remove; the form field then holds a returned file id, so a failed submit costs nothing and re-submitting does not re-upload. Orphaned uploads need a server-side sweep for files whose form was never submitted.
- **Upload on submit** (fine for one file small enough that re-sending it after a failed submit costs little - a few MB): simpler, but submit now takes as long as the transfer, and any validation failure discards every byte the user just waited for.

Validate size and type client-side before the transfer starts - it is the one validation that saves the user real time - and again on the server, since the client check is a courtesy, not a control. Accept the `accept` attribute's limits as a hint only; browsers do not enforce it.

### Progressive Enhancement

A form that must work before hydration (Server Actions, plain `<form action>`) cannot rely on client JS, so the client-side rules become enhancements layered on a working baseline rather than requirements:

- Double submission is prevented server-side, by an idempotency key or a one-time form token; `useFormStatus`/`isSubmitting` disables the button once hydrated.
- Validation is server-authoritative and re-rendered with the response; client validation only shortens the round trip.
- Dirty-navigation warnings simply do not exist pre-hydration - that is acceptable, not a defect.
- Files upload on submit whatever their size; upload on selection is a hydrated enhancement.
- Repeating rows cannot use a client field-array primitive before hydration: add rows with a submit button (`name="intent" value="add-row"`) handled by the same action, which returns the parsed rows and entered values so the re-render keeps them (no cookie or redirect), and let `useFieldArray` take over once hydrated. The action parses indexed names (`items.0.sku`) out of `FormData` into an array before the schema runs.

Review such a form against the baseline first: it should submit, validate, and report errors with JS disabled. Findings that amount to "no client-side guard before hydration" are not defects.

### Dirty Tracking

```
// Document unload only (tab close, reload, external link). Not SPA back/forward - that is popstate.
useEffect(() => {
  if (!isDirty) return
  const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = true }
  window.addEventListener("beforeunload", handler)
  return () => window.removeEventListener("beforeunload", handler)
}, [isDirty])
// beforeunload needs sticky activation and never fires when the OS kills a backgrounded tab;
// save the draft on visibilitychange to "hidden" (the last event reliably delivered) if it must survive that.

// SPA route changes: use the router's guard (React Router blocker, Vue Router beforeRouteLeave,
// Angular CanDeactivateFn - the recommended form; the class-based CanDeactivate interface still works)
```

### Schema-Based Validation

```
// Shared schema - used both client and server
const userSchema = z.object({
  email: z.email("Please enter a valid email"),   // Zod 4 top-level format; z.string().email() is deprecated
  password: z.string().min(8, "Password must be at least 8 characters"),
})

// Client
const form = useForm({ resolver: zodResolver(userSchema), mode: "onTouched" }) // validates on blur, then on every change once touched - the default "onSubmit" never validates on blur

// Server
const parsed = userSchema.safeParse(req.body)
```

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: React Hook Form + Zod resolver; `useActionState` for Server Action forms (React 19+/Next.js)
- **Vue**: VeeValidate + Zod, or FormKit for opinionated accessible forms
- **Angular**: Typed Reactive Forms, custom validators, `CanDeactivateFn` for dirty tracking

For any framework not bound above - `unknown`, or a detected one such as Svelte or Solid - apply the universal patterns and point the user to that framework's form docs.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## Form Handling Assessment

**Stack:** {Framework and Language as a display name (`Next.js 15.5 / TypeScript` for stack-detect's `React (Next.js)`) - the major.minor from the owning app's `package.json` (`^15.5.0` -> 15.5); with no `tsconfig.json`, the extensions of the files in scope decide JS vs TS, overriding stack-detect's Language; in a monorepo, the app owning the reviewed code; "unknown - universal patterns applied" when inconclusive}

**Form library:** {detected or recommended library}

**Validation library:** {detected or recommended schema library}

### Form Design

| Form        | Fields  | Validation        | Multi-step | Dirty Tracking |
| ----------- | ------- | ----------------- | ---------- | -------------- |
| {form name} | {count, as `<fixed>` or `<fixed> + N x <per-row>` for a repeating group} | {client + server \| client only \| server only \| none; append `(broken)` when the wiring exists but does not work, `(not submitted)` when the values never reach a server} | {Yes \| No} | {Yes \| No} |

### Recommendations {when at least one applies}

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if form handling is adequate - do not omit this section silently}

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}

Notes: {observations outside this skill's concern, each naming the owning concern; omit when none}
```

Severity: High = data loss (including values collected but never submitted), security exposure, or blocked/duplicate submission (a stuck submit button, a submit with no double-submit guard at all, and a hand-rolled flag that contradicts the framework's pending state all land here), and a mutation with no server-side validation; Medium = broken validation timing, error-display UX (including per-keystroke validation and a server error mapped to the wrong field), a missing or placeholder-only label, or field-array rows keyed by index so errors follow the wrong row; Low = polish (debounce values, focus order, copy). A defect not named here takes the band whose description fits; when two fit, the higher wins.

Include either `Issues Found` or `No Issues Found`, never both. A clean run emits every header field, the in-scope table, `Recommendations` when any apply, and `No Issues Found`; only the `Issues Found` blocks are omitted. Order Issues Found by severity, highest first; within a band, file order (the order the input lists the files; ascending line within a file). A review reports every defect in the files in scope, not only the reported symptom. `Location` may list several `file:line` entries (or several lines of one file), comma-separated, when one root cause spans them; lead with the file the fix changes, and sort the finding by that lead file. In implement or design mode (building a form, not reviewing), the Form Design table documents what was built or planned, and Issues Found carries residual risks knowingly accepted. When the build or design touches existing code, defects already in it are ordinary Issues Found entries marked `(pre-existing)` at their own severity; the residual-risk reading covers only the new work. `stack-detect` has no field for this (it carries versions only when a `## Tech Stack` section declares them): read the form and validation libraries from `package.json` dependencies (the owning app's manifest in a monorepo) and the imports in the files in scope.

---

## Avoid

- Placeholder as the only label
- Validating on every keystroke
- Generic errors like "Invalid input" or "Error"
- Allowing double submission with no guard at all - a form that must work pre-hydration needs the server-side one, a hydrated form needs the disabled button
- Losing form data on navigation without warning, wherever client JS is running to give one
- Client-only validation without server enforcement
- Resetting the entire form on a single field's server error
- Multi-step forms that drop data on "Back"
- Showing all validation errors on page load
- Persisting sensitive data (card numbers, CVV, SSN) to local/session storage
- Handling raw card data in form state instead of using provider tokenization
