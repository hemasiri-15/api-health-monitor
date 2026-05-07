"""
=============================================================================
main.py - Application Entry Point
=============================================================================
"""

import argparse
import logging
import sys
import threading

import database
from monitor import load_config, start_monitoring_loop
from database import initialize_database
from dashboard import run_dashboard


def configure_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-20s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


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
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print historical summary report and exit"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Step 1 — Logging
    configure_logging("INFO")
    logger = logging.getLogger("main")

    logger.info("=" * 60)
    logger.info("  API Health Check Monitor  —  Starting up")
    logger.info("=" * 60)

    # Step 2 — Load config.yaml
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logging.error(
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

    # Step 4 — Handle --report flag
    if args.report:
        print("\n📊 API Health Monitor — Historical Report")
        print("=" * 55)
        stats = database.get_uptime_stats(db_path)
        if not stats:
            print("No data yet. Run 'python main.py' first to collect data.")
        else:
            for s in stats:
                bar = "█" * int(s['uptime_pct'] / 5) + "░" * (20 - int(s['uptime_pct'] / 5))
                print(f"\n  {s['endpoint_name']}")
                print(f"  [{bar}] {s['uptime_pct']}% uptime")
                print(f"  Avg response: {s['avg_response_ms']} ms | Total checks: {s['total_checks']}")
        print()
        sys.exit(0)

    # Step 5 — Start monitoring loop in a background daemon thread
    monitor_thread = threading.Thread(
        target=start_monitoring_loop,
        args=(config,),
        name="MonitorLoop",
        daemon=True,
    )
    monitor_thread.start()
    logger.info("Monitoring thread started (daemon=True).")

    # Step 6 — Start Flask dashboard (BLOCKING — runs until Ctrl+C)
    dash_cfg = config.get("dashboard", {})
    port = dash_cfg.get("port", 5000)
    logger.info("Dashboard → http://localhost:%d  (press Ctrl+C to stop)", port)

    try:
        run_dashboard(config)
    except KeyboardInterrupt:
        logger.info("Shutdown requested — goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
