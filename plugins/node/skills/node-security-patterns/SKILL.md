---
name: node-security-patterns
description: Node.js security - JWT, mass-assignment DTOs, prototype pollution, SSRF, file upload, webhook signatures, secrets, eval/vm prohibitions.
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, security, jwt, owasp, ssrf, prototype-pollution]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Canonical "build it right" security patterns for NestJS / Express. `task-node-review-security` delegates here and only flags deviations.

## When to Use

- Wiring auth (NestJS Passport JWT / Express `jose` or `jsonwebtoken`) or authz (Guards / middleware)
- Adding request DTOs / Zod schemas that touch user-supplied data
- Implementing file upload, webhook receivers, SSRF-exposed outbound HTTP, or `child_process` callers
- Setting up secrets / typed `ConfigService` with env validation
- Reviewing any code path that crosses an untrusted boundary

## Rules

- Every JWT verify call declares `algorithms: [...]` explicitly (`jsonwebtoken<9` accepted `alg: none` without an allowlist; keep the rule unconditional)
- Every request body has a DTO / Zod schema; whitelist mode strips unknown fields. Privilege fields are a **class**, not a list: any field the server assigns (ownership, tenancy, role, entitlement, price, status) is off the input contract entirely
- Authorization is checked per object, not per route: after loading the record, verify the actor owns or is scoped to it. A route guard proves who is calling, never what they may touch
- Passwords hashed with `argon2id` (or `bcrypt`); never a bare SHA. Compare with the library's `verify`, and hash a dummy on a missing user so the timing does not reveal account existence
- Never `Object.assign(target, userInput)`, `_.merge`, or spread untrusted keys onto framework / domain objects - prototype pollution
- Never `eval`, `new Function(string)`, `vm.runInNewContext`, `require(userInput)`, dynamic `import(userInput)` on user input; `vm2` is deprecated (CVEs)
- Outbound `fetch`/`axios` with user-controlled URL resolves the host and rejects RFC1918, link-local, `127.0.0.0/8`/`::1`, cloud metadata `169.254.169.254` (re-resolve at request time to defeat DNS rebinding)
- File uploads validated by magic bytes (`file-type`), not `mimetype` header; stored outside webroot; served with `Content-Disposition: attachment`
- Webhook signature compared with `crypto.timingSafeEqual` on the raw body (`bodyParser.raw`); never on parsed JSON. Sign the provider's actual signed string (Stripe `t.payload`, Slack `v0:t:body`), strip the scheme prefix (`sha256=`, `v0=`), and reject a timestamp outside a few minutes - a signature with no freshness check is replayable forever
- Secrets via typed `ConfigService` (NestJS) or Zod-validated env loader (Express); fail at startup on missing keys
- `child_process.execFile([...args])` arg array only - never `exec(string)`, never `shell: true` with user input
- `rejectUnauthorized: false` on TLS clients only in documented test fixtures
- `res.redirect(userInput)` validated against a same-origin / allowlist check

## Patterns

### JWT Signing and Verification

**NestJS (Passport):**

Pick the algorithm from the topology first: HS256 only when one service both signs and verifies; **RS256 whenever any other service verifies**, so the verifier holds only the public key. Publishing a public key makes the RS256-to-HS256 confusion attack live, which is why the `algorithms` allowlist below is load-bearing rather than hygiene.

```typescript
// auth.module.ts - RS256 (cross-service). For single-service HS256, swap the key pair for `secret:`.
JwtModule.registerAsync({
  useFactory: (config: ConfigService) => ({
    privateKey: config.getOrThrow('JWT_PRIVATE_KEY'),
    publicKey: config.getOrThrow('JWT_PUBLIC_KEY'),
    signOptions: { algorithm: 'RS256', expiresIn: '15m', issuer: 'api', audience: 'web' },
  }),
  inject: [ConfigService],
});

// jwt.strategy.ts - verifier holds the PUBLIC key only; allowlist must match the signer
super({
  jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
  secretOrKey: config.getOrThrow('JWT_PUBLIC_KEY'),   // the shared secret under HS256
  algorithms: ['RS256'],              // mandatory, and it is what blocks RS256->HS256 confusion
  issuer: 'api',
  audience: 'web',
});
```

