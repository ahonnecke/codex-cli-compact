#!/usr/bin/env bash
# Start dual-graph MCP server locally for a given project root.
#
# Usage:
#   ./run_local.sh /path/to/your/project
#
# Then in another terminal:
#   codex --mcp-server-uri http://localhost:8080/sse "your task"
#
# Or scan from within codex by calling graph_scan("/path/to/project").

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-$(pwd)}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"  # resolve to absolute path

INTERNAL_PORT=8787
MCP_PORT=8080

export DUAL_GRAPH_PROJECT_ROOT="$PROJECT_ROOT"
export DG_BASE_URL="http://127.0.0.1:$INTERNAL_PORT"

echo "[dg] Project root : $PROJECT_ROOT"
echo "[dg] Dashboard    : http://127.0.0.1:$INTERNAL_PORT"
echo "[dg] MCP SSE      : http://127.0.0.1:$MCP_PORT/sse"
echo ""

# ── Build initial info graph ──────────────────────────────────────────────────
echo "[dg] Scanning project..."
python3 "$SCRIPT_DIR/graph_builder.py" --root "$PROJECT_ROOT" --out "$SCRIPT_DIR/data/info_graph.json"
echo "[dg] Scan complete."
echo ""

# ── Start dashboard API (internal) ────────────────────────────────────────────
PORT=$INTERNAL_PORT python3 "$SCRIPT_DIR/server.py" &
DASH_PID=$!
trap 'kill $DASH_PID 2>/dev/null; exit' INT TERM EXIT

# Wait for dashboard to be ready (up to 15s)
for i in $(seq 1 15); do
    if python3 - <<'PY' 2>/dev/null
import urllib.request, sys
try:
    urllib.request.urlopen("http://127.0.0.1:8787/healthz", timeout=2)
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
    then
        echo "[dg] Dashboard ready."
        break
    fi
    sleep 1
done

echo ""
echo "[dg] MCP server starting on port $MCP_PORT..."
echo "[dg] Use with codex:"
echo "     codex --mcp-server-uri http://localhost:$MCP_PORT/sse \"your task\""
echo ""

# ── Start MCP server (foreground, SSE) ───────────────────────────────────────
PORT=$MCP_PORT python3 "$SCRIPT_DIR/mcp_graph_server.py"
