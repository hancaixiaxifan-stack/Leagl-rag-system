"""
4-Annotator Human Evaluation Analysis
======================================
基于 annotation_final 的 4 标注员 × 200 对数据：

1. IAA: Fleiss' κ (4人) + 全配对 Cohen's κ (6对)
2. 人工评估精度: 分 round1/round2/combined 的 source 别 "both≥1" / "majority≥1"
3. 显著性检验: Fisher / Chi-square / Bootstrap CI

数据:
  experiments/annotation_final/已标注excel/annotator_group{1,2}_{A,B}_completed.xlsx
  experiments/annotation_final/ground_truth.json

运行: .venv/Scripts/python.exe scripts/human_eval_4annotator.py
"""
import sys
import json
import os
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANNOT_DIR = PROJECT_ROOT / "experiments" / "annotation_final"
EXCEL_DIR = ANNOT_DIR / "已标注excel"
N_BOOT = 10000
RNG_SEED = 42

ANNOTATORS = [
    "group1_A", "group1_B", "group2_A", "group2_B"
]
ANNOTATOR_FILES = {
    name: EXCEL_DIR / f"annotator_{name}_completed.xlsx"
    for name in ANNOTATORS
}


def load_annotations():
    """Load per-item scores from all 4 annotators + source labels from ground_truth.json."""
    import openpyxl

    # Load source labels
    with open(ANNOT_DIR / "ground_truth.json", encoding="utf-8") as f:
        gt = json.load(f)

    # Load each annotator's scores
    all_scores = {}
    for name in ANNOTATORS:
        wb = openpyxl.load_workbook(ANNOTATOR_FILES[name])
        ws = wb["Sheet1"]
        scores = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            seq = row[0]
            score = row[6]  # '您的评分(0/1/2)'
            reason = row[7]
            if seq is not None and score is not None:
                scores[int(seq)] = {"score": int(score), "reason": reason}
        all_scores[name] = scores
        print(f"  Loaded {name}: {len(scores)} items")

    # Build per-item records
    items = []
    all_seqs = sorted(set().union(*(s.keys() for s in all_scores.values())))
    for seq in all_seqs:
        gt_entry = gt.get(str(seq), {})
        scores = {}
        for name in ANNOTATORS:
            if seq in all_scores[name]:
                scores[name] = all_scores[name][seq]["score"]

        if len(scores) == 4:  # all 4 annotators labeled this item
            items.append({
                "seq": seq,
                "source": gt_entry.get("source", "unknown"),
                "domain": gt_entry.get("domain", "unknown"),
                "target": gt_entry.get("target", ""),
                "candidate": gt_entry.get("candidate", ""),
                **{f"score_{name}": scores[name] for name in ANNOTATORS},
            })

    print(f"  Items with all 4 annotators: {len(items)}")
    return items


# ================================================================
# Part 1: IAA
# ================================================================

def cohens_kappa(scores_a, scores_b, labels=(0, 1, 2)):
    """Cohen's κ between two annotators."""
    n = len(scores_a)
    cm = {(l1, l2): 0 for l1 in labels for l2 in labels}
    for sa, sb in zip(scores_a, scores_b):
        cm[(sa, sb)] += 1
    po = sum(cm[(l, l)] for l in labels) / n
    pe = 0
    for l in labels:
        row_sum = sum(cm[(l, l2)] for l2 in labels)
        col_sum = sum(cm[(l2, l)] for l2 in labels)
        pe += (row_sum / n) * (col_sum / n)
    kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0
    return po, pe, kappa


def cohens_kappa_weighted(scores_a, scores_b, labels=(0, 1, 2), weights="quadratic"):
    """Weighted Cohen's κ."""
    n = len(scores_a)
    k = len(labels)
    label_to_idx = {l: i for i, l in enumerate(labels)}

    # Weight matrix
    w = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            if weights == "linear":
                w[i][j] = abs(i - j) / (k - 1)
            elif weights == "quadratic":
                w[i][j] = ((i - j) ** 2) / ((k - 1) ** 2)

    # Confusion matrix
    cm = np.zeros((k, k))
    for sa, sb in zip(scores_a, scores_b):
        cm[label_to_idx[sa]][label_to_idx[sb]] += 1
    cm /= n

    # Marginals
    row_marginals = cm.sum(axis=1)
    col_marginals = cm.sum(axis=0)

    # Expected matrix
    expected = np.outer(row_marginals, col_marginals)

    # Weighted agreement
    po_w = 1 - np.sum(w * cm)
    pe_w = 1 - np.sum(w * expected)

    kappa_w = (po_w - pe_w) / (1 - pe_w) if pe_w != 1 else 1.0
    return po_w, pe_w, kappa_w


