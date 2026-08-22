---
name: spring-security-patterns
description: "Spring Security 6 / Boot 3.5+: SecurityFilterChain, OAuth2/JWT resource server, method security, CORS, CSRF, security headers."
metadata:
  category: backend
  tags: [security, spring-security, oauth2, jwt, cors, csrf, authorization]
user-invocable: false
---

# Spring Security Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Configuring auth for Spring Boot 3.5+ APIs
- OAuth2 / JWT resource server, method-level security, CORS, CSRF, headers

## Rules

- One `SecurityFilterChain` bean per `securityMatcher` path scope; order with `@Order`. Declaring any chain removes Boot's default, so a path matched by no `securityMatcher` runs with **no security filters at all**. The last chain (largest `@Order` value, evaluated last) must therefore be matcher-less and close with `anyRequest()`; add a `denyAll()` chain only when every other chain carries a `securityMatcher`. Permit `/error` there - Spring Security also filters the ERROR dispatch, so denying it replaces every real error response with a 403
- A `CorsConfigurationSource` bean does nothing until a chain calls `.cors(...)`; a chain that omits it rejects preflight before CORS is ever evaluated
- STATELESS APIs: `csrf(AbstractHttpConfigurer::disable)` and `sessionCreationPolicy(STATELESS)` together
- Stateful sessions: keep CSRF on. SPAs reading the token cookie use `CookieCsrfTokenRepository.withHttpOnlyFalse()` (see CSRF pattern); server-rendered forms keep the default session repository + hidden field
- `@EnableMethodSecurity` on any `@Configuration`; method security uses `@PreAuthorize`/`@PostAuthorize` with SpEL
- `hasRole("X")` matches authority `ROLE_X`. If JWT claims already carry `ROLE_*`, set `JwtGrantedAuthoritiesConverter` prefix to `""` to avoid `ROLE_ROLE_X`
- CORS origins, JWT issuer URIs, allowed roles: externalize to properties; never wildcard `*` with credentials
- Passwords: `BCryptPasswordEncoder` via `PasswordEncoder` bean; never store plaintext
- JWTs to browsers: HttpOnly cookie or in-memory only - `localStorage` is XSS-exposed
- Constructor injection only; Boot 3.5 auto-enables `@EnableWebSecurity` (omit unless customizing `WebSecurity`)

## Patterns

### Multi-chain SecurityFilterChain

Separate chains per audience (public API, admin, actuator, webhooks). Each chain uses `securityMatcher` to claim a path scope; lower `@Order` wins.

```java
@Configuration @RequiredArgsConstructor
public class SecurityConfig {

    @Bean @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(withDefaults()))
            .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .cors(withDefaults())
            .build();
    }

    @Bean @Order(2)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/actuator/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(withDefaults())   // needs a UserDetailsService; on a pure JWT app use oauth2ResourceServer here too
            .build();
    }
}
```

Role hierarchy (ADMIN implies MANAGER implies USER):

```java
@Bean RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withRolePrefix("ROLE_")
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("USER").build();
}
```

### OAuth2 Resource Server (JWT)

`application.yml`:

```yaml
spring.security.oauth2.resourceserver.jwt.issuer-uri: https://auth.example.com/realms/app
```

Customize when you need audience validation or non-standard role claims:

```java
@Bean
JwtDecoder jwtDecoder(@Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}") String issuerUri) {
    var decoder = (NimbusJwtDecoder) JwtDecoders.fromIssuerLocation(issuerUri);
    var audience = new JwtClaimValidator<List<String>>("aud", aud -> aud != null && aud.contains("my-api"));
    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuerUri), audience));
    return decoder;
}

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    var granted = new JwtGrantedAuthoritiesConverter();
    granted.setAuthoritiesClaimName("roles");   // top-level claims only (e.g. "roles", "scope")
    granted.setAuthorityPrefix("ROLE_");        // "" if claim already has ROLE_
    var c = new JwtAuthenticationConverter();
    c.setJwtGrantedAuthoritiesConverter(granted);
    return c;
}
```

Both beans are picked up by `.jwt(withDefaults())` automatically - no explicit DSL wiring. For top-level claims, the properties `spring.security.oauth2.resourceserver.jwt.authorities-claim-name` / `.authority-prefix` achieve the converter's effect with no code; nested claims still need the custom converter below.

