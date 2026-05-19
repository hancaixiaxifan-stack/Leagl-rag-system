#!/usr/bin/env python3
"""
仅执行向量生成和索引构建（跳过文档解析）
用于在已有chunks.jsonl的情况下快速重建向量索引
"""

import json
from pathlib import Path

from rag_contract.chunking import Chunk
from rag_contract.index import ensure_collection, get_qdrant, upsert_chunks
from rag_contract.local_embed import embed_texts
from rag_contract.settings import settings


def main() -> None:
    chunks_path = Path(settings.chunks_path)
    
    if not chunks_path.exists():
        print(f"错误: chunks文件不存在 {chunks_path}")
        print("请先运行 python -m scripts.ingest 生成chunks")
        return
    
    # 加载已有的chunks
    print(f"加载chunks文件: {chunks_path}")
    all_chunks = []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            chunk = Chunk(**data)
            all_chunks.append(chunk)
    
    print(f"加载完成: {len(all_chunks)} 个chunks")
    
    if not all_chunks:
        print("错误: 没有加载到任何chunks")
        return
    
    # 生成嵌入向量
    print("开始生成嵌入向量...")
    texts = [c.text for c in all_chunks]
    embeddings = embed_texts(texts)
    print(f"嵌入向量生成完成: {len(embeddings)} 个向量")
    
    # 构建向量索引
    print("开始构建向量索引...")
    vector_size = len(embeddings[0])
    client = get_qdrant()
    ensure_collection(client, vector_size=vector_size)
    upsert_chunks(client, embeddings=embeddings, chunks=all_chunks)
    
    print("\n" + "="*50)
    print("向量知识库重建完成！")
    print(f"qdrant_collection={settings.qdrant_collection}")
    print(f"vectors={len(embeddings)}")
    print(f"dim={vector_size}")
    print("="*50)


if __name__ == "__main__":
    main()