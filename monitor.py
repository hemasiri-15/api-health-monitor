"""
=============================================================================
monitor.py - Core Monitoring Engine
=============================================================================
Responsibility:
    - Load the YAML configuration file.
    - Continuously poll every configured endpoint at the defined interval.
    - Measure response time, check HTTP status, and parse JSON bodies.
    - Delegate validation to validator.py.
    - Dispatch alerts through alerts.py on failure.
    - Persist every check result to SQLite via database.py.

This module is the "heartbeat" of the entire system. It runs in a background
thread so the Flask dashboard can serve requests concurrently.
=============================================================================
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

from alerts import dispatch_alert
from database import initialize_database, save_result
from validator import run_all_validations

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory cache of the most recent result per endpoint
# (used by dashboard to avoid a DB round-trip for 'current status')
# ---------------------------------------------------------------------------
_latest_results: Dict[str, Dict] = {}
_results_lock = threading.Lock()  # Thread-safe access to shared dict


def get_latest_results() -> Dict[str, Dict]:
    """Return a copy of the in-memory latest results cache."""
    with _results_lock:
        return dict(_latest_results)


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Read and parse the YAML configuration file.

    Args:
        config_path: Path to config.yaml (relative or absolute).

    Returns:
        Parsed configuration as a Python dict.

    Raises:
        FileNotFoundError: If config.yaml does not exist.
        yaml.YAMLError:    If the YAML syntax is invalid.
    """
    with open(config_path, "r") as fh:
        config = yaml.safe_load(fh)
    logger.info(
        "Config loaded: %d endpoint(s) found.",
        len(config.get("endpoints", []))
    )
    return config


# ---------------------------------------------------------------------------
# Single endpoint check
# ---------------------------------------------------------------------------

