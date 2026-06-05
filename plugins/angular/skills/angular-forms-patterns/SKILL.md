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

- Reactive Forms for any form with >1 control or any validation. Template-driven only for a single isolated checkbox/toggle.
- Build via `inject(NonNullableFormBuilder)` so controls default to `nonNullable` (`getRawValue()` returns `string`, not `string | null`).
- Validators live on the control, not in the submit handler.
- Submit reads `form.getRawValue()` (typed), not `form.value` (loose `Partial<...>`).
- Server validation maps back to the offending control via `setErrors`, and clears via `setErrors(null)` on next edit. Never surface a 422 only as a toast.
- Custom inputs implement `ControlValueAccessor`; never write to a child's `[(ngModel)]` from a parent.
- `[disabled]` on a reactive control is a finding - call `control.disable()`/`enable()` (driven by an `effect` in an injection context when reactive).

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
  timer(300).pipe( // delay to throttle requests; the validator framework cancels stale runs on new value
    switchMap(() => this.users.checkEmail(ctrl.value)),
    map((taken) => (taken ? { taken: true } : null)),
    catchError(() => of(null)), // network failure - do not block submit
  );

email = this.fb.control('', {
  validators: [Validators.required, Validators.email],
  asyncValidators: [this.uniqueEmail],
  updateOn: 'blur', // stops the check from running per keystroke
});
```

While async runs, `control.pending` is `true` - submit buttons should reflect it.

### Server-Side Validation Surfacing

```typescript
private destroyRef = inject(DestroyRef);

submit(): void {
  if (this.form.invalid) { this.form.markAllAsTouched(); return; }
  this.api.create(this.form.getRawValue())
    .pipe(takeUntilDestroyed(this.destroyRef))
    .subscribe({
      error: (err: HttpErrorResponse) => {
        if (err.status !== 422 || !err.error?.errors) return;
        // { email: ["already in use"], "lines.0.sku": ["unknown SKU"] }
        for (const [path, messages] of Object.entries(err.error.errors)) {
          const ctrl = this.form.get(path);
          if (!ctrl) continue;
          ctrl.setErrors({ ...(ctrl.errors ?? {}), server: messages }); // merge, don't clobber client errors
          ctrl.valueChanges.pipe(take(1), takeUntilDestroyed(this.destroyRef)).subscribe(() => {
            const { server, ...rest } = ctrl.errors ?? {};
            ctrl.setErrors(Object.keys(rest).length ? rest : null); // clear server slot, keep others
          });
        }
        this.form.markAllAsTouched();
      },
    });
}
```

Server errors must clear on next edit, or the field stays invalid after the user fixes it. Merge with `ctrl.errors` to keep client validation in play.

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

### Conditional Validators

When a control's validators depend on a sibling (`shipTo.required` only when `pickup === false`), swap them at runtime and recompute without re-emitting:

```typescript
this.form.controls.pickup.valueChanges.pipe(takeUntilDestroyed()).subscribe((pickup) => {
  const shipTo = this.form.controls.shipTo;
  shipTo.setValidators(pickup ? [] : [Validators.required]);
  shipTo.updateValueAndValidity({ emitEvent: false });
});
```

Same call (`updateValueAndValidity({ emitEvent: false })`) applies after `addValidators` / `removeValidators`.

### CVA + Internal Validation

If a custom input enforces format (hex color, IBAN, phone), register it as a validator too via `NG_VALIDATORS` so parent forms see the error without re-implementing the check:

```typescript
providers: [
  { provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => HexInputComponent), multi: true },
  { provide: NG_VALIDATORS,     useExisting: forwardRef(() => HexInputComponent), multi: true },
],
// in class:
validate(ctrl: AbstractControl): ValidationErrors | null {
  return /^#[0-9a-f]{6}$/i.test(ctrl.value) ? null : { hex: true };
}
```

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

- `FormGroup` without a type parameter on non-trivial forms - loses `getRawValue()` typing
- `Validators.required` on a control that is only conditionally required - swap with `setValidators` based on a sibling
- `valueChanges.subscribe(...)` without `takeUntilDestroyed()` - or convert to `toSignal`
- Mixing template-driven and reactive on the same form
