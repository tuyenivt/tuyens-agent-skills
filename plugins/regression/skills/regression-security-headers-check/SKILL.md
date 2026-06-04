---
name: regression-security-headers-check
description: Security header assertions for outside-in regression - CSP / HSTS / X-Frame / Referrer-Policy / Permissions-Policy. Opt-in via flow.checks.
metadata:
  category: testing
  tags: [regression, security, headers, csp, hsts]
user-invocable: false
---

# Regression Security Headers Check

Catches regressions where a deploy strips or weakens a security header (CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy). Header presence + structural match against the expected policy.

## When to Use

- Flow has `checks:` containing `security-headers`.
- The user passes `--check security-headers` to `task-regression-scenario`.

## Rules

1. **Expected headers come from `flows.yaml#securityHeaders`.** No global defaults - what counts as "the policy" varies per surface (the marketing site does not need the same CSP as the dashboard).
2. **Structural compare, not byte equality.** CSP `default-src 'self'; script-src 'self' cdn.example` matches `default-src 'self' ; script-src cdn.example 'self'` (whitespace + directive order tolerant). HSTS compares `max-age` numerically with `>=` semantics; `includeSubDomains` and `preload` are exact-match flags.
3. **HTTPS-only headers (HSTS) skip on http://.** Local compose serves on http; HSTS assertions run only when the scenario hits an https origin OR the flow sets `securityHeaders: { hstsRequiredOnHttp: true }`. The default for local-build is skip; CI under `pinned-images` against an https origin enforces.
4. **Missing header is a `real-bug`.** Weakening (e.g. `default-src 'self'` -> `default-src '*'`) is `real-bug`. Strengthening (e.g. added `Permissions-Policy: geolocation=()`) is allowed - the assertion is `at-least-as-strict-as`, not `equals`.
5. **One assertion per response,** not per page navigation. Browser flows assert on `page.waitForResponse` for the document response; API flows assert on the API response.

## Patterns

### `securityHeaders:` flow field

```yaml
- name: dashboard-load
  checks: [security-headers]
  securityHeaders:
    required:
      Content-Security-Policy: "default-src 'self'; script-src 'self' cdn.example"
      Strict-Transport-Security: "max-age=31536000; includeSubDomains"
      X-Frame-Options: "DENY"
      Referrer-Policy: "strict-origin-when-cross-origin"
    forbidden:
      Server: ".*"               # regex - any value -> fail (don't leak server software)
    hstsRequiredOnHttp: false
```

### Helper signature

```ts
import { assertSecurityHeaders } from "../../fixtures/security-headers";
// helper shipped by this skill at .regression/fixtures/security-headers/index.ts

await page.goto("/dashboard");
const resp = await page.waitForResponse(r => r.url().endsWith("/dashboard") && r.status() === 200);
const result = assertSecurityHeaders(resp.headers(), flowSecurityHeaders, { isHttps: page.url().startsWith("https") });
expect(result.violations, JSON.stringify(result.violations)).toEqual([]);
```

`result.violations` is `Array<{ header, expected, got, kind: "missing" | "weakened" | "forbidden-present" }>`.

### CSP structural compare

```ts
// "default-src 'self'; script-src 'self' cdn.example" matches
// "script-src cdn.example 'self'; default-src 'self'"
```

The helper parses CSP into `{ directive: Set<source> }` and asserts each expected directive's sources are a subset of the actual.

### Header-name case insensitivity

HTTP headers are case-insensitive. The helper lowercases all names before compare; the policy file may use any case.

### Forbidden regex

`forbidden:` matches the entire header value as a regex. Anchors implicit. `Server: ".*"` means any value of `Server` fails. Use this to detect leaked server software / version banners.

## Output Format

- JUnit failure message lists each violation in structured form.
- `regression-report-format` clusters by `(header, kind)` so "all routes lost HSTS" clusters as one.

## Avoid

- Exact-string CSP compare (whitespace / order false positives).
- Asserting HSTS on http:// in local-build (always fails - the policy is correct but the transport is wrong).
- Global default policy - varies per surface.
- Failing when the response gains a new strengthening header.
- Treating `Server` / `X-Powered-By` leakage as low severity (it's `real-bug`).
