
import sqlite3
import os
import time
from typing import Any, Optional, Dict

DB_PATH = os.getenv("CACHE_DB_PATH", "data/cache.sqlite3")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS kvstore (
    k TEXT NOT NULL,
    ts INTEGER NOT NULL,
    ttl INTEGER NOT NULL,
    v BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_k_ts ON kvstore(k, ts DESC);
"""

def _conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

CONN = _conn()
for stmt in SCHEMA.strip().split(";"):
    s = stmt.strip()
    if s:
        CONN.execute(s)

def put(key: str, value: Any, ttl: int = 120, max_rows: int = 100) -> None:
    """Store value with TTL (seconds). Keeps only last max_rows for the key."""
    now = int(time.time())
    CONN.execute("INSERT INTO kvstore(k, ts, ttl, v) VALUES(?,?,?,?)", (key, now, ttl, json_dumps(value)))
    # trim old rows
    CONN.execute("""
        DELETE FROM kvstore
        WHERE k = ? AND ts NOT IN (
            SELECT ts FROM kvstore WHERE k = ? ORDER BY ts DESC LIMIT ?
        )
    """, (key, key, max_rows))
    # purge expired (best-effort)
    purge_expired()

def get_latest(key: str) -> Optional[Any]:
    """Return latest, non-expired value for key or None."""
    now = int(time.time())
    row = CONN.execute("""
        SELECT v, ts, ttl FROM kvstore
        WHERE k = ?
        ORDER BY ts DESC
        LIMIT 1
    """, (key,)).fetchone()
    if not row:
        return None
    v, ts, ttl = row
    if ts + ttl < now:
        return None
    return json_loads(v)

def purge_expired() -> int:
    now = int(time.time())
    cur = CONN.execute("DELETE FROM kvstore WHERE ts + ttl < ?", (now,))
    return cur.rowcount

# small JSON helpers tolerant to basic types
import json as _json
def json_dumps(x: Any) -> str:
    try:
        return _json.dumps(x, separators=(',',':'), ensure_ascii=False)
    except TypeError:
        # fallback: str() for non-serializable types
        return _json.dumps(str(x))

def json_loads(s: str) -> Any:
    try:
        return _json.loads(s)
    except Exception:
        return s
