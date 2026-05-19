#!/usr/bin/env python3
"""
Batch Evaluation — Large-Scale R_hard Test (multi-law)

Usage:
    python scripts/batch_evaluation.py --law 刑法 --sample 25 --seed 42
    python scripts/batch_evaluation.py --law 民航法 --sample all --seed 42
    python scripts/batch_evaluation.py --law 民法典 --sample 25 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
import io
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from rag_contract.lineage import SENSITIVE_WORD_CATEGORIES, classify_word

# ────────────────────────────────────────────────────────────
# Law registry
# ────────────────────────────────────────────────────────────

LAW_REGISTRY = {
    "刑法": {
        "full_name": "中华人民共和国刑法",
        "csv": "data/batch_eval_criminal.csv",
        "json": "data/batch_eval_criminal.json",
    },
    "民航法": {
        "full_name": "中华人民共和国民用航空法",
        "csv": "data/batch_eval_aviation.csv",
        "json": "data/batch_eval_aviation.json",
    },
    "民法典": {
        "full_name": "中华人民共和国民法典",
        "csv": "data/batch_eval_civilcode.csv",
        "json": "data/batch_eval_civilcode.json",
    },
}

RUNS_PER_ARTICLE = 3

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


# ────────────────────────────────────────────────────────────
# Utility functions (reused from ablation scripts)
# ────────────────────────────────────────────────────────────


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


CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_to_arabic(s: str) -> int:
    if not s:
        return -1
    if s.isdigit():
        return int(s)
    total, section = 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            section = CN_DIGITS[ch]
        elif ch == "十":
            section = section * 10 if section else 10
            total += section
            section = 0
        elif ch == "百":
            section = section * 100 if section else 100
            total += section
            section = 0
        elif ch == "千":
            section = section * 1000 if section else 1000
            total += section
            section = 0
    total += section
    return total if total > 0 else -1


def arabic_to_cn(num: int) -> str:
    if num <= 0:
        return str(num)
    if num < 10:
        return "零一二三四五六七八九"[num]
    if num == 10:
        return "十"
    if num < 20:
        return "十" + arabic_to_cn(num - 10)
    if num < 100:
        tens, ones = divmod(num, 10)
        return arabic_to_cn(tens) + "十" + (arabic_to_cn(ones) if ones else "")
    if num < 1000:
        h, rest = divmod(num, 100)
        head = arabic_to_cn(h) + "百"
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + arabic_to_cn(rest)
        if rest < 20:
            return head + "一十" + (arabic_to_cn(rest - 10) if rest > 10 else "")
        return head + arabic_to_cn(rest)
    if num < 10000:
        th, rest = divmod(num, 1000)
        head = arabic_to_cn(th) + "千"
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + arabic_to_cn(rest)
        if rest < 100:
            return head + "零" + arabic_to_cn(rest)
        return head + arabic_to_cn(rest)
    return str(num)


def normalize_art_no(article: str) -> str:
    """尝试将条文编号在阿拉伯/中文格式间转换，返回另一种格式。"""
    m = re.search(r"第(\d+)条", article)
    if m:
        return "第" + arabic_to_cn(int(m.group(1))) + "条"
    m = re.search(r"第([零一二三四五六七八九十百千]+)条", article)
    if m:
        n = cn_to_arabic(m.group(1))
        if n > 0:
            return f"第{n}条"
    return article


def canonical_art_set(articles: set[str]) -> set[str]:
    """将条文编号集合归一化为中文格式，用于跨格式比较。"""
    result = set()
    for a in articles:
        m = re.search(r"第(\d+)条", a)
        if m:
            result.add("第" + arabic_to_cn(int(m.group(1))) + "条")
        else:
            result.add(a)
    return result


def get_article_text(law: str, article: str) -> str | None:
    alt = normalize_art_no(article)
    with open("data/chunks.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("doc_title") != law:
                continue
            art_no = d.get("article_no", "")
            if art_no == article or art_no == alt:
                return d.get("text", "")
    return None


def art_sort_key(article_no: str) -> int:
    m = re.search(r"第([零一二三四五六七八九十百千\d]+)条", article_no)
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


# ────────────────────────────────────────────────────────────
# Graph BFS (reused from ablation scripts)
# ────────────────────────────────────────────────────────────


def get_graph_candidates(law_title: str, article_no: str,
                         by_article: dict, max_depth: int = 1) -> list[dict]:
    target_key = f"《{law_title}》{article_no}"
    if target_key not in by_article:
        return []

    visited = set()
    queue = [(target_key, 0)]
    candidates = []

    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > max_depth:
            continue
        visited.add(current)

        if current != target_key and depth > 0:
            m = re.search(r"《(.+?)》(.+)", current)
            if m:
                citing_law, citing_article = m.group(1), m.group(2)
                text = get_article_text(citing_law, citing_article)
                if text:
                    candidates.append({
                        "law": citing_law,
                        "article": citing_article,
                        "text": text,
                        "_depth": depth,
                    })

        if current in by_article:
            for edge in by_article[current]:
                next_key = f"{edge['citing_law']}{edge['citing_article']}"
                if next_key not in visited:
                    queue.append((next_key, depth + 1))

    return candidates


# ────────────────────────────────────────────────────────────
# Explicit Constraint Filter (ECF) — 194-term lexicon, two-tier design
# Matches main experiment pipeline: classify_word from rag_contract.lineage
# ────────────────────────────────────────────────────────────

# Flatten all classified terms for fast lookup
_ALL_CLASSIFIED_TERMS: set[str] = set()
for _terms in SENSITIVE_WORD_CATEGORIES.values():
    _ALL_CLASSIFIED_TERMS.update(_terms)


def ecf_classify_text(text: str) -> set[str]:
    """Return set of classified terms found in text."""
    found = set()
    for term in _ALL_CLASSIFIED_TERMS:
        if term in text:
            found.add(term)
    return found


def ecf_filter_candidates(candidates: list[dict],
                          shift_category: str | None = None) -> list[dict]:
    """Two-tier ECF filtering (permissive strategy).

    Priority tier: retain if text contains terms from shift_category.
    Fallback tier: retain if text contains ANY classified term.
    Discard: only when text has zero classified terms.
    """
    passed = []
    for cand in candidates:
        text = cand["text"]
        found = ecf_classify_text(text)
        if not found:
            continue  # discard: no classified terms at all
        # Priority: overlap with shift-direction category
        if shift_category and shift_category in SENSITIVE_WORD_CATEGORIES:
            cat_terms = set(SENSITIVE_WORD_CATEGORIES[shift_category])
            if found & cat_terms:
                cand["_ecf_priority"] = True
                cand["_ecf_terms"] = sorted(found)
                passed.append(cand)
                continue
        # Fallback: any classified term
        cand["_ecf_priority"] = False
        cand["_ecf_terms"] = sorted(found)
        passed.append(cand)
    return passed


# ────────────────────────────────────────────────────────────
# LLM call
# ────────────────────────────────────────────────────────────


def build_user_prompt(target_law: str, target_article: str, target_text: str,
                      candidates: list[dict]) -> str:
    lines = [
        f"目标条文：《{target_law}》{target_article}",
        f"条文原文：{target_text.strip()[:200]}",
        "立法偏移方向：条文适用范围与处罚力度的调整",
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


def run_single(target_law: str, target_article: str, target_text: str,
               candidates: list[dict]) -> dict[str, Any]:
    from rag_contract.llm_client import chat_answer

    user_prompt = build_user_prompt(target_law, target_article, target_text, candidates)
    prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user_prompt)

    t0 = time.perf_counter()
    try:
        response = chat_answer(SYSTEM_PROMPT, user_prompt, max_tokens=4000)
    except Exception as e:
        return {"error": str(e), "prompt_tokens": prompt_tokens}
    latency_ms = (time.perf_counter() - t0) * 1000

    parsed = parse_llm_response(response)
    predicted = extract_article_numbers(parsed)

    return {
        "predicted": sorted(predicted),
        "prompt_tokens": prompt_tokens,
        "latency_ms": round(latency_ms, 1),
        "raw_response": response[:500] if response else "",
    }


# ────────────────────────────────────────────────────────────
# Sample criminal law articles with in-degree
# ────────────────────────────────────────────────────────────


def sample_law_articles(by_article: dict, law_full_name: str,
                        n: int | str, seed: int) -> tuple[list[str], int]:
    """Sample N articles with same-law in-degree. n='all' uses all eligible.

    Returns (sampled_articles, total_eligible_count).
    Only includes articles that have retrievable text in chunks.jsonl.
    """
    eligible = []

    for key, edges in by_article.items():
        if law_full_name not in key:
            continue
        same_law_edges = [e for e in edges if law_full_name in e.get("citing_law", "")]
        if not same_law_edges:
            continue
        m = re.search(r"第[零一二三四五六七八九十百千\d]+条", key)
        if m:
            art_no = m.group(0)
            if art_no not in eligible:
                # Only include if text is retrievable
                if get_article_text(law_full_name, art_no):
                    eligible.append(art_no)

    eligible.sort(key=art_sort_key)
    total = len(eligible)

    if n == "all":
        return eligible, total

    random.seed(seed)
    sampled = random.sample(eligible, min(int(n), len(eligible)))
    sampled.sort(key=art_sort_key)
    return sampled, total


# ────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(description="Batch R_hard evaluation")
    parser.add_argument("--law", default="刑法", choices=LAW_REGISTRY.keys(),
                        help="Target law (default: 刑法)")
    parser.add_argument("--sample", default="25",
                        help="Number of articles to sample, or 'all' (default: 25)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    return parser.parse_args()


def main():
    args = parse_args()
    law_cfg = LAW_REGISTRY[args.law]
    target_law = law_cfg["full_name"]
    output_csv = Path(law_cfg["csv"])
    output_json = Path(law_cfg["json"])

    print(f"Batch Evaluation — {args.law} ({target_law})")
    print("=" * 60)

    # Load reference graph
    with open("data/reference_graph.json", "r", encoding="utf-8") as f:
        graph = json.load(f)
    by_article = graph.get("by_article", {})

    # Sample articles
    sampled_articles, total_eligible = sample_law_articles(
        by_article, target_law, args.sample, args.seed
    )
    sample_label = f"all {total_eligible}" if args.sample == "all" else f"{len(sampled_articles)}/{total_eligible}"
    print(f"Sampled {sample_label} articles (seed={args.seed}):")
    for art in sampled_articles:
        gt_key = f"《{target_law}》{art}"
        gt_edges = [e for e in by_article.get(gt_key, [])
                    if target_law in e.get("citing_law", "")]
        print(f"  {art}: {len(gt_edges)} same-law in-edges")
    print()

    all_results = []
    csv_rows = []

    for idx, target_article in enumerate(sampled_articles, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(sampled_articles)}] Target: {target_law} {target_article}")

        # Get article text
        target_text = get_article_text(target_law, target_article)
        if not target_text:
            print(f"  ✗ No text found, skipping")
            continue

        # Get Hard-GT from reference graph (exclude self-referential edges)
        gt_key = f"《{target_law}》{target_article}"
        gt_edges = by_article.get(gt_key, [])
        hard_gt = set()
        for edge in gt_edges:
            if target_law in edge.get("citing_law", ""):
                if edge["citing_article"] != target_article:  # exclude a_i = a*
                    hard_gt.add(edge["citing_article"])
        print(f"  Hard-GT ({len(hard_gt)}): {sorted(hard_gt, key=art_sort_key)}")

        if not hard_gt:
            print(f"  ✗ No same-law in-edges, skipping")
            continue

        # Graph BFS candidates
        candidates = get_graph_candidates(target_law, target_article, by_article, max_depth=1)
        candidates.sort(key=lambda c: art_sort_key(c["article"]))
        print(f"  Graph BFS: {len(candidates)} candidates")

        if not candidates:
            print(f"  ✗ No BFS candidates, skipping")
            continue

        # ECF filtering (Group D) — two-tier, matching main pipeline
        c_set = {c["article"] for c in candidates}  # C = BFS candidates
        filtered = ecf_filter_candidates(candidates)
        d_set = {c["article"] for c in filtered}     # D = ECF-filtered
        c_equals_d = c_set == d_set
        print(f"  Graph BFS (C): {len(c_set)} candidates")
        print(f"  ECF filter  (D): {len(d_set)} candidates")
        print(f"  C = D: {c_equals_d}")

        # Run LLM
        runs = []
        for run_idx in range(RUNS_PER_ARTICLE):
            result = run_single(target_law, target_article, target_text, filtered)
            if "error" in result:
                print(f"  Run {run_idx+1}: ERROR — {result['error']}")
                runs.append(result)
                continue

            predicted = canonical_art_set(set(result["predicted"]))
            hits = predicted & hard_gt
            r_hard = len(hits) / len(hard_gt) if hard_gt else 0.0
            precision = len(hits) / len(predicted) if predicted else 0.0

            result["r_hard"] = round(r_hard, 4)
            result["precision"] = round(precision, 4)
            result["hits"] = sorted(hits)
            result["missed"] = sorted(hard_gt - predicted)
            runs.append(result)

            print(f"  Run {run_idx+1}: predicted={result['predicted']}, "
                  f"hits={result['hits']}, missed={result['missed']}, "
                  f"R_hard={r_hard:.3f}, Prec={precision:.3f}")

            time.sleep(2)

        # Aggregate
        valid_runs = [r for r in runs if "error" not in r and "r_hard" in r]
        if valid_runs:
            r_hard_values = [r["r_hard"] for r in valid_runs]
            prec_values = [r["precision"] for r in valid_runs]
            mean_r_hard = sum(r_hard_values) / len(r_hard_values)
            mean_prec = sum(prec_values) / len(prec_values)
            std_r_hard = (sum((x - mean_r_hard)**2 for x in r_hard_values)
                          / max(len(r_hard_values) - 1, 1)) ** 0.5

            # Collect all articles ever predicted across runs
            all_predicted = set()
            for r in valid_runs:
                all_predicted.update(r["predicted"])
            all_predicted = canonical_art_set(all_predicted)
            union_r_hard = len(all_predicted & hard_gt) / len(hard_gt) if hard_gt else 0.0

            # Stable predictions (appeared in all runs)
            if valid_runs:
                stable = canonical_art_set(set(valid_runs[0]["predicted"]))
                for r in valid_runs[1:]:
                    stable &= canonical_art_set(set(r["predicted"]))
                stable_r_hard = len(stable & hard_gt) / len(hard_gt) if hard_gt else 0.0
            else:
                stable = set()
                stable_r_hard = 0.0

            print(f"  Summary: mean R_hard={mean_r_hard:.3f} (±{std_r_hard:.3f}), "
                  f"union R_hard={union_r_hard:.3f}, stable R_hard={stable_r_hard:.3f}")

            article_result = {
                "target_article": target_article,
                "hard_gt": sorted(hard_gt, key=art_sort_key),
                "hard_gt_size": len(hard_gt),
                "c_size": len(c_set),
                "d_size": len(d_set),
                "c_equals_d": c_equals_d,
                "candidates_after_filter": len(filtered),
                "mean_r_hard": round(mean_r_hard, 4),
                "std_r_hard": round(std_r_hard, 4),
                "min_r_hard": round(min(r_hard_values), 4),
                "max_r_hard": round(max(r_hard_values), 4),
                "mean_precision": round(mean_prec, 4),
                "union_r_hard": round(union_r_hard, 4),
                "stable_r_hard": round(stable_r_hard, 4),
                "runs": runs,
            }
            all_results.append(article_result)

            csv_rows.append({
                "target_article": target_article,
                "hard_gt_size": len(hard_gt),
                "c_size": len(c_set),
                "d_size": len(d_set),
                "c_equals_d": c_equals_d,
                "candidates": len(filtered),
                "mean_r_hard": round(mean_r_hard, 4),
                "std_r_hard": round(std_r_hard, 4),
                "min_r_hard": round(min(r_hard_values), 4),
                "max_r_hard": round(max(r_hard_values), 4),
                "mean_precision": round(mean_prec, 4),
                "union_r_hard": round(union_r_hard, 4),
                "stable_r_hard": round(stable_r_hard, 4),
            })

    # ── Save results ──
    if csv_rows:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\nCSV saved to {output_csv}")

    full_output = {
        "experiment": f"batch_evaluation_{args.law}",
        "target_law": target_law,
        "total_eligible": total_eligible,
        "sample_size": len(all_results),
        "runs_per_article": RUNS_PER_ARTICLE,
        "random_seed": args.seed,
        "articles": all_results,
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(full_output, f, ensure_ascii=False, indent=2, default=str)
    print(f"JSON saved to {output_json}")

    # ── Final summary ──
    if all_results:
        r_hard_means = [a["mean_r_hard"] for a in all_results]
        overall_mean = sum(r_hard_means) / len(r_hard_means)
        overall_std = (sum((x - overall_mean)**2 for x in r_hard_means)
                       / max(len(r_hard_means) - 1, 1)) ** 0.5
        overall_min = min(r_hard_means)
        overall_max = max(r_hard_means)

        perfect = sum(1 for a in all_results if a["mean_r_hard"] == 1.0)
        partial = sum(1 for a in all_results if 0 < a["mean_r_hard"] < 1.0)
        zero = sum(1 for a in all_results if a["mean_r_hard"] == 0.0)
        c_d_equal = sum(1 for a in all_results if a["c_equals_d"])

        print(f"\n{'='*60}")
        print(f"BATCH EVALUATION SUMMARY — {args.law}")
        print(f"{'='*60}")
        print(f"Total eligible: {total_eligible}")
        print(f"Articles evaluated: {len(all_results)}")
        print(f"R_hard mean:  {overall_mean:.4f} (±{overall_std:.4f})")
        print(f"R_hard range: [{overall_min:.4f}, {overall_max:.4f}]")
        print(f"Perfect (R_hard=1.0): {perfect}/{len(all_results)}")
        print(f"Partial (0<R_hard<1): {partial}/{len(all_results)}")
        print(f"Zero (R_hard=0):      {zero}/{len(all_results)}")
        print(f"C = D ratio:          {c_d_equal}/{len(all_results)} ({c_d_equal/len(all_results)*100:.1f}%)")

        # Failure analysis
        failures = [a for a in all_results if a["mean_r_hard"] < 1.0]
        if failures:
            print(f"\nFailure analysis ({len(failures)} articles):")
            for a in failures:
                print(f"  {a['target_article']}: R_hard={a['mean_r_hard']:.3f}, "
                      f"GT={a['hard_gt_size']}, missed in some runs")
                # Show which articles were consistently missed
                consistently_missed = set(a["hard_gt"])
                for r in a["runs"]:
                    if "predicted" in r:
                        consistently_missed -= set(r["predicted"])
                if consistently_missed:
                    print(f"    Consistently missed: {sorted(consistently_missed)}")


if __name__ == "__main__":
    main()
