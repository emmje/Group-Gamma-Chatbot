"""SQLite database for users, chat history, and analytics."""

import sqlite3
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
