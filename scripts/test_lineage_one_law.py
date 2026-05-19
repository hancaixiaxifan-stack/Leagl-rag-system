"""
scripts/test_lineage_one_law.py

《公司法》专项血缘测试脚本
- 修复 lineage_chain 反序列化问题
- 链式对比 v2014 → v2018 → v2024
- 输出 Markdown 报告 + JSONL 明细
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# 将项目根目录加入 path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataclasses import asdict

from rag_contract.chunking import Chunk
from rag_contract.lineage import (
    build_version_lineage,
    lineage_summary,
    get_embed_model_version,
    LineageStep,
    SensitiveWordDelta,
)


def _load_chunks_by_title(jsonl_path: str, target_title: str) -> list[dict]:
    """从 chunks.jsonl 中加载指定法律的所有 chunks"""
    chunks = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if target_title in d.get("doc_title", ""):
                chunks.append(d)
    return chunks


def _dict_to_lineage_step(step_dict: dict) -> LineageStep:
    """将 dict 反序列化为 LineageStep"""
    deltas = []
    for delta_dict in step_dict.get("sensitive_deltas", []):
        deltas.append(SensitiveWordDelta(**delta_dict))
    step_dict = dict(step_dict)  # 复制，避免修改原 dict
    step_dict["sensitive_deltas"] = deltas
    return LineageStep(**step_dict)


def _chunk_dict_to_obj(c: dict, include_lineage: bool = True) -> Chunk:
    """将 chunk dict 转换为 Chunk 对象，并还原 lineage_chain"""
    safe_keys = (
        "doc_id", "doc_title", "doc_type", "jurisdiction", "publish_date",
        "source", "status", "article_no", "clause_no", "item_no",
        "para_start", "para_end", "text",
        "effective_start", "effective_end", "change_type", "law_category",
    )
    kwargs = {k: c[k] for k in safe_keys if k in c}

    obj = Chunk(**kwargs)

    if include_lineage and c.get("lineage_chain"):
        obj.lineage_chain = [_dict_to_lineage_step(s) for s in c["lineage_chain"]]

    return obj


def analyze_company_law(target_title: str = "公司法") -> dict:
    """
    对《公司法》三个版本进行链式血缘分析
    """
    chunks_path = ROOT / "data" / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(f"chunks.jsonl not found at {chunks_path}")

    print(f"加载《{target_title}》数据...")
    all_chunks = _load_chunks_by_title(str(chunks_path), target_title)
    print(f"共加载 {len(all_chunks)} 个 chunks")

    # 按 effective_start 分组
    version_groups: dict[str, list[dict]] = defaultdict(list)
    for c in all_chunks:
        eff = c.get("effective_start") or "unknown"
        version_groups[eff].append(c)

    version_keys = sorted(version_groups.keys())
    print(f"发现 {len(version_keys)} 个版本: {version_keys}")

    if len(version_keys) < 2:
        print("警告：版本不足，跳过血缘分析")
        return {}

    # 转换为 Chunk 对象（保留已有的 lineage_chain，用于链式追溯）
    version_chunks: dict[str, list[Chunk]] = {}
    for vk in version_keys:
        version_chunks[vk] = [_chunk_dict_to_obj(c) for c in version_groups[vk]]

    embed_model = get_embed_model_version()

    # 链式血缘：v1 → v2 → v3
    # 关键：两轮使用同一个 version_chunks 字典，Round 1 的结果会被 Round 2 复用
    # Round 1: v2014 (base) vs v2018 (new) → v2018 得到 lineage_chain = [step(v2018→v2014)]
    # Round 2: v2018 (带 lineage) vs v2024 (new)
    #   → 将 v2018 的 lineage_chain 注入到 v2024 的 Chunk 对象中
    #   → v2024 先有 [step(v2018→v2014)]，再 prepend step(v2024→v2018)
    #   → 最终 v2024 的 lineage_chain = [step(v2024→v2018), step(v2018→v2014)]
    results = {}

    for vi in range(1, len(version_keys)):
        prev_key = version_keys[vi - 1]
        curr_key = version_keys[vi]

        print(f"\n=== Round {vi}: {prev_key} → {curr_key} ===")
        print(f"  旧版 chunks: {len(version_chunks[prev_key])}")
        print(f"  新版 chunks: {len(version_chunks[curr_key])}")

        lineages = build_version_lineage(
            new_chunks=version_chunks[curr_key],
            prev_chunks=version_chunks[prev_key],
            doc_title=target_title,
            prev_version_label=prev_key,
            embed_model_version=embed_model,
        )

        # 将结果写回 version_chunks（用于下一轮链式追溯）
        for c, lin in zip(version_chunks[curr_key], lineages):
            c.lineage_chain = lin.lineage_chain
            c.lineage_id = lin.lineage_id

        print(f"  {lineage_summary(lineages)}")
        results[f"{prev_key}_to_{curr_key}"] = lineages

    return results, version_chunks, version_keys


def generate_report(
    version_keys: list[str],
    version_chunks: dict[str, list[Chunk]],
    results: dict,
) -> str:
    """生成 Markdown 格式的血缘报告"""

    lines = []
    lines.append(f"# 《公司法》法条血缘分析报告")
    lines.append("")

    # 总览：每个版本的 chunk 数
    lines.append("## 版本概览")
    lines.append("")
    lines.append("| 版本 | 施行日期 | Chunk 数 |")
    lines.append("|------|----------|---------|")
    for vk in version_keys:
        cnt = len(version_chunks.get(vk, []))
        lines.append(f"| v{version_keys.index(vk)+1} | {vk} | {cnt} |")
    lines.append("")

    # 统计各版本的变化类型
    lines.append("## 变化类型统计")
    lines.append("")

    for round_key, lineages in results.items():
        parts = round_key.split("_to_")
        prev_ver = parts[0]
        curr_ver = parts[1]
        lines.append(f"### {prev_ver} → {curr_ver}")
        lines.append("")

        change_types = defaultdict(int)
        high_drift = []
        splits = []
        merges = []

        for lin in lineages:
            if lin.lineage_chain:
                last_step = lin.lineage_chain[-1]
                change_types[last_step.change_type] += 1
                if last_step.is_split:
                    splits.append(lin.article_no)
                if last_step.is_merge:
                    merges.append(lin.article_no)
                if last_step.drift_score and last_step.drift_score > 0.3:
                    high_drift.append((lin.article_no, last_step.drift_score, last_step.change_type))

        lines.append(f"**变化类型分布**：{dict(change_types)}")
        lines.append("")
        lines.append(f"- 拆分案件数：{len(splits)}")
        lines.append(f"- 合并案件数：{len(merges)}")
        lines.append(f"- 高漂移（drift > 0.3）条数：{len(high_drift)}")
        lines.append("")

        if high_drift:
            lines.append("**高漂移条文 TOP 10**：")
            lines.append("")
            lines.append("| 条号 | drift_score | 变化类型 |")
            lines.append("|------|------------|----------|")
            for art, drift, ct in sorted(high_drift, key=lambda x: -x[1])[:10]:
                lines.append(f"| {art} | {drift:.4f} | {ct} |")
            lines.append("")

        if splits:
            lines.append(f"**发生拆分的条号**：{splits[:10]}")
            lines.append("")

        if merges:
            lines.append(f"**发生合并的条号**：{merges[:10]}")
            lines.append("")

    # 长链条追踪：找一个经历三个版本的条文
    lines.append("## 长链条追踪（经历所有版本）")
    lines.append("")

    latest_key = version_keys[-1]
    for c in version_chunks.get(latest_key, []):
        if c.lineage_chain and len(c.lineage_chain) >= 2:
            lines.append(f"### {c.article_no} (经历 {len(c.lineage_chain)} 次变迁)")
            lines.append("")
            lines.append(f"**最新版本文本**：{c.text[:200]}...")
            lines.append("")
            lines.append("**变迁链**：")
            lines.append("")
            lines.append("| 步骤 | 源版本 | 源自条号 | drift | 变化类型 | 关键变化 |")
            lines.append("|------|--------|---------|-------|---------|---------|")
            for step in reversed(c.lineage_chain):
                critical = "!! " + ", ".join(
                    d.word for d in step.sensitive_deltas if d.category_shifted or d.polarity_flipped
                ) if step.sensitive_deltas else ""
                drift_str = f"{step.drift_score:.4f}" if step.drift_score is not None else "-"
                lines.append(
                    f"| {step.version_label} | {step.derived_from_article or '新增'} | "
                    f"{drift_str} | {step.change_type} | {critical} |"
                )
            lines.append("")
            break  # 只展示第一条

    # 汇总：列出 drift 最大的前5条
    lines.append("## drift_score TOP 5（最新版 vs 最初版）")
    lines.append("")

    all_drift = []
    for c in version_chunks.get(latest_key, []):
        if c.lineage_chain:
            # 取第一个 step（最老的对比）
            oldest = c.lineage_chain[-1]
            if oldest.drift_score is not None:
                all_drift.append((c.article_no, oldest.drift_score, c.text[:100]))

    lines.append("| 条号 | 累计 drift | 文本摘要 |")
    lines.append("|------|-----------|---------|")
    for art, drift, text in sorted(all_drift, key=lambda x: -x[1])[:5]:
        lines.append(f"| {art} | {drift:.4f} | {text}... |")

    lines.append("")
    lines.append("---")
    lines.append("*报告生成时间：自动生成*")

    return "\n".join(lines)


def main():
    target = "公司法"
    print(f"=" * 60)
    print(f"《{target}》法条血缘分析")
    print(f"=" * 60)

    results, version_chunks, version_keys = analyze_company_law(target)

    if not results:
        print("无法生成报告，版本不足")
        return

    # 生成 Markdown 报告
    report = generate_report(version_keys, version_chunks, results)

    # 写入报告文件
    report_path = ROOT / "data" / "公司法_lineage_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已生成: {report_path}")

    # 同时输出 JSONL 明细（新版每个 chunk 的 lineage）
    jsonl_path = ROOT / "data" / "公司法_lineage_detail.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        latest_key = version_keys[-1]
        for c in version_chunks.get(latest_key, []):
            if c.lineage_chain:
                record = {
                    "article_no": c.article_no,
                    "doc_title": c.doc_title,
                    "lineage_chain": [asdict(s) for s in c.lineage_chain],
                    "text_preview": c.text[:200],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"明细已生成: {jsonl_path}")

    # 打印 Markdown 到终端
    print("\n" + "=" * 60)
    print("Markdown 报告预览：")
    print("=" * 60)
    print(report)


if __name__ == "__main__":
    main()