"""
rag_contract/lineage.py

自动语义血缘发现（Automated Semantic Lineage）
- 向量相似度 + BM25 融合（0.65 + 0.35）
- 敏感词极性检测（含 category_shift）
- 1:N 拆分检测 & M:1 合并检测
- 链式血缘：每个版本只与前一版本对比，但保留完整变迁链
- Embedding 模型版本隔离
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

# ----------------------------------------------------------------------
# 日期噪声检测（施行日期变更不计入法理修订）
# ----------------------------------------------------------------------
_DATE_CLAUSE_PATTERN = re.compile(
    r'^第[零一二三四五六七八九十百千万\d]+条\s*本法自\d{4}年\d{1,2}月\d{1,2}日起施行[。.]?$'
)


def is_date_clause_text(text: str) -> bool:
    """检测文本是否仅为施行日期变更（如'第X条 本法自2024年1月1日起施行。）"""
    cleaned = re.sub(r'\s+', '', text.strip())
    return bool(_DATE_CLAUSE_PATTERN.match(cleaned))

# ----------------------------------------------------------------------
# 扩展 jieba 词典（法律专用词，避免分词错误导致漏检）
# ----------------------------------------------------------------------
_LEGAL_EXTRA_WORDS = [
    "准予", "不予", "应当", "必须", "可以", "不得", "禁止",
    "法定代表人", "第三人", "连带责任", "过错责任",
    "无过错责任", "缔约过失责任", "霸王条款", "格式条款",
    "不可抗力", "情势变更", "不安抗辩权", "同时履行抗辩权",
    "先履行抗辩权", "代位权", "撤销权", "解除权", "变更权",
    "善意第三人", "恶意第三人", "无效", "可撤销", "效力待定",
]
for _w in _LEGAL_EXTRA_WORDS:
    jieba.add_word(_w)

from .chunking import Chunk
from .local_embed import embed_texts
from .settings import settings

# ----------------------------------------------------------------------
# 敏感词分类体系
# ----------------------------------------------------------------------
SENSITIVE_WORD_CATEGORIES = {
    # ── 否定词 ──
    "negation": [
        "不", "无", "非", "否", "莫", "勿", "未", "别", "毋",
        "没有", "不存在", "拒绝", "防止", "避免", "杜绝",
    ],
    # ── 义务性规范（命令/禁止/责任） ──
    "obligation": [
        "应当", "必须", "可以", "不得", "禁止", "理应",
        "责令", "负责", "责任", "处罚", "处分", "罚款", "并处",
        "承担", "履行", "执行", "予以", "作出", "决定",
        "限期", "逾期", "及时", "立即",
        "义务", "职责", "改正", "没收", "赔偿", "处以", "处罚金",
        "责任人员", "主管人员", "刑事责任", "行政处罚", "行政处分",
    ],
    # ── 作用范围（空间/主体/例外） ──
    "scope": [
        "所有", "任何", "仅", "只", "仅限", "一切", "凡是",
        "其他", "有关", "相关", "下列", "之一",
        "境内", "境外", "领域", "区域", "范围",
        "除外", "例外", "单独", "分别",
        "国家", "地方", "各级", "县级", "本级", "自治区", "直辖市",
        "个人", "单位", "企业", "公司", "组织", "机构", "机关",
        "当事人", "人员", "工作人员", "公民", "未成年人", "经营者",
        "及其", "或者", "以及",
    ],
    # ── 限制性规范（门槛/数量/程度） ──
    "threshold": [
        "以上", "以下", "不超过", "不得超过", "不低于", "不少于",
        "条件", "标准", "质量", "数量", "金额", "数额",
        "期限", "期间", "定期", "限期",
        "制度", "规范", "要求", "需要",
        "严重", "重大", "较大", "轻微",
        "有期徒刑", "情节严重", "构成犯罪", "依法追究",
    ],
    # ── 权利规范（权利/保护/利益） ──
    "right": [
        "有权", "权利", "权限", "允许",
        "保护", "保障", "保证", "维护",
        "利益", "权益", "合法", "合理",
        "自由", "平等", "公平", "公正",
        "申请", "请求", "提出", "主张",
        "鼓励", "支持", "促进", "推动",
        "使用权", "授权", "职权", "债权人",
    ],
    # ── 手续规范（程序/行为/处置） ──
    "procedure": [
        "程序", "步骤", "方式", "手续",
        "批准", "许可", "核准", "登记", "注册", "备案",
        "审查", "审核", "检查", "检验", "检测", "调查",
        "报告", "通知", "公告", "公示", "告知",
        "协商", "协议", "约定", "合同",
        "组织", "实施", "开展", "进行", "采取", "使用",
        "处理", "处置", "管理", "监督",
        "办理", "设立", "建立", "实行", "适用",
        "审计", "审批", "确定", "取得",
    ],
}

