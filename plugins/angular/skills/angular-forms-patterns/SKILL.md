---
name: angular-forms-patterns
description: Angular Reactive Forms - typed FormGroup, nonNullable, FormArray, async/cross-field validators, ControlValueAccessor, server validation surfacing.
metadata:
  category: frontend
  tags: [angular, forms, reactive-forms, formgroup, formarray, validators, controlvalueaccessor, server-validation]
user-invocable: false
---

# Angular Forms Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or reviewing any non-trivial form (login, signup, multi-step, dynamic, nested)
- Wiring validators (sync, async, cross-field) or surfacing server-side validation
- Authoring a custom input via `ControlValueAccessor`
- Choosing between Reactive Forms and Template-driven for a new feature

## Rules

- Reactive Forms only for non-trivial forms - typed `FormGroup<{...}>`. Template-driven is acceptable only for one-field opt-in toggles.
- Build forms with `inject(NonNullableFormBuilder)`; `nonNullable: true` is the default for new controls.
- Validators live on the control, not in the submit handler.
- Submit handler reads `form.getRawValue()` (typed), not `form.value` (loose).
- Server-validation errors are mapped back to controls via `setErrors`; never surface raw 422 text only at the form level.
- Custom inputs implement `ControlValueAccessor`; never write to a host `[(ngModel)]` from a parent component.
- `[disabled]` on a reactive control is a TS finding - use `control.disable()`/`enable()`.

## Patterns

### Typed `FormGroup` with `NonNullableFormBuilder`

```typescript
type LoginForm = { email: FormControl<string>; password: FormControl<string>; remember: FormControl<boolean> };

@Component({...})
export class LoginComponent {
  private fb = inject(NonNullableFormBuilder);

  form: FormGroup<LoginForm> = this.fb.group({
    email:    this.fb.control('', { validators: [Validators.required, Validators.email] }),
    password: this.fb.control('', { validators: [Validators.required, Validators.minLength(8)] }),
    remember: this.fb.control(false),
  });

  submit(): void {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = this.form.getRawValue(); // { email: string; password: string; remember: boolean }
    this.auth.login(value).subscribe(...);
  }
}
```

`NonNullableFormBuilder` guarantees `string` not `string | null` in `getRawValue()` - eliminates the most common typed-forms friction.

### `FormArray` of `FormGroup`

```typescript
type Line = { sku: FormControl<string>; qty: FormControl<number> };
type OrderForm = { customer: FormControl<string>; lines: FormArray<FormGroup<Line>> };

form = this.fb.group({
  customer: this.fb.control('', Validators.required),
  lines: this.fb.array<FormGroup<Line>>([]),
});

addLine(): void {
  this.form.controls.lines.push(this.fb.group<Line>({
    sku: this.fb.control('', Validators.required),
    qty: this.fb.control(1, [Validators.required, Validators.min(1)]),
  }));
}
removeLine(i: number): void { this.form.controls.lines.removeAt(i); }
```

Iterate the array via `@for (line of form.controls.lines.controls; track line)`; bind with `[formGroup]="line"`.

### Cross-Field Validator

```typescript
const matchPasswords: ValidatorFn = (group) => {
  const a = group.get('password')?.value;
  const b = group.get('confirm')?.value;
  return a && b && a !== b ? { mismatch: true } : null;
};

form = this.fb.group(
  { password: this.fb.control('', Validators.required), confirm: this.fb.control('', Validators.required) },
  { validators: [matchPasswords] },
);
```

Group-level errors surface on the parent (`form.errors`), not on the child controls - render them in the appropriate hint slot.

### Async Validator (Uniqueness)

```typescript
private users = inject(UserService);

uniqueEmail: AsyncValidatorFn = (ctrl) =>
  timer(300).pipe( // debounce keystroke
    switchMap(() => this.users.checkEmail(ctrl.value)),
    map((taken) => (taken ? { taken: true } : null)),
    catchError(() => of(null)), // network failure - do not block submit
  );

email = this.fb.control('', { validators: [Validators.required, Validators.email], asyncValidators: [this.uniqueEmail] });
```

While async runs, `control.pending` is `true` - submit buttons should reflect it.

### Server-Side Validation Surfacing

