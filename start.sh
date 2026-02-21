#!/bin/bash
set -e

APP_DIR="/app/dual-graph-dashboard"
INTERNAL_PORT=8787

# ── Clone or update the target project repo ──────────────────────────────────
if [ -n "$GITHUB_REPO_URL" ]; then
    REPO_DIR="${DUAL_GRAPH_PROJECT_ROOT:-/app/project}"
    if [ -d "$REPO_DIR/.git" ]; then
        echo "[start] pulling latest: $REPO_DIR"
        git -C "$REPO_DIR" pull --ff-only
    else
        echo "[start] cloning $GITHUB_REPO_URL -> $REPO_DIR"
        if [ -n "$GITHUB_TOKEN" ]; then
            # Inject token for private repos: https://token@github.com/...
            CLONE_URL="${GITHUB_REPO_URL/https:\/\//https://$GITHUB_TOKEN@}"
        else
            CLONE_URL="$GITHUB_REPO_URL"
        fi
        git clone --depth=1 "$CLONE_URL" "$REPO_DIR"
    fi
    export DUAL_GRAPH_PROJECT_ROOT="$REPO_DIR"
    echo "[start] project root: $DUAL_GRAPH_PROJECT_ROOT"
fi

# ── Start dashboard API on a fixed internal port ─────────────────────────────
# We override PORT here so server.py does not consume Railway's public PORT.
echo "[start] starting dashboard API on 127.0.0.1:$INTERNAL_PORT"
DUAL_GRAPH_PORT=$INTERNAL_PORT PORT=$INTERNAL_PORT \
    python3 "$APP_DIR/server.py" &
DASHBOARD_PID=$!

# ── Wait for dashboard to be ready (up to 30 s) ──────────────────────────────
echo "[start] waiting for dashboard..."
for i in $(seq 1 30); do
    if python3 - <<'PY' 2>/dev/null
import urllib.request, sys
try:
    urllib.request.urlopen("http://127.0.0.1:8787/healthz", timeout=2)
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
    then
        echo "[start] dashboard ready"
        break
    fi
    sleep 1
done

# ── Point MCP server at the internal dashboard ────────────────────────────────
export DG_BASE_URL="http://127.0.0.1:$INTERNAL_PORT"

# ── Start MCP server (SSE, on Railway's public PORT) ─────────────────────────
echo "[start] starting MCP SSE server on PORT=${PORT:-8080}"
exec python3 "$APP_DIR/mcp_graph_server.py"
