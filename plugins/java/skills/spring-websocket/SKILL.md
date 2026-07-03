---
name: spring-websocket
description: "Spring WebSocket / STOMP: CONNECT-frame JWT auth, message-level security, broker relay for multi-instance, Virtual Thread safety."
metadata:
  category: backend
  tags: [websocket, stomp, messaging, real-time, spring]
user-invocable: false
---

# Spring WebSocket

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Real-time bidirectional channels (chat, notifications, live status)
- Server-pushed updates over STOMP / WebSocket

## Rules

- Authenticate once at the STOMP `CONNECT` frame via `ChannelInterceptor`. Prefer CONNECT-frame JWT over handshake query params (query strings leak to proxy logs and browser history).
- `/topic/**` for broadcasts; `/user/queue/**` via `convertAndSendToUser` for per-user delivery. Never broadcast sensitive payloads on `/topic`.
- `enableSimpleBroker` is in-process. For >1 instance, use `enableStompBrokerRelay` (broker choice: whatever STOMP-capable broker the org already runs - RabbitMQ / Artemis / ActiveMQ; RabbitMQ needs the STOMP plugin). `convertAndSendToUser` still breaks across instances unless the sender's instance knows where the user is connected: enable `setUserRegistryBroadcast` / `setUserDestinationBroadcast` on the relay. Sticky sessions are the fallback only when the broker cannot carry the registry topics. A relay alone does not fix per-user routing.
- Set heartbeats, message size, send buffer, and send time limits. Without them stale or slow clients consume threads and memory indefinitely.
- Use `ReentrantLock` or concurrent collections in handlers - `synchronized` pins Virtual Threads.
- Handle errors with `@MessageExceptionHandler`. Unhandled exceptions close the session with no client-visible reason.

## Patterns

### Broker + transport config

```java
@Configuration @EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Value("${app.cors.origins}") private String[] allowedOrigins;  // ${...} in a plain method argument is NOT resolved

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        // Single instance: in-process broker
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[]{10_000, 10_000});
        // Multi-instance: swap the line above for the relay below. The relay has no
        // setHeartbeatValue - heartbeats use the system API. The two broadcasts are what
        // make convertAndSendToUser reach users connected to another instance.
        // registry.enableStompBrokerRelay("/topic", "/queue")
        //         .setRelayHost("rabbitmq").setRelayPort(61613)
        //         .setClientLogin("app").setClientPasscode(brokerPassword)
        //         .setUserRegistryBroadcast("/topic/simp-user-registry")
        //         .setUserDestinationBroadcast("/topic/simp-user-destination")
        //         .setSystemHeartbeatSendInterval(10_000)
        //         .setSystemHeartbeatReceiveInterval(10_000);
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns(allowedOrigins); // patterns, not origins, when behind proxy
        // .withSockJS() only if legacy fallback is required - its HTTP transports need
        // sticky sessions, which contradicts the relay-based multi-instance story
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration r) {
        r.setMessageSizeLimit(64 * 1024)
         .setSendBufferSizeLimit(512 * 1024)
         .setSendTimeLimit(20_000);
    }
}
```

`SimpleBrokerMessageHandler` heartbeats need a `TaskScheduler` - configure one if not already present.

### CONNECT-frame JWT auth

```java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(Message<?> message, MessageChannel channel) {
            StompHeaderAccessor acc = StompHeaderAccessor.wrap(message);
            if (StompCommand.CONNECT.equals(acc.getCommand())) {
                String header = acc.getFirstNativeHeader("Authorization");
                if (header == null || !header.startsWith("Bearer ")) {
                    throw new MessageDeliveryException("Missing Bearer token");
                }
                Jwt jwt = jwtDecoder.decode(header.substring(7));
                acc.setUser(jwtAuthConverter.convert(jwt)); // reuse the HTTP JwtAuthenticationConverter bean
            }
            return message;
        }
    });
}
```

Reusing the existing `JwtAuthenticationConverter` keeps role mapping consistent with the REST side. The `Principal` set here flows through `@MessageMapping` methods and powers `convertAndSendToUser`.

### Message-level authorization

