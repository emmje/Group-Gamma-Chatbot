"""Database layer for users, chat history, and analytics.

Uses PostgreSQL (via DATABASE_URL) when available — required for Render /
production.  Falls back to SQLite for local development when no DATABASE_URL
is set.
"""

import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

_USE_POSTGRES = bool(DATABASE_URL and psycopg is not None)

# SQLite path (only used when Postgres is not available)
_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "gamma.db"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _pg_conn():
    """Return a new psycopg connection with dict rows."""
    kw = {"row_factory": dict_row}
    if "sslmode=" not in DATABASE_URL.lower():
        kw["sslmode"] = "require"
    return psycopg.connect(DATABASE_URL, **kw)


def _sqlite_conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chats (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chats_user_created ON chats(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chats_created ON chats(created_at);

CREATE TABLE IF NOT EXISTS data_deletion_requests (
    id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    whatsapp_number TEXT,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS interaction_events (
    id BIGSERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    user_ref TEXT,
    question_text TEXT,
    answer_text TEXT,
    source_language TEXT NOT NULL DEFAULT 'eng',
    translated_inbound INTEGER NOT NULL DEFAULT 0,
    translated_outbound INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL,
    error_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ie_created ON interaction_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ie_channel_created ON interaction_events(channel, created_at);
CREATE INDEX IF NOT EXISTS idx_ie_success_created ON interaction_events(success, created_at);
"""

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS data_deletion_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    whatsapp_number TEXT,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS interaction_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    user_ref TEXT,
    question_text TEXT,
    answer_text TEXT,
    source_language TEXT NOT NULL DEFAULT 'eng',
    translated_inbound INTEGER NOT NULL DEFAULT 0,
    translated_outbound INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL,
    error_type TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ie_created ON interaction_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ie_channel_created ON interaction_events(channel, created_at);
CREATE INDEX IF NOT EXISTS idx_ie_success_created ON interaction_events(success, created_at);
"""


def init_db():
    """Create tables if they don't exist."""
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_PG_SCHEMA)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
        conn.close()

    _bootstrap_admin()


# ---------------------------------------------------------------------------
# Bootstrap admin (Render first-deploy convenience)
# ---------------------------------------------------------------------------

def _bootstrap_admin():
    """Create an admin account from env vars if the users table is empty."""
    username = (os.getenv("GAMMA_BOOTSTRAP_ADMIN_USERNAME") or "").strip()
    password = (os.getenv("GAMMA_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not username or not password:
        return

    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM users")
                if (cur.fetchone() or {}).get("cnt", 0) > 0:
                    return
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
                    (username, generate_password_hash(password)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count > 0:
                return
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, generate_password_hash(password)),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(username, password, role="student"):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
                    (username, generate_password_hash(password), role),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"] if row else None
        except Exception:
            conn.rollback()
            return None
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()


def verify_user(username, password):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
            if row and check_password_hash(row["password_hash"], password):
                return dict(row)
            return None
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            return dict(row)
        return None


def get_user_by_id(user_id):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

def save_chat(user_id, question, answer):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chats (user_id, question, answer) VALUES (%s, %s, %s) RETURNING id",
                    (user_id, question, answer),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"] if row else None
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        cur = conn.execute(
            "INSERT INTO chats (user_id, question, answer) VALUES (?, ?, ?)",
            (user_id, question, answer),
        )
        conn.commit()
        chat_id = cur.lastrowid
        conn.close()
        return chat_id


def get_user_chats(user_id, limit=50):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT question, answer, created_at FROM chats WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit),
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        rows = conn.execute(
            "SELECT question, answer, created_at FROM chats WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Aggregate helpers (used by old-style dashboard and new analytics)
# ---------------------------------------------------------------------------

def get_total_users():
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM users")
                return (cur.fetchone() or {}).get("cnt", 0)
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return count


def get_total_chats():
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM chats")
                return (cur.fetchone() or {}).get("cnt", 0)
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        count = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        conn.close()
        return count


def get_frequent_questions(limit=10):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT question, COUNT(*) AS count FROM chats GROUP BY question ORDER BY count DESC LIMIT %s",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        rows = conn.execute(
            "SELECT question, COUNT(*) as count FROM chats GROUP BY question ORDER BY count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_recent_chats(limit=20):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT c.question, c.answer, c.created_at, u.username
                       FROM chats c JOIN users u ON c.user_id = u.id
                       ORDER BY c.created_at DESC LIMIT %s""",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        rows = conn.execute(
            """SELECT c.question, c.answer, c.created_at, u.username
               FROM chats c JOIN users u ON c.user_id = u.id
               ORDER BY c.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_chats_per_day(days=14):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT created_at::date AS day, COUNT(*) AS count
                       FROM chats WHERE created_at >= NOW() - make_interval(days => %s)
                       GROUP BY day ORDER BY day""",
                    (days,),
                )
                return [{"day": str(r["day"]), "count": r["count"]} for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        rows = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as count
               FROM chats WHERE created_at >= datetime('now', ?)
               GROUP BY day ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_avg_answer_length():
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT AVG(LENGTH(answer)) AS avg_len FROM chats")
                row = cur.fetchone()
                val = (row or {}).get("avg_len")
                return round(float(val), 1) if val else 0.0
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        result = conn.execute("SELECT AVG(LENGTH(answer)) FROM chats").fetchone()[0]
        conn.close()
        return round(result, 1) if result else 0.0


# ---------------------------------------------------------------------------
# Data deletion requests
# ---------------------------------------------------------------------------

def create_data_deletion_request(full_name, contact_email, whatsapp_number="", details=""):
    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO data_deletion_requests (full_name, contact_email, whatsapp_number, details)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (full_name, contact_email, whatsapp_number, details),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"] if row else None
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        cur = conn.execute(
            """INSERT INTO data_deletion_requests (full_name, contact_email, whatsapp_number, details)
               VALUES (?, ?, ?, ?)""",
            (full_name, contact_email, whatsapp_number, details),
        )
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        return rid


# ---------------------------------------------------------------------------
# Interaction analytics
# ---------------------------------------------------------------------------

def record_interaction(
    channel,
    user_ref="",
    question_text="",
    answer_text="",
    source_language="eng",
    translated_inbound=False,
    translated_outbound=False,
    success=True,
    fallback_used=False,
    latency_ms=None,
    error_type="",
):
    q = (question_text or "").strip()[:1000]
    a = (answer_text or "").strip()[:4000]

    params = (
        (channel or "unknown").strip() or "unknown",
        (user_ref or "").strip(),
        q,
        a,
        (source_language or "eng").strip() or "eng",
        1 if translated_inbound else 0,
        1 if translated_outbound else 0,
        1 if success else 0,
        1 if fallback_used else 0,
        float(latency_ms) if latency_ms is not None else None,
        (error_type or "").strip(),
    )

    if _USE_POSTGRES:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO interaction_events
                       (channel, user_ref, question_text, answer_text, source_language,
                        translated_inbound, translated_outbound, success, fallback_used,
                        latency_ms, error_type)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    params,
                )
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        conn.execute(
            """INSERT INTO interaction_events
               (channel, user_ref, question_text, answer_text, source_language,
                translated_inbound, translated_outbound, success, fallback_used,
                latency_ms, error_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            params,
        )
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Dashboard metrics snapshot
# ---------------------------------------------------------------------------

def _percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(ordered[int(rank)], 1)
    value = ordered[low] + (ordered[high] - ordered[low]) * (rank - low)
    return round(value, 1)


def _safe_pct(part, total):
    if not total:
        return 0.0
    return round((part / total) * 100.0, 2)


def _row_val(row, key):
    """Extract a value from either a dict or a sqlite3.Row."""
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def get_dashboard_metrics_snapshot(days=14, hours=24, top_n=8):
    if _USE_POSTGRES:
        return _dashboard_pg(days, hours, top_n)
    return _dashboard_sqlite(days, hours, top_n)


def _dashboard_pg(days, hours, top_n):
    conn = _pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM interaction_events")
            total_interactions = (cur.fetchone() or {}).get("cnt", 0)

            cur.execute(
                """SELECT COUNT(*) AS interactions,
                          SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success_count,
                          SUM(CASE WHEN fallback_used=1 THEN 1 ELSE 0 END) AS fallback_count,
                          COUNT(DISTINCT CASE WHEN TRIM(COALESCE(user_ref,''))!='' THEN user_ref END) AS active_users,
                          AVG(CASE WHEN answer_text IS NOT NULL THEN LENGTH(answer_text) END) AS avg_answer_len
                   FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(hours => %s)""",
                (hours,),
            )
            w = cur.fetchone() or {}

            cur.execute(
                """SELECT latency_ms FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(hours => %s) AND latency_ms IS NOT NULL""",
                (hours,),
            )
            latencies = [r["latency_ms"] for r in cur.fetchall() if r.get("latency_ms") is not None]

            cur.execute(
                """SELECT channel, COUNT(*) AS count FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(days => %s)
                   GROUP BY channel ORDER BY count DESC""",
                (days,),
            )
            channel_rows = cur.fetchall()

            cur.execute(
                """SELECT source_language, COUNT(*) AS count FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(days => %s)
                     AND TRIM(COALESCE(source_language,''))!=''
                   GROUP BY source_language ORDER BY count DESC LIMIT 10""",
                (days,),
            )
            language_rows = cur.fetchall()

            cur.execute(
                """SELECT created_at::date AS day, COUNT(*) AS count FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(days => %s)
                   GROUP BY day ORDER BY day""",
                (days,),
            )
            daily_rows = cur.fetchall()

            cur.execute(
                """SELECT TO_CHAR(created_at, 'YYYY-MM-DD HH24:00') AS hour, COUNT(*) AS count
                   FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(hours => %s)
                   GROUP BY hour ORDER BY hour""",
                (hours,),
            )
            hourly_rows = cur.fetchall()

            cur.execute(
                """SELECT MIN(TRIM(question_text)) AS question, COUNT(*) AS count
                   FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(days => %s)
                     AND TRIM(COALESCE(question_text,''))!=''
                   GROUP BY LOWER(TRIM(question_text))
                   ORDER BY count DESC LIMIT %s""",
                (days, top_n),
            )
            top_q_rows = cur.fetchall()

            cur.execute(
                """SELECT COALESCE(NULLIF(TRIM(error_type),''),'unknown') AS error_type, COUNT(*) AS count
                   FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(days => %s) AND success=0
                   GROUP BY error_type ORDER BY count DESC LIMIT 8""",
                (days,),
            )
            error_rows = cur.fetchall()

            cur.execute(
                """SELECT created_at, channel, error_type, question_text, latency_ms
                   FROM interaction_events
                   WHERE created_at >= NOW() - make_interval(days => %s) AND success=0
                   ORDER BY created_at DESC LIMIT 12""",
                (days,),
            )
            incident_rows = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM interaction_events WHERE created_at >= NOW() - INTERVAL '15 minutes'"
            )
            pulse = (cur.fetchone() or {}).get("cnt", 0)

        interactions_h = int(w.get("interactions") or 0)
        success_h = int(w.get("success_count") or 0)
        fallback_h = int(w.get("fallback_count") or 0)
        active_users_h = int(w.get("active_users") or 0)
        avg_ans_len = round(float(w.get("avg_answer_len") or 0), 1)

        return _build_snapshot(
            total_interactions, interactions_h, success_h, fallback_h,
            active_users_h, avg_ans_len, latencies, pulse,
            channel_rows, language_rows, daily_rows, hourly_rows,
            top_q_rows, error_rows, incident_rows,
        )
    finally:
        conn.close()


def _dashboard_sqlite(days, hours, top_n):
    day_window = f"-{int(days)} days"
    hour_window = f"-{int(hours)} hours"

    conn = _sqlite_conn()

    total_interactions = conn.execute("SELECT COUNT(*) FROM interaction_events").fetchone()[0]

    w = conn.execute(
        """SELECT COUNT(*) AS interactions,
                  SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success_count,
                  SUM(CASE WHEN fallback_used=1 THEN 1 ELSE 0 END) AS fallback_count,
                  COUNT(DISTINCT CASE WHEN TRIM(COALESCE(user_ref,''))!='' THEN user_ref END) AS active_users,
                  AVG(CASE WHEN answer_text IS NOT NULL THEN LENGTH(answer_text) END) AS avg_answer_len
           FROM interaction_events WHERE created_at >= datetime('now', ?)""",
        (hour_window,),
    ).fetchone()

    lat_rows = conn.execute(
        "SELECT latency_ms FROM interaction_events WHERE created_at >= datetime('now', ?) AND latency_ms IS NOT NULL",
        (hour_window,),
    ).fetchall()
    latencies = [r[0] for r in lat_rows if r[0] is not None]

    channel_rows = conn.execute(
        "SELECT channel, COUNT(*) AS count FROM interaction_events WHERE created_at >= datetime('now', ?) GROUP BY channel ORDER BY count DESC",
        (day_window,),
    ).fetchall()

    language_rows = conn.execute(
        "SELECT source_language, COUNT(*) AS count FROM interaction_events WHERE created_at >= datetime('now', ?) AND TRIM(COALESCE(source_language,''))!='' GROUP BY source_language ORDER BY count DESC LIMIT 10",
        (day_window,),
    ).fetchall()

    daily_rows = conn.execute(
        "SELECT DATE(created_at) AS day, COUNT(*) AS count FROM interaction_events WHERE created_at >= datetime('now', ?) GROUP BY day ORDER BY day",
        (day_window,),
    ).fetchall()

    hourly_rows = conn.execute(
        "SELECT strftime('%%Y-%%m-%%d %%H:00', created_at) AS hour, COUNT(*) AS count FROM interaction_events WHERE created_at >= datetime('now', ?) GROUP BY hour ORDER BY hour",
        (hour_window,),
    ).fetchall()

    top_q_rows = conn.execute(
        "SELECT MIN(TRIM(question_text)) AS question, COUNT(*) AS count FROM interaction_events WHERE created_at >= datetime('now', ?) AND TRIM(COALESCE(question_text,''))!='' GROUP BY LOWER(TRIM(question_text)) ORDER BY count DESC LIMIT ?",
        (day_window, int(top_n)),
    ).fetchall()

    error_rows = conn.execute(
        "SELECT COALESCE(NULLIF(TRIM(error_type),''),'unknown') AS error_type, COUNT(*) AS count FROM interaction_events WHERE created_at >= datetime('now', ?) AND success=0 GROUP BY error_type ORDER BY count DESC LIMIT 8",
        (day_window,),
    ).fetchall()

    incident_rows = conn.execute(
        "SELECT created_at, channel, error_type, question_text, latency_ms FROM interaction_events WHERE created_at >= datetime('now', ?) AND success=0 ORDER BY created_at DESC LIMIT 12",
        (day_window,),
    ).fetchall()

    pulse = conn.execute(
        "SELECT COUNT(*) FROM interaction_events WHERE created_at >= datetime('now', '-15 minutes')"
    ).fetchone()[0]

    conn.close()

    interactions_h = int(w["interactions"] or 0)
    success_h = int(w["success_count"] or 0)
    fallback_h = int(w["fallback_count"] or 0)
    active_users_h = int(w["active_users"] or 0)
    avg_ans_len = round(float(w["avg_answer_len"] or 0), 1)

    return _build_snapshot(
        total_interactions, interactions_h, success_h, fallback_h,
        active_users_h, avg_ans_len, latencies, pulse,
        [dict(r) for r in channel_rows],
        [dict(r) for r in language_rows],
        [dict(r) for r in daily_rows],
        [dict(r) for r in hourly_rows],
        [dict(r) for r in top_q_rows],
        [dict(r) for r in error_rows],
        [dict(r) for r in incident_rows],
    )


def _build_snapshot(
    total_interactions, interactions_h, success_h, fallback_h,
    active_users_h, avg_ans_len, latencies, pulse_15m,
    channel_rows, language_rows, daily_rows, hourly_rows,
    top_q_rows, error_rows, incident_rows,
):
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "kpis": {
            "total_interactions": int(total_interactions or 0),
            "interactions_24h": interactions_h,
            "active_users_24h": active_users_h,
            "success_rate_24h": _safe_pct(success_h, interactions_h),
            "fallback_rate_24h": _safe_pct(fallback_h, interactions_h),
            "avg_answer_len_24h": avg_ans_len,
            "median_latency_ms_24h": _percentile(latencies, 0.50),
            "p95_latency_ms_24h": _percentile(latencies, 0.95),
            "events_per_min_15m": round(int(pulse_15m or 0) / 15.0, 2),
        },
        "channels": [
            {"channel": _row_val(r, "channel"), "count": int(_row_val(r, "count") or 0)}
            for r in channel_rows
        ],
        "languages": [
            {"language": _row_val(r, "source_language"), "count": int(_row_val(r, "count") or 0)}
            for r in language_rows
        ],
        "daily_volume": [
            {"day": str(_row_val(r, "day")), "count": int(_row_val(r, "count") or 0)}
            for r in daily_rows
        ],
        "hourly_volume": [
            {"hour": _row_val(r, "hour"), "count": int(_row_val(r, "count") or 0)}
            for r in hourly_rows
        ],
        "top_questions": [
            {"question": (_row_val(r, "question") or "(empty)")[:120], "count": int(_row_val(r, "count") or 0)}
            for r in top_q_rows
        ],
        "error_breakdown": [
            {"error_type": _row_val(r, "error_type"), "count": int(_row_val(r, "count") or 0)}
            for r in error_rows
        ],
        "recent_incidents": [
            {
                "created_at": str(_row_val(r, "created_at") or ""),
                "channel": _row_val(r, "channel"),
                "error_type": _row_val(r, "error_type") or "unknown",
                "question": (_row_val(r, "question_text") or "")[:120],
                "latency_ms": round(float(_row_val(r, "latency_ms") or 0), 1),
            }
            for r in incident_rows
        ],
    }
