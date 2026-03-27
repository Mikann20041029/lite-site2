"""SQLite operations for job storage and deduplication."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                description TEXT,
                budget_text TEXT,
                proposals_text TEXT,
                payment_verified INTEGER DEFAULT 0,
                client_location TEXT,
                skills TEXT,
                posted_text TEXT,
                score INTEGER DEFAULT 0,
                score_reasons TEXT,
                proposal_draft TEXT,
                first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                notified INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_score ON jobs (score DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notified ON jobs (notified, score DESC)
        """)


def is_seen(job_id: str) -> bool:
    """Return True if this job ID is already in the DB."""
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None


def save_job(job: dict) -> None:
    """Insert a new job. Silently ignore duplicates."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO jobs
              (id, title, url, description, budget_text, proposals_text,
               payment_verified, client_location, skills, posted_text,
               score, score_reasons, proposal_draft, first_seen_at, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                job["id"],
                job["title"],
                job.get("url", ""),
                job.get("description", ""),
                job.get("budget_text", ""),
                job.get("proposals_text", ""),
                1 if job.get("payment_verified") else 0,
                job.get("client_location", ""),
                json.dumps(job.get("skills", []), ensure_ascii=False),
                job.get("posted_text", ""),
                job.get("score", 0),
                json.dumps(job.get("score_reasons", []), ensure_ascii=False),
                job.get("proposal_draft", ""),
                datetime.utcnow().isoformat(),
            ),
        )


def update_score(job_id: str, score: int, reasons: list[str], proposal_draft: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE jobs
               SET score = ?, score_reasons = ?, proposal_draft = ?
             WHERE id = ?
            """,
            (score, json.dumps(reasons, ensure_ascii=False), proposal_draft, job_id),
        )


def mark_notified(job_ids: list[str]) -> None:
    with get_conn() as conn:
        conn.executemany(
            "UPDATE jobs SET notified = 1 WHERE id = ?",
            [(jid,) for jid in job_ids],
        )


def get_unnotified_top(limit: int = 5, min_score: int = 0) -> list[dict]:
    """Return top unnotified jobs sorted by score desc."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
             WHERE notified = 0 AND score >= ?
             ORDER BY score DESC
             LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()
    return [dict(r) for r in rows]
