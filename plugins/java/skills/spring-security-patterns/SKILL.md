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

- One `SecurityFilterChain` bean per `securityMatcher` path scope; order with `@Order`
- STATELESS APIs: `csrf().disable()` and `sessionCreationPolicy(STATELESS)` together
- Stateful sessions: keep CSRF on; use `CookieCsrfTokenRepository.withHttpOnlyFalse()`
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
            .httpBasic(withDefaults())
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
    granted.setAuthoritiesClaimName("roles");   // or "scope", "realm_access.roles"
    granted.setAuthorityPrefix("ROLE_");        // "" if claim already has ROLE_
    var c = new JwtAuthenticationConverter();
    c.setJwtGrantedAuthoritiesConverter(granted);
    return c;
}
```

Multi-tenant: dispatch by `iss` claim:

```java
@Bean
JwtDecoder multiTenant(@Value("${jwt.issuer-uris}") List<String> issuerUris) {
    Map<String, JwtDecoder> decoders = issuerUris.stream()
        .collect(toMap(identity(), JwtDecoders::fromIssuerLocation));
    return token -> {
        var iss = JWTParser.parse(token).getJWTClaimsSet().getIssuer();
        var d = decoders.get(iss);
        if (d == null) throw new JwtException("Unknown issuer: " + iss);
        return d.decode(token);
    };
}
```

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

Domain-object checks use `hasPermission(...)` backed by a `PermissionEvaluator` - prefer this over scattering ownership checks across services. SS6 wires it through a custom expression handler (the old `GlobalMethodSecurityConfiguration` override is gone):

```java
@Bean
static MethodSecurityExpressionHandler expressionHandler(PermissionEvaluator evaluator) {
    var handler = new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(evaluator);  // @PreAuthorize("hasPermission(#id, 'Order', 'read')")
    return handler;
}
```

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

```java
http.headers(h -> h
    .contentSecurityPolicy(csp ->
        csp.policyDirectives("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"))
    .httpStrictTransportSecurity(hsts -> hsts.includeSubDomains(true).maxAgeInSeconds(31536000))
    .contentTypeOptions(withDefaults())
    .frameOptions(f -> f.deny()));
```

### Webhook endpoints

External webhooks (Stripe, GitHub) authenticate via HMAC signature, not JWT. Put them in a dedicated chain with `permitAll`, then verify the signature in a filter or the controller - Spring Security doesn't know about provider-specific signing schemes.

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

```java
@WebMvcTest(OrderController.class)
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;

    @Test void unauthenticated_returns_401() throws Exception {
        mockMvc.perform(get("/api/orders")).andExpect(status().isUnauthorized());
    }

    @Test void jwt_with_role_passes() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(new SimpleGrantedAuthority("ROLE_USER"))
                    .jwt(j -> j.subject("user-123"))))
            .andExpect(status().isOk());
    }
}
```

## Output Format

```
Endpoint: {path pattern}
Auth: {permitAll | authenticated | hasRole(X) | @PreAuthorize(expr)}
CSRF: {enabled | disabled - reason}
Session: {STATELESS | IF_REQUIRED}
CORS Origins: {list or N/A}
JWT Issuer: {URI or N/A}
```

## Avoid

- `WebSecurityConfigurerAdapter`, `antMatchers()`, `@EnableGlobalMethodSecurity` (removed/deprecated in Spring Security 6)
- `@Secured` - prefer `@PreAuthorize` (SpEL, richer expressions)
- Disabling CSRF on stateful (session-based) apps
- JWT in `localStorage` - XSS-exposed
- Wildcard CORS origins (`*`) with `allowCredentials(true)` - rejected by browsers, insecure regardless
- Hardcoded secrets, issuer URIs, allowed origins
