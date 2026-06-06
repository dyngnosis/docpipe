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
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    job_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    output_format TEXT NOT NULL,
    output_name TEXT NOT NULL,
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
    UNIQUE (document_id, version_number)
);
"""


def get_document(doc_id: int, user_id: int):
    """Return a document row if it exists and belongs to user_id, else None."""
    with get_db() as db:
        return db.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        ).fetchone()


def create_version(document_id: int, user_id: int, job_id: str, output_format: str, output_name: str, file_size: int) -> int:
    """Insert a new version record and return its version_number."""
    with get_db() as db:
        row = db.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_ver FROM document_versions WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        next_ver = row["next_ver"]
        db.execute(
            """INSERT INTO document_versions
               (document_id, user_id, job_id, version_number, output_format, output_name, file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (document_id, user_id, job_id, next_ver, output_format, output_name, file_size),
        )
    return next_ver


def list_versions(document_id: int, user_id: int):
    """Return all version rows for a document owned by user_id."""
    with get_db() as db:
        return db.execute(
            """SELECT dv.*, j.status AS job_status
               FROM document_versions dv
               JOIN jobs j ON dv.job_id = j.job_id
               WHERE dv.document_id = ? AND dv.user_id = ?
               ORDER BY dv.version_number ASC""",
            (document_id, user_id),
        ).fetchall()


def get_version(document_id: int, version_number: int, user_id: int):
    """Return a single version row."""
    with get_db() as db:
        return db.execute(
            """SELECT * FROM document_versions
               WHERE document_id = ? AND version_number = ? AND user_id = ?""",
            (document_id, version_number, user_id),
        ).fetchone()


def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()

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
