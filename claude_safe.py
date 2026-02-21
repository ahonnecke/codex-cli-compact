#!/usr/bin/env python3
"""CLI control plane for graph-first safe editing and token reporting."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
AB_DIR = DATA_DIR / "ab_runs"
GRAPH_JSON = DATA_DIR / "info_graph.json"
DEFAULT_ROOT = Path(
    os.environ.get(
        "DUAL_GRAPH_PROJECT_ROOT",
        "/Users/krishnakant/documents/personal projects/restaurant CRM/restaurant-crm",
    )
).resolve()


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and v and k not in os.environ:
            os.environ[k] = v


def _latest_report() -> Path | None:
    if not AB_DIR.exists():
        return None
    files = sorted(AB_DIR.glob("ab_*.json"))
    return files[-1] if files else None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _ensure_graph(project_root: Path, refresh: bool = False) -> None:
    if GRAPH_JSON.exists() and not refresh:
        return
    cmd = [
        sys.executable,
        str(BASE_DIR / "dg.py"),
        "scan",
        "--root",
        str(project_root),
        "--out",
        str(GRAPH_JSON),
    ]
    proc = _run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "graph scan failed")


def cmd_doctor(args: argparse.Namespace) -> int:
    _load_env_file()
    print("claude-safe doctor")
    print(f"- project_root: {args.project_root}")
    print(f"- graph_json: {GRAPH_JSON}")
    print(f"- openai_key_set: {'yes' if bool(os.environ.get('OPENAI_API_KEY', '').strip()) else 'no'}")

    server = _run([sys.executable, str(BASE_DIR / "server.py"), "--help"])
    print(f"- server_py: {'ok' if server.returncode == 0 else 'missing/broken'}")
    dg = _run([sys.executable, str(BASE_DIR / "dg.py"), "--help"])
    print(f"- dg_py: {'ok' if dg.returncode == 0 else 'missing/broken'}")
    ab = _run([sys.executable, str(BASE_DIR / "codex_ab_compare.py"), "--help"])
    print(f"- fixer_py: {'ok' if ab.returncode == 0 else 'missing/broken'}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(BASE_DIR / "dg.py"),
        "scan",
        "--root",
        str(args.project_root),
        "--out",
        str(GRAPH_JSON),
    ]
    proc = _run(cmd)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(BASE_DIR / "dg.py"),
        "retrieve",
        "--query",
        args.query,
        "--top-files",
        str(args.top_files),
        "--top-edges",
        str(args.top_edges),
        "--json",
    ]
    proc = _run(cmd)
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    payload = json.loads(proc.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Query: {args.query}\n")
    print("Top files:")
    for f in payload.get("files", []):
        print(f"- {f.get('id')} (score={f.get('_score', 0)}, role={f.get('_role', 'n/a')}, intent={f.get('_intent', 'n/a')})")
    print("\nTop edges:")
    for e in payload.get("edges", []):
        print(f"- {e.get('from')} --{e.get('rel')}--> {e.get('to')}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    _load_env_file()
    cmd = [
        sys.executable,
        str(BASE_DIR / "codex_ab_compare.py"),
        "--query",
        args.query,
        "--codex-tokens",
        str(args.codex_tokens),
        "--model",
        args.model,
        "--project-root",
        str(args.project_root),
        "--top-files",
        str(args.top_files),
        "--top-edges",
        str(args.top_edges),
    ]
    if args.apply:
        cmd.append("--apply")
    if args.validate:
        cmd.append("--validate")
    if args.check_cmd:
        cmd.extend(["--check-cmd", args.check_cmd])
    if args.allow_fullfile:
        cmd.append("--allow-fullfile")
    if args.out:
        cmd.extend(["--out", str(Path(args.out).resolve())])

    proc = _run(cmd)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    report_path = Path(args.out).resolve() if args.out else _latest_report()
    if not report_path or not report_path.exists():
        return 0
    report = _load_json(report_path)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    t = report.get("tool_tokens", {})
    led = report.get("token_ledger", {})
    sg = report.get("scope_guard", {})
    print("\nRun Summary")
    print(f"- mode: {'apply' if args.apply else 'dry_run'}")
    print(f"- report: {report_path}")
    print(f"- tool_tokens: {t.get('total_tokens', 0)} (in={t.get('input_tokens', 0)}, out={t.get('output_tokens', 0)})")
    print(f"- reduction_vs_codex: {report.get('reduction_pct_vs_codex', 0)}%")
    print(f"- model_summary: {report.get('model_summary', '')}")
    print(f"- edits: {len(report.get('edits', []))}")
    print(f"- scope_drift: {sg.get('drift_detected', False)}")
    print(f"- pipeline_tokens_est: {led.get('pipeline_tokens_est', 0)}")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    _load_env_file()
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("OPENAI_API_KEY not set. Add it to environment or dual-graph-dashboard/.env", file=sys.stderr)
        return 2

    print("claude-safe chat")
    print(f"- project_root: {args.project_root}")
    print("- type /exit to quit")

    # Keep graph fresh at chat start.
    scan_proc = _run(
        [
            sys.executable,
            str(BASE_DIR / "dg.py"),
            "scan",
            "--root",
            str(args.project_root),
            "--out",
            str(GRAPH_JSON),
        ]
    )
    if scan_proc.returncode != 0:
        print(scan_proc.stderr.strip() or "scan failed", file=sys.stderr)
        return scan_proc.returncode

    while True:
        try:
            q = input("\nquery> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        if q in {"/exit", "exit", "quit"}:
            return 0

        dry_cmd = [
            sys.executable,
            str(BASE_DIR / "codex_ab_compare.py"),
            "--query",
            q,
            "--codex-tokens",
            str(args.codex_tokens),
            "--model",
            args.model,
            "--project-root",
            str(args.project_root),
            "--top-files",
            str(args.top_files),
            "--top-edges",
            str(args.top_edges),
            "--validate",
        ]
        dry = _run(dry_cmd)
        if dry.returncode != 0:
            print(dry.stderr.strip() or dry.stdout.strip() or "dry-run failed")
            continue

        rp = _latest_report()
        if not rp:
            print("No report generated.")
            continue
        rep = _load_json(rp)
        t = rep.get("tool_tokens", {})
        print("\nDry run summary")
        print(f"- files: {', '.join(rep.get('retrieval', {}).get('files', []))}")
        print(f"- edits: {len(rep.get('edits', []))}")
        print(f"- model_summary: {rep.get('model_summary', '')}")
        print(f"- tool_tokens: {t.get('total_tokens', 0)}")
        print(f"- scope_drift: {rep.get('scope_guard', {}).get('drift_detected', False)}")

        if not rep.get("edits"):
            print("- no edits proposed")
            continue
        yn = input("apply? [y/N] ").strip().lower()
        if yn not in {"y", "yes"}:
            continue

        apply_cmd = [
            sys.executable,
            str(BASE_DIR / "codex_ab_compare.py"),
            "--query",
            q,
            "--codex-tokens",
            str(args.codex_tokens),
            "--model",
            args.model,
            "--project-root",
            str(args.project_root),
            "--top-files",
            str(args.top_files),
            "--top-edges",
            str(args.top_edges),
            "--validate",
            "--apply",
        ]
        app = _run(apply_cmd)
        if app.returncode != 0:
            print(app.stderr.strip() or app.stdout.strip() or "apply failed")
            continue
        print("applied")


def cmd_ledger(args: argparse.Namespace) -> int:
    rp = Path(args.report).resolve() if args.report else _latest_report()
    if not rp or not rp.exists():
        print("No A/B report found.", file=sys.stderr)
        return 2
    report = _load_json(rp)
    led = report.get("token_ledger", {})
    t = report.get("tool_tokens", {})
    print(f"Report: {rp}")
    print(f"- codex_tokens_real: {report.get('codex_tokens_real', 0)}")
    print(f"- tool_tokens_total: {t.get('total_tokens', 0)}")
    print(f"- reduction_pct_vs_codex: {report.get('reduction_pct_vs_codex', 0)}")
    print("- token_ledger:")
    for k in (
        "query_tokens_est",
        "retrieval_tokens_est",
        "prompt_tokens_est",
        "model_input_tokens_real",
        "model_output_tokens_real",
        "model_total_tokens_real",
        "validation_output_tokens_est",
        "pipeline_tokens_est",
    ):
        print(f"  - {k}: {led.get(k, 0)}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    log = DATA_DIR / "mcp_tool_calls.jsonl"
    if not log.exists():
        print(f"Log not found: {log}", file=sys.stderr)
        return 2
    lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
    rows = lines[-args.last :] if args.last > 0 else lines
    for row in rows:
        try:
            j = json.loads(row)
        except json.JSONDecodeError:
            continue
        print(f"{j.get('timestamp')} | {j.get('tool')} | {json.dumps(j.get('payload', {}), ensure_ascii=False)}")
    return 0


def cmd_read_project(args: argparse.Namespace) -> int:
    try:
        _ensure_graph(Path(args.project_root).resolve(), refresh=args.refresh)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    graph = _load_json(GRAPH_JSON)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    by_ext: Counter[str] = Counter()
    by_area: Counter[str] = Counter()
    local_files = {str(n.get("id", "")) for n in nodes}
    degree: Counter[str] = Counter()

    total_bytes = 0
    for n in nodes:
        ext = str(n.get("ext", "") or "(none)")
        by_ext[ext] += 1
        fid = str(n.get("id", ""))
        if "/" in fid:
            by_area[fid.split("/", 1)[0]] += 1
        else:
            by_area["(root)"] += 1
        total_bytes += int(n.get("size", 0) or 0)

    for e in edges:
        frm = str(e.get("from", ""))
        to = str(e.get("to", ""))
        if frm in local_files:
            degree[frm] += 1
        if to in local_files:
            degree[to] += 1

    top_connected = sorted(
        [{"file": k, "degree": v} for k, v in degree.items() if k in local_files],
        key=lambda x: (-x["degree"], x["file"]),
    )[: args.top]
    top_large = sorted(
        [
            {"file": str(n.get("id", "")), "size": int(n.get("size", 0) or 0)}
            for n in nodes
        ],
        key=lambda x: (-x["size"], x["file"]),
    )[: args.top]

    lines: list[str] = []
    lines.append("# Project Read Summary")
    lines.append("")
    lines.append(f"- root: {graph.get('root')}")
    lines.append(f"- files: {graph.get('node_count', len(nodes))}")
    lines.append(f"- relations: {graph.get('edge_count', len(edges))}")
    lines.append(f"- total_size_bytes: {total_bytes}")
    lines.append("")
    lines.append("## Top Areas")
    for name, count in by_area.most_common(args.top):
        lines.append(f"- {name}: {count}")
    lines.append("")
    lines.append("## Top Extensions")
    for ext, count in by_ext.most_common(args.top):
        lines.append(f"- {ext}: {count}")
    lines.append("")
    lines.append("## Most Connected Files")
    for row in top_connected:
        lines.append(f"- {row['file']} (degree={row['degree']})")
    lines.append("")
    lines.append("## Largest Files")
    for row in top_large:
        lines.append(f"- {row['file']} (bytes={row['size']})")

    summary_text = "\n".join(lines)
    full_context_tokens_est = max(1, total_bytes // 4)
    summary_tokens_est = _est_tokens(summary_text)
    reduction_pct = round(
        (full_context_tokens_est - summary_tokens_est) * 100 / max(1, full_context_tokens_est),
        2,
    )

    payload = {
        "root": graph.get("root"),
        "node_count": graph.get("node_count", len(nodes)),
        "edge_count": graph.get("edge_count", len(edges)),
        "total_size_bytes": total_bytes,
        "top_areas": [{"name": k, "count": v} for k, v in by_area.most_common(args.top)],
        "top_extensions": [{"ext": k, "count": v} for k, v in by_ext.most_common(args.top)],
        "top_connected_files": top_connected,
        "top_large_files": top_large,
        "token_compare_est": {
            "full_context_tokens_est": full_context_tokens_est,
            "summary_tokens_est": summary_tokens_est,
            "reduction_pct_est": reduction_pct,
        },
        "summary_text": summary_text,
    }

    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".json":
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            out.write_text(summary_text + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(summary_text)
    print("")
    print("## Token Compare (Estimate)")
    print(f"- full_context_tokens_est: {full_context_tokens_est}")
    print(f"- summary_tokens_est: {summary_tokens_est}")
    print(f"- reduction_pct_est: {reduction_pct}%")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="claude-safe CLI")
    p.add_argument("--project-root", default=str(DEFAULT_ROOT), help="Target project root")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Check environment and scripts")
    d.set_defaults(func=cmd_doctor)

    s = sub.add_parser("scan", help="Build info graph")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("retrieve", help="Retrieve ranked files for a query")
    r.add_argument("--query", required=True)
    r.add_argument("--top-files", type=int, default=8)
    r.add_argument("--top-edges", type=int, default=20)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_retrieve)

    run = sub.add_parser("run", help="Run dry-run/apply safe fixer and write A/B report")
    run.add_argument("--query", required=True)
    run.add_argument("--codex-tokens", type=int, default=0)
    run.add_argument("--model", default="gpt-5-mini")
    run.add_argument("--top-files", type=int, default=3)
    run.add_argument("--top-edges", type=int, default=24)
    run.add_argument("--apply", action="store_true")
    run.add_argument("--validate", action="store_true")
    run.add_argument("--check-cmd", default="")
    run.add_argument("--allow-fullfile", action="store_true")
    run.add_argument("--out", default="")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    chat = sub.add_parser("chat", help="Interactive one-command mode: dry-run then optional apply")
    chat.add_argument("--model", default="gpt-5-mini")
    chat.add_argument("--codex-tokens", type=int, default=0, help="Optional real Codex tokens for % reduction")
    chat.add_argument("--top-files", type=int, default=3)
    chat.add_argument("--top-edges", type=int, default=24)
    chat.set_defaults(func=cmd_chat)

    l = sub.add_parser("ledger", help="Show token ledger from latest/specified report")
    l.add_argument("--report", default="")
    l.set_defaults(func=cmd_ledger)

    logs = sub.add_parser("logs", help="Show MCP tool-call logs")
    logs.add_argument("--last", type=int, default=25)
    logs.set_defaults(func=cmd_logs)

    rp = sub.add_parser("read-project", help="Scan + summarize project for comparison baselines")
    rp.add_argument("--refresh", action="store_true", help="Force re-scan before summary")
    rp.add_argument("--top", type=int, default=10, help="Top N rows per section")
    rp.add_argument("--out", default="", help="Optional output path (.md or .json)")
    rp.add_argument("--json", action="store_true")
    rp.set_defaults(func=cmd_read_project)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
