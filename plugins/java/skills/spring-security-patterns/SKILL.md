---
name: spring-security-patterns
description: "Spring Security 7 / Boot 4: SecurityFilterChain, OAuth2/JWT resource server, method security, CORS, CSRF, security headers."
metadata:
  category: backend
  tags: [security, spring-security, oauth2, jwt, cors, csrf, authorization]
user-invocable: false
---

# Spring Security Patterns

> Load `Use skill: stack-detect` first to determine the project stack. Written for Spring Boot 4 / Spring Security 7 (version from the Boot BOM or parent; `unknown` when neither is declared); lines that differ on Security 6 say so. The patterns are servlet (MVC); WebFlux uses `SecurityWebFilterChain` / `ServerHttpSecurity`, `@EnableReactiveMethodSecurity`, the `Server*` CSRF classes, and `@WebFluxTest` + `mockJwt()` - the `/error` dispatch rule is servlet-only.

## When to Use

- Configuring auth for Spring Boot APIs and server-rendered/SPA apps
- OAuth2 / JWT resource server (single or multi-tenant), method-level security, CORS, CSRF, headers, webhooks
- Reviewing existing Spring Security configuration and its tests

## Rules

- One `SecurityFilterChain` bean per `securityMatcher` path scope, ordered with `@Order`. Declaring any chain removes Boot's default, so a path matched by no chain runs with **no security filters at all**. The last chain (largest `@Order`) is matcher-less and closes with `anyRequest()`; permit `/error` there - the ERROR dispatch is filtered too, and denying it replaces every real error response with a 401/403
- CORS: every browser-facing chain calls `.cors(withDefaults())` explicitly (automatic application depends on exactly one `UrlBasedCorsConfigurationSource` bean and is not worth relying on); without it preflight is rejected before CORS is evaluated. A same-origin SPA needs no CORS configuration at all. Never wildcard origins with credentials
- STATELESS APIs: `csrf(AbstractHttpConfigurer::disable)` and `sessionCreationPolicy(STATELESS)` together
- Stateful sessions: keep CSRF on. SPAs reading the token cookie use `csrf.spa()` (Security 7; Security 6 form in the CSRF pattern); server-rendered forms keep the default session repository + hidden field
- Method security needs `@EnableMethodSecurity` on a `@Configuration`; use `@PreAuthorize`/`@PostAuthorize` with SpEL. `@Secured` is off under it unless `securedEnabled = true` - existing `@Secured` methods are unenforced today; convert them to `@PreAuthorize`
- `hasRole("X")` matches authority `ROLE_X`. The default `JwtGrantedAuthoritiesConverter` maps `scope`/`scp` with prefix `SCOPE_`; for role claims set the claim name and prefix (properties or converter setters); when values already carry `ROLE_`, set the prefix to `""`
- Issuer URIs, audiences, CORS origins, allowed roles: externalize to properties
- Passwords: a `DelegatingPasswordEncoder` (`PasswordEncoderFactories.createDelegatingPasswordEncoder()`, bcrypt default); never plaintext
- JWTs to browsers: HttpOnly cookie or in-memory only - `localStorage` is XSS-exposed
- Boot applies `@EnableWebSecurity` itself; add it only when security auto-configuration is excluded

## Patterns

### Multi-chain SecurityFilterChain

Separate chains per audience (public API, admin, actuator, webhooks). Lower `@Order` wins.

```java
@Configuration
public class SecurityConfig {

    @Bean @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/invoices/**").hasAuthority("SCOPE_invoices.read")
                .requestMatchers("/api/invoices/**").hasAuthority("SCOPE_invoices.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(withDefaults()))
            .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean @Order(2)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class, InfoEndpoint.class)).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(withDefaults())   // needs a UserDetailsService; on a pure JWT app use oauth2ResourceServer here
            .build();
    }

    @Bean @Order(Ordered.LOWEST_PRECEDENCE)
    SecurityFilterChain defaultChain(HttpSecurity http) throws Exception {   // matcher-less catch-all
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .anyRequest().denyAll())
            .build();
    }
}
```

Prometheus scraping: serve actuator on a separate `management.server.port` that is not exposed outside the cluster/VPC and permit `/actuator/prometheus` in the actuator chain; network placement is the control, so say so in `Cross-cutting`.

Role hierarchy (ADMIN implies MANAGER implies USER):

```java
@Bean static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withRolePrefix("ROLE_")
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("USER").build();
}
```

### OAuth2 Resource Server (JWT)

