"""
=============================================================================
database.py - Historical Logging Module
=============================================================================
Responsibility:
    - Initialize and manage the SQLite database.
    - Provide functions to INSERT monitoring results and QUERY historical data.
    - Used by: monitor.py (write), dashboard.py (read)
=============================================================================
"""

import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Create and return a SQLite connection with row_factory set so
    rows behave like dictionaries (column_name -> value).

    Args:
        db_path: File path to the SQLite database (e.g., 'monitoring.db')

    Returns:
        sqlite3.Connection object
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # row_factory lets us access columns by name: row["status"] instead of row[2]
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: str) -> None:
    """
    Create the monitoring_results table if it does not already exist.
    This is called once at application startup.

    Table schema:
        id             - Auto-increment primary key
        endpoint_name  - Human-readable name from config.yaml
        url            - The full URL that was checked
        timestamp      - ISO-8601 datetime string of when the check ran
        status         - 'UP', 'DOWN', or 'DEGRADED'
        http_code      - Actual HTTP status code received (or 0 on timeout)
        response_time  - Response duration in milliseconds (float)
        error_message  - Null on success; description of failure otherwise
        is_valid       - 1 if response validation passed, 0 otherwise

    Args:
        db_path: File path to the SQLite database
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_name   TEXT    NOT NULL,
                url             TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL,
                status          TEXT    NOT NULL,
                http_code       INTEGER,
                response_time   REAL,
                error_message   TEXT,
                is_valid        INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        logger.info("Database initialized at: %s", db_path)
    finally:
        conn.close()


def save_result(db_path: str, result: Dict[str, Any]) -> None:
    """
    Insert a single monitoring check result into the database.

    Args:
        db_path: File path to the SQLite database
        result:  Dictionary with keys:
                   endpoint_name, url, timestamp, status,
                   http_code, response_time, error_message, is_valid
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_results
                (endpoint_name, url, timestamp, status, http_code,
                 response_time, error_message, is_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.get("endpoint_name"),
            result.get("url"),
            result.get("timestamp", datetime.utcnow().isoformat()),
            result.get("status"),
            result.get("http_code"),
            result.get("response_time"),
            result.get("error_message"),
            int(result.get("is_valid", True)),
        ))
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("DB write error: %s", exc)
    finally:
        conn.close()


def get_recent_results(db_path: str, limit: int = 200) -> List[Dict]:
    """
    Fetch the most recent monitoring records across all endpoints.

    Args:
        db_path: File path to the SQLite database
        limit:   Maximum number of rows to return (default 200)

    Returns:
        List of dicts, newest first.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM monitoring_results
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        # Convert sqlite3.Row objects to plain dicts for JSON serialization
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_uptime_stats(db_path: str) -> List[Dict]:
    """
    Calculate per-endpoint uptime percentage, average response time,
    and total check counts from ALL historical records.

    Returns:
        List of dicts with keys:
            endpoint_name, total_checks, up_count, uptime_pct, avg_response_ms
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                endpoint_name,
                COUNT(*)                                    AS total_checks,
                SUM(CASE WHEN status = 'UP' THEN 1 ELSE 0 END) AS up_count,
                ROUND(
                    100.0 * SUM(CASE WHEN status = 'UP' THEN 1 ELSE 0 END) / COUNT(*),
                    2
                )                                           AS uptime_pct,
                ROUND(AVG(response_time), 2)                AS avg_response_ms
            FROM monitoring_results
            GROUP BY endpoint_name
            ORDER BY endpoint_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_latest_per_endpoint(db_path: str) -> List[Dict]:
    """
    Return only the LATEST check result for every unique endpoint.
    Used by the dashboard to show 'current status' cards.

    Returns:
        List of dicts, one per endpoint, with the most recent record.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM monitoring_results
            WHERE id IN (
                SELECT MAX(id) FROM monitoring_results GROUP BY endpoint_name
            )
            ORDER BY endpoint_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_response_time_history(db_path: str, endpoint_name: str, limit: int = 50) -> List[Dict]:
    """
    Return recent response times for a specific endpoint (for sparklines/charts).

    Args:
        db_path:       File path to the SQLite database
        endpoint_name: Name of the endpoint to query
        limit:         Number of data points to return

    Returns:
        List of dicts with 'timestamp' and 'response_time' keys, oldest first.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, response_time, status
            FROM monitoring_results
            WHERE endpoint_name = ?
            ORDER BY id DESC
            LIMIT ?
        """, (endpoint_name, limit))
        rows = [dict(row) for row in cursor.fetchall()]
        return list(reversed(rows))  # Return in chronological order
    finally:
        conn.close()
