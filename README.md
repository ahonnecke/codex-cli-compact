# Dual Graph Dashboard (Sample Frontend)

This sample provides:

1. A project scanner that builds an **information graph** from files/imports/references.
2. A local API server.
3. A frontend dashboard to:
   - trigger scans
   - view graph stats and nodes
   - log token usage events (`baseline` vs `dual_graph`)
   - view token usage summary and recent trend chart
   - compare token usage with either heuristic counting or Anthropic model counting
4. A starter CLI (`dg.py`) for Claude Code style hook integration.

## Files

- `graph_builder.py` - scans project and emits information graph JSON.
- `server.py` - serves UI + API (`/api/info-graph`, `/api/scan`, `/api/token-event`, `/api/token-summary`).
- `static/` - frontend dashboard.
- `data/info_graph.json` - generated information graph.
- `data/token_usage.jsonl` - append-only token event log.

## Run

From repo root:

```bash
python3 ./dual-graph-dashboard/server.py
```

Open:

`http://127.0.0.1:8787`

## `dg` CLI Starter

Run from anywhere:

```bash
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg.py scan
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg.py retrieve --query "fix checkout pricing bug"
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg.py prime --query "update auth middleware"
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg.py action log --kind tool_run --summary "rg checkout"
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg.py stats --json
```

Subcommands:

- `scan` - Build/update information graph JSON.
- `retrieve` - Get top files/edges for query.
- `prime` - Print compact markdown context for hooks.
- `action log` - Append action event to `data/action_events.jsonl`.
- `stats` - Summarize token usage from dashboard log.

## Claude Hooks Draft

See sample:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/claude-hooks.sample.json`

Copy that into your Claude settings and adjust paths if needed.

## MCP Gateway (Claude/VS Code)

This lets Claude call your graph tools (`graph_retrieve`, `graph_read`, `graph_impact`) instead of broad repo search first.

Files added:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/mcp_graph_server.py`
- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/claude-mcp.sample.json`
- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/claude-graph-policy.sample.txt`

### 1) Install MCP Python package

```bash
python3 -m pip install mcp
```

### 2) Start dual-graph dashboard server

```bash
DUAL_GRAPH_PROJECT_ROOT="/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm" \
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/server.py
```

### 3) Register MCP server in Claude config

Use this JSON block from:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/claude-mcp.sample.json`

Config location depends on client:

- Claude Desktop (macOS): `~/Library/Application Support/Claude/claude_desktop_config.json`
- Other Claude clients / VS Code integrations: use that integration's MCP servers config UI/file and paste the same `mcpServers.dual-graph` block.

### 4) Restart Claude/VS Code integration

After restart, Claude should see tools:

- `graph_retrieve`
- `graph_read`
- `graph_neighbors`
- `graph_impact`
- `fallback_rg`

### 5) Use graph-first policy

Paste policy text from:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/claude-graph-policy.sample.txt`

into your project instruction/system prompt area.

### 6) Verify

Ask Claude:

- `Find files for: update payment status button in restaurant portal`

Expected:

- first tool call should be `graph_retrieve`
- then `graph_read` for top-ranked files
- `fallback_rg` only when retrieval is weak

## Railway Hosting (Public API)

You can host the dual-graph API on Railway and let users connect via local MCP adapters.

Important:

- The hosted service can only scan files available inside the deployed container.
- To let "anyone" use it safely, keep per-user auth and per-workspace isolation.

### 1) Prepare deploy

Dockerfile is included:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/Dockerfile`

In Railway service settings:

- Root Directory: `dual-graph-dashboard`
- Port: Railway uses `PORT` automatically.

### 2) Set required Railway env vars

- `DUAL_GRAPH_PROJECT_ROOT=/app` (or your mounted repo path inside container)
- `DG_API_TOKEN=<strong-random-token>`
- Optional:
  - `DUAL_GRAPH_HOST=0.0.0.0`
  - `DUAL_GRAPH_PORT=8787`

### 3) Deploy + healthcheck

After deploy, check:

- `GET https://<your-service>.up.railway.app/healthz`

### 4) Point MCP adapter to Railway

When adding MCP server to Codex:

- `DG_BASE_URL=https://<your-service>.up.railway.app`
- `DG_API_TOKEN=<same token>`

Example add command:

```bash
codex mcp add dual-graph \
  --env DG_BASE_URL=https://<your-service>.up.railway.app \
  --env DG_API_TOKEN=<same-token> \
  --env DUAL_GRAPH_PROJECT_ROOT="/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm" \
  -- "/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/.venv-mcp/bin/python" \
  "/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/mcp_graph_server.py"
```

### 5) Security baseline

- Keep `DG_API_TOKEN` set (server rejects unauthenticated `/api/*` requests).
- Rotate token regularly.
- Add Railway rate limits / WAF if exposing publicly.

## One-Liner Codex Run (Server URL)

Use wrapper:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/codex_with_dual_graph.sh`

Run:

```bash
/Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/codex_with_dual_graph.sh \
  "https://<your-service>.up.railway.app" \
  "/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm" \
  "Update payment status button behavior in restaurant portal with minimal scoped changes." \
  "<DG_API_TOKEN>"
```

This command:

- configures/updates MCP server
- injects strict graph policy
- launches Codex in one step

## Auto-Update Graph On File Changes

Use daemon:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/graph_sync_daemon.py`

