const $ = (id) => document.getElementById(id);
const state = { samples: [], sources: [], active: 0, sampleId: null, lines: {}, sourceNames: {}, analysis: null, markdown: "", verdicts: {}, counts: null, running: false, timer: null, started: 0 };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const shortModel = (m) => (m || "").replace(/^nvidia\//, "");
const fmt = (n) => Number(n || 0).toLocaleString("en-US");

async function init() {
  const health = await fetch("/api/health").then((r) => r.json());
  state.live = health.live;
  const labels = { extract: "Extract", reason: "Reason", verify: "Verify" };
  $("models").innerHTML = Object.entries(health.models).map(([k, m]) => `<span class="chip">${labels[k]} <b>${esc(shortModel(m))}</b></span>`).join("");
  document.querySelectorAll("[data-model]").forEach((el) => (el.textContent = health.models[el.dataset.model]));
  $("liveBadge").textContent = health.live ? "Token Factory connected" : "Replay-only mode (no API key on this server)";
  $("runLive").disabled = !health.live;
  state.samples = await fetch("/api/samples").then((r) => r.json());
  $("samples").innerHTML = state.samples.map((s) => `<button class="sample" data-id="${esc(s.id)}"><b>${esc(s.title)}</b><span>${esc(s.description)}</span></button>`).join("");
  document.querySelectorAll(".sample").forEach((b) => b.addEventListener("click", () => loadSample(b.dataset.id)));
  if (state.samples.length) loadSample(state.samples[0].id);
  else renderTabs();
}

function loadSample(id) {
  const sample = state.samples.find((s) => s.id === id);
  state.sampleId = id;
  state.sources = sample.sources.map((s) => ({ ...s }));
  state.active = 0;
  document.querySelectorAll(".sample").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  renderTabs();
}

function saveEditor() {
  if (!state.sources[state.active]) return;
  state.sources[state.active].text = $("editor").value;
  state.sources[state.active].name = $("sourceName").value || state.sources[state.active].name;
}

function renderTabs() {
  if (!state.sources.length) state.sources = [{ name: "incident.log", text: "" }];
  $("tabs").innerHTML = state.sources.map((s, i) => `<button class="tab ${i === state.active ? "active" : ""}" data-i="${i}">${esc(s.name)}</button>`).join("");
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => { saveEditor(); state.active = +t.dataset.i; renderTabs(); }));
  $("editor").value = state.sources[state.active].text;
  $("sourceName").value = state.sources[state.active].name;
  const sample = state.samples.find((s) => s.id === state.sampleId);
  $("runReplay").disabled = !(sample && sample.has_recording);
}

$("editor").addEventListener("input", () => { state.sampleId = state.sampleId && null; document.querySelectorAll(".sample").forEach((b) => b.classList.remove("active")); saveEditor(); $("runReplay").disabled = true; });
$("sourceName").addEventListener("change", () => { saveEditor(); renderTabs(); });
$("addSource").addEventListener("click", () => { saveEditor(); state.sources.push({ name: `source-${state.sources.length + 1}.log`, text: "" }); state.active = state.sources.length - 1; renderTabs(); $("editor").focus(); });
$("removeSource").addEventListener("click", () => { if (state.sources.length <= 1) return; state.sources.splice(state.active, 1); state.active = Math.max(0, state.active - 1); renderTabs(); });

function setStage(name, status, body) {
  const el = $(`st-${name}`);
  el.classList.remove("running", "done", "failed");
  if (status) el.classList.add(status);
  if (body !== undefined) el.querySelector(".st-body").innerHTML = body;
}

function reset() {
  ["redact", "extract", "reason", "verify"].forEach((s) => setStage(s, null, "waiting"));
  $("chunkBars").innerHTML = ""; $("verifyBars").innerHTML = ""; $("warnings").innerHTML = "";
  $("results").hidden = true;
  Object.assign(state, { lines: {}, sourceNames: {}, analysis: null, markdown: "", verdicts: {}, counts: null, chunks: 0, chunksDone: 0, events: 0, verifyTotal: 0, verifyDone: 0 });
}

