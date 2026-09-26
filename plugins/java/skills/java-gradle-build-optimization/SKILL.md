---
name: java-gradle-build-optimization
description: "Gradle for Spring Boot multi-module: Kotlin DSL, version catalog, build/config cache, convention plugins, toolchains, scope hygiene."
metadata:
  category: backend
  tags: [gradle, build, spring-boot, multi-module, performance]
user-invocable: false
---

# Gradle Build Optimization

> Load `Use skill: stack-detect` first to determine the project stack. `Build tool: Maven` with no migration asked: state that this skill covers Gradle builds and Maven-to-Gradle migrations only, and stop. `Build tool: unknown`: proceed only when `settings.gradle*` or `gradlew` exists.

## When to Use

- New Spring Boot Gradle project / migration from Maven
- Slow Gradle builds (local clean, incremental, or CI)
- Multi-module structure needing shared conventions
- Standardizing dependency versions across modules
- Resolving Boot-managed version conflicts and CVE pins via BOM / `platform()`

## Rules

- Kotlin DSL (`.gradle.kts`) for new projects and active modernizations; keep Groovy only in maintenance-only legacy builds
- Dependency and plugin versions live in `gradle/libs.versions.toml`. Two places cannot use the type-safe `libs.*` accessors: the `settings.gradle.kts` `plugins {}` block (carries a literal) and precompiled convention plugins (read versions via `versionCatalogs.named("libs")`, `providers.gradleProperty(...)`, or a plugin extension). A version this skill does not state (a plugin, a CVE fix) is written `(version to confirm)`, never guessed
- Build cache + configuration cache on by default; `org.gradle.parallel` from the second module on (a no-op on a single-module build)
- Shared logic via convention plugins in `build-logic/`, never `allprojects {}` / `subprojects {}`; single-module builds apply plugins directly and introduce `build-logic/` with the second module
- Spring Boot plugin only on application modules: it adds `bootJar` (which fails on a module with no main class) and reclassifies `jar` as `-plain`
- One BOM mechanism per build, used in every module: `platform(libs.spring.boot.bom)` (default; pins with `strictly`) or the `io.spring.dependency-management` plugin (property overrides like `extra["jackson-bom.version"]`). `platform()` covers only the configuration it is declared on - add it to every configuration carrying version-less deps, `annotationProcessor` included; the plugin covers all configurations. The plugin imports Boot's BOM by itself only alongside `org.springframework.boot`; in a library module it imports nothing until `dependencyManagement { imports { mavenBom(SpringBootPlugin.BOM_COORDINATES) } }` (with `alias(libs.plugins.spring.boot) apply false` on the classpath and `import org.springframework.boot.gradle.plugin.SpringBootPlugin`)
- Scopes: `implementation` by default; `api` only when a type appears in the module's public API; `runtimeOnly` for deps never referenced at compile time (JDBC drivers, Flyway DB modules); `annotationProcessor` for processors (MapStruct, `spring-boot-configuration-processor`); Lombok on both `compileOnly` and `annotationProcessor`
- Toolchain declared with the foojay resolver so CI auto-provisions the JDK
- Commit `gradlew` / `gradle-wrapper.jar`; CI invokes only `./gradlew`

## Patterns

### Diagnose before optimizing

Measure first: `./gradlew <task> --scan` (build scan, the richest view), `--profile` (HTML report under `build/reports/profile/`), `:<module>:dependencyInsight --dependency <name> --configuration runtimeClasspath` (who requested a version and why it won; the default `compileClasspath` misses runtime-only deps). "Cache enabled but still slow" is usually cache misses from non-reproducible task inputs (absolute paths, timestamps) - the scan names the miss reason. A Maven-to-Gradle migration has no Gradle baseline: record the Maven wall time (`time mvn -B verify`) as the "before", then `--scan` the Gradle build.

When `test` dominates and the log shows many Spring contexts started, the lever is context reuse in the test suite (`spring-test-integration`), not the build script; the build-side levers are `maxParallelForks` and the integration-test split below.

### Migration mapping and order