```java
@Configuration @EnableWebSocketSecurity
public class WebSocketSecurityConfig {
    @Bean
    AuthorizationManager<Message<?>> messageAuthz(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        return messages
            .nullDestMatcher().authenticated()               // CONNECT/DISCONNECT
            .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
            .simpDestMatchers("/app/**").authenticated()     // client SENDs enter through /app only
            .simpDestMatchers("/topic/**", "/queue/**").denyAll() // clients never SEND to broker prefixes -
                                                             // a relay fans such frames out verbatim (broadcast spoofing)
            .simpSubscribeDestMatchers("/topic/**", "/user/queue/**").authenticated()
            .anyMessage().denyAll()
            .build();
    }

    // @EnableWebSocketSecurity enforces a CSRF token on CONNECT by default. A header-JWT
    // SPA has no CSRF token, so every CONNECT is rejected with an ERROR frame - disable
    // STOMP CSRF via the no-op interceptor when auth is CONNECT-frame JWT:
    @Bean(name = "csrfChannelInterceptor")
    ChannelInterceptor noopCsrfChannelInterceptor() { return new ChannelInterceptor() {}; }
}
```

`simpSubscribeDestMatchers` guards SUBSCRIBE; `simpDestMatchers` guards SEND. Both are needed - a SEND-only rule lets attackers subscribe.

Claim-scoped subscriptions (`/topic/region.{region}`, per-tenant feeds): matchers cannot compare the destination to a principal claim - use `.access(...)` with a custom manager:

```java
.simpSubscribeDestMatchers("/topic/region.{region}").access((auth, ctx) ->
    new AuthorizationDecision(ctx.getVariables().get("region")
        .equals(((JwtAuthenticationToken) auth.get()).getToken().getClaimAsString("region"))))
```

### Controller + per-user send

```java
@Controller
@RequiredArgsConstructor
public class ChatController {
    private final SimpMessagingTemplate template;
    private final ChatService chatService;

    @MessageMapping("/chat.send")
    public void send(@Payload ChatMessageDTO msg, Principal principal) {
        ChatMessageDTO saved = chatService.save(msg, principal.getName());
        template.convertAndSend("/topic/chat." + msg.roomId(), saved);
    }

    @MessageMapping("/chat.private")
    public void privateMessage(@Payload PrivateMessageDTO m, Principal sender) {
        // Authorize the relationship: never trust recipientId from the payload alone -
        // destination matchers don't cover business rules (e.g. blocked users, non-contacts).
        chatService.assertCanMessage(sender.getName(), m.recipientId());
        template.convertAndSendToUser(m.recipientId(), "/queue/messages", m);
    }

    @MessageExceptionHandler
    @SendToUser("/queue/errors")
    public ErrorDTO handle(Exception ex) {
        return new ErrorDTO(ex.getMessage());
    }
}
```

### Connection lifecycle

```java
@Component
@RequiredArgsConstructor
public class WebSocketEventListener {
    private final UserPresenceService presence;

    @EventListener
    public void onConnect(SessionConnectedEvent e) {
        presence.markOnline(e.getUser().getName()); // service publishes to /topic/presence
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent e) {
        presence.markOffline(e.getUser().getName());
    }
}
```

Keep broadcasting inside the service - listeners stay thin and the presence rule (debounce, last-write-wins) lives in one place.

### Reverse proxy

Behind nginx/ALB: forward `Upgrade` / `Connection` headers, set `proxy_read_timeout` above the heartbeat interval (default 60s drops idle WS). Use `setAllowedOriginPatterns(...)` (not `setAllowedOrigins`) when CORS varies by tenant or `X-Forwarded-Host` is rewritten.

## Output Format

```
Endpoint: {WebSocket path, e.g. /ws}
Protocol: {STOMP | raw WebSocket}
Auth: {CONNECT-frame JWT | handshake JWT | session}
Broker: {simple in-process | STOMP relay (RabbitMQ/Artemis/ActiveMQ)}
Destinations: {/topic/*, /queue/* patterns}
Heartbeat: {client ms, server ms}
Limits: {message size, send buffer, send time}
Multi-instance: {yes via relay | single instance only}
```

## Avoid

- Authenticating per message instead of once at CONNECT
- `synchronized` in `@MessageMapping` / interceptors (Virtual Thread pinning)
- Authorizing only SEND while leaving SUBSCRIBE open
- Shipping `enableSimpleBroker` to a multi-instance deployment
- Omitting heartbeat or transport size limits
- Swallowing exceptions instead of `@MessageExceptionHandler` (session dies silently)
