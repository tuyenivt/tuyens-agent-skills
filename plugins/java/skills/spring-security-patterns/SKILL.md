---
name: spring-security-patterns
description: Spring Security 6.x configuration patterns for Spring Boot 3.5+. Covers SecurityFilterChain, OAuth2/JWT resource server, method-level security, CORS, and common vulnerability prevention. All patterns use the component-based configuration (no WebSecurityConfigurerAdapter).
metadata:
  category: backend
  tags: [security, spring-security, oauth2, jwt, cors, csrf, authorization]
user-invocable: false
---

# Spring Security Patterns

## When to Use

- Configuring authentication and authorization for Spring Boot 3.5+ APIs
- Setting up OAuth2/JWT resource server
- Applying method-level security with SpEL expressions
- Configuring CORS for SPA frontends
- Hardening security headers and CSRF protection

## Rules

- Use `SecurityFilterChain` as `@Bean` — never extend `WebSecurityConfigurerAdapter` (removed in Spring Security 6)
- Use `requestMatchers()` API — never `antMatchers()` (removed)
- Use `@EnableMethodSecurity` — never `@EnableGlobalMethodSecurity` (deprecated)
- STATELESS APIs must disable CSRF and sessions
- Never store JWT in localStorage — use HttpOnly cookie or Authorization header from memory
- Never use wildcard CORS origins (`*`) in production
- Constructor injection only (`@RequiredArgsConstructor`)
- Externalize security configuration (issuer URIs, allowed origins) via `@Value` or `@ConfigurationProperties`

## Pattern

### Security Filter Chain

Multiple filter chains for different path groups, ordered by specificity:

```java
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session.sessionCreationPolicy(STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain actuatorSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/actuator/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Role hierarchy configuration:

```java
@Bean
RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withRolePrefix("ROLE_")
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("USER")
        .build();
}
```

### JWT / OAuth2 Resource Server

JwtDecoder with issuer validation:

```java
@Bean
JwtDecoder jwtDecoder(@Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}") String issuerUri) {
    var decoder = JwtDecoders.fromIssuerLocation(issuerUri);
    if (decoder instanceof NimbusJwtDecoder nimbusDecoder) {
        var audienceValidator = new JwtClaimValidator<List<String>>(
            "aud", aud -> aud != null && aud.contains("my-api")
        );
        var withIssuer = JwtValidators.createDefaultWithIssuer(issuerUri);
        var combined = new DelegatingOAuth2TokenValidator<>(withIssuer, audienceValidator);
        nimbusDecoder.setJwtValidator(combined);
    }
    return decoder;
}
```

Custom role extraction from JWT claims:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    var grantedAuthoritiesConverter = new JwtGrantedAuthoritiesConverter();
    grantedAuthoritiesConverter.setAuthoritiesClaimName("roles");
    grantedAuthoritiesConverter.setAuthorityPrefix("ROLE_");

    var converter = new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grantedAuthoritiesConverter);
    return converter;
}
```

Multi-tenant JWT validation (multiple issuers):

```java
@Bean
JwtDecoder multiTenantJwtDecoder(
        @Value("${jwt.issuer-uris}") List<String> issuerUris) {
    Map<String, JwtDecoder> decoders = issuerUris.stream()
        .collect(Collectors.toMap(
            Function.identity(),
            JwtDecoders::fromIssuerLocation
        ));

    return token -> {
        var issuer = JWTParser.parse(token).getJWTClaimsSet().getIssuer();
        var decoder = decoders.get(issuer);
        if (decoder == null) {
            throw new JwtException("Unknown issuer: " + issuer);
        }
        return decoder.decode(token);
    };
}
```

### Method-Level Security

Enable and use `@PreAuthorize` / `@PostAuthorize`:

