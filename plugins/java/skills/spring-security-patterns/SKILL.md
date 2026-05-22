---
name: spring-security-patterns
description: "Spring Security 6 / Boot 3.5+: SecurityFilterChain, OAuth2/JWT, method security, CORS, CSRF, security headers, multi-chain config."
metadata:
  category: backend
  tags: [security, spring-security, oauth2, jwt, cors, csrf, authorization]
user-invocable: false
---

# Spring Security Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Configuring auth for Spring Boot 3.5+ APIs
- OAuth2 / JWT resource server setup
- Method-level security with SpEL
- CORS / CSRF / security headers

## Rules

- `SecurityFilterChain` bean - `WebSecurityConfigurerAdapter` was removed in Spring Security 6
- `requestMatchers(...)` - `antMatchers(...)` was removed
- `@EnableMethodSecurity` - `@EnableGlobalMethodSecurity` is deprecated
- STATELESS APIs disable CSRF and sessions
- Externalize issuer URIs, allowed origins via `@ConfigurationProperties` / `@Value`
- Constructor injection only
- Never wildcard CORS origins (`*`) in prod
- JWT in HttpOnly cookie or in-memory - never `localStorage`

## Patterns

### Multi-chain SecurityFilterChain

```java
@Configuration @EnableWebSecurity @RequiredArgsConstructor
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

Role hierarchy via `RoleHierarchy` bean:

```java
@Bean RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withRolePrefix("ROLE_")
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("USER").build();
}
```

### JWT / OAuth2 Resource Server

```java
@Bean
JwtDecoder jwtDecoder(@Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}") String issuerUri) {
    var decoder = (NimbusJwtDecoder) JwtDecoders.fromIssuerLocation(issuerUri);
    var audienceValidator = new JwtClaimValidator<List<String>>(
        "aud", aud -> aud != null && aud.contains("my-api"));
    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuerUri), audienceValidator));
    return decoder;
}

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    var granted = new JwtGrantedAuthoritiesConverter();
    granted.setAuthoritiesClaimName("roles");
    granted.setAuthorityPrefix("ROLE_");
    var c = new JwtAuthenticationConverter();
    c.setJwtGrantedAuthoritiesConverter(granted);
    return c;
}
```

`hasRole("ADMIN")` matches authority `ROLE_ADMIN`; `hasAuthority("ADMIN")` matches `ADMIN`. If tokens already carry `ROLE_*`-prefixed authorities, set the prefix to `""` to avoid `ROLE_ROLE_ADMIN`.

Multi-tenant: use a token-introspecting decoder that picks per-issuer:

```java
@Bean
JwtDecoder multiTenant(@Value("${jwt.issuer-uris}") List<String> issuerUris) {
    Map<String, JwtDecoder> decoders = issuerUris.stream()
        .collect(toMap(identity(), JwtDecoders::fromIssuerLocation));
    return token -> {
        var issuer = JWTParser.parse(token).getJWTClaimsSet().getIssuer();
        var d = decoders.get(issuer);
        if (d == null) throw new JwtException("Unknown issuer: " + issuer);
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
    public List<OrderDTO> findByUser(String userId) { ... }

    @PostAuthorize("returnObject.ownerId() == authentication.name or hasRole('ADMIN')")
    public OrderDTO findById(Long id) { ... }
}
```

Domain-object authorization via `PermissionEvaluator`:

```java
@Component
public class ProjectPermissionEvaluator implements PermissionEvaluator {
    public boolean hasPermission(Authentication auth, Object target, Object permission) {
        return target instanceof Project p &&
            (p.getOwnerId().equals(auth.getName())
                || auth.getAuthorities().stream().anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
    }
    public boolean hasPermission(Authentication auth, Serializable id, String type, Object permission) {
        return false;
    }
}

// @PreAuthorize("hasPermission(#project, 'WRITE')")
```

### CORS for JWT SPAs

```java
@Bean
CorsConfigurationSource corsConfigurationSource(
        @Value("${app.cors.allowed-origins}") List<String> allowedOrigins) {
    var config = new CorsConfiguration();
    config.setAllowedOrigins(allowedOrigins);
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-XSRF-TOKEN"));
    config.setExposedHeaders(List.of("X-Total-Count"));
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);
    var src = new UrlBasedCorsConfigurationSource();
    src.registerCorsConfiguration("/api/**", config);
    return src;
}
```

### CSRF

```java
// STATELESS API
http.csrf(AbstractHttpConfigurer::disable)
    .sessionManagement(s -> s.sessionCreationPolicy(STATELESS));

// Stateful SPA: cookie + header
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()));
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

External webhooks (Stripe, GitHub) use signature-based authn, not JWT. Separate chain with `permitAll`:

```java
@Bean @Order(0)
SecurityFilterChain webhookChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/webhooks/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
        .build();
}
```

Signature validation (HMAC-SHA256 for Stripe, etc.) happens in the controller / dedicated filter, not Spring Security.

### Tests

```java
@WebMvcTest(UserController.class)
class UserControllerSecurityTest {
    @Test @WithMockUser(roles = "ADMIN")
    void admin_endpoint_returns_200() throws Exception {
        mockMvc.perform(get("/api/admin/users")).andExpect(status().isOk());
    }

    @Test
    void unauthenticated_returns_401() throws Exception {
        mockMvc.perform(get("/api/admin/users")).andExpect(status().isUnauthorized());
    }

    @Test
    void with_jwt_authority() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(new SimpleGrantedAuthority("ROLE_USER"))
                    .jwt(j -> j.claim("sub", "user-123"))))
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

- `WebSecurityConfigurerAdapter`, `antMatchers()`, `@EnableGlobalMethodSecurity` (all removed/deprecated)
- `@Secured` (limited - prefer `@PreAuthorize`)
- Disabling CSRF on stateful apps
- JWT in `localStorage` (XSS vector)
- Wildcard CORS origins in prod
- Hardcoded secrets / issuer URIs
