from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator
from qdrant_client import QdrantClient

from rag_contract.chunking import Chunk
from rag_contract.counterfactual import CounterfactualAnalyzer
from rag_contract.domino import DominoAnalyzer, risk_level_from_drift
from rag_contract.index import get_qdrant, search
from rag_contract.lineage import LineageStep as _LineageStep, SensitiveWordDelta as _SensitiveWordDelta
from rag_contract.local_embed import embed_query
from rag_contract.llm_client import LLMAuthError, chat_answer
from rag_contract.prompting import SYSTEM_PROMPT, build_user_prompt
from rag_contract.retrieval import HybridRetriever
from rag_contract.settings import settings

# ============================================================
# App Setup
# ============================================================
app = FastAPI(title="RAG 民事法律咨询系统", version="0.1.0")

# ============================================================
# DriftService - 全法律漂移统计服务
# ============================================================

CHUNKS_PATH = settings.chunks_path or str(Path("data/chunks.jsonl"))

_CN_MAP = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
           '十': 10, '百': 100, '千': 1000, '万': 10000}

# 中文转数字
def _cn_to_int(cn: str) -> int:
    total = temp = 0
    for ch in cn:
        if ch == '十':
            temp = temp * 10 if temp else 10
            total += temp
            temp = 0
        elif ch == '千':
            total += temp * 1000 if temp else 1000
            temp = 0
        elif ch == '百':
            total += temp * 100 if temp else 100
            temp = 0
        elif ch == '万':
            total = (total + temp) * 10000
            temp = 0
        elif ch in _CN_MAP:
            temp = temp * 10 + _CN_MAP[ch]
    return total + temp

# 阿拉伯数字转数字
def _parse_article_number(art_no: str) -> int | None:
    if not art_no:
        return None
    import re
    m = re.match(r'^第([零一二三四五六七八九十百千万\d]+)条$', art_no)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        try:
            return _cn_to_int(m.group(1))
        except Exception:
            return None

# 全法律漂移统计服务
class DriftService:
    """全法律漂移统计服务"""
    _instance = None
    _stats: dict | None = None
     # 单例模式
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
     # 初始化
    def __init__(self):
        self._stats = None
        self._law_chunks: dict[str, list[dict]] = {}
    
    def load_data(self):
        """加载 chunks.jsonl 并计算统计（如果尚未加载）"""
        if self._stats is not None:
            return

        chunks_by_law: dict[str, list[dict]] = defaultdict(list)
        all_chunks = []

        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line.strip())
                if d.get("lineage_chain"):
                    all_chunks.append(d)
                    title = d.get("doc_title", "unknown")
                    chunks_by_law[title].append(d)

        self._law_chunks = dict(chunks_by_law)

        # 计算每部法律的统计
        stats = {}
        for doc_title, law_chunks in chunks_by_law.items():    # 遍历每部法律
            stat = {
                "doc_title": doc_title,     # 法律标题
                "version_count": len(set(c.get("effective_start") for c in law_chunks if c.get("effective_start"))),    # 版本数量
                "chunk_count": len(law_chunks),    # 段落数量
                "drift_scores": [],    # 漂移分数
                "law_logic_drift_scores": [],    # 法律逻辑漂移分数
                "relocated_chunks": [],  # 迁址段落统计
                "reassigned_chunks": [],  # 重分配段落统计
                "high_drift_chunks": [],  # 高漂移段落统计
            }
        # 遍历每个段落
            all_drift = []
            for c in law_chunks:
                for step in c.get("lineage_chain", []):
                    ds = step.get("drift_score")
                    if ds is None:
                        continue
                    art_no = c.get("article_no", "")
                    derived_from = step.get("derived_from_article")
                    similarity = step.get("similarity_with_prev")
                    change_type = step.get("change_type", "")

                    all_drift.append(ds)
                    stat["drift_scores"].append(ds)

                    # L2: 迁址
                    is_relocated = (
                        derived_from is not None
                        and derived_from != art_no
                        and similarity is not None
                        and similarity >= 0.9
                    )
                    # L3: 重分配
                    is_reassigned = (
                        derived_from == art_no
                        and similarity is not None
                        and similarity < 0.3
                        and change_type == "新增"
                    )
                # L4: 高漂移
                    if is_relocated:
                        stat["relocated_chunks"].append({
                            "article_no": art_no,
                            "derived_from": derived_from,
                            "similarity": similarity,
                            "drift_score": ds,
                            "text_preview": c.get("text", "")[:80],
                            "effective_start": c.get("effective_start"),
                            "effective_end": c.get("effective_end"),
                        })
                        stat["law_logic_drift_scores"].append(ds)
                    elif is_reassigned:
                        stat["reassigned_chunks"].append({
                            "article_no": art_no,
                            "similarity": similarity,
                            "drift_score": ds,
                            "text_preview": c.get("text", "")[:80],
                            "effective_start": c.get("effective_start"),
                            "effective_end": c.get("effective_end"),
                        })
                        stat["law_logic_drift_scores"].append(ds)
                    elif ds > 0.2 and derived_from == art_no:
                        stat["high_drift_chunks"].append({
                            "article_no": art_no,
                            "drift_score": ds,
                            "change_type": change_type,
                        })
                        stat["law_logic_drift_scores"].append(ds)

            total_ds = all_drift
            lds = stat["law_logic_drift_scores"]
            stat["avg_drift"] = sum(total_ds) / len(total_ds) if total_ds else 0
            stat["avg_law_logic_drift"] = sum(lds) / len(lds) if lds else 0
            stat["total_chunks"] = len(all_chunks)

            stats[doc_title] = stat

        self._stats = stats
     # 获取所有法律的统计
    def get_all_stats(self) -> dict:
        self.load_data()
        return self._stats
     # 获取指定法律的统计
    def get_law_stats(self, law_title: str) -> dict | None:
        self.load_data()
        return self._stats.get(law_title)
     # 获取虚拟章节热力图
    def get_chapters(self, law_title: str, chunk_size: int = 30) -> list[dict]:
        """获取虚拟章节热力图"""
        self.load_data()
        law_chunks = self._law_chunks.get(law_title, [])
        if not law_chunks:
            return []
        
        article_drifts: dict[str, list[float]] = defaultdict(list)     # 每个段落的漂移分数
        article_relocated: dict[str, int] = defaultdict(int)     # 每个段落的移址次数
        article_reassigned: dict[str, int] = defaultdict(int)     # 每个段落的重分配次数
         # 遍历每个段落
        for c in law_chunks:
            art_no = c.get("article_no", "")
            for step in c.get("lineage_chain", []):
                ds = step.get("drift_score")
                if ds is not None:
                    article_drifts[art_no].append(ds)

                derived_from = step.get("derived_from_article")
                similarity = step.get("similarity_with_prev")
                change_type = step.get("change_type", "")

                if derived_from == art_no and similarity is not None and similarity < 0.3 and change_type == "新增":
                    article_reassigned[art_no] += 1
                if derived_from is not None and derived_from != art_no and similarity is not None and similarity >= 0.9:
                    article_relocated[art_no] += 1

        article_nums = [_parse_article_number(a) for a in article_drifts.keys()]
        article_nums = [n for n in article_nums if n is not None]
        if not article_nums:
            return []

        min_art, max_art = min(article_nums), max(article_nums)
        chapters = []
        lo = min_art
        while lo <= max_art:
            hi = lo + chunk_size - 1
            chapter_label = f"第{lo}-{hi}条" if lo != hi else f"第{lo}条"

            chapter_drift = []
            major_count = 0
            relocated_count = 0
            reassigned_count = 0

            for art_no, drifts in article_drifts.items():
                art_int = _parse_article_number(art_no)
                if art_int is not None and lo <= art_int <= hi:
                    chapter_drift.extend(drifts)
                    for ds in drifts:
                        if ds > 0.2:
                            major_count += 1
                    relocated_count += article_relocated.get(art_no, 0)
                    reassigned_count += article_reassigned.get(art_no, 0)

            if chapter_drift:
                chapters.append({
                    "chapter_label": chapter_label,
                    "article_range": f"{lo}-{hi}",
                    "avg_drift": round(sum(chapter_drift) / len(chapter_drift), 4),
                    "major_revision_count": major_count,
                    "relocated_count": relocated_count,
                    "reassigned_count": reassigned_count,
                })

            lo += chunk_size

        return chapters

    def get_relocated_path(self, law_title: str, article_no: str) -> list[dict]:
        """查询某条文的迁址路径（前世今生）"""
        self.load_data()
        law_chunks = self._law_chunks.get(law_title, [])

        # 找到所有 version 的相同 article_no
        versions: dict[str, dict] = {}
        for c in law_chunks:
            if c.get("article_no") == article_no:
                eff = c.get("effective_start", "unknown")
                versions[eff] = c

        # 收集所有迁址记录
        path = []
        for eff, c in sorted(versions.items()):
            step = c.get("lineage_chain", [{}])[-1] if c.get("lineage_chain") else {}
            derived_from = step.get("derived_from_article")
            similarity = step.get("similarity_with_prev")
            change_type = step.get("change_type", "")
            drift_score = step.get("drift_score")

            path.append({
                "effective_start": eff,
                "article_no": article_no,
                "derived_from": derived_from,
                "similarity": similarity,
                "drift_score": drift_score,
                "change_type": change_type,
                "text_preview": c.get("text", "")[:100],
            })

        return path


