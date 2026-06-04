---
name: regression-artifact-scrub
description: PII / PCI scrubbing of traces, videos, screenshots, compose logs before upload as CI artifacts. Playwright masks plus pattern-based redaction.
metadata:
  category: testing
  tags: [regression, governance, pii, pci, ci-artifacts, security]
user-invocable: false
---

# Regression Artifact Scrub

`regression-data-isolation` Rule 5 enforces synthetic `acme-test-*` identifiers by convention. Nothing today scrubs the artifact. A scenario that reads prod-shaped fixtures records real-looking emails / card numbers / SSNs into a CI artifact retained for days. This skill closes that gap.

## When to Use

- During `regression-runner` teardown, just before upload to CI artifact storage.
- Always opt-in via `config.json#scrub.enabled: true`. Off by default; the convention-only baseline is what most projects want.

## Rules

1. **Two layers, both required when enabled.**
   - **Layer 1 (capture-time):** Playwright `mask` selectors hide DOM nodes from screenshots / videos / traces. The user marks sensitive elements with `data-sensitive` (or a project-specific attribute); the global config masks them.
   - **Layer 2 (post-capture):** pattern-based redaction sweeps `compose.log`, `line.log`, and trace JSON for known patterns (emails not under `*.acme-test.local`, card-number Luhn matches, JWT bodies). Replaces with `[REDACTED:<kind>]`.
2. **Allowlist of test-domain identifiers.** Anything matching `*@acme-test.local` (per `regression-data-isolation` convention) or `acme-test-*` IS allowed - it is by definition synthetic. The pattern list is configurable per project.
3. **Fail-open by default for missing patterns.** A pattern the regex did not catch slips through; the user is the gate. The skill writes a one-line summary into `summary.md`: `Scrub: N email matches, N card-number matches, N JWT body matches redacted.` So the user sees the volume of what was caught.
4. **Scrub before teardown,** not after. Volumes go with `down -v`; if we scrub after, we have to write into the artifact dir from outside the container - which means the unscrubbed bytes already left.
5. **Never modify the source DOM.** Layer 1 masks at capture time via Playwright; it does not edit page content.

## Patterns

### Playwright global config

```ts
// playwright.config.ts
export default defineConfig({
  use: {
    screenshot: {
      mode: "only-on-failure",
      mask: [/* per-test masks via expect.toHaveScreenshot({ mask: ... }) */],
    },
    video: { mode: "retain-on-failure" },
    trace: { mode: "retain-on-failure" },
  },
});
```

Per-test mask:

```ts
await expect(page).toHaveScreenshot("checkout.png", {
  mask: [
    page.locator("[data-sensitive]"),
    page.locator("input[type=password]"),
    page.locator(".credit-card-number"),
  ],
});
```

Per-step mask for video / trace:

```ts
await page.locator("[data-sensitive]").evaluate(el => el.setAttribute("aria-hidden", "true"));
```

### Pattern catalog

```
{
  "emailNonTest":      "\\b[a-zA-Z0-9._%+-]+@(?!acme-test\\.local)[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}\\b",
  "cardNumberLuhn":    "\\b(?:\\d[ -]?){12,18}\\d\\b",   # post-match Luhn check; only redact if it passes
  "jwtBody":           "\\beyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\b",
  "ssnUS":             "\\b\\d{3}-\\d{2}-\\d{4}\\b",
  "phoneE164":         "\\+?[1-9]\\d{6,14}\\b"
}
```

Project-specific extensions go in `.regression/config.json#scrub.patterns`. Each pattern needs a `kind` name used in `[REDACTED:<kind>]`.

### Scrub script

```bash
# .regression/scripts/scrub.sh - shipped by regression-artifact-scrub
set -euo pipefail
REPORTS="$1"
CONFIG=".regression/config.json"

# Read patterns from config; emit a sed-d redact script
node -e "
const cfg = require('$CONFIG');
if (!(cfg.scrub && cfg.scrub.enabled)) process.exit(0);
const pats = cfg.scrub.patterns || {};
for (const [kind, regex] of Object.entries(pats)) {
  console.log(\`s|\${regex}|[REDACTED:\${kind}]|g\`);
}
" > /tmp/scrub.sed

# Sweep compose.log and line.log
for f in "$REPORTS/compose.log" "$REPORTS/line.log"; do
  [ -f "$f" ] && sed -E -f /tmp/scrub.sed -i "$f"
done

# Trace.zip contents: extract, scrub network-resources/*.json, rezip
find "$REPORTS/traces" -name "*.zip" 2>/dev/null | while read -r zip; do
  tmp="$(mktemp -d)"
  ( cd "$tmp" && unzip -q "$zip" && \
    find . -name "*.txt" -o -name "*.json" | xargs -I{} sed -E -f /tmp/scrub.sed -i {} && \
    zip -qr "$zip" . )
  rm -rf "$tmp"
done
```

### Runner integration

In `regression-runner`'s teardown, before `down -v`:

```bash
.regression/scripts/scrub.sh "$REPORTS" || true   # fail-open: scrub failure does not block teardown
```

### Summary integration

`regression-report-format` reads `$REPORTS/.scrub-summary.json` (written by `scrub.sh`) and appends a single line under `## Run Metadata`:

```
- scrub: N emailNonTest, N cardNumberLuhn redacted
```

### Mask selectors as the primary defense

Layer 2 catches what slipped through Layer 1, but Layer 1 is structural - marking DOM nodes is the deterministic option. The skill recommends `data-sensitive` as the project-wide convention and surfaces uncovered patterns in the summary so the team adds masks over time.

## Output Format

- `.regression/scripts/scrub.sh` (committed) - the sweep.
- `.regression/config.json#scrub` schema:

  ```json
  {
    "scrub": {
      "enabled": true,
      "patterns": { "emailNonTest": "...", "cardNumberLuhn": "..." },
      "allowedDomains": ["acme-test.local"]
    }
  }
  ```

- `$REPORTS/.scrub-summary.json` per run with redaction counts per kind.

## Avoid

- Treating mask selectors alone as sufficient (DOM patterns drift; pattern redaction is the safety net).
- Blocking teardown on scrub failure (fail-open).
- Scrubbing in-place without first capturing the count - the user wants to know what was redacted.
- Adding scrub patterns globally that match test domains (`acme-test.local`) - exclude them via allowlist.
- Scrubbing `summary.md` itself - it should not contain PII (we control its content).
- Layer 2 only - DOM masking at capture time is faster and deterministic.
