#Syed
# group_1_storage.py
import sqlite3
import json
from contextlib import contextmanager

# Updated schema to match admin_server expectations exactly
SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT NOT NULL,
    location TEXT,
    core_temp REAL,
    packet_id INTEGER,
    valid INTEGER,
    schema_ok INTEGER,
    qos INTEGER,
    topic TEXT,
    raw_data TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_device ON messages(device_id);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT,
    kind TEXT NOT NULL,
    details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anomalies_ts ON anomalies(ts);

CREATE TABLE IF NOT EXISTS statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT,
    location TEXT,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_statuses_device ON statuses(device_id);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    action TEXT NOT NULL,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_device ON schedules(device_id);

CREATE TABLE IF NOT EXISTS service_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT,
    topic TEXT,
    qos INTEGER,
    schema_ok INTEGER,
    log_message TEXT,
    anomaly_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_service_logs_ts ON service_logs(ts);
"""

@contextmanager
def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=15, isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()

def init_db(db_path):
    with connect(db_path) as c:
        c.executescript(SCHEMA)

# Insert functions
def insert_message(db_path, ts, device_id, location, core_temp, packet_id, valid, schema_ok, qos, topic, raw_data):
    with connect(db_path) as c:
        c.execute("""
            INSERT INTO messages (ts, device_id, location, core_temp, packet_id, valid, schema_ok, qos, topic, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ts, device_id, location, core_temp, packet_id, valid, schema_ok, qos, topic, json.dumps(raw_data)))

def insert_anomaly(db_path, ts, device_id, kind, details):
    with connect(db_path) as c:
        c.execute("""
            INSERT INTO anomalies (ts, device_id, kind, details)
            VALUES (?, ?, ?, ?)
        """, (ts, device_id, kind, details))

def insert_status(db_path, ts, device_id, location, status):
    with connect(db_path) as c:
        c.execute("""
            INSERT INTO statuses (ts, device_id, location, status)
            VALUES (?, ?, ?, ?)
        """, (ts, device_id, location, status))

def insert_service_log(db_path, ts, device_id, topic, qos, schema_ok, log_message, anomaly_type=None):
    with connect(db_path) as c:
        c.execute("""
            INSERT INTO service_logs (ts, device_id, topic, qos, schema_ok, log_message, anomaly_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ts, device_id, topic, qos, schema_ok, log_message, anomaly_type))

# Queries
def list_devices(db_path):
    with connect(db_path) as c:
        rows = c.execute("""
            SELECT s.device_id, s.location, s.status, s.ts
            FROM statuses s
            JOIN (
                SELECT device_id, MAX(ts) AS mts
                FROM statuses
                GROUP BY device_id
            ) t ON s.device_id = t.device_id AND s.ts = t.mts
            ORDER BY s.device_id
        """).fetchall()
    return [{"device_id": r[0], "location": r[1], "status": r[2], "ts": r[3]} for r in rows]

def query_messages(db_path, device_id=None, since=None, until=None, limit=500):
    q = """
        SELECT device_id, ts, location, core_temp, packet_id, valid, schema_ok, qos, topic, raw_data
        FROM messages
        WHERE 1=1
    """
    params = []
    if device_id:
        q += " AND device_id=?"; params.append(device_id)
    if since is not None:
        q += " AND ts>=?"; params.append(since)
    if until is not None:
        q += " AND ts<=?"; params.append(until)
    q += " ORDER BY ts DESC LIMIT ?"; params.append(limit)

    with connect(db_path) as c:
        rows = c.execute(q, params).fetchall()

    return [
        {
            "device_id": r[0],
            "ts": r[1],
            "location": r[2],
            "core_temp": r[3],
            "packet_id": r[4],
            "valid": r[5],
            "schema_ok": bool(r[6]),
            "qos": r[7],
            "topic": r[8],
            "raw_data": r[9]
        }
        for r in rows
    ]

def list_anomalies(db_path, limit=10):
    with connect(db_path) as c:
        rows = c.execute("""
            SELECT ts, device_id, kind, details
            FROM anomalies
            ORDER BY ts DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [{"ts": r[0], "device_id": r[1], "kind": r[2], "details": r[3]} for r in rows]

def aggregate_stats(db_path, device_id=None, since=None, until=None):
    q = "SELECT COUNT(*), AVG(core_temp), MIN(core_temp), MAX(core_temp) FROM messages WHERE schema_ok=1"
    params = []
    if device_id:
        q += " AND device_id=?"; params.append(device_id)
    if since is not None:
        q += " AND ts>=?"; params.append(since)
    if until is not None:
        q += " AND ts<=?"; params.append(until)
    with connect(db_path) as c:
        m = c.execute(q, params).fetchone()

        aq = "SELECT COUNT(*) FROM anomalies WHERE 1=1"
        aparams = []
        if device_id:
            aq += " AND device_id=?"; aparams.append(device_id)
        if since is not None:
            aq += " AND ts>=?"; aparams.append(since)
        if until is not None:
            aq += " AND ts<=?"; aparams.append(until)
        a = c.execute(aq, aparams).fetchone()[0]

    return {
        "count": m[0] or 0,
        "avg": m[1],
        "min": m[2],
        "max": m[3],
        "anomalies": a
    }

def upsert_schedule(db_path, device_id, action, start_ts, end_ts):
    with connect(db_path) as c:
        c.execute("""
            INSERT INTO schedules (device_id, action, start_ts, end_ts)
            VALUES (?, ?, ?, ?)
        """, (device_id, action, start_ts, end_ts))

def get_schedules(db_path, device_id=None, active_only=False, now_ts=None):
    q = "SELECT id, device_id, action, start_ts, end_ts FROM schedules WHERE 1=1"
    params = []
    if device_id:
        q += " AND device_id=?"; params.append(device_id)
    if active_only and now_ts is not None:
        q += " AND start_ts<=? AND end_ts>=?"; params.extend([now_ts, now_ts])
    q += " ORDER BY start_ts DESC"

    with connect(db_path) as c:
        rows = c.execute(q, params).fetchall()

    return [{"id": r[0], "device_id": r[1], "action": r[2], "start_ts": r[3], "end_ts": r[4]} for r in rows]
