"""SQLite database for users, chat history, and analytics."""

import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None

ROOT_DIR = Path(__file__).resolve().parent.parent


def _resolve_storage_path(env_key, default_path):
    configured = (os.getenv(env_key) or "").strip()
    if not configured:
        return default_path

    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate

    resolved = candidate.resolve()
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved
    except OSError:
        return default_path


DEFAULT_DB_PATH = (ROOT_DIR / "data" / "gamma.db").resolve()
DB_PATH = _resolve_storage_path("GAMMA_DB_PATH", DEFAULT_DB_PATH)

DEFAULT_USERS_BACKUP_PATH = DB_PATH.with_name("users_backup.json")
USERS_BACKUP_PATH = _resolve_storage_path("GAMMA_USERS_BACKUP_PATH", DEFAULT_USERS_BACKUP_PATH)
AUTH_DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

FALLBACK_RESPONSE_PREFIX = "i'm not fully confident in the answer based on the available documents"
AUTH_SOURCE_SQLITE = "sqlite"
AUTH_SOURCE_POSTGRES = "postgres"


def _external_auth_enabled():
    return bool(AUTH_DATABASE_URL and psycopg is not None)


def _with_auth_source(user_record, auth_source):
    if user_record is None:
        return None

    tagged = dict(user_record)
    tagged["auth_source"] = auth_source
    return tagged


def _get_postgres_auth_conn():
    if not _external_auth_enabled():
        return None

    connect_kwargs = {"row_factory": dict_row}

    explicit_sslmode = (os.getenv("DATABASE_SSLMODE") or "").strip()
    if explicit_sslmode:
        connect_kwargs["sslmode"] = explicit_sslmode
    elif "sslmode=" not in AUTH_DATABASE_URL.lower():
        connect_kwargs["sslmode"] = "require"

    connect_timeout = (os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS") or "").strip()
    if connect_timeout:
        try:
            connect_kwargs["connect_timeout"] = max(1, int(connect_timeout))
        except ValueError:
            pass

    return psycopg.connect(AUTH_DATABASE_URL, **connect_kwargs)


def _load_legacy_db_paths():
    paths = []

    configured = (os.getenv("GAMMA_LEGACY_DB_PATHS") or "").strip()
    if configured:
        for raw in configured.split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = ROOT_DIR / path
            paths.append(path.resolve())

    # Keep the historical default path as a migration source.
    paths.append(DEFAULT_DB_PATH)

    unique = []
    target = DB_PATH.resolve()
    for path in paths:
        resolved = path.resolve()
        if resolved == target:
            continue
        if resolved in unique:
            continue
        unique.append(resolved)
    return unique


LEGACY_DB_PATHS = _load_legacy_db_paths()


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _users_table_exists(conn):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    return row is not None


def _normalize_role(role):
    normalized_role = (role or "student").strip().lower()
    if normalized_role not in {"student", "admin"}:
        return "student"
    return normalized_role


def _normalize_user_record(username, password_hash, role, created_at):
    normalized_username = (username or "").strip()
    normalized_hash = (password_hash or "").strip()
    if not normalized_username or not normalized_hash:
        return None

    normalized_role = _normalize_role(role)

    normalized_created_at = (created_at or "").strip() or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "username": normalized_username,
        "password_hash": normalized_hash,
        "role": normalized_role,
        "created_at": normalized_created_at,
    }


def _insert_missing_users(conn, user_rows):
    inserted = 0
    for row in user_rows:
        record = _normalize_user_record(
            row.get("username"),
            row.get("password_hash"),
            row.get("role"),
            row.get("created_at"),
        )
        if record is None:
            continue

        exists = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?)",
            (record["username"],),
        ).fetchone()
        if exists:
            continue

        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                record["username"],
                record["password_hash"],
                record["role"],
                record["created_at"],
            ),
        )
        inserted += 1
    return inserted


def _ensure_postgres_auth_schema(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_username_lower
                ON auth_users(LOWER(username))
            """
        )


def _ensure_postgres_app_schema(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                role TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_chats_user_created ON chats(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_chats_created ON chats(created_at);
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS interaction_events (
                id BIGSERIAL PRIMARY KEY,
                legacy_chat_id BIGINT,
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
            CREATE INDEX IF NOT EXISTS idx_interaction_events_created_at_pg ON interaction_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_interaction_events_channel_created_pg ON interaction_events(channel, created_at);
            CREATE INDEX IF NOT EXISTS idx_interaction_events_success_created_pg ON interaction_events(success, created_at);
            """
        )


def _load_all_chats_sqlite(conn):
    rows = conn.execute(
        "SELECT id, user_id, username, role, question, answer, created_at FROM chats"
    ).fetchall()
    return [dict(r) for r in rows]