```yaml
spring.security.oauth2.resourceserver.jwt:
  issuer-uri: https://auth.example.com/realms/app
  audiences: my-api                     # aud validation, no code
  authorities-claim-name: roles         # top-level claim -> authorities
  authority-prefix: ROLE_
```

Properties cover top-level claims and audience; Boot 4.1 also maps a nested claim - `authorities-claim-expressions: "[realm_access][roles].![toUpperCase()]"` with `authority-prefix: ROLE_` (SpEL over the claims map; exclusive with `authorities-claim-name`; a missing claim yields no authorities). Security 7 validates the JWT `typ` header by default: `JWT` or absent passes, anything else is 401 - an IdP issuing RFC 9068 `at+jwt` tokens needs `JwtValidators.createAtJwtValidator()`. A custom `JwtDecoder` bean makes Boot's decoder auto-configuration back off (including the `audiences` property), and a `JwtAuthenticationConverter` bean makes it ignore `authorities-claim-name` / `authority-prefix` - use the properties or the bean, never both, and inject bean values from properties.

Nested claims (Keycloak `realm_access.roles`) are not resolvable by `JwtGrantedAuthoritiesConverter` - it silently yields zero authorities and every `hasRole` fails. One prefix applies to every claim it maps, so roles *and* scopes need a custom converter (as does a nested claim on Boot 4.0 / 3.x). Make it a named class so tests can feed it:

```java
public class KeycloakRealmRoleConverter implements Converter<Jwt, Collection<GrantedAuthority>> {
    private final JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();   // scope/scp -> SCOPE_*

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        var realm = jwt.getClaimAsMap("realm_access");
        var roles = realm == null ? List.<String>of() : (List<String>) realm.getOrDefault("roles", List.of());
        var out = new ArrayList<GrantedAuthority>(scopes.convert(jwt));
        // realm roles are lowercase and unprefixed; hasRole("ADMIN") matches ROLE_ADMIN exactly
        roles.forEach(r -> out.add(new SimpleGrantedAuthority("ROLE_" + r.toUpperCase(Locale.ROOT))));
        return out;
    }
}

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    var c = new JwtAuthenticationConverter();
    c.setJwtGrantedAuthoritiesConverter(new KeycloakRealmRoleConverter());
    return c;   // picked up by .jwt(withDefaults())
}
```

`JwtGrantedAuthoritiesConverter` accepts `scp`/`scope` as a space-delimited string (Entra) or an array (Okta).

### Multi-tenant (issuer allowlist)

Stock option: `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(Predicate<String>)`, wired with `.oauth2ResourceServer(o -> o.authenticationManagerResolver(resolver))`. It checks the allowlist before any discovery call, builds per-issuer managers lazily and caches them; a predicate backed by a refreshable source (DB table, config server) adds tenants without a restart. It applies no audience validator and ignores the app's `JwtAuthenticationConverter` bean - when you need either, build per-issuer providers yourself:

```java
@Bean
AuthenticationManagerResolver<HttpServletRequest> tenantResolver(TenantRegistry tenants, JwtAuthenticationConverter converter) {
    Map<String, AuthenticationManager> managers = new ConcurrentHashMap<>();
    return new JwtIssuerAuthenticationManagerResolver(issuer -> {
        if (!tenants.isTrusted(issuer)) return null;   // untrusted -> 401, no outbound discovery call
        return managers.computeIfAbsent(issuer, i -> {
            NimbusJwtDecoder decoder = JwtDecoders.fromIssuerLocation(i);
            decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(i),
                new JwtClaimValidator<List<String>>("aud", aud -> aud != null && aud.contains(tenants.audience()))));
            var provider = new JwtAuthenticationProvider(decoder);
            provider.setJwtAuthenticationConverter(converter);
            return provider::authenticate;
        });
    });
}
// TenantRegistry: an issuer allowlist read live from a store; a removed issuer stops matching on the next call.
```

`iss` must match byte-for-byte, trailing slash included. A discovery failure for a trusted-but-down IdP must surface as 5xx, not 401 - a valid token is not an invalid one (test: a registry entry pointing at an unreachable issuer returns 5xx). A registry backed by a DB table, or `@RefreshScope` configuration (Spring Cloud), adds tenants without a restart; removals must take effect on the next request. Keep IdP role values' case as issued and write `hasRole` checks to match (normalise only when an IdP is known to lowercase, as Keycloak realm roles are). Per-IdP claim shapes (Entra `roles`, Okta `groups`) are one converter that reads whichever claim is present.

### Method security

