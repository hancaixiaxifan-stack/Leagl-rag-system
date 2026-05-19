from __future__ import annotations

from typing import Iterable

from .settings import settings

_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from fastembed import TextEmbedding

        _EMBEDDER = TextEmbedding(model_name=settings.local_embed_model)
    return _EMBEDDER


def _prefix_texts(texts: list[str], prefix: str) -> list[str]:
    p = (prefix or "").strip()
    if not p:
        return texts
    return [f"{p}{t}" for t in texts]


def _batched(xs: list[str], batch_size: int) -> Iterable[list[str]]:
    for i in range(0, len(xs), batch_size):
        yield xs[i : i + batch_size]

# 本地ONNX嵌入模型，用于文档索引和检索
def embed_texts(texts: list[str]) -> list[list[float]]:
    """Local ONNX embeddings (fastembed). Used for indexing documents."""
    m = _get_embedder()
    batch_size = max(1, int(settings.local_embed_batch_size))
    out: list[list[float]] = []
    for batch in _batched(texts, batch_size=batch_size):
        batch2 = _prefix_texts(batch, settings.local_doc_prefix)
        for vec in m.embed(batch2):
            out.append(list(vec))
    return out


def embed_query(text: str) -> list[float]:
    """Same model as embed_texts; optional query prefix for retrieval models."""
    m = _get_embedder()
    t = _prefix_texts([text], settings.local_query_prefix)[0]
    return list(next(m.embed([t])))
