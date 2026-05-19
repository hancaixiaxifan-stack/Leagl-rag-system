from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from time import time

from dataclasses import asdict, is_dataclass

from tqdm import tqdm
from rag_contract.chunking import chunk_docx, Chunk
from rag_contract.docx_parse import parse_docx
from rag_contract.index import ensure_collection, get_qdrant, upsert_chunks
from rag_contract.lineage import build_version_lineage, get_embed_model_version, lineage_summary, step_from_dict
from rag_contract.local_embed import embed_texts


def _safe_asdict(obj):
    """asdict that handles non-dataclass objects (e.g. dict from JSON)"""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    # if it's a plain dict, return as-is
    return obj
from rag_contract.settings import settings


def iter_docx_files(root: str):
    """
    遍历目录下的所有.docx文件，排除Word临时文件
    """
    for dp, _dns, fns in os.walk(root):
        for fn in fns:
            if fn.lower().endswith(".docx") and not fn.startswith("~$"):
                yield os.path.join(dp, fn)


def load_excel_index(excel_path: str) -> dict[tuple[str, str], tuple[str, str]]:
    """
    加载 Excel，返回 {(标题, 公布日期): (施行日期, 法律分类)} 的映射
    """
    import openpyxl
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb.active
    index: dict[tuple[str, str], tuple[str, str]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        title = row[0]
        publish_date = str(row[1]) if row[1] else ""
        effective_date = str(row[2]) if row[2] else ""
        law_category = str(row[3]) if row[3] else "法律"
        if title and publish_date:
            index[(title, publish_date)] = (effective_date, law_category)
    return index


def date_minus_one(date_str: str) -> str:
    """返回 (date_str - 1天) 的 YYYY-MM-DD 格式"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def compute_effective_dates(chunks_data: list[dict], excel_index: dict[tuple[str, str], tuple[str, str]]) -> list[dict]:
    """
    对 chunks 数据计算 effective_start、effective_end、status 和 law_category
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # 第一步：为每个 chunk 查找 effective_start 和 law_category
    for chunk in chunks_data:
        doc_title = chunk.get("doc_title", "")
        pub_date = chunk.get("publish_date")

        if pub_date and len(pub_date) == 8:
            pub_date_formatted = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:8]}"
        else:
            pub_date_formatted = pub_date

        result = excel_index.get((doc_title, pub_date_formatted))
        if not result and pub_date_formatted:
            result = excel_index.get((doc_title, pub_date))

        if result:
            chunk["effective_start"] = result[0]
            chunk["law_category"] = result[1]
        else:
            chunk["effective_start"] = None
            chunk["law_category"] = chunk.get("law_category", "法律")

    # 第二步：按 (doc_title, effective_start) 分组得到版本
    versions: dict[tuple, list[dict]] = defaultdict(list)
    for chunk in chunks_data:
        key = (chunk.get("doc_title"), chunk.get("effective_start"))
        versions[key].append(chunk)

    # 第三步：按 doc_title 分组，组内按 effective_start 排序版本
    by_title: dict[str, list] = defaultdict(list)
    for (title, eff_start), version_chunks in versions.items():
        by_title[title].append((eff_start, version_chunks))

    for title in by_title:
        by_title[title].sort(key=lambda x: (x[0] or "9999-99-99"))

    # 第四步：计算每个版本的 effective_end（在同法律内）
    for title, version_list in by_title.items():
        for i, (eff_start, version_chunks) in enumerate(version_list):
            if i + 1 < len(version_list):
                next_eff_start = version_list[i + 1][0]
                if next_eff_start:
                    eff_end = date_minus_one(next_eff_start)
                else:
                    eff_end = None
            else:
                eff_end = None

            for chunk in version_chunks:
                chunk["effective_end"] = eff_end

                if eff_start and eff_start > today:
                    chunk["status"] = "尚未生效"
                elif eff_end and eff_end < today:
                    chunk["status"] = "已修改" if i + 1 < len(version_list) else "已废止"
                elif eff_end is None and eff_start and eff_start <= today:
                    chunk["status"] = "有效"
                else:
                    chunk["status"] = chunk.get("status", "有效")

    return chunks_data


