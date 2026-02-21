#!/usr/bin/env bash
set -euo pipefail

# One-liner launcher:
# ./codex_with_dual_graph.sh <server_url> <project_root> "<prompt>" [api_token]
#
# Example:
# ./codex_with_dual_graph.sh \
#   "https://your-service.up.railway.app" \
#   "/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm" \
#   "Call graph_continue first and keep context minimal."

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <server_url> <project_root> <prompt> [api_token]" >&2
  exit 2
fi

SERVER_URL="$1"
PROJECT_ROOT="$2"
PROMPT="$3"
API_TOKEN="${4:-${DG_API_TOKEN:-}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_PY="$SCRIPT_DIR/.venv-mcp/bin/python"
MCP_SERVER="$SCRIPT_DIR/mcp_graph_server.py"

if [[ ! -x "$MCP_PY" ]]; then
  echo "Missing venv python: $MCP_PY" >&2
  echo "Create it with:" >&2
  echo "python3 -m venv \"$SCRIPT_DIR/.venv-mcp\" && \"$SCRIPT_DIR/.venv-mcp/bin/python\" -m pip install mcp" >&2
  exit 2
fi

codex mcp remove dual-graph >/dev/null 2>&1 || true

MCP_ADD_CMD=(
  codex mcp add dual-graph
  --env "DG_BASE_URL=$SERVER_URL"
  --env "DUAL_GRAPH_PROJECT_ROOT=$PROJECT_ROOT"
  --env "DG_HARD_MAX_READ_CHARS=3200"
  --env "DG_TURN_READ_BUDGET_CHARS=12000"
  --env "DG_ENFORCE_REUSE_GATE=1"
  --env "DG_ENFORCE_SINGLE_RETRIEVE=1"
  --env "DG_ENFORCE_READ_ALLOWLIST=1"
  --env "DG_FALLBACK_MAX_CALLS_PER_TURN=1"
  --env "DG_RETRIEVE_CACHE_TTL_SEC=900"
)

if [[ -n "$API_TOKEN" ]]; then
  MCP_ADD_CMD+=( --env "DG_API_TOKEN=$API_TOKEN" )
fi

MCP_ADD_CMD+=( -- "$MCP_PY" "$MCP_SERVER" )

"${MCP_ADD_CMD[@]}"

POLICY="Call graph_continue first. If mode=memory_first, use only recommended_files with graph_read. If insufficient, do one graph_retrieve and then graph_read. Avoid full chat-history dumps. Use fallback_rg only as last resort."

codex -C "$PROJECT_ROOT" "$POLICY $PROMPT"

