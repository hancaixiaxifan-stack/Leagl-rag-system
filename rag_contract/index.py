from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from qdrant_client.models import PointStruct

from .chunking import Chunk
from .settings import settings

# 获取Qdrant客户端
def get_qdrant() -> QdrantClient:
    # Persist locally for dev; later can switch to remote Qdrant in Docker
    return QdrantClient(path=settings.qdrant_path)


# 确保Qdrant集合存在，若不存在则创建
def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection in existing:
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


# 将 chunk 数据和向量写入 Qdrant 索引中
def upsert_chunks(
    client: QdrantClient,
    *,
    embeddings: list[list[float]],
    chunks: list,
) -> None:
    assert len(embeddings) == len(chunks)
    payloads = [c if isinstance(c, dict) else asdict(c) for c in chunks]
    ids = list(range(len(chunks)))
    client.upsert(
        collection_name=settings.qdrant_collection,
        points=[
            PointStruct(id=ids[i], vector=embeddings[i], payload=payloads[i])
            for i in range(len(chunks))
        ],
        wait=True,
    )

#

# 搜索 Qdrant 索引中的 chunks
def search(client: QdrantClient, query_vec: list[float], limit: int):
    # qdrant-client v1.17+ uses `query_points` for unified queries.
    return client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vec,
        limit=limit,
        with_payload=True,
    )