#敏感词分类权重
CATEGORY_WEIGHT = {
    "negation": 1.5,
    "obligation": 1.3,
    "scope": 1.2,
    "threshold": 1.2,
    "right": 1.0,
    "procedure": 0.8,
}

# 敏感词分类函数
def classify_word(word: str) -> str | None:
    for category, keywords in SENSITIVE_WORD_CATEGORIES.items():
        if word in keywords:
            return category
    return None


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------

@dataclass
class SensitiveWordDelta:
    """敏感词变化"""
    word: str
    old_category: str | None    # 旧分类
    new_category: str | None    # 新分类
    category_shifted: bool      # 跨分类变动（如义务→权利）
    polarity_flipped: bool     # 极性翻转（如"不"字增减）
    legal_impact: str          # "重大" / "中等" / "轻微"


@dataclass
class LineageStep:
    """
    血缘链中的单一步骤
    记录当前版本与前一版本的对比结果
    """
    version_label: str              # effective_start，标记这是哪个版本
    derived_from_article: str | None  # 源自前版本的哪一条
    similarity_with_prev: float | None
    drift_score: float | None        # 1 - similarity
    change_type: str                # "微调" / "实质性修订" / "重大修订" / "新增" / "实质性权利变动"
    is_split: bool = False           # 1 → N
    is_merge: bool = False          # M → 1
    sensitive_deltas: list[SensitiveWordDelta] = field(default_factory=list)
    has_critical_change: bool = False  # category_shift 或 polarity_flip
    is_metadata_change: bool = False    # True = 仅施行日期变更，不计入法理修订


@dataclass
class ChunkLineage:
    """单个 Chunk 的血缘信息"""
    chunk_idx: int # 段落索引
    article_no: str | None # 条款编号

    # 完整血缘链（从当前版本往前追溯的所有步骤）
    lineage_chain: list[LineageStep] = field(default_factory=list)

    # 是否有历史版本（用于快速判断）
    has_prev_version: bool = False

    # 当前版本的元数据
    embed_model_version: str | None = None # Embedding 模型版本
    lineage_id: str | None = None   # 跨版本唯一 UID

    # 该 Chunk 源自哪些旧版 Article（用于合并检测）
    derived_from: list[str | None] = field(default_factory=list)


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t for t in jieba.lcut(text) if t.strip()]


def _cosine_sim(v1: list[float], v2: list[float]) -> float:
    a = np.array(v1)
    b = np.array(v2)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm < 1e-9:
        return 0.0
    return float(dot / norm)


def generate_lineage_id(doc_title: str, article_no: str | None) -> str:
    key = f"{doc_title}_{article_no or 'unknown'}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------
