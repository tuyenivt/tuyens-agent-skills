---
name: node-security-patterns
description: Node.js security - JWT, mass-assignment DTOs, prototype pollution, SSRF, file upload, webhook signatures, secrets, eval/vm prohibitions.
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, security, jwt, owasp, ssrf, prototype-pollution]
user-invocable: false
---

> Load `Use skill: stack-detect` first; the detected framework picks the NestJS or the Express variant of each pattern (both when `unknown`) and surfaces only in the `**Stack:**` line above the blocks.

Canonical "build it right" security patterns for NestJS / Express. `task-node-review-security` delegates here and only flags deviations.

## When to Use

- Wiring auth (NestJS Passport JWT / Express `jose` or `jsonwebtoken`) or authz (Guards / middleware)
- Adding request DTOs / Zod schemas that touch user-supplied data
- Implementing file upload or import, webhook receivers and senders, SSRF-exposed outbound HTTP, or `child_process` callers
- Setting up secrets / typed `ConfigService` with env validation
- Reviewing any code path that crosses an untrusted boundary

## Rules

- Every JWT verify call declares `algorithms: [...]` explicitly - unconditional, and the only guard when the key comes from a provider or JWKS
- Every request body has a DTO / Zod schema, and the handler writes the **parsed** result, never the raw body. Privilege fields are a **class**, not a list: any field the server assigns (ownership, tenancy, role, entitlement, price, status) is off the input contract entirely
- Authorization is checked per object, not per route: load the record scoped to the actor (`where: { id, ownerId: user.sub }`) and answer 404 when it is not theirs. A route guard proves who is calling, never what they may touch
- Passwords hashed with `argon2id` (or `bcrypt`, which truncates input at 72 bytes); never a bare SHA. Compare with `argon2.verify(hash, pw)` / `bcrypt.compare(pw, hash)` (opposite argument orders), and compare against a precomputed dummy hash when the user is missing so the timing does not reveal account existence
- Untrusted keys never reach a recursive merge or path setter (prototype pollution), `Object.assign` onto a domain object (prototype re-parenting), or a spread onto a persisted object (mass assignment)
- Never `eval`, `new Function(string)`, `vm.runInNewContext`, `require(userInput)`, dynamic `import(userInput)` on user input; `vm2` and other in-process JS sandboxes have a long record of escapes and are never a security boundary
- Outbound requests to a user-controlled URL go through the SSRF guard below: every resolved address and every IP literal is checked, at connect time, against the blocked ranges, and redirects are followed manually
- File uploads validated by magic bytes (`file-type`), not the `mimetype` header; stored outside webroot under a server-generated name; served with `Content-Disposition: attachment`
- Webhook receivers verify the provider's actual scheme on the raw body (table below), compare with `crypto.timingSafeEqual` on equal-length buffers, bound freshness where the provider signs a timestamp, and dedupe on the delivery / event id everywhere
- Secrets via typed `ConfigService` (NestJS) or a Zod-validated env loader (Express); fail at startup on missing keys
- `child_process.execFile(absoluteBinary, [...args])` only - never `exec(string)`, never `shell: true` with user input
- `rejectUnauthorized: false` on TLS clients only in documented test fixtures
- A redirect target from user input resolves against the app's own origin and is emitted as the full URL only when the origins match
- Errors never echo internals (message of an unknown error, stack, SQL) to the client

## Patterns

### JWT Signing and Verification

Pick the algorithm from the topology first: HS256 only when one service both signs and verifies; **RS256 whenever any other service verifies**, so the verifier holds only the public key.

```typescript
// auth.module.ts - RS256 (cross-service). For single-service HS256, swap the key pair for `secret:`.
JwtModule.registerAsync({
  useFactory: (config: ConfigService<Env, true>) => ({
    privateKey: config.getOrThrow('JWT_PRIVATE_KEY'),
    publicKey: config.getOrThrow('JWT_PUBLIC_KEY'),
    signOptions: { algorithm: 'RS256', expiresIn: '15m', issuer: 'api', audience: 'web' },
    verifyOptions: { algorithms: ['RS256'], issuer: 'api', audience: 'web' },   // JwtService.verify() calls too
  }),
  inject: [ConfigService],
});

// jwt.strategy.ts - the verifier holds the PUBLIC key only; the allowlist matches the signer
super({
  jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
  secretOrKey: config.getOrThrow('JWT_PUBLIC_KEY'),   // the shared secret under HS256
  algorithms: ['RS256'],
  issuer: 'api',
  audience: 'web',
});
```

