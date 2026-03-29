"""SQLite database for users, chat history, and analytics."""

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gamma.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
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
        CREATE INDEX IF NOT EXISTS idx_interaction_events_created_at
            ON interaction_events(created_at);
        CREATE INDEX IF NOT EXISTS idx_interaction_events_channel_created
            ON interaction_events(channel, created_at);
        CREATE INDEX IF NOT EXISTS idx_interaction_events_success_created
            ON interaction_events(success, created_at);
    """)
    conn.commit()
    conn.close()


def create_user(username, password, role="student"):
    conn = get_conn()
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
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def get_user_by_id(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_chat(user_id, question, answer):
    conn = get_conn()
    conn.execute(
        "INSERT INTO chats (user_id, question, answer) VALUES (?, ?, ?)",
        (user_id, question, answer),
    )
    conn.commit()
    conn.close()


def get_user_chats(user_id, limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT question, answer, created_at FROM chats WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_users():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def get_total_chats():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    conn.close()
    return count


def get_frequent_questions(limit=10):
    conn = get_conn()
    rows = conn.execute(
        "SELECT question, COUNT(*) as count FROM chats GROUP BY question ORDER BY count DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_chats(limit=20):
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.question, c.answer, c.created_at, u.username
           FROM chats c JOIN users u ON c.user_id = u.id
           ORDER BY c.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chats_per_day(days=14):
    conn = get_conn()
    rows = conn.execute(
        """SELECT DATE(created_at) as day, COUNT(*) as count
           FROM chats WHERE created_at >= datetime('now', ?)
           GROUP BY day ORDER BY day""",
        (f"-{days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_avg_answer_length():
    conn = get_conn()
    result = conn.execute("SELECT AVG(LENGTH(answer)) FROM chats").fetchone()[0]
    conn.close()
    return round(result, 1) if result else 0.0


def create_data_deletion_request(full_name, contact_email, whatsapp_number="", details=""):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO data_deletion_requests (full_name, contact_email, whatsapp_number, details)
           VALUES (?, ?, ?, ?)""",
        (full_name, contact_email, whatsapp_number, details),
    )
    conn.commit()
    request_id = cur.lastrowid
    conn.close()
    return request_id


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
    q = (question_text or "").strip()
    a = (answer_text or "").strip()
    if len(q) > 1000:
        q = q[:1000]
    if len(a) > 4000:
        a = a[:4000]

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO interaction_events (
            channel,
            user_ref,
            question_text,
            answer_text,
            source_language,
            translated_inbound,
            translated_outbound,
            success,
            fallback_used,
            latency_ms,
            error_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
        ),
    )
    conn.commit()
    conn.close()


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