function tick() { $("clock").textContent = `${((performance.now() - state.started) / 1000).toFixed(1)} s`; }

async function run(mode) {
  if (state.running) return;
  saveEditor();
  reset();
  state.running = true;
  $("runLive").disabled = true; $("runReplay").disabled = true;
  state.started = performance.now();
  state.timer = setInterval(tick, 100);
  setStage("redact", "running", "scrubbing secrets...");
  try {
    const response = mode === "replay"
      ? await fetch(`/api/replay/${encodeURIComponent(state.sampleId)}`)
      : await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sources: state.sources.filter((s) => s.text.trim()) }) });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) handle(JSON.parse(line));
      }
    }
  } catch (err) {
    $("warnings").insertAdjacentHTML("beforeend", `<div class="err">${esc(err.message)}</div>`);
    document.querySelectorAll(".stage.running").forEach((el) => el.classList.replace("running", "failed"));
  } finally {
    clearInterval(state.timer); tick();
    state.running = false;
    $("runLive").disabled = !state.live;
    const sample = state.samples.find((s) => s.id === state.sampleId);
    $("runReplay").disabled = !(sample && sample.has_recording);
  }
}

function handle(e) {
  switch (e.type) {
    case "corpus": {
      state.lines = e.lines;
      e.sources.forEach((s) => (state.sourceNames[s.id] = s.name));
      const total = Object.values(e.redactions || {}).reduce((a, b) => a + b, 0);
      const kinds = Object.entries(e.redactions || {}).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(", ");
      setStage("redact", "done", `${fmt(Object.keys(e.lines).length)} lines from ${e.sources.length} sources &middot; <b>${total} secrets redacted</b>${kinds ? ` (${esc(kinds)})` : ""}${e.truncated ? ` &middot; ${e.truncated} lines over limit skipped` : ""}`);
      break;
    }
    case "stage": return stage(e);
    case "extract_chunk": {
      state.chunksDone++; state.events += e.events;
      const bar = $("chunkBars").children[e.index]; if (bar) bar.className = "bar ok";
      setStage("extract", "running", `${state.chunksDone}/${state.chunks} chunks &middot; ${state.events} events &middot; last: ${esc(e.source)} in ${e.seconds}s`);
      break;
    }
    case "timeline": state.timeline = e.events; break;
    case "analysis": renderAnalysis(e); break;
    case "verdict": {
      state.verifyDone++;
      state.verdicts[e.claim_id] = e;
      const bar = $("verifyBars").children[state.verifyDone - 1]; if (bar) bar.className = `bar ${e.verdict === "supported" ? "ok" : e.verdict === "partial" ? "partial" : "bad"}`;
      document.querySelectorAll(`[data-claim="${CSS.escape(e.claim_id)}"]`).forEach((el) => {
        const badge = el.querySelector(".verdict");
        badge.className = `verdict ${e.verdict}`; badge.textContent = e.verdict;
        el.querySelector(".why").textContent = e.reason || "";
      });
      setStage("verify", "running", `${state.verifyDone}/${state.verifyTotal} claims checked`);
      break;
    }
    case "report": state.markdown = e.markdown; state.counts = e.counts; renderScore(); break;
    case "usage": renderUsage(e.ledger); break;
    case "warning": $("warnings").insertAdjacentHTML("beforeend", `<div class="warn">${esc(e.stage)}: ${esc(e.message)}</div>`); break;
    case "error": $("warnings").insertAdjacentHTML("beforeend", `<div class="err">${esc(e.message)}</div>`); document.querySelectorAll(".stage.running").forEach((el) => el.classList.replace("running", "failed")); break;
  }
}

