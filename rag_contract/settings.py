from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Local embeddings only (fastembed + ONNX); ingest + /ask retrieval use this.
    local_embed_model: str = "BAAI/bge-small-zh-v1.5"
    local_embed_batch_size: int = 64
    local_query_prefix: str = ""
    local_doc_prefix: str = ""

    # Data
    docs_dir: str = "law/法律（全）"
    data_dir: str = "data"
    chunks_path: str = "data/chunks.jsonl"
    reference_graph_path: str = "data/reference_graph.json"

    # Vector store
    qdrant_path: str = "qdrant_data"
    qdrant_collection: str = "law_knowledge"

    # DeepSeek: OpenAI-compatible chat only (answers). Embeddings are always local.
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str | None = None
    deepseek_chat_model: str = "deepseek-v4-pro"
    deepseek_timeout_s: float = 60.0
    deepseek_max_retries: int = 3

    # Retrieval
    vector_top_k: int = 20
    final_top_n: int = 6

    # Hybrid-on-Demand: cosine similarity threshold below which BM25 is activated.
    # Set to 0.0 to always use BM25 (legacy behaviour); 1.0 to force vector-only.
    # Default 0.75 based on empirical calibration on the 100-sample ablation set.
    hybrid_confidence_threshold: float = 0.75

    # Generation
    temperature: float = 0.2
    answer_max_tokens: int = 700


settings = Settings()
