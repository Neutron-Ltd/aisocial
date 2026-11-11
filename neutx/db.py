"""SQLite storage. One connection per call; WAL mode for concurrent readers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY,
    email            TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name             TEXT NOT NULL DEFAULT '',
    password_hash    TEXT NOT NULL,
    timezone         TEXT NOT NULL DEFAULT 'UTC',
    default_hashtags TEXT NOT NULL DEFAULT '',
    default_platforms TEXT NOT NULL DEFAULT '[]',
    default_time     TEXT NOT NULL DEFAULT '15:00',
    default_template_id INTEGER,
    password_changed_at TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_agent   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- NULL = system template
    slug            TEXT UNIQUE,                                     -- system templates only
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    workflow        TEXT NOT NULL,
    aspect          TEXT NOT NULL DEFAULT '9:16',
    style_prompt    TEXT NOT NULL DEFAULT '',
    negative_prompt TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('image', 'video')),
    stored_name   TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    mime          TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    width         INTEGER,
    height        INTEGER,
    source        TEXT NOT NULL CHECK (source IN ('upload', 'generated')),
    job_id        INTEGER,
    prompt        TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id     INTEGER REFERENCES templates(id) ON DELETE SET NULL,
    workflow        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('queued', 'submitted', 'running', 'succeeded', 'failed')),
    prompt          TEXT NOT NULL,
    params          TEXT NOT NULL DEFAULT '{}',
    input_media_id  INTEGER REFERENCES media(id) ON DELETE SET NULL,
    comfy_prompt_id TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS social_accounts (
    id                 INTEGER PRIMARY KEY,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform           TEXT NOT NULL,
    external_id        TEXT NOT NULL,
    username           TEXT NOT NULL DEFAULT '',
    access_token_enc   TEXT NOT NULL,
    refresh_token_enc  TEXT,
    expires_at         TEXT,
    refresh_expires_at TEXT,
    scope              TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (user_id, platform, external_id)
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state_hash    TEXT PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform      TEXT NOT NULL,
    code_verifier TEXT NOT NULL,
    return_to     TEXT NOT NULL DEFAULT 'connections.html',
    expires_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    media_id     INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    title        TEXT NOT NULL DEFAULT '',
    caption      TEXT NOT NULL DEFAULT '',
    scheduled_at TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('scheduled', 'publishing', 'published', 'partial', 'failed', 'cancelled')),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_targets (
    id           INTEGER PRIMARY KEY,
    post_id      INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    account_id   INTEGER REFERENCES social_accounts(id) ON DELETE SET NULL,
    platform     TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'publishing', 'published', 'failed')),
    external_id  TEXT,
    external_url TEXT,
    error        TEXT,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_due ON posts (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_media_user ON media (user_id, created_at);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso(utcnow())


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run a write; returns lastrowid (inserts) or rowcount (updates/deletes)."""
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))
