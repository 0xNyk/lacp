#!/usr/bin/env bash

# Stop Quality Gate — command-type Stop hook for Claude Code
# Evaluates whether Claude is rationalizing incomplete work using a local LLM (ollama).
#
# Workaround for Claude Code v2.1.62 regression where prompt-type Stop hooks
# trigger preventContinuation instead of auto-continuing on rejection.
#
# Uses the same command-type hook API as ralph-wiggum's stop-hook.sh:
#   - exit 0 with no output → allow stop
#   - exit 0 with {"decision": "block", "reason": "..."} → block stop and continue
#
# Dependencies: ollama (running at localhost:11434), jq, curl
# Default model: llama3.1:8b (configurable via LACP_QUALITY_GATE_MODEL)

set -euo pipefail

# Configuration (override via environment)
OLLAMA_URL="${LACP_QUALITY_GATE_URL:-http://localhost:11434/api/chat}"
OLLAMA_MODEL="${LACP_QUALITY_GATE_MODEL:-llama3.1:8b}"
OLLAMA_TIMEOUT="${LACP_QUALITY_GATE_TIMEOUT:-25}"

# Read hook input from stdin
HOOK_INPUT=$(cat)

# Guard: if stop_hook_active is true, allow stop to prevent infinite loops
STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
  exit 0
fi

# Ralph loop state file (cooperate with ralph-wiggum plugin)
RALPH_STATE_FILE=".claude/ralph-loop.local.md"

# Get last assistant message — prefer the direct field, fall back to transcript parsing
LAST_OUTPUT=$(echo "$HOOK_INPUT" | jq -r '.last_assistant_message // empty')

if [[ -z "$LAST_OUTPUT" ]]; then
  # Fallback: parse transcript (older Claude Code versions may not provide the field)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty')

  if [[ -z "$TRANSCRIPT_PATH" ]] || [[ ! -f "$TRANSCRIPT_PATH" ]]; then
    exit 0
  fi

  if ! grep -q '"role":"assistant"' "$TRANSCRIPT_PATH"; then
    exit 0
  fi

  LAST_LINE=$(grep '"role":"assistant"' "$TRANSCRIPT_PATH" | tail -1)
  if [[ -z "$LAST_LINE" ]]; then
    exit 0
  fi

  LAST_OUTPUT=$(echo "$LAST_LINE" | jq -r '
    .message.content |
    map(select(.type == "text")) |
    map(.text) |
    join("\n")
  ' 2>/dev/null || echo "")
fi

if [[ -z "$LAST_OUTPUT" ]]; then
  exit 0
fi

# Truncate to last 2000 chars to keep ollama prompt small and fast
TRUNCATED="${LAST_OUTPUT: -2000}"

# Build system and user messages for chat API
SYSTEM_MSG="You are a binary quality gate. You evaluate AI assistant responses for rationalization of incomplete work. Respond with ONLY a JSON object, no other text."

USER_MSG="Is this AI assistant making excuses for not completing its task?

REJECT (respond ok=false) ONLY if the assistant is making excuses:
- Blaming \"pre-existing\" issues or calling things \"out of scope\"
- Saying there are \"too many\" problems to handle
- Promising to finish in a \"follow-up\" the user never asked for
- Identifying bugs/issues but NOT fixing them (just describing them)
- Saying it is \"done\" but never actually ran tests or verification

ACCEPT (respond ok=true) if the assistant DID the work. A numbered list of COMPLETED actions is fine. Descriptions of what was FIXED or CHANGED are fine.

JSON only:
{\"ok\": false, \"reason\": \"You are rationalizing incomplete work. [what excuse was used]. Go back and finish.\"}
{\"ok\": true}

RESPONSE:
${TRUNCATED}"

# Call ollama chat API with temperature 0 for deterministic output
# curl --max-time handles timeout natively on macOS (no GNU coreutils needed)
OLLAMA_RESPONSE=$(curl -s --max-time "$OLLAMA_TIMEOUT" "$OLLAMA_URL" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg model "$OLLAMA_MODEL" \
    --arg system "$SYSTEM_MSG" \
    --arg user "$USER_MSG" \
    '{
      model: $model,
      messages: [
        {role: "system", content: $system},
        {role: "user", content: $user}
      ],
      stream: false,
      options: {temperature: 0, num_predict: 128}
    }')" \
  2>/dev/null || echo "")

if [[ -z "$OLLAMA_RESPONSE" ]]; then
  # Ollama unreachable or timed out — safe default: allow stop
  exit 0
fi

# Extract the model's text response (chat API returns .message.content)
MODEL_TEXT=$(echo "$OLLAMA_RESPONSE" | jq -r '.message.content // empty' 2>/dev/null || echo "")

if [[ -z "$MODEL_TEXT" ]]; then
  exit 0
fi

# Parse the model response as JSON directly
# If the model wrapped it in markdown, strip code fences first
# Use /usr/bin/sed explicitly to avoid user aliases (e.g. sed→sd)
CLEAN_TEXT=$(echo "$MODEL_TEXT" | /usr/bin/sed 's/^```json//;s/^```//;s/```$//' | tr -d '\n')

# Use jq to parse — handles nested braces correctly (unlike grep -o '{[^}]*}')
# IMPORTANT: jq's // operator treats boolean false as falsy, so we must use
# explicit null checks instead of '.ok // true'
IS_OK=$(echo "$CLEAN_TEXT" | jq -r 'if .ok == null then "true" elif .ok then "true" else "false" end' 2>/dev/null || echo "true")
REASON=$(echo "$CLEAN_TEXT" | jq -r '.reason // empty' 2>/dev/null || echo "")

if [[ "$IS_OK" == "true" ]] || [[ "$IS_OK" != "false" ]] || [[ -z "$REASON" ]]; then
  # Quality gate passed (or ambiguous result) — allow stop
  exit 0
fi

# Quality gate FAILED — behavior depends on ralph loop state

if [[ -f "$RALPH_STATE_FILE" ]]; then
  # Ralph loop active — don't block (ralph-wiggum handles continuation)
  # Inject quality feedback as a system message so Claude sees it next iteration
  jq -n \
    --arg reason "$REASON" \
    '{
      "decision": "allow",
      "systemMessage": ("Quality gate feedback: " + $reason)
    }'
  exit 0
fi

# No ralph loop — block stop and feed reason back as continuation prompt
jq -n \
  --arg reason "$REASON" \
  '{
    "decision": "block",
    "reason": $reason
  }'

exit 0
