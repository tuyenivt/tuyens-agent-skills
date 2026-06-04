---
name: regression-a11y-check
description: Playwright + axe accessibility scan for browser flows. Opt-in via flow.checks contains "a11y". Asserts WCAG 2.1 AA, surfaces failed rules per page.
metadata:
  category: testing
  tags: [regression, accessibility, a11y, axe, wcag]
user-invocable: false
---

# Regression A11y Check

Catches accessibility regressions at scenario time: missing labels, contrast violations, role mismatches. Browser flows only.

## When to Use

- Flow `kind: browser | mixed` AND `checks:` contains `a11y`.
- The user passes `--check a11y` to `task-regression-scenario`.

## Rules

1. **Browser flows only.** API flows can not be a11y-scanned. The skill aborts emission when applied to `kind: api`.
2. **WCAG 2.1 AA is the default rule set.** Configurable per flow via `a11y: { tags: [wcag21a, wcag21aa] }`. Stricter sets (`best-practice`, `experimental`) opt-in only.
3. **Disable list per flow,** not global. A flow with a known false positive declares `a11y: { disable: ["color-contrast"] }`; the disabled rule names appear in the report so they cannot rot.
4. **One scan per `@smoke`** after the golden-path assertion succeeds. Negative-path tests do not scan (they're asserting on the error surface, which is allowed to be ugly).
5. **Failure is a `real-bug` verdict.** A11y regressions ship to real users; they are not flake.

## Patterns

### Scenario emission

```ts
import AxeBuilder from "@axe-core/playwright";

// A11Y (regression-a11y-check)
const a11y = await new AxeBuilder({ page })
  .withTags(["wcag21a", "wcag21aa"])
  .disableRules(["color-contrast"])   // from flow.a11y.disable
  .analyze();
expect(a11y.violations, JSON.stringify(a11y.violations.map(v => v.id))).toEqual([]);
```

The `JSON.stringify(...)` second arg surfaces failed rule names in JUnit so failure clustering groups by `(error-class, rule-id-set)`.

### Per-page scans for multi-step browser flows

```ts
// Step 1: scan after navigate
await pom.goto();
const homeScan = await new AxeBuilder({ page }).analyze();
expect(homeScan.violations).toEqual([]);

// Step 2: scan after action (the surface that actually changed)
await pom.placeOrder();
const checkoutScan = await new AxeBuilder({ page }).analyze();
expect(checkoutScan.violations).toEqual([]);
```

The skill emits one `AxeBuilder` scan per `observableOutcome` entry that mentions a UI surface ("UI shows 'Thank you' screen" -> scan after that surface renders).

### `a11y:` flow field shape

```yaml
- name: order-checkout-happy
  checks: [a11y]
  a11y:
    tags: [wcag21a, wcag21aa]    # default
    disable: []                   # opt-in suppression list, one rule-id per line
```

### Suppression entries decay

The plan workflow (`task-regression-plan`) renders `a11y.disable:` entries verbatim in the `Additional fields` row so they are visible during sign-off. Long-standing suppressions become a sign-off conversation; nothing in this skill auto-expires them.

## Output Format

- Per-flow JUnit failures with rule-id list in the message.
- `regression-report-format` reads the rule-id set to cluster by it.
- `Additional fields` in `task-regression-plan` lists `a11y.disable:` entries verbatim.

## Avoid

- A11y scans on `kind: api` (no DOM).
- Disabling rules globally - keep suppression local to the flow with a comment.
- Scanning every step in a long flow without intent - one scan per UI-state-change observable.
- Using `axe-core` directly instead of `@axe-core/playwright` (we want the Playwright integration's page handle, not a manual `document` query).
- `best-practice` / `experimental` tags by default - they fire on near-misses that aren't WCAG.
