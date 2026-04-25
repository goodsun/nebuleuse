"""ingest テスト用フィクスチャ。

埋め込みモデルの実ロードを避けるため、`embed.embed_passages` を決定論的な
スタブに差し替える。
"""
from __future__ import annotations

import hashlib
import os

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """各テストごとに ~/nebuleuse 相当を tmp_path に隔離する。"""
    monkeypatch.setenv("NEBULEUSE_HOME", str(tmp_path))
    # キャッシュ済み DEFAULT_DATA_DIR を再評価させるために再 import 風の対処
    from nebuleuse import db as db_mod

    monkeypatch.setattr(db_mod, "DEFAULT_DATA_DIR", tmp_path)
    yield


@pytest.fixture
def fake_embeddings(monkeypatch):
    """埋め込みを決定論的ハッシュベースのベクトルにする（重いモデルロード回避）。"""
    from nebuleuse import db as db_mod
    from nebuleuse import embed

    dim = db_mod.EMBED_DIM

    def _stub_passages(texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            seed = int.from_bytes(h[:8], "big")
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(dim).astype(np.float32)
            v /= np.linalg.norm(v) + 1e-12
            out.append(v)
        return np.stack(out)

    def _stub_query(t):
        return _stub_passages([t])[0]

    monkeypatch.setattr(embed, "embed_passages", _stub_passages)
    monkeypatch.setattr(embed, "embed_query", _stub_query)
    return _stub_passages
