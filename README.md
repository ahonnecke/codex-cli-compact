# Dual-Graph — Compounding Context for Claude Code & Codex CLI

A local MCP (Model Context Protocol) server that gives Claude and Codex a persistent memory of your codebase. Instead of re-reading files on every turn, it builds a semantic graph of your project and routes the AI directly to the files and symbols it already knows matter — so each conversation turn is cheaper than the last.

💬 **Questions, bugs, or feedback? Join the community → [discord.gg/rxgVVgCh](https://discord.gg/rxgVVgCh)**

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Install](#install)
- [Usage](#usage)
  - [Claude Code (dgc)](#claude-code-dgc)
  - [Codex CLI (dg)](#codex-cli-dg)
  - [Windows](#windows)
- [MCP Tools Reference](#mcp-tools-reference)
- [Data & Files](#data--files)
- [Configuration](#configuration)
- [Context Store](#context-store)
- [Token Tracking](#token-tracking)
- [Self-Update](#self-update)
- [Privacy & Security](#privacy--security)
- [Repository Structure](#repository-structure)

---

## How It Works

```
Session start  →  project is scanned → info_graph.json written
Turn 1         →  cold start, AI reads freely via graph_retrieve + graph_read
Turn 2+        →  memory_first: routed to previously-touched files instantly
               →  no redundant re-reads, token budget saved
```

Token savings **compound** across a session. The graph remembers which files were read, which were edited, and what decisions were made — so each turn is cheaper than the last.

The system runs two graphs simultaneously:

| Graph | Purpose |
|---|---|
| **Info Graph** (`info_graph.json`) | Static semantic graph of the project: files, symbols, import edges, scored by keyword overlap |
| **Action Graph** (`chat_action_graph.json`) | Dynamic memory of the current session: what was read, edited, queried, decided |

On each turn, `graph_continue` checks the **action graph first**. If previously-touched files are relevant to the query, it returns them as `memory_first` hits with `confidence=high` — no retrieval needed. If not, it falls back to the **info graph** to rank files by semantic similarity.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  AI Client (Claude Code / Codex CLI)                    │
│                                                         │
│  Uses MCP tools:                                        │
│    graph_continue → graph_read → graph_register_edit   │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP  (localhost:808x/mcp)
                           ▼
┌─────────────────────────────────────────────────────────┐
│  mcp_graph_server.py  (FastMCP, Starlette, uvicorn)    │
│                                                         │
│  ┌─────────────────┐   ┌──────────────────────────┐    │
│  │  Info Graph     │   │  Action Graph (memory)   │    │
│  │  info_graph.json│   │  chat_action_graph.json  │    │
│  │  (static scan)  │   │  (live, updated per turn)│    │
│  └────────┬────────┘   └──────────────┬───────────┘    │
│           │ dg.py::retrieve           │                 │
│           ▼                           ▼                 │
│     semantic ranking           action history           │
│     by keyword overlap         (reads, edits, queries)  │
└─────────────────────────────────────────────────────────┘
                           │ built by
                           ▼
┌─────────────────────────────────────────────────────────┐
│  graph_builder.py                                       │
│  Walks project directory, extracts:                     │
│   - file nodes (path, language, summary)               │
│   - symbol nodes (functions, classes, line ranges)     │
│   - import / call edges between files                  │
│   - body_hash per symbol for staleness detection       │
└─────────────────────────────────────────────────────────┘
```

### Launcher flow (`dual_graph_launch.sh` / `.cmd` / `.ps1`)

1. Kill any stale MCP server for the project (frees the port).
2. Self-update: checks Cloudflare R2 for a newer version; downloads and re-execs if found.
3. Create a Python venv if missing; install `mcp`, `uvicorn`, `anyio`, `starlette`.
4. Run `graph_builder.py` to scan the project and write `info_graph.json`.
5. Start `mcp_graph_server.py` in the background on a free port (8080–8099).
6. Register the MCP server with the CLI (`claude mcp add` / `codex mcp add`).
7. For Claude: write `prime.sh` / `stop.sh` hooks into `.claude/settings.local.json`
   — these inject session context at `SessionStart`, `PreCompact`, and `Stop`.
8. Show the one-time feedback form (once per install, after the first day).
9. Launch the AI CLI (`claude` or `codex`).

---

## Install

**macOS / Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/kunal12203/Codex-CLI-Compact/main/install.sh | bash
source ~/.zshrc   # or ~/.bashrc / ~/.profile
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/kunal12203/Codex-CLI-Compact/main/install.ps1 | iex
```

The installer places launcher scripts in `~/.dual-graph/` (Windows) or `~/bin/` (macOS/Linux) and adds them to your `PATH`.

---

## Usage

### Claude Code (`dgc`)

```bash
# From inside the project:
dgc

# Point to a specific project:
dgc /path/to/your/project

# Start with a prompt:
dgc /path/to/your/project "add a dark mode toggle"
```

### Codex CLI (`dg`)

```bash
dg                          # scan current directory, start codex
dg /path/to/project         # scan given project, start codex
dg /path/to/project "task"  # scan and start with a prompt
```

### Windows

The `.cmd` launchers work the same way:

```cmd
dgc                           :: Claude Code
dg                            :: Codex CLI
dgc C:\path\to\project
```

PowerShell variants (`dgc.ps1`, `dg.ps1`) are also available.

If you installed with Scoop and the package version lags behind GitHub, `dgc .` still refreshes the real launcher payload in `%USERPROFILE%\.dual-graph\`. If the Scoop shim itself needs repair, run `scoop update dual-graph`.

---

## MCP Tools Reference

All tools are served over HTTP at `http://localhost:<port>/mcp` and exposed to the AI client.

### `graph_continue` _(start here every turn)_

Routes to relevant files using action-memory first, then info-graph retrieval only if needed. This is the **mandatory first call** at the start of every turn.

**Returns:**
- `mode: "memory_first"` — relevant files found in action history → `confidence=high`
- `mode: "retrieve_then_read"` — no history match, falling back to graph retrieval → confidence `medium`/`low`
- `needs_project: true` — no graph scanned yet, must call `graph_scan` first
- `skip: true` — fewer than 5 files in project, use targeted reads only

**Confidence levels and what they mean:**

| Confidence | Top score | `max_supplementary_greps` | `max_supplementary_files` |
|---|---|---|---|
| `high` | ≥ 10 | 0 | 0 |
| `medium` | 4–9 | 2 | 2 |
| `low` | < 4 | 3 | 3 |

---

### `graph_read`

Reads one file safely from the project root with adaptive excerpting.

- Supports `file::symbol` notation (e.g. `src/auth.ts::handleLogin`) to read only a specific function or class.
- Enforces a **per-turn read budget** (`DG_TURN_READ_BUDGET_CHARS`, default 18 000 chars).
- Hard cap per file: `DG_HARD_MAX_READ_CHARS` (default 4 000 chars).
- Uses query-aware excerpting: returns the most relevant lines, not just the file head.
- Detects **staleness**: if a symbol's body hash changed since the last scan, returns `stale: true`.
- Deduplicates repeated reads in the same turn (returns only a 500-char preview on repeat).

---

### `graph_retrieve`

Scores and ranks files by query relevance using the info graph.

- Tries local retrieval first (`dg.py::retrieve`); falls back to HTTP if unavailable.
- **Cross-turn retrieval cache** (TTL: 15 min, max 50 entries) — invalidated when changed files are registered.
- Cache is keyed by query terms + `top_files` + `top_edges`; file mtime stamps ensure freshness.
- Returns `reuse_candidates`: files touched in past turns with overlapping query terms.

---

### `graph_register_edit`

Records which files were edited so future turns route to them correctly.

- Updates the action graph with an edit node and increments `edited_count` per file.
- Supports an optional `summary` string stored in the **decisions log** (rolling window of 20, archived beyond that).
- Invalidates retrieval cache for the changed files.
- On the first-ever edit in a session, returns `graph_state: "primed"`.

---

### `graph_scan`

Scans a local project directory and builds/refreshes the info graph.

- Calls `graph_builder.py` to walk the directory tree, extract symbols, compute edges.
- Supports **incremental re-scan**: preserves summaries for unchanged files.
- Writes `info_graph.json` and `symbol_index.json`.
- Resets action graph, retrieval cache, and turn state for the new project.

---

### `fallback_rg`

Controlled fallback grep (uses `rg` / ripgrep) when retriever confidence is low.

- Rate-limited to `DG_FALLBACK_MAX_CALLS_PER_TURN` calls per query turn (default: 1).
- Runs against `PROJECT_ROOT` with `-n -S` flags (line numbers, smart case).

---

### `graph_neighbors`

Returns all graph edges touching a specific file — shows what imports/is-imported-by the file.

---

### `graph_impact`

Given a list of changed files, returns connected files likely impacted by the edits.

---

### `graph_action_summary`

Returns recent action graph summary and query-relevant touched files. Useful for debugging or understanding what the AI has been doing in a session.

---

## Data & Files

All data lives in `<project>/.dual-graph/` (gitignored automatically).

| File | Description |
|---|---|
| `info_graph.json` | Static info graph: files, symbols, edges, scores |
| `symbol_index.json` | Flat `{symbol_id: metadata}` for O(1) `graph_read` symbol lookups |
| `chat_action_graph.json` | Dynamic session memory: reads, edits, queries, decisions |
| `retrieval_cache.json` | Short-lived retrieval cache (TTL 15 min, mtime-validated) |
| `context-store.json` | Persistent JSON store for decisions/tasks/facts/blockers across sessions |
| `mcp_server.pid` | PID of the running MCP server (used for cleanup) |
| `mcp_port` | Port the server is running on |
| `mcp_server.log` | MCP server stdout/stderr |
| `mcp_tool_calls.jsonl` | Append-only log of every tool call with timestamps |
| `prime.sh` | Claude hook: injects context at `SessionStart` and `PreCompact` |
| `stop.sh` | Claude hook: auto-logs token estimates at `Stop` |

Global identity (not project-specific):
- `~/.dual-graph/identity.json` — stable machine ID for analytics pings

---

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `DG_HARD_MAX_READ_CHARS` | `4000` | Hard cap on characters returned per `graph_read` call |
| `DG_TURN_READ_BUDGET_CHARS` | `18000` | Total chars that can be read in one query turn |
| `DG_ENFORCE_REUSE_GATE` | `1` | Block reads of non-reuse-candidate files until a reuse candidate is read first |
| `DG_ENFORCE_SINGLE_RETRIEVE` | `1` | Allow only one `graph_retrieve` per query key per turn |
| `DG_ENFORCE_READ_ALLOWLIST` | `0` | Block reads of files not in the retrieved set |
| `DG_FALLBACK_MAX_CALLS_PER_TURN` | `1` | Max `fallback_rg` calls per query turn |
| `DG_RETRIEVE_CACHE_TTL_SEC` | `900` | Retrieval cache TTL in seconds (15 min) |
| `DG_MCP_PORT` | auto (8080–8099) | Force a specific port for the MCP server |
| `DUAL_GRAPH_PROJECT_ROOT` | `/app/project` | Override project root (set by launcher) |
| `DG_DATA_DIR` | `<script_dir>/data` | Override data directory (set by launcher to `<project>/.dual-graph`) |

---

## Context Store

For Claude sessions, decisions, tasks, next steps, facts, and blockers made during a conversation are persisted in `.dual-graph/context-store.json`. This store is injected back into Claude at the start of the next session via the `prime.sh` hook (max 15 entries, 7-day window).

Entry format:
```json
{
  "type": "decision|task|next|fact|blocker",
  "content": "one sentence, max 15 words",
  "tags": ["topic"],
  "files": ["relevant/file.ts"],
  "date": "YYYY-MM-DD"
}
```

The hook also re-injects `CONTEXT.md` from the project root if present, providing an additional free-form session carry-over (~200 tokens).

---

## Token Tracking

When running with Claude Code, a `token-counter` MCP is registered globally:

```bash
# Installed automatically by dgc — no extra steps needed
# Dashboard runs at http://localhost:8899
```

Usage from inside the Claude session:
```
count_tokens({text: "<content>"})   # estimate tokens before reading
get_session_stats()                  # running session cost
log_usage({input_tokens: N, output_tokens: N, description: "task"})
```

The `stop.sh` hook estimates token usage from the session transcript and posts it to the dashboard automatically at session end.

---

## Self-Update

On every launch, the launcher checks Cloudflare R2 for a new version:

```
https://pub-18426978d5a14bf4a60ddedd7d5b6dab.r2.dev/version.txt
```

If a new version is found:
- `mcp_graph_server.py`, `graph_builder.py`, `dg.py` are pulled from R2.
- `dual_graph_launch.sh` is pulled from GitHub main.
- The launcher re-execs itself with the updated files.

Current version: see `bin/version.txt`.

---

## Privacy & Security

- **All project data stays local.** `info_graph.json`, `chat_action_graph.json`, and all session data are stored in `<project>/.dual-graph/` on your machine and are never uploaded.
- The only outbound network calls are:
  - **Version check** (GET `r2.dev/version.txt`) — no project data, just a version string.
  - **Heartbeat ping** (POST `dual-graph-license-production.up.railway.app/ping`) — sends only `machine_id`, `platform`, and `tool`. Runs every 15 minutes as a daemon thread. Never sends file names, code, or project data.
  - **One-time feedback form** (POST to a Google Apps Script) — sends only a numeric rating, optional free-text, and `machine_id`. Shown once after the first day of use.
- The `.dual-graph/` directory is automatically added to `.gitignore` so graph data is never accidentally committed.

---

## Repository Structure

```
dual-graph-dashboard/
├── bin/
│   ├── dgc                    ← Claude Code launcher (macOS/Linux)
│   ├── dg                     ← Codex CLI launcher (macOS/Linux)
│   ├── dgc.cmd                ← Claude Code launcher (Windows)
│   ├── dg.cmd                 ← Codex CLI launcher (Windows)
│   ├── dgc.ps1                ← Claude Code launcher (PowerShell)
│   ├── dg.ps1                 ← Codex CLI launcher (PowerShell)
│   ├── dual_graph_launch.sh   ← Shared launcher logic (bash)
│   ├── mcp_graph_server.py    ← MCP server (FastMCP, all tools)
│   └── version.txt            ← Current version string
├── data/
│   ├── functionality_index.md ← Optional: map product features to files
│   ├── action_events.jsonl    ← Event log
│   └── token_usage.jsonl      ← Token usage log
├── .dual-graph/               ← Per-project graph data (gitignored)
│   ├── info_graph.json
│   ├── chat_action_graph.json
│   ├── retrieval_cache.json
│   ├── context-store.json
│   ├── mcp_server.log
│   └── prime.sh / stop.sh
├── CLAUDE.md                  ← Policy injected into Claude (auto-maintained)
└── README.md                  ← This file
```

> **Note:** `graph_builder.py` and `dg.py` are downloaded from R2 at first launch and are not committed to the repository. They live alongside `mcp_graph_server.py` in `bin/` after install.

---

## Community

Have a question, found a bug, or want to share feedback?

👉 **Join the Discord: [discord.gg/rxgVVgCh](https://discord.gg/rxgVVgCh)**

- Get help with setup and usage
- Report bugs and get them fixed fast
- Share your workflows and tips
- Follow updates and new releases
