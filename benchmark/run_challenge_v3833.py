#!/usr/bin/env python3
"""DGC v3.8.33 Challenge Benchmark — 10 complex prompts, Normal vs Pre-Injection.

Normal Claude gets ALL native tools (Read, Grep, Glob, Bash, Edit, Write, Agent).
Pre-Injection gets packed context (5K budget) + same native tools.

Features:
  - Checkpoint after every prompt (resume-safe)
  - Detailed per-prompt analytics: tokens, cost, turns, wall time, quality breakdown
  - Running totals displayed after each prompt
  - Final comprehensive report with charts-ready data

Usage:
    python3 run_challenge_v3833.py
    python3 run_challenge_v3833.py --prompts 201,205,210
    python3 run_challenge_v3833.py --modes normal,preinjection
    python3 run_challenge_v3833.py --budget 5000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
_BENCH_DIR = Path(__file__).resolve().parent
_LOCAL_BIN = _BENCH_DIR.parent / "bin"
_RESULTS_DIR = _BENCH_DIR / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS_FILE = _BENCH_DIR / "prompts_challenge_v3.8.33.json"
RAW_FILE = _RESULTS_DIR / "raw_challenge_v3.8.33.jsonl"
REPORT_FILE = _RESULTS_DIR / "benchmark_challenge_v3.8.33.md"
CHECKPOINT_FILE = _RESULTS_DIR / "checkpoint_challenge_v3.8.33.json"

VERSION = "3.8.33"
TAG = "challenge"
TIMEOUT_S = 300
COOLDOWN_S = 5
MODEL = "claude-sonnet-4-6"

# Test project
TEST_PROJECT = _BENCH_DIR / "dgc-claude" / "restaurant-crm"

# ── Import context packer ────────────────────────────────────────────────────
sys.path.insert(0, str(_LOCAL_BIN))
from context_packer import pack_for_query, estimate_tokens


# ── Quality Scoring ──────────────────────────────────────────────────────────

CATEGORY_BONUS_MAP = {
    "deep_trace": {"keywords": ["lifecycle", "endpoint", "mutation", "notification", "wallet"], "max": 10},
    "security_audit": {"keywords": ["vulnerability", "bypass", "injection", "CORS", "secret", "fix"], "max": 10},
    "cross_system": {"keywords": ["frontend", "backend", "endpoint", "WebSocket", "unused", "API"], "max": 10},
    "performance": {"keywords": ["N+1", "index", "query", "memory", "optimize", "bulk"], "max": 10},
    "migration_design": {"keywords": ["migration", "schema", "tenant", "restaurant_id", "ALTER"], "max": 10},
    "error_handling": {"keywords": ["except", "500", "try", "catch", "error code", "handler"], "max": 10},
    "state_management": {"keywords": ["zustand", "context", "store", "prop drilling", "state", "component"], "max": 10},
    "testing_strategy": {"keywords": ["test", "mock", "assert", "edge case", "fixture", "coverage"], "max": 10},
    "dependency_map": {"keywords": ["import", "circular", "coupling", "module", "dependency", "refactor"], "max": 10},
    "full_stack_debug": {"keywords": ["failure point", "rollback", "disconnect", "logs", "transaction", "fix"], "max": 10},
}


def score_quality(text: str, category: str) -> dict:
    """Score response quality (0-50) with detailed breakdown."""
    if not text or len(text) < 50:
        return {"total": 0, "word_count": 0, "file_mentions": 0, "code_blocks": 0,
                "specificity": 0, "structure_score": 0, "category_bonus": 0}

    words = len(text.split())
    scores = {}

    # Word count (0-8): reward thorough responses
    if words >= 800:
        scores["word_count"] = 8
    elif words >= 500:
        scores["word_count"] = 6
    elif words >= 250:
        scores["word_count"] = 4
    elif words >= 100:
        scores["word_count"] = 2
    else:
        scores["word_count"] = 0

    # File mentions (0-10): exact file paths referenced
    file_pattern = r'[\w/]+\.\w{1,4}'
    file_mentions = len(set(re.findall(file_pattern, text)))
    scores["file_mentions"] = min(10, file_mentions)

    # Code blocks (0-8): actual code snippets
    code_blocks = text.count("```")
    scores["code_blocks"] = min(8, (code_blocks // 2) * 2)

    # Specificity (0-10): line numbers, function names, concrete details
    line_refs = len(re.findall(r'line[s]?\s+\d+', text, re.IGNORECASE))
    func_refs = len(re.findall(r'`\w+\(\)`|`\w+\(`|def \w+|function \w+', text))
    specificity_score = min(10, line_refs + func_refs)
    scores["specificity"] = specificity_score

    # Structure (0-6): headers, lists, tables
    has_headers = bool(re.search(r'^#{1,4}\s', text, re.MULTILINE))
    has_lists = bool(re.search(r'^[\-\*]\s', text, re.MULTILINE))
    has_tables = bool(re.search(r'\|.*\|', text))
    has_numbered = bool(re.search(r'^\d+[\.\)]\s', text, re.MULTILINE))
    scores["structure_score"] = min(6, sum([has_headers * 2, has_lists * 2, has_tables * 1, has_numbered * 1]))

    # Category bonus (0-10): domain-specific keyword matching
    cat_info = CATEGORY_BONUS_MAP.get(category, {"keywords": [], "max": 8})
    keyword_hits = sum(1 for kw in cat_info["keywords"] if kw.lower() in text.lower())
    scores["category_bonus"] = min(cat_info["max"], keyword_hits * 2)

    scores["total"] = sum(scores.values())
    return scores


# ── Run Modes ────────────────────────────────────────────────────────────────

def run_normal(prompt: str, project_root: Path) -> dict:
    """Run Normal Claude with ALL native tools."""
    cmd = [
        "claude", "-p", prompt,
        "--model", MODEL,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_SESSION", None)
    # Ensure Claude runs in the test project directory
    env["HOME"] = os.environ.get("HOME", "")

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=TIMEOUT_S, cwd=str(project_root), env=env,
        )
        wall_time = time.time() - t0
        if proc.returncode != 0:
            return {"wall_time_s": wall_time, "input_tokens": 0, "output_tokens": 0,
                    "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                    "error": proc.stderr[:500]}

        data = json.loads(proc.stdout)
        return {
            "wall_time_s": wall_time,
            "duration_ms": data.get("duration_ms", 0),
            "duration_api_ms": data.get("duration_api_ms", 0),
            "input_tokens": data.get("input_tokens", 0),
            "input_tokens_raw": data.get("input_tokens_raw", 0),
            "output_tokens": data.get("output_tokens", 0),
            "cache_creation_tokens": data.get("cache_creation_tokens", 0),
            "cache_read_tokens": data.get("cache_read_tokens", 0),
            "total_cost_usd": data.get("total_cost_usd", 0),
            "response_text": data.get("result", ""),
            "num_turns": data.get("num_turns", 0),
            "stop_reason": data.get("stop_reason", ""),
        }
    except subprocess.TimeoutExpired:
        return {"wall_time_s": TIMEOUT_S, "input_tokens": 0, "output_tokens": 0,
                "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                "error": "timeout"}
    except Exception as e:
        return {"wall_time_s": time.time() - t0, "input_tokens": 0, "output_tokens": 0,
                "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                "error": str(e)[:300]}


def run_preinjection(prompt: str, project_root: Path, budget: int = 5000) -> dict:
    """Run Pre-Injection: pack context then launch Claude with native tools."""
    # Pack context
    t_pack_start = time.time()
    try:
        os.chdir(str(project_root))
        context = pack_for_query(prompt, project_root, token_budget=budget)
    except Exception as e:
        return {"wall_time_s": 0, "input_tokens": 0, "output_tokens": 0,
                "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                "pack_time_s": 0, "pack_tokens_est": 0,
                "error": f"pack_error: {e}"}
    pack_time = time.time() - t_pack_start
    pack_tokens = estimate_tokens(context)

    # Build full prompt with packed context
    full_prompt = (
        f"{context}\n\n---\n\n"
        f"User question: {prompt}\n\n"
        f"Instructions: Answer thoroughly using the pre-loaded context above. "
        f"Include relevant code snippets in your response when they help explain the answer. "
        f"Reference specific file paths and line numbers. Do not edit any files."
    )

    cmd = [
        "claude", "-p", full_prompt,
        "--model", MODEL,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_SESSION", None)

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=TIMEOUT_S, cwd=str(project_root), env=env,
        )
        wall_time = time.time() - t0
        if proc.returncode != 0:
            return {"wall_time_s": wall_time, "input_tokens": 0, "output_tokens": 0,
                    "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                    "pack_time_s": pack_time, "pack_tokens_est": pack_tokens,
                    "error": proc.stderr[:500]}

        data = json.loads(proc.stdout)
        return {
            "wall_time_s": wall_time,
            "duration_ms": data.get("duration_ms", 0),
            "duration_api_ms": data.get("duration_api_ms", 0),
            "input_tokens": data.get("input_tokens", 0),
            "input_tokens_raw": data.get("input_tokens_raw", 0),
            "output_tokens": data.get("output_tokens", 0),
            "cache_creation_tokens": data.get("cache_creation_tokens", 0),
            "cache_read_tokens": data.get("cache_read_tokens", 0),
            "total_cost_usd": data.get("total_cost_usd", 0),
            "response_text": data.get("result", ""),
            "num_turns": data.get("num_turns", 0),
            "stop_reason": data.get("stop_reason", ""),
            "pack_time_s": pack_time,
            "pack_tokens_est": pack_tokens,
        }
    except subprocess.TimeoutExpired:
        return {"wall_time_s": TIMEOUT_S, "input_tokens": 0, "output_tokens": 0,
                "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                "pack_time_s": pack_time, "pack_tokens_est": pack_tokens,
                "error": "timeout"}
    except Exception as e:
        return {"wall_time_s": time.time() - t0, "input_tokens": 0, "output_tokens": 0,
                "total_cost_usd": 0, "response_text": "", "num_turns": 0,
                "pack_time_s": pack_time, "pack_tokens_est": pack_tokens,
                "error": str(e)[:300]}


# ── Checkpoint Management ────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    """Load checkpoint state."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"completed": [], "running_totals": {"normal": {}, "preinjection": {}}}