# 敏感词变化检测
# ----------------------------------------------------------------------
def detect_sensitive_word_delta(old_text: str, new_text: str) -> list[SensitiveWordDelta]:
    """检测 old_text → new_text 中的敏感词变化"""
    old_words = set(_tokenize(old_text))
    new_words = set(_tokenize(new_text))

    added = new_words - old_words
    removed = old_words - new_words

    deltas: list[SensitiveWordDelta] = []
    all_changed = added | removed

    for word in all_changed:
        old_cat = classify_word(word) if word in removed else None
        new_cat = classify_word(word) if word in added else None

        # 跨分类检测
        category_shifted = (
            old_cat is not None and new_cat is not None and old_cat != new_cat
        )

        # 极性翻转检测
        polarity_flipped = False
        if word in SENSITIVE_WORD_CATEGORIES["negation"] and word in removed:
            # 检查是否"不X"变没了
            for neg in SENSITIVE_WORD_CATEGORIES["negation"]:
                if neg in old_text and neg not in new_text:
                    polarity_flipped = True
                    break

        # 法律影响评估
        if category_shifted:
            legal_impact = "重大"
        elif polarity_flipped:
            legal_impact = "重大"
        elif old_cat in ("obligation", "scope", "threshold") or new_cat in ("obligation", "scope", "threshold"):
            legal_impact = "中等"
        else:
            legal_impact = "轻微"

        deltas.append(SensitiveWordDelta(
            word=word,
            old_category=old_cat,
            new_category=new_cat,
            category_shifted=category_shifted,
            polarity_flipped=polarity_flipped,
            legal_impact=legal_impact,
        ))

    return deltas


# ----------------------------------------------------------------------
# change_type 判定
# ----------------------------------------------------------------------
def _classify_change_type(
    similarity: float | None,
    deltas: list[SensitiveWordDelta],
) -> str:
    if similarity is None:
        return "新增"

    # category_shift 直接判定为"实质性权利变动"
    if any(d.category_shifted for d in deltas):
        return "实质性权利变动"

    # 极性翻转降档
    if any(d.polarity_flipped for d in deltas):
        if similarity > 0.90:
            return "实质性修订"
        return "重大修订"

    # 正常阈值判定（法律语义漂移阈值：0.2）
    if similarity > 0.95:
        return "微调"        # drift < 0.05：纯文字润色
    elif similarity >= 0.80:
        return "实质性修订"  # drift 0.05-0.2：法理逻辑变化
    else:
        return "重大修订"     # drift >= 0.2：重大结构变化


# ----------------------------------------------------------------------
# 血缘发现核心（基于向量相似度和 BM25）
# ----------------------------------------------------------------------
class LineageDiscoverer:
    """
    对两个版本的 Chunk 列表进行语义血缘发现
    只做 1:1 对比（新版每个 Chunk 找最相似的旧版 Chunk）
    拆分/合并检测在调用侧处理
    """
# 输入参数
    def __init__(
        self,
        new_chunks: list[Chunk],
        prev_chunks: list[Chunk],
        embed_model_version: str,
    ):
        self.new_chunks = new_chunks
        self.prev_chunks = prev_chunks
        self.embed_model_version = embed_model_version

        self._new_embeddings: list[list[float]] | None = None
        self._prev_embeddings: list[list[float]] | None = None
        self._bm25: BM25Okapi | None = None
#确保嵌入模型版本一致
    def _ensure_embeddings(self) -> None:
        if self._new_embeddings is None:
            texts = [c.text for c in self.new_chunks]
            self._new_embeddings = embed_texts(texts)

        if self._prev_embeddings is None:
            texts = [c.text for c in self.prev_chunks]
            self._prev_embeddings = embed_texts(texts)

        if self._bm25 is None:
            corpus = [_tokenize(c.text) for c in self.prev_chunks]
            self._bm25 = BM25Okapi(corpus)