def apply_lineage(
    chunks_data: list[dict],
    embed_model_version: str,
) -> list[dict]:
    """
    对所有版本执行链式血缘发现
    - 按 doc_title 分组，组内按 effective_start 排序（版本从旧到新）
    - 每个版本只与前一个版本对比，但通过 lineage_chain 保留完整变迁历史
    - 单版本法律（无历史）→ 直接标记"新增"
    """
    from rag_contract.chunking import Chunk

    # 排除的血缘相关字段（用于创建 Chunk 对象）
    # 包含：(1) 新格式 lineage_chain 相关字段, (2) 旧格式残留字段（历史 chunks.jsonl 中）
    _LINEAGE_FIELDS = (
        "lineage_id", "lineage_chain", "embed_model_version",
        "derived_from", "is_split", "is_merge", "similarity_with_prev", "drift_score",
    )

    # 按 doc_title 分组
    by_title: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks_data:
        by_title[chunk.get("doc_title", "")].append(chunk)

    for title, chunks in by_title.items():
        # 按 effective_start 排序（从旧到新）
        chunks.sort(key=lambda c: (c.get("effective_start") or ""))

        # 按版本分组（一个 effective_start = 一个版本）
        version_groups: dict[str, list[dict]] = defaultdict(list)
        for c in chunks:
            version_groups[c.get("effective_start", "")].append(c)

        version_keys: list[str] = sorted(version_groups.keys())

        # 逐版本血缘分析（从旧到新：v1, v2, v3, ...）
        for vi, eff_start in enumerate(version_keys):
            version_chunks = version_groups[eff_start]
            prev_version_label = version_keys[vi - 1] if vi > 0 else None

            # 将 dict 转回 Chunk 对象（保留已有的 lineage_chain，用于链式追溯）
            # 注意：lineage_chain 可能是 list[dict]（写入后读回）或 list[LineageStep]（内存中）
            # 需要统一转换为 LineageStep 对象以保证 build_version_lineage 的链式追溯正确
            chunk_objs = []
            for c in version_chunks:
                safe_c = {k: v for k, v in c.items() if k not in _LINEAGE_FIELDS}
                obj = Chunk(**safe_c)
                # 注入前一个版本的 lineage_chain（如果有）
                if vi > 0 and c.get("lineage_chain"):
                    obj.lineage_chain = [
                        step_from_dict(s) if isinstance(s, dict) else s
                        for s in c["lineage_chain"]
                    ]
                chunk_objs.append(obj)

            # 查找前一个版本的 Chunk 对象
            prev_chunks_obj: list[Chunk] = []
            if vi > 0:
                prev_eff = version_keys[vi - 1]
                for c in version_groups[prev_eff]:
                    safe_c = {k: v for k, v in c.items() if k not in _LINEAGE_FIELDS}
                    obj = Chunk(**safe_c)
                    if c.get("lineage_chain"):
                        obj.lineage_chain = [
                            step_from_dict(s) if isinstance(s, dict) else s
                            for s in c["lineage_chain"]
                        ]
                    prev_chunks_obj.append(obj)

            # 执行链式血缘发现
            lineages = build_version_lineage(
                new_chunks=chunk_objs,
                prev_chunks=prev_chunks_obj,
                doc_title=title,
                prev_version_label=prev_version_label,
                embed_model_version=embed_model_version,
            )

            # 把血缘信息写回 dict
            for c, lin in zip(version_chunks, lineages):
                c["lineage_id"] = lin.lineage_id
                c["lineage_chain"] = [_safe_asdict(step) for step in lin.lineage_chain]
                c["embed_model_version"] = lin.embed_model_version

            version_tag = version_keys[vi - 1] if vi > 0 else "initial"
            print(f"  {title} {version_tag}→{eff_start}: {lineage_summary(lineages)}")

    return chunks_data