| Maven | Gradle |
| --- | --- |
| `<parent>spring-boot-starter-parent` / `<dependencyManagement>` BOM | `platform(libs.spring.boot.bom)` |
| `<properties><x.version>` override of one Boot-managed artifact | `strictly` pin (see Dependency management) |
| `<properties><x-bom.version>` override of a whole family (`jackson-bom.version`: Jackson 3 on Boot 4; Jackson 2 there is `jackson-2-bom.version`) | a second platform: `implementation(platform("tools.jackson:jackson-bom:<version>"))` (Jackson 2: `com.fasterxml.jackson:jackson-bom`) - the higher version wins across the family |
| `<modules>` | `include()` in `settings.gradle.kts` |
| Profile activated on demand (`-Pit`) | Separate task invoked explicitly in CI, not wired into `check` |
| Profile active by default | Task wired into `check` |
| `maven-failsafe-plugin` | `integrationTest` suite (below) |
| `jacoco-maven-plugin` | `jacoco` plugin + `tasks.jacocoTestReport { dependsOn(tasks.test) }` |
| `frontend-maven-plugin` | `com.github.node-gradle.node` plugin (below) |
| `mvnw` | `gradle wrapper --gradle-version <v>` once (Boot 4 supports Gradle 8.14+ and 9.x; a Java 25 toolchain needs 9.1+; Gradle 9 runs on JDK 17+), then commit the wrapper |

Frontend build (node-gradle): the `npm_run_<script>` rule tasks declare no outputs, so register one that does:

```kotlin
node { download.set(true); version.set("22.11.0"); nodeProjectDir.set(file("web")); npmInstallCommand.set("ci") }
val buildFrontend by tasks.registering(com.github.gradle.node.npm.task.NpmTask::class) {
    dependsOn(tasks.npmInstall)
    args.set(listOf("run", "build"))
    inputs.dir("web/src"); outputs.dir("web/dist")
}
tasks.processResources { from(buildFrontend) { into("static") } }
```

Order for modernizing any existing multi-module build (Maven or Groovy DSL): version catalog first, then convention plugins (kills `allprojects`), then per-module DSL flip - each step ships independently.

### Version catalog

`gradle/libs.versions.toml` - hyphens in keys become dots in accessors (`spring-boot-starter-webmvc` -> `libs.spring.boot.starter.webmvc`):

```toml
[versions]
spring-boot = "4.1.1"            # pin the current 4.1.x patch
dependency-analysis = "2.19.0"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-starter-webmvc = { module = "org.springframework.boot:spring-boot-starter-webmvc" }   # Boot 4 name; Boot 3: spring-boot-starter-web
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-webmvc-test = { module = "org.springframework.boot:spring-boot-starter-webmvc-test" }   # per-technology test starters; Boot 3: spring-boot-starter-test

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
dependency-analysis = { id = "com.autonomousapps.dependency-analysis", version.ref = "dependency-analysis" }
```

Boot-managed libraries get no `version` (the BOM aligns them); pin a version only for deps outside Boot's BOM.

### Toolchain with foojay auto-provisioning

```kotlin
// settings.gradle.kts - the catalog is not reachable here, so the version is a literal
plugins { id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0" }
```

Without it, fresh CI runners fail when no matching JDK is installed. `settings.gradle.kts` is one file: `pluginManagement {}` first, then `plugins {}`, then `rootProject.name` / `include` / `dependencyResolutionManagement` / `buildCache`.

### `gradle.properties` for build speed

```properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
# Some 3rd-party plugins still touch Task.project at execution time - start at warn, flip to fail once green
org.gradle.configuration-cache.problems=warn
org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g -Dfile.encoding=UTF-8
```

### Multi-module via convention plugin

```kotlin
// settings.gradle.kts
pluginManagement {
    includeBuild("build-logic")          // recommended form; the only one that also serves settings plugins
    repositories { gradlePluginPortal(); mavenCentral() }
}
rootProject.name = "acme"
include(":domain", ":app")

dependencyResolutionManagement {
    repositories { mavenCentral() }      // replaces allprojects { repositories {...} }
}
```

`build-logic` is a standalone build: its own `settings.gradle.kts` (`rootProject.name = "build-logic"`), its own repositories, and `kotlin-dsl`:

```kotlin
// build-logic/build.gradle.kts
plugins { `kotlin-dsl` }
repositories { gradlePluginPortal(); mavenCentral() }
```

`Plugin [id: '...'] was not found` for a convention plugin: the file is not under `build-logic/src/main/kotlin/`, `kotlin-dsl` is missing, `build-logic` has no `settings.gradle.kts`, or the id differs - the id is the file name minus `.gradle.kts` (`acme.java-conventions.gradle.kts` -> `acme.java-conventions`), prefixed by its `package` when the script declares one. A top-level `includeBuild` also contributes project plugins, so moving it into `pluginManagement` alone rarely fixes this error.

`build-logic/src/main/kotlin/java-conventions.gradle.kts` - `group`/`version` land here (replacing `allprojects`); `toolchain` replaces `sourceCompatibility`/`targetCompatibility` (delete those):

