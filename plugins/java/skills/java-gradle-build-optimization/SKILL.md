---
name: java-gradle-build-optimization
description: "Gradle for Spring Boot multi-module: Kotlin DSL, version catalog, build/config cache, convention plugins, toolchains, scope hygiene."
metadata:
  category: backend
  tags: [gradle, build, spring-boot, multi-module, performance]
user-invocable: false
---

# Gradle Build Optimization

> Load `Use skill: stack-detect` first to determine the project stack. If the build tool is Maven, stop and use a Maven-focused skill.

## When to Use

- New Spring Boot Gradle project / migration from Maven
- Slow Gradle builds (local clean, incremental, or CI)
- Multi-module structure needing shared conventions
- Standardizing dependency versions across modules
- Resolving Boot-managed version conflicts via BOM / `platform()`

## Rules

- Kotlin DSL (`.gradle.kts`) for new projects and active modernizations; keep Groovy only in maintenance-only legacy builds
- All dependency and plugin versions in `gradle/libs.versions.toml`
- Parallel + build cache + configuration cache on by default
- Shared logic via convention plugins in `build-logic/`, never `allprojects {}` / `subprojects {}`
- Spring Boot plugin only on application modules (it disables `jar` and produces `bootJar`)
- `implementation()` is the default; `api()` only when a type appears in the module's public API; `runtimeOnly` for deps never referenced at compile time (JDBC drivers, Flyway DB modules); `compileOnly` for compile-time-only (annotation processors, Lombok)
- Toolchain declared with foojay resolver so CI auto-provisions the JDK
- Commit `gradlew` / `gradle-wrapper.jar`; CI invokes only `./gradlew`

## Patterns

### Version catalog

`gradle/libs.versions.toml` - hyphens in keys become dots in accessors (`spring-boot-starter-web` -> `libs.spring.boot.starter.web`):

```toml
[versions]
spring-boot = "3.5.0"
spring-dep-mgmt = "1.1.7"

[libraries]
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
spring-dep-mgmt = { id = "io.spring.dependency-management", version.ref = "spring-dep-mgmt" }
```

Versioning policy: Boot-managed libraries get no `version` entry (the `platform()` BOM aligns them); pin `version`/`version.ref` only for deps outside Boot's BOM.

```kotlin
dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(libs.spring.boot.starter.web)
    testImplementation(libs.spring.boot.starter.test)
}
```

### Toolchain with foojay auto-provisioning

`settings.gradle.kts`:

```kotlin
plugins { id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0" }  // use latest release
```

Without this, fresh CI runners fail when no matching JDK is found.

### Diagnose before optimizing

Measure where the time goes before changing anything: `./gradlew <task> --scan` (shareable build scan, the richest view), `--profile` (HTML timing report under `build/reports/profile/`), and `:<module>:dependencyInsight --dependency <name>` to trace a version conflict to its requester. "Cache enabled but still slow" is usually cache misses from non-reproducible task inputs (absolute paths, timestamps) - a build scan shows the miss reasons.

### `gradle.properties` for build speed

```properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
# Spring Boot 3.5 + AOT is config-cache compatible. Some 3rd-party plugins
# still access Task.project at execution time - start with `warn`, flip to
# `fail` once the build is green.
org.gradle.configuration-cache.problems=warn
org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g -XX:+UseG1GC
```

### Multi-module via convention plugin

Wire the modules and the `build-logic` included build in the root `settings.gradle.kts` first - without `includeBuild` the convention plugin id does not resolve:

```kotlin
rootProject.name = "acme"
includeBuild("build-logic")
include(":domain", ":app")

dependencyResolutionManagement {
    repositories { mavenCentral() }   // replaces allprojects { repositories {...} }
}
```