**Express (`jose` preferred; `jsonwebtoken` acceptable with an explicit allowlist):**

```typescript
// Bad - no allowlist. jsonwebtoken <= 8.5.1 accepted alg:none when the key resolved falsy
const claims = jwt.verify(token, secret);

// Good - jose
const { payload } = await jwtVerify(token, key, { algorithms: ['HS256'], issuer: 'api', audience: 'web' });
```

Access tokens 5-15 min; refresh tokens rotated and revocable (track `jti` in Redis/DB denylist). A second service that must verify these tokens gets the public key (or a JWKS endpoint) and its own `audience`.

### Object-Level Authorization

```typescript
// Bad - any authenticated caller can read any order by id
return this.prisma.order.findUnique({ where: { id } });

// Good - scoped load; not-theirs and not-found are the same 404
const order = await this.prisma.order.findFirst({ where: { id, tenantId: user.tenantId } });
if (!order) throw new NotFoundException();
```

The same applies to writes (`updateMany({ where: { id, ownerId } })` and check the count), aggregates (a summary endpoint filters by tenant), and admin routes (a role guard plus the scope).

### Mass-Assignment Whitelist DTOs

**NestJS - `ValidationPipe` global + DTO classes:**

```typescript
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,             // strip unknown fields
  forbidNonWhitelisted: true,  // 400 on unknown
  transform: true,
}));

// Bad - privilege fields on the input DTO
export class CreateOrderDto {
  @IsString() productId!: string;
  @IsInt() quantity!: number;
  @IsString() ownerId!: string;    // client overrides the server-assigned owner
  @IsNumber() price!: number;      // client sets its own price
}

// Good - server-assigned fields off the input contract
export class CreateOrderDto {
  @IsString() productId!: string;
  @IsInt() @Min(1) quantity!: number;
}
// service: price from the catalog, owner from the token
```

**Express - Zod:**

```typescript
// Bad - validated, then the raw body is written anyway
schema.parse(req.body);
prisma.user.update({ where: { id }, data: req.body });

// Good - write the parsed result, field by field
const parsed = schema.parse(req.body);   // default mode strips unknown keys; .strict() makes parse throw on them - map ZodError to 400
prisma.user.update({ where: { id }, data: { name: parsed.name, email: parsed.email } });
```

Privilege fields (`role`, `isAdmin`, `ownerId`, `userId`, `tenantId`, `verified`, `price`, `status`) are server-set. Admin paths use a separate DTO/schema with an explicit role guard.

### Prototype Pollution and Re-Parenting

```typescript
// Bad - a recursive merge or path setter walks "__proto__" / "constructor" into Object.prototype
deepMerge(config, JSON.parse(userInput));
setPath(obj, req.body.path, req.body.value);      // path "__proto__.isAdmin"

// Bad - Object.assign uses [[Set]]: an own "__proto__" key from JSON.parse re-parents `user`
Object.assign(user, JSON.parse(userInput));        // user now inherits attacker props

// Good - bounded surface, own keys only
const allowed = ['name', 'email'] as const;
for (const k of allowed) if (req.body && Object.hasOwn(req.body, k)) target[k] = req.body[k];

// Good - prototype-less map for untrusted keys
const map = Object.create(null);
```

Object spread (`{ ...req.body }`) defines own properties and pollutes nothing - its hazard is mass assignment, and a latent own `"__proto__"` key that a later merge will act on. Current lodash guards `merge` / `set` / `defaultsDeep` against these keys and Express's `qs` drops `__proto__` by default, so the live vectors are hand-rolled recursive merges and path setters - and any library path function (`set`, `unset`, `omit`) handed a user-controlled path; keep lodash current.

### SSRF Guard

Validating a hostname and then handing the raw URL to `fetch` does **not** work: `fetch` resolves again, so a DNS record can answer public on your check and private on the real request. The address you approve has to be the address the socket dials, and an IP literal never reaches DNS at all.