def fleiss_kappa(ratings_matrix):
    """
    Fleiss' κ for multiple annotators.
    ratings_matrix: list of lists, each inner list is [count_0, count_1, count_2] for one item.
    """
    N = len(ratings_matrix)  # number of items
    n = sum(ratings_matrix[0])  # number of annotators
    k = len(ratings_matrix[0])  # number of categories

    # Category proportions
    p = np.sum(ratings_matrix, axis=0) / (N * n)

    # Per-item agreement
    P_items = []
    for row in ratings_matrix:
        P_i = (sum(c * c for c in row) - n) / (n * (n - 1))
        P_items.append(P_i)
    P_bar = np.mean(P_items)

    # Expected agreement
    Pe = sum(pi * pi for pi in p)

    kappa = (P_bar - Pe) / (1 - Pe) if Pe != 1 else 1.0
    return kappa, P_bar, Pe


def compute_iaa(items, label="ALL"):
    """Compute all IAA metrics for a set of items."""
    print(f"\n{'=' * 70}")
    print(f"  IAA: {label} (n={len(items)})")
    print(f"{'=' * 70}")

    # ---- Pairwise Cohen's κ ----
    print(f"\n  --- Pairwise Cohen's κ ---")
    pairs = list(combinations(ANNOTATORS, 2))
    for a, b in pairs:
        sa = [item[f"score_{a}"] for item in items]
        sb = [item[f"score_{b}"] for item in items]
        po, pe, k = cohens_kappa(sa, sb)
        _, _, k_lin = cohens_kappa_weighted(sa, sb, weights="linear")
        _, _, k_quad = cohens_kappa_weighted(sa, sb, weights="quadratic")
        print(f"    {a:>10} vs {b:<10}: κ={k:.3f}, κ_lin={k_lin:.3f}, κ_quad={k_quad:.3f} (Po={po:.3f})")

    # ---- Fleiss' κ ----
    print(f"\n  --- Fleiss' κ (4 annotators) ---")
    ratings = []
    for item in items:
        scores = [item[f"score_{name}"] for name in ANNOTATORS]
        counts = [scores.count(0), scores.count(1), scores.count(2)]
        ratings.append(counts)
    ratings_matrix = np.array(ratings)

    kappa_fleiss, P_bar, Pe = fleiss_kappa(ratings_matrix)
    print(f"    Fleiss' κ = {kappa_fleiss:.3f} (P̄={P_bar:.3f}, Pe={Pe:.3f})")

    # ---- Interpretation ----
    if kappa_fleiss >= 0.8:
        interp = "almost perfect"
    elif kappa_fleiss >= 0.6:
        interp = "substantial"
    elif kappa_fleiss >= 0.4:
        interp = "moderate"
    else:
        interp = "fair"
    print(f"    Interpretation: {interp}")

    # ---- Exact agreement ----
    exact = sum(1 for item in items
                if len(set(item[f"score_{name}"] for name in ANNOTATORS)) == 1)
    majority = sum(1 for item in items
                   if any(item[f"score_{name}"] == v
                          for name in ANNOTATORS
                          for v in [0, 1, 2]
                          if sum(1 for n2 in ANNOTATORS if item[f"score_{n2}"] == v) >= 3))
    print(f"\n    Exact 4-way agreement: {exact}/{len(items)} ({exact/len(items)*100:.1f}%)")
    print(f"    Majority (≥3/4) agreement: {majority}/{len(items)} ({majority/len(items)*100:.1f}%)")

    return {
        "fleiss_kappa": kappa_fleiss,
        "p_bar": P_bar,
        "p_expected": Pe,
        "exact_agreement_pct": exact / len(items) * 100,
        "majority_agreement_pct": majority / len(items) * 100,
    }


# ================================================================
# Part 2: Human Evaluation Precision
# ================================================================

