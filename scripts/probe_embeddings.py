"""Smoke test: local embedding model loads and returns a vector."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag_contract.settings import settings  # noqa: E402
from rag_contract.local_embed import embed_query  # noqa: E402


def main() -> None:
    print("local_embed_model:", settings.local_embed_model)
    v = embed_query("测试本地向量维度")
    print("dim:", len(v))


if __name__ == "__main__":
    main()