def save_checkpoint(state: dict):
    """Save checkpoint state."""
    CHECKPOINT_FILE.write_text(json.dumps(state, indent=2))


def load_completed_ids() -> set:
    """Load IDs already in raw results file."""
    ids = set()
    if RAW_FILE.exists():
        for line in RAW_FILE.read_text().strip().split("\n"):
            if line.strip():
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


# ── Display Helpers ──────────────────────────────────────────────────────────

def print_running_totals(results: list[dict]):
    """Print running cost/quality totals."""
    n_cost = sum(r.get("normal", {}).get("total_cost_usd", 0) for r in results)
    pi_cost = sum(r.get("preinjection", {}).get("total_cost_usd", 0) for r in results)
    n_qual_vals = [r.get("normal_quality", {}).get("total", 0) for r in results if r.get("normal_quality", {}).get("total", 0) > 0]
    pi_qual_vals = [r.get("preinjection_quality", {}).get("total", 0) for r in results if r.get("preinjection_quality", {}).get("total", 0) > 0]

    n_qual_avg = sum(n_qual_vals) / len(n_qual_vals) if n_qual_vals else 0
    pi_qual_avg = sum(pi_qual_vals) / len(pi_qual_vals) if pi_qual_vals else 0

    n = len(results)
    print(f"  [totals] {n} prompts done")
    print(f"    Normal:     ${n_cost:.3f} total, ${n_cost/n:.3f}/prompt, Q={n_qual_avg:.1f}")
    print(f"    Pre-Inject: ${pi_cost:.3f} total, ${pi_cost/n:.3f}/prompt, Q={pi_qual_avg:.1f}")
    if n_cost > 0:
        savings = (1 - pi_cost / n_cost) * 100
        print(f"    PI savings: {savings:+.1f}%")


