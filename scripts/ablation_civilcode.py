#!/usr/bin/env python3
"""
2×2 Factorial Ablation — Civil Code Art. 510 (民法典 第五百一十条)

Hard-GT only: Ground Truth = Graph BFS topological citations (25 unique articles).
No Soft-GT.

Purpose: Dense graph scenario (25 edges) — third domain for cross-domain comparison.

Groups:
  A: All Civil Code articles (no graph, no filter)       — baseline
  B: All Civil Code → domain keyword filter              — semantic only
  C: Graph BFS 25 candidates (no filter)                 — topological only
  D: Graph BFS → keyword filter                          — full pipeline

Usage:
    python scripts/ablation_civilcode.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import io
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────

TARGET_LAW = "中华人民共和国民法典"
TARGET_ARTICLE = "第五百一十条"
DIRECTION_DESC = "合同条款补充确定规则调整 (contract_term_supplement_adjustment)"

OLD_TEXT = (
    "第五百一十条 合同生效后，当事人就质量、价款或者报酬、履行地点等内容"
    "没有约定或者约定不明确的，可以协议补充；不能达成补充协议的，"
    "按照合同相关条款或者交易习惯确定。"
)

# Hard-GT: Graph BFS topological citations (deduplicated, 25 unique)
GRAPH_GT = {
    "第五百八十二条", "第六百条", "第六百一十六条", "第六百一十九条",
    "第六百二十六条", "第六百二十七条", "第六百二十八条", "第六百三十七条",
    "第六百七十四条", "第六百七十五条", "第七百条", "第七百二十一条",
    "第七百三十条", "第七百五十七条", "第七百八十二条", "第八百三十一条",
    "第八百三十三条", "第八百五十八条", "第八百六十一条", "第八百七十五条",
    "第八百八十九条", "第九百条", "第九百五十五条", "第九百六十三条",
    "第九百七十六条",
}

GROUND_TRUTH = GRAPH_GT

RUNS_PER_GROUP = 3
OUTPUT_CSV = Path("data/ablation_civilcode_comparison.csv")
OUTPUT_JSON = Path("data/ablation_civilcode_results.json")

SYSTEM_PROMPT = """你是一个立法影响分析专家。你的任务是：给定目标条文的"旧版原文"和"立法偏移方向"，分析该条文修订后，同一部法律内部哪些其他条文会受到波及影响。

约束：
- 只能从提供的"候选条文"列表中选择受波及的条文，不得编造未出现的条文。
- 必须说明传导逻辑：目标条文的修订内容如何导致候选条文出现适用矛盾、逻辑冲突或需要配套修改。
- reasoning 必须简洁，控制在 100 字以内，只说核心传导逻辑。
- 若多个候选均受影响，全部返回，不设数量上限。
- 风险等级判定标准：
  - High：目标条文的偏移直接导致候选条文的适用条件、权利义务或程序要求发生实质性矛盾或失效
  - Medium：目标条文的偏移与候选条文存在逻辑张力，可能需要司法解释或配套修改
  - Low：目标条文的偏移对候选条文影响轻微，或仅涉及表述一致性
- 输出必须是合法的 JSON 数组，每项包含：article_key（格式"《法律名》第X条"）、risk_level（High/Medium/Low）、reasoning（传导逻辑说明）。
- 如果候选列表中没有任何条文会受波及，返回空数组 []。