```java
@Configuration @EnableMethodSecurity
class MethodSecurityConfig {}

@Service
class OrderService {
    @PreAuthorize("hasRole('ADMIN') or #userId == authentication.name")   // #param names need -parameters: set by the
    List<OrderDTO> findByUser(String userId) { ... }                       // Boot Gradle plugin and spring-boot-starter-parent; a BOM-only Maven build adds it (or use @P)

    @PostAuthorize("returnObject.ownerId() == authentication.name or hasRole('ADMIN')")
    OrderDTO findById(Long id) { ... }
}
```

Domain-scoped checks call a bean in SpEL; the principal carries the scope (a custom `UserDetails` with `storeId`, or a JWT claim), and the method takes the scoped ID as a parameter (add it when missing) or checks the loaded entity in `@PostAuthorize`. A resource ID taken from the path with no ownership check is an IDOR - `[Must]`. A URL rule and a `@PreAuthorize` on the same route both apply (AND) - check they agree:

```java
@PreAuthorize("hasAuthority('HEAD_OFFICE') or (#req.amount() <= 500 and @storeAuthz.isManagerOf(authentication, #req.storeId()))")
Refund issue(RefundRequest req) { ... }
```

When the same domain-object check recurs, centralize it as `hasPermission(...)` via a `PermissionEvaluator`:

```java
@Bean
static MethodSecurityExpressionHandler expressionHandler(PermissionEvaluator evaluator, RoleHierarchy roleHierarchy) {
    var handler = new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(evaluator);     // @PreAuthorize("hasPermission(#id, 'Order', 'read')")
    handler.setRoleHierarchy(roleHierarchy);       // a custom handler replaces the auto-wired one - keep the hierarchy
    return handler;
}
```

### Passwords, including legacy plaintext rows

```java
@Bean PasswordEncoder passwordEncoder() {
    var encoder = (DelegatingPasswordEncoder) PasswordEncoderFactories.createDelegatingPasswordEncoder();
    encoder.setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder.getInstance());   // legacy rows have no {id} prefix
    return encoder;
}
```

Implement `UserDetailsPasswordService` so each legacy user is re-hashed with bcrypt on their next successful login; for users who never log in, run a one-off job that hashes the plaintext (prefix `{bcrypt}`), then remove the `NoOp` default.

### CORS

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource(CorsProperties props) {   // @ConfigurationProperties("app.cors")
    var config = new CorsConfiguration();
    config.setAllowedOrigins(props.allowedOrigins());                         // never "*" with credentials
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);
    var src = new UrlBasedCorsConfigurationSource();
    src.registerCorsConfiguration("/api/**", config);
    return src;
}
```

`@Value` cannot bind a YAML sequence - bind lists through `@ConfigurationProperties` (or use a comma-separated string with `@Value`).

### CSRF

```java
// STATELESS API (JWT in the Authorization header)
http.csrf(AbstractHttpConfigurer::disable)
    .sessionManagement(s -> s.sessionCreationPolicy(STATELESS));

// Stateful SPA: JS-readable cookie token (CookieCsrfTokenRepository.withHttpOnlyFalse()), echoed in X-XSRF-TOKEN.
// spa() keeps BREACH (XOR) protection for rendered tokens, accepts the raw cookie value from the header,
// and loads the token on every request so the cookie is written on the first GET. Security 7.0+; on
// Security 6 hand-write the same CsrfTokenRequestHandler (plain + XOR delegates, header decides).
http.csrf(csrf -> csrf.spa());
```

### Security headers

Every chain already writes `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, cache-control, and HSTS (1 year, includeSubDomains, on HTTPS requests only). Browser-facing chains add a CSP:

```java
http.headers(h -> h.contentSecurityPolicy(csp ->
    csp.policyDirectives("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'")));
```

Behind a TLS-terminating proxy, set `server.forward-headers-strategy` so requests are recognized as secure and HSTS is written.

### Webhook endpoints

External webhooks authenticate by signature, not JWT: a dedicated chain with `permitAll`, verification in the controller or a filter. Verify per the provider's scheme - raw-body HMAC (Stripe, GitHub) takes the body as `@RequestBody byte[]` (a `String` is charset-decoded and a DTO re-serialized, both changing the signed bytes); field-signature schemes (Adyen notifications sign selected fields, carried in the payload) verify over the parsed fields exactly as the provider documents. Compare in constant time (`MessageDigest.isEqual`). An unverifiable payload is 400 (not a server fault); providers that retry non-2xx will retry it, which is harmless because it keeps failing - alert on verification failures (a rotated secret fails genuine events too). Adyen's Java library ships `HMACValidator` for its notification signatures - use the provider's validator where one exists.