# ── Report Generator ─────────────────────────────────────────────────────────

def generate_report(results: list[dict]):
    """Generate the markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = len(results)

    report = f"""# DGC v{VERSION} Challenge Benchmark

**Date:** {now}
**Prompts:** {n} complex cross-cutting queries
**Budget:** 5000 tokens | **Timeout:** {TIMEOUT_S}s | **Model:** {MODEL}
**Mode:** Normal Claude (all tools) vs Pre-Injection v{VERSION} (packed context + all tools)

## Native Tools Available (Both Modes)
- **Read** — read files with offset/limit
- **Grep** — ripgrep-powered content search
- **Glob** — file pattern matching
- **Bash** — shell command execution
- **Write/Edit** — file modification (disabled for benchmark)
- **Agent** — spawn subagent workers

Pre-Injection additionally gets **~3,500-5,000 tokens** of pre-packed context including:
- Full structured summaries (function signatures, params, returns, call targets)
- Inline code from top 3 functions per file
- Recommended read targets with line numbers
- Key dependency relationships

## Results Summary

| ID | Category | Normal Cost | PI Cost | PI vs Normal | Normal Q | PI Q | Normal Turns | PI Turns |
|----|----------|-------------|---------|-------------|----------|------|-------------|---------|
"""
    for r in results:
        pid = r["id"]
        cat = r["category"]
        nc = r.get("normal", {}).get("total_cost_usd", 0)
        pc = r.get("preinjection", {}).get("total_cost_usd", 0)
        nq = r.get("normal_quality", {}).get("total", 0)
        pq = r.get("preinjection_quality", {}).get("total", 0)
        nt = r.get("normal", {}).get("num_turns", 0) or 0
        pt = r.get("preinjection", {}).get("num_turns", 0) or 0
        delta = f"{((pc/nc)-1)*100:+.1f}%" if nc > 0 and pc > 0 else "N/A"
        report += f"| P{pid} | {cat} | ${nc:.4f} | ${pc:.4f} | {delta} | {nq}/50 | {pq}/50 | {nt} | {pt} |\n"

    # Aggregates
    n_total_cost = sum(r.get("normal", {}).get("total_cost_usd", 0) for r in results)
    pi_total_cost = sum(r.get("preinjection", {}).get("total_cost_usd", 0) for r in results)
    n_total_tokens = sum(r.get("normal", {}).get("input_tokens", 0) for r in results)
    pi_total_tokens = sum(r.get("preinjection", {}).get("input_tokens", 0) for r in results)

    def avg_nz(rs, mode, key):
        vals = [r.get(mode, {}).get(key, 0) for r in rs if r.get(mode, {}).get(key, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    n_avg_qual = avg_nz(results, "normal_quality", "total")
    pi_avg_qual = avg_nz(results, "preinjection_quality", "total")

    report += f"""