# 计算融合分数
    def _compute_fused_score(
        self,
        new_vec: list[float],
        old_vec: list[float],
        bm25_score: float,
    ) -> float:
        """向量相似度(0.65) + BM25(0.35) 融合"""
        vec_sim = _cosine_sim(new_vec, old_vec)
        bm25_norm = min(bm25_score / 10.0, 1.0) if bm25_score > 0 else 0.0
        return 0.65 * vec_sim + 0.35 * bm25_norm


    def discover(self, prev_version_label: str) -> list[ChunkLineage]:
        """
        对每个新版 Chunk，在旧版本中寻找血缘关系
        返回每个新 Chunk 的血缘信息（不含 lineage_chain，需要调用侧拼接）
        """
        self._ensure_embeddings()

        # 统计每个旧版 Article 被多少新 Chunk 引用（用于拆分检测）
        derived_count: dict[str, int] = defaultdict(int)

        # 按 (article_no编码, item_no项编码) 建立旧版 chunk 索引，加速精确匹配
        old_index: dict[tuple[str | None, str | None], list[int]] = defaultdict(list)
        for oi, old_c in enumerate(self.prev_chunks):
            key = (old_c.article_no, old_c.item_no)
            old_index[key].append(oi)
        # 初始化血缘列表，用于返回结果
        lineages: list[ChunkLineage] = []

        # 遍历新版 chunk，寻找血缘关系
        for ni, new_c in enumerate(self.new_chunks):
            new_vec = self._new_embeddings[ni]
            bm25_scores = self._bm25.get_scores(_tokenize(new_c.text))

            # ----------------------------------------------------------
            # 精确匹配优先：同一法律、同一 article_no、同一 item_no
            # 这是"分块幂等性"的保障：同一条号在不同版本切出相同数量 chunk 时，
            # 对应的 item_no 应该直接匹配，不走向量融合
            # ----------------------------------------------------------
            exact_match_idx = -1
            for oi in old_index.get((new_c.article_no, new_c.item_no), []):
                old_c = self.prev_chunks[oi]
                if old_c.article_no == new_c.article_no and old_c.item_no == new_c.item_no:
                    exact_match_idx = oi
                    break
                    
            lineage = ChunkLineage(
                chunk_idx=ni,
                article_no=new_c.article_no,
                has_prev_version=True,
                embed_model_version=self.embed_model_version,
            )

            # Case 1：精确匹配成功（同 article_no + item_no）
            if exact_match_idx >= 0:
                best_old = self.prev_chunks[exact_match_idx]
                # 文本完全一致 → 纯平移
                if new_c.text.strip() == best_old.text.strip():
                    step = LineageStep(
                        version_label=prev_version_label,
                        derived_from_article=best_old.article_no,
                        similarity_with_prev=1.0,
                        drift_score=0.0,
                        change_type="微调",
                        sensitive_deltas=[],
                        has_critical_change=False,
                    )
                else:
                    # 文本不同但条号相同 → 检查语义相似度
                    fused_sim = self._compute_fused_score(
                        new_vec, self._prev_embeddings[exact_match_idx], bm25_scores[exact_match_idx]
                    )

                    # 语义锚定阈值（来自用户设计的三门禁逻辑）
                    # Level 3: 编号重分配检测
                    # 若同一 article_no 但语义相似度 < 0.3，说明该编号已被"回收再分配"
                    # 这种情况不应建立血缘关系，应标记为"新增"（跨版本独立条文）
                    if fused_sim < 0.3:
                        # article_no 编号被重分配，当前条文本质上是"新条文"
                        step = LineageStep(
                            version_label=prev_version_label,
                            derived_from_article=None,  # 不继承旧版
                            similarity_with_prev=None,
                            drift_score=None,
                            change_type="新增",
                        )
                        lineage.derived_from = []
                    else:
                        deltas = detect_sensitive_word_delta(best_old.text, new_c.text)
                        step = LineageStep(
                            version_label=prev_version_label,
                            derived_from_article=best_old.article_no,
                            similarity_with_prev=fused_sim,
                            drift_score=round(1.0 - fused_sim, 4),
                            change_type=_classify_change_type(fused_sim, deltas),
                            sensitive_deltas=deltas,
                            has_critical_change=any(d.category_shifted or d.polarity_flipped for d in deltas),
                        )
                        lineage.derived_from = [best_old.article_no]
                lineage.lineage_chain = [step]
                lineages.append(lineage)
                continue

            # Case 2：精确匹配失败 → 全文向量搜索
            # 但增加 Level 2 语义迁移检测：若某旧版 Chunk 与新版 Chunk 相似度 > 0.9
            # 则认为该法条"迁址"了（article_no 改变但内容延续）
            best_old_idx = -1
            best_score = -1.0
            migration_candidate_idx = -1  # 用于记录可能的法条迁址
            migration_candidate_score = 0.0

            for oi, old_c in enumerate(self.prev_chunks):
                score = self._compute_fused_score(
                    new_vec, self._prev_embeddings[oi], bm25_scores[oi]
                )
                if score > best_score:
                    best_score = score
                    best_old_idx = oi

                # 记录潜在的法条迁址（跨 article_no 的高相似匹配）
                # Level 2 阈值: similarity > 0.9 视为法条搬家
                if score > 0.9 and old_c.article_no != new_c.article_no:
                    if score > migration_candidate_score:
                        migration_candidate_score = score
                        migration_candidate_idx = oi

            # Level 2: 法条迁址检测
            # 若最佳匹配来自不同 article_no，且相似度 > 0.9，说明条文"搬家"了
            # 这是重要法律信息，应在 derived_from 中记录，并在 drift 中体现
            if migration_candidate_idx >= 0 and migration_candidate_score >= 0.9:
                migration_old = self.prev_chunks[migration_candidate_idx]
                # 仅当迁址匹配得分高于精确匹配失败后的默认匹配得分时才采纳
                if migration_candidate_score > best_score:
                    best_old = migration_old
                    best_score = migration_candidate_score
                    best_old_idx = migration_candidate_idx

            if best_old_idx >= 0 and best_score > 0.3:
                best_old = self.prev_chunks[best_old_idx]

                deltas = detect_sensitive_word_delta(best_old.text, new_c.text)

                # 记录真实来源（旧 article_no）
                lineage.derived_from = [best_old.article_no] if best_old.article_no else []

                # 日期噪声检测：仅施行日期变更的条文，标记为 is_metadata_change
                metadata_change = is_date_clause_text(new_c.text) or is_date_clause_text(best_old.text)

                step = LineageStep(
                    version_label=prev_version_label,
                    derived_from_article=best_old.article_no,
                    similarity_with_prev=best_score,
                    drift_score=round(1.0 - best_score, 4),
                    change_type=_classify_change_type(best_score, deltas),
                    sensitive_deltas=deltas,
                    has_critical_change=any(d.category_shifted or d.polarity_flipped for d in deltas),
                    is_metadata_change=metadata_change,
                )
                lineage.lineage_chain = [step]

                if best_old.article_no:
                    derived_count[best_old.article_no] += 1

            else:
                # 无相似版本 → 当前版本新增
                step = LineageStep(
                    version_label=prev_version_label,
                    derived_from_article=None,
                    similarity_with_prev=None,
                    drift_score=None,
                    change_type="新增",
                )
                lineage.lineage_chain = [step]

            lineage.lineage_id = generate_lineage_id(new_c.doc_title, new_c.article_no)
            lineages.append(lineage)

        # 第二遍：标记拆分
        # is_split：同一个旧版 Article 产生多个新版 Chunk（1→N）
        # is_merge（M:1）：当前算法只记录每个新版 Chunk 的最佳旧版，无法直接检测，
        #                 需要后续算法改进（每个新版 Chunk 支持多个来源）
        for lin in lineages:
            if lin.lineage_chain and lin.lineage_chain[0].derived_from_article:
                primary = lin.lineage_chain[0].derived_from_article
                if derived_count[primary] > 1:
                    lin.lineage_chain[0].is_split = True
                # is_merge 暂时禁用，需要算法支持多个旧来源
                # if len([l for l in lineages if l.lineage_chain and l.lineage_chain[0].derived_from_article == primary]) > 1:
                #     lin.lineage_chain[0].is_merge = True

        return lineages