def _load_all_interactions_sqlite(conn):
    rows = conn.execute(
        """
        SELECT legacy_chat_id, channel, user_ref, question_text, answer_text, source_language,
               translated_inbound, translated_outbound, success, fallback_used, latency_ms, error_type, created_at
        FROM interaction_events
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _insert_chats_postgres(pg_conn, chats):
    inserted = 0
    with pg_conn.cursor() as cur:
        for row in chats:
            cur.execute(
                """
                SELECT 1 FROM chats
                WHERE user_id = %s AND TRIM(question) = TRIM(%s) AND TRIM(answer) = TRIM(%s) AND created_at = %s
                LIMIT 1
                """,
                (
                    row.get("user_id"),
                    row.get("question"),
                    row.get("answer"),
                    row.get("created_at"),
                ),
            )
            if cur.fetchone() is not None:
                continue

            cur.execute(
                """
                INSERT INTO chats (user_id, username, role, question, answer, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    row.get("user_id"),
                    row.get("username"),
                    _normalize_role(row.get("role")),
                    row.get("question"),
                    row.get("answer"),
                    row.get("created_at"),
                ),
            )
            inserted += 1 if cur.fetchone() else 0
    return inserted


def _insert_interactions_postgres(pg_conn, events):
    inserted = 0
    with pg_conn.cursor() as cur:
        for row in events:
            cur.execute(
                """
                SELECT 1 FROM interaction_events
                WHERE TRIM(COALESCE(question_text,'')) = TRIM(COALESCE(%s,''))
                  AND TRIM(COALESCE(answer_text,'')) = TRIM(COALESCE(%s,''))
                  AND TRIM(COALESCE(user_ref,'')) = TRIM(COALESCE(%s,''))
                  AND created_at = %s
                LIMIT 1
                """,
                (
                    row.get("question_text"),
                    row.get("answer_text"),
                    row.get("user_ref"),
                    row.get("created_at"),
                ),
            )
            if cur.fetchone() is not None:
                continue

            cur.execute(
                """
                INSERT INTO interaction_events (
                    legacy_chat_id, channel, user_ref, question_text, answer_text, source_language,
                    translated_inbound, translated_outbound, success, fallback_used, latency_ms, error_type, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    row.get("legacy_chat_id"),
                    row.get("channel"),
                    row.get("user_ref"),
                    row.get("question_text"),
                    row.get("answer_text"),
                    row.get("source_language"),
                    row.get("translated_inbound"),
                    row.get("translated_outbound"),
                    row.get("success"),
                    row.get("fallback_used"),
                    row.get("latency_ms"),
                    row.get("error_type"),
                    row.get("created_at"),
                ),
            )
            inserted += 1 if cur.fetchone() else 0
    return inserted


def _migrate_sqlite_app_data_to_postgres(pg_conn):
    if not Path(DB_PATH).exists():
        return

    conn = get_conn()
    try:
        chats = _load_all_chats_sqlite(conn)
        events = _load_all_interactions_sqlite(conn)

        _ensure_postgres_app_schema(pg_conn)

        inserted_chats = _insert_chats_postgres(pg_conn, chats)
        inserted_events = _insert_interactions_postgres(pg_conn, events)
        pg_conn.commit()
    finally:
        conn.close()
def _insert_missing_users_postgres(pg_conn, user_rows):
    inserted = 0
    with pg_conn.cursor() as cur:
        for row in user_rows:
            record = _normalize_user_record(
                row.get("username"),
                row.get("password_hash"),
                row.get("role"),
                row.get("created_at"),
            )
            if record is None:
                continue

            cur.execute(
                "SELECT id FROM auth_users WHERE LOWER(username) = LOWER(%s)",
                (record["username"],),
            )
            if cur.fetchone() is not None:
                continue

            cur.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    record["username"],
                    record["password_hash"],
                    record["role"],
                    record["created_at"],
                ),
            )
            inserted += 1
    return inserted


def _load_all_users_from_postgres(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, password_hash, role, created_at
            FROM auth_users
            ORDER BY id ASC
            """
        )
        return cur.fetchall()


def _postgres_table_exists(pg_conn, table_name):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = %s
            ) AS present
            """,
            (table_name,),
        )
        row = cur.fetchone() or {}
        if isinstance(row, dict):
            return bool(row.get("present"))
        return bool(row[0])


def _postgres_table_columns(pg_conn, table_name):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            (table_name,),
        )
        rows = cur.fetchall()
    names = set()
    for row in rows:
        if isinstance(row, dict):
            names.add((row.get("column_name") or "").strip().lower())
        else:
            names.add((row[0] or "").strip().lower())
    return names


def _collect_users_from_legacy_postgres_table(pg_conn):
    # Support environments that already store accounts in a generic Postgres "users" table.
    if not _postgres_table_exists(pg_conn, "users"):
        return []

    columns = _postgres_table_columns(pg_conn, "users")
    if "username" not in columns or "password_hash" not in columns:
        return []

    role_expr = "COALESCE(role, 'student')" if "role" in columns else "'student'"
    created_expr = "COALESCE(created_at, NOW())" if "created_at" in columns else "NOW()"

    with pg_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                username,
                password_hash,
                {role_expr} AS role,
                {created_expr} AS created_at
            FROM users
            WHERE username IS NOT NULL
              AND password_hash IS NOT NULL
            """
        )
        rows = cur.fetchall()

    records = []
    for row in rows:
        if isinstance(row, dict):
            records.append(
                {
                    "username": row.get("username"),
                    "password_hash": row.get("password_hash"),
                    "role": row.get("role"),
                    "created_at": row.get("created_at"),
                }
            )
        else:
            records.append(
                {
                    "username": row[0],
                    "password_hash": row[1],
                    "role": row[2] if len(row) > 2 else "student",
                    "created_at": row[3] if len(row) > 3 else None,
                }
            )
    return records