function stage(e) {
  if (e.stage === "extract" && e.status === "start") {
    state.chunks = e.calls;
    $("chunkBars").innerHTML = Array.from({ length: e.calls }, () => `<span class="bar run"></span>`).join("");
    setStage("extract", "running", `${e.calls} parallel calls to Nano...`);
  } else if (e.stage === "extract" && e.status === "done") {
    setStage("extract", "done", `${state.chunks} chunks in parallel &rarr; <b>${state.timeline.length} events</b> on one timeline`);
  } else if (e.stage === "reason" && e.status === "start") {
    const saved = e.raw_tokens_estimate ? Math.max(0, Math.round(100 - (100 * e.context_tokens_estimate) / e.raw_tokens_estimate)) : 0;
    state.reasonStart = e;
    setStage("reason", "running", saved > 0 ? `Ultra is reasoning over ~${fmt(e.context_tokens_estimate)} tokens of distilled evidence instead of ~${fmt(e.raw_tokens_estimate)} tokens of raw logs (${saved}% smaller)...` : `Ultra is reasoning over the merged timeline and cited lines (~${fmt(e.context_tokens_estimate)} tokens)...`);
  } else if (e.stage === "reason" && e.status === "done") {
    const a = state.analysisMeta || {};
    setStage("reason", "done", `causal analysis in ${a.seconds}s &middot; ${fmt(a.reasoning_tokens)} reasoning tokens &middot; ${state.claimCount} claims with citations`);
  } else if (e.stage === "verify" && e.status === "start") {
    state.verifyTotal = state.claimCount;
    $("verifyBars").innerHTML = Array.from({ length: state.claimCount }, () => `<span class="bar run"></span>`).join("");
    setStage("verify", "running", `${e.calls} parallel fact-checks with Lightning...`);
  } else if (e.stage === "verify" && e.status === "done") {
    const c = e.counts;
    setStage("verify", "done", `<b>${c.supported}</b> supported &middot; <b>${c.partial}</b> partial &middot; <b>${c.unsupported}</b> unsupported`);
  }
}

function refs(list) { return (list || []).map((r) => `<span class="ref" data-ref="${esc(r)}">${esc(r)}</span>`).join(""); }

function claimHTML(item, label) {
  if (!item || !item.statement) return "";
  return `<div class="claim" data-claim="${esc(item.id)}">${label ? `<div class="label">${esc(label)}</div>` : ""}${esc(item.statement)}<span class="verdict pending">checking</span><div>${refs(item.refs)}</div><div class="why"></div></div>`;
}

function renderAnalysis(e) {
  const a = e.data;
  state.analysis = a;
  state.analysisMeta = e;
  const ids = [];
  const collect = (x) => { if (x && x.id) ids.push(x.id); };
  ["impact", "trigger", "root_cause", "detection", "resolution"].forEach((k) => collect(a[k]));
  ["causal_chain", "contributing_factors", "red_herrings"].forEach((k) => (a[k] || []).forEach(collect));
  state.claimCount = ids.length;
  $("results").hidden = false;
  $("sev").textContent = a.severity || "SEV?";
  $("title").textContent = a.title || "Incident";
  $("summary").textContent = a.summary || "";
  $("window").textContent = a.window ? `${a.window.start || "?"}  →  ${a.window.end || "?"}` : "";
  $("chain").innerHTML = (a.causal_chain || []).map((c) => `<li>${claimHTML(c).replace('class="claim"', 'class="claim flat"')}</li>`).join("");
  $("herrings").innerHTML = (a.red_herrings || []).map((c) => `<li>${claimHTML(c)}</li>`).join("") || `<li class="hint">none identified</li>`;
  $("keyclaims").innerHTML = [["root_cause", "Root cause"], ["trigger", "Trigger"], ["impact", "Impact"], ["detection", "Detection"], ["resolution", "Resolution"]].map(([k, l]) => claimHTML(a[k], l)).join("");
  $("factors").innerHTML = (a.contributing_factors || []).map((c) => `<li>${claimHTML(c)}</li>`).join("");
  $("actionsBody").innerHTML = (a.action_items || []).map((x) => `<tr><td class="pri ${esc(x.priority)}">${esc(x.priority)}</td><td>${esc(x.type)}</td><td>${esc(x.action)}</td></tr>`).join("");
  $("questions").innerHTML = (a.open_questions || []).map((q) => `<li>${esc(q)}</li>`).join("");
  $("questionsWrap").hidden = !(a.open_questions || []).length;
  const tl = state.timeline || [];
  $("timelineHint").textContent = `${tl.length} events extracted by Nano`;
  $("timeline").innerHTML = tl.map((ev) => `<li><span class="t">${esc(ev.time || "")}</span><span class="kind ${esc(ev.kind)}">${esc(ev.kind)}</span><span>${esc(ev.summary)}<span class="evwrap"></span></span><span>${refs([ev.ref])}</span></li>`).join("");
  $("score").innerHTML = `<div class="hint">Evidence check</div><div class="big">…</div><div class="legend">verifying ${ids.length} claims</div>`;
}