```java
@Configuration
@EnableMethodSecurity  // replaces @EnableGlobalMethodSecurity
public class MethodSecurityConfig {}

@Service
@Transactional(readOnly = true)
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository orderRepository;

    @PreAuthorize("hasRole('ADMIN') or #userId == authentication.name")
    public List<OrderDTO> findByUser(String userId) {
        return orderRepository.findByUserId(userId).stream()
            .map(OrderDTO::from)
            .toList();
    }

    @PostAuthorize("returnObject.ownerId() == authentication.name or hasRole('ADMIN')")
    public OrderDTO findById(Long id) {
        return orderRepository.findById(id)
            .map(OrderDTO::from)
            .orElseThrow(() -> new NotFoundException("Order not found"));
    }
}
```

Custom permission evaluator for domain-object authorization:

```java
@Component
public class ProjectPermissionEvaluator implements PermissionEvaluator {

    @Override
    public boolean hasPermission(Authentication auth, Object target, Object permission) {
        if (target instanceof Project project) {
            return project.getOwnerId().equals(auth.getName())
                || auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN"));
        }
        return false;
    }

    @Override
    public boolean hasPermission(Authentication auth, Serializable targetId,
                                  String targetType, Object permission) {
        return false; // implement if needed
    }
}

// Usage:
@PreAuthorize("hasPermission(#project, 'WRITE')")
public void updateProject(Project project) { ... }
```

### CORS Configuration

`CorsConfigurationSource` bean for JWT-based SPAs:

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
    config.setMaxAge(3600L); // preflight cache 1 hour

    var source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Wire into SecurityFilterChain:

```java
http.cors(cors -> cors.configurationSource(corsConfigurationSource(allowedOrigins)))
```

### CSRF Handling

STATELESS APIs — disable CSRF (no session to protect):

```java
http.csrf(AbstractHttpConfigurer::disable)
    .sessionManagement(session -> session.sessionCreationPolicy(STATELESS))
```

Stateful apps — CookieCsrfTokenRepository for SPA (XSRF-TOKEN cookie + X-XSRF-TOKEN header):

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
)
```

### Security Headers

Configure via SecurityFilterChain `headers()` block:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp ->
        csp.policyDirectives("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"))
    .httpStrictTransportSecurity(hsts ->
        hsts.includeSubDomains(true).maxAgeInSeconds(31536000))
    .contentTypeOptions(Customizer.withDefaults())  // X-Content-Type-Options: nosniff
    .frameOptions(frame -> frame.deny())
)
```

### Testing Security

Simple role-based test with `@WithMockUser`:

```java
@WebMvcTest(UserController.class)
class UserControllerSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminEndpoint_withAdminRole_returns200() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
            .andExpect(status().isOk());
    }

    @Test
    void adminEndpoint_unauthenticated_returns401() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
            .andExpect(status().isUnauthorized());
    }
}
```

JWT-based test with `SecurityMockMvcRequestPostProcessors.jwt()`:

```java
@Test
void jwtEndpoint_withValidJwt_returns200() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(jwt().authorities(new SimpleGrantedAuthority("ROLE_USER"))
                .jwt(j -> j.claim("sub", "user-123"))))
        .andExpect(status().isOk());
}
```

Integration test with real test key pair:

```java
@SpringBootTest(webEnvironment = RANDOM_PORT)
class SecurityIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void publicEndpoint_noAuth_returns200() {
        var response = restTemplate.getForEntity("/api/public/health", String.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void protectedEndpoint_noAuth_returns401() {
        var response = restTemplate.getForEntity("/api/orders", String.class);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
```

## Avoid

- ❌ `WebSecurityConfigurerAdapter` — removed in Spring Security 6
- ❌ `antMatchers()` — replaced by `requestMatchers()`
- ❌ `@EnableGlobalMethodSecurity` — replaced by `@EnableMethodSecurity`
- ❌ `@Secured` — limited; prefer `@PreAuthorize` with SpEL
- ❌ Disabling CSRF on stateful (session-based) applications
- ❌ Storing JWT in `localStorage` — vulnerable to XSS; use HttpOnly cookie or keep in memory
- ❌ Wildcard CORS origins (`*`) in production — specify exact origins
- ❌ Hardcoded secrets or issuer URIs — externalize to configuration