def compute_precision(items, label="ALL"):
    """Compute per-source precision with different aggregation methods."""
    print(f"\n{'=' * 70}")
    print(f"  Human Evaluation Precision: {label} (n={len(items)})")
    print(f"{'=' * 70}")

    # Group by source
    by_source = defaultdict(list)
    for item in items:
        by_source[item["source"]].append(item)

    results = {}
    for src in sorted(by_source.keys()):
        group = by_source[src]
        n = len(group)

        # "both≥1" for all 4 annotators (all 4 must be ≥1)
        all_geq1 = sum(1 for item in group
                       if all(item[f"score_{name}"] >= 1 for name in ANNOTATORS))

        # "majority≥1" (at least 3/4 annotators ≥1)
        maj_geq1 = sum(1 for item in group
                       if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)

        # "any≥1" (at least 1/4 annotators ≥1)
        any_geq1 = sum(1 for item in group
                       if any(item[f"score_{name}"] >= 1 for name in ANNOTATORS))

        # "all=2" (all 4 annotators scored 2)
        all_eq2 = sum(1 for item in group
                      if all(item[f"score_{name}"] == 2 for name in ANNOTATORS))

        # "majority=2" (at least 3/4 scored 2)
        maj_eq2 = sum(1 for item in group
                      if sum(1 for name in ANNOTATORS if item[f"score_{name}"] == 2) >= 3)

        # Mean score across 4 annotators
        mean_scores = []
        for item in group:
            ms = np.mean([item[f"score_{name}"] for name in ANNOTATORS])
            mean_scores.append(ms)

        results[src] = {
            "n": n,
            "all_geq1": all_geq1,
            "all_geq1_pct": all_geq1 / n * 100,
            "maj_geq1": maj_geq1,
            "maj_geq1_pct": maj_geq1 / n * 100,
            "any_geq1": any_geq1,
            "any_geq1_pct": any_geq1 / n * 100,
            "all_eq2": all_eq2,
            "all_eq2_pct": all_eq2 / n * 100,
            "maj_eq2": maj_eq2,
            "maj_eq2_pct": maj_eq2 / n * 100,
            "mean_score": float(np.mean(mean_scores)),
        }

    # Print table
    print(f"\n  {'Source':<20} {'n':>4} {'all≥1':>8} {'maj≥1':>8} {'any≥1':>8} {'all=2':>8} {'maj=2':>8} {'mean':>6}")
    print(f"  {'-'*20} {'-'*4} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")
    for src in sorted(results.keys()):
        r = results[src]
        print(f"  {src:<20} {r['n']:>4} {r['all_geq1_pct']:>7.1f}% {r['maj_geq1_pct']:>7.1f}% "
              f"{r['any_geq1_pct']:>7.1f}% {r['all_eq2_pct']:>7.1f}% {r['maj_eq2_pct']:>7.1f}% {r['mean_score']:>6.2f}")

    return results


# ================================================================
# Part 3: Significance Tests
# ================================================================

def fisher_exact_test(table):
    from scipy.stats import fisher_exact
    _, p = fisher_exact(table, alternative="two-sided")
    return p


def chi_square_test(counts, totals):
    from scipy.stats import chi2_contingency
    failures = [t - s for s, t in zip(counts, totals)]
    table = [counts, failures]
    chi2, p, dof, expected = chi2_contingency(table, correction=False)
    return chi2, p, dof


def bootstrap_diff_ci(successes_a, n_a, successes_b, n_b, n_boot=N_BOOT, seed=RNG_SEED):
    rng = np.random.default_rng(seed)
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    observed_diff = p_a - p_b
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sample_a = rng.binomial(n_a, p_a) / n_a
        sample_b = rng.binomial(n_b, p_b) / n_b
        diffs[i] = sample_a - sample_b
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return observed_diff, float(lo), float(hi)


