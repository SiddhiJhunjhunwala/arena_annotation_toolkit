"""
Step 2: Annotation UI — Flask server with embedded single-page HTML.

Run: python annotator_app.py
Opens: http://localhost:5000

Keyboard shortcuts:
  1-4  : set task domain
  r/i/f/a/n : set signal type (rephrasing / ignoring / frustration / abandonment / none)
  H/M/L : confidence high / medium / low
  → / Enter : save & next
  ← : go back

Progress is auto-saved to data/arena_candidates.json after every annotation.
"""

import json, os
from pathlib import Path
from flask import Flask, jsonify, request, render_template_string

DATA_FILE = Path("data/arena_candidates.json")
app = Flask(__name__)

# ── Load data ─────────────────────────────────────────────────────────────────

def load_data():
    with open(DATA_FILE) as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/data")
def api_data():
    data = load_data()
    stats = {
        "total": len(data),
        "annotated": sum(1 for r in data if r["annotation"]["confirmed_signal"] is not None),
        "by_signal": {},
    }
    for sig in ("response_ignoring", "frustration_marker", "task_abandonment", "none"):
        stats["by_signal"][sig] = sum(
            1 for r in data if r["annotation"]["confirmed_signal"] == sig
        )
    return jsonify({"records": data, "stats": stats})

@app.route("/api/save", methods=["POST"])
def api_save():
    payload = request.json
    idx = payload["index"]
    annotation = payload["annotation"]
    data = load_data()
    if 0 <= idx < len(data):
        data[idx]["annotation"] = annotation
        save_data(data)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "index out of range"}), 400

@app.route("/api/export")
def api_export():
    """Trigger Excel export from frontend."""
    import subprocess, sys
    result = subprocess.run([sys.executable, "save_annotations.py"], capture_output=True, text=True)
    if result.returncode == 0:
        return jsonify({"ok": True, "message": result.stdout.strip()})
    return jsonify({"ok": False, "error": result.stderr.strip()}), 500