# ============================================================
# FastAPI 响应模型
# ============================================================

qdrant: QdrantClient | None = None
retriever: HybridRetriever | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    current_date: str | None = Field(None, description="查询基准日期，格式 YYYY-MM-DD，用于筛选该日期有效的法律版本")


class SensitiveWordDelta(BaseModel):
    """FastAPI 响应模型：使用 from_attributes=True 让 Pydantic 从 dataclass 读取字段"""
    model_config = {"from_attributes": True}

    word: str
    old_category: str | None = None
    new_category: str | None = None
    category_shifted: bool = False
    polarity_flipped: bool = False
    legal_impact: str | None = None


class LineageStep(BaseModel):
    """FastAPI 响应模型：使用 from_attributes=True 让 Pydantic 从 dataclass 读取字段"""
    model_config = {"from_attributes": True}

    version_label: str
    derived_from_article: str | None = None
    similarity_with_prev: float | None = None
    drift_score: float | None = None
    change_type: str = "平移"
    is_split: bool = False
    is_merge: bool = False
    sensitive_deltas: list[dict] = []  # dict 直接序列化，避免嵌套 Pydantic 转换
    has_critical_change: bool = False


class Citation(BaseModel):     # FastAPI 响应模型
    label: str     # 段落标签
    doc_title: str       # 法律标题
    doc_type: str | None     # 法律类型
    jurisdiction: str | None     # 管辖区域
    publish_date: str | None  # 公布日期
    effective_start: str | None  # 施行日期（真正生效日）
    effective_end: str | None    # 失效日期
    change_type: str | None      # 修订/修正/新编
    law_category: str | None     # 法律/修正案/法律解释/决定
    status: str                  # 有效/已修改/尚未生效/已废止
    article_no: str | None     # 条文号
    clause_no: str | None        # 条款号
    item_no: str | None          # 项目号
    para_start: int              # 段落开始位置
    para_end: int                # 段落结束位置
    snippet: str                 # 段落摘要
    lineage_chain: list[LineageStep] = field(default_factory=list)  # 血缘链（从新到旧）


class AskResponse(BaseModel):     # FastAPI 响应模型
    answer: str     # 回答内容
    citations: list[Citation]     # 引用的法律段落
    current_date: str  # 实际用于筛选的基准日期
    historical_answer: str | None = None     # 历史回答内容
    historical_citations: list[Citation] | None = None     # 历史引用的法律段落


# ============================================================
# FastAPI 请求模型
# ============================================================

class DriftReportRequest(BaseModel):
    law_title: str = Field(..., min_length=1, max_length=200)
    current_date: str | None = Field(None, description="查询基准日期，格式 YYYY-MM-DD")


class HotspotItem(BaseModel):
    range: str  # e.g., "1-20条"
    intensity: str  # "High" / "Medium" / "Low"
    reason: str  # "Structural Reorganization" / "Content Evolution" / "Normal"


class HighDriftDetail(BaseModel):
    article_no: str
    status: str  # "Reassigned" / "Relocated" / "Modified"
    old_content_trace: str | None = None  # 迁址前的条文号
    similarity: float | None = None
    drift_score: float | None = None
    text_preview: str | None = None
    effective_status: str | None = None  # 基于 current_date 的动态法律有效性
    effective_start: str | None = None
    effective_end: str | None = None


class DriftReportResponse(BaseModel):
    law_title: str
    summary: dict  # avg_drift, major_changes_count, relocated_count, reassigned_count
    hotspots: list[HotspotItem]
    high_drift_details: list[HighDriftDetail]
    chapters: list[dict]  # full chapter-level data


@app.on_event("startup")
def _startup() -> None:
    global qdrant, retriever
    qdrant = get_qdrant()
    if not settings.chunks_path or not settings.chunks_path:
        raise RuntimeError("Missing chunks_path setting")
    retriever = HybridRetriever.from_jsonl(settings.chunks_path)
    # 预加载 DominoAnalyzer（reference_graph.json）
    DominoAnalyzer.get_instance().load()
    # 预加载 CounterfactualAnalyzer
    CounterfactualAnalyzer(chunks_path=settings.chunks_path)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


def _build_citations(
    contexts: list[tuple[int, Chunk, list]],
    current_date: str,
) -> list[Citation]:
    """从 contexts 构建 Citation 列表，使用基于 current_date 的动态 status。"""
    citations: list[Citation] = []
    for _rank, (_idx, c, _lineage_chain) in enumerate(contexts, start=1):
        snippet = c.text
        if len(snippet) > 500:
            snippet = snippet[:500] + "…"

        # 动态计算 status（不修改原始 chunk，避免并发问题）
        dynamic_status = c.resolve_status(current_date)
        original_status = c.status
        c.status = dynamic_status  # 临时覆盖，供 citation_label_with_status 使用

        # 构建 lineage_chain
        lineage_chain: list[LineageStep] = []
        if c.lineage_chain:
            for step in c.lineage_chain:
                if isinstance(step, dict):
                    lineage_chain.append(LineageStep(
                        version_label=step.get("version_label", ""),
                        derived_from_article=step.get("derived_from_article"),
                        similarity_with_prev=step.get("similarity_with_prev"),
                        drift_score=step.get("drift_score"),
                        change_type=step.get("change_type", "平移"),
                        is_split=step.get("is_split", False),
                        is_merge=step.get("is_merge", False),
                        sensitive_deltas=step.get("sensitive_deltas", []),
                        has_critical_change=step.get("has_critical_change", False),
                    ))
                else:
                    lineage_chain.append(step)

        # 恢复原始 status
        c.status = original_status
         # 构建 citation 实例
        citations.append(
            Citation(
                label=c.citation_label_with_status(),     # 段落标签
                doc_title=c.doc_title,     # 法律标题
                doc_type=c.doc_type,     # 法律类型
                jurisdiction=c.jurisdiction,     # 管辖区域
                publish_date=c.publish_date,     # 发布日期
                effective_start=c.effective_start,     # 施行日期
                effective_end=c.effective_end,     # 有效截至日期
                change_type=c.change_type,     # 变更类型
                law_category=c.law_category,     # 法律分类
                status=dynamic_status,     # 法律有效性
                article_no=c.article_no,     # 条文号
                clause_no=c.clause_no,     # 条款号
                item_no=c.item_no,     # 条款项目号
                para_start=c.para_start,     # 段落起始位置
                para_end=c.para_end,     # 段落结束位置
                snippet=snippet,     # 段落预览
                lineage_chain=lineage_chain,     #  法律血缘链
            )
        )
    return citations

