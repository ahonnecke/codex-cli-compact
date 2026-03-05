# Dual-Graph one-time setup for Windows
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/kunal12203/Codex-CLI-Compact/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$R2          = "https://pub-18426978d5a14bf4a60ddedd7d5b6dab.r2.dev"
$BASE_URL    = "https://raw.githubusercontent.com/kunal12203/Codex-CLI-Compact/main"
$INSTALL_DIR = "$env:USERPROFILE\.dual-graph"

New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null

# ── Download core engine ──────────────────────────────────────────────────────
Write-Host "[install] Downloading core engine..."
Invoke-WebRequest "$R2/mcp_graph_server.py" -OutFile "$INSTALL_DIR\mcp_graph_server.py"
Invoke-WebRequest "$R2/graph_builder.py"    -OutFile "$INSTALL_DIR\graph_builder.py"
Invoke-WebRequest "$R2/dual_graph_launch.sh" -OutFile "$INSTALL_DIR\dual_graph_launch.sh"
Invoke-WebRequest "$R2/dg.py"              -OutFile "$INSTALL_DIR\dg.py"

Write-Host "[install] Downloading CLI wrappers..."
Invoke-WebRequest "$BASE_URL/bin/dgc.cmd" -OutFile "$INSTALL_DIR\dgc.cmd"
Invoke-WebRequest "$BASE_URL/bin/dg.cmd"  -OutFile "$INSTALL_DIR\dg.cmd"
Invoke-WebRequest "$BASE_URL/bin/dgc.ps1" -OutFile "$INSTALL_DIR\dgc.ps1"
Invoke-WebRequest "$BASE_URL/bin/dg.ps1"  -OutFile "$INSTALL_DIR\dg.ps1"

Write-Host "[install] Creating Python venv..."
python -m venv "$INSTALL_DIR\venv"

Write-Host "[install] Installing Python dependencies..."
& "$INSTALL_DIR\venv\Scripts\pip" install "mcp>=1.3.0" uvicorn anyio starlette --quiet

# Add to user PATH if not already there
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*\.dual-graph*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$INSTALL_DIR", "User")
    Write-Host "[install] Added $INSTALL_DIR to PATH"
}

Write-Host ""
Write-Host "[install] Done! Open a NEW terminal, then run:"
Write-Host "  dgc `"C:\path\to\your\project`"   # Claude Code"
Write-Host "  dg  `"C:\path\to\your\project`"   # Codex CLI"
