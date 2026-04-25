"""
=============================================================================
dashboard.py - Flask Web Dashboard
=============================================================================
Responsibility:
    - Serve a web-based dashboard showing real-time API health status.
    - Expose REST API endpoints for the frontend to fetch live data as JSON.
    - Display: uptime statistics, response times, per-endpoint status cards.
    - Auto-refresh every 15 seconds without a page reload (AJAX polling).

Routes:
    GET /           - Main dashboard HTML page
    GET /api/status - Current status of all endpoints (JSON)
    GET /api/stats  - Uptime statistics per endpoint (JSON)
    GET /api/history - Recent check log (JSON)
    GET /api/history/<name> - Response time history for one endpoint (JSON)
=============================================================================
"""

import json
import logging
import threading
from datetime import datetime
from typing import Any, Dict

from flask import Flask, jsonify, render_template_string

import database
from monitor import get_latest_results

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask application factory
# ---------------------------------------------------------------------------

def create_app(config: Dict[str, Any]) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config: Full parsed config dict from config.yaml.

    Returns:
        Configured Flask app instance (not yet running).
    """
    app = Flask(__name__)
    db_path = config.get("database", {}).get("path", "monitoring.db")

    # ------------------------------------------------------------------
    # Route: Main Dashboard HTML
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        """Serve the single-page dashboard."""
        return render_template_string(DASHBOARD_HTML)

    # ------------------------------------------------------------------
    # Route: Current status of all endpoints
    # ------------------------------------------------------------------
    @app.route("/api/status")
    def api_status():
        """
        Return the latest check result for every endpoint.
        The frontend polls this every 15s to update status cards.
        """
        latest = database.get_latest_per_endpoint(db_path)

        # Also merge in-memory results (useful during first few seconds)
        in_memory = get_latest_results()
        names_in_db = {r["endpoint_name"] for r in latest}

        for name, res in in_memory.items():
            if name not in names_in_db:
                latest.append(res)

        return jsonify(latest)

    # ------------------------------------------------------------------
    # Route: Uptime statistics
    # ------------------------------------------------------------------
    @app.route("/api/stats")
    def api_stats():
        """
        Return aggregated uptime % and average response time per endpoint.
        """
        stats = database.get_uptime_stats(db_path)
        return jsonify(stats)

    # ------------------------------------------------------------------
    # Route: Recent check log (all endpoints)
    # ------------------------------------------------------------------
    @app.route("/api/history")
    def api_history():
        """Return the 100 most recent check results across all endpoints."""
        results = database.get_recent_results(db_path, limit=100)
        return jsonify(results)

    # ------------------------------------------------------------------
    # Route: Response time history for one specific endpoint
    # ------------------------------------------------------------------
    @app.route("/api/history/<path:endpoint_name>")
    def api_history_endpoint(endpoint_name: str):
        """
        Return the last 50 response times for a named endpoint.
        Used to draw sparkline charts on the dashboard.
        """
        history = database.get_response_time_history(db_path, endpoint_name, limit=50)
        return jsonify(history)

    return app


# ---------------------------------------------------------------------------
# Dashboard HTML / CSS / JS  (single-file, no templates directory needed)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>API Health Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  /* ── Design tokens ─────────────────────────── */
  :root {
    --bg:          #0a0e17;
    --surface:     #111827;
    --surface2:    #1a2235;
    --border:      #1e2d45;
    --accent:      #00d4ff;
    --accent2:     #7b5ea7;
    --up:          #10d98a;
    --down:        #ff4757;
    --degraded:    #ffa502;
    --text:        #e2e8f0;
    --muted:       #64748b;
    --mono:        'JetBrains Mono', monospace;
    --display:     'Syne', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--display);
    min-height: 100vh;
  }

  /* ── Animated grid background ──────────────── */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  .container { max-width: 1280px; margin: 0 auto; padding: 0 24px; position: relative; z-index: 1; }

  /* ── Header ─────────────────────────────────── */
  header {
    border-bottom: 1px solid var(--border);
    padding: 20px 0;
    margin-bottom: 32px;
  }
  .header-inner {
    display: flex; align-items: center; justify-content: space-between;
  }
  .logo {
    display: flex; align-items: center; gap: 12px;
  }
  .logo-icon {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 8px;
    display: grid; place-items: center;
    font-size: 18px;
  }
  .logo h1 {
    font-size: 1.15rem; font-weight: 800; letter-spacing: -.02em;
    background: linear-gradient(90deg, var(--accent), #fff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .logo span { font-size: .7rem; color: var(--muted); font-family: var(--mono); display: block; }

  .header-right { display: flex; align-items: center; gap: 16px; }
  #last-updated { font-family: var(--mono); font-size: .72rem; color: var(--muted); }
  .pulse-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--up);
    box-shadow: 0 0 0 0 rgba(16,217,138,.5);
    animation: pulse-ring 1.5s infinite;
  }
  @keyframes pulse-ring {
    0%   { box-shadow: 0 0 0 0 rgba(16,217,138,.5); }
    70%  { box-shadow: 0 0 0 8px rgba(16,217,138,0); }
    100% { box-shadow: 0 0 0 0 rgba(16,217,138,0); }
  }

  /* ── Summary bar ─────────────────────────────── */
  .summary-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 32px;
  }
  .summary-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .summary-card::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
  }
  .summary-label {
    font-size: .7rem; color: var(--muted); text-transform: uppercase;
    letter-spacing: .1em; font-family: var(--mono); margin-bottom: 8px;
  }
  .summary-value {
    font-size: 2rem; font-weight: 800;
    line-height: 1;
  }
  .summary-value.up    { color: var(--up); }
  .summary-value.down  { color: var(--down); }
  .summary-value.avg   { color: var(--accent); }
  .summary-value.total { color: var(--text); }

  /* ── Section title ───────────────────────────── */
  .section-title {
    font-size: .75rem; color: var(--muted); text-transform: uppercase;
    letter-spacing: .12em; font-family: var(--mono);
    margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
  }
  .section-title::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
  }

  /* ── Status grid ─────────────────────────────── */
  #status-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }

  .endpoint-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    transition: border-color .2s, transform .15s;
    position: relative;
    overflow: hidden;
  }
  .endpoint-card:hover { transform: translateY(-2px); border-color: var(--accent); }

  .status-stripe {
    position: absolute; top: 0; left: 0; bottom: 0; width: 3px;
    border-radius: 12px 0 0 12px;
  }
  .status-stripe.UP       { background: var(--up); }
  .status-stripe.DOWN     { background: var(--down); }
  .status-stripe.DEGRADED { background: var(--degraded); }
  .status-stripe.UNKNOWN  { background: var(--muted); }

  .card-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    margin-bottom: 14px; padding-left: 10px;
  }
  .card-name {
    font-size: .9rem; font-weight: 700; color: var(--text);
    max-width: 220px; line-height: 1.3;
  }
  .card-url {
    font-family: var(--mono); font-size: .65rem; color: var(--muted);
    word-break: break-all; padding-left: 10px; margin-bottom: 14px;
  }

  .status-badge {
    font-family: var(--mono); font-size: .65rem; font-weight: 700;
    padding: 3px 10px; border-radius: 20px; letter-spacing: .05em;
    white-space: nowrap;
  }
  .status-badge.UP       { background: rgba(16,217,138,.15); color: var(--up); }
  .status-badge.DOWN     { background: rgba(255,71,87,.15);  color: var(--down); }
  .status-badge.DEGRADED { background: rgba(255,165,2,.15);  color: var(--degraded); }
  .status-badge.UNKNOWN  { background: rgba(100,116,139,.15); color: var(--muted); }

  .card-metrics {
    display: grid; grid-template-columns: 1fr 1fr 1fr;
    gap: 8px; padding-left: 10px;
  }
  .metric { }
  .metric-label {
    font-size: .62rem; color: var(--muted); font-family: var(--mono);
    text-transform: uppercase; letter-spacing: .06em;
  }
  .metric-value {
    font-size: .85rem; font-weight: 700; font-family: var(--mono); color: var(--text);
    margin-top: 2px;
  }

  /* sparkline */
  .sparkline-wrap { padding: 14px 10px 0; }
  .sparkline-label {
    font-size: .62rem; color: var(--muted); font-family: var(--mono);
    text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px;
  }
  canvas.sparkline { width: 100%; height: 40px; display: block; }

  /* error pill */
  .error-msg {
    margin: 10px 10px 0;
    background: rgba(255,71,87,.08);
    border: 1px solid rgba(255,71,87,.2);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: .68rem;
    font-family: var(--mono);
    color: var(--down);
    word-break: break-word;
    line-height: 1.4;
  }

  /* ── Uptime stats table ───────────────────────── */
  #stats-table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 40px;
  }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    background: var(--surface2);
    padding: 12px 16px;
    text-align: left;
    font-size: .7rem; text-transform: uppercase;
    letter-spacing: .1em; color: var(--muted);
    font-family: var(--mono);
    border-bottom: 1px solid var(--border);
  }
  tbody tr { border-bottom: 1px solid var(--border); }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: var(--surface2); }
  tbody td {
    padding: 12px 16px;
    font-size: .82rem;
    font-family: var(--mono);
  }
  .uptime-bar-wrap {
    display: flex; align-items: center; gap: 8px;
  }
  .uptime-bar {
    flex: 1; height: 6px;
    background: var(--border); border-radius: 3px; overflow: hidden;
  }
  .uptime-bar-fill {
    height: 100%; border-radius: 3px;
    background: var(--up);
    transition: width .5s ease;
  }
  .uptime-bar-fill.warn { background: var(--degraded); }
  .uptime-bar-fill.crit { background: var(--down); }
  .uptime-pct { font-weight: 700; min-width: 48px; }

  /* ── Log table ───────────────────────────────── */
  #log-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 60px;
  }
  .log-row-UP       { }
  .log-row-DOWN     td:first-child { color: var(--down); }
  .log-row-DEGRADED td:first-child { color: var(--degraded); }

  /* ── Loading state ───────────────────────────── */
  .loading {
    text-align: center; padding: 60px;
    color: var(--muted); font-family: var(--mono); font-size: .85rem;
  }
  .loading::after {
    content: ''; display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin .8s linear infinite;
    margin-left: 10px; vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  @media (max-width: 768px) {
    .summary-bar { grid-template-columns: 1fr 1fr; }
  }
</style>
</head>
<body>

<div class="container">

  <!-- ── Header ─────────────────────────────────── -->
  <header>
    <div class="header-inner">
      <div class="logo">
        <div class="logo-icon">⚡</div>
        <div>
          <h1>API Health Monitor</h1>
          <span>Real-time endpoint surveillance</span>
        </div>
      </div>
      <div class="header-right">
        <span id="last-updated">Initializing…</span>
        <div class="pulse-dot" id="pulse-dot"></div>
      </div>
    </div>
  </header>

  <!-- ── Summary bar ────────────────────────────── -->
  <div class="summary-bar">
    <div class="summary-card">
      <div class="summary-label">Total Endpoints</div>
      <div class="summary-value total" id="sum-total">—</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Currently UP</div>
      <div class="summary-value up" id="sum-up">—</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Currently DOWN</div>
      <div class="summary-value down" id="sum-down">—</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Avg Response</div>
      <div class="summary-value avg" id="sum-avg">—</div>
    </div>
  </div>

  <!-- ── Endpoint status cards ──────────────────── -->
  <div class="section-title">Live Status</div>
  <div id="status-grid"><div class="loading">Fetching endpoint status</div></div>

  <!-- ── Uptime statistics table ────────────────── -->
  <div class="section-title">Uptime Statistics</div>
  <div id="stats-table-wrap">
    <div class="loading">Loading statistics</div>
  </div>

  <!-- ── Recent log ─────────────────────────────── -->
  <div class="section-title">Recent Check Log</div>
  <div id="log-wrap">
    <div class="loading">Loading log</div>
  </div>

</div>

<script>
// ── Sparkline histories (endpoint_name → array of ms values) ──
const sparklineData = {};

// ── Helpers ───────────────────────────────────────────────────

function fmtTime(ms) {
  if (ms === null || ms === undefined) return '—';
  return ms < 1000 ? ms.toFixed(0) + ' ms' : (ms/1000).toFixed(2) + ' s';
}

function fmtTs(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function statusClass(s) {
  return ['UP','DOWN','DEGRADED'].includes(s) ? s : 'UNKNOWN';
}

// ── Draw a tiny sparkline in a <canvas> ──────────────────────
function drawSparkline(canvas, values) {
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth || 280;
  const H = 40;
  canvas.width = W;
  canvas.height = H;
  ctx.clearRect(0, 0, W, H);

  if (!values || values.length < 2) return;

  const min = Math.min(...values);
  const max = Math.max(...values) || 1;
  const range = (max - min) || 1;
  const pts = values.map((v, i) => ({
    x: (i / (values.length - 1)) * W,
    y: H - ((v - min) / range) * (H - 8) - 4
  }));

  // Fill
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, 'rgba(0,212,255,.25)');
  grad.addColorStop(1, 'rgba(0,212,255,0)');
  ctx.beginPath();
  ctx.moveTo(pts[0].x, H);
  pts.forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length-1].x, H);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  pts.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ── Fetch sparkline data for one endpoint ─────────────────────
async function fetchSparkline(name) {
  try {
    const res = await fetch('/api/history/' + encodeURIComponent(name));
    const data = await res.json();
    sparklineData[name] = data.map(r => r.response_time).filter(v => v !== null);
  } catch(e) {}
}

// ── Render endpoint status cards ─────────────────────────────
function renderStatusCards(endpoints) {
  const grid = document.getElementById('status-grid');
  if (!endpoints || endpoints.length === 0) {
    grid.innerHTML = '<div class="loading">No data yet — check starting…</div>';
    return;
  }

  // Summary counts
  const upCount   = endpoints.filter(e => e.status === 'UP').length;
  const downCount = endpoints.filter(e => e.status !== 'UP').length;
  const avgMs     = endpoints
    .map(e => e.response_time).filter(Boolean)
    .reduce((a, b, _, arr) => a + b / arr.length, 0);

  document.getElementById('sum-total').textContent = endpoints.length;
  document.getElementById('sum-up').textContent    = upCount;
  document.getElementById('sum-down').textContent  = downCount;
  document.getElementById('sum-avg').textContent   = fmtTime(avgMs || null);

  let html = '';
  endpoints.forEach(ep => {
    const sc = statusClass(ep.status || 'UNKNOWN');
    const sparkId = 'spark-' + btoa(ep.endpoint_name || ep.url).replace(/=/g,'');
    html += `
      <div class="endpoint-card">
        <div class="status-stripe ${sc}"></div>
        <div class="card-header">
          <div class="card-name">${ep.endpoint_name || 'Unknown'}</div>
          <span class="status-badge ${sc}">${sc}</span>
        </div>
        <div class="card-url">${ep.url || ''}</div>
        <div class="card-metrics">
          <div class="metric">
            <div class="metric-label">Response</div>
            <div class="metric-value">${fmtTime(ep.response_time)}</div>
          </div>
          <div class="metric">
            <div class="metric-label">HTTP</div>
            <div class="metric-value">${ep.http_code || '—'}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Checked</div>
            <div class="metric-value">${fmtTs(ep.timestamp)}</div>
          </div>
        </div>
        <div class="sparkline-wrap">
          <div class="sparkline-label">Response time trend</div>
          <canvas class="sparkline" id="${sparkId}"></canvas>
        </div>
        ${ep.error_message ? `<div class="error-msg">⚠ ${ep.error_message}</div>` : ''}
      </div>
    `;
    // Kick off sparkline data fetch
    fetchSparkline(ep.endpoint_name).then(() => {
      const canvas = document.getElementById(sparkId);
      if (canvas && sparklineData[ep.endpoint_name]) {
        drawSparkline(canvas, sparklineData[ep.endpoint_name]);
      }
    });
  });

  grid.innerHTML = html;
}

// ── Render uptime stats table ─────────────────────────────────
function renderStats(stats) {
  const wrap = document.getElementById('stats-table-wrap');
  if (!stats || stats.length === 0) {
    wrap.innerHTML = '<div class="loading">Collecting data…</div>';
    return;
  }

  let rows = stats.map(s => {
    const pct  = s.uptime_pct || 0;
    const cls  = pct >= 99 ? '' : pct >= 90 ? 'warn' : 'crit';
    return `
      <tr>
        <td>${s.endpoint_name}</td>
        <td>${s.total_checks}</td>
        <td>
          <div class="uptime-bar-wrap">
            <div class="uptime-bar">
              <div class="uptime-bar-fill ${cls}" style="width:${pct}%"></div>
            </div>
            <span class="uptime-pct" style="color:${pct>=99?'var(--up)':pct>=90?'var(--degraded)':'var(--down)'}">${pct}%</span>
          </div>
        </td>
        <td>${fmtTime(s.avg_response_ms)}</td>
      </tr>
    `;
  }).join('');

  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Endpoint</th>
          <th>Total Checks</th>
          <th>Uptime</th>
          <th>Avg Response</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ── Render recent log table ───────────────────────────────────
function renderLog(history) {
  const wrap = document.getElementById('log-wrap');
  if (!history || history.length === 0) {
    wrap.innerHTML = '<div class="loading">No log entries yet</div>';
    return;
  }

  let rows = history.slice(0, 40).map(r => {
    const sc = statusClass(r.status);
    return `
      <tr class="log-row-${sc}">
        <td><span class="status-badge ${sc}">${sc}</span></td>
        <td>${r.endpoint_name}</td>
        <td>${fmtTs(r.timestamp)}</td>
        <td>${fmtTime(r.response_time)}</td>
        <td>${r.http_code || '—'}</td>
        <td style="color:var(--muted);font-size:.7rem;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${r.error_message || '—'}
        </td>
      </tr>
    `;
  }).join('');

  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Status</th><th>Endpoint</th><th>Time</th>
          <th>Response</th><th>HTTP</th><th>Error</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ── Main refresh loop ─────────────────────────────────────────
async function refresh() {
  try {
    const [statusRes, statsRes, histRes] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/stats'),
      fetch('/api/history'),
    ]);

    renderStatusCards(await statusRes.json());
    renderStats(await statsRes.json());
    renderLog(await histRes.json());

    document.getElementById('last-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  } catch(e) {
    console.error('Refresh error:', e);
  }
}

// Initial load + auto-refresh every 15 seconds
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point — run when this file is executed directly
# ---------------------------------------------------------------------------

def run_dashboard(config: Dict[str, Any]) -> None:
    """
    Start the Flask development server.

    Args:
        config: Full parsed config dict.
    """
    dash_cfg = config.get("dashboard", {})
    host = dash_cfg.get("host", "0.0.0.0")
    port = dash_cfg.get("port", 5000)

    app = create_app(config)

    logger.info("Dashboard starting at http://%s:%d", host, port)
    # use_reloader=False is critical — we're inside a thread already
    app.run(host=host, port=port, debug=False, use_reloader=False)