def main(rebuild_vectors_only: bool = False) -> None:
    docs_dir = Path(settings.docs_dir)
    out_path = Path(settings.chunks_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 找到 Excel 文件（merged.xlsx）
    excel_path = docs_dir / "merged.xlsx"
    if not excel_path.exists():
        excel_path = docs_dir / "merged.xlsx"
        found = False
        for dp, _dns, fns in os.walk(docs_dir):
            for fn in fns:
                if fn.endswith(".xlsx"):
                    excel_path = Path(dp) / fn
                    found = True
                    break
            if found:
                break

    if rebuild_vectors_only and out_path.exists():
        # 只重建向量，不重新生成 chunks
        print(f"跳过 chunk 生成，直接从 {out_path} 读取...")
        chunks_data = []
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                chunks_data.append(json.loads(line))
        print(f"从现有文件加载 {len(chunks_data)} 个 chunks")
        all_chunks = chunks_data
    else:
        # 完整流程：解析 -> chunk -> 填充 Excel 数据 -> 写入
        all_chunks = []
        processed_files = 0
        failed_files = 0

        print(f"开始处理文档目录: {docs_dir}")

        for path in iter_docx_files(str(docs_dir)):
            try:
                parsed = parse_docx(path)
                chunks = chunk_docx(parsed)
                if chunks:
                    all_chunks.extend(chunks)
                    processed_files += 1
                    if processed_files % 100 == 0:
                        print(f"已处理 {processed_files} 个文件，生成 {len(all_chunks)} 个chunks")
            except Exception as e:
                failed_files += 1
                print(f"警告: 无法处理文件 {path} - 错误: {e}")
                continue

        print(f"\n处理完成:")
        print(f"成功处理文件: {processed_files}")
        print(f"处理失败文件: {failed_files}")
        print(f"生成chunks总数: {len(all_chunks)}")

        if not all_chunks:
            raise SystemExit(f"No chunks produced. Check docs_dir={docs_dir}")

        # 转换为 dict 并填充 Excel 数据
        print(f"加载 Excel: {excel_path}")
        excel_index = load_excel_index(str(excel_path))
        print(f"Excel 共 {len(excel_index)} 条记录")

        chunks_data = [c.__dict__ if hasattr(c, '__dict__') else c for c in all_chunks]
        print("计算 effective_start/end、status 和 law_category...")
        chunks_data = compute_effective_dates(chunks_data, excel_index)

        # Embedding 模型版本检查（防止跨模型 drift 值失效）
        current_embed_model = get_embed_model_version()
        for chunk in chunks_data:
            stored_version = chunk.get("embed_model_version")
            if stored_version and stored_version != current_embed_model:
                raise RuntimeError(
                    f"Embedding 模型已变更：当前={current_embed_model}，历史={stored_version}。"
                    "所有 drift 值将失效。请删除 qdrant_data/ 后重新 ingest。"
                )

        # 执行自动语义血缘发现
        print("开始计算血缘关系（向量 + BM25 融合）...")
        chunks_data = apply_lineage(chunks_data, current_embed_model)

        # 统计
        from collections import Counter
        status_counts = Counter(c.get("status", "unknown") for c in chunks_data)
        law_cat_counts = Counter(c.get("law_category", "unknown") for c in chunks_data)
        print(f"状态分布: {dict(status_counts)}")
        print(f"法律分类分布: {dict(law_cat_counts)}")

        matched = sum(1 for c in chunks_data if c.get("effective_start"))
        print(f"Excel 匹配率: {matched}/{len(chunks_data)} ({100*matched/len(chunks_data):.1f}%)")

        # Write JSONL
        with open(out_path, "w", encoding="utf-8") as f:
            for c in chunks_data:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        print(f"chunks={len(chunks_data)} written to {out_path}")
        all_chunks = chunks_data

        # 重建跨法律引用图（Direction 3）
        print("开始提取跨法律引用...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "extract_citations.py")],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"警告: 引用提取失败: {result.stderr}")
        else:
            # 只打印最后一行（保存路径）
            last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
            print(f"引用图重建完成: {last_line}")

    # Local embed + index
    print("开始生成嵌入向量（带进度条）...")
    t0 = time()
    texts = [c["text"] if isinstance(c, dict) else c.text for c in all_chunks]
    embeddings = []
    total_batches = (len(texts) + settings.local_embed_batch_size - 1) // settings.local_embed_batch_size
    for bi in range(total_batches):
        i = bi * settings.local_embed_batch_size
        batch = texts[i:i + settings.local_embed_batch_size]
        embeddings.extend(embed_texts(batch))
        if (bi + 1) % 20 == 0 or bi == total_batches - 1:
            elapsed = time() - t0
            rate = len(embeddings) / elapsed if elapsed > 0 else 0
            eta = (total_batches - bi - 1) * elapsed / (bi + 1) if bi > 0 else 0
            print(f"  [{bi+1}/{total_batches}] {len(embeddings)}/{len(texts)} ({rate:.1f}条/s, 剩余约{eta:.0f}s)")
    t1 = time()
    print(f"嵌入完成：{len(embeddings)} 条，耗时 {t1-t0:.1f}s")

    print("开始构建向量索引...")
    vector_size = len(embeddings[0])
    client = get_qdrant()
    ensure_collection(client, vector_size=vector_size)
    upsert_chunks(client, embeddings=embeddings, chunks=all_chunks)

    print("向量知识库重建完成！")
    print(f"qdrant_collection={settings.qdrant_collection} vectors={len(embeddings)} dim={vector_size}")


if __name__ == "__main__":
    rebuild_vectors_only = "--rebuild-vectors-only" in sys.argv
    main(rebuild_vectors_only=rebuild_vectors_only)
