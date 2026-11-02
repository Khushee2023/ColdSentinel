import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "coldsentinel.db"

COLUMNS = ["unit_id", "timestamp", "temp_c", "score", "status",
           "severity", "eta_min", "reason", "message"]


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                temp_c REAL,
                score REAL,
                status TEXT,
                severity TEXT,
                eta_min INTEGER,
                reason TEXT,
                message TEXT
            )
        """)


def save_result(result: dict):
    values = [result.get(col) for col in COLUMNS]
    with _conn() as c:
        c.execute(
            f"INSERT INTO readings ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
            values,
        )


def latest_per_unit():
    """Most recent reading for each unit."""
    with _conn() as c:
        rows = c.execute("""
            SELECT * FROM readings
            WHERE id IN (SELECT MAX(id) FROM readings GROUP BY unit_id)
            ORDER BY unit_id
        """).fetchall()
    return [dict(r) for r in rows]


def recent_alerts(limit=20):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM readings WHERE status = 'alert' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def history(unit_id, limit=60):
    """Last N readings for one unit, oldest first (for charts)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM readings WHERE unit_id = ? ORDER BY id DESC LIMIT ?",
            (unit_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear():
    with _conn() as c:
        c.execute("DELETE FROM readings")