# POST /ask
# 问法模型
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    if qdrant is None or retriever is None:
        raise HTTPException(status_code=503, detail="Service not ready; build index first.")

    try:
        qv = embed_query(req.question)
    except LLMAuthError as e:
        raise HTTPException(status_code=400, detail={
            "error": str(e),
            "suggestion": "请检查 API Key 配置或网络连接。向量嵌入依赖 LLM API，请确保 DEEPSEEK_API_KEY 已正确设置。"
        })

    current_date = req.current_date or "9999-12-31"

    # 1. Qdrant 向量检索（扩大 limit）
    hits = search(qdrant, qv, limit=settings.vector_top_k * 3)
    raw_hits = []
    scored_points = getattr(hits, "points", hits)
    for h in scored_points:
        try:
            idx = int(getattr(h, "id"))
        except Exception:
            continue
        raw_hits.append((idx, float(getattr(h, "score"))))

    # 2. BM25 + 融合排序（Hybrid-on-Demand: 仅当向量置信度不足时激活 BM25）
    bm25_scores = retriever.bm25_scores(req.question)

    # Hybrid-on-Demand gate: check vector top-1 confidence
    _hybrid_threshold = getattr(settings, "hybrid_confidence_threshold", 0.75)
    _activate_bm25 = retriever.should_activate_bm25(raw_hits, _hybrid_threshold)

    if _activate_bm25:
        combined = retriever.combine_scores(raw_hits, bm25_scores)[: settings.final_top_n]
    else:
        # Vector-only path: skip BM25 to save ~470 ms latency
        combined = [(idx, score) for idx, score in raw_hits[: settings.final_top_n]]

    # 3. 按日期分离：现行有效 vs 历史版本
    current_contexts: list[tuple[int, Chunk, list]] = []
    historical_contexts: list[tuple[int, Chunk, list]] = []

    for idx, _ in combined:
        c = retriever.chunks[idx]
        es = c.effective_start  # 施行日期，必须有值才参与过滤
        ee = c.effective_end    # 失效日期，None 表示最新版（永不过期）

        if not es:
            # 没有有效起始日期的 chunk，跳过（数据质量问题）
            continue

        lineage_chain = c.lineage_chain if c.lineage_chain else []

        if ee is None:
            # 最新版本：只要 effective_start <= current_date 就有效
            if es <= current_date:
                current_contexts.append((idx, c, lineage_chain))
            # else: effective_start > current_date，尚未生效，跳过
        elif current_date <= ee:
            # 有失效日期，且当前日期在有效期内
            if es <= current_date:
                current_contexts.append((idx, c, lineage_chain))
            # else: es > current_date，尚未生效
        else:
            # current_date > ee，已失效 → 历史版本
            historical_contexts.append((idx, c, lineage_chain))

    # 4. 生成现行法律回答
    current_answer = ""
    current_citations: list[Citation] = []
    if current_contexts:
        user_prompt = build_user_prompt(req.question, current_contexts)
        try:
            current_answer = chat_answer(SYSTEM_PROMPT, user_prompt)
        except LLMAuthError as e:
            raise HTTPException(status_code=400, detail={
                "error": str(e),
                "suggestion": "请检查 API Key 配置或网络连接。问答功能依赖 LLM 调用，请确保 DEEPSEEK_API_KEY 已正确设置。"
            })
        current_citations = _build_citations(current_contexts, current_date)

    # 5. 生成历史版本回答（如果有历史版本）
    historical_answer = None
    historical_citations: list[Citation] | None = None
    if historical_contexts:
        historical_prompt = build_user_prompt(req.question, historical_contexts)
        try:
            historical_answer = chat_answer(SYSTEM_PROMPT, historical_prompt)
        except LLMAuthError as e:
            raise HTTPException(status_code=400, detail={
                "error": str(e),
                "suggestion": "请检查 API Key 配置或网络连接。问答功能依赖 LLM 调用，请确保 DEEPSEEK_API_KEY 已正确设置。"
            })
        historical_citations = _build_citations(historical_contexts, current_date)

    # 如果现行回答为空，给出明确提示
    if not current_answer.strip():
        current_answer = f"在您指定的日期（{current_date}）下，暂无现行有效的相关法律条文。"

    return AskResponse(
        answer=current_answer.strip(),
        citations=current_citations,
        current_date=current_date,
        historical_answer=historical_answer.strip() if historical_answer else None,
        historical_citations=historical_citations if historical_citations else None,
    )


# ============================================================
# POST /drift_report
# 全法律漂移报告 API
# ============================================================

