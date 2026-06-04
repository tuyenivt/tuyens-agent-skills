---
name: regression-preflight
description: Preflight host checks for outside-in regression - docker daemon, disk space, declared host ports, host/container clock skew. Stable exit codes.
metadata:
  category: testing
  tags: [regression, preflight, docker, ci, infrastructure]
user-invocable: false
---

# Regression Preflight

Host-side gating before `docker compose up`. Each check has a named exit code so CI can react to a specific failure without parsing log text.

## When to Use

- During `task-regression` Step 2, after `docker version` succeeds and `services.yaml` is parsed.
- During `task-regression-discover` final report, as a smoke check.

## Rules

1. **Exit codes are stable.** CI must be able to match on `exit==21` etc. without parsing log lines.

   | Code | Failure |
   | --- | --- |
   | `0` | All checks passed |
   | `20` | `docker info` failed (daemon unreachable) |
   | `21` | Free disk under threshold at docker root |
   | `22` | Declared host port already bound |
   | `23` | Host/container clock skew over threshold (post-`up`) |

2. **Disk threshold default 5 GiB at the docker root.** Configurable via `.regression/config.json#preflight.diskMinGib`. The skill computes the docker root via `docker info --format '{{.DockerRootDir}}'`.
3. **Port checks only when `services.yaml` declares host port mappings.** Default config declares none; skip silently when none. Probe with `ss -tlnp` (Linux), `lsof -i -P` (mac), `netstat -ano` (Windows). Any one matching listener -> exit 22.
4. **Clock skew check fires AFTER `up --wait`,** because it needs a healthy container. Diff `date -u +%s` host vs the first healthy container; threshold 60 seconds (configurable via `.regression/config.json#preflight.clockSkewMaxSec`).
5. **All-or-nothing reporting.** Aggregate all failures, do not bail on the first. Report every check that failed; exit with the first failing code.

## Patterns

### Canonical preflight script

```bash
#!/usr/bin/env bash
# .regression/scripts/preflight.sh - shipped by regression-preflight
set -euo pipefail

FAIL=0
FIRST_CODE=0
record() {
  local code="$1" msg="$2"
  echo "[preflight] FAIL ($code) - $msg" >&2
  FAIL=1
  [ "$FIRST_CODE" -eq 0 ] && FIRST_CODE="$code"
}

# Check 1: docker daemon
docker info >/dev/null 2>&1 || record 20 "docker info failed; is the daemon running?"

# Check 2: disk space at docker root
DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
DISK_MIN="${REGRESSION_DISK_MIN_GIB:-5}"
FREE_GIB="$(df -BG "$DOCKER_ROOT" 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}')"
if [ -n "$FREE_GIB" ] && [ "$FREE_GIB" -lt "$DISK_MIN" ]; then
  record 21 "free disk at $DOCKER_ROOT is ${FREE_GIB}G, threshold ${DISK_MIN}G"
fi

# Check 3: declared host ports. Reads ports from a colon-separated list piped in.
while IFS= read -r port; do
  [ -z "$port" ] && continue
  if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    record 22 "host port ${port} already bound"
  fi
done < <(echo "${REGRESSION_DECLARED_PORTS:-}" | tr ',' '\n')

exit "$FIRST_CODE"
```

### Post-up clock skew check

```bash
# .regression/scripts/preflight-clock.sh - invoked AFTER up --wait
set -euo pipefail
PROJECT="${1:?compose project required}"
SKEW_MAX="${REGRESSION_CLOCK_SKEW_MAX_SEC:-60}"

HOST_T="$(date -u +%s)"
# Pick the first healthy container (any service)
CID="$(docker ps --filter "label=com.docker.compose.project=$PROJECT" \
       --filter "health=healthy" -q | head -n1)"
[ -z "$CID" ] && exit 0   # nothing to compare; surface as warning only
CT="$(docker exec "$CID" date -u +%s 2>/dev/null || echo "$HOST_T")"

DRIFT=$(( HOST_T > CT ? HOST_T - CT : CT - HOST_T ))
if [ "$DRIFT" -gt "$SKEW_MAX" ]; then
  echo "[preflight] FAIL (23) - host/container clock skew ${DRIFT}s exceeds ${SKEW_MAX}s" >&2
  exit 23
fi
```

### CI matching examples

```bash
# GitHub Actions
if ! .regression/scripts/preflight.sh; then
  case $? in
    20) echo "::error::Docker daemon unreachable" ;;
    21) echo "::error::CI runner is out of disk" ;;
    22) echo "::error::Port conflict on CI runner" ;;
  esac
  exit 1
fi
```

## Output Format

stderr lines `[preflight] FAIL (<code>) - <message>` per failed check. Exit code is the first failure encountered (stable contract). On success: no stderr, exit `0`.

## Avoid

- Bailing after the first failure (CI users want the full picture in one run).
- Coupling exit codes to message text (CI greps on the code).
- Skipping the clock-skew check on CI runners (the most likely place for drift).
- Probing ports the inventory does not declare - hidden races on shared CI runners.