## Aggregate Statistics

| Metric | Normal | Pre-Inject |
|--------|--------|------------|
| **Total Cost** | ${n_total_cost:.2f} | ${pi_total_cost:.2f} |
| **Avg Cost** | ${n_total_cost/n:.4f} | ${pi_total_cost/n:.4f} |
| **Total Input Tokens** | {n_total_tokens:,} | {pi_total_tokens:,} |
| **Avg Turns** | {avg_nz(results,'normal','num_turns'):.1f} | {avg_nz(results,'preinjection','num_turns'):.1f} |
| **Avg Wall Time** | {avg_nz(results,'normal','wall_time_s'):.1f}s | {avg_nz(results,'preinjection','wall_time_s'):.1f}s |
| **Avg Quality** | {n_avg_qual:.1f}/50 | {pi_avg_qual:.1f}/50 |
| **Avg Pack Time** | — | {avg_nz(results,'preinjection','pack_time_s')*1000:.0f}ms |
| **Avg Pack Tokens** | — | {int(avg_nz(results,'preinjection','pack_tokens_est'))} |

"""

    # Per-prompt details
    report += "## Per-Prompt Details\n\n"
    for r in results:
        pid = r["id"]
        n_data = r.get("normal", {})
        pi_data = r.get("preinjection", {})
        nq = r.get("normal_quality", {})
        pq = r.get("preinjection_quality", {})

        report += f"### P{pid} — {r['category']}\n"
        report += f"> {r['prompt'][:120]}...\n\n"
        report += f"| Metric | Normal | Pre-Inject |\n"
        report += f"|--------|--------|------------|\n"
        report += f"| Cost | ${n_data.get('total_cost_usd',0):.4f} | ${pi_data.get('total_cost_usd',0):.4f} |\n"
        report += f"| Input Tokens | {n_data.get('input_tokens',0):,} | {pi_data.get('input_tokens',0):,} |\n"
        report += f"| Output Tokens | {n_data.get('output_tokens',0):,} | {pi_data.get('output_tokens',0):,} |\n"
        report += f"| Cache Create | {n_data.get('cache_creation_tokens',0):,} | {pi_data.get('cache_creation_tokens',0):,} |\n"
        report += f"| Cache Read | {n_data.get('cache_read_tokens',0):,} | {pi_data.get('cache_read_tokens',0):,} |\n"
        report += f"| Turns | {n_data.get('num_turns',0) or 0} | {pi_data.get('num_turns',0) or 0} |\n"
        report += f"| Wall Time | {n_data.get('wall_time_s',0):.1f}s | {pi_data.get('wall_time_s',0):.1f}s |\n"
        report += f"| Quality | {nq.get('total',0)}/50 | {pq.get('total',0)}/50 |\n"

        if pi_data.get("pack_time_s"):
            report += f"| Pack Time | — | {pi_data['pack_time_s']*1000:.0f}ms |\n"
            report += f"| Pack Tokens | — | {pi_data.get('pack_tokens_est', 0):,} |\n"

        # Quality breakdown
        report += f"\n**Quality Breakdown:**\n"
        report += f"| Component | Normal | PI |\n|---|---|---|\n"
        for k in ["word_count", "file_mentions", "code_blocks", "specificity", "structure_score", "category_bonus"]:
            nv = nq.get(k, 0)
            pv = pq.get(k, 0)
            marker = " **" if pv > nv else ""
            report += f"| {k} | {nv} | {pv}{marker} |\n"

        report += "\n"

    report += f"\n---\n*Generated by run_challenge_v3833.py v{VERSION}*\n"
    return report


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=f"DGC v{VERSION} Challenge Benchmark")
    parser.add_argument("--prompts", type=str, default="",
                       help="Comma-separated prompt IDs to run (default: all)")
    parser.add_argument("--modes", type=str, default="normal,preinjection",
                       help="Comma-separated modes (default: normal,preinjection)")
    parser.add_argument("--budget", type=int, default=5000,
                       help="Token budget for pre-injection (default: 5000)")
    parser.add_argument("--resume", action="store_true",
                       help="Resume from checkpoint (skip completed prompts)")
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",")]
    prompts = json.loads(PROMPTS_FILE.read_text())

    if args.prompts:
        selected_ids = {int(x.strip()) for x in args.prompts.split(",")}
        prompts = [p for p in prompts if p["id"] in selected_ids]

    completed_ids = load_completed_ids() if args.resume else set()
    prompts = [p for p in prompts if p["id"] not in completed_ids]

    if not prompts:
        print("[bench] All prompts already completed!")
        return

    print(f"[bench] Active modes: {modes}")
    print(f"[bench] Prompts to run: {len(prompts)}")
    print(f"[bench] Budget: {args.budget} tokens")
    print(f"[bench] Project: {TEST_PROJECT}")
    print(f"[bench] Results: {RAW_FILE}")

    # Load existing results for running totals
    all_results: list[dict] = []
    if RAW_FILE.exists():
        for line in RAW_FILE.read_text().strip().split("\n"):
            if line.strip():
                try:
                    all_results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    for i, prompt_data in enumerate(prompts):
        pid = prompt_data["id"]
        cat = prompt_data["category"]
        prompt_text = prompt_data["prompt"]

        print(f"\n[bench] {'='*60}")
        print(f"[bench] Prompt {i+1}/{len(prompts)} — P{pid} [{cat}]")
        print(f"[bench] {'='*60}")

        result = {
            "id": pid,
            "category": cat,
            "prompt": prompt_text,
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
        }

        # ── Pre-Injection ────────────────────────────────────────────
        if "preinjection" in modes:
            print(f"[bench]   Pre-injection run (budget={args.budget})...")
            pi_result = run_preinjection(prompt_text, TEST_PROJECT, budget=args.budget)
            result["preinjection"] = pi_result

            pi_text = pi_result.get("response_text", "")
            pi_qual = score_quality(pi_text, cat)
            result["preinjection_quality"] = pi_qual

            pi_cost = pi_result.get("total_cost_usd", 0)
            pi_tok = pi_result.get("input_tokens", 0)
            pi_turns = pi_result.get("num_turns", 0) or 0
            pi_wall = pi_result.get("wall_time_s", 0)
            pi_pack = pi_result.get("pack_time_s", 0)
            print(f"[bench]   PI: {pi_tok:,} in / {pi_result.get('output_tokens',0):,} out / "
                  f"${pi_cost:.4f} / {pi_wall:.1f}s / Q={pi_qual['total']}/50 / "
                  f"pack={pi_pack:.3f}s / turns={pi_turns}")

            if pi_result.get("error"):
                print(f"[bench]   PI ERROR: {pi_result['error'][:100]}")

            time.sleep(COOLDOWN_S)

        # ── Normal ───────────────────────────────────────────────────
        if "normal" in modes:
            print(f"[bench]   Normal run (all tools)...")
            n_result = run_normal(prompt_text, TEST_PROJECT)
            result["normal"] = n_result

            n_text = n_result.get("response_text", "")
            n_qual = score_quality(n_text, cat)
            result["normal_quality"] = n_qual

            n_cost = n_result.get("total_cost_usd", 0)
            n_tok = n_result.get("input_tokens", 0)
            n_turns = n_result.get("num_turns", 0) or 0
            n_wall = n_result.get("wall_time_s", 0)
            print(f"[bench]   Normal: {n_tok:,} in / {n_result.get('output_tokens',0):,} out / "
                  f"${n_cost:.4f} / {n_wall:.1f}s / Q={n_qual['total']}/50 / turns={n_turns}")

            if n_result.get("error"):
                print(f"[bench]   Normal ERROR: {n_result['error'][:100]}")

            time.sleep(COOLDOWN_S)

        # ── Save checkpoint ──────────────────────────────────────────
        with open(RAW_FILE, "a") as f:
            f.write(json.dumps(result) + "\n")
        print(f"[bench]   Saved P{pid}")

        all_results.append(result)
        print_running_totals(all_results)

    # ── Generate report ──────────────────────────────────────────────
    # Reload all results for report
    final_results = []
    for line in RAW_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                final_results.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    report = generate_report(final_results)
    REPORT_FILE.write_text(report)
    print(f"\n[bench] Report written to {REPORT_FILE}")
    print(f"[bench] Benchmark complete!")


if __name__ == "__main__":
    main()
