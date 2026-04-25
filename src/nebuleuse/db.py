"""SQLite 接続・スキーマ管理。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import sqlite_vss

EMBED_DIM = 1024  # multilingual-e5-large

DEFAULT_DATA_DIR = Path(os.environ.get("NEBULEUSE_HOME", str(Path.home() / "nebuleuse")))


def data_dir() -> Path:
    p = DEFAULT_DATA_DIR
    p.mkdir(parents=True, exist_ok=True)
    (p / "raw").mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "nebuleuse.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.enable_load_extension(True)
    sqlite_vss.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    title       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    mtime       REAL NOT NULL,
    hash        TEXT NOT NULL,
    source      TEXT,
    source_meta TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    char_start   INTEGER NOT NULL,
    char_end     INTEGER NOT NULL,
    UNIQUE(document_id, chunk_index)
);

-- FTS5 は bigram 前処理済みテキストを自前で保持する（external-content は使わない）。
-- ingest 側で chunks への INSERT と同時に chunks_fts へ bigram 化テキストを挿入する。
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE rowid = old.id;
END;

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vss USING vss0(
    embedding({EMBED_DIM})
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset_chunks_for_document(conn: sqlite3.Connection, document_id: int) -> None:
    """vss は CASCADE 対象外なので手動で削除する。chunks_fts はトリガーで連動。"""
    rows = conn.execute(
        "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
    ).fetchall()
    chunk_ids = [r["id"] for r in rows]
    if chunk_ids:
        placeholders = ",".join("?" * len(chunk_ids))
        conn.execute(f"DELETE FROM chunks_vss WHERE rowid IN ({placeholders})", chunk_ids)
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