```typescript
import { Agent, fetch } from 'undici';               // fetch and dispatcher from the same undici
import { lookup } from 'node:dns';
import { isIP } from 'node:net';
import ipaddr from 'ipaddr.js';

// unicast only - rejects loopback, private, link-local (incl. 169.254.169.254), CGNAT, unspecified,
// multicast, reserved; process() unmaps ::ffff:a.b.c.d to IPv4 first
const isPublic = (ip: string) => ipaddr.process(ip).range() === 'unicast';

const guardedAgent = new Agent({
  connect: {
    lookup: (hostname, opts, cb) =>
      lookup(hostname, { ...opts, all: true }, (err, addrs) => {
        if (err) return cb(err, []);
        const list = addrs as { address: string; family: number }[];
        // every answer must be public - one private record in a round-robin set is enough to pivot
        if (!list.every((a) => isPublic(a.address))) return cb(new Error('blocked'), []);
        if (opts.all) return cb(null, list);                     // Node 20+ autoSelectFamily asks for all
        cb(null, list[0].address, list[0].family);
      }),
  },
});

async function safeFetch(rawUrl: string, hops = 3): Promise<Response> {
  const url = new URL(rawUrl);                       // normalises (backslash -> slash, IDN -> punycode); check the parsed URL
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('protocol');
  const host = url.hostname.replace(/^\[|\]$/g, '');
  if (isIP(host) && !isPublic(host)) throw new Error('blocked');   // IP literals skip lookup entirely
  const res = await fetch(url, { dispatcher: guardedAgent, redirect: 'manual', signal: AbortSignal.timeout(5_000) });
  const next = res.headers.get('location');
  if (res.status >= 300 && res.status < 400 && next) {
    await res.body?.cancel();                          // an unread body holds the connection
    if (hops === 0) throw new Error('too many redirects');
    return safeFetch(new URL(next, url).href, hops - 1);          // re-validate every hop
  }
  return res;
}
```

`URL` normalises decimal and octal IPv4 (`http://2130706433/` becomes `127.0.0.1`), which the literal check then catches. Never echo the upstream status, headers, or body back to the caller - that alone is a port scanner; report delivered / failed.

### Outbound Webhooks (sending)

Sign what you send so customers can verify it: `HMAC-SHA256(endpointSecret, `${timestamp}.${rawBody}`)` in a header carrying the timestamp, a per-endpoint secret shown once and rotatable (two valid secrets during rotation), delivery through the SSRF guard above, and the delivery id in a header for their dedupe. A "send test event" button is the same path with a test payload.

### File Upload and Import

```typescript
import { fileTypeFromBuffer } from 'file-type';     // ESM-only since v17 - a CommonJS build needs Node 20.19+ / 22.12+ require(esm) or file-type@16 (FileType.fromBuffer)
import { randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';

const ALLOWED_MIME = new Set(['image/jpeg', 'image/png', 'application/pdf']);
const UPLOAD_DIR = '/srv/uploads';

@Post('upload')
@UseInterceptors(FileInterceptor('file', { limits: { fileSize: 10 * 1024 * 1024 } }))
async upload(@UploadedFile() file: Express.Multer.File) {
  const type = await fileTypeFromBuffer(file.buffer);
  if (!type || !ALLOWED_MIME.has(type.mime)) throw new BadRequestException('type');
  const target = path.resolve(UPLOAD_DIR, `${randomUUID()}.${type.ext}`);
  if (!target.startsWith(UPLOAD_DIR + path.sep)) throw new BadRequestException('traversal');
  await writeFile(target, file.buffer);
}
```

Text formats (CSV, JSON) have no magic bytes: enforce the size limit, parse as a stream with a row cap, validate every row with the schema, and reject the file on the first invalid row rather than importing part of it. A CSV the app later **exports** neutralises cells beginning with `=`, `+`, `-`, `@`, tab, or CR (prefix `'`) - formula injection when a user opens it in a spreadsheet.

### Webhook Signatures (receiving)

| Provider | What is signed | Header | Freshness | Replay |
|----------|----------------|--------|-----------|--------|
| Stripe | `${t}.${rawBody}`, HMAC-SHA256 hex | `Stripe-Signature: t=..,v1=..` (several `v1` during a secret roll) | reject `t` older than 5 min | dedupe on `event.id` |
| Slack | `v0:${timestamp}:${rawBody}` | `X-Slack-Signature: v0=..` + `X-Slack-Request-Timestamp` | 5 min | dedupe on `event_id` |
| GitHub | `rawBody`, HMAC-SHA256 | `X-Hub-Signature-256: sha256=..` | none signed | dedupe on `X-GitHub-Delivery` |
| Twilio | form bodies: full public URL + sorted **parsed** params, HMAC-SHA1 base64; JSON bodies: the URL incl. `bodySHA256`, plus the SHA-256 of the raw body | `X-Twilio-Signature` | none signed | dedupe on `I-Twilio-Idempotency-Token` (status callbacks repeat `MessageSid`) |
| Plaid | an ES256 JWT, not an HMAC: verify it with the JWK from `/webhook_verification_key/get` (by `kid`), check `iat` within 5 min, and compare its `request_body_sha256` claim with the SHA-256 of the raw body | `Plaid-Verification` | `iat` 5 min | no delivery id: dedupe on `request_body_sha256` and keep handlers idempotent |

