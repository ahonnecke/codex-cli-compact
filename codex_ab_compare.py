#!/usr/bin/env python3
"""Separate A/B runner: real Codex tokens (manual) vs info-graph fixer tokens."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dg import DEFAULT_ROOT, retrieve
from graph_builder import scan


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
GRAPH_JSON = DATA_DIR / "info_graph.json"
AB_DIR = DATA_DIR / "ab_runs"


def load_graph(project_root: Path) -> dict:
    if GRAPH_JSON.exists():
        return json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    g = scan(project_root)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_JSON.write_text(json.dumps(g, indent=2), encoding="utf-8")
    return g


def read_file_text(path: Path, max_chars: int = 6_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n/* truncated */\n"
    return text


def est_tokens(text: str) -> int:
    # Fast, model-agnostic approximation for non-API pipeline steps.
    return max(1, len(text) // 4) if text else 0


def is_presentation_only_query(query: str) -> bool:
    q = query.lower()
    present = any(k in q for k in ("show", "display", "label", "text", "style", "color", "button", "badge", "status"))
    structural = any(k in q for k in ("refactor", "migrate", "schema", "api", "backend", "database", "flow", "logic", "state"))
    return present and not structural


def scope_hints_for_query(query: str) -> list[str]:
    hints = []
    if is_presentation_only_query(query):
        hints.append("- Treat this as PRESENTATION-ONLY unless explicitly asked otherwise.")
        hints.append("- Do not change data models/types/api/store/backend contracts.")
        hints.append("- Do not rename fields or props unless required to compile.")
        hints.append("- Keep existing action flow and handlers; only adjust UI text/style/disabled state.")
    else:
        hints.append("- Keep changes minimal and scoped to request intent.")
    return hints


def query_terms(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+", query.lower())
    stop = {
        "a", "an", "the", "and", "or", "to", "for", "with", "in", "on", "by", "of",
        "please", "can", "could", "would", "should", "will", "use", "update", "fix",
        "make", "show", "this", "that", "it",
    }
    out: list[str] = []
    seen = set()
    for w in words:
        if len(w) < 3 or w in stop or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:8]


def excerpt_for_query(text: str, terms: list[str], max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    if not terms:
        return text[:max_chars] + "\n/* truncated */\n"
    lines = text.splitlines()
    if not lines:
        return text[:max_chars] + "\n/* truncated */\n"
    blocks: list[str] = []
    seen_starts: set[int] = set()
    for i, line in enumerate(lines):
        blob = line.lower()
        if not any(t in blob for t in terms):
            continue
        s = max(0, i - 14)
        e = min(len(lines), i + 15)
        if s in seen_starts:
            continue
        seen_starts.add(s)
        blocks.append("\n".join(lines[s:e]))
        if sum(len(b) for b in blocks) >= max_chars:
            break
    if not blocks:
        return text[:max_chars] + "\n/* truncated */\n"
    out = "\n\n/* --- excerpt --- */\n\n".join(blocks)
    if len(out) > max_chars:
        out = out[:max_chars]
    return out


def call_openai_fix(model: str, prompt: str) -> tuple[dict, dict]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    def request_once(user_prompt: str, max_completion_tokens: int) -> dict:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return valid JSON only. No markdown fences. No commentary.",
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": max_completion_tokens,
        }
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="https://api.openai.com/v1/chat/completions",
            data=raw,
            method="POST",
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            details = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI HTTP {e.code}: {details}") from e
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"OpenAI request failed: {e}") from e

    # First attempt: moderate budget.
    data = request_once(prompt, 3500)

    usage = data.get("usage", {})
    usage_norm = {
        "input_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        "output_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }
    text = ""
    choices = data.get("choices", [])
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        text = msg.get("content", "") if isinstance(msg, dict) else ""
    if not text:
        text = extract_response_text(data)

    # Retry with larger budgets if model used budget without visible output.
    if not text:
        finish_reason = ""
        choices = data.get("choices", [])
        if isinstance(choices, list) and choices:
            finish_reason = str(choices[0].get("finish_reason", ""))
        if finish_reason == "length":
            retry_prompt = (
                prompt
                + "\n\nIMPORTANT:\n"
                + "- Return compact JSON only with keys: summary, edits.\n"
                + "- Edit at most 1 file.\n"
                + "- If uncertain, return empty edits.\n"
            )
            for budget in (7000, 12000):
                data = request_once(retry_prompt, budget)
                usage2 = data.get("usage", {})
                usage_norm = {
                    "input_tokens": int(usage2.get("prompt_tokens", usage2.get("input_tokens", 0)) or 0),
                    "output_tokens": int(usage2.get("completion_tokens", usage2.get("output_tokens", 0)) or 0),
                    "total_tokens": int(usage2.get("total_tokens", 0) or 0),
                }
                text = ""
                choices = data.get("choices", [])
                if isinstance(choices, list) and choices:
                    msg = choices[0].get("message", {})
                    text = msg.get("content", "") if isinstance(msg, dict) else ""
                if not text:
                    text = extract_response_text(data)
                if text:
                    break

    if not text:
        # Keep run alive: return explicit no-op edits payload.
        text = json.dumps(
            {
                "summary": "Model returned empty content; no edits generated.",
                "edits": [],
            }
        )

    return {"output_text": text, "raw": data}, usage_norm


def extract_response_text(data: dict) -> str:
    out = data.get("output", [])
    if not isinstance(out, list):
        return ""
    chunks: list[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict):
                    t = c.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
        t2 = item.get("text")
        if isinstance(t2, str):
            chunks.append(t2)
    return "\n".join(chunks).strip()


def parse_output_payload(text: str) -> dict:
    """Parse JSON block from model output.

    Expected shape:
    {
      "summary": "...",
      "edits": [{"file":"...", "new_content":"..."}]
    }
    """
    # Try fenced JSON first.
    fence = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidate = fence.group(1) if fence else text.strip()

    # Find first JSON object if text has extra prose.
    if not candidate.startswith("{"):
        obj = re.search(r"(\{.*\})", candidate, flags=re.DOTALL)
        if obj:
            candidate = obj.group(1)

    try:
        data = json.loads(candidate)
    except Exception as e:  # noqa: BLE001
        snippet = candidate[:800]
        raise RuntimeError(f"Could not parse JSON edits from model output: {e}. Snippet: {snippet}") from e

    if not isinstance(data, dict):
        raise RuntimeError("Invalid model payload: expected JSON object")
    return data


def parse_edits_from_payload(data: dict) -> list[dict]:
    edits = data.get("edits", [])
    if not isinstance(edits, list):
        raise RuntimeError("Invalid edits payload: 'edits' must be a list")

    normalized: list[dict] = []
    for e in edits:
        if not isinstance(e, dict):
            continue
        file = str(e.get("file", "")).strip()
        old_snippet = str(e.get("old_snippet", ""))
        new_snippet = str(e.get("new_snippet", ""))
        new_content = str(e.get("new_content", ""))
        if file and old_snippet and new_snippet:
            normalized.append(
                {
                    "file": file,
                    "mode": "snippet",
                    "old_snippet": old_snippet,
                    "new_snippet": new_snippet,
                    "reason": str(e.get("reason", "")),
                }
            )
            continue
        if file and new_content:
            normalized.append({"file": file, "mode": "fullfile", "new_content": new_content})
    return normalized


def apply_edits(project_root: Path, edits: list[dict], dry_run: bool, allow_fullfile: bool = False) -> list[dict]:
    applied: list[dict] = []
    for edit in edits:
        rel = edit["file"]
        tgt = (project_root / rel).resolve()
        if project_root.resolve() not in tgt.parents and tgt != project_root.resolve():
            applied.append({"file": rel, "status": "skipped_outside_root"})
            continue
        if not tgt.exists():
            applied.append({"file": rel, "status": "skipped_missing_file"})
            continue
        old = read_file_text(tgt, max_chars=2_000_000)
        mode = str(edit.get("mode", "fullfile"))
        if mode == "snippet":
            old_snippet = str(edit.get("old_snippet", ""))
            new_snippet = str(edit.get("new_snippet", ""))
            hits = old.count(old_snippet)
            if hits == 0:
                applied.append({"file": rel, "status": "skipped_anchor_not_found", "mode": "snippet"})
                continue
            if hits > 1:
                applied.append({"file": rel, "status": "skipped_anchor_ambiguous", "mode": "snippet"})
                continue
            new = old.replace(old_snippet, new_snippet, 1)
        else:
            if not allow_fullfile:
                applied.append({"file": rel, "status": "skipped_fullfile_disallowed", "mode": "fullfile"})
                continue
            new = str(edit.get("new_content", ""))
        if old == new:
            applied.append({"file": rel, "status": "no_change"})
            continue
        changed_lines_est = abs(new.count("\n") - old.count("\n"))
        if dry_run:
            applied.append(
                {
                    "file": rel,
                    "status": "planned_change",
                    "old_chars": len(old),
                    "new_chars": len(new),
                    "mode": mode,
                    "changed_lines_est": changed_lines_est,
                }
            )
            continue
        tgt.write_text(new, encoding="utf-8")
        applied.append(
            {
                "file": rel,
                "status": "applied",
                "old_chars": len(old),
                "new_chars": len(new),
                "mode": mode,
                "changed_lines_est": changed_lines_est,
            }
        )
    return applied


def evaluate_scope_guard(query: str, applied: list[dict]) -> dict:
    presentation = is_presentation_only_query(query)
    edited_files = [e.get("file", "") for e in applied if e.get("status") in {"applied", "planned_change"}]
    total_changed_lines = sum(int(e.get("changed_lines_est", 0) or 0) for e in applied)
    risky_paths = []
    for f in edited_files:
        fl = f.lower()
        if any(k in fl for k in ("/types", "/store/", "/api/", "/models/", "/backend/")):
            risky_paths.append(f)
    drift = False
    reasons: list[str] = []
    if presentation and len(edited_files) > 3:
        drift = True
        reasons.append("presentation-only query changed too many files")
    if presentation and total_changed_lines > 80:
        drift = True
        reasons.append("presentation-only query changed too many lines")
    if presentation and risky_paths:
        drift = True
        reasons.append("presentation-only query edited data/logic contract files")
    return {
        "presentation_only": presentation,
        "edited_file_count": len(edited_files),
        "total_changed_lines_est": total_changed_lines,
        "risky_paths": risky_paths,
        "drift_detected": drift,
        "reasons": reasons,
    }


def is_local_file_ref(value: str) -> bool:
    # Keep only repo-like file refs (not package imports like react or @/foo alias).
    if not value:
        return False
    if value.startswith("@") or ":" in value:
        return False
    if "/" not in value:
        return False
    return "." in value.split("/")[-1]


def collect_impact(graph: dict, applied: list[dict]) -> dict:
    edited = {
        e.get("file", "")
        for e in applied
        if e.get("status") in {"applied", "planned_change", "no_change"}
    }
    edited = {e for e in edited if e}
    connected: set[str] = set()
    for edge in graph.get("edges", []):
        frm = str(edge.get("from", ""))
        to = str(edge.get("to", ""))
        if frm in edited and is_local_file_ref(to):
            connected.add(to)
        if to in edited and is_local_file_ref(frm):
            connected.add(frm)
    untouched = sorted(x for x in connected if x not in edited)
    return {
        "edited_files": sorted(edited),
        "connected_files": sorted(connected),
        "untouched_connected_files": untouched,
        "needs_followup_review": len(untouched) > 0,
    }


def detect_default_check(project_root: Path) -> tuple[str | None, Path | None]:
    rp = project_root / "restaurant-portal"
    if (rp / "package.json").exists():
        return "npm run build", rp
    if (project_root / "package.json").exists():
        return "npm run build", project_root
    return None, None


def run_validation(project_root: Path, check_cmd: str | None) -> dict:
    cmd = check_cmd
    cwd: Path | None = project_root
    if not cmd:
        cmd, cwd = detect_default_check(project_root)
    if not cmd or cwd is None:
        return {"status": "skipped", "reason": "no check command detected"}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e), "cmd": cmd, "cwd": str(cwd)}
    return {
        "status": "pass" if proc.returncode == 0 else "fail",
        "returncode": proc.returncode,
        "cmd": cmd,
        "cwd": str(cwd),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def build_fix_prompt(query: str, project_root: Path, relevant_files: list[dict], max_file_chars: int) -> str:
    sections = []
    sections.append(
        "You are a code editing tool. Return ONLY JSON with shape: "
        '{"summary":"...", "edits":[{"file":"relative/path","old_snippet":"exact existing text","new_snippet":"replacement text","reason":"why"}]}.'
    )
    sections.append("Constraints:")
    sections.append("- Edit only files from provided file list.")
    sections.append("- Prefer feature-level files first (pages/features/api) before shared UI primitives.")
    sections.append("- Avoid editing shared primitives unless query explicitly asks for global/shared behavior.")
    sections.append("- Preserve existing behavior except what is needed for the request.")
    sections.append("- Prefer SNIPPET edits; avoid rewriting full files.")
    sections.append("- Snippets must be exact matches from provided content.")
    sections.extend(scope_hints_for_query(query))
    sections.append("- If no safe change, return empty edits list.")
    sections.append(f"Request: {query}")
    sections.append("")
    sections.append("Allowed files:")
    for f in relevant_files:
        sections.append(f"- {f.get('id')}")
    sections.append("")
    sections.append("File contents:")
    terms = query_terms(query)
    for f in relevant_files:
        rel = str(f.get("id", ""))
        path = (project_root / rel).resolve()
        full = read_file_text(path, max_chars=200_000)
        content = excerpt_for_query(full, terms, max_file_chars)
        if not content:
            continue
        sections.append(f"\n### FILE: {rel}\n{content}")
    return "\n".join(sections)


def pick_fix_files(files: list[dict], limit: int) -> list[dict]:
    # Prefer source code files over docs/config for real edits.
    code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go"}
    primary = []
    secondary = []
    for f in files:
        ext = str(f.get("ext", "")).lower()
        path = str(f.get("id", "")).lower()
        if "/venv/" in path or "/.venv/" in path:
            continue
        if ext in code_exts:
            primary.append(f)
        else:
            secondary.append(f)
    merged = primary + secondary
    return merged[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare real Codex token usage vs info-graph fixer tokens.")
    parser.add_argument("--query", required=True, help="Same query used in Codex.")
    parser.add_argument("--codex-tokens", type=int, required=True, help="Real token usage observed in Codex for this query.")
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model used for info-graph fixer run.")
    parser.add_argument("--project-root", default=str(DEFAULT_ROOT), help="Target project root.")
    parser.add_argument("--top-files", type=int, default=3, help="How many retrieved files to send to fixer.")
    parser.add_argument("--top-edges", type=int, default=24, help="How many edges to retrieve (for trace only).")
    parser.add_argument("--apply", action="store_true", help="Apply changes to files. Default is dry-run.")
    parser.add_argument("--allow-fullfile", action="store_true", help="Allow full-file rewrites (off by default).")
    parser.add_argument("--validate", action="store_true", help="Run validation command after edits (auto-on when --apply).")
    parser.add_argument("--check-cmd", default="", help="Validation command override (e.g. 'npm run build').")
    parser.add_argument("--out", default="", help="Optional explicit output report path.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    graph = load_graph(project_root)
    retrieved = retrieve(graph, args.query, args.top_files, args.top_edges)
    files = pick_fix_files(retrieved.files, args.top_files)

    prompt = build_fix_prompt(args.query, project_root, files, max_file_chars=3000)
    retrieval_snapshot = {
        "files": [f.get("id") for f in files],
        "edges": retrieved.edges,
    }
    model_out, usage = call_openai_fix(args.model, prompt)
    parsed = parse_output_payload(model_out["output_text"])
    model_summary = str(parsed.get("summary", "")).strip()
    edits = parse_edits_from_payload(parsed)

    # Apply mode should not silently no-op; retry once with broader file context.
    if args.apply and not edits:
        expanded_retrieved = retrieve(graph, args.query, args.top_files + 3, args.top_edges)
        expanded_files = pick_fix_files(expanded_retrieved.files, args.top_files + 3)
        retry_prompt = (
            build_fix_prompt(args.query, project_root, expanded_files, max_file_chars=6500)
            + "\n\nIMPORTANT:\n"
            + "- You MUST return at least one safe, minimal edit for this request.\n"
            + "- Prefer action/behavior surface files over shared primitives for scoped requests.\n"
            + "- If still impossible, include reason in summary and return empty edits.\n"
        )
        retry_out, retry_usage = call_openai_fix(args.model, retry_prompt)
        usage = {
            "input_tokens": usage["input_tokens"] + retry_usage["input_tokens"],
            "output_tokens": usage["output_tokens"] + retry_usage["output_tokens"],
            "total_tokens": usage["total_tokens"] + retry_usage["total_tokens"],
        }
        parsed = parse_output_payload(retry_out["output_text"])
        model_summary = str(parsed.get("summary", "")).strip()
        edits = parse_edits_from_payload(parsed)
        if edits:
            files = expanded_files
            retrieved = expanded_retrieved
            prompt = retry_prompt
            retrieval_snapshot = {
                "files": [f.get("id") for f in files],
                "edges": retrieved.edges,
            }

    applied = apply_edits(project_root, edits, dry_run=not args.apply, allow_fullfile=bool(args.allow_fullfile))
    scope_guard = evaluate_scope_guard(args.query, applied)
    impact = collect_impact(graph, applied)
    should_validate = bool(args.validate or args.apply)
    validation = run_validation(project_root, args.check_cmd.strip() or None) if should_validate else {
        "status": "skipped",
        "reason": "validation disabled",
    }

    tool_tokens = usage["input_tokens"] + usage["output_tokens"]
    validation_text = f"{validation.get('stdout_tail', '')}\n{validation.get('stderr_tail', '')}"
    token_ledger = {
        "query_tokens_est": est_tokens(args.query),
        "retrieval_tokens_est": est_tokens(json.dumps(retrieval_snapshot, ensure_ascii=False)),
        "prompt_tokens_est": est_tokens(prompt),
        "model_input_tokens_real": usage["input_tokens"],
        "model_output_tokens_real": usage["output_tokens"],
        "model_total_tokens_real": tool_tokens,
        "validation_output_tokens_est": est_tokens(validation_text),
        "pipeline_tokens_est": (
            est_tokens(args.query)
            + est_tokens(json.dumps(retrieval_snapshot, ensure_ascii=False))
            + est_tokens(prompt)
            + est_tokens(validation_text)
        ),
    }
    reduction_pct = ((args.codex_tokens - tool_tokens) * 100 / max(1, args.codex_tokens))

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": args.query,
        "project_root": str(project_root),
        "codex_tokens_real": int(args.codex_tokens),
        "tool_mode": "info_graph_fixer",
        "tool_model": args.model,
        "tool_tokens": {
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "total_tokens": tool_tokens,
        },
        "token_ledger": token_ledger,
        "reduction_pct_vs_codex": round(reduction_pct, 1),
        "retrieval": {
            "files": [f.get("id") for f in files],
            "edge_count": len(retrieved.edges),
        },
        "model_summary": model_summary,
        "edits": applied,
        "scope_guard": scope_guard,
        "impact": impact,
        "validation": validation,
        "dry_run": not args.apply,
    }

    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        AB_DIR.mkdir(parents=True, exist_ok=True)
        out = AB_DIR / f"ab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.apply and len(applied) == 0:
        raise RuntimeError(
            f"Apply produced no edits. Model summary: {model_summary or 'No summary provided'}"
        )
    if args.apply and scope_guard.get("drift_detected"):
        raise RuntimeError(
            f"Scope drift detected: {', '.join(scope_guard.get('reasons', []))}"
        )

    print("A/B compare completed")
    print(f"- query: {args.query}")
    print(f"- codex_tokens_real: {args.codex_tokens}")
    print(f"- tool_tokens_total: {tool_tokens}")
    print(f"- pipeline_tokens_est: {token_ledger['pipeline_tokens_est']}")
    print(f"- reduction_pct_vs_codex: {round(reduction_pct, 1)}%")
    print(f"- edits_count: {len(applied)} (dry_run={not args.apply})")
    print(f"- scope_drift: {scope_guard.get('drift_detected')}")
    print(f"- validation: {validation.get('status')}")
    print(f"- impact_followup: {impact.get('needs_followup_review')}")
    print(f"- report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
