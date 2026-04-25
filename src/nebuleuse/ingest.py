"""raw/ をスキャンして DB に取り込む。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import yaml

from . import db, embed
from .chunker import chunk_text
from .tokenize import to_index_text

FRONTMATTER_RE_PREFIX = "---\n"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith(FRONTMATTER_RE_PREFIX):
        return {}, text
    end = text.find("\n---\n", len(FRONTMATTER_RE_PREFIX))
    if end == -1:
        return {}, text
    raw = text[len(FRONTMATTER_RE_PREFIX) : end]
    body = text[end + len("\n---\n") :]
    try:
        meta = yaml.safe_load(raw) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    return meta, body


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _iter_md_files(raw_root: Path):
    yield from sorted(raw_root.rglob("*.md"))


def ingest_all() -> dict:
    """raw/ 以下を全件取り込む（素朴版：差分検出は Phase 3）。"""
    conn = db.connect()
    db.init_schema(conn)

    raw_root = db.data_dir() / "raw"
    seen_paths: set[str] = set()
    stats = {"added": 0, "updated": 0, "deleted": 0, "chunks": 0}

    files = list(_iter_md_files(raw_root))
    for path in files:
        rel = str(path.relative_to(raw_root))
        seen_paths.add(rel)
        text = path.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(text)
        title = meta.get("title") or _infer_title(body) or rel
        source = meta.get("source")
        source_meta = json.dumps(meta, ensure_ascii=False) if meta else None
        h = _file_hash(text)
        mtime = path.stat().st_mtime

        existing = conn.execute(
            "SELECT id, hash FROM documents WHERE path = ?", (rel,)
        ).fetchone()

        if existing and existing["hash"] == h:
            continue

        if existing:
            doc_id = existing["id"]
            db.reset_chunks_for_document(conn, doc_id)
            conn.execute(
                "UPDATE documents SET title=?, updated_at=?, mtime=?, hash=?, source=?, source_meta=? WHERE id=?",
                (title, _now(), mtime, h, source, source_meta, doc_id),
            )
            stats["updated"] += 1
        else:
            cur = conn.execute(
                "INSERT INTO documents(path, title, created_at, updated_at, mtime, hash, source, source_meta) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rel, title, _now(), _now(), mtime, h, source, source_meta),
            )
            doc_id = cur.lastrowid
            stats["added"] += 1

        chunks = chunk_text(body)
        if not chunks:
            continue
        vecs = embed.embed_passages([c.content for c in chunks])
        for idx, (chunk, vec) in enumerate(zip(chunks, vecs)):
            cur = conn.execute(
                "INSERT INTO chunks(document_id, chunk_index, content, char_start, char_end) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, idx, chunk.content, chunk.char_start, chunk.char_end),
            )
            chunk_id = cur.lastrowid
            conn.execute(
                "INSERT INTO chunks_vss(rowid, embedding) VALUES (?, ?)",
                (chunk_id, vec.tobytes()),
            )
            conn.execute(
                "INSERT INTO chunks_fts(rowid, content) VALUES (?, ?)",
                (chunk_id, to_index_text(chunk.content)),
            )
            stats["chunks"] += 1

    # 削除検出
    rows = conn.execute("SELECT id, path FROM documents").fetchall()
    for row in rows:
        if row["path"] not in seen_paths:
            db.reset_chunks_for_document(conn, row["id"])
            conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
            stats["deleted"] += 1

    conn.commit()
    conn.close()
    return stats


def _infer_title(body: str) -> str | None:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s:
            return s[:60]
    return None
