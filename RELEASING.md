# Release Checklist

Follow this checklist **exactly** when bumping a version. All three repos must stay in sync.

## Repos

| Repo | Local path | Remote |
|------|-----------|--------|
| **Dashboard** | `~/Documents/Open source/beads-main/dual-graph-dashboard` | `kunal12203/Codex-CLI-Compact` |
| **Core** | `~/Documents/Open source/Claude-CLI-Compact-core` | `kunal12203/Claude-CLI-Compact-core` |
| **Scoop** | `~/Documents/Open source/scoop-dual-graph` | `kunal12203/scoop-dual-graph` |

## Version locations (ALL must match)

| Repo | File | Field |
|------|------|-------|
| Dashboard | `bin/version.txt` | Entire file content |
| Dashboard | `README.md` | `Current version: **X.Y.Z**` |
| Core | `src/graperoot/__init__.py` | `__version__ = "X.Y.Z"` |
| Core | `pyproject.toml` | `version = "X.Y.Z"` |
| Scoop | `bucket/dual-graph.json` | `"version": "X.Y.Z"` |

## Step-by-step

### 1. Determine the next version

Find the highest version across all three repos and increment by 1:

```bash
# Check all current versions
cat ~/Documents/Open\ source/beads-main/dual-graph-dashboard/bin/version.txt
grep __version__ ~/Documents/Open\ source/Claude-CLI-Compact-core/src/graperoot/__init__.py
grep '"version"' ~/Documents/Open\ source/scoop-dual-graph/bucket/dual-graph.json
```

The new version = max(all versions) + 0.0.1

### 2. Update all version files

Update **all five files** listed in the table above to the new version. Do not skip any.

### 3. Commit Dashboard

```bash
cd ~/Documents/Open\ source/beads-main/dual-graph-dashboard
git add bin/version.txt README.md <any changed .ps1/.sh files>
git commit -m "X.Y.Z: <short description of changes>"
```

### 4. Pull and rebase Dashboard (if needed)

```bash
git stash  # if uncommitted changes exist
git pull --rebase
# resolve conflicts if any — always pick the new version
git stash pop  # if stashed
```

### 5. Get Dashboard commit hash and install.ps1 SHA256

After rebase, the commit hash changes. Recompute both:

```bash
git rev-parse HEAD                    # full commit hash
shasum -a 256 install.ps1             # SHA256 of install.ps1
```

### 6. Update Scoop manifest

In `scoop-dual-graph/bucket/dual-graph.json`, update:

- `"version"` → new version
- `"url"` → replace the commit hash in the URL with the Dashboard commit hash from step 5
- `"hash"` → the SHA256 from step 5

### 7. Commit Core and Scoop

```bash
# Core
cd ~/Documents/Open\ source/Claude-CLI-Compact-core
git add src/graperoot/__init__.py pyproject.toml
git commit -m "X.Y.Z: <description>"

# Scoop
cd ~/Documents/Open\ source/scoop-dual-graph
git add bucket/dual-graph.json
git commit -m "X.Y.Z: <description>"
```

### 8. Push — ORDER MATTERS

Push Dashboard **first** (scoop URL points to a Dashboard commit):

```bash
# 1. Dashboard (FIRST — scoop depends on this)
cd ~/Documents/Open\ source/beads-main/dual-graph-dashboard
git push

# 2. Core and Scoop (can be parallel, after Dashboard)
cd ~/Documents/Open\ source/Claude-CLI-Compact-core
git push

cd ~/Documents/Open\ source/scoop-dual-graph
git push
```

### 9. Publish to PyPI (if Core changed)

If `pyproject.toml` or any Core source files changed:

```bash
cd ~/Documents/Open\ source/Claude-CLI-Compact-core
# build and publish (project-specific build command)
```

Users get the new graperoot automatically — `dgc.ps1` runs `pip install graperoot --upgrade` on self-update.

## Common mistakes

- **Forgetting `pyproject.toml`** — `__init__.py` and `pyproject.toml` versions must match in Core
- **Stale scoop hash** — if you rebase Dashboard after computing the hash, recompute both commit hash and SHA256
- **Pushing scoop before dashboard** — the scoop URL will 404 until the Dashboard commit exists on GitHub
- **Version not highest** — always check all three repos; they can drift independently

## Pip / dependency versions

- `pip` itself: not pinned — `install.ps1` runs `pip install --upgrade pip` (always latest)
- `mcp>=1.3.0`: minimum floor, not pinned
- `graperoot`: installed by Core's `dgc.ps1` and `install.ps1`, auto-upgraded on each run
- Dashboard's `install.ps1` and `dgc.ps1` install: `mcp>=1.3.0 uvicorn anyio starlette`
- Core's `install.ps1` and `dgc.ps1` install: `mcp>=1.3.0 uvicorn anyio starlette graperoot`

No pip version conflicts. Dependencies use minimum floors, not pins.