**Express (`jose` preferred; `jsonwebtoken` acceptable with explicit allowlist):**

```typescript
// Bad - jsonwebtoken with no algorithm allowlist accepts alg:none on some shapes
const claims = jwt.verify(token, secret);

// Good - jose
const { payload } = await jwtVerify(token, key, {
  algorithms: ['HS256'],
  issuer: 'api',
  audience: 'web',
});
```

Access tokens 5-15 min; refresh tokens rotated and revocable (track `jti` in Redis/DB denylist). RS256 preferred cross-service (public-key verify, private-key sign separation).

### Mass-Assignment Whitelist DTOs

**NestJS - `ValidationPipe` global + DTO classes:**

```typescript
// main.ts
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,             // strip unknown fields
  forbidNonWhitelisted: true,  // 400 on unknown
  transform: true,             // instantiate DTO class
}));

// Bad - privilege field on input DTO
export class CreateOrderDto {
  @IsString() productId!: string;
  @IsInt() quantity!: number;
  @IsString() ownerId!: string;  // client overrides server-assigned owner
}

// Good - server-assigned fields off the input contract
export class CreateOrderDto {
  @IsString() productId!: string;
  @IsInt() @Min(1) quantity!: number;
}
// service: this.orders.create({ ...dto, ownerId: user.sub })
```

**Express - Zod with `.strict()`:**

```typescript
// Bad - .passthrough() or default behavior silently accepts unknown keys
const schema = z.object({ name: z.string(), email: z.string().email() });
prisma.user.create({ data: req.body });   // mass-assignment

// Good
const schema = z.object({ name: z.string(), email: z.string().email() }).strict();
const parsed = schema.parse(req.body);
prisma.user.create({ data: { name: parsed.name, email: parsed.email } });
```

Privilege fields (`role`, `isAdmin`, `ownerId`, `userId`, `tenantId`, `verified`) are server-set. Admin paths use a separate DTO/schema with explicit role guard.

### Prototype Pollution

```typescript
// Bad
Object.assign(target, JSON.parse(userInput));      // __proto__ pollutes Object.prototype
_.merge(config, req.query);                        // same
const opts = { ...defaults, ...req.body };         // poisons opts.__proto__

// Good - bounded surface
const allowed = ['name', 'email'] as const;
for (const k of allowed) if (k in req.body) target[k] = req.body[k];

// Good - prototype-less map for trusted keys
const map = Object.create(null);
```

`JSON.parse` has no prototype-pollution surface by itself; the danger is what code does with the result. `lodash.merge` is the most common live vector.

### SSRF Allowlist

Validating a hostname and then handing the raw URL to `fetch` does **not** work: `fetch` resolves again, so an attacker-controlled DNS record can answer public on your check and private on the real request. The address you approve has to be the address the socket dials, so the check belongs inside the connection.

```typescript
import { Agent } from 'undici';
import { lookup } from 'node:dns';

const BLOCKED = ['127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '::1/128', 'fc00::/7', 'fe80::/10'];
const isPublic = (ip: string) => !BLOCKED.some((c) => inCidr(ip, c));   // use `ip-address`/`netmask`, not string prefixes

const guardedAgent = new Agent({
  connect: {
    lookup: (hostname, opts, cb) =>
      lookup(hostname, { ...opts, all: true }, (err, addrs) => {
        if (err) return cb(err, '', 0);
        // every answer must be public - one private record in a round-robin set is enough to pivot
        const list = Array.isArray(addrs) ? addrs : [addrs];
        if (!list.every((a) => isPublic(a.address))) return cb(new Error('blocked'), '', 0);
        cb(null, list[0].address, list[0].family);      // dial the address we just approved
      }),
  },
});

async function safeFetch(rawUrl: string): Promise<Response> {
  const url = new URL(rawUrl);                          // throws on `\\evil`, unicode tricks
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('protocol');
  return fetch(url, { dispatcher: guardedAgent, redirect: 'manual', signal: AbortSignal.timeout(5_000) });
}
```

