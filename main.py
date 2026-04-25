"""
=============================================================================
main.py - Application Entry Point
=============================================================================
Usage:
    python main.py                      # Uses default config.yaml
    python main.py --config myconf.yaml # Use custom config path

What this file does:
    1. Sets up structured logging.
    2. Loads config.yaml.
    3. Initialises the SQLite database.
    4. Starts the monitoring loop in a background daemon thread.
    5. Starts the Flask dashboard in the main thread.

The two components run concurrently:
    - Background thread: polls endpoints every N seconds, writes to DB.
    - Main thread (Flask): serves the web dashboard, reads from DB.
=============================================================================
"""

import argparse
import logging
import sys
import threading

from monitor import load_config, start_monitoring_loop
from database import initialize_database
from dashboard import run_dashboard


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def configure_logging(level_name: str = "INFO") -> None:
    """
    Configure root logger with a readable format.

    We send everything to stdout so it's easy to read in the terminal
    while the dashboard is running.

    Args:
        level_name: Logging level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
    """
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-20s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="API Health Check Monitor — start monitoring + dashboard"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)"
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Application entry point.

    Orchestration order:
        1. Parse CLI args → find config file.
        2. Configure logging.
        3. Load config.yaml.
        4. Initialise SQLite DB (creates table if not present).
        5. Launch monitor loop in a daemon thread.
        6. Launch Flask dashboard on the main thread (blocking).
    """
    args = parse_args()

    # Step 1 — Logging
    # We read log_level from config later, but we need basic logging NOW
    # to log config-loading errors. Default to INFO initially.
    configure_logging("INFO")
    logger = logging.getLogger("main")

    logger.info("=" * 60)
    logger.info("  API Health Check Monitor  —  Starting up")
    logger.info("=" * 60)

    # Step 2 — Load config.yaml
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error(
            "Config file '%s' not found. "
            "Make sure config.yaml is in the same directory as main.py.",
            args.config
        )
        sys.exit(1)

    # Re-configure logging with the level from config.yaml
    log_level = config.get("settings", {}).get("log_level", "INFO")
    configure_logging(log_level)

    # Step 3 — Initialise database
    db_path = config.get("database", {}).get("path", "monitoring.db")
    initialize_database(db_path)

    # Step 4 — Start monitoring loop in a background daemon thread
    # daemon=True means this thread automatically dies when the main
    # thread (Flask) exits — no cleanup needed.
    monitor_thread = threading.Thread(
        target=start_monitoring_loop,
        args=(config,),
        name="MonitorLoop",
        daemon=True,
    )
    monitor_thread.start()
    logger.info("Monitoring thread started (daemon=True).")

    # Step 5 — Start Flask dashboard (BLOCKING — runs until Ctrl+C)
    dash_cfg = config.get("dashboard", {})
    port     = dash_cfg.get("port", 5000)
    logger.info("Dashboard → http://localhost:%d  (press Ctrl+C to stop)", port)

    try:
        run_dashboard(config)
    except KeyboardInterrupt:
        logger.info("Shutdown requested — goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
