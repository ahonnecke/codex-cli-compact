async function api(path, method = "GET", body = null) {
  const resp = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : null,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return resp.json();
}

let currentGraph = null;
let lastComparison = null;
let lastFixQuery = "";

async function countTokens(text) {
  const provider = document.getElementById("tokenizer-provider").value;
  const model = document.getElementById("tokenizer-model").value.trim() || "claude-3-5-sonnet-latest";
  const resp = await api("/api/tokenize", "POST", { text, provider, model });
  return {
    tokens: Number(resp.tokens || 0),
    mode: String(resp.mode || "heuristic"),
    error: resp.ok ? "" : String(resp.error || ""),
  };
}

function setGraph(graph) {
  currentGraph = graph;
  document.getElementById("graph-nodes").textContent = graph.node_count;
  document.getElementById("graph-edges").textContent = graph.edge_count;
  let rootText = `Root: ${graph.root}`;
  if (graph.truncated) {
    rootText += ` | showing ${graph.nodes.length}/${graph.nodes_total} nodes`;
  }
  document.getElementById("graph-root").textContent = rootText;

  const table = document.getElementById("node-table");
  table.innerHTML = "";
  graph.nodes.slice(0, 250).forEach((node) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${node.path}</td>
      <td>${node.ext}</td>
      <td>${node.size}</td>
    `;
    table.appendChild(tr);
  });
  renderGraphTree();
}

function setSummary(summary) {
  document.getElementById("events-count").textContent = summary.event_count;
  document.getElementById("total-tokens").textContent = summary.total_tokens;

  const chips = document.getElementById("mode-breakdown");
  chips.innerHTML = "";
  Object.entries(summary.by_mode || {}).forEach(([mode, total]) => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = `${mode}: ${total}`;
    chips.appendChild(span);
  });

  const table = document.getElementById("events-table");
  table.innerHTML = "";
  (summary.recent || []).slice().reverse().forEach((ev) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${ev.timestamp || ""}</td>
      <td>${ev.mode || ""}</td>
      <td>${ev.prompt_tokens || 0}</td>
      <td>${ev.completion_tokens || 0}</td>
      <td>${ev.total_tokens || 0}</td>
      <td>${ev.notes || ""}</td>
    `;
    table.appendChild(tr);
  });

  drawChart(summary.recent || []);
}

