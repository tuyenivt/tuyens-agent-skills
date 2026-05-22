---
name: spring-websocket
description: "Spring WebSocket / STOMP: handshake auth, CONNECT-frame JWT, message-level security, external broker for multi-instance, Virtual Thread safety."
metadata:
  category: backend
  tags: [websocket, stomp, messaging, real-time, spring]
user-invocable: false
---

# Spring WebSocket

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Real-time bidirectional channels (chat, notifications, live status)
- Server-pushed updates to subscribed clients
- STOMP messaging over WebSocket

## Rules

- Authenticate at handshake (or STOMP `CONNECT` frame via `ChannelInterceptor`) - never per-message
- Prefer CONNECT-frame JWT over query-param tokens (avoids leak to nginx logs / browser history)
- `/topic` for broadcasts, `/queue` (via `convertAndSendToUser`) for user-specific
- For >1 app instance, use an external STOMP relay (RabbitMQ / Artemis) - `enableSimpleBroker` is in-process only
- Set heartbeat to detect stale connections
- Limit message size / send buffer / send time on the transport registry
- No `synchronized` in message handlers - pins Virtual Threads; use `ReentrantLock` / concurrent collections
- Handle exceptions with `@MessageExceptionHandler` - unhandled exceptions close the session silently

## Patterns

### Configuration

```java
@Configuration @EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[]{10000, 10000});
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("${app.cors.origins}")
                .withSockJS();
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration r) {
        r.setMessageSizeLimit(64 * 1024)
         .setSendBufferSizeLimit(512 * 1024)
         .setSendTimeLimit(20_000);
    }
}
```

### Multi-instance: external STOMP relay

`enableSimpleBroker` does not fan out across nodes. For multi-instance, use a relay:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("rabbitmq").setRelayPort(61613)
            .setClientLogin("app").setClientPasscode("${broker.password}");
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user");
}
```

### CONNECT-frame JWT auth

```java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(Message<?> message, MessageChannel channel) {
            var accessor = MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);
            if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
                String bearer = accessor.getFirstNativeHeader("Authorization");
                if (bearer == null || !bearer.startsWith("Bearer "))
                    throw new MessageDeliveryException("Missing Bearer token");
                Jwt jwt = jwtDecoder.decode(bearer.substring(7));
                accessor.setUser(new JwtAuthenticationToken(jwt,
                    AuthorityUtils.createAuthorityList("ROLE_" + jwt.getClaimAsString("role"))));
            }
            return message;
        }
    });
}
```

### Handshake interceptor (alternative)

```java
@Component
public class JwtHandshakeInterceptor implements HandshakeInterceptor {
    public boolean beforeHandshake(ServerHttpRequest req, ServerHttpResponse resp,
                                    WebSocketHandler h, Map<String, Object> attrs) {
        String token = extractToken(req);
        if (token == null || !jwtService.isValid(token)) {
            resp.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }
        attrs.put("userId", jwtService.extractSubject(token));
        return true;
    }
    public void afterHandshake(...) {}
}
```

### Message-level authorization

```java
@Configuration @EnableWebSocketSecurity
public class WebSocketSecurityConfig {
    @Bean
    AuthorizationManager<Message<?>> messageAuthz(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        return messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
            .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
            .simpSubscribeDestMatchers("/user/queue/**").authenticated()
            .anyMessage().authenticated()
            .build();
    }
}
```

### Controllers

```java
@Controller
@RequiredArgsConstructor
public class ChatController {
    private final SimpMessagingTemplate template;

    @MessageMapping("/chat.send")
    public void send(@Payload ChatMessageDTO message, Principal principal) {
        ChatMessageDTO saved = chatService.save(message, principal.getName());
        template.convertAndSend("/topic/chat." + message.roomId(), saved);
    }

    @MessageMapping("/chat.private")
    public void privateMessage(@Payload PrivateMessageDTO m, Principal p) {
        template.convertAndSendToUser(m.recipientId(), "/queue/messages", m);
    }

    @MessageExceptionHandler
    @SendToUser("/queue/errors")
    public String handleException(Exception ex) {
        log.error("WebSocket error", ex);
        return ex.getMessage();
    }
}
```

### Connection lifecycle

```java
@Component
@RequiredArgsConstructor
public class WebSocketEventListener {
    private final SimpMessagingTemplate template;
    private final UserPresenceService presence;

    @EventListener
    public void onConnect(SessionConnectedEvent e) { presence.markOnline(e.getUser().getName()); }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent e) {
        String userId = e.getUser().getName();
        presence.markOffline(userId);
        template.convertAndSend("/topic/presence", new PresenceEvent(userId, "OFFLINE"));
    }
}
```

### Reverse proxy (nginx)

Needs `Upgrade` / `Connection` headers and a long read timeout (default 60s kills idle WS).

```nginx
location /ws {
    proxy_pass http://app:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 3600s;
}
```

Behind `X-Forwarded-Host`, use `setAllowedOriginPatterns(...)` instead of `setAllowedOrigins(...)`.

## Output Format

```
Endpoint: {WebSocket path}
Protocol: {STOMP | raw WebSocket}
Auth: {handshake JWT | CONNECT-frame JWT | session | none}
Broker: {simple in-process | STOMP relay (RabbitMQ/Artemis)}
Topics: {/topic and /queue destinations}
Heartbeat: {interval ms}
Message Limit: {max size}
```

## Avoid

- `synchronized` blocks in message handlers (pins Virtual Threads)
- Missing heartbeat (stale connections accumulate)
- Per-message authentication (authenticate once at handshake/CONNECT)
- Broadcasting sensitive data on `/topic` (use `/queue` for user-specific)
- `enableSimpleBroker` in multi-instance deployments