def run_significance_tests(precision_results, items, label="ALL"):
    """Run significance tests on precision results."""
    print(f"\n{'=' * 70}")
    print(f"  Significance Tests: {label}")
    print(f"{'=' * 70}")

    # Determine which sources to compare
    sources = sorted(precision_results.keys())

    # Group items by source for per-item analysis
    by_source = defaultdict(list)
    for item in items:
        by_source[item["source"]].append(item)

    # Use "majority≥1" as the primary metric (most robust for 4 annotators)
    metric = "maj_geq1"

    # ---- Fisher exact test (pairwise) ----
    print(f"\n  --- Fisher Exact Test (majority≥1) ---")
    pairs = list(combinations(sources, 2))
    for src_a, src_b in pairs:
        a = precision_results[src_a]
        b = precision_results[src_b]
        table = [
            [a[metric], a["n"] - a[metric]],
            [b[metric], b["n"] - b[metric]],
        ]
        p = fisher_exact_test(table)
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
        print(f"    {src_a:>20} ({a[metric+'_pct']:.1f}%) vs {src_b:<20} ({b[metric+'_pct']:.1f}%): "
              f"Fisher p={p:.2e}  {sig}")

    # ---- Chi-square (overall) ----
    print(f"\n  --- Chi-Square Test (overall, majority≥1) ---")
    counts = [precision_results[s][metric] for s in sources]
    totals = [precision_results[s]["n"] for s in sources]
    chi2, p, dof = chi_square_test(counts, totals)
    print(f"    chi2={chi2:.4f}, df={dof}, p={p:.2e}")
    print(f"    {'SIGNIFICANT' if p < 0.05 else 'NOT significant'} (α=0.05)")

    # ---- Bootstrap CI for key pairwise comparisons ----
    print(f"\n  --- Bootstrap {N_BOOT}-resample 95% CI (majority≥1) ---")
    for src_a, src_b in pairs:
        a = precision_results[src_a]
        b = precision_results[src_b]
        diff, lo, hi = bootstrap_diff_ci(a[metric], a["n"], b[metric], b["n"])
        excludes_zero = "YES" if (lo > 0 or hi < 0) else "NO"
        print(f"    {src_a:>20} - {src_b:<20}: diff={diff:+.4f}, 95%CI=[{lo:+.4f}, {hi:+.4f}], excludes 0: {excludes_zero}")

    # ---- Bonferroni-corrected pairwise chi-square ----
    n_comparisons = len(pairs)
    alpha_bonf = 0.05 / n_comparisons
    print(f"\n  --- Pairwise Chi-Square with Bonferroni (α={alpha_bonf:.4f}={0.05}/{n_comparisons}) ---")
    for src_a, src_b in pairs:
        a = precision_results[src_a]
        b = precision_results[src_b]
        c = [a[metric], b[metric]]
        t = [a["n"], b["n"]]
        _, p_p, _ = chi_square_test(c, t)
        sig = "SIG" if p_p < alpha_bonf else "ns"
        print(f"    {src_a:>20} vs {src_b:<20}: p={p_p:.2e}  {sig}")


# ================================================================
# Part 4: Per-domain breakdown
# ================================================================

def per_domain_analysis(items):
    """Per-domain IAA and precision."""
    print(f"\n{'=' * 70}")
    print(f"  Per-Domain Analysis")
    print(f"{'=' * 70}")

    by_domain = defaultdict(list)
    for item in items:
        by_domain[item["domain"]].append(item)

    for domain in sorted(by_domain.keys()):
        domain_items = by_domain[domain]
        print(f"\n  --- Domain: {domain} (n={len(domain_items)}) ---")

        # Fleiss' κ
        ratings = []
        for item in domain_items:
            scores = [item[f"score_{name}"] for name in ANNOTATORS]
            counts = [scores.count(0), scores.count(1), scores.count(2)]
            ratings.append(counts)
        if len(ratings) >= 5:
            ratings_matrix = np.array(ratings)
            kappa_f, _, _ = fleiss_kappa(ratings_matrix)
            print(f"    Fleiss' κ = {kappa_f:.3f}")

        # Precision by source
        by_src = defaultdict(list)
        for item in domain_items:
            by_src[item["source"]].append(item)
        for src in sorted(by_src.keys()):
            group = by_src[src]
            n = len(group)
            maj_geq1 = sum(1 for item in group
                           if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)
            print(f"    {src:<20}: n={n}, majority≥1={maj_geq1}/{n} ({maj_geq1/n*100:.1f}%)")


# ================================================================
# Part 5: Round1 vs Round2 comparison
# ================================================================

