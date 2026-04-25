"""multilingual-e5 による埋め込み生成。"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

MODEL_NAME = os.environ.get("NEBULEUSE_EMBED_MODEL", "intfloat/multilingual-e5-large")


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed_passages(texts: list[str]) -> np.ndarray:
    prefixed = [f"passage: {t}" for t in texts]
    vecs = _model().encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    vec = _model().encode(
        [f"query: {text}"], normalize_embeddings=True, show_progress_bar=False
    )
    return np.asarray(vec[0], dtype=np.float32)