Prefer the SDK's helper: Stripe `stripe.webhooks.constructEvent`, Slack `verifySlackRequest` (`@slack/bolt`), GitHub `verify` (`@octokit/webhooks-methods`), Twilio `twilio.validateRequest` / `validateRequestWithBody`, Plaid `/webhook_verification_key/get` + `jose`. Hand-rolled:

```typescript
@Public()
@Post('webhooks/stripe')
@HttpCode(200)
async stripe(@Req() req: RawBodyRequest<Request>, @Headers('stripe-signature') sig: string) {
  // rawBody needs NestFactory.create(AppModule, { rawBody: true }); it is also undefined when no parser
  // matched the Content-Type - fail closed
  if (!req.rawBody?.length || !sig) throw new UnauthorizedException();
  const parts = sig.split(',').map((p) => p.split('=', 2) as [string, string]);
  const t = parts.find(([k]) => k === 't')?.[1];
  const v1s = parts.filter(([k]) => k === 'v1').map(([, v]) => v);
  if (!t || Math.abs(Date.now() / 1000 - Number(t)) > 300) throw new UnauthorizedException();
  const expected = createHmac('sha256', this.config.getOrThrow('STRIPE_WEBHOOK_SECRET'))
    .update(`${t}.`).update(req.rawBody)               // raw bytes, not parsed JSON
    .digest('hex');
  const a = Buffer.from(expected);
  // timingSafeEqual throws on length mismatch - check first; accept any v1 (secret rotation)
  if (!v1s.some((v) => { const b = Buffer.from(v); return b.length === a.length && timingSafeEqual(a, b); })) {
    throw new UnauthorizedException();
  }
  // ... handle, keyed on event.id so a replayed delivery is a no-op
}

// Express - the raw parser on the webhook path, mounted BEFORE app.use(express.json())
app.use('/webhooks/stripe', express.raw({ type: '*/*', limit: '1mb' }));
```

A signed download link (`/statements/:id?exp=..&sig=..`) is the same shape: `HMAC(secret, `${id}.${exp}`)`, `timingSafeEqual`, reject an expired `exp`.

### Secrets and Typed Config

```typescript
// config.schema.ts
export const ConfigSchema = z.object({
  DATABASE_URL: z.string().url(),
  JWT_PRIVATE_KEY: z.string().startsWith('-----BEGIN'),
  JWT_PUBLIC_KEY: z.string().startsWith('-----BEGIN'),
  STRIPE_WEBHOOK_SECRET: z.string().min(16),
});
export type Env = z.infer<typeof ConfigSchema>;

// NestJS
ConfigModule.forRoot({ validate: (raw) => ConfigSchema.parse(raw), isGlobal: true });

// Express - parse once at boot, then read from the frozen object
export const env = Object.freeze(ConfigSchema.parse(process.env));
```

Secrets come from Vault / AWS SM / GCP SM / Doppler; `.env` for local dev only and gitignored. Business logic reads the validated object, never the raw environment.

### `eval` / `new Function` / `vm` Prohibitions

```typescript
// All prohibited on user input - any reachable path is Critical
eval(userInput);
new Function('return ' + userInput)();
vm.runInNewContext(userInput, sandbox);          // vm2 deprecated, CVEs
require(userInput);
await import(userInput);

// Allowlist a fixed dispatch table
const handlers = { invoice: handleInvoice, refund: handleRefund } as const;
// `handlers['constructor']` is truthy, so a truthiness check does NOT close the dispatch
if (!Object.hasOwn(handlers, type)) throw new BadRequestException();
await handlers[type as keyof typeof handlers](payload);
```

### Injection

A user-selectable sort column or table name goes through a fixed map (`const SORT = { date: 'entry.createdAt', amount: 'entry.amount' } as const`), never into `orderBy()` / `raw()` / a template string; values go through bound parameters (`$1`, `:name`, Prisma tagged `$queryRaw`), never `$queryRawUnsafe` with interpolation.

### Open Redirect / `child_process` / TLS