function drawChart(events) {
  const canvas = document.getElementById("usage-chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  ctx.fillStyle = "#fbfbfb";
  ctx.fillRect(0, 0, w, h);

  if (!events.length) {
    ctx.fillStyle = "#667";
    ctx.font = "14px sans-serif";
    ctx.fillText("No token events yet.", 20, 30);
    return;
  }

  const data = events.slice(-30);
  const max = Math.max(...data.map((d) => d.total_tokens || 0), 1);
  const pad = 30;
  const barWidth = (w - pad * 2) / data.length;

  ctx.strokeStyle = "#d7d7d7";
  ctx.beginPath();
  ctx.moveTo(pad, h - pad);
  ctx.lineTo(w - pad, h - pad);
  ctx.stroke();

  data.forEach((event, i) => {
    const t = event.total_tokens || 0;
    const barH = Math.round((t / max) * (h - pad * 2));
    const x = pad + i * barWidth;
    const y = h - pad - barH;
    ctx.fillStyle = event.mode === "dual_graph" ? "#0e6b56" : "#be5a28";
    ctx.fillRect(x + 1, y, Math.max(1, barWidth - 2), barH);
  });

  ctx.fillStyle = "#465";
  ctx.font = "12px sans-serif";
  ctx.fillText(`Max ${max} tokens`, pad, 16);
}

async function refreshGraph() {
  const graph = await api("/api/info-graph?full=1");
  setGraph(graph);
}

async function refreshSummary() {
  const summary = await api("/api/token-summary");
  setSummary(summary);
}

async function doScan() {
  await api("/api/scan", "POST", {});
  await refreshGraph();
}

async function resetTokenLog() {
  await api("/api/token-reset", "POST", {});
  await refreshSummary();
}

function renderBenchmark(result) {
  document.getElementById("bench-avg-base").textContent = String(result.avg_baseline_tokens ?? "-");
  document.getElementById("bench-avg-graph").textContent = String(result.avg_graph_tokens ?? "-");
  document.getElementById("bench-avg-reduction").textContent = `${result.avg_token_reduction_pct ?? "-"}%`;
  document.getElementById("bench-quality-delta").textContent = String(result.avg_quality_delta ?? "-");

  const tbody = document.getElementById("bench-table");
  tbody.innerHTML = "";
  (result.queries || []).forEach((row, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${row.query || ""}</td>
      <td>${row.baseline_tokens ?? 0}</td>
      <td>${row.graph_tokens ?? 0}</td>
      <td>${row.token_reduction_pct ?? 0}%</td>
      <td>${row.baseline_quality ?? 0}</td>
      <td>${row.graph_quality ?? 0}</td>
      <td>${row.quality_delta ?? 0}</td>
    `;
    tbody.appendChild(tr);
  });

  const out = document.getElementById("bench-outputs");
  out.innerHTML = "";
  (result.queries || []).forEach((row, idx) => {
    const wrap = document.createElement("div");
    wrap.className = "bench-pair";
    wrap.innerHTML = `
      <div class="bench-box">
        <h4>Q${idx + 1} Baseline</h4>
        <div class="muted">${row.query || ""}</div>
        <pre>${(row.baseline_output || "").replaceAll("<", "&lt;")}</pre>
      </div>
      <div class="bench-box">
        <h4>Q${idx + 1} Info Graph</h4>
        <div class="muted">${row.query || ""}</div>
        <pre>${(row.graph_output || "").replaceAll("<", "&lt;")}</pre>
      </div>
    `;
    out.appendChild(wrap);
  });
}

async function runBenchmark() {
  const btn = document.getElementById("run-bench-btn");
  const tokenProvider = document.getElementById("bench-token-provider").value;
  const model = document.getElementById("bench-model").value.trim() || "gpt-5-mini";
  const realOutput = document.getElementById("bench-real-output").value === "true";

  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "Running...";
  try {
    const result = await api("/api/benchmark", "POST", {
      token_provider: tokenProvider,
      model,
      real_output: realOutput,
    });
    if (result._meta && result._meta.ok === false) {
      throw new Error(result._meta.error || "Benchmark failed");
    }
    renderBenchmark(result);
    if (result.warnings && result.warnings.length) {
      alert(`Benchmark completed with warnings:\\n- ${result.warnings.join("\\n- ")}`);
    }
  } catch (err) {
    alert(`Benchmark failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

function appendChatMessage(role, text) {
  const log = document.getElementById("fix-chat-log");
  if (!log) return;
  const box = document.createElement("div");
  box.className = `chat-msg ${role}`;
  const when = new Date().toISOString();
  box.innerHTML = `
    <div class="chat-meta">${role.toUpperCase()} • ${when}</div>
    <div class="chat-text"></div>
  `;
  box.querySelector(".chat-text").textContent = text;
  log.appendChild(box);
  log.scrollTop = log.scrollHeight;
}

async function sendFixChat(e) {
  e.preventDefault();
  const input = document.getElementById("fix-chat-input");
  const query = (input.value || "").trim();
  if (!query) return;

  appendChatMessage("user", query);
  lastFixQuery = query;
  input.value = "";

  try {
    const res = await api("/api/chat-fix", "POST", {
      query,
      top_files: 10,
      top_edges: 24,
      max_grep_hits: 40,
    });

    const files = (res.graph_files || []).slice(0, 8).map((f) => `- ${f.id} (score: ${f._score ?? 0}, role: ${f._role || "n/a"}, intent: ${f._intent || "n/a"})`).join("\n");
    const edges = (res.graph_edges || []).slice(0, 8).map((x) => `- ${x.from} --${x.rel}--> ${x.to}`).join("\n");
    const hits = (res.grep_hits || []).slice(0, 10).map((h) => `- ${h.file}:${h.line}  ${h.text}`).join("\n");
    const cmds = (res.suggested_commands || []).map((c) => `$ ${c}`).join("\n");

    const answer =
`Summary
${res.summary || "(no summary)"}

Top Graph Files
${files || "(none)"}

Top Graph Edges
${edges || "(none)"}

Top Grep Hits
${hits || "(none)"}

Suggested Commands
${cmds || "(none)"}`;

    appendChatMessage("assistant", answer);
  } catch (err) {
    appendChatMessage("assistant", `Error: ${err.message}`);
  }
}

async function runFix(apply) {
  const query = (lastFixQuery || document.getElementById("fix-chat-input").value || "").trim();
  if (!query) {
    alert("Send a fix query first.");
    return;
  }
  if (apply) {
    const ok = confirm("This will apply file changes. Continue?");
    if (!ok) return;
  }

  const codexTokens = Number(document.getElementById("fix-codex-tokens").value || 0);
  const model = (document.getElementById("fix-model").value || "gpt-5-mini").trim();
  const validate = document.getElementById("fix-validate").value === "1";
  const checkCmd = (document.getElementById("fix-check-cmd").value || "").trim();
  const box = document.getElementById("fix-run-result");
  box.textContent = `Running ${apply ? "apply" : "dry-run"}...`;

  try {
    const res = await api("/api/fix-run", "POST", {
      query,
      codex_tokens: codexTokens,
      model,
      apply,
      validate,
      check_cmd: checkCmd,
    });
    if (res && res.ok === false) {
      const err = res.error || "fix run failed";
      const stderr = res.stderr ? `\n\nstderr:\n${res.stderr}` : "";
      const stdout = res.stdout ? `\n\nstdout:\n${res.stdout}` : "";
      throw new Error(`${err}${stderr}${stdout}`);
    }

    const edits = (res.edits || []).map((e) => `- ${e.file}: ${e.status}`).join("\n");
    const retrievalFiles = ((res.retrieval && res.retrieval.files) || []).map((f) => `- ${f}`).join("\n");
    const impactFiles = ((res.impact && res.impact.connected_files) || []).map((f) => `- ${f}`).join("\n");
    const ledger = res.token_ledger || {};
    const scope = res.scope_guard || {};
    const validation = res.validation || {};
    const validationSummary = [
      `status=${validation.status || "unknown"}`,
      validation.command ? `cmd=${validation.command}` : "",
      validation.return_code !== undefined ? `code=${validation.return_code}` : "",
    ].filter(Boolean).join(" | ");
    box.textContent =
`Mode: ${res._meta?.mode || (apply ? "apply" : "dry_run")}
Query: ${res.query || query}
Codex tokens (real): ${res.codex_tokens_real ?? codexTokens}
Tool tokens: ${res.tool_tokens?.total_tokens ?? 0}
Reduction vs Codex: ${res.reduction_pct_vs_codex ?? 0}%
Model summary: ${res.model_summary || "(none)"}
Token Ledger (start -> end):
- query_est: ${ledger.query_tokens_est ?? 0}
- retrieval_est: ${ledger.retrieval_tokens_est ?? 0}
- prompt_est: ${ledger.prompt_tokens_est ?? 0}
- model_input_real: ${ledger.model_input_tokens_real ?? 0}
- model_output_real: ${ledger.model_output_tokens_real ?? 0}
- model_total_real: ${ledger.model_total_tokens_real ?? 0}
- validation_output_est: ${ledger.validation_output_tokens_est ?? 0}
- pipeline_est: ${ledger.pipeline_tokens_est ?? 0}
Edits:
${edits || "(none)"}
Retrieved Files:
${retrievalFiles || "(none)"}
Impact (connected files):
${impactFiles || "(none)"}
Needs follow-up review: ${res.impact?.needs_followup_review ? "yes" : "no"}
Validation: ${validationSummary || "(none)"}
Validation stdout (tail):
${validation.stdout_tail || "(none)"}
Validation stderr (tail):
${validation.stderr_tail || "(none)"}
Scope Guard:
- presentation_only: ${scope.presentation_only ? "yes" : "no"}
- edited_file_count: ${scope.edited_file_count ?? 0}
- total_changed_lines_est: ${scope.total_changed_lines_est ?? 0}
- drift_detected: ${scope.drift_detected ? "yes" : "no"}
- reasons: ${(scope.reasons || []).join("; ") || "(none)"}
Report: ${res._meta?.report_path || ""}`;
  } catch (err) {
    box.textContent = `Fix run failed: ${err.message}`;
  }
}

async function submitTokenEvent(e) {
  e.preventDefault();
  const mode = document.getElementById("mode").value;
  const prompt = document.getElementById("prompt-text").value;
  const completionTokens = Number(document.getElementById("completion-tokens").value || 0);
  const notes = document.getElementById("notes").value;

  const counted = await countTokens(prompt);
  const promptTokens = counted.tokens;
  const payload = {
    mode,
    prompt_chars: prompt.length,
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    total_tokens: promptTokens + completionTokens,
    notes: counted.error ? `${notes} | tokenizer_warning=${counted.error}` : notes,
  };

  await api("/api/token-event", "POST", payload);
  e.target.reset();
  await refreshSummary();
}

function buildComparison() {
  if (!currentGraph || !Array.isArray(currentGraph.nodes) || !Array.isArray(currentGraph.edges)) {
    throw new Error("Graph data not loaded yet. Scan or refresh graph first.");
  }

  const request = document.getElementById("compare-request").value.trim();
  const chat = document.getElementById("compare-chat").value.trim();
  const keywordsRaw = document.getElementById("compare-keywords").value || "";
  const keywords = keywordsRaw
    .split(",")
    .map((k) => k.trim().toLowerCase())
    .filter(Boolean);

  const matchedNodes = currentGraph.nodes.filter((node) => {
    const blob = `${node.id} ${node.path || ""}`.toLowerCase();
    return keywords.some((k) => blob.includes(k));
  });
  const matchedSet = new Set(matchedNodes.map((n) => n.id));

  const matchedEdges = currentGraph.edges.filter((edge) => {
    const rel = String(edge.rel || "").toLowerCase();
    return matchedSet.has(edge.from) || matchedSet.has(edge.to) || keywords.some((k) => rel.includes(k));
  });

  const chatLines = chat.split("\n").filter((l) => l.trim().length > 0);
  const recentLines = chatLines.slice(-8);

  // Claude-style baseline: broad, noisy, transcript-heavy context.
  const baselineParts = [];
  baselineParts.push("System: You are an assistant editing this codebase. Preserve behavior and use all relevant prior context.");
  baselineParts.push("");
  baselineParts.push("Conversation transcript (broad):");
  baselineParts.push(chat);
  baselineParts.push("");
  baselineParts.push("Potentially relevant files (broad sweep):");
  currentGraph.nodes.slice(0, 180).forEach((n) => {
    baselineParts.push(`- ${n.id}`);
  });
  baselineParts.push("");
  baselineParts.push("Potentially relevant relations (broad sweep):");
  currentGraph.edges.slice(0, 300).forEach((e) => {
    baselineParts.push(`- ${e.from} --${e.rel}--> ${e.to}`);
  });
  baselineParts.push("");
  baselineParts.push("Current request:");
  baselineParts.push(request);
  const baselineContext = baselineParts.join("\n");

  // Info-graph context: compact, selective, edge-aware.
  const graphParts = [];
  graphParts.push("System: Use compact context. Only include graph-backed files and direct relations for this task.");
  graphParts.push("");
  graphParts.push("Current request:");
  graphParts.push(request);
  graphParts.push("");
  graphParts.push("Recent chat only:");
  recentLines.forEach((line) => graphParts.push(`- ${line}`));
  graphParts.push("");
  graphParts.push("Relevant files:");
  matchedNodes.slice(0, 25).forEach((n) => graphParts.push(`- ${n.id}`));
  graphParts.push("");
  graphParts.push("Relevant relations:");
  matchedEdges.slice(0, 40).forEach((e) => graphParts.push(`- ${e.from} --${e.rel}--> ${e.to}`));
  const graphContext = graphParts.join("\n");

  return {
    request,
    keywords,
    baselineContext,
    graphContext,
    baselineTokens: 0,
    graphTokens: 0,
    reduction: 0,
  };
}

async function runComparison(e) {
  e.preventDefault();
  try {
    const cmp = buildComparison();
    const [baselineCount, graphCount] = await Promise.all([
      countTokens(cmp.baselineContext),
      countTokens(cmp.graphContext),
    ]);
    cmp.baselineTokens = baselineCount.tokens;
    cmp.graphTokens = graphCount.tokens;
    cmp.reduction = cmp.baselineTokens > 0
      ? ((cmp.baselineTokens - cmp.graphTokens) / cmp.baselineTokens) * 100
      : 0;
    cmp.tokenMode = `${baselineCount.mode}/${graphCount.mode}`;
    cmp.tokenWarning = [baselineCount.error, graphCount.error].filter(Boolean).join(" | ");

    lastComparison = cmp;
    document.getElementById("cmp-baseline-context").value = cmp.baselineContext;
    document.getElementById("cmp-graph-context").value = cmp.graphContext;
    document.getElementById("cmp-baseline-tokens").textContent = String(cmp.baselineTokens);
    document.getElementById("cmp-graph-tokens").textContent = String(cmp.graphTokens);
    document.getElementById("cmp-reduction").textContent = `${cmp.reduction.toFixed(1)}% (${cmp.tokenMode})`;
    if (cmp.tokenWarning) {
      alert(`Tokenizer warning: ${cmp.tokenWarning}`);
    }
  } catch (err) {
    alert(`Comparison failed: ${err.message}`);
  }
}

async function logComparison() {
  try {
    if (!lastComparison) {
      lastComparison = buildComparison();
    }

    const baselineEvent = {
      mode: "baseline",
      prompt_chars: lastComparison.baselineContext.length,
      prompt_tokens: lastComparison.baselineTokens,
      completion_tokens: 0,
      total_tokens: lastComparison.baselineTokens,
      notes: `auto-compare baseline: ${lastComparison.request}${lastComparison.tokenWarning ? ` | ${lastComparison.tokenWarning}` : ""}`,
    };
    const graphEvent = {
      mode: "dual_graph",
      prompt_chars: lastComparison.graphContext.length,
      prompt_tokens: lastComparison.graphTokens,
      completion_tokens: 0,
      total_tokens: lastComparison.graphTokens,
      notes: `auto-compare dual_graph: ${lastComparison.request}${lastComparison.tokenWarning ? ` | ${lastComparison.tokenWarning}` : ""}`,
    };

    await api("/api/token-event", "POST", baselineEvent);
    await api("/api/token-event", "POST", graphEvent);
    await refreshSummary();
    alert("Logged baseline and dual_graph events.");
  } catch (err) {
    alert(`Log failed: ${err.message}`);
  }
}

function _fmtTs(ts) {
  return (ts || "").replace("T", "  ").replace("Z", "");
}
function _fmtDur(secs) {
  if (!secs) return "-";
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}
function _sanitize(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

async function refreshBenchLog() {
  try {
    const data = await api("/api/bench-log");
    const now = new Date().toLocaleTimeString();

    document.getElementById("lm-with").textContent = (data.total_with || 0).toLocaleString();
    document.getElementById("lm-without").textContent = (data.total_without || 0).toLocaleString();
    document.getElementById("lm-saved").textContent = (data.total_saved || 0).toLocaleString();
    document.getElementById("lm-pct").textContent = `${data.pct_saved ?? 0}%`;
    document.getElementById("lm-count").textContent = data.entry_count || 0;
    document.getElementById("live-ts").textContent = `updated ${now}`;

    const dot = document.getElementById("live-dot");
    dot.classList.remove("pulse");
    void dot.offsetWidth;
    dot.classList.add("pulse");

    const tbody = document.getElementById("lm-table");
    tbody.innerHTML = "";
    (data.recent || []).forEach((row) => {
      const tr = document.createElement("tr");
      const isSession = (row.mode || "").startsWith("session");

      // Mode badge
      let modeLabel = row.mode || "";
      let modeCls = "mode-badge";
      if (modeLabel === "live") modeCls += " mode-live";
      else if (modeLabel.includes("with-graph")) modeCls += " mode-with";
      else if (modeLabel.includes("without-graph")) modeCls += " mode-without";
      const modeBadge = `<span class="${modeCls}">${_sanitize(modeLabel)}</span>`;

      // Prompt cell
      const promptFull = _sanitize(row.prompt || "");
      const promptShort = _sanitize((row.prompt || "").slice(0, 72)) + ((row.prompt || "").length > 72 ? "…" : "");
      const promptCount = row.prompt_count ? ` <span class="muted">(+${row.prompt_count - 1} more)</span>` : "";
      const promptCell = `<span class="prompt-cell" title="${promptFull}">${promptShort}</span>${promptCount}`;

      // With / Without / Saved columns
      let withVal, withoutVal, savedCell;
      if (isSession) {
        withVal = row.tok_with > 0 ? row.tok_with.toLocaleString() : "-";
        withoutVal = row.tok_without > 0 ? row.tok_without.toLocaleString() : "-";
        savedCell = "-";
      } else {
        withVal = typeof row.with === "number" ? row.with.toLocaleString() : "-";
        withoutVal = typeof row.without === "number" ? row.without.toLocaleString() : "-";
        const saved = row.saved ?? null;
        if (saved !== null && saved > 0) {
          savedCell = `<span class="tok-saved">+${saved.toLocaleString()}</span>`;
        } else if (saved !== null && saved < 0) {
          savedCell = `<span class="tok-cost">${saved.toLocaleString()}</span>`;
        } else {
          savedCell = saved !== null ? saved.toLocaleString() : "-";
        }
      }

      // Duration column
      let durCell;
      if (isSession) {
        durCell = "-";
      } else {
        const dw = _fmtDur(row.dur_with);
        const dwo = _fmtDur(row.dur_without);
        durCell = `w:${dw} / wo:${dwo}`;
      }

      // inp / out column
      let inpOut;
      if (isSession && (row.inp != null || row.out != null)) {
        inpOut = `${(row.inp || 0).toLocaleString()} / ${(row.out || 0).toLocaleString()}`;
      } else {
        inpOut = "-";
      }

      tr.innerHTML = `
        <td class="ts-cell">${_sanitize(_fmtTs(row.ts))}</td>
        <td class="num-cell" title="${_sanitize(row.project || "")}">${_sanitize((row.project || "unknown").slice(-28))}</td>
        <td>${modeBadge}</td>
        <td>${promptCell}</td>
        <td class="num-cell">${withVal}</td>
        <td class="num-cell">${withoutVal}</td>
        <td class="num-cell">${savedCell}</td>
        <td class="num-cell">${durCell}</td>
        <td class="num-cell">${inpOut}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    const el = document.getElementById("live-ts");
    if (el) el.textContent = `error: ${err.message}`;
  }
}

async function init() {
  document.getElementById("scan-btn").addEventListener("click", doScan);
  document.getElementById("refresh-graph-btn").addEventListener("click", refreshGraph);
  document.getElementById("reset-token-log-btn").addEventListener("click", resetTokenLog);
  document.getElementById("token-form").addEventListener("submit", submitTokenEvent);
  document.getElementById("compare-form").addEventListener("submit", runComparison);
  document.getElementById("log-compare-btn").addEventListener("click", logComparison);
  document.getElementById("run-bench-btn").addEventListener("click", runBenchmark);
  document.getElementById("fix-chat-form").addEventListener("submit", sendFixChat);
  document.getElementById("fix-dry-run-btn").addEventListener("click", () => runFix(false));
  document.getElementById("fix-apply-btn").addEventListener("click", () => runFix(true));
  document.getElementById("bench-log-reset-btn").addEventListener("click", async () => {
    if (!confirm("Clear the entire live monitor log?")) return;
    await api("/api/bench-log-reset", "POST", {});
    await refreshBenchLog();
  });
  await refreshGraph();
  await refreshSummary();
  refreshBenchLog();
  setInterval(refreshBenchLog, 5000);
}

function renderGraphTree() {
  const out = document.getElementById("graph-tree");
  if (!out) return;
  if (!currentGraph || !Array.isArray(currentGraph.nodes) || !Array.isArray(currentGraph.edges)) {
    out.textContent = "No graph data loaded.";
    return;
  }

  const nodeIds = new Set(currentGraph.nodes.map((n) => n.id));
  const grouped = new Map();
  for (const edge of currentGraph.edges) {
    if (!grouped.has(edge.from)) {
      grouped.set(edge.from, []);
    }
    grouped.get(edge.from).push(edge);
  }

  const roots = Array.from(nodeIds).sort((a, b) => a.localeCompare(b));
  const lines = [];
  for (const root of roots) {
    lines.push(root);
    const list = grouped.get(root) || [];
    list.sort((a, b) => {
      const relCmp = (a.rel || "").localeCompare(b.rel || "");
      if (relCmp !== 0) return relCmp;
      return (a.to || "").localeCompare(b.to || "");
    });

    for (let i = 0; i < list.length; i += 1) {
      const edge = list[i];
      const isLast = i === list.length - 1;
      const branch = isLast ? "└─" : "├─";
      lines.push(`${branch} [${edge.rel}] ${edge.to}`);
    }

    if (list.length === 0) {
      lines.push("└─ (no outgoing edges)");
    }
    lines.push("");
  }

  out.textContent = lines.join("\n");
}

init().catch((err) => {
  console.error(err);
  alert(`Initialization failed: ${err.message}`);
});
