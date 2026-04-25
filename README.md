# API Health Check Monitor
### Assignment 31 — Production-Ready Python Project

---

## Project Overview

This system continuously monitors REST API endpoints for **availability**, **response time**, and **response correctness**. It provides:

| Feature | Implementation |
|---|---|
| Endpoint Monitoring | 5 public APIs checked in parallel every 30s |
| Response Validation | HTTP status + required JSON keys + value assertions |
| Alert System | Console logs + optional Email (SMTP) + optional Slack |
| Dashboard | Flask web UI with live status, uptime %, response charts |
| Historical Logging | SQLite database with full check history |
| Configuration | Single `config.yaml` controls everything |

---

## Project Structure

```
api_health_monitor/
│
├── main.py           ← Entry point. Starts monitor thread + Flask dashboard.
├── monitor.py        ← Core engine. Polls endpoints, dispatches results.
├── validator.py      ← Validates HTTP status, JSON keys, and expected values.
├── alerts.py         ← Sends alerts via Console / Email / Slack.
├── database.py       ← SQLite read/write for historical logging.
├── dashboard.py      ← Flask web app + full single-page HTML dashboard.
│
├── config.yaml       ← ALL configuration lives here (endpoints, alerts, etc.)
├── requirements.txt  ← Python dependencies (flask, requests, pyyaml)
│
├── monitoring.db     ← Created automatically at first run (SQLite)
└── README.md         ← This file
```

---

## Monitored APIs (from config.yaml)

| # | Name | URL | What's Validated |
|---|------|-----|-----------------|
| 1 | JSONPlaceholder - Posts | https://jsonplaceholder.typicode.com/posts/1 | Keys: userId, id, title, body; id==1 |
| 2 | Open-Meteo Weather | https://api.open-meteo.com/v1/forecast?... | Keys: latitude, longitude, current_weather |
| 3 | RestCountries - India | https://restcountries.com/v3.1/alpha/IN | Keys: name, capital, region, population |
| 4 | CoinGecko - Bitcoin | https://api.coingecko.com/api/v3/simple/price?... | Key: bitcoin |
| 5 | IP-API - Geolocation | http://ip-api.com/json/8.8.8.8 | Keys: status, country, city, query; status=="success" |

---

## Setup Instructions

### Step 1 — Prerequisites

- Python 3.9 or higher
- pip

Verify with:
```bash
python --version
pip --version
```

### Step 2 — Navigate to project folder

```bash
cd api_health_monitor
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `flask` — Web dashboard framework
- `requests` — HTTP client for endpoint checks
- `pyyaml` — YAML configuration parser

### Step 4 — (Optional) Configure Alerts

Open `config.yaml` and find the `alerts:` section:

**To enable Email alerts (Gmail):**
1. Enable 2FA on your Gmail account
2. Generate an App Password: Google Account → Security → App Passwords
3. Fill in `config.yaml`:
```yaml
alerts:
  email_enabled: true
  email:
    sender_email: "your_email@gmail.com"
    sender_password: "xxxx xxxx xxxx xxxx"   # App Password
    recipient_email: "alert_recipient@email.com"
```

**To enable Slack alerts:**
1. Go to https://api.slack.com/apps → Create New App → Incoming Webhooks
2. Copy the Webhook URL and paste into `config.yaml`:
```yaml
alerts:
  slack_enabled: true
  slack:
    webhook_url: "https://hooks.slack.com/services/T.../B.../..."
```

---

## Running the System

### Start the monitor + dashboard

```bash
python main.py
```

Expected output:
```
2024-01-15 10:00:00 [INFO    ] main                 ============================================================
2024-01-15 10:00:00 [INFO    ] main                   API Health Check Monitor  —  Starting up
2024-01-15 10:00:00 [INFO    ] main                 ============================================================
2024-01-15 10:00:00 [INFO    ] database             Database initialized at: monitoring.db
2024-01-15 10:00:00 [INFO    ] monitor              Config loaded: 5 endpoint(s) found.
2024-01-15 10:00:00 [INFO    ] main                 Monitoring thread started (daemon=True).
2024-01-15 10:00:00 [INFO    ] main                 Dashboard → http://localhost:5000  (press Ctrl+C to stop)
2024-01-15 10:00:01 [INFO    ] monitor              JSONPlaceholder - Posts      | UP       |    187 ms | HTTP 200 | Valid: True
2024-01-15 10:00:01 [INFO    ] monitor              Open-Meteo - Weather Forecast| UP       |    421 ms | HTTP 200 | Valid: True
```

### Use a custom config file

```bash
python main.py --config /path/to/my_config.yaml
```

### Stop the system

Press `Ctrl+C` in the terminal.

---

## Viewing the Dashboard

Open your browser and navigate to:

```
http://localhost:5000
```

The dashboard shows:

1. **Summary Bar** — Total endpoints, UP count, DOWN count, average response time
2. **Live Status Cards** — One card per endpoint showing:
   - Current status badge (UP / DOWN / DEGRADED)
   - HTTP response code
   - Response time in milliseconds
   - Last checked timestamp
   - Response time sparkline (trend over last 50 checks)
   - Error message (if down)
3. **Uptime Statistics Table** — Historical uptime % and average response time
4. **Recent Check Log** — Last 40 individual check results

The dashboard **auto-refreshes every 15 seconds** — no need to manually reload.

---

## Architecture & Data Flow

```
config.yaml
    │
    ▼