def get_dashboard_metrics_snapshot(days=14, hours=24, top_n=8):
    day_window = f"-{int(days)} days"
    hour_window = f"-{int(hours)} hours"

    conn = get_conn()

    total_interactions = conn.execute(
        "SELECT COUNT(*) FROM interaction_events"
    ).fetchone()[0]

    window_row = conn.execute(
        """
        SELECT
            COUNT(*) AS interactions,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN fallback_used = 1 THEN 1 ELSE 0 END) AS fallback_count,
            COUNT(DISTINCT CASE WHEN TRIM(COALESCE(user_ref, '')) != '' THEN user_ref END) AS active_users,
            AVG(CASE WHEN answer_text IS NOT NULL THEN LENGTH(answer_text) END) AS avg_answer_len
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
        """,
        (hour_window,),
    ).fetchone()

    latency_rows = conn.execute(
        """
        SELECT latency_ms
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
          AND latency_ms IS NOT NULL
        """,
        (hour_window,),
    ).fetchall()
    latencies = [row[0] for row in latency_rows if row[0] is not None]

    channel_rows = conn.execute(
        """
        SELECT channel, COUNT(*) AS count
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
        GROUP BY channel
        ORDER BY count DESC
        """,
        (day_window,),
    ).fetchall()

    language_rows = conn.execute(
        """
        SELECT source_language, COUNT(*) AS count
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
          AND TRIM(COALESCE(source_language, '')) != ''
        GROUP BY source_language
        ORDER BY count DESC
        LIMIT 10
        """,
        (day_window,),
    ).fetchall()

    daily_rows = conn.execute(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS count
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
        GROUP BY day
        ORDER BY day
        """,
        (day_window,),
    ).fetchall()

    hourly_rows = conn.execute(
        """
        SELECT strftime('%Y-%m-%d %H:00', created_at) AS hour, COUNT(*) AS count
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
        GROUP BY hour
        ORDER BY hour
        """,
        (hour_window,),
    ).fetchall()

    top_questions_rows = conn.execute(
        """
        SELECT MIN(TRIM(question_text)) AS question, COUNT(*) AS count
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
          AND TRIM(COALESCE(question_text, '')) != ''
        GROUP BY LOWER(TRIM(question_text))
        ORDER BY count DESC
        LIMIT ?
        """,
        (day_window, int(top_n)),
    ).fetchall()

    error_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(error_type), ''), 'unknown') AS error_type, COUNT(*) AS count
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
          AND success = 0
        GROUP BY error_type
        ORDER BY count DESC
        LIMIT 8
        """,
        (day_window,),
    ).fetchall()

    recent_incidents_rows = conn.execute(
        """
        SELECT created_at, channel, error_type, question_text, latency_ms
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
          AND success = 0
        ORDER BY created_at DESC
        LIMIT 12
        """,
        (day_window,),
    ).fetchall()

    pulse_row = conn.execute(
        """
        SELECT COUNT(*) AS interactions_15m
        FROM interaction_events
        WHERE created_at >= datetime('now', '-15 minutes')
        """
    ).fetchone()

    conn.close()

    interactions_24h = int(window_row["interactions"] or 0)
    success_24h = int(window_row["success_count"] or 0)
    fallback_24h = int(window_row["fallback_count"] or 0)
    active_users_24h = int(window_row["active_users"] or 0)
    avg_answer_len_24h = round(float(window_row["avg_answer_len"] or 0.0), 1)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "kpis": {
            "total_interactions": int(total_interactions or 0),
            "interactions_24h": interactions_24h,
            "active_users_24h": active_users_24h,
            "success_rate_24h": _safe_pct(success_24h, interactions_24h),
            "fallback_rate_24h": _safe_pct(fallback_24h, interactions_24h),
            "avg_answer_len_24h": avg_answer_len_24h,
            "median_latency_ms_24h": _percentile(latencies, 0.50),
            "p95_latency_ms_24h": _percentile(latencies, 0.95),
            "events_per_min_15m": round((int(pulse_row["interactions_15m"] or 0) / 15.0), 2),
        },
        "channels": [
            {"channel": row["channel"], "count": int(row["count"] or 0)}
            for row in channel_rows
        ],
        "languages": [
            {"language": row["source_language"], "count": int(row["count"] or 0)}
            for row in language_rows
        ],
        "daily_volume": [
            {"day": row["day"], "count": int(row["count"] or 0)}
            for row in daily_rows
        ],
        "hourly_volume": [
            {"hour": row["hour"], "count": int(row["count"] or 0)}
            for row in hourly_rows
        ],
        "top_questions": [
            {
                "question": (row["question"] or "(empty)")[:120],
                "count": int(row["count"] or 0),
            }
            for row in top_questions_rows
        ],
        "error_breakdown": [
            {"error_type": row["error_type"], "count": int(row["count"] or 0)}
            for row in error_rows
        ],
        "recent_incidents": [
            {
                "created_at": row["created_at"],
                "channel": row["channel"],
                "error_type": row["error_type"] or "unknown",
                "question": (row["question_text"] or "")[:120],
                "latency_ms": round(float(row["latency_ms"] or 0.0), 1),
            }
            for row in recent_incidents_rows
        ],
    }