# ----------------------------------------------------------------------
# 主入口：链式血缘构建
# ----------------------------------------------------------------------
def build_version_lineage(
    new_chunks: list[Chunk],
    prev_chunks: list[Chunk],
    doc_title: str,
    prev_version_label: str | None,  # 前一个版本的 effective_start
    embed_model_version: str,
) -> list[ChunkLineage]:
    """
    链式血缘：处理单个版本的血缘发现

    输入：
        new_chunks: 当前版本的 Chunk 列表
        prev_chunks: 前一个版本的 Chunk 列表
        prev_version_label: 前一个版本的 effective_start

    输出：
        每个新 Chunk 的 ChunkLineage，其中 lineage_chain 包含：
        - 从 prev_version 继承的完整链（如果有的话）
        - 当前版本与 prev_version 的对比结果作为最新一步

    设计：链式追溯
    - 处理 v2→v1 时，得到 v2 的 lineage_chain = [step(v2→v1)]
    - 处理 v3→v2 时，v3 的 chunk 先复制 v2 的完整 lineage_chain，
      然后 prepend step(v3→v2)，最终得到 [step(v3→v2), step(v2→v1)]
    """
    if not prev_version_label or not prev_chunks:
        # 单版本法律（无历史）→ 全部为新增
        current_version = embed_model_version
        lineages = []
        for i, c in enumerate(new_chunks):
            lineages.append(ChunkLineage(
                chunk_idx=i,
                article_no=c.article_no,
                lineage_chain=[
                    LineageStep(
                        version_label="initial",
                        derived_from_article=None,
                        similarity_with_prev=None,
                        drift_score=None,
                        change_type="新增",
                    )
                ],
                has_prev_version=False,
                embed_model_version=current_version,
                lineage_id=generate_lineage_id(doc_title, c.article_no),
            ))
        return lineages

    # 与前版本对比
    discoverer = LineageDiscoverer(new_chunks, prev_chunks, embed_model_version)
    lineages = discoverer.discover(prev_version_label)

    # 链式追溯：将前版本的 lineage_chain 接到当前步骤之前
    # 关键：prev_chunks 中的每个 Chunk 对象已经有 lineage_chain（由前一轮写入）
    #       我们需要将 prev_chunks[i] 的 lineage_chain 与当前的 lineage_chain[i] 拼接
    #       通过 article_no 匹配（或直接按索引，因为两个列表的 chunks 已按 article_no 排序）
    for ni, new_c in enumerate(new_chunks):
        lin = lineages[ni]
        # 找到 prev_chunks 中与当前 new_c 对应的 Chunk（按 article_no 匹配）
        matching_prev = None
        for prev_c in prev_chunks:
            if prev_c.article_no == new_c.article_no:
                matching_prev = prev_c
                break
        if matching_prev:
            prev_lineage = getattr(matching_prev, 'lineage_chain', None) or []
            if prev_lineage:
                lin.lineage_chain = prev_lineage + lin.lineage_chain

    return lineages