```kotlin
plugins { java }

group = "com.acme"
version = "0.1.0"

java { toolchain { languageVersion.set(JavaLanguageVersion.of(25)) } }   // Java 25 needs Gradle 9.1+

dependencies {
    "testRuntimeOnly"("org.junit.platform:junit-platform-launcher")   // required from Gradle 9; version from the module's BOM
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxParallelForks = (Runtime.getRuntime().availableProcessors() / 2).coerceAtLeast(1)
}
```

Precompiled script plugins cannot see `libs.*` accessors: catalog-backed declarations stay in module files; version-less or property-versioned ones (the launcher above, a CVE pin via `providers.gradleProperty("jacksonFixVersion").get()`) may live in the convention plugin.

Root `build.gradle.kts` declares shared plugins once so every module loads them in one classloader:

```kotlin
plugins { alias(libs.plugins.spring.boot) apply false }
```

Application module:

```kotlin
plugins {
    id("java-conventions")
    alias(libs.plugins.spring.boot)
}
dependencies {
    implementation(platform(libs.spring.boot.bom))
    annotationProcessor(platform(libs.spring.boot.bom))   // version-less processors resolve too
    implementation(project(":domain"))
    implementation(libs.spring.boot.starter.webmvc)
}
```

Library module - no Spring Boot plugin; the BOM goes on `api` when version-less `api` deps would otherwise reach consumers without a version:

```kotlin
plugins {
    id("java-conventions")
    `java-library`
}
dependencies {
    api(platform(libs.spring.boot.bom))
    api(libs.spring.boot.starter.data.jpa)         // types leak into public API
    implementation(libs.spring.boot.starter.webmvc)   // internal use only
}
```

### `api()` vs `implementation()`

```kotlin
// Bad - downstream modules compile against infrastructure types and recompile whenever its ABI changes
api(project(":infrastructure"))

// Good - encapsulated; only this module's ABI affects downstream compile avoidance
implementation(project(":infrastructure"))
```

Whether a module's public API exposes another module's types is not visible from build files - `buildHealth` (below) reports it.

### Dependency management and CVE pins

```kotlin
// Avoid failOnVersionConflict() with the Spring BOM - the BOM intentionally overrides
// transitive requests, so it reports dozens of expected "conflicts".

// Pin a patched transitive under platform() - one artifact, fails the build if unsatisfiable:
dependencies {
    implementation("tools.jackson.core:jackson-databind") {   // Jackson 3 on Boot 4; Boot 3, or a Jackson 2 CVE on Boot 4: com.fasterxml.jackson.core
        version { strictly(libs.versions.jackson.fix.get()) }   // catalog: jackson-fix = "<first fixed version>"
    }
}
// Under the dependency-management plugin instead: extra["jackson-bom.version"] = libs.versions.jackson.fix.get()
// (realigns the whole family). It is silently a no-op in modules that use platform() -
// the usual reason a scanner still reports the old version in one module.
```

The pin value is the first fixed version from the advisory, and it must be at or above the version the BOM already manages - a pin below it downgrades. Confirm with `dependencyInsight`; when the fixed version is unknown, write the block with `(version to confirm)` rather than a guess. Multi-module: put the pin where every module sees it (the convention plugin, with the version from `gradle.properties`). On every Boot upgrade, delete pins the new BOM already clears.

```kotlin
dependencyLocking { lockAllConfigurations() }
// ./gradlew dependencies --write-locks  (commit gradle.lockfile) - reproducible builds, relock on every bump
```

### Dependency hygiene

```kotlin
// root build.gradle.kts - the plugin must be applied at the root (per-project application is optional)
plugins { alias(libs.plugins.dependency.analysis) }
// ./gradlew buildHealth
```

Surfaces unused deps and `api`/`implementation` misdeclarations the `api()` rule alone cannot catch.

### Spring Boot bootJar (application module only)

Layering is on by default - never present `layered {}` as an optimization. The Docker-rebuild benefit needs a Dockerfile that extracts layers: `java -Djarmode=tools -jar app.jar extract --layers --launcher` (Boot 3.3+; older 3.x uses `-Djarmode=layertools`, which Boot 4.1 removed).

AOT: `processAot` exists only when `org.springframework.boot.aot` is applied - directly, or by the Boot plugin when `org.graalvm.buildtools.native` is applied alongside it; it is enabled by default then. Native image: apply the native plugin and run `./gradlew nativeCompile`.

### Integration tests (JVM Test Suite)

```kotlin
// build-logic/.../java-conventions.gradle.kts
testing {
    suites {
        val test by getting(JvmTestSuite::class)
        register<JvmTestSuite>("integrationTest") {
            dependencies { implementation(project()) }
            targets.all { testTask.configure { shouldRunAfter(test) } }
        }
    }
}
configurations["integrationTestImplementation"].extendsFrom(configurations.testImplementation.get())
configurations["integrationTestRuntimeOnly"].extendsFrom(configurations.testRuntimeOnly.get())
```