def _migrate_users_from_legacy_postgres_table(pg_conn):
    records = _collect_users_from_legacy_postgres_table(pg_conn)
    if not records:
        return 0
    return _insert_missing_users_postgres(pg_conn, records)


def _load_users_from_backup():
    if not USERS_BACKUP_PATH.exists():
        return []

    try:
        payload = json.loads(USERS_BACKUP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(payload, dict):
        users = payload.get("users") or []
    elif isinstance(payload, list):
        users = payload
    else:
        return []

    records = []
    for item in users:
        if not isinstance(item, dict):
            continue
        record = _normalize_user_record(
            item.get("username"),
            item.get("password_hash"),
            item.get("role"),
            item.get("created_at"),
        )
        if record is not None:
            records.append(record)
    return records


def _restore_users_from_backup(conn):
    records = _load_users_from_backup()
    if not records:
        return 0
    return _insert_missing_users(conn, records)


def _restore_users_from_backup_postgres(pg_conn):
    records = _load_users_from_backup()
    if not records:
        return 0
    return _insert_missing_users_postgres(pg_conn, records)


def _collect_users_from_legacy_dbs():
    collected = []
    for path in LEGACY_DB_PATHS:
        if not path.exists():
            continue

        source_conn = None
        try:
            source_conn = sqlite3.connect(str(path))
            source_conn.row_factory = sqlite3.Row

            if not _users_table_exists(source_conn):
                continue

            rows = source_conn.execute(
                """
                SELECT
                    username,
                    password_hash,
                    COALESCE(role, 'student') AS role,
                    COALESCE(created_at, datetime('now')) AS created_at
                FROM users
                """
            ).fetchall()

            collected.extend(
                [
                    {
                        "username": row["username"],
                        "password_hash": row["password_hash"],
                        "role": row["role"],
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]
            )
        except Exception:
            continue
        finally:
            if source_conn is not None:
                source_conn.close()

    return collected


def _migrate_users_from_legacy_dbs(conn):
    records = _collect_users_from_legacy_dbs()
    if not records:
        return 0
    return _insert_missing_users(conn, records)


def _migrate_users_from_legacy_dbs_postgres(pg_conn):
    records = _collect_users_from_legacy_dbs()
    if not records:
        return 0
    return _insert_missing_users_postgres(pg_conn, records)


def _serialize_created_at(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _write_users_backup(rows):
    payload = {
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "users": [
            {
                "id": int(row["id"]),
                "username": row["username"],
                "password_hash": row["password_hash"],
                "role": row["role"],
                "created_at": _serialize_created_at(row.get("created_at")),
            }
            for row in rows
        ],
    }

    try:
        USERS_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = USERS_BACKUP_PATH.with_suffix(USERS_BACKUP_PATH.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(USERS_BACKUP_PATH)
    except Exception:
        # Backup sync failures should not block the app from serving traffic.
        return


def _sync_users_backup_from_conn(conn):
    if not _users_table_exists(conn):
        return

    rows = conn.execute(
        """
        SELECT id, username, password_hash, role, created_at
        FROM users
        ORDER BY id ASC
        """
    ).fetchall()

    normalized_rows = [
        {
            "id": int(row["id"]),
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    _write_users_backup(normalized_rows)


def _sync_users_backup_from_postgres(pg_conn):
    rows = _load_all_users_from_postgres(pg_conn)
    normalized_rows = [
        {
            "id": int(row["id"]),
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]
    _write_users_backup(normalized_rows)


def _bootstrap_admin_credentials():
    username = (os.getenv("GAMMA_BOOTSTRAP_ADMIN_USERNAME") or "").strip()
    password = os.getenv("GAMMA_BOOTSTRAP_ADMIN_PASSWORD") or ""
    if not username or not password:
        return None
    return username, password


def _sync_users_backup():
    if _external_auth_enabled():
        pg_conn = None
        try:
            pg_conn = _get_postgres_auth_conn()
            _ensure_postgres_auth_schema(pg_conn)
            _sync_users_backup_from_postgres(pg_conn)
            return
        except Exception:
            pass
        finally:
            if pg_conn is not None:
                pg_conn.close()

    conn = None
    try:
        conn = get_conn()
        _sync_users_backup_from_conn(conn)
    except Exception:
        return
    finally:
        if conn is not None:
            conn.close()


def _bootstrap_admin_from_env(conn):
    credentials = _bootstrap_admin_credentials()
    if credentials is None:
        return False
    username, password = credentials

    exists = conn.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(?)",
        (username,),
    ).fetchone()
    if exists:
        return False

    conn.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, 'admin')
        """,
        (username, generate_password_hash(password)),
    )
    return True


def _bootstrap_admin_from_env_postgres(pg_conn):
    credentials = _bootstrap_admin_credentials()
    if credentials is None:
        return False
    username, password = credentials

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM auth_users WHERE LOWER(username) = LOWER(%s)",
            (username,),
        )
        if cur.fetchone() is not None:
            return False

        cur.execute(
            """
            INSERT INTO auth_users (username, password_hash, role)
            VALUES (%s, %s, 'admin')
            """,
            (username, generate_password_hash(password)),
        )
    return True

def _table_columns(conn, table_name):
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_interaction_events_schema(conn):
    columns = _table_columns(conn, "interaction_events")
    if "legacy_chat_id" not in columns:
        conn.execute("ALTER TABLE interaction_events ADD COLUMN legacy_chat_id INTEGER")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_events_legacy_chat_id
            ON interaction_events(legacy_chat_id)
            WHERE legacy_chat_id IS NOT NULL
        """
    )


def _backfill_interaction_events_from_chats(conn):
    # Pull legacy web chats into interaction_events so dashboard analytics include historical data.
    conn.execute(
        """
        INSERT INTO interaction_events (
            legacy_chat_id,
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
            error_type,
            created_at
        )
        SELECT
            c.id,
            'web_legacy',
            'user:' || c.user_id,
            c.question,
            c.answer,
            'eng',
            0,
            0,
            1,
            CASE
                WHEN LOWER(TRIM(COALESCE(c.answer, ''))) LIKE ? THEN 1
                ELSE 0
            END,
            NULL,
            '',
            c.created_at
        FROM chats c
        WHERE NOT EXISTS (
            SELECT 1
            FROM interaction_events e
            WHERE e.legacy_chat_id = c.id
               OR (
                    TRIM(COALESCE(e.question_text, '')) = TRIM(COALESCE(c.question, ''))
                AND TRIM(COALESCE(e.answer_text, '')) = TRIM(COALESCE(c.answer, ''))
                AND TRIM(COALESCE(e.user_ref, '')) = ('user:' || c.user_id)
                AND ABS(strftime('%s', COALESCE(e.created_at, c.created_at)) - strftime('%s', c.created_at)) <= 120
               )
        )
        """,
        (f"{FALLBACK_RESPONSE_PREFIX}%",),
    )


def _candidate_passwords(password):
    raw_password = password or ""
    candidates = [raw_password]
    stripped_password = raw_password.strip()
    if stripped_password != raw_password:
        candidates.append(stripped_password)
    return candidates


def _sqlite_rows_for_user_migration(conn):
    rows = conn.execute(
        """
        SELECT username, password_hash, role, created_at
        FROM users
        """
    ).fetchall()
    return [
        {
            "username": row["username"],
            "password_hash": row["password_hash"],
            "role": row["role"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _lookup_postgres_user_by_username(pg_conn, normalized_username):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, password_hash, role, created_at
            FROM auth_users
            WHERE username = %s
            """,
            (normalized_username,),
        )
        row = cur.fetchone()
        if row is not None:
            return row

        cur.execute(
            """
            SELECT id, username, password_hash, role, created_at
            FROM auth_users
            WHERE LOWER(username) = LOWER(%s)
            ORDER BY id ASC
            """,
            (normalized_username,),
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]
        return None


def _lookup_legacy_postgres_user_by_username(pg_conn, normalized_username):
    columns = _postgres_table_columns(pg_conn, "users")
    if "username" not in columns or "password_hash" not in columns:
        return None

    role_expr = "COALESCE(role, 'student')" if "role" in columns else "'student'"
    created_expr = "COALESCE(created_at, NOW())" if "created_at" in columns else "NOW()"

    with pg_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                username,
                password_hash,
                {role_expr} AS role,
                {created_expr} AS created_at
            FROM users
            WHERE username = %s
            """,
            (normalized_username,),
        )
        row = cur.fetchone()
        if row is not None:
            return row

        cur.execute(
            f"""
            SELECT
                username,
                password_hash,
                {role_expr} AS role,
                {created_expr} AS created_at
            FROM users
            WHERE LOWER(username) = LOWER(%s)
            ORDER BY username ASC
            """,
            (normalized_username,),
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]
        return None


def _create_user_sqlite(normalized_username, normalized_password, normalized_role):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?)",
            (normalized_username,),
        ).fetchone()
        if existing:
            return None

        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (normalized_username, generate_password_hash(normalized_password), normalized_role),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def _create_user_postgres(normalized_username, normalized_password, normalized_role):
    pg_conn = _get_postgres_auth_conn()
    try:
        _ensure_postgres_auth_schema(pg_conn)
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM auth_users WHERE LOWER(username) = LOWER(%s)",
                (normalized_username,),
            )
            if cur.fetchone() is not None:
                return None

            cur.execute(
                """
                INSERT INTO auth_users (username, password_hash, role)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (
                    normalized_username,
                    generate_password_hash(normalized_password),
                    normalized_role,
                ),
            )
            inserted = cur.fetchone()

        pg_conn.commit()
        _sync_users_backup_from_postgres(pg_conn)
        return int(inserted["id"]) if inserted else None
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        pg_conn.close()


def _sync_single_user_to_postgres(user_record):
    if not _external_auth_enabled() or not user_record:
        return False

    normalized = _normalize_user_record(
        user_record.get("username"),
        user_record.get("password_hash"),
        user_record.get("role"),
        user_record.get("created_at"),
    )
    if normalized is None:
        return False

    pg_conn = _get_postgres_auth_conn()
    try:
        _ensure_postgres_auth_schema(pg_conn)
        inserted = _insert_missing_users_postgres(pg_conn, [normalized])
        pg_conn.commit()
        if inserted:
            _sync_users_backup_from_postgres(pg_conn)
        return inserted > 0
    except Exception:
        pg_conn.rollback()
        return False
    finally:
        pg_conn.close()


def _verify_user_sqlite(normalized_username, password):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized_username,)).fetchone()

        if row is None:
            matches = conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
                (normalized_username,),
            ).fetchall()
            if len(matches) == 1:
                row = matches[0]

        if row is None:
            restored = _restore_users_from_backup(conn)
            if restored:
                row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized_username,)).fetchone()
                if row is None:
                    matches = conn.execute(
                        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
                        (normalized_username,),
                    ).fetchall()
                    if len(matches) == 1:
                        row = matches[0]

        if row is None:
            return None

        stored_hash = row["password_hash"] or ""
        for candidate in _candidate_passwords(password):
            try:
                if check_password_hash(stored_hash, candidate):
                    return _with_auth_source(dict(row), AUTH_SOURCE_SQLITE)
            except ValueError:
                # Some legacy deployments may have plaintext values from older setups.
                if stored_hash == candidate:
                    conn.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(candidate), row["id"]),
                    )
                    conn.commit()
                    _sync_users_backup()
                    return _with_auth_source(dict(row), AUTH_SOURCE_SQLITE)

        return None
    finally:
        conn.close()


def _verify_user_postgres(normalized_username, password):
    pg_conn = _get_postgres_auth_conn()
    try:
        _ensure_postgres_auth_schema(pg_conn)
        row = _lookup_postgres_user_by_username(pg_conn, normalized_username)
        if row is not None:
            stored_hash = row.get("password_hash") or ""
            for candidate in _candidate_passwords(password):
                try:
                    if check_password_hash(stored_hash, candidate):
                        return _with_auth_source(dict(row), AUTH_SOURCE_POSTGRES)
                except ValueError:
                    if stored_hash == candidate:
                        with pg_conn.cursor() as cur:
                            cur.execute(
                                "UPDATE auth_users SET password_hash = %s WHERE id = %s",
                                (generate_password_hash(candidate), row["id"]),
                            )
                        pg_conn.commit()
                        _sync_users_backup_from_postgres(pg_conn)
                        return _with_auth_source(dict(row), AUTH_SOURCE_POSTGRES)

        # Legacy path: verify against a pre-existing Postgres `users` table, then migrate into auth_users.
        if not _postgres_table_exists(pg_conn, "users"):
            return None

        legacy_row = _lookup_legacy_postgres_user_by_username(pg_conn, normalized_username)
        if legacy_row is None:
            return None

        stored_hash = legacy_row.get("password_hash") or ""
        for candidate in _candidate_passwords(password):
            verified = False
            normalized_hash = stored_hash

            try:
                verified = check_password_hash(stored_hash, candidate)
            except ValueError:
                if stored_hash == candidate:
                    verified = True
                    normalized_hash = generate_password_hash(candidate)

            if not verified:
                continue

            migration_record = {
                "username": legacy_row.get("username"),
                "password_hash": normalized_hash,
                "role": legacy_row.get("role"),
                "created_at": legacy_row.get("created_at"),
            }
            _insert_missing_users_postgres(pg_conn, [migration_record])
            pg_conn.commit()

            synced = _lookup_postgres_user_by_username(pg_conn, normalized_username)
            if synced is not None:
                _sync_users_backup_from_postgres(pg_conn)
                return _with_auth_source(dict(synced), AUTH_SOURCE_POSTGRES)

            return None

        return None
    finally:
        pg_conn.close()


def _get_user_by_id_sqlite(user_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _with_auth_source(dict(row), AUTH_SOURCE_SQLITE) if row else None
    finally:
        conn.close()


def _get_user_by_id_postgres(user_id):
    pg_conn = _get_postgres_auth_conn()
    try:
        _ensure_postgres_auth_schema(pg_conn)
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, password_hash, role, created_at
                FROM auth_users
                WHERE id = %s
                """,
                (int(user_id),),
            )
            row = cur.fetchone()
            return _with_auth_source(dict(row), AUTH_SOURCE_POSTGRES) if row else None
    finally:
        pg_conn.close()


def init_db():
    conn = get_conn()
    pg_conn = None
    using_external_auth = False
    try:
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
                legacy_chat_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_users_username_nocase
                ON users(username COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_interaction_events_created_at
                ON interaction_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_interaction_events_channel_created
                ON interaction_events(channel, created_at);
            CREATE INDEX IF NOT EXISTS idx_interaction_events_success_created
                ON interaction_events(success, created_at);
        """)

        _ensure_interaction_events_schema(conn)

        if _external_auth_enabled():
            try:
                pg_conn = _get_postgres_auth_conn()
                _ensure_postgres_auth_schema(pg_conn)
                _restore_users_from_backup_postgres(pg_conn)
                _insert_missing_users_postgres(pg_conn, _sqlite_rows_for_user_migration(conn))
                _migrate_users_from_legacy_dbs_postgres(pg_conn)
                _migrate_users_from_legacy_postgres_table(pg_conn)
                _bootstrap_admin_from_env_postgres(pg_conn)
                _ensure_postgres_app_schema(pg_conn)
                _migrate_sqlite_app_data_to_postgres(pg_conn)
                pg_conn.commit()
                using_external_auth = True
            except Exception:
                if pg_conn is not None:
                    pg_conn.rollback()
                    pg_conn.close()
                    pg_conn = None

        if not using_external_auth:
            _restore_users_from_backup(conn)
            _migrate_users_from_legacy_dbs(conn)
            _bootstrap_admin_from_env(conn)

        _backfill_interaction_events_from_chats(conn)

        conn.commit()
        if using_external_auth and pg_conn is not None:
            _sync_users_backup_from_postgres(pg_conn)
        else:
            _sync_users_backup_from_conn(conn)
    finally:
        conn.close()
        if pg_conn is not None:
            pg_conn.close()


def create_user(username, password, role="student"):
    normalized_username = (username or "").strip()
    normalized_password = password or ""
    normalized_role = _normalize_role(role)
    if not normalized_username or not normalized_password:
        return None

    if _external_auth_enabled():
        try:
            return _create_user_postgres(normalized_username, normalized_password, normalized_role)
        except Exception:
            pass

    user_id = _create_user_sqlite(normalized_username, normalized_password, normalized_role)
    _sync_users_backup()
    return user_id


def verify_user(username, password):
    normalized_username = (username or "").strip()
    if not normalized_username:
        return None

    if _external_auth_enabled():
        postgres_user = None
        try:
            postgres_user = _verify_user_postgres(normalized_username, password)
            if postgres_user is not None:
                return postgres_user
        except Exception:
            pass

        sqlite_user = _verify_user_sqlite(normalized_username, password)
        if sqlite_user is not None:
            _sync_single_user_to_postgres(sqlite_user)
            try:
                postgres_user = _verify_user_postgres(normalized_username, password)
                if postgres_user is not None:
                    return postgres_user
            except Exception:
                pass
            return sqlite_user

        return None

    return _verify_user_sqlite(normalized_username, password)


def get_user_by_id(user_id, auth_source=None):
    normalized_source = (auth_source or "").strip().lower()

    if normalized_source == AUTH_SOURCE_POSTGRES:
        if not _external_auth_enabled():
            return None
        try:
            return _get_user_by_id_postgres(user_id)
        except Exception:
            return None

    if normalized_source == AUTH_SOURCE_SQLITE:
        return _get_user_by_id_sqlite(user_id)

    if _external_auth_enabled():
        try:
            user = _get_user_by_id_postgres(user_id)
            if user is not None:
                return user
        except Exception:
            pass

    return _get_user_by_id_sqlite(user_id)


def _resolve_chat_user_id(user_id, username=None, role=None):
    """
    Normalize chat user id to the local SQLite users table so chat history is consistent
    even when auth is backed by Postgres (different numeric ids).
    """
    conn = get_conn()
    try:
        # Exact id match first.
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return row["id"]

        normalized_username = (username or "").strip()
        if normalized_username:
            match = conn.execute(
                "SELECT id FROM users WHERE LOWER(username) = LOWER(?)",
                (normalized_username,),
            ).fetchone()
            if match:
                return match["id"]

            placeholder_hash = generate_password_hash(f"external-auth:{normalized_username}")
            normalized_role = _normalize_role(role)
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (normalized_username, placeholder_hash, normalized_role),
            )
            conn.commit()
            return cur.lastrowid

        return user_id
    finally:
        conn.close()


def save_chat(user_id, question, answer, username=None, role=None):
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chats (user_id, username, role, question, answer)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, username, _normalize_role(role), question, answer),
                )
                row = cur.fetchone()
            pg_conn.commit()
            return int(row["id"]) if row else None
        finally:
            pg_conn.close()

    chat_user_id = _resolve_chat_user_id(user_id, username=username, role=role)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO chats (user_id, question, answer) VALUES (?, ?, ?)",
        (chat_user_id, question, answer),
    )
    conn.commit()
    chat_id = cur.lastrowid
    conn.close()
    return chat_id


def get_user_chats(user_id, limit=50, username=None, role=None):
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT question, answer, created_at
                    FROM chats
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, int(limit)),
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            pg_conn.close()

    chat_user_id = _resolve_chat_user_id(user_id, username=username, role=role)
    conn = get_conn()
    rows = conn.execute(
        "SELECT question, answer, created_at FROM chats WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (chat_user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_users():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def get_total_chats():
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM chats")
                row = cur.fetchone()
            return int(row["c"] or 0)
        finally:
            pg_conn.close()

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
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT question, answer, created_at, COALESCE(username, '') AS username
                    FROM chats
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            pg_conn.close()

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
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DATE(created_at) AS day, COUNT(*) AS count
                    FROM chats
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                    GROUP BY day
                    ORDER BY day
                    """,
                    (int(days),),
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            pg_conn.close()

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
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute("SELECT AVG(LENGTH(answer)) AS avg_len FROM chats")
                row = cur.fetchone()
            return round(float(row["avg_len"] or 0.0), 1)
        finally:
            pg_conn.close()

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
    legacy_chat_id=None,
):
    q = (question_text or "").strip()
    a = (answer_text or "").strip()
    if len(q) > 1000:
        q = q[:1000]
    if len(a) > 4000:
        a = a[:4000]

    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO interaction_events (
                        legacy_chat_id,
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
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(legacy_chat_id) if legacy_chat_id is not None else None,
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
            pg_conn.commit()
        finally:
            pg_conn.close()
        return

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO interaction_events (
            legacy_chat_id,
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(legacy_chat_id) if legacy_chat_id is not None else None,
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
    if _external_auth_enabled():
        pg_conn = _get_postgres_auth_conn()
        try:
            _ensure_postgres_app_schema(pg_conn)

            day_window = f"{int(days)} days"
            hour_window = f"{int(hours)} hours"

            with pg_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM interaction_events")
                total_interactions = int(cur.fetchone()["c"] or 0)

                cur.execute(
                    "SELECT COUNT(*) AS c FROM interaction_events WHERE created_at >= NOW() - INTERVAL %s",
                    (hour_window,),
                )
                recent_hour_count = int(cur.fetchone()["c"] or 0)

                cur.execute(
                    "SELECT COUNT(*) AS c FROM interaction_events WHERE created_at >= NOW() - INTERVAL %s",
                    (day_window,),
                )
                recent_day_count = int(cur.fetchone()["c"] or 0)

                use_historical_day_window = recent_day_count == 0 and total_interactions > 0
                use_historical_hour_window = recent_hour_count == 0 and total_interactions > 0

                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS interactions,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success_count,
                        SUM(CASE WHEN fallback_used = 1 THEN 1 ELSE 0 END) AS fallback_count,
                        COUNT(DISTINCT NULLIF(TRIM(COALESCE(user_ref, '')), '')) AS active_users,
                        AVG(LENGTH(COALESCE(answer_text, ''))) AS avg_answer_len
                    FROM interaction_events
                    WHERE created_at >= NOW() - INTERVAL %s
                    """,
                    (hour_window,),
                )
                window_row = cur.fetchone()

                cur.execute(
                    """
                    SELECT latency_ms
                    FROM interaction_events
                    WHERE created_at >= NOW() - INTERVAL %s
                      AND latency_ms IS NOT NULL
                    """,
                    (hour_window,),
                )
                latencies = [row["latency_ms"] for row in cur.fetchall() if row["latency_ms"] is not None]

                if use_historical_day_window:
                    cur.execute("SELECT channel, COUNT(*) AS count FROM interaction_events GROUP BY channel ORDER BY count DESC")
                    channel_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT source_language, COUNT(*) AS count
                        FROM interaction_events
                        WHERE TRIM(COALESCE(source_language, '')) != ''
                        GROUP BY source_language
                        ORDER BY count DESC
                        LIMIT 10
                        """
                    )
                    language_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT day, count FROM (
                            SELECT CAST(created_at AS DATE) AS day, COUNT(*) AS count
                            FROM interaction_events
                            GROUP BY day
                            ORDER BY day DESC
                            LIMIT %s
                        ) t ORDER BY day
                        """,
                        (int(days),),
                    )
                    daily_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT MIN(TRIM(question_text)) AS question, COUNT(*) AS count
                        FROM interaction_events
                        WHERE TRIM(COALESCE(question_text, '')) != ''
                        GROUP BY LOWER(TRIM(question_text))
                        ORDER BY count DESC
                        LIMIT %s
                        """,
                        (int(top_n),),
                    )
                    top_questions_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT COALESCE(NULLIF(TRIM(error_type), ''), 'unknown') AS error_type, COUNT(*) AS count
                        FROM interaction_events
                        WHERE success = 0
                        GROUP BY error_type
                        ORDER BY count DESC
                        LIMIT 8
                        """
                    )
                    error_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT created_at, channel, error_type, question_text, latency_ms
                        FROM interaction_events
                        WHERE success = 0
                        ORDER BY created_at DESC
                        LIMIT 12
                        """
                    )
                    recent_incidents_rows = cur.fetchall()
                else:
                    cur.execute(
                        """
                        SELECT channel, COUNT(*) AS count
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                        GROUP BY channel
                        ORDER BY count DESC
                        """,
                        (day_window,),
                    )
                    channel_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT source_language, COUNT(*) AS count
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                          AND TRIM(COALESCE(source_language, '')) != ''
                        GROUP BY source_language
                        ORDER BY count DESC
                        LIMIT 10
                        """,
                        (day_window,),
                    )
                    language_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT CAST(created_at AS DATE) AS day, COUNT(*) AS count
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                        GROUP BY day
                        ORDER BY day
                        """,
                        (day_window,),
                    )
                    daily_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT MIN(TRIM(question_text)) AS question, COUNT(*) AS count
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                          AND TRIM(COALESCE(question_text, '')) != ''
                        GROUP BY LOWER(TRIM(question_text))
                        ORDER BY count DESC
                        LIMIT %s
                        """,
                        (day_window, int(top_n)),
                    )
                    top_questions_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT COALESCE(NULLIF(TRIM(error_type), ''), 'unknown') AS error_type, COUNT(*) AS count
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                          AND success = 0
                        GROUP BY error_type
                        ORDER BY count DESC
                        LIMIT 8
                        """,
                        (day_window,),
                    )
                    error_rows = cur.fetchall()

                    cur.execute(
                        """
                        SELECT created_at, channel, error_type, question_text, latency_ms
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                          AND success = 0
                        ORDER BY created_at DESC
                        LIMIT 12
                        """,
                        (day_window,),
                    )
                    recent_incidents_rows = cur.fetchall()

                if use_historical_hour_window:
                    cur.execute(
                        """
                        SELECT hour, count FROM (
                            SELECT to_char(created_at, 'YYYY-MM-DD HH24:00') AS hour, COUNT(*) AS count
                            FROM interaction_events
                            GROUP BY hour
                            ORDER BY hour DESC
                            LIMIT %s
                        ) t ORDER BY hour
                        """,
                        (int(hours),),
                    )
                    hourly_rows = cur.fetchall()
                else:
                    cur.execute(
                        """
                        SELECT to_char(created_at, 'YYYY-MM-DD HH24:00') AS hour, COUNT(*) AS count
                        FROM interaction_events
                        WHERE created_at >= NOW() - INTERVAL %s
                        GROUP BY hour
                        ORDER BY hour
                        """,
                        (hour_window,),
                    )
                    hourly_rows = cur.fetchall()

                cur.execute(
                    "SELECT COUNT(*) AS interactions_15m FROM interaction_events WHERE created_at >= NOW() - INTERVAL '15 minutes'"
                )
                pulse_row = cur.fetchone()

            interactions_24h = int(window_row["interactions"] or 0)
            success_24h = int(window_row["success_count"] or 0)
            fallback_24h = int(window_row["fallback_count"] or 0)
            active_users_24h = int(window_row["active_users"] or 0)
            avg_answer_len_24h = round(float(window_row["avg_answer_len"] or 0.0), 1)

            return {
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "time_windows": {
                    "daily_mode": "historical_last_14_active_days"
                    if use_historical_day_window
                    else "recent_14d",
                    "hourly_mode": "historical_last_24_active_hours"
                    if use_historical_hour_window
                    else "recent_24h",
                },
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
        finally:
            pg_conn.close()

    day_window = f"-{int(days)} days"
    hour_window = f"-{int(hours)} hours"

    conn = get_conn()

    total_interactions = conn.execute(
        "SELECT COUNT(*) FROM interaction_events"
    ).fetchone()[0]

    recent_day_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
        """,
        (day_window,),
    ).fetchone()[0]

    recent_hour_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM interaction_events
        WHERE created_at >= datetime('now', ?)
        """,
        (hour_window,),
    ).fetchone()[0]

    use_historical_day_window = recent_day_count == 0 and total_interactions > 0
    use_historical_hour_window = recent_hour_count == 0 and total_interactions > 0

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

    if use_historical_day_window:
        channel_rows = conn.execute(
            """
            SELECT channel, COUNT(*) AS count
            FROM interaction_events
            GROUP BY channel
            ORDER BY count DESC
            """
        ).fetchall()

        language_rows = conn.execute(
            """
            SELECT source_language, COUNT(*) AS count
            FROM interaction_events
            WHERE TRIM(COALESCE(source_language, '')) != ''
            GROUP BY source_language
            ORDER BY count DESC
            LIMIT 10
            """
        ).fetchall()

        daily_rows = conn.execute(
            """
            SELECT day, count
            FROM (
                SELECT DATE(created_at) AS day, COUNT(*) AS count
                FROM interaction_events
                GROUP BY day
                ORDER BY day DESC
                LIMIT ?
            )
            ORDER BY day
            """,
            (int(days),),
        ).fetchall()

        top_questions_rows = conn.execute(
            """
            SELECT MIN(TRIM(question_text)) AS question, COUNT(*) AS count
            FROM interaction_events
            WHERE TRIM(COALESCE(question_text, '')) != ''
            GROUP BY LOWER(TRIM(question_text))
            ORDER BY count DESC
            LIMIT ?
            """,
            (int(top_n),),
        ).fetchall()

        error_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(error_type), ''), 'unknown') AS error_type, COUNT(*) AS count
            FROM interaction_events
            WHERE success = 0
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 8
            """
        ).fetchall()

        recent_incidents_rows = conn.execute(
            """
            SELECT created_at, channel, error_type, question_text, latency_ms
            FROM interaction_events
            WHERE success = 0
            ORDER BY created_at DESC
            LIMIT 12
            """
        ).fetchall()
    else:
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

    if use_historical_hour_window:
        hourly_rows = conn.execute(
            """
            SELECT hour, count
            FROM (
                SELECT strftime('%Y-%m-%d %H:00', created_at) AS hour, COUNT(*) AS count
                FROM interaction_events
                GROUP BY hour
                ORDER BY hour DESC
                LIMIT ?
            )
            ORDER BY hour
            """,
            (int(hours),),
        ).fetchall()
    else:
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
        "time_windows": {
            "daily_mode": "historical_last_14_active_days"
            if use_historical_day_window
            else "recent_14d",
            "hourly_mode": "historical_last_24_active_hours"
            if use_historical_hour_window
            else "recent_24h",
        },
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
