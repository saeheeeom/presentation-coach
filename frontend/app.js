"use strict";

const $ = (id) => document.getElementById(id);

let editorSegments = [];   // [{text}]
let script = null;         // saved script from the API
let run = null;            // latest run snapshot from the API
let receivedAt = 0;        // performance.now() when `run` arrived
let recorder = null;
let audioChunks = [];

// --- helpers --------------------------------------------------------------
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(typeof detail.detail === "string" ? detail.detail : res.statusText);
  }
  return res.json();
}

const countWords = (t) => (t.match(/[A-Za-z0-9]+(?:['’\-.][A-Za-z0-9]+)*/g) || []).length;

function fmt(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function fmtDelta(d) {
  return `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(1)}s`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function showView(name) {
  for (const v of ["setup", "practice", "history"]) $(`view-${v}`).hidden = v !== name;
  $("topbar-script").textContent = name === "setup" || !script ? "" : script.title;
}

// --- setup view -----------------------------------------------------------
async function loadSaved() {
  const scripts = await api("GET", "/api/scripts");
  $("saved-card").hidden = scripts.length === 0;
  $("saved-list").innerHTML = "";
  for (const s of scripts) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${escapeHtml(s.title)} <span class="muted">· ${s.runs} run${s.runs === 1 ? "" : "s"}</span></span>`;
    const practice = document.createElement("button");
    practice.textContent = "Practice";
    practice.onclick = () => openScript(s.id);
    const edit = document.createElement("button");
    edit.textContent = "Edit";
    edit.onclick = () => editScript(s.id);
    li.append(edit, practice);
    $("saved-list").append(li);
  }
}

async function splitScript() {
  const text = $("script").value.trim();
  if (!text) return alert("Paste a script first.");
  $("split-btn").disabled = true;
  $("split-btn").textContent = $("mode").value === "llm" ? "Running local model…" : "Splitting…";
  try {
    const res = await api("POST", "/api/segment", {
      script: text, mode: $("mode").value, wpm: Number($("wpm").value) || 140,
    });
    editorSegments = res.segments.map((s) => ({ text: s.text }));
    $("split-note").hidden = !res.note;
    $("split-note").textContent = res.note || "";
    renderEditor();
  } catch (e) {
    alert(`Split failed: ${e.message}`);
  } finally {
    $("split-btn").disabled = false;
    $("split-btn").textContent = "Split into segments";
  }
}

function renderEditor() {
  const wpm = Number($("wpm").value) || 140;
  const ol = $("segment-editor");
  ol.innerHTML = "";
  editorSegments.forEach((seg, i) => {
    const li = document.createElement("li");
    const ta = document.createElement("textarea");
    ta.rows = Math.max(2, Math.ceil(seg.text.length / 90));
    ta.value = seg.text;
    const meta = document.createElement("div");
    meta.className = "seg-meta";
    const info = document.createElement("span");
    const updateInfo = () => {
      const w = countWords(seg.text);
      info.textContent = `${w} words · target ${(w / wpm * 60).toFixed(1)}s`;
      updateEditTotal();
    };
    ta.oninput = () => { seg.text = ta.value; updateInfo(); };

    const btn = (label, fn, disabled = false) => {
      const b = document.createElement("button");
      b.className = "small";
      b.textContent = label;
      b.disabled = disabled;
      b.onclick = fn;
      return b;
    };
    const spacer = document.createElement("span");
    spacer.className = "spacer";
    meta.append(
      info, spacer,
      btn("Split here", () => {
        const at = ta.selectionStart;
        const left = seg.text.slice(0, at).trim(), right = seg.text.slice(at).trim();
        if (!left || !right) return;
        editorSegments.splice(i, 1, { text: left }, { text: right });
        renderEditor();
      }),
      btn("Merge with next", () => {
        editorSegments.splice(i, 2, { text: `${seg.text.trim()} ${editorSegments[i + 1].text.trim()}` });
        renderEditor();
      }, i === editorSegments.length - 1),
      btn("Delete", () => { editorSegments.splice(i, 1); renderEditor(); }),
    );
    li.append(ta, meta);
    ol.append(li);
    updateInfo();
  });
  $("edit-card").hidden = editorSegments.length === 0;
  updateEditTotal();
}

function updateEditTotal() {
  const wpm = Number($("wpm").value) || 140;
  const words = editorSegments.reduce((n, s) => n + countWords(s.text), 0);
  const limit = Number($("limit").value) * 60;
  let text = `${editorSegments.length} segments · ${words} words · target ${fmt(words / wpm * 60)}`;
  if (limit) text += ` (limit ${fmt(limit)})`;
  $("edit-total").textContent = text;
}

async function saveScript() {
  const segments = editorSegments.map((s) => s.text.trim()).filter(Boolean);
  if (!segments.length) return alert("No segments to save.");
  const limit = Number($("limit").value);
  script = await api("POST", "/api/scripts", {
    title: $("title").value.trim() || "Untitled talk",
    segments,
    wpm: Number($("wpm").value) || 140,
    time_limit_s: limit > 0 ? limit * 60 : null,
  });
  await newRun();
}

async function editScript(id) {
  const s = await api("GET", `/api/scripts/${id}`);
  $("title").value = s.title;
  $("wpm").value = s.wpm;
  $("limit").value = s.time_limit_s ? s.time_limit_s / 60 : "";
  $("script").value = s.segments.map((x) => x.text).join("\n\n");
  editorSegments = s.segments.map((x) => ({ text: x.text }));
  renderEditor();
  showView("setup");
}

// --- practice view --------------------------------------------------------
async function openScript(id) {
  script = await api("GET", `/api/scripts/${id}`);
  await newRun();
}

async function newRun() {
  discardRecording();
  setRun(await api("POST", `/api/scripts/${script.id}/runs`));
  showView("practice");
}

function setRun(snapshot) {
  run = snapshot;
  receivedAt = performance.now();
  render();
}

async function act(action) {
  if (!run) return;
  try {
    if (action === "start" && $("record").checked) await startRecording();
    setRun(await api("POST", `/api/runs/${run.run_id}/${action}`));
    if (run.state === "finished") await finishRecording();
  } catch (e) {
    console.warn(action, e.message);
  }
}

function attemptElapsed() {
  if (!run || run.state !== "running") return 0;
  return run.attempt_elapsed + (performance.now() - receivedAt) / 1000;
}

function render() {
  if (!run || !script) return;
  const segs = script.segments;
  const i = Math.min(run.current, segs.length - 1);
  const st = run.state;

  $("prev-text").textContent = run.current > 0 ? segs[run.current - 1].text : "";
  $("current-text").textContent = st === "finished" ? "Done! 🎉" : segs[i].text;
  $("current-text").classList.toggle("paused", st === "stopped");
  $("next-text").textContent = st !== "finished" && i + 1 < segs.length ? segs[i + 1].text : "";
  $("seg-count").textContent = `${Math.min(run.current + 1, segs.length)} / ${segs.length}`;
  $("state-label").textContent = {
    idle: "Ready", running: "Speaking", stopped: "Stopped — resume when ready", finished: "Finished",
  }[st];

  const show = (id, on) => { $(id).hidden = !on; };
  show("btn-start", st === "idle");
  show("btn-advance", st === "running");
  show("btn-stop", st === "running");
  show("btn-resume", st === "stopped");
  show("btn-rewind", (st === "running" || st === "stopped" || st === "finished") && run.current > 0);
  show("finish-card", st === "finished");
  $("record").disabled = st !== "idle";

  const tbody = $("seg-table");
  tbody.innerHTML = "";
  run.segments.forEach((s, k) => {
    const tr = document.createElement("tr");
    if (k === run.current && st !== "finished") tr.className = "active";
    const delta = s.actual == null ? "" : fmtDelta(s.actual - s.target);
    const cls = s.actual == null ? "" : s.actual > s.target * 1.25 ? "over" : s.actual > s.target * 1.1 ? "near" : "";
    tr.innerHTML = `<td>${k + 1}</td><td class="snippet">${escapeHtml(segs[k].text)}</td>` +
      `<td>${s.target.toFixed(1)}s</td><td>${s.actual == null ? "—" : s.actual.toFixed(1) + "s"}</td>` +
      `<td class="${cls}">${delta}</td><td>${s.tries || ""}</td>`;
    tbody.append(tr);
  });

  if (st === "finished") {
    const total = run.base_elapsed;
    const limit = script.time_limit_s;
    const stops = run.segments.reduce((n, s) => n + Math.max(0, s.tries - 1), 0);
    let summary = `Total ${fmt(total)} vs. target ${fmt(run.total_target)}`;
    if (limit) summary += total > limit ? ` — ${fmt(total - limit)} over your limit.` : ` — within your ${fmt(limit)} limit.`;
    summary += ` ${stops} restart${stops === 1 ? "" : "s"}.`;
    $("finish-summary").textContent = summary;
  }
  tick();
}

function tick() {
  if (!run || !script) return;
  const seg = run.segments[Math.min(run.current, run.segments.length - 1)];
  const a = attemptElapsed();
  const total = run.base_elapsed + a;
  const limit = script.time_limit_s;

  $("total-clock").textContent = fmt(total);
  $("total-clock").className = "big" + (limit && total > limit ? " over" : limit && total > limit * 0.9 ? " near" : "");
  $("total-sub").textContent = limit ? `limit ${fmt(limit)}` : `target ${fmt(run.total_target)}`;

  const finished = run.state === "finished";
  $("seg-clock").textContent = finished ? "—" : fmt(a);
  $("seg-sub").textContent = finished ? "" : `target ${seg.target.toFixed(1)}s`;
  const ratio = finished ? 0 : a / seg.target;
  const bar = $("seg-progress");
  bar.style.width = `${Math.min(100, ratio * 100)}%`;
  bar.className = ratio > 1.25 ? "over" : ratio > 1 ? "near" : "";
  $("seg-clock").className = "big" + (ratio > 1.25 ? " over" : ratio > 1 ? " near" : "");
}
setInterval(tick, 100);

// --- recording (kept for Phase 2/3 analysis) ------------------------------
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => e.data.size && audioChunks.push(e.data);
    recorder.start(1000);
  } catch (e) {
    recorder = null;
    $("record").checked = false;
    alert(`Microphone unavailable (${e.message}). Practicing without recording.`);
  }
}

function stopRecorder() {
  return new Promise((resolve) => {
    if (!recorder || recorder.state === "inactive") return resolve();
    recorder.onstop = resolve;
    recorder.stop();
    recorder.stream.getTracks().forEach((t) => t.stop());
  });
}

async function finishRecording() {
  if (!recorder) return;
  const runId = run.run_id;
  await stopRecorder();
  const blob = new Blob(audioChunks, { type: recorder.mimeType || "audio/webm" });
  recorder = null;
  if (blob.size) {
    await fetch(`/api/runs/${runId}/audio`, { method: "PUT", body: blob }).catch((e) => console.warn(e));
  }
}

function discardRecording() {
  stopRecorder();
  recorder = null;
  audioChunks = [];
}

// --- history view ---------------------------------------------------------
async function showHistory() {
  const runs = (await api("GET", `/api/scripts/${script.id}/runs`))
    .filter((r) => r.durations.some((d) => d != null));
  const table = $("history-table");
  if (!runs.length) {
    table.innerHTML = `<tr><td class="muted">No runs yet.</td></tr>`;
  } else {
    const head = runs.map((r, k) => `<th>Run ${k + 1}<br><span class="muted">${new Date(r.started_at * 1000).toLocaleDateString()}</span></th>`).join("");
    const rows = script.segments.map((seg, i) => {
      const cells = runs.map((r) => {
        const d = r.durations[i];
        if (d == null) return "<td>—</td>";
        const cls = d > seg.target_seconds * 1.25 ? "over" : d > seg.target_seconds * 1.1 ? "near" : "";
        return `<td class="${cls}">${d.toFixed(1)}s</td>`;
      }).join("");
      return `<tr><td>${i + 1}</td><td>${seg.target_seconds.toFixed(1)}s</td>${cells}</tr>`;
    }).join("");
    const totals = runs.map((r) => `<td><b>${fmt(r.total_seconds || 0)}</b>${r.state === "finished" ? "" : " <span class='muted'>(partial)</span>"}</td>`).join("");
    const restarts = runs.map((r) => `<td>${r.attempts.filter((a) => a.status !== "completed").length}</td>`).join("");
    table.innerHTML = `<thead><tr><th>#</th><th>Target</th>${head}</tr></thead><tbody>${rows}` +
      `<tr><td colspan="2"><b>Total</b></td>${totals}</tr>` +
      `<tr><td colspan="2">Restarts</td>${restarts}</tr></tbody>`;
  }
  showView("history");
}

// --- wiring ---------------------------------------------------------------
$("split-btn").onclick = splitScript;
$("save-btn").onclick = () => saveScript().catch((e) => alert(`Save failed: ${e.message}`));
$("wpm").oninput = renderEditor;
$("limit").oninput = updateEditTotal;
$("home-link").onclick = (e) => { e.preventDefault(); discardRecording(); run = null; showView("setup"); loadSaved(); };
for (const a of ["start", "advance", "stop", "resume", "rewind"]) $(`btn-${a}`).onclick = () => act(a);
$("btn-again").onclick = newRun;
$("btn-history").onclick = showHistory;
$("btn-back").onclick = () => showView("practice");
$("btn-edit").onclick = () => editScript(script.id);

document.addEventListener("keydown", (e) => {
  if ($("view-practice").hidden || !run || e.target.closest("input, textarea, select")) return;
  const key = { " ": run.state === "idle" ? "start" : "advance", Escape: "stop", Enter: "resume", Backspace: "rewind" }[e.key];
  if (!key) return;
  e.preventDefault();
  act(key);
});

api("GET", "/api/health").then((h) => {
  if (!h.llm_available) {
    $("llm-option").disabled = true;
    $("llm-option").textContent = "Local LLM (install with: uv sync --extra llm)";
  }
}).catch(() => {});
loadSaved().catch(() => {});