function renderScore() {
  const c = state.counts;
  const total = c.supported + c.partial + c.unsupported;
  const pct = total ? Math.round((100 * (c.supported + 0.5 * c.partial)) / total) : 0;
  $("score").innerHTML = `<div class="hint">Evidence score</div><div class="big">${pct}%</div><div class="legend"><span style="color:var(--ok)">${c.supported} supported</span><span style="color:var(--warn)">${c.partial} partial</span><span style="color:var(--bad)">${c.unsupported} unsupported</span></div>`;
}

function renderUsage(ledger) {
  const roles = { extract: "Extract (map)", reason: "Reason", verify: "Verify" };
  const cards = Object.entries(ledger.by_stage).map(([stage, u]) => {
    const model = stage === "extract" ? $("st-extract") : stage === "reason" ? $("st-reason") : $("st-verify");
    return `<div class="ucard"><div class="hint">${esc(roles[stage] || stage)} &middot; ${u.calls} call${u.calls === 1 ? "" : "s"}</div><div class="n">${fmt(u.prompt_tokens + u.completion_tokens)} tok</div><div class="m">${esc(model.querySelector(".st-model").textContent)}</div><div class="hint">${fmt(u.prompt_tokens)} in / ${fmt(u.completion_tokens)} out (${fmt(u.reasoning_tokens)} reasoning) &middot; ${u.seconds}s model time</div></div>`;
  });
  cards.push(`<div class="ucard"><div class="hint">Whole run</div><div class="n">${fmt(ledger.total_tokens)} tok</div><div class="hint">wall clock ${((performance.now() - state.started) / 1000).toFixed(1)}s</div></div>`);
  $("usage").innerHTML = cards.join("");
}

document.addEventListener("click", (ev) => {
  const chip = ev.target.closest(".ref");
  if (!chip) return;
  const host = chip.closest(".claim") || chip.closest("li");
  const existing = host.querySelector(`.evidence[data-for="${CSS.escape(chip.dataset.ref)}"]`);
  if (existing) return existing.remove();
  const [sid] = chip.dataset.ref.split(":");
  host.insertAdjacentHTML("beforeend", `<div class="evidence" data-for="${esc(chip.dataset.ref)}"><span class="src">${esc(state.sourceNames[sid] || sid)} · ${esc(chip.dataset.ref)}</span>\n${esc(state.lines[chip.dataset.ref] || "(line not found)")}</div>`);
});

$("runLive").addEventListener("click", () => run("live"));
$("runReplay").addEventListener("click", () => run("replay"));
$("copyMd").addEventListener("click", async () => { await navigator.clipboard.writeText(state.markdown); $("copyMd").textContent = "Copied"; setTimeout(() => ($("copyMd").textContent = "Copy Markdown"), 1500); });
$("downloadMd").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([state.markdown], { type: "text/markdown" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "postmortem.md" });
  a.click(); URL.revokeObjectURL(url);
});

init();