main.py ──────────────────────────────────────────────────────────────────────
    │                                                                          │
    ├──► Thread: monitor.py (background daemon)               Flask: dashboard.py
    │        │                                                      │
    │        ├─► check_endpoint()  ─► requests.get(url)            │  GET /
    │        │       │                                              │  GET /api/status
    │        │       ├─► validator.py ─► ValidationResult          │  GET /api/stats
    │        │       │                                              │  GET /api/history
    │        │       └─► result dict                               │
    │        │                                                      │
    │        ├─► alerts.py ◄─── if status != 'UP'                 │
    │        │       │                                              │
    │        │       ├── Console log (always)                      │
    │        │       ├── Email (if enabled)                        │
    │        │       └── Slack (if enabled)                        │
    │        │                                                      │
    │        └─► database.py ──► monitoring.db ◄──────────────────┘
    │                (write)                       (read)
    │
    └──► Ctrl+C → clean shutdown
```

---

## Module Reference

### `config.yaml`
Single source of truth. Controls:
- `settings.check_interval_seconds` — How often to poll all endpoints
- `settings.request_timeout_seconds` — Per-request timeout
- `endpoints[].validation.required_keys` — Keys that must exist in JSON response
- `endpoints[].validation.expected_values` — Key-value assertions
- `endpoints[].thresholds.max_response_time_ms` — Slow threshold (triggers DEGRADED)
- `alerts.*` — Toggle and configure each notification channel

### `monitor.py`
- `load_config(path)` — Parses YAML into a Python dict
- `check_endpoint(ep, timeout)` — Makes one HTTP request, measures time, returns result dict
- `run_monitoring_cycle(...)` — Checks all endpoints in parallel using threads
- `start_monitoring_loop(config)` — Infinite loop that calls the cycle every N seconds

### `validator.py`
- `validate_status_code(actual, expected)` → ValidationResult
- `validate_required_keys(json, keys)` → ValidationResult
- `validate_expected_values(json, expected_dict)` → ValidationResult
- `run_all_validations(...)` → Merged ValidationResult (all checks combined)

### `alerts.py`
- `dispatch_alert(name, status, details, config)` — Routes to enabled channels
- `send_console_alert(...)` — Logs WARNING to stdout
- `send_email_alert(...)` — Sends HTML email via SMTP
- `send_slack_alert(...)` — Posts Block Kit message to Slack Webhook

### `database.py`
- `initialize_database(path)` — Creates SQLite table on first run
- `save_result(path, result)` — INSERT one check result
- `get_uptime_stats(path)` — GROUP BY endpoint, compute uptime %
- `get_latest_per_endpoint(path)` — Latest result per endpoint (for status cards)
- `get_response_time_history(path, name, limit)` — For sparkline charts
- `get_recent_results(path, limit)` — For the log table

### `dashboard.py`
- `create_app(config)` — Flask app factory; registers all routes
- `run_dashboard(config)` — Starts Flask server (blocking)

---

## SQLite Database Schema

**Table: `monitoring_results`**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment row ID |
| endpoint_name | TEXT | Human-readable name from config.yaml |
| url | TEXT | Full URL that was checked |
| timestamp | TEXT | ISO-8601 UTC datetime |
| status | TEXT | `UP`, `DOWN`, or `DEGRADED` |
| http_code | INTEGER | Actual HTTP response code (0 = timeout) |
| response_time | REAL | Duration in milliseconds |
| error_message | TEXT | NULL on success; failure reason otherwise |
| is_valid | INTEGER | 1 = validation passed, 0 = failed |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: flask` | Run `pip install -r requirements.txt` |
| `FileNotFoundError: config.yaml` | Run from the project directory, or use `--config path/to/config.yaml` |
| All endpoints show DOWN | Check your internet connection; some APIs rate-limit residential IPs |
| Email alerts not sending | Use Gmail App Password (not login password); enable 2FA first |
| Dashboard shows no data | Wait 30s for the first monitoring cycle to complete |
| Port 5000 in use | Change `dashboard.port` in `config.yaml` to e.g. 5001 |

---

## Adding a New Endpoint

Add an entry to `config.yaml` under `endpoints:`:

```yaml
- name: "My API - Health Check"
  url: "https://api.example.com/health"
  method: GET
  expected_status: 200
  validation:
    required_keys:
      - "status"
      - "version"
    expected_values:
      status: "ok"
  thresholds:
    max_response_time_ms: 1500
```

No code changes required — just edit `config.yaml` and restart.

---

*Built for CS Assignment 31 — demonstrates threading, HTTP, YAML config, SQLite, Flask, and modular Python architecture.*