def check_endpoint(endpoint: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """
    Perform one HTTP request against a single endpoint and return a result dict.

    Steps:
        1. Send the HTTP request (GET/POST as configured), measure elapsed time.
        2. Determine status: UP, DOWN, or DEGRADED (slow but alive).
        3. Parse JSON body (if any).
        4. Run all validation rules.
        5. Build and return a result dictionary ready for DB + alerts.

    Args:
        endpoint: One entry from config.yaml['endpoints'].
        timeout:  Request timeout in seconds from config.yaml['settings'].

    Returns:
        Dict with keys: endpoint_name, url, timestamp, status,
                        http_code, response_time, error_message, is_valid
    """
    name    = endpoint["name"]
    url     = endpoint["url"]
    method  = endpoint.get("method", "GET").upper()
    max_ms  = endpoint.get("thresholds", {}).get("max_response_time_ms", 5000)

    # Initialise result with safe defaults
    result: Dict[str, Any] = {
        "endpoint_name": name,
        "url":           url,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "status":        "DOWN",
        "http_code":     0,
        "response_time": None,
        "error_message": None,
        "is_valid":      False,
    }

    try:
        # --- Step 1: Execute HTTP request ---
        start_time = time.perf_counter()

        response = requests.request(
            method=method,
            url=url,
            headers=endpoint.get("headers", {}),
            json=endpoint.get("body"),       # Only used for POST/PUT
            timeout=timeout,
            allow_redirects=True,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000  # Convert to ms

        result["http_code"]     = response.status_code
        result["response_time"] = round(elapsed_ms, 2)

        # --- Step 2: Determine status ---
        # 'DEGRADED' = alive but too slow
        if elapsed_ms > max_ms:
            result["status"] = "DEGRADED"
            logger.warning(
                "%s responded in %.0fms (threshold: %dms) — DEGRADED",
                name, elapsed_ms, max_ms
            )
        else:
            result["status"] = "UP"  # Tentatively UP; validation may change this

        # --- Step 3: Try to parse JSON ---
        response_json: Optional[Any] = None
        try:
            response_json = response.json()
        except ValueError:
            # Not all endpoints return JSON (shouldn't happen for our config)
            logger.debug("%s: response is not JSON", name)

        # --- Step 4: Run validation ---
        validation_cfg  = endpoint.get("validation", {})
        expected_status = endpoint.get("expected_status", 200)

        val_result = run_all_validations(
            actual_status   = response.status_code,
            response_json   = response_json,
            validation_config = validation_cfg,
            expected_status = expected_status,
        )

        result["is_valid"] = val_result.passed

        if not val_result.passed:
            # Override to DOWN if validation failed even if server replied 200
            result["status"]        = "DOWN"
            result["error_message"] = val_result.summary()

        logger.info(
            "%-45s | %s | %6.0f ms | HTTP %s | Valid: %s",
            name, result["status"], elapsed_ms,
            response.status_code, val_result.passed
        )

    except requests.exceptions.Timeout:
        result["error_message"] = f"Request timed out after {timeout}s"
        logger.error("%s: TIMEOUT", name)

    except requests.exceptions.ConnectionError as exc:
        result["error_message"] = f"Connection error: {exc}"
        logger.error("%s: CONNECTION ERROR — %s", name, exc)

    except Exception as exc:
        result["error_message"] = f"Unexpected error: {exc}"
        logger.error("%s: UNEXPECTED ERROR — %s", name, exc)

    return result


# ---------------------------------------------------------------------------
# One full monitoring cycle (all endpoints, run concurrently)
# ---------------------------------------------------------------------------

def run_monitoring_cycle(
    endpoints:    List[Dict],
    timeout:      int,
    alert_config: Dict,
    db_path:      str,
) -> None:
    """
    Check all configured endpoints, save results, and fire alerts as needed.

    Uses Python threads so all endpoints are checked simultaneously,
    keeping the cycle time close to the slowest single endpoint.

    Args:
        endpoints:    List of endpoint dicts from config.yaml.
        timeout:      HTTP request timeout in seconds.
        alert_config: Dict from config.yaml['alerts'].
        db_path:      Path to SQLite database file.
    """
    threads: List[threading.Thread] = []
    results: List[Dict] = []
    results_lock = threading.Lock()

    def _check_and_collect(ep: Dict) -> None:
        """Thread worker: check one endpoint and append result."""
        res = check_endpoint(ep, timeout)
        with results_lock:
            results.append(res)

    # Spawn one thread per endpoint (all checks run in parallel)
    for ep in endpoints:
        t = threading.Thread(target=_check_and_collect, args=(ep,), daemon=True)
        threads.append(t)
        t.start()

    # Wait for all threads to finish
    for t in threads:
        t.join()

    # Process results: save to DB, alert on failure, update in-memory cache
    for res in results:
        # Persist to SQLite
        save_result(db_path, res)

        # Update in-memory cache for the dashboard
        with _results_lock:
            _latest_results[res["endpoint_name"]] = res

        # Fire alert if endpoint is not UP
        if res["status"] != "UP":
            dispatch_alert(
                endpoint_name = res["endpoint_name"],
                status        = res["status"],
                details       = res.get("error_message") or "No details available",
                alert_config  = alert_config,
            )


# ---------------------------------------------------------------------------
# Background monitoring loop (runs in a daemon thread)
# ---------------------------------------------------------------------------

def start_monitoring_loop(config: Dict[str, Any]) -> None:
    """
    Entry point for the continuous background monitoring loop.

    Called once at startup; runs forever until the process exits.
    Designed to be run inside a daemon thread so Flask can co-exist.

    Args:
        config: Full parsed config dict from load_config().
    """
    settings     = config.get("settings", {})
    interval     = settings.get("check_interval_seconds", 60)
    timeout      = settings.get("request_timeout_seconds", 10)
    endpoints    = config.get("endpoints", [])
    alert_config = config.get("alerts", {})
    db_path      = config.get("database", {}).get("path", "monitoring.db")

    logger.info(
        "Monitoring loop started — %d endpoints, interval=%ds, timeout=%ds",
        len(endpoints), interval, timeout
    )

    while True:
        cycle_start = time.perf_counter()

        logger.info("--- Starting monitoring cycle @ %s ---", datetime.utcnow().isoformat())

        run_monitoring_cycle(
            endpoints    = endpoints,
            timeout      = timeout,
            alert_config = alert_config,
            db_path      = db_path,
        )

        cycle_duration = time.perf_counter() - cycle_start
        # Sleep only the REMAINING interval time after the cycle completes
        sleep_time = max(0, interval - cycle_duration)

        logger.info(
            "--- Cycle complete (%.1fs). Next check in %.0fs ---",
            cycle_duration, sleep_time
        )
        time.sleep(sleep_time)