`redirect: 'manual'` is required: a public URL that 302s to `169.254.169.254` walks past any pre-flight check. Re-run `safeFetch` on the `Location` header, with a hop limit. Watch `URL` quirks: backslash, unicode, `::ffff:127.0.0.1` (IPv4-mapped IPv6), decimal and octal IP forms. Never echo the upstream status or body length back to the caller - that alone is a port scanner.

### File Upload Validation

```typescript
import { fileTypeFromBuffer } from 'file-type';
import path from 'node:path';

const ALLOWED_MIME = new Set(['image/jpeg', 'image/png', 'application/pdf']);
const UPLOAD_DIR = '/srv/uploads';

@Post('upload')
@UseInterceptors(FileInterceptor('file', { limits: { fileSize: 10 * 1024 * 1024 } }))
async upload(@UploadedFile() file: Express.Multer.File) {
  const type = await fileTypeFromBuffer(file.buffer);
  if (!type || !ALLOWED_MIME.has(type.mime)) throw new BadRequestException('type');

  const safeName = `${randomUUID()}.${type.ext}`;
  const target = path.resolve(UPLOAD_DIR, safeName);
  if (!target.startsWith(UPLOAD_DIR + path.sep)) throw new BadRequestException('traversal');
  await fs.writeFile(target, file.buffer);
}

@Get('upload/:id')
async serve(@Res() res: Response, @Param('id') id: string) {
  res.setHeader('Content-Disposition', 'attachment; filename="' + sanitize(id) + '"');
  // ... stream from UPLOAD_DIR with the same resolve+startsWith check
}
```

Trust magic bytes, not the `mimetype` header (client-supplied). Generate filenames server-side; never use raw user input as a path component.

### Webhook Signatures

```typescript
import { timingSafeEqual, createHmac } from 'node:crypto';

// NestJS bootstrap - enable rawBody so @Req() RawBodyRequest exposes req.rawBody
const app = await NestFactory.create(AppModule, { rawBody: true });

@Post('webhooks/stripe')
@HttpCode(200)
async stripe(@Req() req: RawBodyRequest<Request>, @Headers('stripe-signature') sig: string) {
  // rawBody is undefined when no registered parser matched the Content-Type - fail closed,
  // or an attacker sends text/plain and the HMAC is computed over an empty buffer
  if (!req.rawBody?.length) throw new UnauthorizedException();
  const { t, v1 } = parseStripeSig(sig);
  // Freshness first - a valid signature with no time bound replays forever
  if (Math.abs(Date.now() / 1000 - Number(t)) > 300) throw new UnauthorizedException();
  // Stripe signs `${timestamp}.${rawBody}` - hashing the body alone never matches
  const expected = createHmac('sha256', this.config.getOrThrow('STRIPE_WEBHOOK_SECRET'))
    .update(`${t}.`).update(req.rawBody!)    // raw bytes, not parsed JSON
    .digest('hex');
  const a = Buffer.from(expected), b = Buffer.from(v1);
  // timingSafeEqual throws on length mismatch - check first or a forged short sig becomes a 500
  if (a.length !== b.length || !timingSafeEqual(a, b)) throw new UnauthorizedException();
  // ... handle, keyed on the provider's event id so a replayed delivery is a no-op
}

// Express equivalent - mount raw parser only on the webhook path
app.use('/webhooks/stripe', express.raw({ type: '*/*', limit: '1mb' }));
```

`===` on hex strings leaks timing. JSON-parsing before verification breaks signature comparison (whitespace, key order). Prefer the SDK's `constructEvent` (Stripe) / `verify` (GitHub, Slack) helpers when available - they enforce raw-body + timing-safe internally.

### Secrets and Typed Config

**NestJS:**