输出格式（严格 JSON，不要输出任何其他内容）：
[
  {
    "article_key": "《法律名》第X条",
    "risk_level": "High",
    "reasoning": "传导逻辑说明"
  }
]"""

# Civil Code contract domain keywords
CIVILCODE_KEYWORDS = {
    "当事人", "合同", "约定", "质量", "价款", "报酬",
    "履行地点", "交易习惯", "补充协议", "协议补充",
    "标的", "数量", "履行方式", "条款", "合同条款",
    "不明确", "补充", "出卖人", "买受人",
    "承揽人", "定作人", "承运人", "托运人",
}


# ────────────────────────────────────────────────────────────
# Utility functions
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


def art_sort_key(item: dict) -> int:
    m = re.search(r"第([零一二三四五六七八九十百千\d]+)条", item["article"])
    if not m:
        return 99999
    s = m.group(1)
    cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if s.isdigit():
        return int(s)
    if s in cn:
        return cn[s]
    if "十" in s:
        parts = s.split("十")
        tens = cn.get(parts[0], 1) * 10 if parts[0] else 10
        ones = cn.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens + ones
    return 99999


def estimate_tokens(text: str) -> int:
    chinese = len(re.findall(r"[一-鿿]", text))
    other = len(text) - chinese
    return int(chinese * 1.5 + other * 0.3)


def parse_llm_response(response: str) -> list[dict]:
    response = response.strip()
    if not response or response == "[]":
        return []
    m = re.search(r"```json\s*([\s\S]*?)\s*```", response)
    json_str = m.group(1).strip() if m else response
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "impacts" in data:
            return data["impacts"]
        return []
    except json.JSONDecodeError:
        m2 = re.search(r"\[\s*\{[\s\S]*\}\s*\]", json_str)
        if m2:
            try:
                return json.loads(m2.group(0))
            except json.JSONDecodeError:
                pass
        return []


def extract_article_numbers(parsed: list[dict]) -> set[str]:
    result = set()
    for item in parsed:
        key = item.get("article_key", "")
        m = re.search(r"第[零一二三四五六七八九十百千\d]+条", key)
        if m:
            result.add(m.group(0))
    return result


def jaccard_similarity(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


# ────────────────────────────────────────────────────────────
# Keyword filtering
# ────────────────────────────────────────────────────────────


def filter_by_keywords(
    candidates: list[dict], keywords: set[str]
) -> tuple[list[dict], list[dict]]:
    passed, filtered_out = [], []
    for cand in candidates:
        text = cand["text"]
        matched = {kw for kw in keywords if kw in text}
        entry = {**cand, "_keywords": matched}
        if matched:
            passed.append(entry)
        else:
            filtered_out.append(entry)
    return passed, filtered_out


# ────────────────────────────────────────────────────────────
# Graph BFS (deduplicated)
# ────────────────────────────────────────────────────────────


def get_graph_candidates(law_title: str, article_no: str,
                         max_depth: int = 1) -> list[dict]:
    target_key = f"《{law_title}》{article_no}"

    with open("data/reference_graph.json", "r", encoding="utf-8") as f:
        graph = json.load(f)
    by_article = graph.get("by_article", {})

    if target_key not in by_article:
        return []

    visited = set()
    queue = [(target_key, 0)]
    candidates = []
    seen_articles = set()

    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > max_depth:
            continue
        visited.add(current)

        if current != target_key and depth > 0:
            m = re.search(r"《(.+?)》(.+)", current)
            if m:
                citing_law, citing_article = m.group(1), m.group(2)
                if citing_article not in seen_articles:
                    text = _get_article_text(citing_law, citing_article)
                    if text:
                        candidates.append({
                            "law": citing_law,
                            "article": citing_article,
                            "text": text,
                            "_depth": depth,
                        })
                        seen_articles.add(citing_article)

        if current in by_article:
            for edge in by_article[current]:
                next_key = f"{edge['citing_law']}{edge['citing_article']}"
                if next_key not in visited:
                    queue.append((next_key, depth + 1))

    return candidates


def _get_article_text(law: str, article: str) -> str | None:
    with open("data/chunks.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("doc_title") == law and d.get("article_no") == article:
                return d.get("text", "")
    return None


# ────────────────────────────────────────────────────────────
# LLM call
# ────────────────────────────────────────────────────────────


def build_user_prompt(candidates: list[dict]) -> str:
    lines = [
        f"目标条文：《{TARGET_LAW}》{TARGET_ARTICLE}（旧版）",
        f"条文原文：{OLD_TEXT.strip()}",
        f"立法偏移方向：{DIRECTION_DESC}",
        "偏移幅度：中等",
        "",
        f"候选下游条文（仅能从以下列表中选择，共 {len(candidates)} 条）：",
    ]
    for i, c in enumerate(candidates, 1):
        lines.append(f"[{i}] 《{c['law']}》{c['article']}")
        lines.append(f"    内容：{c['text'].strip()[:80]}")
    lines.append("")
    lines.append("请分析目标条文的偏移会波及哪些候选条文，返回 JSON 数组。")
    return "\n".join(lines)


def run_single(candidates: list[dict]) -> dict[str, Any]:
    from rag_contract.llm_client import chat_answer

    user_prompt = build_user_prompt(candidates)
    prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user_prompt)

    t0 = time.perf_counter()
    try:
        response = chat_answer(SYSTEM_PROMPT, user_prompt, max_tokens=4000)
    except Exception as e:
        return {"error": str(e), "prompt_tokens": prompt_tokens}
    latency_ms = (time.perf_counter() - t0) * 1000

    parsed = parse_llm_response(response)
    predicted = extract_article_numbers(parsed)
    hits = predicted & GROUND_TRUTH
    precision = len(hits) / len(predicted) if predicted else 0.0
    recall = len(hits) / len(GROUND_TRUTH) if GROUND_TRUTH else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    logic_density = precision / (prompt_tokens / 1000) if prompt_tokens > 0 else 0.0

    return {
        "predicted": sorted(predicted),
        "hits": sorted(hits),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "logic_density": round(logic_density, 4),
        "prompt_tokens": prompt_tokens,
        "latency_ms": round(latency_ms, 1),
        "raw_response": response[:2000] if response else "",
    }


# ────────────────────────────────────────────────────────────
# Aggregation
# ────────────────────────────────────────────────────────────


def aggregate_runs(runs: list[dict]) -> dict:
    valid = [r for r in runs if "error" not in r]
    if not valid:
        return {"error": "all runs failed"}

    def avg(key):
        return sum(r[key] for r in valid) / len(valid)

    def stdev(key):
        if len(valid) < 2:
            return 0.0
        mean = avg(key)
        return (sum((r[key] - mean) ** 2 for r in valid) / (len(valid) - 1)) ** 0.5

    pairs = []
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            pairs.append(jaccard_similarity(set(valid[i]["predicted"]),
                                            set(valid[j]["predicted"])))
    stability = sum(pairs) / len(pairs) if pairs else 1.0

    return {
        "avg_precision": round(avg("precision"), 4),
        "avg_recall": round(avg("recall"), 4),
        "avg_f1": round(avg("f1"), 4),
        "avg_logic_density": round(avg("logic_density"), 4),
        "avg_stability": round(stability, 4),
        "avg_latency_ms": round(avg("latency_ms"), 1),
        "avg_prompt_tokens": round(avg("prompt_tokens")),
        "sd_precision": round(stdev("precision"), 4),
        "sd_recall": round(stdev("recall"), 4),
        "sd_f1": round(stdev("f1"), 4),
        "sd_logic_density": round(stdev("logic_density"), 4),
    }


# ────────────────────────────────────────────────────────────
# Main experiment
# ────────────────────────────────────────────────────────────


def run_group(label: str, candidates: list[dict]) -> tuple[dict, list[dict]]:
    print(f"\n{'='*60}")
    print(f"Group: {label}")
    print(f"  Candidates: {len(candidates)}")
    for c in candidates[:8]:
        print(f"    {c['article']}")
    if len(candidates) > 8:
        print(f"    ... and {len(candidates)-8} more")

    runs = []
    for i in range(RUNS_PER_GROUP):
        print(f"\n  ── Run {i+1}/{RUNS_PER_GROUP} ──")
        result = run_single(candidates)
        if "error" in result:
            print(f"  ✗ Error: {result['error']}")
        else:
            print(f"  Predicted: {result['predicted']}")
            print(f"  Hits: {result['hits']}")
            print(f"  P={result['precision']:.3f} R={result['recall']:.3f} "
                  f"F1={result['f1']:.3f} LD={result['logic_density']:.3f}")
        runs.append(result)
        time.sleep(2)

    agg = aggregate_runs(runs)
    return agg, runs


def main():
    print("2×2 Factorial Ablation — Civil Code Art. 510 (Hard-GT Only)")
    print("=" * 60)
    print(f"Target: {TARGET_LAW} {TARGET_ARTICLE}")
    print(f"Direction: {DIRECTION_DESC}")
    print(f"Ground Truth (Hard-GT): {len(GROUND_TRUTH)} articles")
    print(f"Keywords: {len(CIVILCODE_KEYWORDS)}")
    print(f"Total LLM calls: 4 groups × {RUNS_PER_GROUP} = {4 * RUNS_PER_GROUP}")

    # Load all law articles
    all_articles = load_law_articles(TARGET_LAW)
    all_articles.sort(key=art_sort_key)
    print(f"\n{TARGET_LAW}: {len(all_articles)} active articles (excluding Art.510)")

    # Graph BFS (deduplicated)
    graph_candidates = get_graph_candidates(TARGET_LAW, TARGET_ARTICLE, max_depth=1)
    graph_candidates.sort(key=art_sort_key)
    print(f"Graph BFS (depth=1, deduped): {len(graph_candidates)} candidates")
    for c in graph_candidates:
        print(f"    {c['article']}")

    # Keyword filter on all articles
    passed_kw, filtered_kw = filter_by_keywords(all_articles, CIVILCODE_KEYWORDS)
    keyword_candidates = sorted(passed_kw, key=art_sort_key)
    print(f"\nKeyword filter: {len(keyword_candidates)} passed / {len(all_articles)} total")

    # Build 4 groups
    group_a = all_articles
    group_b = keyword_candidates
    group_c = graph_candidates

    # D: graph candidates that also match keywords
    passed_d, _ = filter_by_keywords(graph_candidates, CIVILCODE_KEYWORDS)
    group_d = sorted(passed_d, key=art_sort_key)
    if not group_d:
        print("  ⚠ Group D: no graph candidates match keywords, using all graph")
        group_d = graph_candidates

    print(f"\nGroup sizes: A={len(group_a)}, B={len(group_b)}, "
          f"C={len(group_c)}, D={len(group_d)}")

    # Run 4 groups
    results = {
        "experiment": "factorial_ablation_civilcode_hard_gt",
        "target": f"{TARGET_LAW} {TARGET_ARTICLE}",
        "direction": DIRECTION_DESC,
        "ground_truth": {
            "type": "Hard-GT only (graph topological citations)",
            "total": len(GROUND_TRUTH),
            "articles": sorted(GROUND_TRUTH),
        },
        "keywords": sorted(CIVILCODE_KEYWORDS),
        "groups": {},
    }

    csv_rows = []

    for label, candidates, group_key in [
        ("A: Unconstrained", group_a, "A"),
        ("B: Keywords Only", group_b, "B"),
        ("C: Graph Only", group_c, "C"),
        ("D: Graph + Keywords", group_d, "D"),
    ]:
        agg, runs = run_group(label, candidates)

        if "error" not in agg:
            print(f"\n  ── {label} Summary ──")
            print(f"  Prec={agg['avg_precision']:.4f}  Recall={agg['avg_recall']:.4f}  "
                  f"F1={agg['avg_f1']:.4f}  LD={agg['avg_logic_density']:.4f}")

        results["groups"][group_key] = {
            "label": label,
            "candidate_count": len(candidates),
            "candidates": [c["article"] for c in candidates],
            "aggregated": agg,
            "runs": runs,
        }

        csv_rows.append({
            "group": group_key,
            "label": label,
            "candidate_count": len(candidates),
            "avg_precision": agg.get("avg_precision", 0),
            "avg_recall": agg.get("avg_recall", 0),
            "avg_f1": agg.get("avg_f1", 0),
            "avg_logic_density": agg.get("avg_logic_density", 0),
            "avg_prompt_tokens": agg.get("avg_prompt_tokens", 0),
            "avg_latency_ms": agg.get("avg_latency_ms", 0),
            "avg_stability": agg.get("avg_stability", 0),
            "sd_precision": agg.get("sd_precision", 0),
            "sd_recall": agg.get("sd_recall", 0),
            "sd_f1": agg.get("sd_f1", 0),
            "sd_logic_density": agg.get("sd_logic_density", 0),
        })

    # Save CSV
    if csv_rows:
        with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\nCSV saved to {OUTPUT_CSV}")

    # Save JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"JSON saved to {OUTPUT_JSON}")

    # Final summary
    print(f"\n{'='*75}")
    print("Final Comparison (Hard-GT Only)")
    print(f"{'='*75}")
    print(f"{'Group':<25} {'Cands':>6} {'Prec':>8} {'R_hard':>8} "
          f"{'F1':>8} {'Density':>8} {'Tokens':>8}")
    print(f"{'─'*75}")
    for row in csv_rows:
        print(f"{row['label']:<25} {row['candidate_count']:>6} "
              f"{row['avg_precision']:>8.4f} {row['avg_recall']:>8.4f} "
              f"{row['avg_f1']:>8.4f} {row['avg_logic_density']:>8.4f} "
              f"{row['avg_prompt_tokens']:>8}")


if __name__ == "__main__":
    main()