```typescript
submit(): void {
  if (this.form.invalid) { this.form.markAllAsTouched(); return; }
  this.api.create(this.form.getRawValue()).subscribe({
    error: (err: HttpErrorResponse) => {
      if (err.status === 422 && err.error?.errors) {
        // { email: ["already in use"], "lines.0.sku": ["unknown SKU"] }
        for (const [path, messages] of Object.entries(err.error.errors)) {
          const ctrl = this.form.get(path);
          ctrl?.setErrors({ server: messages });
        }
        this.form.markAllAsTouched();
      }
    },
  });
}
```

Server errors are first-class; render them alongside client-side messages in the same UI.

### `valueChanges` -> Signal

```typescript
query = this.fb.control('');
results = toSignal(
  this.query.valueChanges.pipe(
    debounceTime(300),
    distinctUntilChanged(),
    switchMap((q) => this.search.run(q ?? '')),
  ),
  { initialValue: [] as Result[] },
);
```

For `disabled` state, `valueChanges` skips emissions - use `valueChanges` + `statusChanges` or read `getRawValue()` on submit.

### Disabling Controls

```typescript
// Wrong
<input [formControl]="ctrl" [disabled]="isReadonly()" />  // emits a warning; the disabled attribute fights the FormControl

// Right
constructor() { effect(() => (this.isReadonly() ? this.ctrl.disable() : this.ctrl.enable())); }
```

### `ControlValueAccessor` Skeleton

```typescript
@Component({
  selector: 'app-color-picker',
  standalone: true,
  template: '...',
  providers: [{ provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => ColorPickerComponent), multi: true }],
})
export class ColorPickerComponent implements ControlValueAccessor {
  value = signal<string>('#000');
  private onChange: (v: string) => void = () => {};
  private onTouched: () => void = () => {};
  disabled = signal(false);

  writeValue(v: string | null): void { this.value.set(v ?? '#000'); }
  registerOnChange(fn: (v: string) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(d: boolean): void { this.disabled.set(d); }

  pick(color: string): void {
    this.value.set(color);
    this.onChange(color);
    this.onTouched();
  }
}
```

Usage: `<app-color-picker formControlName="brandColor" />` - validators, disabled state, dirty/touched all flow through.

### `updateValueAndValidity` Recompute

When you change a validator at runtime (`addValidators`, `removeValidators`) or modify a dependent field, call `control.updateValueAndValidity({ emitEvent: false })` to re-run validation without firing `valueChanges`.

### Template Error Display

```html
@let emailErrors = form.controls.email.errors;
@if (form.controls.email.touched && emailErrors) {
  @if (emailErrors['required']) { <p class="hint">Email is required.</p> }
  @if (emailErrors['email'])    { <p class="hint">Invalid format.</p> }
  @if (emailErrors['taken'])    { <p class="hint">That email is already in use.</p> }
  @if (emailErrors['server'])   { @for (m of emailErrors['server']; track m) { <p class="hint">{{ m }}</p> } }
}
```

## Output Format

```
## Form Design

**Angular version:** {detected}

### Forms

| Form        | Top-level group        | Validators        | Async? | Submit endpoint |
| ----------- | ---------------------- | ----------------- | ------ | --------------- |

### Custom Inputs (ControlValueAccessor)

| Component   | Wraps                  | Validates internally? |
| ----------- | ---------------------- | --------------------- |

### Server Validation Mapping

| Server key path  | Form control path |
| ---------------- | ----------------- |

### Recommendations

- {recommendation}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- `FormGroup` without an explicit type parameter on non-trivial forms
- `Validators.required` on a control whose only purpose is conditional - use `setValidators` based on a sibling
- Putting validation inside the submit handler instead of on the control
- Reading `form.value` for a submit payload (typed as `Partial<...>`) - use `getRawValue()`
- `[disabled]` template binding on a reactive control
- Writing to a child component's `[(ngModel)]` from a parent - use `ControlValueAccessor`
- Surfacing server validation only as a toast - map it to the offending control
- `valueChanges.subscribe(...)` in components without `takeUntilDestroyed()` - or convert to `toSignal`
- Mixing template-driven and reactive on the same form
