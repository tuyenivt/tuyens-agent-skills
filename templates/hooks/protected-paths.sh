#!/usr/bin/env bash
# protected-paths.sh - PreToolUse guard for the Bash tool.
#
# Blocks shell writes into files that control host-side execution, and any command that references a credential path or a real .env file.
#
# This exists because permission rules only reach the Edit and Write tools.
# Edit(**/.claude/settings.json) does not stop `sed -i` from rewriting the same file through the Bash tool, and Bash(sed:*) is allowlisted.

IN=$(cat)

# Shell writes (redirect, tee, or sed) into a file that controls execution.
if printf '%s' "$IN" | grep -qiE '((>>?|[|;&][[:space:]]*tee[[:space:]])[^|;&]*|(^|[[:space:];&|("])sed[[:space:]][^|;&]*)(\.devcontainer/|devcontainer\.json|\.husky/|\.git/hooks/|\.claude/settings|\.claude/hooks/)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: shell write into a protected file (devcontainer config, git hooks, or claude settings/hooks). These files control host-side execution and must not be modified by the agent."}}'
  exit 0
fi

# Any reference to a credential path.
if printf '%s' "$IN" | grep -qiE '\.ssh/|\.aws/|\.gnupg/|id_rsa|id_ed25519|\.netrc|\.pgpass|master\.key|\.bundle/config|\.gem/credentials|\.pem([^A-Za-z0-9_]|$)|\.p12([^A-Za-z0-9_]|$)|\.pfx([^A-Za-z0-9_]|$)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: command references a credential path (ssh/aws/gnupg keys, netrc, pgpass, certificates)."}}'
  exit 0
fi

# .env files, except the example/sample/template variants.
if printf '%s' "$IN" | grep -qiE '\.env([^A-Za-z0-9_]|$)|\.envrc' && ! printf '%s' "$IN" | grep -qiE '\.env[._-]?(example|sample|template|dist)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: command references a .env file. Only .env.example/.env.sample style files may be touched."}}'
  exit 0
fi

exit 0