Nested claims (Keycloak's `realm_access.roles`) are NOT resolvable by `JwtGrantedAuthoritiesConverter` - it silently yields zero authorities and every `hasRole` fails. It also reads exactly one claim with one prefix, so mapping roles *and* permissions needs a custom converter too:

```java
c.setJwtGrantedAuthoritiesConverter(jwt -> {
    var realm = (Map<String, Object>) jwt.getClaims().getOrDefault("realm_access", Map.of());
    return ((List<String>) realm.getOrDefault("roles", List.of())).stream()
        // Keycloak realm roles are lowercase and unprefixed; hasRole("ADMIN") matches the
        // authority ROLE_ADMIN exactly, so "ROLE_" + "admin" would never match.
        .<GrantedAuthority>map(r -> new SimpleGrantedAuthority("ROLE_" + r.toUpperCase(Locale.ROOT)))
        .toList();   // explicit <GrantedAuthority> - List<SimpleGrantedAuthority> does not compile here
});
```

Multi-tenant: dispatch by `iss` claim. Bind the issuer list with `@ConfigurationProperties` (`@Value` cannot bind a YAML sequence), check it against the allowlist **before** building a decoder so an unknown `iss` never triggers an outbound discovery call to an attacker-supplied host, and build lazily so startup does not depend on every tenant's IdP being reachable:

```java
@Bean
JwtDecoder multiTenant(TenantProperties props) {   // record TenantProperties(List<String> issuers, String audience)
    Set<String> allowed = Set.copyOf(props.issuers());
    Map<String, JwtDecoder> decoders = new ConcurrentHashMap<>();
    return token -> {
        String iss;
        try { iss = JWTParser.parse(token).getJWTClaimsSet().getIssuer(); }
        catch (ParseException e) { throw new BadJwtException("Malformed token", e); }
        if (iss == null || !allowed.contains(iss)) throw new BadJwtException("Untrusted issuer: " + iss);
        // decoderFor = the single-tenant JwtDecoder above, parameterised by issuer
        return decoders.computeIfAbsent(iss, i -> decoderFor(i, props.audience())).decode(token);
    };
}
```

`iss` must match byte-for-byte, trailing slash included. A discovery failure for a reachable-but-down tenant must surface as 5xx, not 401 - a valid token is not an invalid one.

### Method security

```java
@Configuration @EnableMethodSecurity
class MethodSecurityConfig {}

@Service
class OrderService {
    @PreAuthorize("hasRole('ADMIN') or #userId == authentication.name")
    List<OrderDTO> findByUser(String userId) { ... }

    @PostAuthorize("returnObject.ownerId() == authentication.name or hasRole('ADMIN')")
    OrderDTO findById(Long id) { ... }
}
```

One-off conditional checks can call a bean directly in SpEL - no evaluator wiring needed:

```java
@PreAuthorize("#req.amount() <= 1000 or @storeAuthz.isManagerOf(authentication, #req.storeId())")
Refund issue(RefundRequest req) { ... }
```

When the same domain-object check recurs across services, centralize it as `hasPermission(...)` backed by a `PermissionEvaluator`. SS6 wires it through a custom expression handler (the old `GlobalMethodSecurityConfiguration` override is gone):

```java
@Bean
static MethodSecurityExpressionHandler expressionHandler(PermissionEvaluator evaluator) {
    var handler = new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(evaluator);  // @PreAuthorize("hasPermission(#id, 'Order', 'read')")
    return handler;
}
```

A custom handler replaces the auto-wired one: if a `RoleHierarchy` bean exists, also call `handler.setRoleHierarchy(roleHierarchy)` - otherwise the hierarchy silently stops applying to method security.

### Password encoding

```java
@Bean PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }
// signup:  user.setPassword(passwordEncoder.encode(raw));
// login:   passwordEncoder.matches(raw, user.getPassword());
```

### CORS

```java
@Bean
CorsConfigurationSource corsConfigurationSource(
        @Value("${app.cors.allowed-origins}") List<String> origins) {
    var config = new CorsConfiguration();
    config.setAllowedOrigins(origins);                                          // never "*" with credentials
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);
    var src = new UrlBasedCorsConfigurationSource();
    src.registerCorsConfiguration("/api/**", config);
    return src;
}
```

### CSRF

```java
// STATELESS API (JWT in Authorization header)
http.csrf(AbstractHttpConfigurer::disable)
    .sessionManagement(s -> s.sessionCreationPolicy(STATELESS));

// Stateful SPA: cookie token, SPA echoes via X-XSRF-TOKEN header.
// SS6 defers/BREACH-encodes the token by default, which breaks SPAs that read the raw
// cookie value - pair the repository with a request handler that resolves it eagerly.
var requestHandler = new CsrfTokenRequestAttributeHandler();
requestHandler.setCsrfRequestAttributeName(null);          // opt out of deferred lookup
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(requestHandler));
```

### Security headers

Apply in every chain that serves browsers (typically all non-webhook chains):

```java
http.headers(h -> h
    .contentSecurityPolicy(csp ->
        csp.policyDirectives("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"))
    .httpStrictTransportSecurity(hsts -> hsts.includeSubDomains(true).maxAgeInSeconds(31536000))
    .contentTypeOptions(withDefaults())
    .frameOptions(f -> f.deny()));
```

### Webhook endpoints

External webhooks (Stripe, GitHub) authenticate via HMAC signature, not JWT. Put them in a dedicated chain with `permitAll`, then verify the signature in a filter or the controller - Spring Security doesn't know about provider-specific signing schemes. Take the body as `@RequestBody String`, never a DTO: the HMAC covers the exact bytes sent, and a parse/re-serialize round trip changes them. An unverifiable payload is 400, not 5xx - a 5xx makes the provider retry it.

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

`@WebMvcTest` does not pick up custom `SecurityFilterChain` `@Configuration` classes - without `@Import` the tests run against Boot's default security and pass for the wrong reason. Stub `JwtDecoder` so an imported config's `fromIssuerLocation` doesn't fetch the issuer at context startup:

```java
@WebMvcTest(OrderController.class)
@Import({SecurityConfig.class, MethodSecurityConfig.class})
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean JwtDecoder jwtDecoder;

    @Test void unauthenticated_returns_401() throws Exception {
        mockMvc.perform(get("/api/orders")).andExpect(status().isUnauthorized());
    }

    @Test void jwt_with_role_passes() throws Exception {
        mockMvc.perform(get("/api/orders")
                // Feed the REAL converter, not a literal authority, or a broken claim mapping
                // still passes: .authorities(literal) bypasses the converter entirely.
                .with(jwt().jwt(j -> j.subject("user-123")
                        .claim("realm_access", Map.of("roles", List.of("user"))))
                    .authorities(new KeycloakRealmRoleConverter())))
            .andExpect(status().isOk());
    }
}
```

`@MockitoBean` on a service replaces the Spring proxy, so its `@PreAuthorize` does not run - assert method-security rules against the real bean in a `@SpringBootTest`, not through a mocked collaborator. Migrating `@Secured` is not optional either: under `@EnableMethodSecurity` it is off unless `securedEnabled = true`, so existing `@Secured` methods are unenforced today - convert them to `@PreAuthorize` rather than switching enforcement on for code that has never been checked.

## Output Format

One block per `SecurityFilterChain`, including the matcher-less catch-all; list its endpoints inside, and map each method-security rule into the block of the chain that serves it. Reviews put findings in prose before the blocks and state whether the blocks describe as-is or target state.

```
Chain: {securityMatcher pattern | no securityMatcher - catch-all} (order {n})
CSRF: {enabled | disabled - reason}
Session: {STATELESS | IF_REQUIRED}
CORS Origins: {list | N/A}
JWT Issuer: {URI | URI list for multi-tenant | N/A} {+ required aud}
Headers: {CSP, HSTS, nosniff, frame-options | none - not browser-facing}
Endpoints:
- {path pattern}: {permitAll | authenticated | denyAll | hasRole(X) | hasAuthority(X)}
- {Class.method}: @PreAuthorize({expr})
```

Close with a `Cross-cutting:` list for what is not chain-scoped - password encoder, method-security enablement, authority-claim mapping.

## Avoid

- `WebSecurityConfigurerAdapter`, `antMatchers()`, `@EnableGlobalMethodSecurity` (removed/deprecated in Spring Security 6)
- `@Secured` - prefer `@PreAuthorize` (SpEL, richer expressions)
- Disabling CSRF on stateful (session-based) apps
- JWT in `localStorage` - XSS-exposed
- Wildcard CORS origins (`*`) with `allowCredentials(true)` - rejected by browsers, insecure regardless
- Hardcoded secrets, issuer URIs, allowed origins