@app.post("/drift_report", response_model=DriftReportResponse)
def drift_report(req: DriftReportRequest) -> DriftReportResponse:
    """全法律漂移报告 API"""

    # 懒加载 DriftService
    ds = DriftService.get_instance()
    ds.load_data()

    stat = ds._stats.get(req.law_title)
    if stat is None:
        # 尝试模糊匹配
        matched = [k for k in ds._stats.keys() if req.law_title in k]
        if matched:
            stat = ds._stats[matched[0]]
            req = DriftReportRequest(law_title=matched[0])
        else:
            raise HTTPException(status_code=404, detail=f"Law '{req.law_title}' not found")

    # 获取章节数据
    chapters = ds.get_chapters(req.law_title)

    # 生成 hotspots
    hotspots = []
    for ch in chapters:
        avg_d = ch["avg_drift"]
        relocated = ch["relocated_count"]
        reassigned = ch["reassigned_count"]

        if reassigned > 3:
            intensity = "High"
            reason = "Structural Reorganization"
        elif relocated > 3:
            intensity = "High"
            reason = "Logical Migration"
        elif avg_d >= 0.2:
            intensity = "High"
            reason = "Content Evolution"
        elif avg_d >= 0.1:
            intensity = "Medium"
            reason = "Moderate Revision"
        else:
            intensity = "Low"
            reason = "Stable"

        hotspots.append(HotspotItem(
            range=ch["chapter_label"],
            intensity=intensity,
            reason=reason,
        ))

    # 生成高漂移详情（含动态法律有效性 status）
    current_date = req.current_date or "9999-12-31"
    high_drift_details = []

    def _resolve_eff_status(item: dict) -> str:
        es = item.get("effective_start") or ""
        ee = item.get("effective_end") or "9999-12-31"
        if es and es > current_date:
            return "尚未生效"
        if item.get("effective_end") and item.get("effective_end") < current_date:
            return "已修改"
        return "有效"

    for item in (stat.get("relocated_chunks", [])[:5]):
        high_drift_details.append(HighDriftDetail(
            article_no=item["article_no"],
            status="Relocated",
            old_content_trace=item.get("derived_from"),
            similarity=item.get("similarity"),
            drift_score=item.get("drift_score"),
            text_preview=item.get("text_preview"),
            effective_status=_resolve_eff_status(item),
            effective_start=item.get("effective_start"),
            effective_end=item.get("effective_end"),
        ))
    for item in (stat.get("reassigned_chunks", [])[:5]):
        high_drift_details.append(HighDriftDetail(
            article_no=item["article_no"],
            status="Reassigned",
            old_content_trace=None,
            similarity=item.get("similarity"),
            drift_score=item.get("drift_score"),
            text_preview=item.get("text_preview"),
            effective_status=_resolve_eff_status(item),
            effective_start=item.get("effective_start"),
            effective_end=item.get("effective_end"),
        ))

    # summary
    lds = stat.get("law_logic_drift_scores", [])
    summary = {
        "avg_drift": round(stat.get("avg_drift", 0), 4),
        "avg_law_logic_drift": round(stat.get("avg_law_logic_drift", 0), 4),
        "major_changes_count": len(stat.get("high_drift_chunks", [])),
        "relocated_count": len(stat.get("relocated_chunks", [])),
        "reassigned_count": len(stat.get("reassigned_chunks", [])),
        "version_count": stat.get("version_count", 0),
        "total_chunks": stat.get("chunk_count", 0),
    }

    return DriftReportResponse(
        law_title=req.law_title,
        summary=summary,
        hotspots=hotspots,
        high_drift_details=high_drift_details[:10],
        chapters=chapters,
    )

# GET /drift_report
# 全法律漂移报告 API
# ============================================================

@app.get("/drift_report")
def drift_report_get(
    law_title: str = Query(..., min_length=1),
    current_date: str | None = Query(None, description="查询基准日期，格式 YYYY-MM-DD"),
) -> DriftReportResponse:
    """GET 版本"""
    return drift_report(DriftReportRequest(law_title=law_title, current_date=current_date))

# GET /drift_report/laws
# 返回所有法律列表（用于前端选择）
# ============================================================

@app.get("/drift_report/laws")
def drift_report_laws() -> dict:
    """返回所有法律列表（用于前端选择）"""
    ds = DriftService.get_instance()
    ds.load_data()
    return {
        "count": len(ds._stats),
        "laws": list(ds._stats.keys()),
    }


# ============================================================
# /domino_impact API（跨法律多米诺效应检测 - Direction 3）
# ============================================================

class DominoImpactRequest(BaseModel):     # 请求参数
    law_title: str = Field(..., min_length=1, max_length=200)     # 法律标题
    article_no: str = Field(..., min_length=1, max_length=50, description="条文编号（如'第十八条'），也可传入'整部法律'查询整部法律被引用的情况")
    recursive: bool = False     # 是否递归查询
    max_depth: int = Field(2, ge=1, le=5)     # 最大递归深度
    current_date: str | None = Field(None, description="查询基准日期，格式 YYYY-MM-DD")     # 查询基准日期


class DominoImpactItem(BaseModel):     # 多米诺效应项
    citing_law: str  # 引用法律标题
    citing_article: str    # 引用文章编号
    reference_text: str    # 引用文本摘要
    keyword: str | None = None     # 关键词
    risk_level: str  # High / Medium / Low / Potential / Unknown     # 风险等级
    risk_score: float | None = None  # 深度衰减后的风险分数
    via_article: str | None = None  # 仅 indirect_impacts 中出现     # 通过文章编号


class DominoImpactResponse(BaseModel):     # 响应参数
    trigger_node: str     # 触发节点标题
    trigger_law_title: str     # 触发法律法律标题
    trigger_article_no: str     # 触发法律文章编号
    effective_status: str | None = None     # 触发法律生效状态
    drift_score: float | None = None     # 触发法律漂移分数
    direct_impacts: list[DominoImpactItem]     # 直接影响项
    indirect_impacts: list[DominoImpactItem]     # 间接影响项
    total_affected_articles: int     # 总受影响文章数

#函数：查询触发节点的 status 和 drift_score（status 基于 current_date 动态计算）
def _resolve_trigger_metadata(
    law_title: str, article_no: str, current_date: str
) -> tuple[str | None, float | None, str | None]:
    """从 DriftService 中查询触发节点的 status 和 drift_score（status 基于 current_date 动态计算）

    Returns:
        (matched_doc_title, drift_score, status)
    """
    ds = DriftService.get_instance()
    ds.load_data()

    matched_title: str | None = None
    if law_title in ds._law_chunks:
        matched_title = law_title
    else:
        # 模糊匹配（可能用户输入的是简称或带版本后缀）
        cleaned_input = law_title.replace(" ", "").replace("\n", "")
        for k in ds._law_chunks.keys():
            cleaned_k = k.replace(" ", "").replace("\n", "")
            if cleaned_input == cleaned_k or cleaned_input in cleaned_k or cleaned_k.endswith(cleaned_input):
                matched_title = k
                break

    if matched_title is None:
        return None, None, None

    chunks = ds._law_chunks[matched_title]
    matching = [c for c in chunks if c.get("article_no") == article_no]
    if not matching:
        return matched_title, None, None

    # 取最新版本（按 effective_start 倒序）
    latest = max(matching, key=lambda c: c.get("effective_start") or "")

    # 动态计算 status（覆盖静态值）
    es = latest.get("effective_start") or ""
    ee = latest.get("effective_end") or "9999-12-31"
    if es and es > current_date:
        status = "尚未生效"
    elif latest.get("effective_end") and latest.get("effective_end") < current_date:
        status = "已修改"
    else:
        status = "有效"

    drift_score: float | None = None
    chain_steps = latest.get("lineage_chain") or []
    if chain_steps:
        first_step = chain_steps[0]
        if isinstance(first_step, dict):
            drift_score = first_step.get("drift_score")

    return matched_title, drift_score, status

# POST /domino_impact API（跨法律多米诺效应检测 - Direction 3）
# ============================================================