Run in a separate terminal:

```bash
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/graph_sync_daemon.py \
  --root "/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm" \
  --interval 3 \
  --debounce 2
```

Behavior:

- watches repo files
- on change, debounced re-scan updates info graph
- action graph is updated by MCP tools (`graph_read`, `graph_register_edit`, `graph_continue`)

## CLI-First Workflow (Phase 1)

Use:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/claude_safe.py`

### Quick start

```bash
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py doctor
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py scan
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py retrieve --query "update payment status button in restaurant portal"
```

### Dry run (safe)

```bash
OPENAI_API_KEY=... python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py run \
  --query "update payment status button in restaurant portal" \
  --codex-tokens 49000 \
  --validate
```

### Apply with guards

```bash
OPENAI_API_KEY=... python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py run \
  --query "update payment status button in restaurant portal" \
  --codex-tokens 49000 \
  --apply \
  --validate
```

By default this enforces:

- snippet-anchored edits
- scope drift checks
- no full-file rewrites

### Token ledger + logs

```bash
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py ledger
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/claude_safe.py logs --last 30
```

## 10-Query Quality Benchmark

Run benchmark using local mimic outputs:

```bash
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/compare_quality.py
```

Run benchmark using OpenAI token counts and real generated outputs:

```bash
OPENAI_API_KEY=... python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/compare_quality.py --token-provider openai --real-output --model gpt-5-mini
```

Report is written to:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/data/compare_quality_report.json`

## Real Codex vs Info-Graph Fixer (Separate A/B)

Use this when you already have real token usage from Codex UI and want to compare against the info-graph fixer run.

Dry-run (no file writes):

```bash
OPENAI_API_KEY=... python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/codex_ab_compare.py \
  --query "fix checkout pricing flow" \
  --codex-tokens 4200 \
  --model gpt-5-mini
```

Apply edits to project files:

```bash
OPENAI_API_KEY=... python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/codex_ab_compare.py \
  --query "fix checkout pricing flow" \
  --codex-tokens 4200 \
  --model gpt-5-mini \
  --apply
```

A/B reports are saved under:

- `/Users/krishnakant/Documents/Open source/beads-main/dual-graph-dashboard/data/ab_runs/`

You can also run this from UI now:

1. Open dashboard
2. Use **Fix Chat (Graph + Grep)** to send query
3. Enter real Codex tokens (optional but recommended)
4. Click **Dry Run Fix** first
5. Click **Apply Fix** if dry-run output looks correct

## Codex vs DG Session Logging (Dashboard Live Monitor)

Use this to compare **normal Codex** (without graph) vs **DG launcher** (with graph)
across two folders and auto-log prompts + real token usage into dashboard live monitor.

1) Start dashboard server:

```bash
python3 /Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/server.py
```

2) Run in your **without-graph** folder and auto-log:

```bash
/Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg-bench \
  --mode codex \
  --project "/absolute/path/to/without-graph" \
  --label "without-graph"
```

3) Run in your **with-graph** folder and auto-log:

```bash
/Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg-bench \
  --mode dg \
  --project "/absolute/path/to/with-graph" \
  --label "with-graph"
```

4) Open dashboard and check **Live Token Monitor**:

- [http://127.0.0.1:8787](http://127.0.0.1:8787)

Notes:

- `dg-bench` reads Codex session files from `~/.codex/sessions`.
- It writes rows to `~/.dual-graph/bench_log.jsonl` (already used by `/api/bench-log`).
- Use labels containing `with` / `without` so the dashboard aggregates correctly.

Optional helpers:

```bash
# Log latest session for a project after manual run
/Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg-bench --save --project "/absolute/path/to/with-graph" --label "with-graph"

# Show aggregate totals from the same bench log file
/Users/krishnakant/Documents/Open\ source/beads-main/dual-graph-dashboard/dg-bench --report
```

## Mount in Existing Project

Set project root to scan via environment variable:

```bash
DUAL_GRAPH_PROJECT_ROOT="/absolute/path/to/your/project" python3 ./dual-graph-dashboard/server.py
```

You can also change port:

```bash
DUAL_GRAPH_PORT=8799 python3 ./dual-graph-dashboard/server.py
```

## API Shape

### POST `/api/token-event`

```json
{
  "mode": "baseline",
  "prompt_chars": 1200,
  "prompt_tokens": 300,
  "completion_tokens": 250,
  "total_tokens": 550,
  "notes": "scenario-1"
}
```

### GET `/api/token-summary`

Returns aggregate totals and recent events for chart/table rendering.

### POST `/api/tokenize`

Use tokenizer provider:

- `heuristic`: chars/4 approximation
- `openai`: calls `https://api.openai.com/v1/responses` and reads usage tokens
- `anthropic`: calls `https://api.anthropic.com/v1/messages/count_tokens`

OpenAI mode needs:

```bash
OPENAI_API_KEY=... python3 ./dual-graph-dashboard/server.py
```

Anthropic mode needs:

```bash
ANTHROPIC_API_KEY=... python3 ./dual-graph-dashboard/server.py
```

## Next Step

Action graph can be added later by introducing new endpoints like:

- `POST /api/action-event`
- `GET /api/action-graph`

and rendering an action timeline panel in the frontend.
