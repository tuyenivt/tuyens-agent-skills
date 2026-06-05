---
name: node-security-patterns
description: Node.js security - JWT, mass-assignment DTOs, prototype pollution, SSRF, file upload, webhook signatures, secrets, eval/vm prohibitions.
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, security, jwt, owasp, ssrf, prototype-pollution]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

For prototype-pollution and request-body validation specifics under NestJS / Express, this skill is the canonical owner. The security review workflow (`task-node-review-security`) delegates here for "build it right" patterns and only flags deviations.

## When to Use

- Wiring auth (NestJS Passport JWT / Express `jose` or `jsonwebtoken`) or authz (Guards / middleware)
- Adding request DTOs / Zod schemas that touch user-supplied data
- Implementing file upload, webhook receivers, SSRF-exposed outbound HTTP, or `child_process` callers
- Setting up secrets / typed `ConfigService` with env validation
- Reviewing any code path that crosses an untrusted boundary

## Rules

- Every JWT verify call declares `algorithms: [...]` explicitly - implicit allowlists accept `alg: none` on some token shapes
- Every request body has a DTO / Zod schema; whitelist mode strips unknown fields and rejects privilege fields (`role`, `ownerId`, `tenantId`, `isAdmin`)
- Never `Object.assign(target, userInput)`, `_.merge`, or spread untrusted keys onto framework / domain objects - prototype pollution
- Never `eval`, `new Function(string)`, `vm.runInNewContext`, `require(userInput)`, dynamic `import(userInput)` on user input; `vm2` is deprecated (CVEs)
- Outbound `fetch`/`axios` with user-controlled URL resolves the host and rejects RFC1918, link-local, `127.0.0.0/8`/`::1`, cloud metadata `169.254.169.254` (re-resolve at request time to defeat DNS rebinding)
- File uploads validated by magic bytes (`file-type`), not `mimetype` header; stored outside webroot; served with `Content-Disposition: attachment`
- Webhook signature compared with `crypto.timingSafeEqual` on the raw body (`bodyParser.raw`); never on parsed JSON
- Secrets via typed `ConfigService` (NestJS) or Zod-validated env loader (Express); fail at startup on missing keys
- `child_process.execFile([...args])` arg array only - never `exec(string)`, never `shell: true` with user input
- `rejectUnauthorized: false` on TLS clients only in documented test fixtures
- `res.redirect(userInput)` validated against a same-origin / allowlist check

## Patterns

### JWT Signing and Verification

**NestJS (Passport):**

```typescript
// auth.module.ts - rotation-friendly secret provider
JwtModule.registerAsync({
  useFactory: (config: ConfigService) => ({
    secret: config.getOrThrow('JWT_SECRET'),
    signOptions: { algorithm: 'HS256', expiresIn: '15m', issuer: 'api', audience: 'web' },
  }),
  inject: [ConfigService],
});

// jwt.strategy.ts - explicit algorithm allowlist + iss/aud verification
super({
  jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
  secretOrKey: config.getOrThrow('JWT_SECRET'),
  algorithms: ['HS256'],              // mandatory - or ['RS256'] for asymmetric
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

```typescript
import { lookup } from 'node:dns/promises';
import net from 'node:net';

const BLOCKED_CIDRS = ['127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16'];

async function safeFetch(rawUrl: string): Promise<Response> {
  const url = new URL(rawUrl);                          // throws on `\\evil`, unicode tricks
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('protocol');

  const { address } = await lookup(url.hostname);       // re-resolve - defeats DNS rebinding
  if (net.isIPv4(address) && BLOCKED_CIDRS.some(c => inCidr(address, c))) throw new Error('blocked');
  if (address === '::1' || address.startsWith('fe80:') || address.startsWith('fd00:ec2:')) throw new Error('blocked');

  return fetch(rawUrl, { signal: AbortSignal.timeout(5_000) });
}
```

Re-resolve at request time. Watch `URL` quirks: backslash, unicode, `::ffff:127.0.0.1` (IPv4-mapped IPv6).

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

// NestJS - raw body for the route
@Module({ /* configure ConsumerOptions with bodyParser: false on this route, or use rawBody: true */ })

@Post('webhooks/stripe')
@HttpCode(200)
async stripe(@Req() req: RawBodyRequest<Request>, @Headers('stripe-signature') sig: string) {
  const expected = createHmac('sha256', this.config.getOrThrow('STRIPE_WEBHOOK_SECRET'))
    .update(req.rawBody!)                    // raw bytes, not parsed JSON
    .digest('hex');
  const got = parseStripeSig(sig).v1;
  if (!timingSafeEqual(Buffer.from(expected), Buffer.from(got))) throw new UnauthorizedException();
  // ... handle
}
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
const h = handlers[type as keyof typeof handlers];
if (!h) throw new BadRequestException();
await h(payload);
```

### Open Redirect / `child_process` / TLS

```typescript
// Bad
res.redirect(req.query.next as string);

// Good - relative path, no protocol-relative
const next = String(req.query.next ?? '/');
if (!next.startsWith('/') || next.startsWith('//')) res.redirect('/');
else res.redirect(next);

// Bad - shell injection
exec(`convert ${userInput} out.png`);

// Good - arg array, no shell
execFile('convert', [userInput, 'out.png']);     // allowlist binaries

// Bad - disables TLS verification globally
const agent = new https.Agent({ rejectUnauthorized: false });

// Good - never in production paths; test fixtures only with a comment
```

## Output Format

```
Pattern: {JWT | Mass Assignment | Prototype Pollution | SSRF | File Upload | Webhook | Secrets | Eval | Open Redirect | Exec | TLS}
Surface: {file:line - controller/service/middleware}
Change: {what was applied}
Risk Mitigated: {auth bypass | mass assignment | prototype pollution | SSRF | RCE | secret exposure | timing oracle | open redirect | TLS bypass}
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
- `rejectUnauthorized: false` outside documented test fixtures
- Same-origin open redirects masquerading as "internal" - allowlist paths, not "starts with /"