# ── Frontend ──────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arena Signal Annotator</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

  :root {
    --bg:        #0d0f14;
    --surface:   #151820;
    --border:    #252a35;
    --accent:    #4fffb0;
    --accent2:   #ff6b6b;
    --accent3:   #ffcc44;
    --accent4:   #74b9ff;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --mono:      'IBM Plex Mono', monospace;
    --sans:      'IBM Plex Sans', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    height: 100vh;
    display: grid;
    grid-template-rows: 52px 1fr;
    grid-template-columns: 280px 1fr 340px;
    overflow: hidden;
  }

  /* ── Header ── */
  header {
    grid-column: 1 / -1;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    padding: 0 16px;
    gap: 16px;
  }

  .logo {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .progress-bar-wrap {
    flex: 1;
    background: var(--border);
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
  }
  .progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent4));
    border-radius: 3px;
    transition: width 0.4s ease;
  }

  .stat-chips {
    display: flex;
    gap: 8px;
  }
  .chip {
    font-family: var(--mono);
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
    color: var(--muted);
  }
  .chip span { color: var(--text); font-weight: 600; }

  .header-actions {
    display: flex;
    gap: 8px;
  }

  .btn-export {
    font-family: var(--mono);
    font-size: 11px;
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 5px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-export:hover { background: rgba(79,255,176,0.1); }

  /* ── Conversation list panel ── */
  #list-panel {
    grid-column: 1;
    grid-row: 2;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .list-search {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    position: relative;
  }
  .list-search input {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: var(--mono);
    font-size: 11px;
    border-radius: 4px;
    padding: 6px 10px 6px 28px;
    outline: none;
    transition: border-color 0.12s;
  }
  .list-search input:focus { border-color: var(--accent); }
  .list-search .search-icon {
    position: absolute;
    left: 20px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    font-size: 11px;
    pointer-events: none;
  }

  .list-filters {
    padding: 8px 12px;
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .filter-chip {
    font-family: var(--mono);
    font-size: 10px;
    padding: 3px 7px;
    border-radius: 3px;
    border: 1px solid var(--border);
    color: var(--muted);
    background: transparent;
    cursor: pointer;
    transition: all 0.1s;
  }
  .filter-chip:hover { color: var(--text); border-color: var(--text); }
  .filter-chip.active-filter { color: var(--accent); border-color: var(--accent); background: rgba(79,255,176,0.08); }
  .filter-chip.f-red.active-filter    { color: var(--accent2); border-color: var(--accent2); background: rgba(255,107,107,0.08); }
  .filter-chip.f-yellow.active-filter { color: var(--accent3); border-color: var(--accent3); background: rgba(255,204,68,0.08); }
  .filter-chip.f-blue.active-filter   { color: var(--accent4); border-color: var(--accent4); background: rgba(116,185,255,0.08); }

  #conv-list {
    overflow-y: auto;
    flex: 1;
  }

  .conv-item {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.1s;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .conv-item:hover { background: rgba(255,255,255,0.03); }
  .conv-item.selected { background: rgba(79,255,176,0.07); border-left: 2px solid var(--accent); }

  .conv-item-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }
  .conv-id {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 120px;
  }
  .conv-sig-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .dot-response_ignoring  { background: var(--accent4); }
  .dot-frustration_marker { background: var(--accent2); }
  .dot-task_abandonment   { background: var(--accent3); }
  .dot-none               { background: var(--muted); }
  .dot-unannotated        { background: var(--border); border: 1px solid var(--muted); }

  .conv-preview {
    font-size: 11px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .conv-annotated-badge {
    font-family: var(--mono);
    font-size: 9px;
    color: var(--accent);
    border: 1px solid rgba(79,255,176,0.3);
    padding: 1px 5px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .list-count {
    padding: 6px 12px;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }

  /* ── Main conversation area ── */
  main {
    grid-column: 2;
    grid-row: 2;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .record-meta {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    display: flex;
    gap: 16px;
    align-items: center;
  }
  .signal-badge {
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-weight: 600;
  }
  .sig-response_ignoring  { background: rgba(116,185,255,0.15); color: var(--accent4); border: 1px solid rgba(116,185,255,0.3); }
  .sig-frustration_marker { background: rgba(255,107,107,0.15); color: var(--accent2); border: 1px solid rgba(255,107,107,0.3); }
  .sig-task_abandonment   { background: rgba(255,204,68,0.15);  color: var(--accent3); border: 1px solid rgba(255,204,68,0.3); }
  .sig-none               { background: rgba(100,116,139,0.15); color: var(--muted);   border: 1px solid var(--border); }

  .convo-label {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 4px;
    padding: 0 4px;
  }

  .conversation {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    max-height: 420px;
    overflow-y: auto;
  }

  .bubble-row {
    display: flex;
    align-items: flex-end;
    gap: 8px;
  }
  .bubble-row.user { flex-direction: row-reverse; }

  .avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 700;
    flex-shrink: 0;
    font-family: var(--mono);
    letter-spacing: 0.03em;
  }
  .avatar.user-av  { background: rgba(79,255,176,0.18); color: var(--accent); }
  .avatar.asst-av  { background: rgba(116,185,255,0.18); color: var(--accent4); }

  .bubble {
    max-width: 75%;
    padding: 9px 13px;
    border-radius: 18px;
    font-size: 13px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .bubble.user {
    background: rgba(79,255,176,0.13);
    border: 1px solid rgba(79,255,176,0.25);
    color: var(--text);
    border-bottom-right-radius: 4px;
  }
  .bubble.assistant {
    background: rgba(116,185,255,0.10);
    border: 1px solid rgba(116,185,255,0.2);
    color: var(--text);
    border-bottom-left-radius: 4px;
  }
  .bubble.signal-highlight {
    outline: 2px solid var(--accent2);
    outline-offset: 2px;
  }

  /* ── Sidebar annotation panel ── */
  aside {
    grid-column: 3;
    grid-row: 2;
    background: var(--surface);
    border-left: 1px solid var(--border);
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .panel-section { display: flex; flex-direction: column; gap: 8px; }

  .panel-label {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .btn-choice {
    font-family: var(--mono);
    font-size: 11px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 6px 10px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.12s;
    flex: 1;
    min-width: 80px;
    text-align: center;
  }
  .btn-choice:hover { border-color: var(--text); color: var(--text); }
  .btn-choice.active {
    background: rgba(79,255,176,0.12);
    border-color: var(--accent);
    color: var(--accent);
  }
  .btn-choice.active.red   { background: rgba(255,107,107,0.12); border-color: var(--accent2); color: var(--accent2); }
  .btn-choice.active.yellow { background: rgba(255,204,68,0.12);  border-color: var(--accent3); color: var(--accent3); }
  .btn-choice.active.blue  { background: rgba(116,185,255,0.12); border-color: var(--accent4); color: var(--accent4); }
  .btn-choice.active.gray  { background: rgba(100,116,139,0.12); border-color: var(--muted);   color: var(--muted); }

  textarea, input[type=text] {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: var(--sans);
    font-size: 13px;
    border-radius: 4px;
    padding: 8px 10px;
    width: 100%;
    resize: vertical;
    outline: none;
    transition: border-color 0.12s;
  }
  textarea:focus, input[type=text]:focus { border-color: var(--accent); }

  .nav-row {
    display: flex;
    gap: 8px;
    margin-top: auto;
  }

  .btn-nav {
    flex: 1;
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    padding: 10px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.12s;
    border: none;
    letter-spacing: 0.05em;
  }
  .btn-prev {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
  }
  .btn-prev:hover { border-color: var(--text); color: var(--text); }
  .btn-next {
    background: var(--accent);
    color: #0d0f14;
  }
  .btn-next:hover { filter: brightness(0.9); }
  .btn-next:disabled { opacity: 0.4; cursor: not-allowed; }

  .shortcut-hint {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    text-align: center;
    line-height: 1.8;
  }
  kbd {
    background: var(--border);
    border-radius: 2px;
    padding: 1px 4px;
    color: var(--text);
    font-size: 10px;
  }

  .index-display {
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 600;
    color: var(--text);
    line-height: 1;
  }
  .index-display span { color: var(--muted); font-size: 14px; font-weight: 400; }

  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--accent);
    color: #0d0f14;
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    padding: 8px 20px;
    border-radius: 4px;
    opacity: 0;
    transition: opacity 0.2s;
    pointer-events: none;
    z-index: 999;
  }
  .toast.show { opacity: 1; }
</style>
</head>
<body>

<header>
  <div class="logo">Arena Annotator</div>
  <div class="progress-bar-wrap">
    <div class="progress-bar-fill" id="progressFill" style="width:0%"></div>
  </div>
  <div class="stat-chips">
    <div class="chip">Total <span id="statTotal">—</span></div>
    <div class="chip">Done <span id="statDone">—</span></div>
    <div class="chip">Ignoring <span id="statIgnoring">—</span></div>
    <div class="chip">Frustration <span id="statFrustration">—</span></div>
    <div class="chip">Abandonment <span id="statAbandonment">—</span></div>
  </div>
  <div class="header-actions">
    <button class="btn-export" onclick="exportExcel()">⬇ Export Excel</button>
  </div>
</header>

<div id="list-panel">
  <div class="list-search">
    <span class="search-icon">⌕</span>
    <input type="text" id="searchInput" placeholder="Search by ID or message…" oninput="filterList()">
  </div>
  <div class="list-filters">
    <button class="filter-chip active-filter" data-sig="all"                onclick="setFilter(this)">All</button>
    <button class="filter-chip f-blue"        data-sig="response_ignoring"  onclick="setFilter(this)">Ignoring</button>
    <button class="filter-chip f-red"         data-sig="frustration_marker" onclick="setFilter(this)">Frustration</button>
    <button class="filter-chip f-yellow"      data-sig="task_abandonment"   onclick="setFilter(this)">Abandon</button>
    <button class="filter-chip"               data-sig="unannotated"        onclick="setFilter(this)">Todo</button>
  </div>
  <div class="list-count" id="listCount">—</div>
  <div id="conv-list"></div>
</div>

<main id="main">
  <div style="color:var(--muted);font-family:var(--mono);padding:40px;text-align:center;">← Select a conversation</div>
</main>

<aside id="sidebar">
  <div class="panel-section">
    <div class="index-display" id="indexDisplay">— <span>/ —</span></div>
    <div id="autoInfo" style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:6px;line-height:1.8;"></div>
  </div>

  <div class="panel-section">
    <div class="panel-label">Confirmed Signal Type</div>
    <div class="btn-group">
      <button class="btn-choice blue"   data-field="confirmed_signal" data-val="response_ignoring"  onclick="setField(this)">Ignoring</button>
      <button class="btn-choice red"    data-field="confirmed_signal" data-val="frustration_marker" onclick="setField(this)">Frustration</button>
      <button class="btn-choice yellow" data-field="confirmed_signal" data-val="task_abandonment"   onclick="setField(this)">Abandonment</button>
      <button class="btn-choice gray"   data-field="confirmed_signal" data-val="none"               onclick="setField(this)">None</button>
    </div>
  </div>

  <div class="panel-section">
    <div class="panel-label">Confidence</div>
    <div class="btn-group">
      <button class="btn-choice" data-field="confidence" data-val="high"   onclick="setField(this)">High</button>
      <button class="btn-choice" data-field="confidence" data-val="medium" onclick="setField(this)">Medium</button>
      <button class="btn-choice" data-field="confidence" data-val="low"    onclick="setField(this)">Low</button>
    </div>
  </div>

  <div class="panel-section">
    <div class="panel-label">Task Domain</div>
    <div class="btn-group">
      <button class="btn-choice" data-field="task_domain" data-val="mathematics"     onclick="setField(this)">Math</button>
      <button class="btn-choice" data-field="task_domain" data-val="coding"          onclick="setField(this)">Code</button>
      <button class="btn-choice" data-field="task_domain" data-val="writing"         onclick="setField(this)">Writing</button>
      <button class="btn-choice" data-field="task_domain" data-val="general_knowledge" onclick="setField(this)">General</button>
    </div>
  </div>

  <div class="panel-section">
    <div class="panel-label">Signal Evidence (which turn shows it?)</div>
    <textarea id="fieldEvidence" rows="2" placeholder="e.g. Turn 3, user says 'still wrong'" oninput="annotation.signal_evidence = this.value"></textarea>
  </div>

  <div class="panel-section">
    <div class="panel-label">What's Updated (agent should update…)</div>
    <textarea id="fieldUpdated" rows="2" placeholder="e.g. Response length preference, explanation depth" oninput="annotation.what_is_updated = this.value"></textarea>
  </div>

  <div class="panel-section">
    <div class="panel-label">Inferred Preference</div>
    <textarea id="fieldPreference" rows="3" placeholder="e.g. User prefers step-by-step explanations with examples" oninput="annotation.inferred_preference = this.value"></textarea>
  </div>

  <div class="panel-section">
    <div class="panel-label">Notes</div>
    <textarea id="fieldNotes" rows="2" placeholder="Any edge cases or ambiguity..." oninput="annotation.notes = this.value"></textarea>
  </div>

  <div class="nav-row">
    <button class="btn-nav btn-prev" onclick="navigate(-1)">← Back</button>
    <button class="btn-nav btn-next" id="btnNext" onclick="saveAndNext()">Save & Next →</button>
  </div>

  <div class="shortcut-hint">
    <kbd>i</kbd> ignoring &nbsp; <kbd>f</kbd> frustration &nbsp; <kbd>a</kbd> abandon &nbsp; <kbd>n</kbd> none<br>
    <kbd>H</kbd>/<kbd>M</kbd>/<kbd>L</kbd> confidence &nbsp; <kbd>1</kbd>-<kbd>4</kbd> domain<br>
    <kbd>→</kbd> or <kbd>Enter</kbd> save &amp; next &nbsp; <kbd>←</kbd> back
  </div>
</aside>

<div class="toast" id="toast"></div>

<script>
let records = [];
let stats = {};
let currentIdx = 0;
let annotation = {};
let activeFilter = 'all';
let searchQuery = '';

async function fetchData() {
  const res = await fetch('/api/data');
  const d = await res.json();
  records = d.records;
  stats = d.stats;
  updateStats();
  renderList();
  if (records.length) renderRecord(currentIdx);
}

function updateStats() {
  document.getElementById('statTotal').textContent       = stats.total || 0;
  document.getElementById('statDone').textContent        = stats.annotated || 0;
  document.getElementById('statIgnoring').textContent    = stats.by_signal?.response_ignoring || 0;
  document.getElementById('statFrustration').textContent = stats.by_signal?.frustration_marker || 0;
  document.getElementById('statAbandonment').textContent = stats.by_signal?.task_abandonment || 0;
  const pct = stats.total ? (stats.annotated / stats.total * 100) : 0;
  document.getElementById('progressFill').style.width = pct + '%';
}

function getFilteredIndices() {
  const q = searchQuery.toLowerCase();
  return records.reduce((acc, rec, i) => {
    const sig    = rec.annotation?.confirmed_signal;
    const isAnnotated = sig !== null && sig !== undefined;

    // filter
    if (activeFilter === 'unannotated' && isAnnotated) return acc;
    if (activeFilter !== 'all' && activeFilter !== 'unannotated' && rec.feedback_type !== activeFilter) return acc;

    // search
    if (q) {
      const id      = String(rec.question_id || rec.conv_id || i).toLowerCase();
      const preview = (rec.user_msg_preview || '').toLowerCase();
      const signal  = (rec.feedback_type || '').toLowerCase();
      if (!id.includes(q) && !preview.includes(q) && !signal.includes(q)) return acc;
    }
    acc.push(i);
    return acc;
  }, []);
}

function renderList() {
  const indices = getFilteredIndices();
  document.getElementById('listCount').textContent = `${indices.length} conversation${indices.length !== 1 ? 's' : ''}`;

  const container = document.getElementById('conv-list');
  container.innerHTML = indices.map(i => {
    const rec = records[i];
    const sig = rec.annotation?.confirmed_signal;
    const isAnnotated = sig !== null && sig !== undefined;
    const dotClass = isAnnotated ? `dot-${sig || 'none'}` : 'dot-unannotated';
    const sigType  = rec.feedback_type || '';
    const preview  = rec.user_msg_preview || '';
    const id       = rec.question_id || rec.conv_id || i;
    const selected = i === currentIdx ? ' selected' : '';

    return `<div class="conv-item${selected}" onclick="selectRecord(${i})">
      <div class="conv-item-top">
        <span class="conv-id" title="${escHtml(String(id))}">#${escHtml(String(id).substring(0,18))}</span>
        <div style="display:flex;align-items:center;gap:5px">
          ${isAnnotated ? '<span class="conv-annotated-badge">✓</span>' : ''}
          <div class="conv-sig-dot ${dotClass}" title="${sigType}"></div>
        </div>
      </div>
      <div class="conv-preview">${escHtml(preview.substring(0,60))}${preview.length > 60 ? '…' : ''}</div>
    </div>`;
  }).join('');
}

function selectRecord(idx) {
  currentIdx = idx;
  renderList();
  renderRecord(idx);
  // scroll selected into view
  const selected = document.querySelector('.conv-item.selected');
  if (selected) selected.scrollIntoView({ block: 'nearest' });
}

function setFilter(btn) {
  document.querySelectorAll('.filter-chip').forEach(b => b.classList.remove('active-filter'));
  btn.classList.add('active-filter');
  activeFilter = btn.dataset.sig;
  renderList();
}

function filterList() {
  searchQuery = document.getElementById('searchInput').value;
  renderList();
}

function renderRecord(idx) {
  if (!records.length) return;
  currentIdx = Math.max(0, Math.min(idx, records.length - 1));
  const rec = records[currentIdx];
  annotation = JSON.parse(JSON.stringify(rec.annotation));

  document.getElementById('indexDisplay').innerHTML =
    `${currentIdx + 1} <span>/ ${records.length}</span>`;

  // Show auto-inferred metadata
  const ai = document.getElementById('autoInfo');
  if (rec.turn || rec.how_its_given) {
    ai.innerHTML =
      `<span style="color:var(--accent3)">Turn ${rec.turn || '?'}</span> &nbsp;·&nbsp; ` +
      `${escHtml(rec.how_its_given || '')}` +
      (rec.user_msg_preview ? `<br><span style="color:var(--text);font-style:italic">"${escHtml(rec.user_msg_preview.substring(0,100))}…"</span>` : '');
  } else {
    ai.innerHTML = '';
  }

  const badges = (rec.detected_signals || []).map(s =>
    `<span class="signal-badge sig-${s}">${s.replace(/_/g, ' ')}</span>`
  ).join(' ');

  document.getElementById('main').innerHTML = `
    <div class="record-meta">
      <span>#${escHtml(String(rec.question_id || currentIdx))}</span>
      ${badges}
      <span>Winner: <strong style="color:var(--accent3)">${rec.winner || '—'}</strong></span>
      <span style="color:var(--muted)">${rec.num_user_turns || ''} user turns</span>
    </div>
    <div>
      <div class="convo-label">Model A (${escHtml(rec.model_a || '')})</div>
      ${renderConvoHTML(rec.conversation_a, rec.turn)}
    </div>
    ${rec.conversation_b && rec.conversation_b.length ? `<div>
      <div class="convo-label">Model B (${escHtml(rec.model_b || '')})</div>
      ${renderConvoHTML(rec.conversation_b, rec.turn)}
    </div>` : ''}
  `;

  restoreSidebarState();
}

function renderConvoHTML(turns, signalTurnNumber) {
  if (!turns || !turns.length) {
    return '<div class="conversation" style="color:var(--muted);font-size:12px;font-family:var(--mono);">No turns</div>';
  }
  const bubblesHTML = turns.map((t, i) => {
    const isUser    = t.role === 'user';
    const isSignal  = signalTurnNumber && (i + 1) === signalTurnNumber;
    const highlight = isSignal ? ' signal-highlight' : '';
    return `
      <div class="bubble-row ${isUser ? 'user' : ''}">
        <div class="avatar ${isUser ? 'user-av' : 'asst-av'}">${isUser ? 'U' : 'AI'}</div>
        <div class="bubble ${isUser ? 'user' : 'assistant'}${highlight}">${escHtml(t.content)}</div>
      </div>`;
  }).join('');
  return `<div class="conversation">${bubblesHTML}</div>`;
}

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function restoreSidebarState() {
  document.querySelectorAll('.btn-choice').forEach(b => b.classList.remove('active'));
  ['confirmed_signal','confidence','task_domain'].forEach(field => {
    if (annotation[field]) {
      const btn = document.querySelector(`.btn-choice[data-field="${field}"][data-val="${annotation[field]}"]`);
      if (btn) btn.classList.add('active');
    }
  });
  document.getElementById('fieldEvidence').value   = annotation.signal_evidence || '';
  document.getElementById('fieldUpdated').value    = annotation.what_is_updated || '';
  document.getElementById('fieldPreference').value = annotation.inferred_preference || '';
  document.getElementById('fieldNotes').value      = annotation.notes || '';
}

function setField(btn) {
  const field = btn.dataset.field;
  const val   = btn.dataset.val;
  if (annotation[field] === val) {
    annotation[field] = null;
    btn.classList.remove('active');
    return;
  }
  annotation[field] = val;
  document.querySelectorAll(`.btn-choice[data-field="${field}"]`).forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

async function saveAndNext() {
  await saveAnnotation();
  const indices = getFilteredIndices();
  const pos = indices.indexOf(currentIdx);
  if (pos < indices.length - 1) {
    selectRecord(indices[pos + 1]);
  } else {
    showToast('All done in this view! Export to Excel ↗');
  }
}

async function navigate(dir) {
  const indices = getFilteredIndices();
  const pos = indices.indexOf(currentIdx);
  const nextPos = pos + dir;
  if (nextPos < 0 || nextPos >= indices.length) return;
  await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ index: currentIdx, annotation })
  });
  selectRecord(indices[nextPos]);
}

async function saveAnnotation() {
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ index: currentIdx, annotation })
  });
  const d = await res.json();
  if (d.ok) showToast('Saved ✓');
  records[currentIdx].annotation = JSON.parse(JSON.stringify(annotation));
  updateStats();
  renderList();
}

