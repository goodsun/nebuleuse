"""ingest と search のエンドツーエンド（埋め込みはスタブ）。"""
from __future__ import annotations

from nebuleuse import capture, db, ingest, search


def test_ingest_creates_documents_and_chunks(fake_embeddings):
    capture.capture("# 創価学会\n牧口常三郎による創立。", source="human")
    capture.capture("# Other\nまったく無関係なメモ。")

    stats = ingest.ingest_all()
    assert stats["added"] == 2
    assert stats["chunks"] >= 2

    # 2回目は no-op（差分なし）
    stats2 = ingest.ingest_all()
    assert stats2["added"] == 0
    assert stats2["updated"] == 0


def test_search_hits_japanese_via_bigram_fts(fake_embeddings):
    capture.capture("# 創価学会\n牧口常三郎による創立。", source="human")
    capture.capture("# 関係なし\n全然違う話。")
    ingest.ingest_all()

    hits = search.search("牧口", top_n=5)
    assert hits, "FTS bigram should match 牧口 inside 牧口常三郎"
    assert any("牧口" in h.content for h in hits)


def test_delete_propagates(fake_embeddings):
    p = capture.capture("# 一時的なメモ\n削除予定。", source="human")
    ingest.ingest_all()
    p.unlink()
    stats = ingest.ingest_all()
    assert stats["deleted"] == 1

    conn = db.connect()
    db.init_schema(conn)
    n_docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    n_chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    n_fts = conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
    n_vss = conn.execute("SELECT COUNT(*) AS n FROM chunks_vss").fetchone()["n"]
    conn.close()
    assert n_docs == 0
    assert n_chunks == 0
    assert n_fts == 0
    assert n_vss == 0