```typescript
// config.schema.ts
export const ConfigSchema = z.object({
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
  STRIPE_WEBHOOK_SECRET: z.string().min(16),
});
export type Env = z.infer<typeof ConfigSchema>;

// config.module.ts
ConfigModule.forRoot({
  validate: (raw) => ConfigSchema.parse(raw),     // fails at startup on missing/malformed
  isGlobal: true,
});

// usage
this.config.getOrThrow<Env['JWT_SECRET']>('JWT_SECRET');
```

**Express:** load + validate at boot, then read from a frozen typed object.

```typescript
const env = ConfigSchema.parse(process.env);     // throws at startup
Object.freeze(env);
export { env };
```

Secrets come from Vault / AWS SM / GCP SM / Doppler; `.env` for local dev only and gitignored. Never read `process.env.X` in business logic - go through the validated object.

### `eval` / `new Function` / `vm` Prohibitions

Treat any of these as Critical when reachable from user input:

```typescript
// All prohibited on user input - any reachable path is Critical
eval(userInput);
new Function('return ' + userInput)();
vm.runInNewContext(userInput, sandbox);          // vm2 deprecated, CVEs
require(userInput);                              // dynamic require
await import(userInput);                         // dynamic ESM import
```

Allowlist a fixed string set if dynamic dispatch is genuinely required:

```typescript
const handlers = { invoice: handleInvoice, refund: handleRefund } as const;
// `handlers['constructor']` is truthy, so a truthiness check does NOT close the dispatch
if (!Object.hasOwn(handlers, type)) throw new BadRequestException();
await handlers[type as keyof typeof handlers](payload);
```

### Open Redirect / `child_process` / TLS

```typescript
// Bad
res.redirect(req.query.next as string);

// Bad - startsWith('/') check: bypassed by backslash normalization, e.g. /\evil.com
if (next.startsWith('/') && !next.startsWith('//')) res.redirect(next);

// Good - resolve against own origin exactly like the browser will, then compare origins
const target = new URL(String(req.query.next ?? '/'), env.APP_ORIGIN);
res.redirect(target.origin === env.APP_ORIGIN ? target.pathname + target.search : '/');

// Bad - shell injection
exec(`convert ${userInput} out.png`);

// Bad - no shell, but user input in argv position is still argument injection:
// a value starting with `-` becomes a flag (`-write /etc/...`, ffmpeg `-i` protocol tricks)
execFile('convert', [userInput, 'out.png']);

// Good - server-generated paths only, flags fixed, `--` terminator, bounded
execFile('convert', ['--', srcPath, '-resize', '100x100', outPath],
  { timeout: 10_000, maxBuffer: 8 << 20, env: {} });

// Bad - disables TLS verification globally
const agent = new https.Agent({ rejectUnauthorized: false });

// Good - never in production paths; test fixtures only with a comment
```

## Output Format

When authoring, emit one block per pattern applied. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one block per gap, reading `Change:` as the required fix rather than an applied one.

```
Pattern: {JWT | Authorization | Mass Assignment | Prototype Pollution | SSRF | File Upload | Webhook | Secrets | Eval | Open Redirect | Exec | TLS | Password Storage}
Surface: {file:line - controller/service/middleware, or the module being authored}
Change: {what was applied, or what must be}
Risk Mitigated: {auth bypass | broken object-level authorization | mass assignment | prototype pollution | SSRF | RCE | argument injection | path traversal | replay | secret exposure | timing oracle | account enumeration | open redirect | TLS bypass}
```

## Avoid

- `jsonwebtoken.verify(token, key)` without an `algorithms` allowlist
- DTOs / Zod schemas without `whitelist: true` / `.strict()` - mass-assignment vector
- `Object.assign(target, req.body)` or `lodash.merge` on user input
- `===` on signatures / tokens - use `crypto.timingSafeEqual` on equal-length buffers
- File-type validation by `mimetype` header
- SSRF allowlists that check the raw URL string instead of the resolved IP
- Reading secrets via raw `process.env.X` in business logic - go through validated config
- `vm2` (deprecated, CVEs); recommending `isolated-vm` without explicit justification
- `csurf` (deprecated) - recommend `csrf-csrf` or session-anti-CSRF
- Same-origin open redirects masquerading as "internal" - allowlist paths, not "starts with /"