async function exportExcel() {
  showToast('Exporting...');
  const res = await fetch('/api/export');
  const d = await res.json();
  if (d.ok) showToast('Exported! Check data/arena_annotations.xlsx');
  else showToast('Export error: ' + d.error);
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

document.addEventListener('keydown', e => {
  if (e.target.id === 'searchInput') return;
  if (['INPUT','TEXTAREA'].includes(e.target.tagName)) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); saveAndNext(); }
    return;
  }
  const map = {
    'i': ['confirmed_signal','response_ignoring'],
    'f': ['confirmed_signal','frustration_marker'],
    'a': ['confirmed_signal','task_abandonment'],
    'n': ['confirmed_signal','none'],
    'H': ['confidence','high'],
    'M': ['confidence','medium'],
    'L': ['confidence','low'],
    '1': ['task_domain','mathematics'],
    '2': ['task_domain','coding'],
    '3': ['task_domain','writing'],
    '4': ['task_domain','general_knowledge'],
  };
  if (map[e.key]) {
    const [field, val] = map[e.key];
    const btn = document.querySelector(`.btn-choice[data-field="${field}"][data-val="${val}"]`);
    if (btn) setField(btn);
  }
  if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); saveAndNext(); }
  if (e.key === 'ArrowLeft')  { e.preventDefault(); navigate(-1); }
});

fetchData();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    if not DATA_FILE.exists():
        print("ERROR: data/arena_candidates.json not found.")
        print("Run: python download_data.py first.")
        exit(1)
    print("\n  Arena Signal Annotator")
    print("  ──────────────────────────────────────────────────")
    print("  ▶  Paste this into Chrome / Safari / Firefox:")
    print("     http://127.0.0.1:8765")
    print("  ◼  Stop server: Ctrl+C")
    print("  ──────────────────────────────────────────────────\n")
    app.run(debug=False, host="127.0.0.1", port=8765)