"""ベクター + 全文のハイブリッド検索（RRF 統合）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import db, embed

K_INTERMEDIATE = 50
RRF_K = 60


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    document_path: str
    chunk_index: int
    title: str | None
    source: str | None
    content: str
    score: float


def _vss_search(conn, qvec, k: int) -> list[int]:
    rows = conn.execute(
        "SELECT rowid FROM chunks_vss WHERE vss_search(embedding, vss_search_params(?, ?))",
        (qvec.tobytes(), k),
    ).fetchall()
    return [r["rowid"] for r in rows]


_FTS_SAFE = re.compile(r"[^\w぀-ヿ一-鿿]+", re.UNICODE)


def _fts_query(query: str) -> str:
    """FTS5 用にトークンを OR で結ぶ。記号は除去。"""
    tokens = [t for t in _FTS_SAFE.split(query) if t]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def _fts_search(conn, query: str, k: int) -> list[int]:
    fts_q = _fts_query(query)
    if not fts_q:
        return []
    try:
        rows = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_q, k),
        ).fetchall()
    except Exception:
        return []
    return [r["rowid"] for r in rows]


def _rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def search(query: str, top_n: int = 10) -> list[Hit]:
    conn = db.connect()
    db.init_schema(conn)

    qvec = embed.embed_query(query)
    vss_ids = _vss_search(conn, qvec, K_INTERMEDIATE)
    fts_ids = _fts_search(conn, query, K_INTERMEDIATE)

    fused = _rrf([vss_ids, fts_ids])[:top_n]
    if not fused:
        conn.close()
        return []

    ids = [cid for cid, _ in fused]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""
        SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.content,
               d.path AS document_path, d.title, d.source
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    by_id = {r["chunk_id"]: r for r in rows}

    hits: list[Hit] = []
    for cid, score in fused:
        r = by_id.get(cid)
        if not r:
            continue
        hits.append(
            Hit(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                document_path=r["document_path"],
                chunk_index=r["chunk_index"],
                title=r["title"],
                source=r["source"],
                content=r["content"],
                score=score,
            )
        )
    conn.close()
    return hits


def stats() -> dict:
    conn = db.connect()
    db.init_schema(conn)
    docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    conn.close()
    return {
        "documents": docs,
        "chunks": chunks,
        "db_path": str(db.db_path()),
        "db_size_bytes": db.db_path().stat().st_size if db.db_path().exists() else 0,
    }
