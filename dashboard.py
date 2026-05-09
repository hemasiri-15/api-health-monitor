"""
=============================================================================
dashboard.py - Flask Web Dashboard
=============================================================================
Responsibility:
    - Serve a web-based dashboard at http://localhost:5000
    - Expose REST JSON endpoints for live AJAX polling
    - Display: status cards, Chart.js analytics, uptime table, check log
    - Auto-refreshes every 15 seconds without page reload

Routes:
    GET /                        - Main dashboard HTML page
    GET /api/status              - Current status of all endpoints (JSON)
    GET /api/stats               - Uptime statistics per endpoint (JSON)
    GET /api/history             - Recent check log (JSON)
    GET /api/history/<name>      - Response time history for one endpoint (JSON)
=============================================================================
"""

import logging
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
    Create and configure the Flask application with all routes.

    Args:
        config: Full parsed config dict from config.yaml

    Returns:
        Configured Flask app instance
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
        Merges DB results with in-memory cache for freshness.
        """
        latest = database.get_latest_per_endpoint(db_path)
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
        """Return aggregated uptime % and avg response time per endpoint."""
        return jsonify(database.get_uptime_stats(db_path))

    # ------------------------------------------------------------------
    # Route: Recent check log
    # ------------------------------------------------------------------
    @app.route("/api/history")
    def api_history():
        """Return the 100 most recent check results across all endpoints."""
        return jsonify(database.get_recent_results(db_path, limit=100))

    # ------------------------------------------------------------------
    # Route: Response time history for one endpoint (sparklines)
    # ------------------------------------------------------------------
    @app.route("/api/history/<path:endpoint_name>")
    def api_history_endpoint(endpoint_name: str):
        """Return last 50 response times for a named endpoint."""
        return jsonify(database.get_response_time_history(db_path, endpoint_name, limit=50))

    return app


# ---------------------------------------------------------------------------
# Dashboard HTML — single file, all CSS/JS inline, no external templates
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>API Health Monitor</title>
<!-- Chart.js for analytics charts -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<!-- Google Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  /* ── Design tokens ─────────────────────────── */
  :root {
    --bg:       #0a0e17;
    --surface:  #111827;
    --surface2: #1a2235;
    --border:   #1e2d45;
    --accent:   #00d4ff;
    --accent2:  #7b5ea7;
    --up:       #10d98a;
    --down:     #ff4757;
    --degraded: #ffa502;
    --text:     #e2e8f0;
    --muted:    #64748b;
    --mono:     'JetBrains Mono', monospace;
    --display:  'Syne', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--display); min-height: 100vh; }

  /* Animated grid background */
  body::before {
    content: ''; position: fixed; inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none; z-index: 0;
  }

  .container { max-width: 1400px; margin: 0 auto; padding: 0 24px; position: relative; z-index: 1; }

  /* ── Header ─────────────────────────────────── */
  header { border-bottom: 1px solid var(--border); padding: 20px 0; margin-bottom: 32px; }
  .header-inner { display: flex; align-items: center; justify-content: space-between; }
  .logo { display: flex; align-items: center; gap: 12px; }
  .logo-icon { width: 40px; height: 40px; background: linear-gradient(135deg, var(--accent), var(--accent2)); border-radius: 10px; display: grid; place-items: center; font-size: 20px; }
  .logo h1 { font-size: 1.2rem; font-weight: 800; background: linear-gradient(90deg, var(--accent), #fff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .logo span { font-size: .7rem; color: var(--muted); font-family: var(--mono); display: block; }
  .header-right { display: flex; align-items: center; gap: 12px; }
  #last-updated { font-family: var(--mono); font-size: .72rem; color: var(--muted); }
  .pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--up); animation: pulse-ring 1.5s infinite; }
  @keyframes pulse-ring {
    0%   { box-shadow: 0 0 0 0   rgba(16,217,138,.5); }
    70%  { box-shadow: 0 0 0 8px rgba(16,217,138,0);  }
    100% { box-shadow: 0 0 0 0   rgba(16,217,138,0);  }
  }

  /* ── Summary bar ─────────────────────────────── */
  .summary-bar { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 32px; }
  .summary-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; position: relative; overflow: hidden; }
  .summary-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, var(--accent), var(--accent2)); }
  .summary-label { font-size: .7rem; color: var(--muted); text-transform: uppercase; letter-spacing: .1em; font-family: var(--mono); margin-bottom: 8px; }
  .summary-value { font-size: 2rem; font-weight: 800; line-height: 1; }
  .summary-value.up    { color: var(--up);    }
  .summary-value.down  { color: var(--down);  }
  .summary-value.avg   { color: var(--accent);}
  .summary-value.total { color: var(--text);  }

  /* ── Section title ───────────────────────────── */
  .section-title { font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .12em; font-family: var(--mono); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
  .section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }

  /* ── Status cards ────────────────────────────── */
  #status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px,1fr)); gap: 16px; margin-bottom: 40px; }
  .endpoint-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; transition: border-color .2s, transform .15s; position: relative; overflow: hidden; }
  .endpoint-card:hover { transform: translateY(-2px); border-color: var(--accent); }
  .status-stripe { position: absolute; top: 0; left: 0; bottom: 0; width: 3px; border-radius: 12px 0 0 12px; }
  .status-stripe.UP       { background: var(--up);      }
  .status-stripe.DOWN     { background: var(--down);    }
  .status-stripe.DEGRADED { background: var(--degraded);}
  .status-stripe.UNKNOWN  { background: var(--muted);   }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; padding-left: 10px; }
  .card-name   { font-size: .88rem; font-weight: 700; max-width: 210px; line-height: 1.3; }
  .card-url    { font-family: var(--mono); font-size: .62rem; color: var(--muted); word-break: break-all; padding-left: 10px; margin-bottom: 12px; }
  .status-badge { font-family: var(--mono); font-size: .63rem; font-weight: 700; padding: 3px 10px; border-radius: 20px; letter-spacing: .05em; white-space: nowrap; }
  .status-badge.UP       { background: rgba(16,217,138,.15); color: var(--up);      }
  .status-badge.DOWN     { background: rgba(255,71,87,.15);  color: var(--down);    }
  .status-badge.DEGRADED { background: rgba(255,165,2,.15);  color: var(--degraded);}
  .status-badge.UNKNOWN  { background: rgba(100,116,139,.15);color: var(--muted);   }
  .card-metrics { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; padding-left: 10px; }
  .metric-label { font-size: .6rem; color: var(--muted); font-family: var(--mono); text-transform: uppercase; letter-spacing: .06em; }
  .metric-value { font-size: .82rem; font-weight: 700; font-family: var(--mono); margin-top: 2px; }
  .sparkline-wrap  { padding: 12px 10px 0; }
  .sparkline-label { font-size: .6rem; color: var(--muted); font-family: var(--mono); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
  canvas.sparkline { width: 100% !important; height: 40px !important; }
  .error-msg { margin: 10px 10px 0; background: rgba(255,71,87,.08); border: 1px solid rgba(255,71,87,.2); border-radius: 6px; padding: 6px 10px; font-size: .67rem; font-family: var(--mono); color: var(--down); word-break: break-word; line-height: 1.4; }

  /* ── Analytics charts row ────────────────────── */
  .charts-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 40px; }
  .chart-card  { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .chart-title { font-size: .72rem; color: var(--muted); font-family: var(--mono); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 16px; }
  .chart-canvas-wrap { position: relative; height: 200px; }

  /* ── Uptime stats table ───────────────────────── */
  #stats-table-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 40px; }
  table { width: 100%; border-collapse: collapse; }
  thead th { background: var(--surface2); padding: 12px 16px; text-align: left; font-size: .68rem; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); font-family: var(--mono); border-bottom: 1px solid var(--border); }
  tbody tr { border-bottom: 1px solid var(--border); }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: var(--surface2); }
  tbody td { padding: 12px 16px; font-size: .82rem; font-family: var(--mono); }
  .uptime-bar-wrap { display: flex; align-items: center; gap: 8px; }
  .uptime-bar      { flex: 1; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .uptime-bar-fill { height: 100%; border-radius: 3px; background: var(--up); transition: width .5s ease; }
  .uptime-bar-fill.warn { background: var(--degraded); }
  .uptime-bar-fill.crit { background: var(--down);     }
  .uptime-pct { font-weight: 700; min-width: 48px; }

  /* ── Log table ───────────────────────────────── */
  #log-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 60px; }

  /* ── Loading spinner ─────────────────────────── */
  .loading { text-align: center; padding: 40px; color: var(--muted); font-family: var(--mono); font-size: .85rem; }
  .loading::after { content: ''; display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; margin-left: 10px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Responsive ──────────────────────────────── */
  @media (max-width: 900px) {
    .summary-bar { grid-template-columns: 1fr 1fr; }
    .charts-row  { grid-template-columns: 1fr; }
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
        <div class="pulse-dot"></div>
      </div>
    </div>
  </header>

  <!-- ── Summary bar ────────────────────────────── -->
  <div class="summary-bar">
    <div class="summary-card"><div class="summary-label">Total Endpoints</div><div class="summary-value total" id="sum-total">—</div></div>
    <div class="summary-card"><div class="summary-label">Currently UP</div>   <div class="summary-value up"    id="sum-up">—</div></div>
    <div class="summary-card"><div class="summary-label">Currently DOWN</div> <div class="summary-value down"  id="sum-down">—</div></div>
    <div class="summary-card"><div class="summary-label">Avg Response</div>   <div class="summary-value avg"   id="sum-avg">—</div></div>
  </div>

  <!-- ── Live status cards ──────────────────────── -->
  <div class="section-title">Live Status</div>
  <div id="status-grid"><div class="loading">Fetching endpoint status</div></div>

  <!-- ── Chart.js analytics ─────────────────────── -->
  <div class="section-title">Analytics</div>
  <div class="charts-row">
    <div class="chart-card">
      <div class="chart-title">📊 Uptime % per Endpoint</div>
      <div class="chart-canvas-wrap"><canvas id="chartUptime"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">⚡ Avg Response Time (ms)</div>
      <div class="chart-canvas-wrap"><canvas id="chartResponse"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🟢 Health Overview</div>
      <div class="chart-canvas-wrap"><canvas id="chartPie"></canvas></div>
    </div>
  </div>

  <!-- ── Uptime statistics table ────────────────── -->
  <div class="section-title">Uptime Statistics</div>
  <div id="stats-table-wrap"><div class="loading">Loading statistics</div></div>

  <!-- ── Recent check log ───────────────────────── -->
  <div class="section-title">Recent Check Log</div>
  <div id="log-wrap"><div class="loading">Loading log</div></div>

</div>

<script>
// ── Chart instances (persisted so we update instead of recreate) ──
let chartUptime = null, chartResponse = null, chartPie = null;

// ── Per-endpoint sparkline data cache ────────────────────────────
const sparklineData = {};

// ── Shared Chart.js default options ──────────────────────────────
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
};

// ── Utility helpers ───────────────────────────────────────────────

function fmtTime(ms) {
  if (ms === null || ms === undefined) return '—';
  return ms < 1000 ? ms.toFixed(0) + ' ms' : (ms / 1000).toFixed(2) + ' s';
}

function fmtTs(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString();
}

function statusClass(s) {
  return ['UP', 'DOWN', 'DEGRADED'].includes(s) ? s : 'UNKNOWN';
}

// ── Draw a sparkline in a <canvas> using raw 2D API ──────────────
function drawSparkline(canvas, values) {
  const W = canvas.offsetWidth || 280, H = 40;
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, W, H);
  if (!values || values.length < 2) return;

  const min = Math.min(...values), max = Math.max(...values) || 1, range = (max - min) || 1;
  const pts = values.map((v, i) => ({
    x: (i / (values.length - 1)) * W,
    y: H - ((v - min) / range) * (H - 8) - 4
  }));

  // Gradient fill under line
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, 'rgba(0,212,255,.25)');
  grad.addColorStop(1, 'rgba(0,212,255,0)');
  ctx.beginPath();
  ctx.moveTo(pts[0].x, H);
  pts.forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length - 1].x, H);
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

// ── Fetch sparkline history for one endpoint ──────────────────────
async function fetchSparkline(name) {
  try {
    const r = await fetch('/api/history/' + encodeURIComponent(name));
    const d = await r.json();
    sparklineData[name] = d.map(r => r.response_time).filter(v => v !== null);
  } catch (e) {}
}

// ── Render live status cards ──────────────────────────────────────
function renderStatusCards(endpoints) {
  const grid = document.getElementById('status-grid');
  if (!endpoints || !endpoints.length) {
    grid.innerHTML = '<div class="loading">No data yet — first check starting…</div>';
    return;
  }

  // Update summary bar
  const upCount = endpoints.filter(e => e.status === 'UP').length;
  const downCount = endpoints.filter(e => e.status !== 'UP').length;
  const avgMs = endpoints.map(e => e.response_time).filter(Boolean)
    .reduce((a, b, _, arr) => a + b / arr.length, 0);
  document.getElementById('sum-total').textContent = endpoints.length;
  document.getElementById('sum-up').textContent    = upCount;
  document.getElementById('sum-down').textContent  = downCount;
  document.getElementById('sum-avg').textContent   = fmtTime(avgMs || null);

  // Build cards
  let html = '';
  endpoints.forEach(ep => {
    const s = statusClass(ep.status);
    const sid = 'sp-' + Math.random().toString(36).slice(2);
    html += `
      <div class="endpoint-card">
        <div class="status-stripe ${s}"></div>
        <div class="card-header">
          <div class="card-name">${ep.endpoint_name || 'Unknown'}</div>
          <span class="status-badge ${s}">${s}</span>
        </div>
        <div class="card-url">${ep.url || ''}</div>
        <div class="card-metrics">
          <div><div class="metric-label">Response</div><div class="metric-value">${fmtTime(ep.response_time)}</div></div>
          <div><div class="metric-label">HTTP</div>    <div class="metric-value">${ep.http_code || '—'}</div></div>
          <div><div class="metric-label">Checked</div> <div class="metric-value">${fmtTs(ep.timestamp)}</div></div>
        </div>
        <div class="sparkline-wrap">
          <div class="sparkline-label">Response Time Trend</div>
          <canvas class="sparkline" id="${sid}"></canvas>
        </div>
        ${ep.error_message ? `<div class="error-msg">⚠ ${ep.error_message}</div>` : ''}
      </div>`;

    // Async: fetch history then draw sparkline
    fetchSparkline(ep.endpoint_name).then(() => {
      const c = document.getElementById(sid);
      if (c && sparklineData[ep.endpoint_name]) drawSparkline(c, sparklineData[ep.endpoint_name]);
    });
  });
  grid.innerHTML = html;
}

// ── Render Chart.js analytics charts ─────────────────────────────
function renderCharts(stats, statusData) {
  if (!stats || !stats.length) return;

  // Short labels (first word before ' - ' or ' — ')
  const labels    = stats.map(s => s.endpoint_name.split(/\s[-—]\s/)[0]);
  const uptimes   = stats.map(s => s.uptime_pct || 0);
  const responses = stats.map(s => s.avg_response_ms || 0);

  // ── Chart 1: Uptime bar chart ──────────────────
  const ctx1 = document.getElementById('chartUptime').getContext('2d');
  if (chartUptime) chartUptime.destroy();
  chartUptime = new Chart(ctx1, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: uptimes,
        backgroundColor: uptimes.map(v => v >= 99 ? '#10d98a33' : v >= 90 ? '#ffa50233' : '#ff475733'),
        borderColor:     uptimes.map(v => v >= 99 ? '#10d98a'   : v >= 90 ? '#ffa502'   : '#ff4757'),
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        y: {
          min: 0, max: 100,
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 }, callback: v => v + '%' },
          grid:  { color: '#1e2d45' }
        },
        x: {
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 9 }, maxRotation: 30 },
          grid:  { display: false }
        }
      },
      plugins: { ...CHART_DEFAULTS.plugins, tooltip: { callbacks: { label: ctx => ctx.raw + '% uptime' } } }
    }
  });

  // ── Chart 2: Response time bar chart ──────────
  const ctx2 = document.getElementById('chartResponse').getContext('2d');
  if (chartResponse) chartResponse.destroy();
  chartResponse = new Chart(ctx2, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: responses,
        backgroundColor: '#00d4ff22',
        borderColor: '#00d4ff',
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      ...CHART_DEFAULTS,
      scales: {
        y: {
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 }, callback: v => v + 'ms' },
          grid:  { color: '#1e2d45' }
        },
        x: {
          ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 9 }, maxRotation: 30 },
          grid:  { display: false }
        }
      },
      plugins: { ...CHART_DEFAULTS.plugins, tooltip: { callbacks: { label: ctx => ctx.raw.toFixed(0) + ' ms avg' } } }
    }
  });

  // ── Chart 3: Health pie / doughnut ────────────
  const upCount   = (statusData || []).filter(e => e.status === 'UP').length;
  const downCount = (statusData || []).filter(e => e.status === 'DOWN').length;
  const degCount  = (statusData || []).filter(e => e.status === 'DEGRADED').length;
  const ctx3 = document.getElementById('chartPie').getContext('2d');
  if (chartPie) chartPie.destroy();
  chartPie = new Chart(ctx3, {
    type: 'doughnut',
    data: {
      labels: ['UP', 'DOWN', 'DEGRADED'],
      datasets: [{
        data: [upCount, downCount, degCount],
        backgroundColor: ['#10d98a44', '#ff475744', '#ffa50244'],
        borderColor:     ['#10d98a',   '#ff4757',   '#ffa502'],
        borderWidth: 2,
      }]
    },
    options: {
      ...CHART_DEFAULTS,
      cutout: '65%',
      plugins: {
        legend: {
          display: true, position: 'bottom',
          labels: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 }, padding: 12 }
        },
        tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.raw + ' endpoint(s)' } }
      }
    }
  });
}

// ── Render uptime statistics table ───────────────────────────────
function renderStats(stats) {
  const wrap = document.getElementById('stats-table-wrap');
  if (!stats || !stats.length) { wrap.innerHTML = '<div class="loading">Collecting data…</div>'; return; }

  const rows = stats.map(s => {
    const pct = s.uptime_pct || 0;
    const cls = pct >= 99 ? '' : pct >= 90 ? 'warn' : 'crit';
    const col = pct >= 99 ? 'var(--up)' : pct >= 90 ? 'var(--degraded)' : 'var(--down)';
    return `<tr>
      <td>${s.endpoint_name}</td>
      <td>${s.total_checks}</td>
      <td>
        <div class="uptime-bar-wrap">
          <div class="uptime-bar"><div class="uptime-bar-fill ${cls}" style="width:${pct}%"></div></div>
          <span class="uptime-pct" style="color:${col}">${pct}%</span>
        </div>
      </td>
      <td>${fmtTime(s.avg_response_ms)}</td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr><th>Endpoint</th><th>Total Checks</th><th>Uptime</th><th>Avg Response</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Render recent check log table ─────────────────────────────────
function renderLog(history) {
  const wrap = document.getElementById('log-wrap');
  if (!history || !history.length) { wrap.innerHTML = '<div class="loading">No log entries yet</div>'; return; }

  const rows = history.slice(0, 40).map(r => {
    const s = statusClass(r.status);
    return `<tr>
      <td><span class="status-badge ${s}">${s}</span></td>
      <td>${r.endpoint_name}</td>
      <td>${fmtTs(r.timestamp)}</td>
      <td>${fmtTime(r.response_time)}</td>
      <td>${r.http_code || '—'}</td>
      <td style="color:var(--muted);font-size:.7rem;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        ${r.error_message || '—'}
      </td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr><th>Status</th><th>Endpoint</th><th>Time</th><th>Response</th><th>HTTP</th><th>Error</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Main refresh — called on load and every 15s ───────────────────
async function refresh() {
  try {
    const [sRes, stRes, hRes] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/stats'),
      fetch('/api/history'),
    ]);
    const statusData = await sRes.json();
    const statsData  = await stRes.json();
    const histData   = await hRes.json();

    renderStatusCards(statusData);
    renderCharts(statsData, statusData);   // ← Chart.js analytics
    renderStats(statsData);
    renderLog(histData);

    document.getElementById('last-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  } catch (e) {
    console.error('Dashboard refresh error:', e);
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
# Entry point
# ---------------------------------------------------------------------------

def run_dashboard(config: Dict[str, Any]) -> None:
    """
    Start the Flask development server.

    Args:
        config: Full parsed config dict from config.yaml
    """
    dash_cfg = config.get("dashboard", {})
    host = dash_cfg.get("host", "0.0.0.0")
    port = dash_cfg.get("port", 5000)
    app = create_app(config)
    logger.info("Dashboard starting at http://%s:%d", host, port)
    # use_reloader=False is critical — we're already inside a thread
    app.run(host=host, port=port, debug=False, use_reloader=False)
