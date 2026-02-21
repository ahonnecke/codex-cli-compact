#!/usr/bin/env python3
"""Lightweight file-change daemon to keep info graph fresh."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DG_PY = BASE_DIR / "dg.py"
DEFAULT_ROOT = Path(
    os.environ.get(
        "DUAL_GRAPH_PROJECT_ROOT",
        "/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm",
    )
).resolve()
SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", "venv", ".venv"}
INCLUDE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".md", ".json", ".yaml", ".yml"}


def snapshot(root: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        base = Path(dp)
        for n in fns:
            p = base / n
            if p.suffix.lower() not in INCLUDE_EXT:
                continue
            try:
                out[str(p.resolve().relative_to(root.resolve()))] = int(p.stat().st_mtime_ns)
            except Exception:
                continue
    return out


def run_scan(root: Path) -> None:
    subprocess.run(
        ["python3", str(DG_PY), "scan", "--root", str(root)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-sync info graph on file changes.")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--debounce", type=float, default=2.0)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    prev = snapshot(root)
    print(f"[graph-sync] watching: {root}")
    print(f"[graph-sync] interval={args.interval}s debounce={args.debounce}s")
    last_change = 0.0

    while True:
        time.sleep(args.interval)
        cur = snapshot(root)
        if cur != prev:
            last_change = time.time()
            prev = cur
            continue
        if last_change and (time.time() - last_change) >= args.debounce:
            print("[graph-sync] changes detected -> scanning info graph")
            run_scan(root)
            last_change = 0.0


if __name__ == "__main__":
    raise SystemExit(main())