`build-logic/build.gradle.kts` needs the `kotlin-dsl` plugin so its `*.gradle.kts` files compile to plugins, plus its own repositories (an included build does not inherit the main build's):

```kotlin
plugins { `kotlin-dsl` }
repositories {
    gradlePluginPortal()
    mavenCentral()
}
```

`build-logic/src/main/kotlin/java-conventions.gradle.kts` - `group`/`version` land here (replacing `allprojects`); `toolchain` replaces `sourceCompatibility`/`targetCompatibility` (delete those):

```kotlin
plugins { java }

group = "com.acme"
version = "0.1.0"

java { toolchain { languageVersion.set(JavaLanguageVersion.of(21)) } }

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxParallelForks = (Runtime.getRuntime().availableProcessors() / 2).coerceAtLeast(1)
}
```

Application module:

```kotlin
plugins {
    id("java-conventions")
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spring.dep.mgmt)
}
dependencies {
    implementation(project(":domain"))
    implementation(libs.spring.boot.starter.web)
}
```

Library module - no Spring Boot plugin (it would produce an unwanted `bootJar` and disable the regular `jar`):

```kotlin
plugins {
    id("java-conventions")
    `java-library`
}
dependencies {
    implementation(platform(libs.spring.boot.bom))
    api(libs.spring.boot.starter.data.jpa)         // types leak into public API
    implementation(libs.spring.boot.starter.web)   // internal use only
}
```

### `api()` vs `implementation()`

```kotlin
// Bad - downstream modules see infrastructure types and recompile on every change
api(project(":infrastructure"))

// Good - encapsulated; only this module's ABI affects downstream compile avoidance
implementation(project(":infrastructure"))
```

### Dependency management

```kotlin
dependencies {
    implementation(platform(libs.spring.boot.bom))   // BOM aligns transitive versions
}

// Avoid `failOnVersionConflict()` with Spring BOM - the BOM intentionally
// pins versions that may conflict with transitive requests.

// Resolve a specific conflict (e.g. CVE-patched transitive) one of two ways:
ext["jackson-bom.version"] = "2.18.2"   // override a Boot-managed BOM property (Spring's idiom)
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind") {
        version { strictly("2.18.2") }   // hard pin one dependency, fails the build if unsatisfiable
    }
}

dependencyLocking { lockAllConfigurations() }
// ./gradlew dependencies --write-locks  (commit gradle.lockfile)
// Tradeoff: reproducible builds vs. needing to relock on every dep bump.
```

### Dependency hygiene

Detect unused / misdeclared dependencies (api leaking as implementation, etc.):

```kotlin
// build-logic/.../java-conventions.gradle.kts
plugins { id("com.autonomousapps.dependency-analysis") }
// ./gradlew buildHealth
```

Run periodically; surface unused deps and incorrect `api`/`implementation` scoping that `api()` rule alone can't catch.

### Spring Boot bootJar (application module only)

```kotlin
tasks.bootJar {
    mainClass.set("com.example.Application")
}
```

Layering is enabled by default in Boot 3.x - do not present `layered {}` as an optimization; the Docker-rebuild benefit only materializes with a layertools-aware Dockerfile.

GraalVM native (only when `org.graalvm.buildtools.native` plugin is applied):

```kotlin
tasks.processAot { enabled = true }
```

### Integration test source set

```kotlin
// build-logic/.../java-conventions.gradle.kts
sourceSets.create("integrationTest") {
    java.srcDir("src/integrationTest/java")
    compileClasspath += sourceSets.main.get().output + configurations.testRuntimeClasspath.get()
    runtimeClasspath += output + compileClasspath
}
val integrationTest by tasks.registering(Test::class) {
    testClassesDirs = sourceSets["integrationTest"].output.classesDirs
    classpath = sourceSets["integrationTest"].runtimeClasspath
    shouldRunAfter("test")
}
```

### CI

Local builds reuse a long-lived daemon (this is what makes incremental fast). On ephemeral CI runners the daemon's JVM dies with the container, so `--no-daemon` avoids a wasted warmup; on self-hosted runners that persist across jobs, keep the daemon.

```bash
./gradlew check --parallel --build-cache --no-daemon                 # ephemeral CI
./gradlew integrationTest --parallel --build-cache --no-daemon
```

Remote build cache (the biggest multi-module CI win - one job's output feeds the next). Requires an existing cache node (Develocity or an HTTP cache server); when none exists, use the Actions cache below instead of emitting placeholder config:

```kotlin
// settings.gradle.kts
buildCache {
    local { isEnabled = true }
    remote<HttpBuildCache> {
        url = uri("https://cache.example.com/cache/")
        isPush = System.getenv("CI") == "true"
    }
}
```

GitHub Actions local-cache fallback:

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-${{ hashFiles('**/*.gradle.kts', 'gradle/libs.versions.toml') }}
```

## Output Format

```
Optimization: {dsl-migration | version-catalog | build-cache-local | build-cache-remote | configuration-cache | parallel | convention-plugin | scope | bom-platform | locking | dependency-analysis | toolchain | ci-cache | ci-workflow}
File: {repo path(s) - list all touched files for multi-file optimizations}
Change: {summary diff - one line per touched file}
Priority: {High | Medium | Low}
Effort: {Trivial | Small | Medium | Large}
Expected Impact: {clean delta | incremental delta | maintainability} - {quantify when estimable, e.g. "clean delta ~-25%"}
Risk: {None | Plugin-incompat | Behavior-change}
```

Aggregate: `Aggregate: estimated clean-build reduction (%); incremental/no-op reduction (%) when changed`.

## Avoid

- Hardcoded versions in `build.gradle.kts` (catalog is the single source of truth)
- `failOnVersionConflict()` with Spring BOM (BOM conflicts are expected and intentional)
- Toolchain declaration without foojay resolver (CI breaks on missing JDK)
- AOT / native tasks referenced when their plugin isn't applied (build script fails to evaluate)
