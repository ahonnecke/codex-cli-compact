# Dual-Graph Fork & Patch Plan
### With Engram Integration Analysis

---

## TL;DR

You do not need to choose. Dual-Graph and Engram operate at different layers and can run simultaneously as separate MCP servers in Claude Code. Fork Dual-Graph, patch out the supply chain and telemetry concerns, and run both.

---

## The Two Tools at a Glance

| Dimension | Dual-Graph | Engram |
|---|---|---|
| **Layer** | Within-session token optimizer | Cross-session knowledge base |
| **Core mechanism** | Semantic codebase graph + live action graph | SQLite FTS5 memory store |
| **Token impact** | Compounds per turn — stops re-reading files | Injects relevant past knowledge at session start |
| **What it remembers** | Which files were read/edited *this session* | Bugfixes, decisions, errors resolved — across all sessions |
| **Agent autonomy** | Mandatory `graph_continue` call routes the agent | Agent decides what's worth saving via `mem_save` |
| **Persistence scope** | Session + limited 15-entry cross-session store | Indefinite, searchable, structured |
| **Runtime** | Python MCP server + bash launcher | Single Go binary |
| **Supply chain risk** | High (see below) | Low — binary is what you install |

---

## Why Fork

Three concerns with running upstream Dual-Graph as-is:

1. **Missing core files** — `graph_builder.py` and `dg.py` are not in the repo. They are downloaded from a Cloudflare R2 bucket at first launch. You have no visibility into what you're running.
2. **Auto-update on every launch** — the launcher checks R2 for a new version of those files and re-execs itself if one is found. An upstream change deploys silently on your next session.
3. **Heartbeat telemetry** — a daemon thread in `mcp_graph_server.py` POSTs `machine_id`, `platform`, and `tool` to a Railway-hosted endpoint every 15 minutes.

---

## Fork & Patch Plan

### Phase 1 — Capture the Missing Files

These steps run once in a sandboxed environment before you fork.

```bash
# In a VM or throwaway container — NOT your main machine yet
mkdir /tmp/dg-capture && cd /tmp/dg-capture

# Run the installer — this triggers the R2 download
curl -sSL https://raw.githubusercontent.com/kunal12203/Codex-CLI-Compact/main/install.sh | bash

# After install completes, the files land in ~/bin/
# Locate and copy them out
cp ~/bin/graph_builder.py /tmp/dg-capture/
cp ~/bin/dg.py /tmp/dg-capture/
cp ~/bin/mcp_graph_server.py /tmp/dg-capture/

# Inspect before committing anything
cat /tmp/dg-capture/graph_builder.py
cat /tmp/dg-capture/dg.py
```

Read both files in full. Confirm they do what the README describes and nothing more.

---

### Phase 2 — Fork and Commit the Captured Files

```bash
# Fork kunal12203/Codex-CLI-Compact to your own GitHub account
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/Codex-CLI-Compact
cd Codex-CLI-Compact

# Add the captured files into the bin/ directory
cp /tmp/dg-capture/graph_builder.py bin/
cp /tmp/dg-capture/dg.py bin/

git add bin/graph_builder.py bin/dg.py
git commit -m "chore: commit R2-hosted files into repo for supply chain control"
```

---

### Phase 3 — Patch the Launcher (Disable R2 Download + Auto-Update)

Open `bin/dual_graph_launch.sh` and locate two blocks:

**Block 1 — Initial R2 download** (runs if files are missing):
```bash
# Find lines that reference the R2 bucket URL
# pub-18426978d5a14bf4a60ddedd7d5b6dab.r2.dev
# Remove or comment out the curl/wget that fetches graph_builder.py and dg.py
# Replace with a direct reference to the local bin/ path
```

**Block 2 — Self-update check** (runs on every launch):
```bash
# Find the version check block — it GETs r2.dev/version.txt
# and re-execs the launcher if newer
# Comment out or delete this entire block
```

After patching:
```bash
git add bin/dual_graph_launch.sh
git commit -m "chore: remove R2 download and auto-update, use local bin files"
```

---

### Phase 4 — Remove Heartbeat Telemetry

Open `bin/mcp_graph_server.py`:

```bash
# Search for the Railway endpoint
grep -n "dual-graph-license-production.up.railway.app" bin/mcp_graph_server.py

# Also search for generic ping/heartbeat patterns
grep -n "heartbeat\|ping\|analytics\|identity.json\|machine_id" bin/mcp_graph_server.py
```

Delete or stub out:
- The daemon thread that fires the heartbeat
- Any reference to `~/.dual-graph/identity.json` (the stable machine ID used for analytics)
- The one-time feedback form POST to Google Apps Script (optional — harmless but noisy)

```bash
git add bin/mcp_graph_server.py
git commit -m "chore: remove telemetry heartbeat and machine identity tracking"
```

---

### Phase 5 — Point Install Script at Your Fork

The `install.sh` and `install.ps1` reference the upstream GitHub raw URLs. Update them to reference your fork:

```bash
# In install.sh, replace:
# https://raw.githubusercontent.com/kunal12203/Codex-CLI-Compact/main/
# with:
# https://raw.githubusercontent.com/YOUR_USERNAME/Codex-CLI-Compact/main/

sed -i 's|kunal12203/Codex-CLI-Compact|YOUR_USERNAME/Codex-CLI-Compact|g' install.sh install.ps1

git add install.sh install.ps1
git commit -m "chore: point install scripts at fork"
```

---

### Phase 6 — Install from Your Fork

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/Codex-CLI-Compact/main/install.sh | bash
source ~/.bashrc  # or ~/.profile on Pop!_OS
```

Verify the `dgc` launcher works and that no outbound calls to R2 or Railway appear in a network monitor during startup.

---

## Running Dual-Graph + Engram Together

### Do they conflict?

No. They register as independent MCP servers under different namespaces and never touch the same files or data directories.

```
Claude Code session
├── MCP: dual-graph  → localhost:808x/mcp  → .dual-graph/ (per project)
└── MCP: engram      → stdio (Go binary)   → ~/.engram/engram.db (global)
```

### How they divide the work

```
Turn 1 (new session)
  Engram:      mem_search → surfaces past decisions, known bugs, arch choices
  Dual-Graph:  graph_scan → builds codebase graph, cold start

Turn 2+ (same session)
  Dual-Graph:  graph_continue → memory_first hits, no re-reads, token savings compound
  Engram:      passive (agent calls mem_save when something worth keeping happens)

Session end
  Engram:      mem_session_summary → persists goal/discoveries/files touched
  Dual-Graph:  stop.sh → logs token estimate to dashboard

Next session start
  Engram:      injects relevant cross-session knowledge via SessionStart hook
  Dual-Graph:  prime.sh → injects recent context-store entries (last 15, 7-day window)
```

### The one overlap

Both inject context at `SessionStart`. This is not a conflict — it's additive. Dual-Graph injects project-scoped recent decisions (shallow, 7 days). Engram injects semantically relevant memories from any past session (deep, indefinite). Combined they give Claude a richer cold-start context than either provides alone.

### Hooks config sketch

In `~/.claude/settings.json` or project-level `.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "dual-graph": {
      "url": "http://localhost:8080/mcp",
      "type": "sse"
    },
    "engram": {
      "command": "/path/to/engram",
      "args": ["mcp"],
      "type": "stdio"
    }
  },
  "hooks": {
    "SessionStart": [
      { "type": "command", "command": "bash ~/.dual-graph/prime.sh" },
      { "type": "command", "command": "engram hook session-start" }
    ],
    "Stop": [
      { "type": "command", "command": "bash ~/.dual-graph/stop.sh" },
      { "type": "command", "command": "engram hook session-end" }
    ]
  }
}
```

> Note: Dual-Graph manages its own MCP registration via `dgc` launcher. Verify the launcher doesn't clobber manual hook entries in `settings.local.json` — inspect `prime.sh` after first run.

---

## Effort Estimate

| Phase | Time |
|---|---|
| Capture R2 files in sandbox | 15 min |
| Read and audit the captured files | 30–60 min |
| Fork + commit files + patch launcher | 20 min |
| Remove telemetry | 15 min |
| Update install scripts + reinstall | 10 min |
| Validate + wire up with Engram | 20 min |
| **Total** | **~2 hours** |

---

## Recommendation

Run both. Fork Dual-Graph first, do the audit, then wire them up together. If the audit of `graph_builder.py` and `dg.py` turns up anything unexpected, you'll be glad you looked before running it against CrewCapable source.