```java
@Bean @Order(0)
SecurityFilterChain webhookChain(HttpSecurity http) throws Exception {
    return http.securityMatcher("/webhooks/**")
        .authorizeHttpRequests(a -> a.anyRequest().permitAll())
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
        .build();
}
```

### Tests

`@WebMvcTest` does not load custom `SecurityFilterChain` or `@EnableMethodSecurity` configuration - without `@Import` the tests run against Boot's default security and pass for the wrong reason. On Boot 4 the slice gets Spring Security's auto-configuration only from `spring-boot-starter-security-test`. Stub `JwtDecoder` so the imported chain has a decoder bean regardless of test properties and no request reaches the IdP, and mock the controller's collaborators:

```java
@WebMvcTest(OrderController.class)
@Import({SecurityConfig.class, MethodSecurityConfig.class})
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;
    @MockitoBean JwtDecoder jwtDecoder;

    @Test void unauthenticated_returns_401() throws Exception {
        mockMvc.perform(get("/api/orders")).andExpect(status().isUnauthorized());
    }

    @Test void realm_role_maps_to_authority() throws Exception {
        mockMvc.perform(get("/api/admin/orders")
                // Feed the REAL converter, not literal authorities - .authorities(literal) would
                // pass even when the claim mapping is broken
                .with(jwt().jwt(j -> j.subject("user-123")
                        .claim("realm_access", Map.of("roles", List.of("admin"))))
                    .authorities(new KeycloakRealmRoleConverter())))
            .andExpect(status().isOk());
    }
}
```

`@MockitoBean` on a service replaces the Spring proxy, so its `@PreAuthorize` does not run - assert method-security rules against the real bean in a `@SpringBootTest`.

## Output Format

In every mode, emit the `**Stack:**` line once, then one block per `SecurityFilterChain`, in order, listing its endpoints and mapping each method-security rule into the block of the chain that serves it, then the `Cross-cutting:` block. A request to fix existing configuration is a review: findings, then the target state. When reviewing, the consuming workflow owns the finding envelope; invoked standalone, list findings first - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when it allows an auth bypass or IDOR, exposes data or endpoints, weakens credential storage or a signature check (a non-constant-time compare included), or breaks an auth flow, `[Recommend]` otherwise - then the blocks of the target state. A missing matcher-less catch-all is itself a finding. Vulnerabilities outside Spring Security's surface seen in passing (SQL injection, SSRF) get one `Out of scope: {issue} at {file:line}` line each.

```
**Stack:** Spring Security {version | unknown} on {MVC | WebFlux}
```

```
Chain: {securityMatcher pattern | no securityMatcher - catch-all} (order {n})

Auth: {JWT | httpBasic | form | signature - <scheme> | none}

CSRF: {enabled - <repository/handler> | disabled - reason}

Session: {STATELESS | IF_REQUIRED}

CORS Origins: {list | N/A - same-origin | N/A - not browser-facing}

JWT Issuer: {URI | allowlist - <source>}{ + aud <value>} {only when Auth is JWT}

Headers: {defaults | CSP + defaults | disabled - reason}

Endpoints:
- {path pattern}: {permitAll | authenticated | denyAll | hasRole(X) | hasAuthority(X) | hasAnyRole(X,...) | hasAnyAuthority(X,...) | access(<manager>)}
- {Class.method}: {@PreAuthorize | @PostAuthorize | @Secured}({expr})
```

```
Cross-cutting:
- Method security: {@EnableMethodSecurity present | missing}; @Secured {enabled | unenforced | none}
- Password encoder: {encoder + legacy-row migration | N/A}
- Authority mapping: {claim -> authority rule | N/A}
- Tenant allowlist: {source + refresh | N/A}
- Outside Spring: {controls enforced by network or infrastructure | none}
```

## Avoid

- `WebSecurityConfigurerAdapter`, `antMatchers()` (removed in Spring Security 6), `and()`, `authorizeRequests()`, `AntPathRequestMatcher` / `MvcRequestMatcher` (removed in 7), `@EnableGlobalMethodSecurity` (deprecated)
- Disabling CSRF on stateful (session-based) apps
- JWT in `localStorage`
- Wildcard CORS origins with credentials
- Hardcoded secrets, issuer URIs, audiences, allowed origins
- Testing roles with literal `.authorities(...)` instead of the production converter
