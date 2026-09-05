#!/usr/bin/env bash
# curl-guard.sh - PreToolUse guard for the Bash tool.
#
# Blocks pipe-to-shell, asks on writes, auto-approves read-only fetches.
#
# Note the blast radius of the allow branch: a hook "allow" is terminal for the WHOLE Bash call, so `curl -s URL; rm -rf build` would ride along on the curl approval.
# The allow branch therefore refuses any command that carries a second segment.

input=$(cat)
[ "$(echo "$input" | jq -r '.tool_name // empty')" != "Bash" ] && exit 0
cmd=$(echo "$input" | jq -r '.tool_input.command // empty')

# not a curl command -> defer to normal permissions
echo "$cmd" | grep -Eq '(^|[;&|[:space:]])curl([[:space:]]|$)' || exit 0

# curl piped into an interpreter -> hard block (exit 2 wins over allow rules)
if echo "$cmd" | grep -Eiq 'curl.*\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh|dash|python[0-9.]*|ruby|perl|node)([[:space:]]|$)|<\([[:space:]]*curl'; then
  echo "Blocked: piping remote content from curl into an interpreter." >&2
  exit 2
fi

# write / send-data flags -> ask for confirmation
if echo "$cmd" | grep -Eiq '(-X|--request)[[:space:]]*(POST|PUT|PATCH|DELETE)|(^|[[:space:]])(-d|-F|-T)([[:space:]]|=)|--data(-raw|-binary|-urlencode|-ascii)?|--form|--upload-file|--json'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"curl sends/modifies data - confirm."}}'
  exit 0
fi

# anything chained after the curl -> do not hand out a whole-call allow
if echo "$cmd" | grep -Eq '[;&|]|\$\(|`'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"curl is chained with another command - confirm."}}'
  exit 0
fi

# read-only curl -> auto approve
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"read-only curl"}}'
exit 0
