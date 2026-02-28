#!/usr/bin/env python3
"""Compare codex-style broad context vs info-graph context across 10 queries."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from graph_builder import scan
from dg import DEFAULT_ROOT, retrieve


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
GRAPH_JSON = DATA_DIR / "info_graph.json"


@dataclass
class QuerySpec:
    query: str
    expected_keywords: list[str]
    expected_paths: list[str]


@dataclass
class QualityBreakdown:
    score: float
    keyword_recall: float
    path_recall: float
    actionability: float
    hallucination_penalty: float
    noise_penalty: float


def default_queries() -> list[QuerySpec]:
    return [
        QuerySpec(
            query="fix checkout pricing flow bug when invoice fails",
            expected_keywords=["checkout", "pricing", "invoice", "validation"],
            expected_paths=["customer-portal/src/pages/Checkout.tsx", "pricing", "order"],
        ),
        QuerySpec(
            query="update whatsapp feature so it can generate invoice pdf",
            expected_keywords=["whatsapp", "invoice", "order", "customer"],
            expected_paths=["backend/app/api/webhook/whatsapp.py", "backend/app/services/whatsapp_tasks.py"],
        ),
        QuerySpec(
            query="improve customer portal cart checkout state handling",
            expected_keywords=["cart", "checkout", "state", "auth"],
            expected_paths=["customer-portal/src/pages/Checkout.tsx", "cartStore", "authStore"],
        ),
        QuerySpec(
            query="add retry logic for whatsapp send failures",
            expected_keywords=["whatsapp", "retry", "error", "task"],
            expected_paths=["whatsapp", "tasks.py", "services"],
        ),
        QuerySpec(
            query="fix order API response mismatch for invoice endpoint",
            expected_keywords=["order", "api", "invoice", "response"],
            expected_paths=["backend/app/api", "orders.py", "invoice"],
        ),
        QuerySpec(
            query="audit authentication checks in checkout submission flow",
            expected_keywords=["auth", "checkout", "token", "validation"],
            expected_paths=["Checkout.tsx", "authStore", "api"],
        ),
        QuerySpec(
            query="reduce duplicate calls in customer checkout query hooks",
            expected_keywords=["checkout", "query", "react-query", "duplicate"],
            expected_paths=["Checkout.tsx", "react-query", "services/api"],
        ),
        QuerySpec(
            query="ensure restaurant location update does not break billing flow",
            expected_keywords=["restaurant", "location", "billing", "flow"],
            expected_paths=["restaurant-portal/src/pages/RestauranLocationUpdate.tsx", "billing"],
        ),
        QuerySpec(
            query="add logging around invoice creation and webhook status",
            expected_keywords=["logging", "invoice", "webhook", "status"],
            expected_paths=["webhook", "invoice", "backend/app"],
        ),
        QuerySpec(
            query="patch checkout page to show clear error for payment failure",
            expected_keywords=["checkout", "error", "payment", "ui"],
            expected_paths=["customer-portal/src/pages/Checkout.tsx", "components/ui"],
        ),
    ]


def load_graph() -> dict:
    if GRAPH_JSON.exists():
        return json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    g = scan(DEFAULT_ROOT)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_JSON.write_text(json.dumps(g, indent=2), encoding="utf-8")
    return g


def chars_to_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def count_tokens_openai(text: str, model: str) -> tuple[int, str | None]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return chars_to_tokens(text), "OPENAI_API_KEY not set; using chars/4 fallback"

    payload = {"model": model, "input": text, "max_output_tokens": 1}
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url="https://api.openai.com/v1/responses",
        data=raw,
        method="POST",
        headers={"content-type": "application/json", "authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return chars_to_tokens(text), f"OpenAI HTTP {e.code}; using fallback"
    except Exception as e:  # noqa: BLE001
        return chars_to_tokens(text), f"OpenAI error ({e}); using fallback"

    usage = data.get("usage", {})
    for key in ("input_tokens", "prompt_tokens", "total_tokens"):
        if key in usage:
            try:
                return int(usage[key]), None
            except (TypeError, ValueError):
                continue
    return chars_to_tokens(text), "OpenAI usage fields missing; using fallback"


def extract_paths(text: str) -> list[str]:
    patt = r"[A-Za-z0-9_\-./]+\.(?:tsx|ts|py|go|js|jsx|md|json|yaml|yml)"
    return list(dict.fromkeys(re.findall(patt, text)))


def extract_path_like_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        if "/" in line and ("--" in line or line.strip().startswith("- ")):
            lines.append(line.strip("- ").strip())
    return lines


def synthesize_from_context(context: str, mode: str) -> str:
    lines = extract_path_like_lines(context)
    if mode == "codex_mimic":
        chosen = lines[:18]
        return "Plan:\n" + "\n".join(f"- Review {x}" for x in chosen)
    chosen = lines[:8]
    return "Plan:\n" + "\n".join(f"- Update {x}" for x in chosen)


def run_openai_response(context: str, model: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return synthesize_from_context(context, mode="info_graph")
    prompt = (
        "You are a coding assistant. Given context below, provide concise actionable plan with files and risks.\n\n"
        f"{context}\n"
    )
    payload = {"model": model, "input": prompt, "max_output_tokens": 280}
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url="https://api.openai.com/v1/responses",
        data=raw,
        method="POST",
        headers={"content-type": "application/json", "authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return synthesize_from_context(context, mode="info_graph")
    text = data.get("output_text", "")
    if text:
        return text
    return synthesize_from_context(context, mode="info_graph")


def quality_score(output: str, spec: QuerySpec, graph: dict) -> QualityBreakdown:
    low = output.lower()
    kw_hits = sum(1 for k in spec.expected_keywords if k.lower() in low)
    path_hits = sum(1 for p in spec.expected_paths if p.lower() in low)
    kw_recall = kw_hits / max(1, len(spec.expected_keywords))
    path_recall = path_hits / max(1, len(spec.expected_paths))

    # Actionability: count concrete next-step bullets.
    action_lines = [
        line for line in output.splitlines()
        if line.strip().startswith("-") and any(v in line.lower() for v in ("fix", "update", "review", "test", "patch", "validate"))
    ]
    actionability = min(1.0, len(action_lines) / 6.0)

    # Hallucination penalty: path-like refs not present in scanned graph nodes.
    known_paths = {str(n.get("id", "")).lower() for n in graph.get("nodes", [])}
    mentioned = [p.lower() for p in extract_paths(output)]
    unknown_mentions = [p for p in mentioned if p and p not in known_paths]
    hallucination_penalty = min(0.35, len(unknown_mentions) * 0.05)

    noise_hits = 0
    for bad in ("site-packages", "venv/", "node_modules", "botocore"):
        if bad in low:
            noise_hits += 1
    noise_penalty = min(0.3, 0.1 * noise_hits)

    # Stricter weighted rubric.
    score = (
        0.35 * kw_recall
        + 0.35 * path_recall
        + 0.30 * actionability
        - hallucination_penalty
        - noise_penalty
    ) * 100
    score = max(0.0, min(100.0, score))
    return QualityBreakdown(
        score=score,
        keyword_recall=kw_recall,
        path_recall=path_recall,
        actionability=actionability,
        hallucination_penalty=hallucination_penalty,
        noise_penalty=noise_penalty,
    )


def build_baseline_context(graph: dict, spec: QuerySpec) -> str:
    parts = []
    parts.append("System: You are coding agent. Use broad context and preserve behavior.")
    parts.append("\nConversation (broad):")
    convo = [
        "User requested a change in a critical flow.",
        "Assistant searched many files and tried to preserve surrounding behavior.",
        "Need to consider auth, billing, checkout, webhooks, and side effects.",
    ]
    parts.append("\n".join(convo * 14))
    parts.append("\nPotentially relevant files:")
    for n in graph.get("nodes", [])[:200]:
        parts.append(f"- {n.get('id')}")
    parts.append("\nPotentially relevant relations:")
    for e in graph.get("edges", [])[:360]:
        parts.append(f"- {e.get('from')} --{e.get('rel')}--> {e.get('to')}")
    parts.append(f"\nCurrent request:\n{spec.query}")
    return "\n".join(parts)


def build_graph_context(graph: dict, spec: QuerySpec) -> str:
    ret = retrieve(graph, spec.query, top_files=20, top_edges=40)
    parts = []
    parts.append("System: Use compact graph-backed context only.")
    parts.append(f"\nCurrent request:\n{spec.query}\n")
    parts.append("Relevant files:")
    for f in ret.files:
        parts.append(f"- {f.get('id')}")
    parts.append("\nRelevant relations:")
    for e in ret.edges:
        parts.append(f"- {e.get('from')} --{e.get('rel')}--> {e.get('to')}")
    return "\n".join(parts)


def build_markdown_report(summary: dict, out_md: Path) -> None:
    lines: list[str] = []
    lines.append("# 10-Query Quality Leaderboard")
    lines.append("")
    lines.append(f"- token_provider: `{summary['token_provider']}`")
    lines.append(f"- real_output: `{summary['real_output']}`")
    lines.append(f"- model: `{summary['model']}`")
    lines.append(f"- avg_token_reduction: **{summary['avg_token_reduction_pct']}%**")
    lines.append(f"- avg_quality_delta: **{summary['avg_quality_delta']}**")
    lines.append("")
    lines.append("| # | Query | Baseline Tokens | Graph Tokens | Reduction | Baseline Q | Graph Q | Delta |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for i, row in enumerate(summary["queries"], start=1):
        lines.append(
            f"| {i} | {row['query']} | {row['baseline_tokens']} | {row['graph_tokens']} | "
            f"{row['token_reduction_pct']}% | {row['baseline_quality']} | {row['graph_quality']} | {row['quality_delta']} |"
        )
    lines.append("")
    lines.append("## Side-by-Side Outputs")
    lines.append("")
    for i, row in enumerate(summary["queries"], start=1):
        lines.append(f"### Q{i}. {row['query']}")
        lines.append("")
        lines.append("**Baseline (codex_mimic)**")
        lines.append("")
        lines.append("```text")
        lines.append(row.get("baseline_output", "").strip() or "(empty)")
        lines.append("```")
        lines.append("")
        lines.append("**Info Graph**")
        lines.append("")
        lines.append("```text")
        lines.append(row.get("graph_output", "").strip() or "(empty)")
        lines.append("```")
        lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare quality/token usage across 10 queries.")
    parser.add_argument("--token-provider", choices=["heuristic", "openai"], default="heuristic")
    parser.add_argument("--model", default="gpt-5-mini", help="Model for token counting/output generation when openai mode is used.")
    parser.add_argument("--real-output", action="store_true", help="Generate outputs via OpenAI; default uses deterministic synth.")
    parser.add_argument("--out", default=str(DATA_DIR / "compare_quality_report.json"))
    parser.add_argument("--out-md", default=str(DATA_DIR / "compare_quality_report.md"))
    args = parser.parse_args()

    graph = load_graph()
    specs = default_queries()

    rows = []
    warnings: list[str] = []
    for i, spec in enumerate(specs, start=1):
        base_ctx = build_baseline_context(graph, spec)
        graph_ctx = build_graph_context(graph, spec)

        if args.token_provider == "openai":
            base_tokens, w1 = count_tokens_openai(base_ctx, args.model)
            graph_tokens, w2 = count_tokens_openai(graph_ctx, args.model)
            if w1:
                warnings.append(f"Q{i} baseline: {w1}")
            if w2:
                warnings.append(f"Q{i} graph: {w2}")
        else:
            base_tokens = chars_to_tokens(base_ctx)
            graph_tokens = chars_to_tokens(graph_ctx)

        if args.real_output:
            base_out = run_openai_response(base_ctx, args.model)
            graph_out = run_openai_response(graph_ctx, args.model)
        else:
            base_out = synthesize_from_context(base_ctx, mode="codex_mimic")
            graph_out = synthesize_from_context(graph_ctx, mode="info_graph")

        base_q = quality_score(base_out, spec, graph)
        graph_q = quality_score(graph_out, spec, graph)

        rows.append(
            {
                "query": spec.query,
                "baseline_tokens": base_tokens,
                "graph_tokens": graph_tokens,
                "token_reduction_pct": round((base_tokens - graph_tokens) * 100 / max(1, base_tokens), 1),
                "baseline_quality": round(base_q.score, 1),
                "graph_quality": round(graph_q.score, 1),
                "quality_delta": round(graph_q.score - base_q.score, 1),
                "baseline_breakdown": {
                    "keyword_recall": round(base_q.keyword_recall, 3),
                    "path_recall": round(base_q.path_recall, 3),
                    "actionability": round(base_q.actionability, 3),
                    "hallucination_penalty": round(base_q.hallucination_penalty, 3),
                    "noise_penalty": round(base_q.noise_penalty, 3),
                },
                "graph_breakdown": {
                    "keyword_recall": round(graph_q.keyword_recall, 3),
                    "path_recall": round(graph_q.path_recall, 3),
                    "actionability": round(graph_q.actionability, 3),
                    "hallucination_penalty": round(graph_q.hallucination_penalty, 3),
                    "noise_penalty": round(graph_q.noise_penalty, 3),
                },
                "baseline_output": base_out,
                "graph_output": graph_out,
            }
        )

    summary = {
        "token_provider": args.token_provider,
        "real_output": args.real_output,
        "model": args.model,
        "queries": rows,
        "avg_baseline_tokens": round(mean(r["baseline_tokens"] for r in rows), 1),
        "avg_graph_tokens": round(mean(r["graph_tokens"] for r in rows), 1),
        "avg_token_reduction_pct": round(mean(r["token_reduction_pct"] for r in rows), 1),
        "avg_baseline_quality": round(mean(r["baseline_quality"] for r in rows), 1),
        "avg_graph_quality": round(mean(r["graph_quality"] for r in rows), 1),
        "avg_quality_delta": round(mean(r["quality_delta"] for r in rows), 1),
        "warnings": warnings,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    out_md = Path(args.out_md)
    build_markdown_report(summary, out_md)

    print("Quality Benchmark (10 queries)")
    print(f"- token_provider: {summary['token_provider']}")
    print(f"- real_output: {summary['real_output']}")
    print(f"- avg_baseline_tokens: {summary['avg_baseline_tokens']}")
    print(f"- avg_graph_tokens: {summary['avg_graph_tokens']}")
    print(f"- avg_token_reduction_pct: {summary['avg_token_reduction_pct']}%")
    print(f"- avg_baseline_quality: {summary['avg_baseline_quality']}")
    print(f"- avg_graph_quality: {summary['avg_graph_quality']}")
    print(f"- avg_quality_delta: {summary['avg_quality_delta']}")
    print(f"- report: {out}")
    print(f"- markdown_report: {out_md}")
    if warnings:
        print("- warnings:")
        for w in warnings:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
