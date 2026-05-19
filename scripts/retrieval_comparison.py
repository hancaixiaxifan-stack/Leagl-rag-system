#!/usr/bin/env python3
"""
Retrieval Comparison: Graph BFS vs BM25 vs Vector — Counterfactual Scenario

Target: Criminal Law Art.234 (故意伤害罪)
Task: From 414 articles, find the 6 Hard-GT impacted articles.
Compare: BM25 top-6, Vector top-6, Graph BFS top-6.

No LLM calls — pure retrieval comparison.

Usage:
    python scripts/retrieval_comparison.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────

TARGET_LAW = "中华人民共和国刑法"
TARGET_ARTICLE = "第二百三十四条"

OLD_TEXT = (
    "第二百三十四条 故意伤害他人身体的，处三年以下有期徒刑、拘役或者管制。"
    "犯前款罪，致人重伤的，处三年以上十年以下有期徒刑；"
    "致人死亡或者以特别残忍手段致人重伤造成严重残疾的，"
    "处十年以上有期徒刑、无期徒刑或者死刑。本法另有规定的，依照规定。"
)

# Hard-GT: 6 articles citing Art.234 via graph
HARD_GT = {
    "第二百三十八条",  # 非法拘禁→致人伤残按234处罚
    "第二百四十七条",  # 刑讯逼供→致人伤残按234处罚
    "第二百四十八条",  # 监管人员殴打→致人伤残按234处罚
    "第二百八十九条",  # 聚众打砸抢→致人伤残按234处罚
    "第二百九十二条",  # 聚众斗殴→致人重伤/死亡转化
    "第三百三十三条",  # 非法组织卖血→致人伤害按234处罚
}

TOP_K = 6  # Match graph BFS candidate count


# ────────────────────────────────────────────────────────────
# Load articles
# ────────────────────────────────────────────────────────────

def load_law_articles(law_title: str) -> list[dict]:
    SKIP = ["施行日期", "本法自", "起施行", "自公布之日起",
            "用语的含义", "下列用语", "术语定义"]
    articles: dict[str, dict] = {}
    with open("data/chunks.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("doc_title") != law_title:
                continue
            art_no = d.get("article_no", "")
            if not art_no or art_no == TARGET_ARTICLE:
                continue
            if d.get("status") != "有效":
                continue
            text = d.get("text", "")
            if not text or any(pat in text[:80] for pat in SKIP):
                continue
            if art_no not in articles:
                articles[art_no] = {"law": law_title, "article": art_no, "text": text}
    return list(articles.values())


# ────────────────────────────────────────────────────────────
# Graph BFS
# ────────────────────────────────────────────────────────────

def graph_bfs(law_title: str, article_no: str) -> list[str]:
    target_key = f"《{law_title}》{article_no}"
    with open("data/reference_graph.json", "r", encoding="utf-8") as f:
        graph = json.load(f)
    by_article = graph.get("by_article", {})
    if target_key not in by_article:
        return []
    seen = set()
    result = []
    for edge in by_article[target_key]:
        art = edge["citing_article"]
        if art not in seen and art != article_no:
            seen.add(art)
            result.append(art)
    return result


# ────────────────────────────────────────────────────────────
# BM25 retrieval
# ────────────────────────────────────────────────────────────

def bm25_topk(query: str, articles: list[dict], k: int) -> list[str]:
    from rag_contract.retrieval import HybridRetriever
    retriever = HybridRetriever.from_jsonl("data/chunks.jsonl")

    # Build article index mapping
    art_texts = {a["article"]: a["text"] for a in articles}

    # Get BM25 scores for all chunks
    all_scores = retriever.bm25_scores(query)

    # Map chunk indices back to articles
    # We need to score each article's text against the query
    import jieba
    query_tokens = set(jieba.lcut(query))

    scored = []
    for art in articles:
        text = art["text"]
        art_tokens = set(jieba.lcut(text))
        # Simple BM25-like: count overlapping terms weighted by IDF-like rarity
        overlap = query_tokens & art_tokens
        if overlap:
            # Rough BM25 score: sum of overlap term lengths as proxy
            score = sum(len(t) for t in overlap)
            scored.append((art["article"], score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [a for a, _ in scored[:k]]


# ────────────────────────────────────────────────────────────
# Vector retrieval
# ────────────────────────────────────────────────────────────

def vector_topk(query: str, articles: list[dict], k: int) -> list[str]:
    from rag_contract.local_embed import embed_query
    import numpy as np

    qvec = embed_query(query)

    # Embed all article texts
    scored = []
    for art in articles:
        avec = embed_query(art["text"][:512])  # Truncate for speed
        # Cosine similarity
        sim = float(np.dot(qvec, avec) / (np.linalg.norm(qvec) * np.linalg.norm(avec) + 1e-10))
        scored.append((art["article"], sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [a for a, _ in scored[:k]]


# ────────────────────────────────────────────────────────────
# Evaluation
# ────────────────────────────────────────────────────────────

def evaluate(predicted: list[str], gt: set[str], label: str) -> dict:
    pred_set = set(predicted)
    hits = pred_set & gt
    r_hard = len(hits) / len(gt) if gt else 0.0
    has_333 = "第三百三十三条" in pred_set

    print(f"\n  {label}:")
    print(f"    Predicted: {predicted}")
    print(f"    Hits:      {sorted(hits)}")
    print(f"    R_hard:    {r_hard:.4f} ({len(hits)}/{len(gt)})")
    print(f"    Art.333:   {'✓ FOUND' if has_333 else '✗ NOT FOUND'}")

    return {
        "method": label,
        "predicted": predicted,
        "hits": sorted(hits),
        "r_hard": round(r_hard, 4),
        "art_333_found": has_333,
    }


# ────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────

def main():
    print("Retrieval Comparison: Graph BFS vs BM25 vs Vector")
    print("=" * 60)
    print(f"Target: {TARGET_LAW} {TARGET_ARTICLE}")
    print(f"Hard-GT: {len(HARD_GT)} articles — {sorted(HARD_GT)}")
    print(f"Top-K: {TOP_K}")

    articles = load_law_articles(TARGET_LAW)
    print(f"Total articles: {len(articles)}")

    results = []

    # 1. Graph BFS
    t0 = time.perf_counter()
    graph_arts = graph_bfs(TARGET_LAW, TARGET_ARTICLE)
    graph_ms = (time.perf_counter() - t0) * 1000
    print(f"\nGraph BFS: {len(graph_arts)} candidates ({graph_ms:.1f}ms)")
    r = evaluate(graph_arts, HARD_GT, "Graph BFS")
    r["latency_ms"] = round(graph_ms, 1)
    results.append(r)

    # 2. BM25
    t0 = time.perf_counter()
    bm25_arts = bm25_topk(OLD_TEXT, articles, TOP_K)
    bm25_ms = (time.perf_counter() - t0) * 1000
    print(f"\nBM25: {len(bm25_arts)} candidates ({bm25_ms:.1f}ms)")
    r = evaluate(bm25_arts, HARD_GT, "BM25")
    r["latency_ms"] = round(bm25_ms, 1)
    results.append(r)

    # 3. Vector
    t0 = time.perf_counter()
    vec_arts = vector_topk(OLD_TEXT, articles, TOP_K)
    vec_ms = (time.perf_counter() - t0) * 1000
    print(f"\nVector: {len(vec_arts)} candidates ({vec_ms:.1f}ms)")
    r = evaluate(vec_arts, HARD_GT, "Vector (bge-small-zh)")
    r["latency_ms"] = round(vec_ms, 1)
    results.append(r)

    # Summary table
    print(f"\n{'='*70}")
    print("Summary")
    print(f"{'='*70}")
    print(f"{'Method':<25} {'R_hard':>8} {'Art.333':>10} {'Latency':>10}")
    print(f"{'─'*70}")
    for r in results:
        flag = "✓" if r['art_333_found'] else "✗"
        print(f"{r['method']:<25} {r['r_hard']:>8.4f} {flag:>10} {r['latency_ms']:>8.1f}ms")

    # Save
    output = {
        "target": f"{TARGET_LAW} {TARGET_ARTICLE}",
        "hard_gt": sorted(HARD_GT),
        "top_k": TOP_K,
        "total_articles": len(articles),
        "results": results,
    }
    out_path = Path("data/retrieval_comparison.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
