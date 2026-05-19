"""
scripts/test_sample_ingest.py

Sample test for ingest lineage flow.
Tests: single-version, two-version, and three-version laws.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataclasses import asdict

from rag_contract.chunking import Chunk
from rag_contract.lineage import (
    build_version_lineage,
    get_embed_model_version,
    LineageStep,
    SensitiveWordDelta,
)


def _load_chunks_by_title(jsonl_path: str, target_title: str) -> list[dict]:
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


def _dict_to_chunk(c: dict) -> Chunk:
    safe_keys = (
        "doc_id", "doc_title", "doc_type", "jurisdiction", "publish_date",
        "source", "status", "article_no", "clause_no", "item_no",
        "para_start", "para_end", "text",
        "effective_start", "effective_end", "change_type", "law_category",
    )
    kwargs = {k: c[k] for k in safe_keys if k in c}
    return Chunk(**kwargs)


def _step_dict_to_obj(step_dict: dict) -> LineageStep:
    deltas = []
    for delta_dict in step_dict.get("sensitive_deltas", []):
        deltas.append(SensitiveWordDelta(**delta_dict))
    step_dict = dict(step_dict)
    step_dict["sensitive_deltas"] = deltas
    return LineageStep(**step_dict)


def _find_test_laws(jsonl_path: str) -> dict:
    title_versions: dict[str, set] = defaultdict(set)
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line.strip())
            title = d.get("doc_title", "")
            eff = d.get("effective_start") or "unknown"
            if title:
                title_versions[title].add(eff)

    result = {"single": [], "two": [], "three_plus": [], "by_title": {}}
    for title, versions in title_versions.items():
        count = len(versions)
        result["by_title"][title] = sorted(versions)
        if count == 1:
            result["single"].append(title)
        elif count == 2:
            result["two"].append(title)
        else:
            result["three_plus"].append(title)

    return result


def test_single_version(chunks: list[dict], title: str) -> dict:
    print(f"\n  [A] Single-version law: {title} ({len(chunks)} chunks)")

    chunk_objs = [_dict_to_chunk(c) for c in chunks]

    lineages = build_version_lineage(
        new_chunks=chunk_objs,
        prev_chunks=[],
        doc_title=title,
        prev_version_label=None,
        embed_model_version=get_embed_model_version(),
    )

    for c, lin in zip(chunks, lineages):
        c["lineage_id"] = lin.lineage_id
        c["lineage_chain"] = [asdict(step) for step in lin.lineage_chain]

    errors = []
    for c, lin in zip(chunks, lineages):
        chain_len = len(lin.lineage_chain)
        if chain_len != 1:
            errors.append(f"  ERROR: {c.get('article_no')} chain_len={chain_len} (expected 1)")
        # For single-version: change_type should be "新增"
        if lin.lineage_chain and lin.lineage_chain[0].change_type != "新增":
            errors.append(f"  ERROR: {c.get('article_no')} change_type={lin.lineage_chain[0].change_type} (expected 新增)")

    result = {"title": title, "total": len(chunks), "passed": len(errors) == 0, "errors": errors}

    if errors:
        print(f"    FAIL: {len(errors)} errors")
        for e in errors[:5]:
            print(e)
    else:
        print(f"    PASS: all {len(chunks)} chunks marked as new")

    return result


def test_two_versions(chunks: list[dict], title: str) -> dict:
    print(f"\n  [B] Two-version law: {title} ({len(chunks)} chunks)")

    version_groups: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        eff = c.get("effective_start") or "unknown"
        version_groups[eff].append(c)

    version_keys = sorted(version_groups.keys())
    v1_chunks = [_dict_to_chunk(c) for c in version_groups[version_keys[0]]]
    v2_chunks = [_dict_to_chunk(c) for c in version_groups[version_keys[1]]]

    lineages = build_version_lineage(
        new_chunks=v2_chunks,
        prev_chunks=v1_chunks,
        doc_title=title,
        prev_version_label=version_keys[0],
        embed_model_version=get_embed_model_version(),
    )

    for c, lin in zip(version_groups[version_keys[1]], lineages):
        c["lineage_id"] = lin.lineage_id
        c["lineage_chain"] = [asdict(step) for step in lin.lineage_chain]

    errors = []
    for c, lin in zip(version_groups[version_keys[1]], lineages):
        chain_len = len(lin.lineage_chain)
        if chain_len != 1:
            errors.append(f"  ERROR: {c.get('article_no')} chain_len={chain_len} (expected 1)")

    has_multi = sum(1 for c in version_groups[version_keys[1]] if len(c.get("lineage_chain", [])) > 1)
    if has_multi > 0:
        errors.append(f"  ERROR: {has_multi} chunks have >1 steps (should not happen in 2-version)")

    result = {
        "title": title, "total": len(chunks),
        "versions": version_keys, "passed": len(errors) == 0, "errors": errors,
    }

    if errors:
        print(f"    FAIL: {len(errors)} errors")
        for e in errors[:5]:
            print(e)
    else:
        print(f"    PASS: v2 {len(v2_chunks)} chunks chain_len=1")

    return result


def test_three_versions(chunks: list[dict], title: str) -> dict:
    print(f"\n  [C] Multi-version law: {title} ({len(chunks)} chunks)")

    version_groups: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        eff = c.get("effective_start") or "unknown"
        version_groups[eff].append(c)

    version_keys = sorted(version_groups.keys())
    print(f"    Versions: {len(version_keys)}")

    all_version_objs = {}
    for vk in version_keys:
        all_version_objs[vk] = [_dict_to_chunk(c) for c in version_groups[vk]]

    for vi in range(1, len(version_keys)):
        prev_key = version_keys[vi - 1]
        curr_key = version_keys[vi]

        lineages = build_version_lineage(
            new_chunks=all_version_objs[curr_key],
            prev_chunks=all_version_objs[prev_key],
            doc_title=title,
            prev_version_label=prev_key,
            embed_model_version=get_embed_model_version(),
        )

        for c, lin in zip(version_groups[curr_key], lineages):
            c["lineage_id"] = lin.lineage_id
            c["lineage_chain"] = [asdict(step) for step in lin.lineage_chain]

        for c_obj, lin in zip(all_version_objs[curr_key], lineages):
            c_obj.lineage_chain = lin.lineage_chain

        expected_len = vi
        actual_lens = [len(c.get("lineage_chain", [])) for c in version_groups[curr_key]]
        wrong_lens = [a for a in actual_lens if a != expected_len]

        print(f"    Round {vi}: {prev_key} -> {curr_key}")
        print(f"      v{vi+1} chain_len = {actual_lens[0]} (expected {expected_len})")
        if wrong_lens:
            print(f"      FAIL: {len(wrong_lens)} chunks wrong length")
        else:
            print(f"      PASS: all correct")

    has_multi = [c for c in version_groups[version_keys[-1]] if len(c.get("lineage_chain", [])) > 1]
    result = {
        "title": title, "total": len(chunks),
        "versions": version_keys,
        "has_multi_version_chain": len(has_multi),
        "passed": len(has_multi) > 0, "errors": [],
    }

    print(f"    VERIFY: {len(has_multi)} chunks have multi-version chains")
    return result


def run_verification(chunks_path: str, output_dir: str):
    print("=" * 60)
    print("Sample Ingest Test")
    print("=" * 60)

    print("\n[1] Scanning chunks.jsonl for law version distribution...")
    law_info = _find_test_laws(chunks_path)

    print(f"  Single-version: {len(law_info['single'])} laws")
    print(f"  Two-version: {len(law_info['two'])} laws")
    print(f"  Three-plus: {len(law_info['three_plus'])} laws")

    results = []

    if law_info["single"]:
        title_a = law_info["single"][0]
        chunks_a = _load_chunks_by_title(chunks_path, title_a)
        result_a = test_single_version(chunks_a, title_a)
        results.append(("A", title_a, result_a))
    else:
        print("\n  [A] No single-version law available")

    if law_info["two"]:
        title_b = law_info["two"][0]
        chunks_b = _load_chunks_by_title(chunks_path, title_b)
        result_b = test_two_versions(chunks_b, title_b)
        results.append(("B", title_b, result_b))
    else:
        print("\n  [B] No two-version law available")

    if law_info["three_plus"]:
        title_c = law_info["three_plus"][0]  # first multi-version law (could be company law)
        chunks_c = _load_chunks_by_title(chunks_path, title_c)
        if chunks_c:
            result_c = test_three_versions(chunks_c, title_c)
            results.append(("C", title_c, result_c))
        else:
            print(f"\n  [C] {title_c} loaded 0 chunks - skipping")
    else:
        print("\n  [C] No three-plus-version law available")

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for label, title, result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  {label}. {title}: {status}")
        if not result["passed"]:
            all_passed = False

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "sample_test_report.json")

    report = {
        "all_passed": all_passed,
        "results": [{"label": l, "title": t, **r} for l, t, r in results],
        "law_summary": {
            "single_count": len(law_info["single"]),
            "two_count": len(law_info["two"]),
            "three_plus_count": len(law_info["three_plus"]),
        },
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nReport written: {report_path}")

    has_multi = sum(1 for _, _, r in results if r.get("has_multi_version_chain", 0) > 0)
    if has_multi == 0:
        print("\nCRITICAL ERROR: No multi-version chains detected in any test!")
        raise ValueError("Lineage backfill FAILED: no multi-version chains")

    print("\nPASS: sample test passed - lineage backfill is correct")
    return all_passed


def main():
    chunks_path = ROOT / "data" / "chunks.jsonl"
    output_dir = ROOT / "data" / "test_output"

    if not chunks_path.exists():
        print(f"ERROR: chunks.jsonl not found at {chunks_path}")
        return

    print(f"Using data source: {chunks_path}")
    run_verification(str(chunks_path), str(output_dir))


if __name__ == "__main__":
    main()