@app.post("/domino_impact", response_model=DominoImpactResponse)
def domino_impact(req: DominoImpactRequest) -> DominoImpactResponse:
    """跨法律多米诺效应检测：当某法律条文修订时，列出所有引用了它的下游法律"""

    analyzer = DominoAnalyzer.get_instance()
    analyzer.load()

    current_date = req.current_date or "9999-12-31"

    # 查询触发节点的元信息（drift_score / status，status 基于 current_date 动态计算）
    matched_title, trigger_drift, trigger_status = _resolve_trigger_metadata(
        req.law_title, req.article_no, current_date
    )

    # 影响链 BFS（传入 trigger 的 drift_score 用于深度衰减）
    chain = analyzer.get_impact_chain(
        law_title=matched_title or req.law_title,
        article_no=req.article_no,
        recursive=req.recursive,
        max_depth=req.max_depth,
        base_drift_score=trigger_drift,
    )

    direct_items = [
        DominoImpactItem(
            citing_law=imp.get("citing_law", ""),
            citing_article=imp.get("citing_article", ""),
            reference_text=imp.get("reference_text", ""),
            keyword=imp.get("keyword"),
            risk_score=imp.get("risk_score"),
            risk_level=risk_level_from_drift(imp.get("risk_score")),
        )
        for imp in chain.get("direct_impacts", [])
    ]

    indirect_items = [
        DominoImpactItem(
            citing_law=imp.get("citing_law", ""),
            citing_article=imp.get("citing_article", ""),
            reference_text=imp.get("reference_text", ""),
            keyword=imp.get("keyword"),
            risk_score=imp.get("risk_score"),
            risk_level=risk_level_from_drift(imp.get("risk_score")),
            via_article=imp.get("via_article"),
        )
        for imp in chain.get("indirect_impacts", [])
    ]

    return DominoImpactResponse(
        trigger_node=chain.get("trigger_node", ""),
        trigger_law_title=matched_title or req.law_title,
        trigger_article_no=req.article_no,
        effective_status=trigger_status,
        drift_score=trigger_drift,
        direct_impacts=direct_items,
        indirect_impacts=indirect_items,
        total_affected_articles=len(direct_items) + len(indirect_items),
    )

# GET /domino_impact API（跨法律多米诺效应检测 - Direction 3）
# ============================================================

@app.get("/domino_impact")
def domino_impact_get(
    law_title: str = Query(..., min_length=1, max_length=200),
    article_no: str = Query(..., min_length=1, max_length=50),
    recursive: bool = Query(False),
    max_depth: int = Query(2, ge=1, le=5),
    current_date: str | None = Query(None, description="查询基准日期，格式 YYYY-MM-DD"),
) -> DominoImpactResponse:
    """GET 版本（便于浏览器调试）"""
    return domino_impact(DominoImpactRequest(
        law_title=law_title,
        article_no=article_no,
        recursive=recursive,
        max_depth=max_depth,
        current_date=current_date,
    ))

# GET /domino_impact/stats API（引用图全局统计 - Direction 3）
# ============================================================

@app.get("/domino_impact/stats")
def domino_impact_stats() -> dict:
    """返回引用图全局统计（节点数、边数、法律数）"""
    analyzer = DominoAnalyzer.get_instance()
    analyzer.load()
    by_article = analyzer.by_article
    cites = analyzer.cites
    edge_count = sum(len(v) for v in by_article.values())
    return {
        "cited_articles": len(by_article),
        "citing_articles": len(cites),
        "total_edges": edge_count,
        "laws_count": len(analyzer.laws),
        "version": analyzer._graph.get("version"),
    }


def _unwrap_law_title(title: str) -> str:
    title = (title or "").strip()
    if title.startswith("《") and "》" in title:
        return title[1:title.index("》")]
    return title


def _split_graph_key(key: str) -> tuple[str, str]:
    key = (key or "").strip()
    if key.startswith("《") and "》" in key:
        close = key.index("》")
        return key[1:close], key[close + 1:] or "整部法律"
    return "", key


def _graph_law_id(law_title: str) -> str:
    return f"law::{law_title}"


def _graph_article_id(law_title: str, article_no: str) -> str:
    if article_no == "整部法律":
        return _graph_law_id(law_title)
    return f"article::{law_title}::{article_no}"


def _short_law_label(law_title: str) -> str:
    label = law_title.replace("中华人民共和国", "")
    return label or law_title


def _citation_degree_risk(total_degree: int) -> str:
    if total_degree >= 8:
        return "High"
    if total_degree >= 3:
        return "Medium"
    if total_degree > 0:
        return "Low"
    return "Unknown"


@app.get("/knowledge_graph")
def knowledge_graph(
    max_nodes: int = Query(5000, ge=200, le=10000),
    include_law_edges: bool = Query(True),
) -> dict:
    """返回前端知识图谱所需的全量引用网络。

    该接口不替代 /domino_impact；它负责全局图谱展示，/domino_impact 继续负责
    选中条文后的传播链分析。
    """
    analyzer = DominoAnalyzer.get_instance()
    analyzer.load()

    by_article = analyzer.by_article
    article_meta: dict[str, dict[str, str | int | None]] = {}
    law_titles: set[str] = {_unwrap_law_title(law) for law in analyzer.laws if law}
    edge_map: dict[tuple[str, str, str], dict] = {}
    in_degree: defaultdict[str, int] = defaultdict(int)
    out_degree: defaultdict[str, int] = defaultdict(int)

    def add_article(
        law_title: str,
        article_no: str,
        reference_text: str | None = None,
        keyword: str | None = None,
    ) -> str:
        law_title = _unwrap_law_title(law_title)
        article_no = article_no or "整部法律"
        if law_title:
            law_titles.add(law_title)
        node_id = _graph_article_id(law_title, article_no)
        if article_no != "整部法律":
            current = article_meta.get(node_id)
            if current is None:
                article_meta[node_id] = {
                    "id": node_id,
                    "law_title": law_title,
                    "article_no": article_no,
                    "reference_text": reference_text,
                    "keyword": keyword,
                }
            else:
                if reference_text and not current.get("reference_text"):
                    current["reference_text"] = reference_text
                if keyword and not current.get("keyword"):
                    current["keyword"] = keyword
        return node_id

    def add_edge(source_id: str, target_id: str, label: str, reference_text: str | None = None) -> None:
        if not source_id or not target_id or source_id == target_id:
            return
        key = (source_id, target_id, label)
        if key not in edge_map:
            edge_map[key] = {
                "from": source_id,
                "to": target_id,
                "label": label,
                "risk_level": "Unknown",
                "is_indirect": label != "包含",
                "reference_text": reference_text,
                "count": 1,
            }
        else:
            edge_map[key]["count"] += 1
            if reference_text and not edge_map[key].get("reference_text"):
                edge_map[key]["reference_text"] = reference_text
        out_degree[source_id] += 1
        in_degree[target_id] += 1

    for cited_key, citing_items in by_article.items():
        cited_law, cited_article = _split_graph_key(cited_key)
        cited_id = add_article(cited_law, cited_article)
        for cite in citing_items:
            citing_law = _unwrap_law_title(str(cite.get("citing_law", "")))
            citing_article = str(cite.get("citing_article", "") or "整部法律")
            reference_text = cite.get("reference_text")
            keyword = cite.get("keyword")
            citing_id = add_article(citing_law, citing_article, reference_text, keyword)
            add_edge(cited_id, citing_id, "引用传导", reference_text)

    for meta in article_meta.values():
        law_title = str(meta["law_title"])
        node_id = str(meta["id"])
        if include_law_edges:
            add_edge(_graph_law_id(law_title), node_id, "包含")

    nodes: list[dict] = []
    for law_title in sorted(law_titles):
        if not law_title:
            continue
        node_id = _graph_law_id(law_title)
        total_degree = in_degree[node_id] + out_degree[node_id]
        nodes.append({
            "id": node_id,
            "label": _short_law_label(law_title),
            "law_title": law_title,
            "article_no": "整部法律",
            "node_type": "law",
            "risk_level": "Unknown",
            "level": "trigger",
            "reference_text": "法律节点，连接本法条文与跨法律引用关系。",
            "keyword": "法律",
            "inbound_count": in_degree[node_id],
            "outbound_count": out_degree[node_id],
            "degree": total_degree,
        })

    for meta in article_meta.values():
        law_title = str(meta["law_title"])
        article_no = str(meta["article_no"])
        node_id = str(meta["id"])
        total_degree = in_degree[node_id] + out_degree[node_id]
        nodes.append({
            "id": node_id,
            "label": f"{_short_law_label(law_title)}\n{article_no}",
            "law_title": law_title,
            "article_no": article_no,
            "node_type": "article",
            "risk_level": _citation_degree_risk(total_degree),
            "level": "indirect",
            "reference_text": meta.get("reference_text"),
            "keyword": meta.get("keyword") or "引用条文",
            "inbound_count": in_degree[node_id],
            "outbound_count": out_degree[node_id],
            "degree": total_degree,
        })

    edges = list(edge_map.values())
    for edge in edges:
        edge["risk_level"] = _citation_degree_risk(
            in_degree[edge["to"]] + out_degree[edge["to"]]
        )

    total_nodes = len(nodes)
    total_edges = len(edges)
    returned_nodes = nodes
    returned_edges = edges
    truncated = total_nodes > max_nodes
    if truncated:
        law_nodes = [node for node in nodes if node["node_type"] == "law"]
        article_nodes = sorted(
            [node for node in nodes if node["node_type"] == "article"],
            key=lambda node: int(node.get("degree") or 0),
            reverse=True,
        )
        remaining = max(max_nodes - len(law_nodes), 0)
        returned_nodes = law_nodes + article_nodes[:remaining]
        allowed = {node["id"] for node in returned_nodes}
        returned_edges = [
            edge for edge in edges
            if edge["from"] in allowed and edge["to"] in allowed
        ]

    return {
        "nodes": returned_nodes,
        "edges": returned_edges,
        "stats": {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "returned_nodes": len(returned_nodes),
            "returned_edges": len(returned_edges),
            "law_count": len([law for law in law_titles if law]),
            "article_count": len(article_meta),
            "truncated": truncated,
            "version": analyzer._graph.get("version"),
        },
    }