# ----------------------------------------------------------------------
# 工具：打印 lineage 报告
# ----------------------------------------------------------------------
def lineage_summary(lineages: list[ChunkLineage]) -> str:
    change_types = [l.lineage_chain[-1].change_type for l in lineages if l.lineage_chain]
    from collections import Counter
    counter = Counter(change_types)

    splits = sum(1 for l in lineages if l.lineage_chain and l.lineage_chain[-1].is_split)
    merges = sum(1 for l in lineages if l.lineage_chain and l.lineage_chain[-1].is_merge)
    critical = sum(1 for l in lineages if l.lineage_chain and l.lineage_chain[-1].has_critical_change)

    parts = [f"total={len(lineages)}", f"types={dict(counter)}"]
    if splits:
        parts.append(f"split={splits}")
    if merges:
        parts.append(f"merge={merges}")
    if critical:
        parts.append(f"critical={critical}")
    return " | ".join(parts)


# ----------------------------------------------------------------------
# Embedding 模型版本检查
# ----------------------------------------------------------------------
def check_embed_model_version(stored_version: str | None, current_version: str) -> bool:
    if stored_version is None:
        return True
    return current_version == stored_version


def get_embed_model_version() -> str:
    return settings.local_embed_model


# ----------------------------------------------------------------------
# 序列化 helpers
# ----------------------------------------------------------------------
def lineage_to_dict(lin: ChunkLineage) -> dict:
    return asdict(lin)


def dict_to_lineage(d: dict) -> ChunkLineage:
    steps = []
    for step_dict in d.get("lineage_chain", []):
        steps.append(step_from_dict(step_dict))
    d["lineage_chain"] = steps
    return ChunkLineage(**d)


def step_from_dict(step_dict: dict) -> LineageStep:
    """将 dict 反序列化为 LineageStep（供 ingest.py 等外部模块使用）"""
    deltas = []
    for delta_dict in step_dict.get("sensitive_deltas", []):
        deltas.append(SensitiveWordDelta(**delta_dict))
    step_dict = dict(step_dict)
    step_dict["sensitive_deltas"] = deltas
    return LineageStep(**step_dict)