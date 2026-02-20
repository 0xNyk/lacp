#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: e2b-runner.sh -- <command> [args...]

Modes:
1) Existing sandbox mode (requires E2B_SANDBOX_ID + e2b CLI):
   - Executes inside an already-running sandbox.
2) Lifecycle mode (default if E2B_SANDBOX_ID is unset):
   - Uses E2B SDK to create sandbox -> execute command -> kill sandbox.

Required env:
- E2B_API_KEY (for lifecycle mode)

Optional env:
- E2B_SANDBOX_ID=<sandbox-id>           Enable existing sandbox mode
- E2B_CLI_BIN=<path-to-e2b-cli>         (default: e2b)
- E2B_TEMPLATE=<template>               (default: base)
- E2B_TIMEOUT_MS=<milliseconds>         (default: 300000)
- E2B_NODE_LAUNCHER=<launcher command>  (default: auto-detect node or npx)

Examples:
- Lifecycle mode:
  E2B_API_KEY=... e2b-runner.sh -- python3 -V
- Existing sandbox mode:
  E2B_SANDBOX_ID=sbx_123 e2b-runner.sh -- python3 -V
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$1" != "--" ]]; then
  echo "[e2b-runner] expected '--' before command" >&2
  exit 1
fi
shift

if [[ $# -eq 0 ]]; then
  echo "[e2b-runner] missing command" >&2
  exit 1
fi

E2B_CLI_BIN="${E2B_CLI_BIN:-e2b}"
E2B_SANDBOX_ID="${E2B_SANDBOX_ID:-}"
E2B_TIMEOUT_MS="${E2B_TIMEOUT_MS:-300000}"
E2B_TEMPLATE="${E2B_TEMPLATE:-base}"

if [[ -n "${E2B_SANDBOX_ID}" ]]; then
  command -v "${E2B_CLI_BIN}" >/dev/null 2>&1 || {
    echo "[e2b-runner] ${E2B_CLI_BIN} CLI not found (required for E2B_SANDBOX_ID mode)." >&2
    exit 2
  }
  exec "${E2B_CLI_BIN}" sandbox exec "${E2B_SANDBOX_ID}" -- "$@"
fi

if [[ -z "${E2B_API_KEY:-}" ]]; then
  echo "[e2b-runner] E2B_API_KEY is required for lifecycle mode." >&2
  exit 3
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[e2b-runner] jq is required." >&2
  exit 4
fi

CMD_JSON="$(printf '%s\n' "$@" | jq -R . | jq -s .)"

NODE_SCRIPT="$(mktemp)"
trap 'rm -f "${NODE_SCRIPT}"' EXIT

cat > "${NODE_SCRIPT}" <<'NODE'
import { Sandbox } from "@e2b/code-interpreter";

function shellQuote(value) {
  if (value === "") return "''";
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

async function main() {
  const cmd = JSON.parse(process.env.LACP_E2B_CMD_JSON || "[]");
  if (!Array.isArray(cmd) || cmd.length === 0) {
    throw new Error("LACP_E2B_CMD_JSON is empty or invalid");
  }

  const timeoutMs = Number(process.env.E2B_TIMEOUT_MS || "300000");
  const template = process.env.E2B_TEMPLATE || "base";
  const command = cmd.map(shellQuote).join(" ");

  let sandbox;
  try {
    sandbox = await Sandbox.create(template, { timeoutMs });
    const result = await sandbox.commands.run(command, { timeoutMs });

    const stdout = result?.stdout ?? "";
    const stderr = result?.stderr ?? "";
    const exitCode = Number(result?.exitCode ?? result?.exit_code ?? result?.code ?? 0);

    if (stdout) process.stdout.write(String(stdout));
    if (stderr) process.stderr.write(String(stderr));
    process.exit(exitCode);
  } finally {
    if (sandbox) {
      try {
        await sandbox.kill();
      } catch {
        // ignore cleanup error
      }
    }
  }
}

main().catch((err) => {
  process.stderr.write(`[e2b-runner] ${err?.message || String(err)}\n`);
  process.exit(5);
});
NODE

LAUNCHER="${E2B_NODE_LAUNCHER:-}"
if [[ -z "${LAUNCHER}" ]]; then
  if command -v node >/dev/null 2>&1 && node -e "require.resolve('@e2b/code-interpreter')" >/dev/null 2>&1; then
    LAUNCHER="node"
  elif command -v npx >/dev/null 2>&1; then
    LAUNCHER="npx -y -p @e2b/code-interpreter@latest node"
  else
    echo "[e2b-runner] No node launcher available. Install node+npx or set E2B_NODE_LAUNCHER." >&2
    exit 6
  fi
fi

export LACP_E2B_CMD_JSON="${CMD_JSON}"
export E2B_TIMEOUT_MS
export E2B_TEMPLATE

exec bash -lc "${LAUNCHER} \"${NODE_SCRIPT}\""