Sources live in `src/integrationTest/java`. Wire `integrationTest` into `check` only when it should run on every build. A non-default suite uses JUnit Jupiter at Gradle's bundled version - pin it to the BOM's (`useJUnitJupiter("<BOM junit version>")`) when they differ, or launcher/engine skew breaks discovery.

### CI

Default: `gradle/actions/setup-gradle@v4` - it caches the dependency and wrapper caches, and with `cache-encryption-key` set it also saves the configuration cache across ephemeral runners.

```yaml
- uses: actions/setup-java@v4
  with: { distribution: temurin, java-version: '25' }
- uses: gradle/actions/setup-gradle@v4
  with:
    cache-encryption-key: ${{ secrets.GRADLE_ENCRYPTION_KEY }}
- run: ./gradlew check
- run: ./gradlew integrationTest
```

CI runs only `./gradlew` - never a `gradle` from the runner's PATH or an install step masked with `|| true`. Flags already set in `gradle.properties` (`--parallel`, `--build-cache`) need not be repeated. `--no-daemon` only stops a daemon from lingering after the build; when `org.gradle.jvmargs` differs from the client JVM, Gradle still forks a single-use daemon. Keep the daemon on self-hosted runners that persist across jobs.

Fallback without the action - key on every build-defining file, and expect stale entries to accumulate under `restore-keys`:

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-${{ hashFiles('**/*.gradle*', 'gradle/libs.versions.toml', '**/gradle-wrapper.properties') }}
    restore-keys: gradle-
```

With `actions/cache` the configuration cache (`<project>/.gradle/configuration-cache`) does not survive an ephemeral runner - claim no ephemeral-CI delta for it there.

Remote build cache (the biggest multi-module CI win) needs an existing cache node (Develocity or an HTTP cache server); with none, stay on the CI cache above rather than emitting placeholder config:

```kotlin
// settings.gradle.kts
buildCache {
    local { isEnabled = true }
    remote<HttpBuildCache> {
        url = uri("https://cache.example.com/cache/")
        isPush = System.getenv("CI") == "true"
        credentials {
            username = System.getenv("GRADLE_CACHE_USER")
            password = System.getenv("GRADLE_CACHE_PASSWORD")
        }
    }
}
```

## Output Format

Emit in this order: the `**Stack:**` line (Gradle version from `distributionUrl` in `gradle/wrapper/gradle-wrapper.properties`, DSL from the build-script extension, `unknown` when absent), the measurement commands (on a migration, the Maven baseline command and the post-migration `--scan`), the full contents of every file the change needs (when the input is fragments, the touched sections), then one block per optimization.

```
**Stack:** {Gradle <version> (Kotlin DSL | Groovy DSL) | Maven -> Gradle migration}, {single-module | <n> modules}
```

```
Optimization: {dsl-migration | version-catalog | build-cache-local | build-cache-remote | configuration-cache | parallel | convention-plugin | scope | bom-platform | security-pin | conflict-resolution | locking | dependency-analysis | toolchain | test-sourceset | ci-cache | ci-workflow | other:<label>}

File: {repo path(s) - every touched file for a multi-file optimization}

Change: {summary diff - one line per touched file}

Priority: {High | Medium | Low}

Effort: {Trivial | Small | Medium | Large}

Expected Impact: {clean delta | incremental delta | ci delta | maintainability | correctness} - {quantified when estimable, e.g. "clean delta ~-25%"}{ (unmeasured estimate)}

Risk: {None | Plugin-incompat | Behavior-change}
```

One block per optimization; a file may appear in several blocks. `other:<label>` when no enum value fits. Priority: High = direct build-time win on its own, or a build-breaking / security fix; Medium = enabler or hygiene with indirect effect; Low = maintainability only. Expected Impact numbers come from `--scan`/`--profile` data; without it, append `(unmeasured estimate)`.

Close with `Aggregate: estimated clean-build reduction ~X%; incremental/no-op reduction ~Y%; CI reduction ~Z%` (terms with no contributing block omitted) when at least one block's Expected Impact is a build-time delta; otherwise `Aggregate: no build-time change - correctness/maintainability only`.

## Avoid

- Hardcoded versions in module build scripts (the catalog is the single source of truth)
- `failOnVersionConflict()` with the Spring BOM
- Two BOM mechanisms in one build
- Toolchain declaration without the foojay resolver
- Referencing `tasks.processAot` / native tasks when their plugin isn't applied (the script fails to evaluate)