def _edge_risk_from_count(count: int) -> str:
    if count >= 20:
        return "High"
    if count >= 5:
        return "Medium"
    if count > 0:
        return "Low"
    return "Unknown"


def _build_graph_runtime() -> dict:
    analyzer = DominoAnalyzer.get_instance()
    analyzer.load()

    article_meta: dict[str, dict[str, str | None]] = {}
    law_titles: set[str] = {_unwrap_law_title(law) for law in analyzer.laws if law}
    citation_edges: dict[tuple[str, str], dict] = {}
    law_edges: dict[tuple[str, str], dict] = {}
    in_degree: defaultdict[str, int] = defaultdict(int)
    out_degree: defaultdict[str, int] = defaultdict(int)
    law_in_degree: defaultdict[str, int] = defaultdict(int)
    law_out_degree: defaultdict[str, int] = defaultdict(int)
    article_ids_by_law: defaultdict[str, list[str]] = defaultdict(list)
    inbound_neighbors: defaultdict[str, set[str]] = defaultdict(set)
    outbound_neighbors: defaultdict[str, set[str]] = defaultdict(set)

    def add_article(law_title: str, article_no: str, reference_text: str | None, keyword: str | None) -> str:
        law_title = _unwrap_law_title(law_title)
        article_no = article_no or "整部法律"
        if law_title:
            law_titles.add(law_title)
        node_id = _graph_article_id(law_title, article_no)
        if article_no != "整部法律" and node_id not in article_meta:
            article_meta[node_id] = {
                "law_title": law_title,
                "article_no": article_no,
                "reference_text": reference_text,
                "keyword": keyword,
            }
            article_ids_by_law[law_title].append(node_id)
        return node_id

    def add_citation_edge(source_id: str, target_id: str, reference_text: str | None) -> None:
        if not source_id or not target_id or source_id == target_id:
            return
        key = (source_id, target_id)
        if key not in citation_edges:
            citation_edges[key] = {
                "from": source_id,
                "to": target_id,
                "label": "引用传导",
                "risk_level": "Unknown",
                "is_indirect": True,
                "reference_text": reference_text,
                "count": 1,
            }
        else:
            citation_edges[key]["count"] += 1
            if reference_text and not citation_edges[key].get("reference_text"):
                citation_edges[key]["reference_text"] = reference_text
        in_degree[target_id] += 1
        out_degree[source_id] += 1
        inbound_neighbors[target_id].add(source_id)
        outbound_neighbors[source_id].add(target_id)

    def add_law_edge(source_law: str, target_law: str, reference_text: str | None) -> None:
        source_law = _unwrap_law_title(source_law)
        target_law = _unwrap_law_title(target_law)
        if not source_law or not target_law or source_law == target_law:
            return
        source_id = _graph_law_id(source_law)
        target_id = _graph_law_id(target_law)
        key = (source_id, target_id)
        if key not in law_edges:
            law_edges[key] = {
                "from": source_id,
                "to": target_id,
                "label": "跨法律引用",
                "risk_level": "Unknown",
                "is_indirect": False,
                "reference_text": reference_text,
                "count": 1,
            }
        else:
            law_edges[key]["count"] += 1
            if reference_text and not law_edges[key].get("reference_text"):
                law_edges[key]["reference_text"] = reference_text
        law_in_degree[target_id] += 1
        law_out_degree[source_id] += 1

    for cited_key, citing_items in analyzer.by_article.items():
        cited_law, cited_article = _split_graph_key(cited_key)
        cited_id = add_article(cited_law, cited_article, None, None)
        for cite in citing_items:
            citing_law = _unwrap_law_title(str(cite.get("citing_law", "")))
            citing_article = str(cite.get("citing_article", "") or "整部法律")
            reference_text = cite.get("reference_text")
            keyword = cite.get("keyword")
            citing_id = add_article(citing_law, citing_article, reference_text, keyword)
            add_citation_edge(cited_id, citing_id, reference_text)
            add_law_edge(cited_law, citing_law, reference_text)

    for edge in citation_edges.values():
        edge["risk_level"] = _edge_risk_from_count(int(edge.get("count") or 0))
    for edge in law_edges.values():
        edge["risk_level"] = _edge_risk_from_count(int(edge.get("count") or 0))

    return {
        "article_meta": article_meta,
        "law_titles": law_titles,
        "citation_edges": citation_edges,
        "law_edges": law_edges,
        "in_degree": in_degree,
        "out_degree": out_degree,
        "law_in_degree": law_in_degree,
        "law_out_degree": law_out_degree,
        "article_ids_by_law": article_ids_by_law,
        "inbound_neighbors": inbound_neighbors,
        "outbound_neighbors": outbound_neighbors,
        "version": analyzer._graph.get("version"),
    }


def _knowledge_graph_stats(runtime: dict, mode: str, returned_nodes: int, returned_edges: int) -> dict:
    return {
        "mode": mode,
        "total_nodes": len(runtime["law_titles"]) + len(runtime["article_meta"]),
        "total_edges": len(runtime["citation_edges"]) + len(runtime["article_meta"]),
        "returned_nodes": returned_nodes,
        "returned_edges": returned_edges,
        "law_count": len([law for law in runtime["law_titles"] if law]),
        "article_count": len(runtime["article_meta"]),
        "truncated": False,
        "version": runtime["version"],
    }