def round_comparison(items):
    """Compare round1 and round2 results."""
    print(f"\n{'=' * 70}")
    print(f"  Round1 vs Round2 Comparison")
    print(f"{'=' * 70}")

    round1 = [item for item in items if item["source"].startswith("round1")]
    round2 = [item for item in items if item["source"].startswith("round2")]

    print(f"\n  Round1: {len(round1)} items")
    print(f"  Round2: {len(round2)} items")

    # Round1 precision (graph vs dense vs random)
    if round1:
        print(f"\n  --- Round1 Sources ---")
        r1_by_src = defaultdict(list)
        for item in round1:
            r1_by_src[item["source"]].append(item)
        for src in sorted(r1_by_src.keys()):
            group = r1_by_src[src]
            n = len(group)
            maj_geq1 = sum(1 for item in group
                           if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)
            print(f"    {src:<20}: n={n}, majority≥1={maj_geq1}/{n} ({maj_geq1/n*100:.1f}%)")

    # Round2 precision (pipeline vs dense)
    if round2:
        print(f"\n  --- Round2 Sources ---")
        r2_by_src = defaultdict(list)
        for item in round2:
            r2_by_src[item["source"]].append(item)
        for src in sorted(r2_by_src.keys()):
            group = r2_by_src[src]
            n = len(group)
            maj_geq1 = sum(1 for item in group
                           if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)
            print(f"    {src:<20}: n={n}, majority≥1={maj_geq1}/{n} ({maj_geq1/n*100:.1f}%)")

    # Round1 graph vs dense (direct comparison with old paper)
    if "round1_graph" in {item["source"] for item in round1}:
        graph_items = [i for i in round1 if i["source"] == "round1_graph"]
        dense_items = [i for i in round1 if i["source"] == "round1_dense"]
        random_items = [i for i in round1 if i["source"] == "round1_random"]

        print(f"\n  --- Round1 Key Comparison (4 annotators) ---")
        for label, group in [("graph", graph_items), ("dense", dense_items), ("random", random_items)]:
            n = len(group)
            if n == 0:
                continue
            maj_geq1 = sum(1 for item in group
                           if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)
            all_geq1 = sum(1 for item in group
                           if all(item[f"score_{name}"] >= 1 for name in ANNOTATORS))
            print(f"    {label:>8}: n={n}, all4≥1={all_geq1}/{n} ({all_geq1/n*100:.1f}%), "
                  f"maj≥1={maj_geq1}/{n} ({maj_geq1/n*100:.1f}%)")

        # Fisher test: graph vs dense
        g_maj = sum(1 for item in graph_items
                    if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)
        d_maj = sum(1 for item in dense_items
                    if sum(1 for name in ANNOTATORS if item[f"score_{name}"] >= 1) >= 3)
        table = [[g_maj, len(graph_items) - g_maj], [d_maj, len(dense_items) - d_maj]]
        p = fisher_exact_test(table)
        print(f"    graph vs dense Fisher p={p:.2e}")


# ================================================================
# Main
# ================================================================

def main():
    print("=" * 70)
    print("4-Annotator Human Evaluation Analysis")
    print("=" * 70)

    # Load data
    print("\n[1/5] Loading annotations...")
    items = load_annotations()

    # Split by round
    round1_items = [i for i in items if i["source"].startswith("round1")]
    round2_items = [i for i in items if i["source"].startswith("round2")]

    # ---- Part 1: IAA ----
    print("\n[2/5] Computing IAA...")
    iaa_all = compute_iaa(items, "ALL (n={})".format(len(items)))
    iaa_r1 = compute_iaa(round1_items, "Round1 (n={})".format(len(round1_items)))
    iaa_r2 = compute_iaa(round2_items, "Round2 (n={})".format(len(round2_items)))

    # ---- Part 2: Precision ----
    print("\n[3/5] Computing precision...")
    prec_all = compute_precision(items, "ALL")
    prec_r1 = compute_precision(round1_items, "Round1")
    prec_r2 = compute_precision(round2_items, "Round2")

    # ---- Part 3: Significance ----
    print("\n[4/5] Running significance tests...")
    run_significance_tests(prec_all, items, "ALL")

    # Round1 specific tests (for paper comparison)
    if round1_items:
        run_significance_tests(prec_r1, round1_items, "Round1")

    # ---- Part 4: Per-domain ----
    print("\n[5/5] Per-domain analysis...")
    per_domain_analysis(items)

    # ---- Part 5: Round comparison ----
    round_comparison(items)

    # ---- Save summary ----
    summary = {
        "n_items_total": len(items),
        "n_round1": len(round1_items),
        "n_round2": len(round2_items),
        "annotators": ANNOTATORS,
        "iaa": {
            "all": iaa_all,
            "round1": iaa_r1,
            "round2": iaa_r2,
        },
        "precision": {
            "all": prec_all,
            "round1": prec_r1,
            "round2": prec_r2,
        },
    }
    output_path = PROJECT_ROOT / "experiments" / "annotation_final" / "analysis_4annotator.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nSummary saved to {output_path}")


if __name__ == "__main__":
    main()
