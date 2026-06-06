import os
import sqlite3
from contextlib import contextmanager

DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/docpipe.db")


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    role TEXT DEFAULT 'user',
    api_token TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    filename TEXT,
    original_name TEXT,
    format TEXT,
    size INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    document_id INTEGER,
    job_id TEXT UNIQUE,
    output_format TEXT,
    output_name TEXT,
    status TEXT DEFAULT 'pending',
    output_path TEXT,
    error TEXT,
    webhook_url TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental schema migrations."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "webhook_url" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN webhook_url TEXT")
        conn.commit()


def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _migrate(conn)

        # Seed admin user
        from passlib.hash import bcrypt as bcrypt_hash
        row = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
        if not row:
            ph = bcrypt_hash.hash("admin123")
            conn.execute(
                "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, 'admin', 'admin@docpipe.local')",
                ("admin", ph),
            )
            conn.commit()
    finally:
        conn.close()