def _law_overview_node(runtime: dict, law_title: str) -> dict:
    node_id = _graph_law_id(law_title)
    degree = runtime["law_in_degree"][node_id] + runtime["law_out_degree"][node_id]
    article_count = len(runtime["article_ids_by_law"][law_title])
    return {
        "id": node_id,
        "label": _short_law_label(law_title),
        "law_title": law_title,
        "article_no": "整部法律",
        "node_type": "law",
        "risk_level": _edge_risk_from_count(degree),
        "level": "trigger",
        "reference_text": f"法律总览节点。引用网络内收录 {article_count} 个相关条文节点。",
        "keyword": "法律总览",
        "inbound_count": runtime["law_in_degree"][node_id],
        "outbound_count": runtime["law_out_degree"][node_id],
        "degree": degree,
    }


def _article_graph_node(runtime: dict, node_id: str) -> dict | None:
    meta = runtime["article_meta"].get(node_id)
    if not meta:
        return None
    law_title = str(meta["law_title"])
    article_no = str(meta["article_no"])
    degree = runtime["in_degree"][node_id] + runtime["out_degree"][node_id]
    return {
        "id": node_id,
        "label": f"{_short_law_label(law_title)}\n{article_no}",
        "law_title": law_title,
        "article_no": article_no,
        "node_type": "article",
        "risk_level": _citation_degree_risk(degree),
        "level": "indirect",
        "reference_text": meta.get("reference_text"),
        "keyword": meta.get("keyword") or "引用条文",
        "inbound_count": runtime["in_degree"][node_id],
        "outbound_count": runtime["out_degree"][node_id],
        "degree": degree,
    }


def _containment_edge(law_title: str, article_id: str) -> dict:
    return {
        "from": _graph_law_id(law_title),
        "to": article_id,
        "label": "包含",
        "risk_level": "Low",
        "is_indirect": False,
        "count": 1,
    }


@app.get("/knowledge_graph/overview")
def knowledge_graph_overview() -> dict:
    """轻量法律层聚合图，用作可视化分析首屏。"""
    runtime = _build_graph_runtime()
    nodes = [
        _law_overview_node(runtime, law)
        for law in sorted(runtime["law_titles"])
        if law
    ]
    edges = list(runtime["law_edges"].values())
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": _knowledge_graph_stats(runtime, "overview", len(nodes), len(edges)),
    }


