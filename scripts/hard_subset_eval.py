"""
Hard Subset Evaluation
======================
评估 cross_chapter_eval.json 中的 pairs 在不同 hard subset 维度上的分布。
测量：dense retrieval HIT rate 在各子集上的差异。

运行: .venv/Scripts/python.exe scripts/hard_subset_eval.py
"""
import sys
import json
import re
import numpy as np
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_ROOT / "data" / "reference_graph.json"
EVAL_PATH = PROJECT_ROOT / "experiments" / "co_amendment" / "cross_chapter_eval.json"


def load_graph_edges():
    with open(GRAPH_PATH, encoding="utf-8") as f:
        graph = json.load(f)
    edges = set()
    by_article = graph.get("by_article", {})
    for cited_key, citations in by_article.items():
        for cit in citations:
            citing_key = f"《{cit['citing_law']}》{cit['citing_article']}"
            edges.add((cited_key, citing_key))
            edges.add((citing_key, cited_key))
    return edges


def tokenize_jieba(text):
    import jieba
    return set(w for w in jieba.cut(text) if len(w.strip()) > 0)


def jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


def main():
    print("=" * 60)
    print("Hard Subset Evaluation")
    print("=" * 60)

    # Load evaluation data
    with open(EVAL_PATH, encoding="utf-8") as f:
        eval_data = json.load(f)
    samples = eval_data["samples"]
    print(f"\n  Total cross-chapter pairs: {len(samples)}")
    print(f"  HIT: {eval_data['hit_count']}  MISS: {eval_data['miss_count']}")

    # Load graph edges
    print("  Loading reference graph...")
    graph_edges = load_graph_edges()
    print(f"  Graph edges: {len(graph_edges)}")

    # Classify each pair by hard subset dimensions
    # 1. non_neighbor_graph: no citation edge
    # 2. cross_topic: different amendments
    # 3. low_lexical_overlap: jieba Jaccard < median

    # First pass: compute Jaccard for all pairs
    print("  Computing lexical overlap (jieba)...")
    jaccards = []
    for s in samples:
        t_tokens = tokenize_jieba(s.get("target_text", ""))
        c_tokens = tokenize_jieba(s.get("candidate_text", ""))
        jaccards.append(jaccard(t_tokens, c_tokens))

    median_jac = np.median(jaccards)
    print(f"  Median Jaccard: {median_jac:.4f}")

    # Classify
    for i, s in enumerate(samples):
        target = s["target"]
        candidate = s["candidate"]

        # Dimension 1: graph edge
        s["has_graph_edge"] = (target, candidate) in graph_edges

        # Dimension 2: same amendment (already in data as "amendments")
        s["same_amendment"] = len(s.get("amendments", [])) > 0

        # Dimension 3: lexical overlap
        s["jaccard"] = jaccards[i]
        s["low_lexical"] = jaccards[i] < median_jac

    # Compute HIT rates by subset
    print(f"\n{'=' * 60}")
    print("  HIT Rate by Subset Dimension")
    print(f"{'=' * 60}")

    def hit_rate(subset_samples):
        if not subset_samples:
            return 0.0, 0
        hits = sum(1 for s in subset_samples if s["category"] == "HIT")
        return hits / len(subset_samples), len(subset_samples)

    # Overall
    overall_hr, overall_n = hit_rate(samples)
    print(f"\n  Overall:                    HIT rate = {overall_hr:.3f}  (n={overall_n})")

    # Dimension 1: Graph edge vs no graph edge
    with_edge = [s for s in samples if s["has_graph_edge"]]
    without_edge = [s for s in samples if not s["has_graph_edge"]]
    we_hr, we_n = hit_rate(with_edge)
    woe_hr, woe_n = hit_rate(without_edge)
    print(f"\n  [Graph Edge Dimension]")
    print(f"    With graph edge:          HIT rate = {we_hr:.3f}  (n={we_n})")
    print(f"    Without graph edge:       HIT rate = {woe_hr:.3f}  (n={woe_n})")
    print(f"    Delta:                    {we_hr - woe_hr:+.3f}")

    # Dimension 2: Same amendment vs different amendment
    same_amend = [s for s in samples if s["same_amendment"]]
    diff_amend = [s for s in samples if not s["same_amendment"]]
    sa_hr, sa_n = hit_rate(same_amend)
    da_hr, da_n = hit_rate(diff_amend)
    print(f"\n  [Amendment Dimension]")
    print(f"    Same amendment:           HIT rate = {sa_hr:.3f}  (n={sa_n})")
    print(f"    Different amendment:      HIT rate = {da_hr:.3f}  (n={da_n})")
    print(f"    Delta:                    {sa_hr - da_hr:+.3f}")

    # Dimension 3: Lexical overlap
    high_lex = [s for s in samples if not s["low_lexical"]]
    low_lex = [s for s in samples if s["low_lexical"]]
    hl_hr, hl_n = hit_rate(high_lex)
    ll_hr, ll_n = hit_rate(low_lex)
    print(f"\n  [Lexical Overlap Dimension]")
    print(f"    High overlap (>=median):  HIT rate = {hl_hr:.3f}  (n={hl_n})")
    print(f"    Low overlap (<median):    HIT rate = {ll_hr:.3f}  (n={ll_n})")
    print(f"    Delta:                    {hl_hr - ll_hr:+.3f}")

    # Combined: hardest subset (no graph edge + low lexical)
    hardest = [s for s in samples if not s["has_graph_edge"] and s["low_lexical"]]
    easiest = [s for s in samples if s["has_graph_edge"] and not s["low_lexical"]]
    h_hr, h_n = hit_rate(hardest)
    e_hr, e_n = hit_rate(easiest)
    print(f"\n  [Combined: Hardest vs Easiest]")
    print(f"    Easiest (graph+high-lex):  HIT rate = {e_hr:.3f}  (n={e_n})")
    print(f"    Hardest (no-graph+low-lex): HIT rate = {h_hr:.3f}  (n={h_n})")
    print(f"    Delta:                    {e_hr - h_hr:+.3f}")

    # Per-law breakdown for hardest subset
    print(f"\n  [Hardest Subset Per-Law Breakdown]")
    hardest_by_law = defaultdict(list)
    for s in hardest:
        hardest_by_law[s["law"]].append(s)
    for law_name in sorted(hardest_by_law.keys()):
        law_samples = hardest_by_law[law_name]
        hr, n = hit_rate(law_samples)
        short = law_name.replace("中华人民共和国", "").replace("法", "")[:12]
        print(f"    {short:<20} HIT rate = {hr:.3f}  (n={n})")

    # Save results
    results = {
        "total": len(samples),
        "median_jaccard": float(median_jac),
        "overall": {"hit_rate": overall_hr, "n": overall_n},
        "graph_edge": {
            "with_edge": {"hit_rate": we_hr, "n": we_n},
            "without_edge": {"hit_rate": woe_hr, "n": woe_n},
            "delta": we_hr - woe_hr,
        },
        "amendment": {
            "same": {"hit_rate": sa_hr, "n": sa_n},
            "different": {"hit_rate": da_hr, "n": da_n},
            "delta": sa_hr - da_hr,
        },
        "lexical_overlap": {
            "high": {"hit_rate": hl_hr, "n": hl_n},
            "low": {"hit_rate": ll_hr, "n": ll_n},
            "delta": hl_hr - ll_hr,
        },
        "combined": {
            "easiest": {"hit_rate": e_hr, "n": e_n},
            "hardest": {"hit_rate": h_hr, "n": h_n},
            "delta": e_hr - h_hr,
        },
    }
    out_path = PROJECT_ROOT / "data" / "hard_subset_eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()