```typescript
// Bad - startsWith('/') check: bypassed by backslash normalisation, e.g. /\evil.com
if (next.startsWith('/') && !next.startsWith('//')) res.redirect(next);

// Good - resolve against own origin exactly like the browser will, compare origins, emit the full URL
// (a pathname can be '//evil.com' after resolving '/.//evil.com' - never emit it bare)
const target = new URL(String(req.query.next ?? '/'), env.APP_ORIGIN);
res.redirect(target.origin === env.APP_ORIGIN ? target.href : '/');

// Bad - shell injection
exec(`convert ${userInput} out.png`);

// Good - absolute binary, server-generated paths with explicit format prefixes from the
// magic-byte-verified type (ImageMagick honours no "--" and reads coder prefixes like msl: /
// ephemeral: from bare paths), bounded. ImageMagick 7: /usr/bin/magick; 6: /usr/bin/convert
const coder = type.ext === 'jpg' ? 'jpeg' : type.ext;
execFile('/usr/bin/magick', [`${coder}:${srcPath}`, '-resize', '100x100', `png:${outPath}`],
  { timeout: 10_000, maxBuffer: 8 << 20 });
// and restrict coders in ImageMagick's policy.xml

// Bad - disables TLS verification for every request through this agent
const agent = new https.Agent({ rejectUnauthorized: false });
// Bad - disables it process-wide: NODE_TLS_REJECT_UNAUTHORIZED=0
```

### Password Storage

```typescript
const DUMMY = await argon2.hash('dummy-password', { type: argon2.argon2id });   // once, at boot
const user = await users.findByEmail(email);
const ok = await argon2.verify(user?.passwordHash ?? DUMMY, password);         // same work either way
if (!user || !ok) throw new UnauthorizedException('invalid credentials');       // one message for both
```

### Error Disclosure

The global filter / terminal error middleware (`node-exception-handling`) answers unknown errors with a fixed body (`{ error: 'internal' }`) and logs the detail; never `err.message`, `err.stack`, or a driver error in a response, and never distinct messages for "no such user" and "wrong password".

### CSRF

Cookie-authenticated routes that change state need CSRF protection: `SameSite=Lax` or `Strict` session cookies plus a double-submit token (`csrf-csrf` `doubleCsrf({ getSecret, getSessionIdentifier: (req) => req.session.id })` (csrf-csrf v4 binds tokens to the session)). `csurf` is deprecated. Bearer-token APIs are not CSRF-exposed.

## Output Format

When authoring, emit the `**Stack:**` line, then one block per pattern applied plus the code; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the blocks. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, the output opens with the `**Stack:**` line, then each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines and then `Pattern:` and `Risk Mitigated:` only - the heading is the surface and `Fix:` is the change. `[Must]` first; `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. One finding per defect at one site; related sub-defects at the same site (a webhook's scheme, freshness, and dedupe) are one finding. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings.

```
**Stack:** {NestJS | Express 4 | Express 5 | unknown (NestJS and Express shown)} + {Passport JWT | jose | jsonwebtoken | none - no JWT surface}

Pattern: {JWT | Authorization | Mass Assignment | Prototype Pollution | SSRF | File Upload | File Import | Webhook Receiver | Webhook Sender | Signed Link | Secrets | Eval | Injection | Open Redirect | Exec | TLS | Password Storage | CSRF | Error Disclosure}

Surface: {file:line - controller/service/middleware, or the module being authored}

Change: {what was applied, or what must be}

Risk Mitigated: {auth bypass | broken object-level authorization | mass assignment | prototype pollution | SSRF | RCE | argument injection | SQL injection | path traversal | replay | forgery | secret exposure | timing oracle | account enumeration | open redirect | TLS bypass | CSRF | formula injection | resource exhaustion | information disclosure}
```

## Avoid

- `jsonwebtoken.verify(token, key)` without an `algorithms` allowlist
- Writing `req.body` after validating it, or `.passthrough()` schemas on persisted input
- `Object.assign(target, req.body)` or a recursive merge on user input
- `===` on signatures / tokens - use `crypto.timingSafeEqual` on equal-length buffers
- File-type validation by `mimetype` header
- SSRF allowlists that check the raw URL string instead of the resolved address
- Reading secrets from the raw environment in business logic - go through validated config
- `vm2` or any in-process JS sandbox as a security boundary
- `csurf` (deprecated)
- A redirect check on "starts with /" - resolve against your own origin and compare origins