@app.get("/knowledge_graph/subgraph")
def knowledge_graph_subgraph(
    law_title: str = Query(..., min_length=1, max_length=200),
    article_no: str | None = Query(None, max_length=50),
    max_hops: int = Query(1, ge=1, le=3),
    max_neighbors: int = Query(220, ge=30, le=800),
) -> dict:
    """返回某部法律或某个条文的局部图，避免前端一次性布局全量条文图。"""
    runtime = _build_graph_runtime()
    selected_law = _unwrap_law_title(law_title)
    selected_article = article_no or "整部法律"
    article_meta = runtime["article_meta"]
    citation_edges = list(runtime["citation_edges"].values())
    selected_ids: set[str] = {_graph_law_id(selected_law)}

    def article_degree(node_id: str) -> int:
        return runtime["in_degree"][node_id] + runtime["out_degree"][node_id]

    if selected_article != "整部法律":
        center_id = _graph_article_id(selected_law, selected_article)
        seen = {center_id}
        frontier = {center_id}
        for _depth in range(max_hops):
            next_frontier: set[str] = set()
            for node_id in frontier:
                neighbors = sorted(
                    runtime["outbound_neighbors"][node_id] | runtime["inbound_neighbors"][node_id],
                    key=article_degree,
                    reverse=True,
                )
                for neighbor_id in neighbors:
                    if len(seen) >= max_neighbors:
                        break
                    if neighbor_id not in seen:
                        seen.add(neighbor_id)
                        next_frontier.add(neighbor_id)
            frontier = next_frontier
            if not frontier or len(seen) >= max_neighbors:
                break
        selected_ids.update(seen)
    else:
        own_articles = sorted(
            runtime["article_ids_by_law"][selected_law],
            key=article_degree,
            reverse=True,
        )[:max_neighbors]
        selected_ids.update(own_articles)
        own_set = set(own_articles)
        external_candidates: set[str] = set()
        for edge in citation_edges:
            if edge["from"] in own_set and edge["to"] not in own_set:
                external_candidates.add(edge["to"])
            if edge["to"] in own_set and edge["from"] not in own_set:
                external_candidates.add(edge["from"])
        selected_ids.update(
            sorted(external_candidates, key=article_degree, reverse=True)[: max(30, max_neighbors // 3)]
        )

    for node_id in list(selected_ids):
        meta = article_meta.get(node_id)
        if meta:
            selected_ids.add(_graph_law_id(str(meta["law_title"])))

    nodes: list[dict] = []
    for node_id in sorted(selected_ids):
        if node_id.startswith("law::"):
            nodes.append(_law_overview_node(runtime, node_id.removeprefix("law::")))
        else:
            node = _article_graph_node(runtime, node_id)
            if node:
                nodes.append(node)

    allowed_ids = {node["id"] for node in nodes}
    edges = [
        _containment_edge(str(article_meta[node_id]["law_title"]), node_id)
        for node_id in allowed_ids
        if node_id in article_meta and _graph_law_id(str(article_meta[node_id]["law_title"])) in allowed_ids
    ]
    edges.extend(
        edge for edge in citation_edges
        if edge["from"] in allowed_ids and edge["to"] in allowed_ids
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            **_knowledge_graph_stats(runtime, "subgraph", len(nodes), len(edges)),
            "target_law": selected_law,
            "target_article": selected_article,
        },
    }


# ============================================================
# /counterfactual API（反事实模拟 - Direction 4）
# ============================================================

class CounterfactualRequest(BaseModel):     # 请求参数
    law_title: str = Field(..., min_length=1, max_length=200)     # 目标法律条文名称
    article_no: str = Field(..., min_length=1, max_length=50)     # 目标法律条文编号
    direction: str = Field(..., min_length=1, max_length=200)     # 反事实方向（"增加" / "减少"）
    magnitude: str | None = None  # "轻微" / "中等" / "重大"  # 反事实强度
    include_indirect: bool = True  # 是否包含间接影响
    max_depth: int = Field(2, ge=1, le=5)  # 最大影响深度（1-5）
    current_date: str | None = Field(None, description="查询基准日期，格式 YYYY-MM-DD")  # 查询基准日期，格式 YYYY-MM-DD

    @field_validator("article_no")
    @classmethod
    def reject_whole_law(cls, v: str) -> str:
        if v == "整部法律":
            raise ValueError("反事实模拟仅支持具体条文，不支持'整部法律'")
        return v


class CounterfactualImpactItem(BaseModel):      # 影响链项
    law_title: str    # 影响法律条文名称
    article_no: str    # 影响法律条文编号
    risk_level: str  # High / Medium / Low    # 影响风险等级
    llm_reasoning: str    # 影响原因解释


class CounterfactualResponse(BaseModel):     # 响应参数
    target_law: str     # 目标法律条文名称
    target_article: str     # 目标法律条文编号
    target_text: str | None     # 目标法律条文内容
    target_status: str | None = None  # 基于 current_date 的动态法律有效性   # 当前法律有效性
    original_direction: str     # 原始反事实方向（"增加" / "减少"）
    interpreted_direction: str     # 解释后的反事实方向（"增加" / "减少"）
    affected_categories: list[str]     # 受影响的法律分类
    direct_impacts: list[CounterfactualImpactItem]     # 直接影响链
    indirect_impacts: list[CounterfactualImpactItem]     # 间接影响链
    llm_summary: str     # LLM 概要（反事实模拟结果的摘要）
    total_affected: int     # 总影响条文数


@app.post("/counterfactual", response_model=CounterfactualResponse)
def counterfactual(req: CounterfactualRequest) -> CounterfactualResponse:
    """反事实模拟分析：当某法律条文向某个方向偏移时，会波及哪些下游条文"""
    current_date = req.current_date or "9999-12-31"

    try:
        analyzer = CounterfactualAnalyzer()
        result = analyzer.analyze(
            law_title=req.law_title,
            article_no=req.article_no,
            direction=req.direction,
            magnitude=req.magnitude,
            include_indirect=req.include_indirect,
            max_depth=req.max_depth,
        )
    except LLMAuthError as e:
        raise HTTPException(status_code=400, detail={
            "error": str(e),
            "suggestion": "请检查 API Key 配置或网络连接。反事实模拟依赖 LLM 调用，请确保 DEEPSEEK_API_KEY 已正确设置。"
        })

    # 动态计算目标条文的 status
    _matched_title, _trigger_drift, target_status = _resolve_trigger_metadata(
        req.law_title, req.article_no, current_date
    )

    direct_impacts = [
        CounterfactualImpactItem(
            law_title=item.get("law_title", ""),
            article_no=item.get("article_no", ""),
            risk_level=item.get("risk_level", "Unknown"),
            llm_reasoning=item.get("llm_reasoning", ""),
        )
        for item in result.get("direct_impacts", [])
    ]

    indirect_impacts = [
        CounterfactualImpactItem(
            law_title=item.get("law_title", ""),
            article_no=item.get("article_no", ""),
            risk_level=item.get("risk_level", "Unknown"),
            llm_reasoning=item.get("llm_reasoning", ""),
        )
        for item in result.get("indirect_impacts", [])
    ]

    return CounterfactualResponse(
        target_law=result["target_law"],
        target_article=result["target_article"],
        target_text=result.get("target_text"),
        target_status=target_status,
        original_direction=result["original_direction"],
        interpreted_direction=result["interpreted_direction"],
        affected_categories=result.get("affected_categories", []),
        direct_impacts=direct_impacts,
        indirect_impacts=indirect_impacts,
        llm_summary=result.get("llm_summary", ""),
        total_affected=result.get("total_affected", 0),
    )


@app.get("/counterfactual")
def counterfactual_get(
    law_title: str = Query(..., min_length=1, max_length=200),
    article_no: str = Query(..., min_length=1, max_length=50),
    direction: str = Query(..., min_length=1, max_length=200),
    magnitude: str | None = Query(None),
    include_indirect: bool = Query(True),
    max_depth: int = Query(2, ge=1, le=5),
    current_date: str | None = Query(None, description="查询基准日期，格式 YYYY-MM-DD"),
) -> CounterfactualResponse:
    """GET 版本（便于浏览器调试）"""
    return counterfactual(CounterfactualRequest(
        law_title=law_title,
        article_no=article_no,
        direction=direction,
        magnitude=magnitude,
        include_indirect=include_indirect,
        max_depth=max_depth,
        current_date=current_date,
    ))


@app.get("/counterfactual/directions")
def counterfactual_directions() -> dict:
    """返回支持的结构化方向列表"""
    from rag_contract.counterfactual import DIRECTION_REGISTRY
    return {
        "directions": [
            {"key": key, "desc": info["desc"], "affected": info["affected"]}
            for key, info in DIRECTION_REGISTRY.items()
        ]
    }


# ============================================================
# /law_articles API（条文内容预览）
# ============================================================

class LawArticleItem(BaseModel):
    article_no: str
    text_preview: str
    effective_start: str | None = None
    effective_end: str | None = None
    status: str  # 有效 / 尚未实施 / 已修改 / 已废止


class LawArticlesResponse(BaseModel):
    law_title: str
    articles: list[LawArticleItem]
    current_date: str


@app.get("/law_articles")
@app.get("/law_articles/{law_title}")
def law_articles(
    law_title: str = Path(...),
    current_date: str | None = Query(None),
) -> LawArticlesResponse:
    """返回某法律的所有条文号及内容摘要，按 current_date 确定最新有效版本

    - 按 current_date 过滤：只返回 effective_start <= current_date 的版本中 effective_start 最大的那条
    - 如果所有版本 effective_start > current_date（全为未来版本），返回 effective_start 最小的版本并标注 尚未实施
    """
    import datetime
    from dataclasses import asdict

    if current_date is None:
        current_date = datetime.date.today().isoformat()

    today = datetime.date.fromisoformat(current_date)

    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        all_chunks = [json.loads(line.strip()) for line in f]

    # 过滤该法律的所有 chunk
    law_chunks = [c for c in all_chunks if c.get("doc_title") == law_title]
    if not law_chunks:
        raise HTTPException(status_code=404, detail=f"Law '{law_title}' not found")

    # 按 article_no 分组，每组取 effective_start <= today 中最大的那条
    by_article: dict[str, dict] = {}
    for c in law_chunks:
        art_no = c.get("article_no", "")
        if not art_no:
            continue
        eff_start = c.get("effective_start") or "1900-01-01"
        eff_start_dt = datetime.date.fromisoformat(eff_start)

        if art_no not in by_article:
            by_article[art_no] = c
        else:
            existing_eff = by_article[art_no].get("effective_start") or "1900-01-01"
            existing_dt = datetime.date.fromisoformat(existing_eff)
            if eff_start_dt <= today and eff_start_dt > existing_dt:
                by_article[art_no] = c

    # 二次处理：检查是否所有版本都是未来版本
    # 如果 by_article 里的版本全是未来的，需要取 effective_start 最小的那个
    future_chunks = [c for c in law_chunks if c.get("article_no") and (datetime.date.fromisoformat(c.get("effective_start") or "1900-01-01") > today)]
    if future_chunks and not any(
        datetime.date.fromisoformat(c.get("effective_start") or "1900-01-01") <= today
        for c in law_chunks if c.get("article_no")
    ):
        # 全是未来版本，取 effective_start 最小的版本作为候选
        by_article.clear()
        for c in sorted(future_chunks, key=lambda x: x.get("effective_start") or "1900-01-01"):
            art_no = c.get("article_no", "")
            if art_no and art_no not in by_article:
                by_article[art_no] = c

    # 构建返回列表
    articles: list[LawArticleItem] = []
    for art_no in sorted(by_article.keys(), key=lambda x: _parse_article_number(x) or 0):
        c = by_article[art_no]
        eff_start = c.get("effective_start")
        eff_end = c.get("effective_end")
        eff_start_dt = datetime.date.fromisoformat(eff_start or "1900-01-01") if eff_start else None

        # 判断状态
        if eff_start_dt and eff_start_dt > today:
            status = "尚未实施"
        elif eff_end and datetime.date.fromisoformat(eff_end) < today:
            status = "已修改" if eff_start_dt else "已废止"
        else:
            status = "有效"

        text = c.get("text", "")
        preview = text[:120] + ("..." if len(text) > 120 else "")

        articles.append(LawArticleItem(
            article_no=art_no,
            text_preview=preview,
            effective_start=eff_start,
            effective_end=eff_end,
            status=status,
        ))

    return LawArticlesResponse(
        law_title=law_title,
        articles=articles,
        current_date=current_date,
    )
